"""AG.2 — Tool wrappers for services and ML functions.

Single-path rule: every wrapper calls the existing function in app/services/ or
app/ml/ — it does NOT copy or reimplement logic. Both /api/plan (E2) and
/api/agent/chat (E1) call the same underlying functions, so they always return
identical plans for the same profile.

One tool per backend service or ML function. All return SourcedValue-bearing
dicts or Pydantic models defined in schemas.py.
"""

from __future__ import annotations

import logging
from datetime import date

from app.schemas import (
    Candidate,
    CostBreakdown,
    ExcludedCrop,
    FarmProfile,
    FertilizerPlan,
    Location,
    OptimizerInputs,
    Scenario,
    Season,
    SourcedValue,
    StrategyResult,
    Suitability,
    WaterBudget,
    WaterNeed,
    YieldPrediction,
)

logger = logging.getLogger(__name__)


# ── Location ──────────────────────────────────────────────────────────────────

async def get_location(location_text: str) -> Location:
    """Resolve a free-text location to a Location with district + coordinates."""
    from app.services import location as loc_svc
    return await loc_svc.locate(location_text)


# ── Weather ───────────────────────────────────────────────────────────────────

async def get_weather(location: Location) -> dict[str, SourcedValue]:
    """Fetch 16-day forecast + past 92 days from Open-Meteo."""
    from app.services import weather as wx_svc
    return await wx_svc.get_weather(location)


# ── Soil ──────────────────────────────────────────────────────────────────────

async def get_soil(profile: FarmProfile, location: Location) -> dict[str, SourcedValue | None]:
    """Return soil data (N, P, K, pH, OC): farmer test > SoilGrids > district dataset."""
    from app.services import soil as soil_svc
    return await soil_svc.get_soil(profile, location)


# ── Water budgets ─────────────────────────────────────────────────────────────

async def get_water_budget(
    profile: FarmProfile,
    location: Location,
    scenarios: list[Scenario],
    weather: dict,
) -> list[WaterBudget]:
    """One WaterBudget per scenario (drought / normal / excess)."""
    from app.services import water as water_svc
    return water_svc.build_water_budgets(profile, location, scenarios, weather)


# ── Prices ────────────────────────────────────────────────────────────────────

async def get_prices(
    district: str,
    crop_ids: list[str],
) -> dict[str, SourcedValue]:
    """Today's Agmarknet price for each crop (with fallback chain)."""
    from app.services import prices as prices_svc
    return await prices_svc.get_prices(district, crop_ids)


# ── Costs ─────────────────────────────────────────────────────────────────────

async def get_costs(
    district: str,
    crop_ids: list[str],
) -> dict[str, CostBreakdown]:
    """DES/CACP 2022-23 cost breakdown per crop, with seed and fertilizer overrides."""
    from app.services import costs as costs_svc
    return await costs_svc.get_costs(district, crop_ids)


# ── ML: candidate crops ───────────────────────────────────────────────────────

def recommend_crops(
    profile: FarmProfile,
    location: Location,
    season: Season,
    water: list[WaterBudget],
    today: date | None = None,
) -> tuple[list[Candidate], list[ExcludedCrop]]:
    """ML.1 + ML.4b — Filter candidates and score with suitability."""
    from app.ml.stubs import candidate_crops
    return candidate_crops(profile, location, season, water)


# ── ML: yield prediction ──────────────────────────────────────────────────────

def predict_yield(
    crop_id: str,
    location: Location,
    season: Season,
    conditions: Scenario,
) -> YieldPrediction:
    """ML.4 — Gradient boosting yield prediction (t/ha)."""
    from app.ml.stubs import predict_yield as _predict_yield
    return _predict_yield(crop_id, location, season, conditions)


# ── ML: suitability ───────────────────────────────────────────────────────────

def get_suitability(
    crop_id: str,
    location: Location,
    season: Season,
    conditions: Scenario,
) -> Suitability:
    """ML.4b — SHAP suitability score, label and top-3 factors."""
    from app.ml.stubs import suitability
    return suitability(crop_id, location, season, conditions)


# ── ML: scenarios ─────────────────────────────────────────────────────────────

def build_scenarios(location: Location, season: Season) -> list[Scenario]:
    """ML.5 — P10/P50/P90 analogue-year scenarios."""
    from app.ml.stubs import build_scenarios as _build_scenarios
    return _build_scenarios(location, season)


# ── ML: water need ────────────────────────────────────────────────────────────

def get_crop_water_need(
    crop_id: str,
    season: Season,
    scenario: Scenario,
    efficiency: float,
) -> WaterNeed:
    """ML.7 — Penman-Monteith crop water need (m3/acre per scenario)."""
    from app.ml.stubs import crop_water_need
    return crop_water_need(crop_id, season, scenario, efficiency)


# ── ML: fertilizer plan ───────────────────────────────────────────────────────

def get_fertilizer_plan(
    crop_id: str,
    fertilizer_prices: dict,
) -> FertilizerPlan:
    """ML.8 — RDF dose → bags → cost."""
    from app.ml.stubs import fertilizer_plan
    return fertilizer_plan(crop_id, fertilizer_prices)


# ── Optimizer ─────────────────────────────────────────────────────────────────

def optimize_plan(strategy: str, inputs: OptimizerInputs) -> StrategyResult:
    """OPT.1/OPT.2 — LP or QP optimizer for one strategy."""
    from app.ml.stubs import optimize
    return optimize(strategy, inputs)


def compare_strategies(inputs: OptimizerInputs) -> list[StrategyResult]:
    """OPT.3 — Run all 4 strategies and return results."""
    from app.ml.stubs import compare_strategies as _compare
    return _compare(inputs)
