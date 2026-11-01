"""Optimizer formulations and their data-quality boundaries.

Public strategies on identical inputs:
  traditional      — district crop-mix from DES area shares (no solver)
  lp_max_profit    — SciPy HiGHS, expected profit only
  qp_balanced      — compatibility id; LP expected-profit while risk QP is gated
  qp_drought_safe  — compatibility id; LP with drought-scenario water cap

LP formulation (all money in Rs, area in acres, water in m3):

  max_x sum_i E[margin_i] x_i
  s.t.  sum_i x_i <= land,
        sum_i cost_i x_i <= budget,
        sum_i net_irrigation_need_i(s) x_i <= irrigation_supply(s),
        0 <= x_i <= diversification_cap * land.

``net_irrigation_need`` is compared with irrigation-only supply; effective
rainfall is already deducted when the data layer constructs demand. There is
no default discrete minimum area, activation, or rotation rule because the
available datasets do not support defensible values. A MILP must only be added
when those farm/business requirements are collected.

The CVXPY QP remains experimental. It is not selected unless validated joint
crop-profit observations are provided; three weather scenarios are not a
covariance dataset.

OPT.4  Infeasibility report: every strategy records which constraints are
       binding/violated and by how much.
OPT.5  Impact vs Traditional: water_saved_pct, fertilizer_saved_pct,
       drought_profit_gain_rs.

Long-duration crops (duration_days > LONG_DURATION_DAYS):
  use their sourced per-crop planning-period margin without annualising a
  subset of crops.  A multi-period model is required before comparing
  follow-on cropping opportunities or annual returns.
"""

from __future__ import annotations

import logging
import math
import time
from typing import TYPE_CHECKING

import numpy as np

