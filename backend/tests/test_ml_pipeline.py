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


@pytest.mark.asyncio
async def test_agent_water_budget_tool_accepts_sync_service(monkeypatch):
    from app.agent import tools
    from app.services import water

    expected = [object(), object(), object()]
    monkeypatch.setattr(water, "build_water_budgets", lambda *args: expected)

    actual = await tools.get_water_budget(object(), object(), [], {})

    assert actual is expected


def test_weather_parser_averages_humidity_for_each_day():
    from app.services.weather import _parse_weather

    raw = {
        "daily": {
            "time": ["2026-10-30", "2026-10-31"],
            "precipitation_sum": [1.0, 2.0],
            "et0_fao_evapotranspiration": [3.0, 4.0],
            "temperature_2m_max": [25.0, 27.0],
            "temperature_2m_min": [15.0, 17.0],
        },
        "hourly": {"relative_humidity_2m": [20.0] * 24 + [80.0] * 24},
    }

    parsed = _parse_weather(raw, status="live", as_of="2026-10-31")

    assert parsed["humidity_pct"].value == 50.0


def test_water_budget_keeps_effective_rain_diagnostic_but_excludes_it_from_irrigation_supply(monkeypatch):
    from app.services import water
    from app.schemas import FarmProfile, Location, Scenario, SourcedValue

    monkeypatch.setattr(water, "_get_groundwater_info", lambda district: ("Safe", 50.0))
    monkeypatch.setattr(water, "_borewell_capacity", lambda profile: 0.0)
    monkeypatch.setattr(water, "_get_efficiency", lambda profile, district: 60.0)

    profile = FarmProfile(
        location_text="Pune", land_acres=1.0, budget_rs=10000.0,
        water_source="rainfed",
    )
    location = Location(
        input="Pune", resolved_name="Pune, Maharashtra", district="Pune",
        state="Maharashtra", latitude=18.52, longitude=73.85,
    )
    scenario = Scenario(
        id="drought", label="Drought",
        season_rain_mm=SourcedValue(
            value=100.0, unit="mm", source="test", as_of="2020",
            status="official_dataset",
        ),
        probability=0.2, analogue_year=2020,
    )
    weather = {
        "precipitation_recent_mm": SourcedValue(
            value=20.0, unit="mm", source="test", as_of="2026-10-31",
            status="live",
        ),
        "precipitation_forecast_mm": SourcedValue(
            value=90.0, unit="mm", source="test", as_of="2026-10-31",
            status="live",
        ),
    }

    budget = water._build_one(profile, location, scenario, weather)

    assert budget.available_m3.rain.value == pytest.approx(110.0 * 0.75 * 4.047, abs=1.0)
    assert budget.available_m3.total.value == 0.0
    assert "already netted" in budget.available_m3.total.source


def test_missing_borewell_capacity_is_disclosed_and_not_credited(monkeypatch):
    from app.services import water
    from app.schemas import FarmProfile, Location, Scenario, SourcedValue

    monkeypatch.setattr(water, "_get_groundwater_info", lambda district: ("Safe", 50.0))
    monkeypatch.setattr(water, "_get_efficiency", lambda profile, district: 60.0)
    profile = FarmProfile(
        location_text="Pune",
        land_acres=1.0,
        budget_rs=10000.0,
        water_source="borewell",
        borewell_count=1,
    )
    location = Location(
        input="Pune",
        resolved_name="Pune, Maharashtra",
        district="Pune",
        state="Maharashtra",
        latitude=18.52,
        longitude=73.85,
    )
    scenario = Scenario(
        id="drought",
        label="Drought",
        season_rain_mm=SourcedValue(
            value=100.0,
            unit="mm",
            source="test",
            as_of="2026",
            status="official_dataset",
        ),
        probability=0.2,
        analogue_year=2020,
    )

    budget = water._build_one(profile, location, scenario, {})

    assert budget.available_m3.groundwater.value == 0.0
    assert budget.available_m3.groundwater.status == "assumption"
    assert "not credited" in budget.available_m3.groundwater.source


