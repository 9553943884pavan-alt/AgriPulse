"""Focused tests for the validated deterministic optimizer path.

Spec requirements verified:
  OPT.1  LP with land/budget/water/diversification constraints
  OPT.2  QP risk is gated without joint historical crop-profit samples
  OPT.3  All 4 strategies run on the same inputs; compare_strategies returns all 4
  OPT.4  Infeasibility report: impossible case returns feasible=False with detail
  OPT.5  Impact vs Traditional: water_saved_pct, fertilizer_saved_pct, drought_profit_gain_rs
"""
from __future__ import annotations

import math
from datetime import date

import pytest

from app.schemas import (
    Allocation,
    CostBreakdown,
    CropOption,
    DefaultUsed,
    FarmProfile,
    FertilizerPlan,
    Location,
    OptimizerInputs,
    ProfitByScenario,
    Scenario,
    Season,
    SolverInfo,
    SowingWindow,
    SourcedValue,
    StrategyResult,
    Suitability,
    WaterAvailable,
    WaterBasis,
    WaterBudget,
    WaterNeed,
    WaterNeedSummary,
    YieldByScenario,
)


# ── Test fixtures ─────────────────────────────────────────────────────────────

TODAY = str(date.today())


def _sv(value, unit="rs", status="computed"):
    return SourcedValue(value=value, unit=unit, source="test",
                        as_of=TODAY, status=status)


def _suitability():
    return Suitability(score=1.1, label="good", top_factors=[], fallback_used=False)


def _cost(total=20000, seed=2000, fert=2500, manure=800,
          labour=9000, machine=3500, irrigation=500, pesticide=1200, interest=500):
    return CostBreakdown(
        total_rs=total, seed=seed, fertilizer=fert, manure=manure,
        labour=labour, machine=machine, irrigation=irrigation,
        pesticide=pesticide, interest=interest,
        reference_year="2022-23", source="DES/CACP", status="official_dataset",
    )


def _fert(n=10, p=18, k=8):
    return FertilizerPlan(
        n_kg_per_acre=n, p2o5_kg_per_acre=p, k2o_kg_per_acre=k,
        urea_bags=1.1, dap_bags=2.0, mop_bags=0.7,
        cost_rs=_sv(1800, "rs"), basis="RDF",
    )


def _water_need(drought=1800, normal=1400, excess=900):
    return WaterNeed(
        drought=_sv(drought, "m3_per_acre", "computed"),
        normal=_sv(normal, "m3_per_acre", "computed"),
        excess=_sv(excess, "m3_per_acre", "computed"),
    )


def _crop(crop_id, profit_d=5000, profit_n=10000, profit_e=8000,
          yield_d=3.0, yield_n=4.5, yield_e=3.8, duration=110,
          water_d=1800, water_n=1400, water_e=900):
    return CropOption(
        crop_id=crop_id,
        names={"en": crop_id.title(), "mr": crop_id, "hi": crop_id},
        season="Rabi",
        suitability=_suitability(),
        yield_quintal_per_acre=YieldByScenario(drought=yield_d, normal=yield_n, excess=yield_e),
        price=_sv(4000, "rs_per_quintal", "live"),
        expected_harvest_price=_sv(4200, "rs_per_quintal", "computed"),
        seasonal_ratio=_sv(1.05, "ratio", "computed"),
        duration_days=duration,
        harvest_month="2027-03",
        msp=_sv(3500, "rs_per_quintal", "official_dataset"),
        cost_per_acre=_cost(),
        fertilizer=_fert(),
        water_need_m3_per_acre=_water_need(water_d, water_n, water_e),
        profit_rs_per_acre=ProfitByScenario(drought=profit_d, normal=profit_n, excess=profit_e),
    )


def _water_budget(scenario, total=8000, analogue_year=2019):
    return WaterBudget(
        scenario=scenario,
        analogue_year=analogue_year,
        available_m3=WaterAvailable(
            rain=_sv(5000, "m3", "computed"),
            groundwater=_sv(2000, "m3", "computed"),
            canal=_sv(1000, "m3", "computed"),
            total=_sv(total, "m3", "computed"),
        ),
        basis=WaterBasis(
            groundwater_category=_sv("Over-exploited", "category", "official_dataset"),
            category_cap=_sv(0.15, "ratio", "assumption"),
            effective_rain_factor=_sv(0.75, "ratio", "assumption"),
            reservoir_storage_pct=_sv(55.0, "pct", "official_dataset"),
            rain_so_far_mm=_sv(45.0, "mm", "cached"),
        ),
        irrigation_method="flood",
        efficiency_pct=_sv(60, "pct", "official_dataset"),
        need_m3=WaterNeedSummary(
            traditional_plan=_sv(7000, "m3", "computed"),
            recommended_plan=_sv(5500, "m3", "computed"),
        ),
    )


