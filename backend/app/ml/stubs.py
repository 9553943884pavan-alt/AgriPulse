"""C.3 — ML interface stubs.

Function signatures match ml/SPECS.md §10 exactly. These raise NotImplementedError
so the backend compiles and the frontend is unblocked on day 1.
The ML lead replaces these implementations in app/ml/suitability.py,
app/ml/yield_model.py, app/ml/scenarios.py, etc.

NOTE: crop_price parameter intentionally absent from fertilizer_plan()
— the fixed RDF dose has no dependency on crop price (alignment fix from
SPECS_ALIGNMENT_RESOLUTION.md §3.4).
"""

from __future__ import annotations

from app.schemas import (
    Candidate,
    ExcludedCrop,
    FarmProfile,
    FertilizerPlan,
    Location,
    OptimizerInputs,
    Scenario,
    Season,
    StrategyResult,
    Suitability,
    WaterBudget,
    WaterNeed,
    YieldPrediction,
)


def candidate_crops(
    profile: FarmProfile,
    location: Location,
    season: Season,
    water: list[WaterBudget],
) -> tuple[list[Candidate], list[ExcludedCrop]]:
    """ML.1 — Filter crops by: grown in district ∩ sowable now ∩ water-feasible."""
    raise NotImplementedError("candidate_crops: ML lead to implement in app/ml/suitability.py")


def predict_yield(
    crop_id: str,
    location: Location,
    season: Season,
    conditions: Scenario,
) -> YieldPrediction:
    """ML.4 — Gradient boosting yield prediction (t/ha) + clipped flag."""
    raise NotImplementedError("predict_yield: ML lead to implement in app/ml/yield_model.py")


def suitability(
    crop_id: str,
    location: Location,
    season: Season,
    conditions: Scenario,
) -> Suitability:
    """ML.4b — Suitability score, label, SHAP top_factors, fallback_used."""
    raise NotImplementedError("suitability: ML lead to implement in app/ml/suitability.py")


def build_scenarios(
    location: Location,
    season: Season,
) -> list[Scenario]:
    """ML.5 — Analogue-year scenarios at P10/P50/P90 of water index.
    Rabi ranked on 0.5×Rabi_rain + 0.5×preceding_Kharif_rain.
    Returns 3 Scenario objects: drought, normal, excess.
    """
    raise NotImplementedError("build_scenarios: ML lead to implement in app/ml/scenarios.py")


def crop_water_need(
    crop_id: str,
    season: Season,
    scenario: Scenario,
    efficiency: float,
) -> WaterNeed:
    """ML.7 — Crop water need per stage and scenario.
    Formula: Σ stages (Kc × ET0 − effective_rain)+ ÷ irrigation_efficiency
    Returns WaterNeed with drought/normal/excess in m3/acre.
    """
    raise NotImplementedError("crop_water_need: ML lead to implement in app/ml/water_need.py")


def fertilizer_plan(
    crop_id: str,
    fertilizer_prices: dict,
) -> FertilizerPlan:
    """ML.8 — RDF dose per crop, priced with official MRPs.
    NOTE: crop_price parameter removed — fixed RDF dose is independent of crop price.
    """
    raise NotImplementedError("fertilizer_plan: ML lead to implement in app/ml/fertilizer.py")


def optimize(
    strategy: str,
    inputs: OptimizerInputs,
) -> StrategyResult:
    """OPT.1/OPT.2 — LP (HiGHS) or QP (CVXPY) optimizer.
    strategy: traditional | lp_max_profit | qp_balanced | qp_drought_safe
    """
    from app.ml.optimizer import optimize as _optimize
    return _optimize(strategy, inputs)


def compare_strategies(
    inputs: OptimizerInputs,
) -> list[StrategyResult]:
    """OPT.3 — Run all 4 strategies and compute impact vs Traditional."""
    from app.ml.optimizer import compare_strategies as _compare
    results, impact, warnings = _compare(inputs)
    return results
