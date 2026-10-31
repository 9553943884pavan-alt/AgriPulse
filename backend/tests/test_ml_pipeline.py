"""Tests for ML integration: scenarios, yield model, suitability SHAP, and pipeline."""

from __future__ import annotations

import pytest

from app.ml.scenarios import build_scenarios
from app.ml.suitability_scoring import suitability
from app.ml.yield_baseline import get_yield_baseline
from app.ml.yield_model import predict_yield
from app.schemas import FarmProfile, Location, Season, SowingWindow


@pytest.fixture
def pune_location() -> Location:
    return Location(
        input="Pune",
        resolved_name="Pune, Maharashtra",
        district="Pune",
        state="Maharashtra",
        latitude=18.5204,
        longitude=73.8567,
    )


@pytest.fixture
def rabi_season() -> Season:
    return Season(
        name="Rabi",
        sowing_window=SowingWindow(start="2026-10-15", end="2026-12-15"),
        status="official_dataset",
    )


# ── ML.5 Scenarios ────────────────────────────────────────────────────────────

def test_build_scenarios_returns_three_scenarios(pune_location, rabi_season):
    scenarios = build_scenarios(pune_location, rabi_season)
    assert len(scenarios) == 3
    ids = [s.id for s in scenarios]
    assert "drought" in ids
    assert "normal" in ids
    assert "excess" in ids


def test_build_scenarios_analogue_years_valid(pune_location, rabi_season):
    scenarios = build_scenarios(pune_location, rabi_season)
    for sc in scenarios:
        assert sc.analogue_year is not None
        assert 1997 <= sc.analogue_year <= 2025
        assert sc.season_rain_mm.value >= 0.0


def test_build_scenarios_relative_ordering(pune_location):
    kharif_season = Season(
        name="Kharif",
        sowing_window=SowingWindow(start="2026-06-01", end="2026-07-31"),
        status="official_dataset",
    )
    sc = {s.id: s for s in build_scenarios(pune_location, kharif_season)}
    assert sc["drought"].season_rain_mm.value <= sc["normal"].season_rain_mm.value
    assert sc["normal"].season_rain_mm.value <= sc["excess"].season_rain_mm.value


# ── ML.3 & ML.4 Yield Predictions ─────────────────────────────────────────────

def test_baseline_yield_hierarchical(pune_location, rabi_season):
    res = get_yield_baseline().lookup(pune_location.district, "chickpea", rabi_season.name)
    assert res.yield_t_per_ha > 0.0
    assert res.yield_t_per_ha < 10.0  # realistic chickpea yield in t/ha
    assert res.tier in ("district_crop_season", "district_crop", "crop_season", "crop")


def test_predict_yield_positive_and_capped(pune_location, rabi_season):
    scenarios = build_scenarios(pune_location, rabi_season)
    normal_sc = next(s for s in scenarios if s.id == "normal")
    yp = predict_yield("chickpea", pune_location, rabi_season, normal_sc)

    assert yp.t_per_ha.value > 0.0
    assert yp.t_per_ha.unit == "t/ha"
    assert isinstance(yp.clipped, bool)
    assert isinstance(yp.out_of_training_range, bool)


def test_predict_yield_scenario_variation(pune_location, rabi_season):
    scenarios = build_scenarios(pune_location, rabi_season)
    drought_sc = next(s for s in scenarios if s.id == "drought")
    normal_sc = next(s for s in scenarios if s.id == "normal")

    yp_d = predict_yield("chickpea", pune_location, rabi_season, drought_sc)
    yp_n = predict_yield("chickpea", pune_location, rabi_season, normal_sc)

    # In drought, yield should typically be less than or equal to normal
    assert yp_d.t_per_ha.value <= yp_n.t_per_ha.value * 1.05


# ── ML.4b Suitability & SHAP ──────────────────────────────────────────────────

def test_suitability_score_and_factors(pune_location, rabi_season):
    scenarios = build_scenarios(pune_location, rabi_season)
    normal_sc = next(s for s in scenarios if s.id == "normal")
    res = suitability("chickpea", pune_location, rabi_season, normal_sc)

    assert 0.0 <= res.score <= 3.0
    assert res.label in ("good", "average", "poor")
    assert len(res.top_factors) == 3
    for f in res.top_factors:
        assert f.feature
        assert f.direction in ("up", "down")
        assert f.effect_quintal_per_acre is not None


# ── Pipeline Integration ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_plan_end_to_end():
    from app.pipeline import run_plan

    profile = FarmProfile(
        location_text="Pune",
        land_acres=5.0,
        budget_rs=70000.0,
        water_source="borewell",
        borewell_count=1,
        pump_hours_per_day=4.0,
        irrigation_method="drip",
        risk_appetite="balanced",
        language="mr",
    )

    plan = await run_plan(profile)
    assert plan.plan_id.startswith("pl_")
    assert plan.location.district == "Pune"
    assert plan.season.name == "Rabi"
    assert len(plan.scenarios) == 3
    assert len(plan.crops) > 0

    # Ensure crops have valid options
    crop_ids = [c.crop_id for c in plan.crops]
    assert "chickpea" in crop_ids or "wheat" in crop_ids

    # Verify strategies
    assert len(plan.strategies) == 4
    strat_ids = [s.id for s in plan.strategies]
    assert "traditional" in strat_ids
    assert "lp_max_profit" in strat_ids
    assert "qp_balanced" in strat_ids
    assert "qp_drought_safe" in strat_ids

    assert plan.recommended_strategy == "qp_balanced"
    rec_strat = next(s for s in plan.strategies if s.id == plan.recommended_strategy)
    assert rec_strat.feasible is True
    assert len(rec_strat.allocations) > 0
    total_acres = sum(a.acres for a in rec_strat.allocations)
    assert total_acres <= profile.land_acres + 1e-4