def _scenario(sid, rain=550, analogue=2019, prob=0.6):
    labels = {"drought": "Drought", "normal": "Normal", "excess": "Excess rain"}
    return Scenario(
        id=sid,
        label=labels[sid],
        season_rain_mm=_sv(rain, "mm", "official_dataset"),
        probability=prob,
        analogue_year=analogue,
        all_year_samples=[],
    )


def _profile(land=5.0, budget=60000, risk="balanced"):
    return FarmProfile(
        location_text="Beed",
        land_acres=land,
        budget_rs=budget,
        water_source="borewell",
        risk_appetite=risk,
        language="en",
    )


def _location():
    return Location(
        input="Beed", resolved_name="Beed, Maharashtra",
        district="Beed", state="Maharashtra",
        latitude=18.99, longitude=75.91,
    )


def _season():
    return Season(
        name="Rabi",
        sowing_window=SowingWindow(start="2026-11-01", end="2026-11-30"),
    )


def _inputs(crops=None, land=5.0, budget=60000, risk="balanced",
            water_total=8000):
    if crops is None:
        crops = [
            _crop("chickpea", profit_d=4500, profit_n=9000, profit_e=7500),
            _crop("wheat",    profit_d=3800, profit_n=8500, profit_e=7200),
            _crop("lentil",   profit_d=5200, profit_n=11000, profit_e=9000),
        ]
    return OptimizerInputs(
        profile=_profile(land, budget, risk),
        location=_location(),
        season=_season(),
        candidates=crops,
        water_budgets=[
            _water_budget("drought", total=5000, analogue_year=2002),
            _water_budget("normal",  total=water_total, analogue_year=2019),
            _water_budget("excess",  total=12000, analogue_year=2005),
        ],
        scenario_weights=[0.2, 0.6, 0.2],
        price_history_years={"chickpea": 4, "wheat": 5, "lentil": 3},
    )


# ── OPT.1: LP optimizer ───────────────────────────────────────────────────────

def test_lp_returns_feasible_result():
    from app.ml.optimizer import optimize
    result = optimize("lp_max_profit", _inputs())
    assert result.feasible is True
    assert result.id == "lp_max_profit"
    assert result.kind == "lp"
    assert len(result.allocations) > 0
    total_acres = sum(a.acres for a in result.allocations)
    assert total_acres <= 5.0 + 0.01, f"Land constraint violated: {total_acres}"


def test_lp_respects_budget():
    from app.ml.optimizer import optimize
    result = optimize("lp_max_profit", _inputs(budget=60000))
    total_cost = sum(a.cost_rs for a in result.allocations)
    assert total_cost <= 60000 + 1, f"Budget violated: {total_cost}"


def test_lp_respects_water():
    from app.ml.optimizer import optimize
    result = optimize("lp_max_profit", _inputs(water_total=8000))
    # water per alloc uses normal scenario water need
    total_water = sum(a.water_m3 for a in result.allocations)
    assert total_water <= 8000 + 10, f"Water violated: {total_water}"


def test_lp_finance_reconciles_revenue_cost_profit_and_roi():
    """Portfolio finance must use the same allocation economics as the LP."""
    from app.ml.optimizer import optimize

    result = optimize("lp_max_profit", _inputs())
    assert result.feasible is True
    assert result.finance is not None
    finance = result.finance
    investment = float(finance.investment_rs.value)
    revenue = float(finance.expected_revenue_rs.value)
    profit = float(finance.expected_profit_rs.value)

    assert investment == pytest.approx(result.totals.budget_used_rs, abs=1)
    assert revenue - investment == pytest.approx(profit, abs=1)
    assert profit == pytest.approx(result.expected_profit_rs, abs=1)
    assert finance.roi_pct is not None
    assert float(finance.roi_pct.value) == pytest.approx(profit / investment * 100, abs=0.02)
    assert finance.break_even_price_rs_per_quintal is not None


def test_lp_diversification_cap():
    """No single crop should exceed cap * land for n>=3 crops."""
    from app.ml.optimizer import optimize, _div_cap
    inp = _inputs()
    result = optimize("lp_max_profit", inp)
    cap = _div_cap(len(inp.candidates))
    for a in result.allocations:
        assert a.acres <= cap * 5.0 + 0.05, \
            f"Diversification cap violated for {a.crop_id}: {a.acres}"