from app.ml.constants import (
    DIVERSIFICATION_CAP,
    DIVERSIFICATION_CAP_DEFAULT,
    LONG_DURATION_DAYS,
    PSD_RIDGE,
    RISK_LAMBDA,
    RISK_QP_DISABLE_REASON,
    RISK_QP_ENABLED,
    RISK_OBJECTIVE_SCALE_RS,
    SATURATION_GAMMA,
    SCENARIO_WEIGHTS_DEFAULT,
    WARN_OLD_COST_YEAR,
    WARN_SINGLE_SEASON_COMPARISON,
)
from app.schemas import (
    Allocation,
    ConstraintDetail,
    FinanceSummary,
    Impact,
    Infeasibility,
    OptimizerInputs,
    ProfitByScenario,
    RevenueByScenario,
    RelaxationApplied,
    SolverInfo,
    SourcedValue,
    StrategyResult,
    StrategyTotals,
    Warning,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Scenario index helpers ────────────────────────────────────────────────────
_SCEN_IDX = {"drought": 0, "normal": 1, "excess": 2}
_SCEN_KEYS = ("drought", "normal", "excess")


# ── Diversification cap ───────────────────────────────────────────────────────

def _div_cap(n: int) -> float:
    """Return the diversification cap for n eligible crops."""
    return DIVERSIFICATION_CAP.get(n, DIVERSIFICATION_CAP_DEFAULT)


# ── Long-duration normalisation ───────────────────────────────────────────────

def _year_fraction(duration_days: int) -> float:
    """Fraction of a year the crop occupies the land."""
    return duration_days / 365.0


def _annual_margin(margin_s: float, duration_days: int) -> float:
    """Return the seasonal margin used by the one-season formulation.

    Earlier code annualised only long-duration crop returns. That changes one
    crop's objective without modelling its foregone next crop or resources, so
    it is mathematically inconsistent. Keep the helper for callers, but make
    the fixed planning horizon explicit.
    """
    return margin_s


# ── Build per-crop vectors ────────────────────────────────────────────────────

def _build_vectors(inputs: OptimizerInputs) -> dict:
    """Pre-compute per-crop vectors used by all solvers.

    Returns a dict with:
      n          — number of crops
      crop_ids   — list of crop_id strings
      land       — farmer land (acres)
      budget     — farmer budget (Rs)
      water_by_s — list[n] water_need_m3 per scenario (drought/normal/excess)
      cost       — list[n] cost_rs_per_acre
      margin     — (3, n) array: margin[s][i] = expected_profit per acre in scenario s
      margin_ann — (3, n) array: seasonal margin (legacy key name)
      duration   — list[n] duration_days
      weights    — [3] scenario weights
      water_cap  — dict scenario→float (total available m3 from WaterBudget)
    """
    crops = inputs.candidates
    n = len(crops)
    L = inputs.profile.land_acres
    B = inputs.profile.budget_rs
    W = {sc.scenario: sc.available_m3.total.value for sc in inputs.water_budgets}
    weights = list(inputs.scenario_weights) if inputs.scenario_weights else list(SCENARIO_WEIGHTS_DEFAULT)

    cost = np.array([
        c.cost_per_acre.total_rs for c in crops
    ], dtype=float)

    # margin[s][i] = yield * expected_harvest_price - cost_per_acre
    # We use profit_rs_per_acre which the pipeline already computed
    margin = np.array([
        [getattr(c.profit_rs_per_acre, s) for c in crops]
        for s in _SCEN_KEYS
    ], dtype=float)   # shape (3, n)

    # Fixed seasonal horizon; do not annualise a subset of crops.
    duration = [c.duration_days for c in crops]
    margin_ann = np.array([
        [_annual_margin(margin[si][i], duration[i]) for i in range(n)]
        for si in range(3)
    ], dtype=float)

    water_by_s = np.array([
        [c.water_need_m3_per_acre.drought.value if s == "drought"
         else c.water_need_m3_per_acre.normal.value if s == "normal"
         else c.water_need_m3_per_acre.excess.value
         for c in crops]
        for s in _SCEN_KEYS
    ], dtype=float)   # shape (3, n)

    return {
        "n": n, "crop_ids": [c.crop_id for c in crops],
        "L": L, "B": B, "W": W, "weights": weights,
        "cost": cost, "margin": margin, "margin_ann": margin_ann,
        "water_by_s": water_by_s, "duration": duration,
    }


# ── Risk matrix (Σ) ───────────────────────────────────────────────────────────

def _risk_matrix(vecs: dict) -> np.ndarray:
    """Experimental covariance helper; not valid for public recommendations.

    ``margin_ann`` contains three constructed weather scenarios, not historical
    joint yield/harvest-price observations. The public dispatcher gates QP
    through ``RISK_QP_ENABLED``; this helper remains for future validation.
    """
    n = vecs["n"]
    margin = vecs["margin_ann"]  # (3, n)
    weights = np.array(vecs["weights"])
    # Weighted mean
    mean = (weights[:, None] * margin).sum(axis=0)  # (n,)
    # Weighted covariance
    diff = margin - mean[None, :]  # (3, n)
    cov = (weights[:, None, None] * diff[:, :, None] * diff[:, None, :]).sum(axis=0)
    # PSD ridge: PSD_RIDGE × trace(Σ)
    ridge = PSD_RIDGE * np.trace(cov) if np.trace(cov) > 0 else PSD_RIDGE
    cov += ridge * np.eye(n)
    return cov


# ── LP solver (OPT.1) ─────────────────────────────────────────────────────────

def _solve_lp(vecs: dict, safety_scenario: str = "normal") -> tuple[np.ndarray | None, str, str]:
    """SciPy HiGHS LP: maximize expected profit subject to constraints."""
    from scipy.optimize import linprog

    n = vecs["n"]
    if n == 0:
        return None, "HiGHS", "no candidates"
    L, B = vecs["L"], vecs["B"]
    W_s = vecs["W"].get(safety_scenario, float("inf"))
    cap = float(vecs.get("_force_cap", _div_cap(n)))
    weights = vecs["weights"]

    # Objective: -expected_profit (linprog minimises)
    c_obj = -np.array([
        sum(weights[s] * vecs["margin_ann"][s][i] for s in range(3))
        for i in range(n)
    ])

    # Inequality constraints: A_ub @ x <= b_ub
    rows, rhs = [], []
    # Land: Σ xᵢ ≤ L
    rows.append(np.ones(n))
    rhs.append(L)
    # Budget: Σ cost_i * xᵢ ≤ B
    rows.append(vecs["cost"])
    rhs.append(B)
    # Water: Σ water_i(s*) * xᵢ ≤ W(s*)
    si = _SCEN_IDX[safety_scenario]
    rows.append(vecs["water_by_s"][si])
    rhs.append(W_s)
    # Diversification cap: xᵢ ≤ cap * L  for each crop
    for i in range(n):
        r = np.zeros(n)
        r[i] = 1.0
        rows.append(r)
        rhs.append(cap * L)

    A_ub = np.array(rows, dtype=float)
    b_ub = np.array(rhs, dtype=float)

    t0 = time.monotonic()
    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub,
                  bounds=[(0, None)] * n, method="highs")
    ms = int((time.monotonic() - t0) * 1000)

    if res.status == 0:
        return res.x, "HiGHS", f"optimal ({ms} ms)"
    return None, "HiGHS", res.message


# ── QP solver (OPT.2) ─────────────────────────────────────────────────────────

def _solve_qp(
    vecs: dict,
    risk_lambda: float,
    safety_scenario: str = "normal",
) -> tuple[np.ndarray | None, str, str]:
    """Experimental CVXPY QP; public planning does not call it while gated."""
    n = vecs["n"]
    if n == 0:
        return None, "CVXPY", "no candidates"
    try:
        import cvxpy as cp
    except ImportError:
        logger.warning("cvxpy not installed — falling back to LP")
        return _solve_lp(vecs, safety_scenario)

    n = vecs["n"]
    L, B = vecs["L"], vecs["B"]
    W_s = vecs["W"].get(safety_scenario, float("inf"))
    cap = float(vecs.get("_force_cap", _div_cap(n)))
    weights = np.array(vecs["weights"])
    Sigma = _risk_matrix(vecs)

    x = cp.Variable(n, nonneg=True)

    # Expected seasonal profit
    exp_profit = sum(
        weights[s] * (vecs["margin_ann"][s] @ x)
        for s in range(3)
    )

    # Risk term: λ · xᵀ Σ x
    risk_term = risk_lambda * cp.quad_form(x, Sigma) / RISK_OBJECTIVE_SCALE_RS

    # Saturation (γ = 0 for single farm, no effect)
    sat_term = SATURATION_GAMMA * cp.sum_squares(x)

    objective = cp.Maximize(exp_profit - risk_term - sat_term)

    constraints = [
        cp.sum(x) <= L,                          # land
        vecs["cost"] @ x <= B,                   # budget
        vecs["water_by_s"][_SCEN_IDX[safety_scenario]] @ x <= W_s,  # water
    ]
    # Diversification cap
    for i in range(n):
        constraints.append(x[i] <= cap * L)

    t0 = time.monotonic()
    prob = cp.Problem(objective, constraints)

    # Try solvers in order: Clarabel → OSQP → ECOS
    for solver in [cp.CLARABEL, cp.OSQP, cp.ECOS]:
        try:
            prob.solve(solver=solver, verbose=False)
            if prob.status in ("optimal", "optimal_inaccurate"):
                ms = int((time.monotonic() - t0) * 1000)
                return x.value, solver, f"{prob.status} ({ms} ms)"
        except Exception:
            continue

    return None, "CVXPY", f"infeasible or solver failed: {prob.status}"