def test_reservoir_lookup_uses_processed_districts_served_column(monkeypatch):
    from datetime import date
    import pandas as pd
    from app.services import water

    monkeypatch.setattr(
        water,
        "load_reservoir_storage",
        lambda: pd.DataFrame([{
            "districts_served": "Pune|Satara",
            "live_storage_pct_of_capacity": 55.0,
            "observation_date": date.today().isoformat(),
        }]),
    )

    assert water._get_reservoir_info("Pune") == (55.0, date.today().isoformat())


def test_reservoir_lookup_rejects_stale_observation(monkeypatch):
    from datetime import date, timedelta
    import pandas as pd
    from app.services import water

    stale_date = (date.today() - timedelta(days=8)).isoformat()
    monkeypatch.setattr(
        water,
        "load_reservoir_storage",
        lambda: pd.DataFrame([{
            "districts_served": "Pune|Satara",
            "live_storage_pct_of_capacity": 55.0,
            "observation_date": stale_date,
        }]),
    )

    assert water._get_reservoir_info("Pune") is None


@pytest.mark.parametrize(
    "rows",
    [
        [{"district": "Pune", "block": "Some Block", "category": "Safe", "extraction_pct": 40.0}],
        [{"district": "Pune", "block": "District Avg", "extraction_pct": 40.0}],
    ],
)
def test_groundwater_lookup_requires_district_average_category(monkeypatch, rows):
    import pandas as pd
    from app.services import water

    monkeypatch.setattr(water, "load_groundwater", lambda: pd.DataFrame(rows))

    assert water._get_groundwater_info("Pune") == ("Unavailable", 0.0)


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
async def test_run_plan_end_to_end(monkeypatch):
    from app.pipeline import run_plan
    from app.schemas import Location, SourcedValue
    from app.services import location, prices, weather

    profile = FarmProfile(
        location_text="Pune",
        land_acres=5.0,
        budget_rs=70000.0,
        water_source="borewell",
        borewell_count=1,
        borewell_yield_lph=10000.0,
        pump_hours_per_day=4.0,
        irrigation_method="drip",
        risk_appetite="balanced",
        language="mr",
    )

    async def locate_pune(_location_text):
        return Location(
            input="Pune",
            resolved_name="Pune, Maharashtra",
            district="Pune",
            state="Maharashtra",
            latitude=18.52,
            longitude=73.85,
        )

    async def no_weather(_location):
        return {}

    async def fixed_price(_crop_id, _district, _state="Maharashtra"):
        return SourcedValue(
            value=10000.0,
            unit="rs_per_quintal",
            source="Deterministic integration-test fixture",
            as_of="2026-11",
            status="cached",
        )

    monkeypatch.setattr(location, "locate", locate_pune)
    monkeypatch.setattr(weather, "get_weather", no_weather)
    monkeypatch.setattr(prices, "get_price", fixed_price)

    plan = await run_plan(profile)
    assert plan.plan_id.startswith("pl_")
    assert plan.location.district == "Pune"
    assert plan.season.name == "Rabi"
    assert len(plan.scenarios) == 3
    assert len(plan.crops) > 0
    assert {budget.scenario for budget in plan.water} == {"drought", "normal", "excess"}
    assert all(budget.need_m3.recommended_plan.status == "computed" for budget in plan.water)
    assert all(budget.need_m3.recommended_plan.value >= 0 for budget in plan.water)

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

    # The public QP path is gated until aligned joint crop-profit samples are
    # available; the verified deterministic LP is the recommendation.
    assert plan.recommended_strategy == "lp_max_profit"
    rec_strat = next(s for s in plan.strategies if s.id == plan.recommended_strategy)
    assert rec_strat.feasible is True
    assert len(rec_strat.allocations) > 0
    total_acres = sum(a.acres for a in rec_strat.allocations)
    assert total_acres <= profile.land_acres + 1e-4