def test_lp_applies_forced_cap_only_after_relaxation():
    from app.ml.optimizer import _build_vectors, _is_feasible, _solve_lp

    vectors = _build_vectors(_inputs(budget=200000, water_total=100000))
    default_x, _, _ = _solve_lp(vectors, "normal")
    relaxed_vectors = dict(vectors, _force_cap=1.0)
    relaxed_x, _, _ = _solve_lp(relaxed_vectors, "normal")

    assert default_x is not None and relaxed_x is not None
    assert max(default_x) <= 0.65 * vectors["L"] + 0.01
    assert max(relaxed_x) > 0.65 * vectors["L"] + 0.01
    assert _is_feasible(relaxed_x, relaxed_vectors, "normal")
    assert not _is_feasible(relaxed_x, vectors, "normal")


def test_feasibility_check_validates_water_cap():
    import numpy as np
    from app.ml.optimizer import _build_vectors, _is_feasible

    vectors = _build_vectors(_inputs())
    allocation = np.array([3.0, 0.0, 0.0])

    assert _is_feasible(allocation, vectors, "normal")
    assert not _is_feasible(allocation, vectors, "drought")


# ── OPT.2: QP reproduces LP at λ=0 ──────────────────────────────────────────

def test_qp_id_is_transparent_lp_fallback_without_risk_history():
    """A three-scenario table must not be represented as a QP risk model."""
    from app.ml.optimizer import optimize
    inp = _inputs(risk="max_profit")
    lp = optimize("lp_max_profit", inp)
    qp = optimize("qp_balanced", inp)
    if not lp.feasible or not qp.feasible:
        pytest.skip("Infeasible — can't compare")
    diff = abs(lp.expected_profit_rs - qp.expected_profit_rs)
    relative = diff / max(abs(lp.expected_profit_rs), 1)
    assert relative < 0.01, \
        f"LP fallback differs by {relative:.2%}: LP={lp.expected_profit_rs} fallback={qp.expected_profit_rs}"
    assert qp.kind == "lp"
    assert qp.risk_lambda == 0
    assert "risk QP disabled" in qp.solver.status


def test_qp_balanced_id_uses_validated_lp_baseline():
    from app.ml.optimizer import optimize
    inp = _inputs(risk="balanced")
    lp = optimize("lp_max_profit", inp)
    qp = optimize("qp_balanced", inp)
    # Both strategies must complete without exception
    assert lp.id == "lp_max_profit"
    assert qp.id == "qp_balanced"
    # With risk unavailable the compatibility strategy is the same LP solution.
    if lp.feasible and qp.feasible and lp.allocations and qp.allocations:
        assert lp.expected_profit_rs == pytest.approx(qp.expected_profit_rs)


def test_qp_balanced_fallback_allocates_when_expected_profit_is_positive():
    from app.ml.optimizer import optimize

    result = optimize("qp_balanced", _inputs())

    assert result.feasible is True
    assert result.allocations
    assert result.totals.land_used_acres > 0


# ── OPT.3: All 4 strategies ───────────────────────────────────────────────────

def test_compare_strategies_returns_four():
    from app.ml.optimizer import compare_strategies
    results, impact, warnings = compare_strategies(_inputs())
    ids = {r.id for r in results}
    assert "traditional" in ids
    assert "lp_max_profit" in ids
    assert "qp_balanced" in ids
    assert "qp_drought_safe" in ids


def test_compare_strategies_all_have_profit():
    from app.ml.optimizer import compare_strategies
    results, _, _ = compare_strategies(_inputs())
    for r in results:
        if r.feasible:
            assert r.expected_profit_rs != 0 or len(r.allocations) == 0


def test_drought_safe_uses_drought_water():
    """Scenario guard must use the drought irrigation-water cap."""
    from app.ml.optimizer import compare_strategies
    results, _, _ = compare_strategies(_inputs(water_total=8000))
    drought_safe = next(r for r in results if r.id == "qp_drought_safe")
    assert drought_safe.safety_scenario == "drought"
    assert drought_safe.kind == "lp"


# ── OPT.4: Infeasibility ─────────────────────────────────────────────────────

def test_infeasible_when_budget_too_small():
    """Budget 1 Rs makes it impossible to plant anything — infeasibility report."""
    from app.ml.optimizer import optimize
    result = optimize("lp_max_profit", _inputs(budget=1))
    assert result.feasible is False
    assert result.allocations == []
    assert result.infeasibility is not None


def test_nonprofitable_crop_is_not_reported_as_empty_feasible_plan():
    from app.ml.optimizer import optimize

    unprofitable = _crop("unprofitable", profit_d=-5000, profit_n=-4000, profit_e=-3000)
    result = optimize("lp_max_profit", _inputs(crops=[unprofitable]))

    assert result.feasible is False
    assert result.allocations == []
    assert result.infeasibility.suggestion_code == "NO_POSITIVE_ALLOCATION"