# ── Constraint diagnosis (OPT.4) ──────────────────────────────────────────────

def _diagnose(
    x: np.ndarray | None,
    vecs: dict,
    safety_scenario: str,
) -> tuple[list[str], Infeasibility | None]:
    """Return (binding_constraints, infeasibility_payload)."""

    n = vecs["n"]
    si = _SCEN_IDX[safety_scenario]
    L, B = vecs["L"], vecs["B"]
    W_s = vecs["W"].get(safety_scenario, float("inf"))

    if x is None:
        # Build infeasibility report
        details = []
        details.append(ConstraintDetail(
            constraint="land",
            required_rs=None, available_rs=None, shortfall_rs=0.0,
            required_m3=None, available_m3=None, shortfall_m3=0.0,
        ))
        min_budget = float(np.min(vecs["cost"])) * L if n > 0 else float("inf")
        details.append(ConstraintDetail(
            constraint="budget",
            required_rs=min_budget, available_rs=B,
            shortfall_rs=max(0.0, min_budget - B),
        ))
        min_water = float(np.min(vecs["water_by_s"][si])) * L if n > 0 else float("inf")
        details.append(ConstraintDetail(
            constraint="water",
            required_m3=min_water, available_m3=W_s,
            shortfall_m3=max(0.0, min_water - W_s),
        ))
        violated = [d.constraint for d in details if (d.shortfall_rs or 0) > 0 or (d.shortfall_m3 or 0) > 0]
        inf = Infeasibility(
            binding=[], violated=violated,
            detail=details, relaxations_tried=[],
            suggestion_code=None, suggestion_params={},
        )
        return [], inf

    # x is a valid solution — find binding constraints
    binding = []
    land_used = float(x.sum())
    if L > 0 and (L - land_used) / L < 0.01:
        binding.append("land")

    budget_used = float(vecs["cost"] @ x)
    if B > 0 and (B - budget_used) / B < 0.01:
        binding.append("budget")

    water_used = float(vecs["water_by_s"][si] @ x)
    if W_s < float("inf") and W_s > 0 and (W_s - water_used) / W_s < 0.01:
        binding.append("water")

    return binding, None


_MIN_PLAN_ACRES = 0.01


def _empty_plan_infeasibility(vecs: dict, safety_scenario: str) -> Infeasibility:
    """Explain why a solver-feasible optimum allocates (almost) no land.

    ``NO_POSITIVE_ALLOCATION`` is reserved for the case where no candidate
    has a positive scenario-weighted margin (the UI tells the farmer every
    crop loses money).  If profitable crops exist, the empty plan is caused
    by a resource limit, which is reported in ``violated``/``detail``.
    """
    n = vecs["n"]
    weights = np.asarray(vecs["weights"], dtype=float)
    expected_margin = (
        (weights[:, None] * vecs["margin_ann"]).sum(axis=0) if n > 0 else np.zeros(0)
    )
    profitable = [i for i in range(n) if expected_margin[i] > 0]
    if not profitable:
        return Infeasibility(
            binding=[], violated=[], detail=[], relaxations_tried=[],
            suggestion_code="NO_POSITIVE_ALLOCATION",
            suggestion_params={"reason": "no_crop_has_positive_expected_margin"},
        )

    L, B = float(vecs["L"]), float(vecs["B"])
    W_s = float(vecs["W"].get(safety_scenario, float("inf")))
    si = _SCEN_IDX[safety_scenario]
    min_cost = float(min(vecs["cost"][i] for i in profitable))
    min_water = float(min(vecs["water_by_s"][si][i] for i in profitable))
    plantable = {
        "land": L,
        "budget": B / min_cost if min_cost > 0 else float("inf"),
        "water": W_s / min_water if min_water > 0 else float("inf"),
    }
    violated = [name for name, acres in plantable.items() if acres < _MIN_PLAN_ACRES]
    details = []
    if "budget" in violated:
        need = min_cost * _MIN_PLAN_ACRES
        details.append(ConstraintDetail(
            constraint="budget", required_rs=round(need, 2), available_rs=B,
            shortfall_rs=round(max(0.0, need - B), 2),
        ))
    if "water" in violated:
        need = min_water * _MIN_PLAN_ACRES
        details.append(ConstraintDetail(
            constraint="water", required_m3=round(need, 2), available_m3=W_s,
            shortfall_m3=round(max(0.0, need - W_s), 2),
        ))
    if "land" in violated:
        details.append(ConstraintDetail(constraint="land"))
    return Infeasibility(
        binding=violated, violated=violated, detail=details, relaxations_tried=[],
        suggestion_code="RESOURCE_LIMIT_BLOCKS_ALLOCATION" if violated else "NO_ALLOCATION_FOUND",
        suggestion_params={
            "limiting": violated,
            "safety_scenario": safety_scenario,
            "profitable_crop_ids": [vecs["crop_ids"][i] for i in profitable],
            "min_plan_acres": _MIN_PLAN_ACRES,
        },
    )


