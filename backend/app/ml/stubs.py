"""C.3 — Stable ML interface wrappers around the production implementations."""

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


# ── ML.1 — Candidate crop filter ✅ implemented ───────────────────────────────

def candidate_crops(
    profile: FarmProfile,
    location: Location,
    season: Season,
    water: list[WaterBudget],
) -> tuple[list[Candidate], list[ExcludedCrop]]:
    """ML.1 — Filter crops: grown in district ∩ sowable now."""
    from app.ml.suitability import candidate_crops as _impl
    return _impl(profile, location, season, water)


# ── ML.4 — Yield model ✅ implemented ─────────────────────────────────────────

def predict_yield(
    crop_id: str,
    location: Location,
    season: Season,
    conditions: Scenario,
) -> YieldPrediction:
    """ML.4 — Gradient boosting yield prediction (Model A) with baseline fallback."""
    from app.ml.yield_model import predict_yield as _impl
    return _impl(crop_id, location, season, conditions)


# ── ML.4b — Suitability ✅ implemented ────────────────────────────────────────

def suitability(
    crop_id: str,
    location: Location,
    season: Season,
    conditions: Scenario,
) -> Suitability:
    """ML.4b — SHAP suitability score and factor attribution."""
    from app.ml.suitability_scoring import suitability as _impl
    return _impl(crop_id, location, season, conditions)


# ── ML.5 — Climate scenarios ✅ implemented ────────────────────────────────────

def build_scenarios(
    location: Location,
    season: Season,
) -> list[Scenario]:
    """ML.5 — Analogue-year scenarios P10/P50/P90 from ERA5 weather series."""
    from app.ml.scenarios import build_scenarios as _impl
    return _impl(location, season)


# ── ML.7 — Crop water need ✅ implemented ────────────────────────────────────

def crop_water_need(
    crop_id: str,
    season: Season,
    scenario: Scenario,
    efficiency: float,
) -> WaterNeed:
    """ML.7 — FAO-56 Kc × ET₀ per stage per scenario."""
    from app.ml.water_need import crop_water_need as _impl
    return _impl(crop_id, season, [scenario], efficiency or None)


# ── ML.8 — Fertilizer plan ✅ implemented ────────────────────────────────────

def fertilizer_plan(
    crop_id: str,
    fertilizer_prices: dict,  # noqa: ARG001 — prices loaded from CSV internally
) -> FertilizerPlan:
    """ML.8 — RDF dose → bags → rupees using official MRPs."""
    from app.ml.fertilizer import fertilizer_plan as _impl
    # season not known at this call site; caller should use fertilizer.fertilizer_plan directly
    return _impl(crop_id, "Kharif")


# ── OPT.1/2 — LP/QP optimizer ✅ implemented ─────────────────────────────────

def optimize(
    strategy: str,
    inputs: OptimizerInputs,
) -> StrategyResult:
    """OPT.1/OPT.2 — LP (HiGHS) or QP (CVXPY) optimizer."""
    from app.ml.optimizer import optimize as _optimize
    return _optimize(strategy, inputs)


# ── OPT.3 — Compare strategies ✅ implemented ────────────────────────────────

def compare_strategies(
    inputs: OptimizerInputs,
) -> list[StrategyResult]:
    """OPT.3 — Run all 4 strategies and compute impact vs Traditional."""
    from app.ml.optimizer import compare_strategies as _compare
    results, _impact, _warnings = _compare(inputs)
    return results
