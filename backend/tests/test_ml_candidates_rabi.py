"""Regression tests for the empty-Rabi-plan investigation (crop aliases, DES 'Whole Year'
rows, season-window ET0, scenario wiring into the yield model)."""

from __future__ import annotations

import math
from datetime import date

import pytest

from app.ml import suitability as S
from app.ml.scenarios import build_scenarios
from app.ml.yield_baseline import get_yield_baseline
from app.ml.yield_model import build_feature_dict, predict_yield
from app.schemas import Location, Season, SowingWindow

RABI = Season(
    name="Rabi",
    sowing_window=SowingWindow(start="2026-10-15", end="2026-12-15"),
    status="official_dataset",
)


def _loc(district: str) -> Location:
    return Location(
        input=district, resolved_name=f"{district}, Maharashtra", district=district,
        state="Maharashtra", latitude=18.5, longitude=73.8,
    )


def test_rabi_maize_calendar_row_maps_to_master_maize():
    sowable = S._sowable_crops(date(2026, 11, 1), "Rabi")
    assert "maize" in sowable and "maize_rabi" not in sowable
    assert sowable["maize"]["season"] == "Rabi"
    assert sowable["maize"]["duration_days"] == 115  # the maize_rabi calendar row


def test_season_filter_drops_other_season_rows():
    sowable = S._sowable_crops(date(2026, 11, 1), "Rabi")
    assert all(v["season"] in ("Rabi", "Whole Year") for v in sowable.values())


@pytest.mark.parametrize("district", ["Pune", "Nashik", "Solapur"])
def test_onion_counted_as_grown_despite_whole_year_des_label(district):
    assert "onion" in S._grown_in_district(district, "Rabi")


def test_more_than_wheat_and_chickpea_eligible_in_pune_rabi():
    cands, excluded = S.candidate_crops(
        None, _loc("Pune"), RABI, [], today=date(2026, 11, 1)
    )
    ids = {c.crop_id for c in cands}
    assert {"wheat", "chickpea", "maize", "onion"} <= ids
    assert all(e.crop_id not in ids for e in excluded)


def test_whole_year_only_crop_uses_district_baseline_not_unseen_season_model():
    base = get_yield_baseline()
    assert not base.has_season("onion", "Rabi")
    sc = build_scenarios(_loc("Pune"), RABI)
    preds = [predict_yield("onion", _loc("Pune"), RABI, s) for s in sc]
    assert all(p.t_per_ha.status == "official_dataset" for p in preds)
    assert len({p.t_per_ha.value for p in preds}) == 1  # disclosed baseline: no weather response


def test_scenario_weather_reaches_model_input():
    loc = _loc("Pune")
    sc = {s.id: s for s in build_scenarios(loc, RABI)}
    fd = {k: build_feature_dict("Pune", "wheat", "Rabi", s) for k, s in sc.items()}
    assert fd["drought"]["et0_total_mm"] == sc["drought"].et0_mm
    assert fd["excess"]["max_temp_c"] == sc["excess"].max_temp_c
    assert fd["drought"]["season_rainfall_mm"] == sc["drought"].rainfall_mm
    # preceding-Kharif rain of each analogue year is looked up and differs between scenarios
    kharif = {k: v["kharif_rain_mm"] for k, v in fd.items()}
    assert all(not math.isnan(v) for v in kharif.values())
    assert len({round(v, 1) for v in kharif.values()}) > 1


def test_scenarios_give_different_rabi_yields():
    loc = _loc("Solapur")
    sc = build_scenarios(loc, RABI)
    ys = {s.id: predict_yield("wheat", loc, RABI, s).t_per_ha.value for s in sc}
    assert len(set(ys.values())) > 1


def test_et0_is_divided_by_season_window_not_crop_duration():
    from app.ml.water_need import _et0_daily
    from app.schemas import SourcedValue, Scenario

    scen = Scenario(
        id="normal", label="n",
        season_rain_mm=SourcedValue(value=10.0, unit="mm", source="t", as_of="2020", status="official_dataset"),
        probability=0.6, analogue_year=2020, rainfall_mm=10.0, et0_mm=755.0,
    )
    assert _et0_daily(scen, "Rabi", 120) == pytest.approx(755.0 / 151)


def test_chickpea_yield_matches_des_history_scale():
    """t/ha -> q/acre sanity: Pune wheat model output stays inside the DES 1997-2014 range."""
    from app.core.units import t_per_ha_to_q_per_acre

    loc = _loc("Pune")
    base = get_yield_baseline().lookup("Pune", "wheat", "Rabi")
    sc = build_scenarios(loc, RABI)
    for s in sc:
        y = predict_yield("wheat", loc, RABI, s).t_per_ha.value
        assert 0.5 * base.yield_t_per_ha <= y <= 1.25 * base.max_yield_t_per_ha
    assert t_per_ha_to_q_per_acre(1.0) == pytest.approx(4.047, abs=0.01)