# ── Relaxation ladder ─────────────────────────────────────────────────────────

def _try_relaxations(
    vecs: dict,
    risk_lambda: float,
    safety_scenario: str,
    use_qp: bool,
) -> tuple[np.ndarray | None, list[RelaxationApplied], dict, str]:
    """Try the 4-step relaxation ladder (ml/SPECS §8.4a) until feasible.

    Returns (x, relaxations_applied, modified_vecs, effective_safety_scenario).
    x is None if still infeasible after all steps.
    """
    relaxations: list[RelaxationApplied] = []
    v = dict(vecs)  # shallow copy — we modify L/W/crops
    n = v["n"]

    _solver = _solve_qp if use_qp else _solve_lp

    # Step 1: Lift diversification cap to 1.0
    orig_cap = _div_cap(n)
    if orig_cap < 1.0:
        v1 = dict(v, _force_cap=1.0)
        x, _, status = _solver(v1, risk_lambda, safety_scenario) if use_qp else _solver(v1, safety_scenario)  # type: ignore[call-arg]
        if x is not None and _is_feasible(x, v1, safety_scenario):
            relaxations.append(RelaxationApplied(step="CAP_TO_1", params={}))
            return x, relaxations, v1, safety_scenario

    # Step 2: Reduce planned area to what the budget allows
    if v["n"] > 0 and np.min(v["cost"]) > 0:
        max_acres = float(v["B"] / np.min(v["cost"]))
        if max_acres < v["L"] * 0.99:
            v2 = dict(v, L=max_acres)
            x, _, status = _solver(v2, risk_lambda, safety_scenario) if use_qp else _solver(v2, safety_scenario)  # type: ignore[call-arg]
            if x is not None and _is_feasible(x, v2, safety_scenario):
                relaxations.append(RelaxationApplied(
                    step="REDUCE_AREA",
                    params={"original_acres": v["L"], "feasible_acres": round(max_acres, 2)},
                ))
                return x, relaxations, v2, safety_scenario

    # Step 3: Drop the most water-hungry crop
    if v["n"] > 1:
        si = _SCEN_IDX.get(safety_scenario, 1)
        water_per_acre = v["water_by_s"][si]
        drop_idx = int(np.argmax(water_per_acre))
        drop_id = v["crop_ids"][drop_idx]
        v3 = _drop_crop(v, drop_idx)
        x, _, status = _solver(v3, risk_lambda, safety_scenario) if use_qp else _solver(v3, safety_scenario)  # type: ignore[call-arg]
        if x is not None and _is_feasible(x, v3, safety_scenario):
            relaxations.append(RelaxationApplied(
                step="DROP_WATER_HUNGRY_CROP",
                params={"dropped_crop_id": drop_id},
            ))
            return x, relaxations, v3, safety_scenario

    # Step 4: Move water limit from safety scenario to Normal
    if safety_scenario != "normal":
        v4 = dict(v)
        x, _, status = _solver(v4, risk_lambda, "normal") if use_qp else _solver(v4, "normal")  # type: ignore[call-arg]
        if x is not None and _is_feasible(x, v4, "normal"):
            relaxations.append(RelaxationApplied(
                step="USE_NORMAL_SCENARIO_WATER", params={},
            ))
            return x, relaxations, v4, "normal"

    return None, relaxations, v, safety_scenario


def _is_feasible(
    x: np.ndarray | None,
    vecs: dict | None = None,
    safety_scenario: str = "normal",
) -> bool:
    if x is None or not np.all(np.isfinite(x)) or np.any(x < -1e-6):
        return False
    if vecs is None:
        return True

    def tolerance(limit: float) -> float:
        return max(1e-6, abs(limit) * 1e-8)

    land_used = float(np.sum(x))
    if land_used > vecs["L"] + tolerance(vecs["L"]):
        return False
    budget_used = float(vecs["cost"] @ x)
    if budget_used > vecs["B"] + tolerance(vecs["B"]):
        return False
    water_cap = vecs["W"].get(safety_scenario, float("inf"))
    water_used = float(vecs["water_by_s"][_SCEN_IDX[safety_scenario]] @ x)
    if water_used > water_cap + tolerance(water_cap):
        return False
    cap = float(vecs.get("_force_cap", _div_cap(vecs["n"])))
    crop_limit = cap * vecs["L"]
    return not np.any(x > crop_limit + tolerance(crop_limit))