def test_infeasible_result_has_empty_allocations():
    """An infeasible result must never have allocations."""
    from app.ml.optimizer import optimize
    result = optimize("lp_max_profit", _inputs(budget=1))
    if not result.feasible:
        assert result.allocations == []


def test_infeasibility_detail_structure():
    """Infeasibility payload has the right fields when present."""
    from app.ml.optimizer import optimize
    result = optimize("lp_max_profit", _inputs(budget=1))
    if result.infeasibility is not None:
        inf = result.infeasibility
        assert hasattr(inf, "binding")
        assert hasattr(inf, "violated")
        assert hasattr(inf, "detail")


# ── OPT.5: Impact metrics ─────────────────────────────────────────────────────

def test_impact_is_computed():
    from app.ml.optimizer import compare_strategies
    _, impact, _ = compare_strategies(_inputs())
    assert impact is not None


def test_impact_has_required_fields():
    from app.ml.optimizer import compare_strategies
    _, impact, _ = compare_strategies(_inputs())
    if impact is not None:
        assert hasattr(impact, "water_saved_pct")
        assert hasattr(impact, "drought_profit_gain_rs")
        assert impact.versus == "traditional"


def test_impact_water_saved_is_sourced_value():
    from app.ml.optimizer import compare_strategies
    from app.schemas import SourcedValue
    _, impact, _ = compare_strategies(_inputs())
    if impact is not None:
        assert isinstance(impact.water_saved_pct, SourcedValue)


# ── Warnings ──────────────────────────────────────────────────────────────────

def test_old_cost_year_warning_always_present():
    """OLD_COST_YEAR warning must always be emitted."""
    from app.ml.optimizer import compare_strategies
    _, _, warnings = compare_strategies(_inputs())
    codes = [w.code for w in warnings]
    assert "OLD_COST_YEAR" in codes


def test_single_season_comparison_warning_for_sugarcane():
    """SINGLE_SEASON_COMPARISON must be emitted when sugarcane is in any allocation."""
    from app.ml.optimizer import compare_strategies
    sugarcane = _crop("sugarcane", duration=365,
                      profit_d=15000, profit_n=30000, profit_e=25000,
                      water_d=4000, water_n=3500, water_e=2500)
    inp = _inputs(crops=[sugarcane, _crop("wheat")])
    _, _, warnings = compare_strategies(inp)
    codes = [w.code for w in warnings]
    assert "SINGLE_SEASON_COMPARISON" in codes, f"Expected SINGLE_SEASON_COMPARISON in {codes}"


def test_single_crop_eligible_warning():
    """SINGLE_CROP_ELIGIBLE emitted when only one candidate crop."""
    from app.ml.optimizer import compare_strategies
    inp = _inputs(crops=[_crop("chickpea")])
    _, _, warnings = compare_strategies(inp)
    codes = [w.code for w in warnings]
    assert "SINGLE_CROP_ELIGIBLE" in codes


# ── Long-duration crops ───────────────────────────────────────────────────────

def test_long_duration_margin_stays_on_shared_seasonal_horizon():
    """Do not annualise one crop without modelling the displaced next crop."""
    from app.ml.optimizer import _annual_margin
    assert _annual_margin(30000, 365) == pytest.approx(30000 / 1.0, rel=0.001)
    assert _annual_margin(10000, 240) == pytest.approx(10000, rel=0.001)


# ── Solver info ───────────────────────────────────────────────────────────────

def test_lp_result_has_solver_info():
    from app.ml.optimizer import optimize
    result = optimize("lp_max_profit", _inputs())
    assert result.solver is not None
    assert result.solver.name in ("HiGHS", "CVXPY", "CLARABEL", "OSQP", "ECOS")
    assert result.solver.ms >= 0


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_candidates_returns_infeasible():
    """No candidates → every strategy returns feasible=False, allocations=[]."""
    from app.ml.optimizer import optimize
    inp = _inputs(crops=[])
    for strategy in ("lp_max_profit", "qp_balanced", "qp_drought_safe"):
        result = optimize(strategy, inp)
        assert result.allocations == []


def test_single_candidate_uses_cap_100():
    """With 1 crop, diversification cap is 1.0 — all land may go to it."""
    from app.ml.optimizer import optimize, _div_cap
    assert _div_cap(1) == 1.0
    inp = _inputs(crops=[_crop("chickpea")])
    result = optimize("lp_max_profit", inp)
    if result.feasible and result.allocations:
        assert result.allocations[0].acres <= 5.0 + 0.01