def _drop_crop(v: dict, idx: int) -> dict:
    """Return a new vecs dict with crop `idx` removed."""
    keep = [i for i in range(v["n"]) if i != idx]
    v2 = dict(v)
    v2["n"] = len(keep)
    v2["crop_ids"] = [v["crop_ids"][i] for i in keep]
    v2["cost"] = v["cost"][keep]
    v2["margin"] = v["margin"][:, keep]
    v2["margin_ann"] = v["margin_ann"][:, keep]
    v2["water_by_s"] = v["water_by_s"][:, keep]
    v2["duration"] = [v["duration"][i] for i in keep]
    return v2


# ── Build StrategyResult ──────────────────────────────────────────────────────

def _floor_acres(acres: float) -> float:
    """Round acres down to 3 decimals (with a float-noise guard) so rounded
    allocations never exceed land/budget/water limits."""
    return math.floor(acres * 1000 + 1e-6) / 1000


def _revenue_per_acre(crop) -> RevenueByScenario:
    """Per-acre revenue by scenario, satisfying R = P + C.

    CropOption created by Phase 3 carries revenue explicitly.  The
    profit-plus-cost fallback preserves compatibility with older,
    source-backed fixtures while retaining the identity R = P + C.
    """
    return crop.revenue_rs_per_acre or RevenueByScenario(
        drought=crop.profit_rs_per_acre.drought + crop.cost_per_acre.total_rs,
        normal=crop.profit_rs_per_acre.normal + crop.cost_per_acre.total_rs,
        excess=crop.profit_rs_per_acre.excess + crop.cost_per_acre.total_rs,
    )


def _build_result(
    strategy_id: str,
    label: str,
    kind: str,
    risk_lambda: float,
    safety_scenario: str,
    x: np.ndarray | None,
    vecs: dict,
    inputs: OptimizerInputs,
    solver_name: str,
    solver_status: str,
    solver_ms: int,
    relaxations: list[RelaxationApplied],
) -> StrategyResult:
    """Convert solver output to StrategyResult."""

    binding, infeasibility = _diagnose(x, vecs, safety_scenario)

    if x is None or not _is_feasible(x, vecs, safety_scenario) or float(np.sum(x)) < 0.01:
        if x is not None and _is_feasible(x, vecs, safety_scenario) and float(np.sum(x)) < 0.01:
            infeasibility = _empty_plan_infeasibility(vecs, safety_scenario)
        return StrategyResult(
            id=strategy_id,           # type: ignore[arg-type]
            label=label,
            kind=kind,                # type: ignore[arg-type]
            risk_lambda=risk_lambda,
            safety_scenario=safety_scenario,  # type: ignore[arg-type]
            allocations=[],
            totals=StrategyTotals(
                land_used_acres=0.0, budget_used_rs=0.0,
                fertilizer_kg={"n": 0.0, "p2o5": 0.0, "k2o": 0.0},
                water_m3=0.0,
            ),
            profit_by_scenario_rs=ProfitByScenario(drought=0.0, normal=0.0, excess=0.0),
            expected_profit_rs=0.0,
            worst_case_profit_rs=0.0,
            feasible=False,
            binding_constraints=binding,
            relaxations_applied=relaxations,
            solver=SolverInfo(name=solver_name, status=solver_status, ms=solver_ms),
            infeasibility=infeasibility,
        )

    # Build allocations
    crop_map = {c.crop_id: c for c in inputs.candidates}
    allocations = []
    weights = vecs["weights"]

    total_fert = {"n": 0.0, "p2o5": 0.0, "k2o": 0.0}
    total_water = 0.0
    total_cost = 0.0
    total_yield = 0.0
    revenue_by_scenario = {"drought": 0.0, "normal": 0.0, "excess": 0.0}

    for i, cid in enumerate(vecs["crop_ids"]):
        acres = _floor_acres(float(x[i]))
        if acres < 0.01:
            continue
        crop = crop_map.get(cid)
        if crop is None:
            continue

        profit_s = ProfitByScenario(
            drought=acres * crop.profit_rs_per_acre.drought,
            normal=acres * crop.profit_rs_per_acre.normal,
            excess=acres * crop.profit_rs_per_acre.excess,
        )
        revenue_per_acre = _revenue_per_acre(crop)
        revenue_s = RevenueByScenario(
            drought=acres * revenue_per_acre.drought,
            normal=acres * revenue_per_acre.normal,
            excess=acres * revenue_per_acre.excess,
        )
        si = _SCEN_IDX[safety_scenario]
        water_m3 = acres * float(vecs["water_by_s"][si][i])

        allocations.append(Allocation(
            crop_id=cid,
            acres=round(acres, 3),
            share_pct=round(acres / vecs["L"] * 100, 1) if vecs["L"] > 0 else 0.0,
            cost_rs=round(acres * crop.cost_per_acre.total_rs, 0),
            water_m3=round(water_m3, 0),
            profit_rs=profit_s,
            revenue_rs=revenue_s,
        ))

        total_fert["n"] += acres * crop.fertilizer.n_kg_per_acre
        total_fert["p2o5"] += acres * crop.fertilizer.p2o5_kg_per_acre
        total_fert["k2o"] += acres * crop.fertilizer.k2o_kg_per_acre
        total_water += water_m3
        total_cost += acres * crop.cost_per_acre.total_rs
        total_yield += acres * sum(
            weights[s] * getattr(crop.yield_quintal_per_acre, _SCEN_KEYS[s])
            for s in range(3)
        )
        for scenario in _SCEN_KEYS:
            revenue_by_scenario[scenario] += getattr(revenue_s, scenario)

    # Totals and profit by scenario
    land_used = float(sum(a.acres for a in allocations))
    pbs = ProfitByScenario(
        drought=sum(a.profit_rs.drought for a in allocations),
        normal=sum(a.profit_rs.normal for a in allocations),
        excess=sum(a.profit_rs.excess for a in allocations),
    )
    exp_profit = sum(weights[s] * getattr(pbs, _SCEN_KEYS[s]) for s in range(3))
    worst = min(pbs.drought, pbs.normal, pbs.excess)
    expected_revenue = sum(weights[s] * revenue_by_scenario[_SCEN_KEYS[s]] for s in range(3))
    roi = (exp_profit / total_cost * 100) if total_cost > 0 else None
    break_even = (total_cost / total_yield) if total_yield > 0 else None
    finance = FinanceSummary(
        investment_rs=_sv(round(total_cost, 0), "Rs", "sum(allocation acres × total cultivation cost per acre)", "computed"),
        expected_yield_quintal=_sv(round(total_yield, 3), "quintal", "scenario-weighted yield × allocation acres", "computed"),
        expected_revenue_rs=_sv(round(expected_revenue, 0), "Rs", "scenario-weighted harvest revenue", "computed"),
        expected_profit_rs=_sv(round(exp_profit, 0), "Rs", "expected revenue − investment", "computed"),
        roi_pct=(
            _sv(round(roi, 2), "pct", "expected profit ÷ investment × 100", "computed")
            if roi is not None else None
        ),
        break_even_price_rs_per_quintal=(
            _sv(round(break_even, 2), "Rs/quintal", "investment ÷ expected yield", "computed")
            if break_even is not None else None
        ),
    )

    return StrategyResult(
        id=strategy_id,           # type: ignore[arg-type]
        label=label,
        kind=kind,                # type: ignore[arg-type]
        risk_lambda=risk_lambda,
        safety_scenario=safety_scenario,  # type: ignore[arg-type]
        allocations=allocations,
        totals=StrategyTotals(
            land_used_acres=round(land_used, 3),
            budget_used_rs=round(total_cost, 0),
            fertilizer_kg={k: round(v, 2) for k, v in total_fert.items()},
            water_m3=round(total_water, 0),
        ),
        finance=finance,
        profit_by_scenario_rs=pbs,
        expected_profit_rs=round(exp_profit, 0),
        worst_case_profit_rs=round(worst, 0),
        feasible=True,
        binding_constraints=binding,
        relaxations_applied=relaxations,
        solver=SolverInfo(name=solver_name, status=solver_status, ms=solver_ms),
        infeasibility=None,
    )


# ── Traditional strategy (no solver) ─────────────────────────────────────────

def _traditional(inputs: OptimizerInputs, vecs: dict) -> StrategyResult:
    """District crop-mix from DES area shares, restricted to plan-season crops
    that have a real price.  Not forced to satisfy constraints.
    """
    from app.data.loaders import load_district_crop_yields

    district = inputs.location.district
    season_name = inputs.season.name
    L = inputs.profile.land_acres

    # Load DES area shares for this district + season
    try:
        yields_df = load_district_crop_yields()
        recent = yields_df[
            (yields_df["district"] == district) &
            (yields_df["season"] == season_name) &
            (yields_df["year"] >= yields_df["year"].max() - 4)
        ]
        total_area = recent.groupby("crop")["area_ha"].mean()
        if total_area.sum() > 0:
            shares = total_area / total_area.sum()
        else:
            shares = {}
    except Exception:
        shares = {}

    # Restrict to crops in our candidates (have a real price)
    eligible = {c.crop_id for c in inputs.candidates}
    shares = {k: float(v) for k, v in shares.items() if k in eligible and v > 0}
    # Spec: restrict to eligible crops, *then* scale to the farmer's land.
    share_sum = sum(shares.values())
    shares = {k: v / share_sum for k, v in shares.items()} if share_sum > 0 else {}
    if not shares:
        # Fall back to equal shares
        shares = {c.crop_id: 1.0 / len(inputs.candidates) for c in inputs.candidates} if inputs.candidates else {}

    # Build allocations
    crop_map = {c.crop_id: c for c in inputs.candidates}
    allocations = []
    weights = vecs["weights"]
    total_fert = {"n": 0.0, "p2o5": 0.0, "k2o": 0.0}
    total_water = 0.0
    total_cost = 0.0

    # Floor to the displayed precision and give the remainder to the last
    # crop so the displayed split never sums to more than the farm.
    share_items = list(shares.items())
    acres_list = [_floor_acres(share * L) for _, share in share_items]
    if acres_list:
        acres_list[-1] = _floor_acres(max(0.0, L - sum(acres_list[:-1])))
    for (cid, share), acres in zip(share_items, acres_list):
        crop = crop_map.get(cid)
        if crop is None or acres < 0.01:
            continue
        water_m3 = acres * crop.water_need_m3_per_acre.normal.value
        revenue_per_acre = _revenue_per_acre(crop)

        allocations.append(Allocation(
            crop_id=cid,
            acres=round(acres, 3),
            share_pct=round(share * 100, 1),
            cost_rs=round(acres * crop.cost_per_acre.total_rs, 0),
            water_m3=round(water_m3, 0),
            profit_rs=ProfitByScenario(
                drought=acres * crop.profit_rs_per_acre.drought,
                normal=acres * crop.profit_rs_per_acre.normal,
                excess=acres * crop.profit_rs_per_acre.excess,
            ),
            revenue_rs=RevenueByScenario(
                drought=acres * revenue_per_acre.drought,
                normal=acres * revenue_per_acre.normal,
                excess=acres * revenue_per_acre.excess,
            ),
        ))
        total_fert["n"] += acres * crop.fertilizer.n_kg_per_acre
        total_fert["p2o5"] += acres * crop.fertilizer.p2o5_kg_per_acre
        total_fert["k2o"] += acres * crop.fertilizer.k2o_kg_per_acre
        total_water += water_m3
        total_cost += acres * crop.cost_per_acre.total_rs

    pbs = ProfitByScenario(
        drought=sum(a.profit_rs.drought for a in allocations),
        normal=sum(a.profit_rs.normal for a in allocations),
        excess=sum(a.profit_rs.excess for a in allocations),
    )
    exp_profit = sum(weights[s] * getattr(pbs, _SCEN_KEYS[s]) for s in range(3))

    # Check which constraints the traditional mix breaks (honest comparison)
    W_normal = vecs["W"].get("normal", float("inf"))
    trad_exceeds = []
    if total_cost > inputs.profile.budget_rs:
        trad_exceeds.append("budget")
    if total_water > W_normal:
        trad_exceeds.append("water")

    return StrategyResult(
        id="traditional",
        label="Traditional",
        kind="traditional",
        risk_lambda=0.0,
        safety_scenario="normal",
        allocations=allocations,
        totals=StrategyTotals(
            land_used_acres=round(sum(a.acres for a in allocations), 3),
            budget_used_rs=round(total_cost, 0),
            fertilizer_kg={k: round(v, 2) for k, v in total_fert.items()},
            water_m3=round(total_water, 0),
        ),
        profit_by_scenario_rs=pbs,
        expected_profit_rs=round(exp_profit, 0),
        worst_case_profit_rs=round(min(pbs.drought, pbs.normal, pbs.excess), 0),
        # The status-quo mix is reported, not forced into the farmer's limits;
        # it is feasible only when it breaks none of them (ml-SPECS §Traditional).
        feasible=bool(allocations) and not trad_exceeds,
        binding_constraints=[],
        relaxations_applied=[],
        solver=SolverInfo(name="none", status="ok", ms=0),
        infeasibility=None,
        traditional_exceeds=trad_exceeds,
    )


# ── Impact vs Traditional (OPT.5) ────────────────────────────────────────────

def _compute_impact(
    recommended: StrategyResult,
    traditional: StrategyResult,
) -> Impact | None:
    """Compute water_saved_pct, fertilizer_saved_pct, drought_profit_gain_rs."""

    trad_water = traditional.totals.water_m3
    rec_water = recommended.totals.water_m3
    water_saved_pct = (
        (trad_water - rec_water) / trad_water * 100
        if trad_water > 0 else 0.0
    )

    trad_fert = sum(traditional.totals.fertilizer_kg.values())
    rec_fert = sum(recommended.totals.fertilizer_kg.values())

    # fertilizer_saved_pct: compare RDF cost of recommended vs traditional
    # When district use < RDF, fertilizer_vs_district_use_pct is null
    fertilizer_saved_pct = (
        (trad_fert - rec_fert) / trad_fert * 100
        if trad_fert > 0 else None
    )

    drought_gain = (
        recommended.profit_by_scenario_rs.drought
        - traditional.profit_by_scenario_rs.drought
    )

    trad_exceeds = getattr(traditional, "traditional_exceeds", [])

    return Impact(
        water_saved_pct=_sv(
            round(water_saved_pct, 1), "pct", "optimizer vs traditional",
            "computed",
        ),
        fertilizer_saved_pct=_sv(
            round(fertilizer_saved_pct, 1), "pct",
            "optimizer vs traditional (RDF kg)", "computed",
        ) if fertilizer_saved_pct is not None else None,
        fertilizer_vs_district_use_pct=None,  # set by pipeline if district data available
        drought_profit_gain_rs=_sv(
            round(drought_gain, 0), "rs",
            "optimizer vs traditional in drought scenario", "computed",
        ),
        versus="traditional",
        traditional_exceeds=trad_exceeds,
    )


def _sv(value, unit, source, status):
    """Shorthand SourcedValue factory."""
    from datetime import date
    return SourcedValue(
        value=value, unit=unit, source=source,
        as_of=str(date.today()), status=status,
    )


# ── Warnings builder ──────────────────────────────────────────────────────────

def _build_warnings(inputs: OptimizerInputs, strategies: list[StrategyResult]) -> list[Warning]:
    warnings: list[Warning] = []

    # OLD_COST_YEAR — always emit (costs are 2022-23)
    warnings.append(Warning(code=WARN_OLD_COST_YEAR, params={"year": "2022-23"}))

    # SINGLE_SEASON_COMPARISON — emit when sugarcane in any allocation
    sugarcane_ids = {"sugarcane", "sugarcane_adsali", "sugarcane_preseasonal", "sugarcane_ratoon"}
    for s in strategies:
        for alloc in s.allocations:
            if alloc.crop_id in sugarcane_ids:
                warnings.append(Warning(
                    code=WARN_SINGLE_SEASON_COMPARISON,
                    params={"crop_id": alloc.crop_id},
                ))
                break

    # SINGLE_CROP_ELIGIBLE
    if len(inputs.candidates) == 1:
        warnings.append(Warning(
            code="SINGLE_CROP_ELIGIBLE",
            params={"crop_id": inputs.candidates[0].crop_id},
        ))

    return warnings


# ── Public API ────────────────────────────────────────────────────────────────

def optimize(strategy: str, inputs: OptimizerInputs) -> StrategyResult:
    """Run a single strategy with a deterministic default.

    The historic ``qp_*`` IDs remain in the response contract. Until a
    validated joint crop-profit history is added, they are transparently
    solved as LPs: expected-profit and drought-water-scenario respectively.
    """
    vecs = _build_vectors(inputs)

    if strategy == "traditional":
        return _traditional(inputs, vecs)

    if strategy == "lp_max_profit":
        t0 = time.monotonic()
        x, sname, sstatus = _solve_lp(vecs, "normal")
        ms = int((time.monotonic() - t0) * 1000)
        relaxations: list[RelaxationApplied] = []
        safety_scenario = "normal"
        if x is None or not _is_feasible(x, vecs, safety_scenario):
            x, relaxations, vecs, safety_scenario = _try_relaxations(
                vecs, 0.0, safety_scenario, use_qp=False
            )
        return _build_result(
            "lp_max_profit", "LP Max-profit", "lp", 0.0, safety_scenario,
            x, vecs, inputs, sname, sstatus, ms, relaxations,
        )

    if strategy == "qp_balanced":
        if not RISK_QP_ENABLED:
            t0 = time.monotonic()
            x, sname, sstatus = _solve_lp(vecs, "normal")
            ms = int((time.monotonic() - t0) * 1000)
            return _build_result(
                "qp_balanced", "LP expected-profit (risk model unavailable)", "lp", 0.0,
                "normal", x, vecs, inputs, sname,
                f"{sstatus}; {RISK_QP_DISABLE_REASON}", ms, [],
            )
        risk_lambda = RISK_LAMBDA[inputs.profile.risk_appetite]
        t0 = time.monotonic()
        x, sname, sstatus = _solve_qp(vecs, risk_lambda, "normal")
        ms = int((time.monotonic() - t0) * 1000)
        relaxations = []
        safety_scenario = "normal"
        if x is None or not _is_feasible(x, vecs, safety_scenario):
            x, relaxations, vecs, safety_scenario = _try_relaxations(
                vecs, risk_lambda, safety_scenario, use_qp=True
            )
        return _build_result(
            "qp_balanced", "QP Balanced", "qp", risk_lambda, safety_scenario,
            x, vecs, inputs, sname, sstatus, ms, relaxations,
        )

    if strategy == "qp_drought_safe":
        if not RISK_QP_ENABLED:
            t0 = time.monotonic()
            x, sname, sstatus = _solve_lp(vecs, "drought")
            ms = int((time.monotonic() - t0) * 1000)
            return _build_result(
                "qp_drought_safe", "LP drought-water scenario (risk model unavailable)", "lp", 0.0,
                "drought", x, vecs, inputs, sname,
                f"{sstatus}; {RISK_QP_DISABLE_REASON}", ms, [],
            )
        risk_lambda = RISK_LAMBDA[inputs.profile.risk_appetite]
        t0 = time.monotonic()
        x, sname, sstatus = _solve_qp(vecs, risk_lambda, "drought")
        ms = int((time.monotonic() - t0) * 1000)
        relaxations = []
        safety_scenario = "drought"
        if x is None or not _is_feasible(x, vecs, safety_scenario):
            x, relaxations, vecs, safety_scenario = _try_relaxations(
                vecs, risk_lambda, safety_scenario, use_qp=True
            )
        return _build_result(
            "qp_drought_safe", "QP Drought-safe", "qp", risk_lambda, safety_scenario,
            x, vecs, inputs, sname, sstatus, ms, relaxations,
        )

    raise ValueError(f"Unknown strategy: {strategy!r}")


def compare_strategies(inputs: OptimizerInputs) -> tuple[list[StrategyResult], Impact | None, list[Warning]]:
    """Run comparable strategies and compute impact vs Traditional.

    Returns (strategies, impact, warnings).
    The recommended mathematical baseline is ``lp_max_profit``. The legacy
    scenario IDs are retained for UI compatibility but must not be presented as
    covariance-based QP risk recommendations while the risk gate is closed.
    """
    results: list[StrategyResult] = []

    for strategy in ("traditional", "lp_max_profit", "qp_balanced", "qp_drought_safe"):
        try:
            r = optimize(strategy, inputs)
            results.append(r)
        except Exception:
            logger.exception("compare_strategies: strategy=%s failed", strategy)
            raise

    # Find traditional and recommended for impact
    trad = next((r for r in results if r.id == "traditional"), None)
    rec_id = "lp_max_profit"
    rec = next((r for r in results if r.id == rec_id), None)

    impact = _compute_impact(rec, trad) if rec and trad else None
    warnings = _build_warnings(inputs, results)

    return results, impact, warnings
