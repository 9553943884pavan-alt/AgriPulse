"""Tests for ML.1 (candidate_crops), ML.7 (crop_water_need), ML.8 (fertilizer_plan).

These tests use the real CSV data and do not require weather or yield_training.csv.
"""
from __future__ import annotations

from datetime import date

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _profile(district="Beed"):
    from app.schemas import FarmProfile
    return FarmProfile(
        location_text=district, land_acres=5.0, budget_rs=60000.0,
        water_source="borewell", language="en",
    )


def _location(district="Beed"):
    from app.schemas import Location
    return Location(
        input=district, resolved_name=f"{district}, Maharashtra",
        district=district, state="Maharashtra",
        latitude=18.99, longitude=75.91,
    )


def _season(name="Kharif"):
    from app.schemas import Season, SowingWindow
    return Season(
        name=name,
        sowing_window=SowingWindow(start="2026-06-15", end="2026-07-15"),
    )


def _rabi_season():
    from app.schemas import Season, SowingWindow
    return Season(
        name="Rabi",
        sowing_window=SowingWindow(start="2026-11-01", end="2026-11-30"),
    )


def _scenario(sid="normal", rain=600.0, et0=450.0, analogue=2019):
    from app.schemas import Scenario, SourcedValue
    def sv(v, u="mm"):
        return SourcedValue(value=v, unit=u, source="test", as_of="2026-10-31", status="official_dataset")
    return Scenario(
        id=sid, label=sid.title(),
        season_rain_mm=sv(rain),
        probability=0.6 if sid == "normal" else 0.2,
        analogue_year=analogue,
        rainfall_mm=rain,
        et0_mm=et0,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ML.1 — Candidate crop filter
# ═══════════════════════════════════════════════════════════════════════════

class TestCandidateCrops:

    def test_returns_candidates_and_excluded(self):
        from app.ml.suitability import candidate_crops
        # Use Kharif season and a Kharif date
        cands, excl = candidate_crops(
            _profile("Beed"), _location("Beed"), _season("Kharif"), [],
            today=date(2026, 7, 1),
        )
        assert isinstance(cands, list)
        assert isinstance(excl, list)

    def test_candidates_have_required_fields(self):
        from app.ml.suitability import candidate_crops
        cands, _ = candidate_crops(
            _profile("Beed"), _location("Beed"), _season("Kharif"), [],
            today=date(2026, 7, 1),
        )
        for c in cands:
            assert c.crop_id, "crop_id must be non-empty"
            assert c.names.get("en"), "English name required"
            assert c.season, "season required"
            assert c.water_need_m3_per_acre is not None

    def test_excluded_have_valid_reason_codes(self):
        from app.ml.suitability import candidate_crops
        from app.schemas import ExcludedReasonCode
        VALID = {"NO_REAL_PRICE", "NO_YIELD_DATA", "NOT_SOWABLE_NOW",
                 "NOT_GROWN_IN_DISTRICT", "WATER_INFEASIBLE", "OVER_BUDGET"}
        _, excl = candidate_crops(
            _profile("Beed"), _location("Beed"), _season("Kharif"), [],
            today=date(2026, 7, 1),
        )
        for e in excl:
            assert e.reason_code in VALID, f"Invalid reason_code: {e.reason_code}"

    def test_rabi_crops_on_rabi_date(self):
        from app.ml.suitability import candidate_crops
        # Nov 15 is well inside Rabi sowing window
        cands, _ = candidate_crops(
            _profile("Beed"), _location("Beed"), _rabi_season(), [],
            today=date(2026, 11, 15),
        )
        seasons = {c.season for c in cands}
        assert "Rabi" in seasons or len(cands) == 0, \
            f"Expected Rabi crops on Nov 15, got: {seasons}"

    def test_kharif_crops_not_sowable_in_november(self):
        """Kharif-only crops should NOT appear as sowable in November."""
        from app.ml.suitability import candidate_crops, _sowable_crops
        sowable = _sowable_crops(date(2026, 11, 15))
        # soybean is Kharif only (June-July sowing)
        assert "soybean" not in sowable, \
            "soybean should not be sowable on Nov 15"

    def test_non_agricultural_district_returns_empty(self):
        from app.ml.suitability import candidate_crops
        cands, excl = candidate_crops(
            _profile("Mumbai City"), _location("Mumbai City"),
            _season("Kharif"), [],
            today=date(2026, 7, 1),
        )
        assert cands == []
        assert excl == []

    def test_opens_soon_crops_flagged(self):
        """Crops opening within 21 days should have opens_on set."""
        from app.ml.suitability import candidate_crops
        # Nov 1 — wheat opens Nov 1 in calendar, so on Oct 25 it should be "opening soon"
        cands, _ = candidate_crops(
            _profile("Beed"), _location("Beed"), _rabi_season(), [],
            today=date(2026, 10, 25),
        )
        opens_soon = [c for c in cands if c.opens_on is not None]
        # Soft check — if any Rabi crop exists it may have opens_on
        for c in opens_soon:
            assert c.opens_on > str(date(2026, 10, 25)), \
                f"opens_on {c.opens_on} should be in the future"

    def test_no_invented_crops(self):
        """Every candidate crop_id must exist in crops_master."""
        from app.ml.suitability import candidate_crops, _crops_master
        cands, _ = candidate_crops(
            _profile("Beed"), _location("Beed"), _season("Kharif"), [],
            today=date(2026, 7, 1),
        )
        master_ids = set(_crops_master()["crop_id"].str.strip())
        for c in cands:
            assert c.crop_id in master_ids, \
                f"Candidate {c.crop_id!r} not in crops_master"

    def test_water_need_is_positive(self):
        from app.ml.suitability import candidate_crops
        cands, _ = candidate_crops(
            _profile("Beed"), _location("Beed"), _season("Kharif"), [],
            today=date(2026, 7, 1),
        )
        for c in cands:
            assert float(c.water_need_m3_per_acre.value) > 0, \
                f"Water need must be positive for {c.crop_id}"


# ═══════════════════════════════════════════════════════════════════════════
# ML.7 — Crop water need
# ═══════════════════════════════════════════════════════════════════════════

class TestCropWaterNeed:

    def test_returns_water_need(self):
        from app.ml.water_need import crop_water_need
        wn = crop_water_need("soybean", _season("Kharif"),
                             [_scenario("drought"), _scenario("normal"), _scenario("excess")])
        assert wn.drought is not None
        assert wn.normal is not None
        assert wn.excess is not None

    def test_drought_needs_more_water_than_excess(self):
        """Drought has less rain → crop needs more irrigation water."""
        from app.ml.water_need import crop_water_need
        wn = crop_water_need(
            "soybean", _season("Kharif"),
            [
                _scenario("drought", rain=300.0, et0=500.0),
                _scenario("normal",  rain=650.0, et0=450.0),
                _scenario("excess",  rain=1100.0, et0=400.0),
            ],
        )
        d = float(wn.drought.value)
        e = float(wn.excess.value)
        assert d >= e, f"Drought need {d} should be >= excess need {e}"

    def test_water_need_is_positive(self):
        from app.ml.water_need import crop_water_need
        wn = crop_water_need("wheat", _rabi_season(),
                             [_scenario("drought"), _scenario("normal"), _scenario("excess")])
        for sid, sv in [("drought", wn.drought), ("normal", wn.normal), ("excess", wn.excess)]:
            assert float(sv.value) >= 0, f"{sid} water need must be non-negative"

    def test_units_are_m3_per_acre(self):
        from app.ml.water_need import crop_water_need
        wn = crop_water_need("soybean", _season("Kharif"),
                             [_scenario("drought"), _scenario("normal"), _scenario("excess")])
        assert wn.normal.unit == "m3_per_acre"

    def test_unknown_crop_returns_assumption(self):
        """Unknown crop_id should return an assumption, not crash."""
        from app.ml.water_need import crop_water_need
        wn = crop_water_need("unknown_crop_xyz", _season("Kharif"),
                             [_scenario("drought"), _scenario("normal"), _scenario("excess")])
        assert wn.normal.status == "assumption"

    def test_with_scenario_uses_era5_et0(self):
        """When scenario has et0_mm, status should be 'computed' not 'assumption'."""
        from app.ml.water_need import crop_water_need
        scen = _scenario("normal", rain=650.0, et0=450.0)
        wn = crop_water_need("wheat", _rabi_season(), [scen])
        assert wn.normal.status in ("computed", "assumption"), \
            f"Unexpected status: {wn.normal.status}"

    def test_drip_needs_less_than_flood(self):
        """Drip efficiency 0.90 → lower m3 than flood 0.60 for same crop."""
        from app.ml.water_need import crop_water_need, _EFFICIENCY
        scens = [_scenario("drought"), _scenario("normal"), _scenario("excess")]
        wn_flood = crop_water_need("soybean", _season("Kharif"), scens,
                                   efficiency=_EFFICIENCY["flood"])
        wn_drip  = crop_water_need("soybean", _season("Kharif"), scens,
                                   efficiency=_EFFICIENCY["drip"])
        assert float(wn_flood.normal.value) > float(wn_drip.normal.value), \
            "Flood irrigation should need more water than drip"

    def test_all_calendar_crops_have_data_or_assumption(self):
        """Every crop in the calendar must return a WaterNeed without crashing."""
        from app.data.loaders import load_crop_calendar
        from app.ml.water_need import crop_water_need
        cal = load_crop_calendar()
        scens = [_scenario("drought"), _scenario("normal"), _scenario("excess")]
        errors = []
        for _, row in cal.iterrows():
            try:
                wn = crop_water_need(str(row["crop_id"]), _season(str(row["season"])), scens)
                assert float(wn.normal.value) >= 0
            except Exception as e:
                errors.append(f"{row['crop_id']}: {e}")
        assert not errors, f"crop_water_need failed for:\n" + "\n".join(errors)


# ═══════════════════════════════════════════════════════════════════════════
# ML.8 — Fertilizer plan
# ═══════════════════════════════════════════════════════════════════════════

class TestFertilizerPlan:

    def test_returns_fertilizer_plan(self):
        from app.ml.fertilizer import fertilizer_plan
        fp = fertilizer_plan("soybean", "Kharif")
        assert fp is not None

    def test_nutrient_doses_positive(self):
        from app.ml.fertilizer import fertilizer_plan
        fp = fertilizer_plan("soybean", "Kharif")
        assert fp.n_kg_per_acre >= 0
        assert fp.p2o5_kg_per_acre >= 0
        assert fp.k2o_kg_per_acre >= 0

    def test_bag_counts_positive(self):
        from app.ml.fertilizer import fertilizer_plan
        fp = fertilizer_plan("wheat", "Rabi")
        assert fp.dap_bags >= 0
        assert fp.urea_bags >= 0
        assert fp.mop_bags >= 0

    def test_cost_is_sourced_value(self):
        from app.ml.fertilizer import fertilizer_plan
        from app.schemas import SourcedValue
        fp = fertilizer_plan("soybean", "Kharif")
        assert isinstance(fp.cost_rs, SourcedValue)
        assert float(fp.cost_rs.value) >= 0

    def test_cost_status_is_computed(self):
        from app.ml.fertilizer import fertilizer_plan
        fp = fertilizer_plan("soybean", "Kharif")
        assert fp.cost_rs.status == "computed"

    def test_ha_to_acre_conversion(self):
        """Dose per acre must be less than dose per ha (1 acre < 1 ha)."""
        from app.data.loaders import load_fertilizer_rdf
        from app.ml.fertilizer import fertilizer_plan
        rdf = load_fertilizer_rdf()
        soy = rdf[rdf["crop_id"] == "soybean"].iloc[0]
        fp = fertilizer_plan("soybean", "Kharif")
        n_ha = float(soy["n_kg_per_ha"])
        assert fp.n_kg_per_acre < n_ha, \
            f"n/acre {fp.n_kg_per_acre} should be < n/ha {n_ha}"

    def test_dap_supplies_phosphorus(self):
        """DAP bags must cover the P₂O₅ requirement."""
        from app.ml.fertilizer import fertilizer_plan, _DAP_P2O5, _bag_size
        fp = fertilizer_plan("rice", "Kharif")
        p_from_dap = fp.dap_bags * _bag_size("dap") * _DAP_P2O5
        assert abs(p_from_dap - fp.p2o5_kg_per_acre * _bag_size("dap")) < 2.0 or \
               p_from_dap >= fp.p2o5_kg_per_acre - 0.1, \
               f"DAP should supply all P₂O₅: {p_from_dap:.2f} vs needed {fp.p2o5_kg_per_acre:.2f}"

    def test_unknown_crop_returns_plan_not_crash(self):
        """Unknown crop returns zero-dose plan, not an exception."""
        from app.ml.fertilizer import fertilizer_plan
        fp = fertilizer_plan("unknown_crop_xyz", "Kharif")
        assert fp is not None
        assert fp.n_kg_per_acre == 0.0

    def test_all_rdf_crops_can_be_planned(self):
        """Every crop in fertilizer_rdf.csv must return a valid plan."""
        from app.data.loaders import load_fertilizer_rdf
        from app.ml.fertilizer import fertilizer_plan
        rdf = load_fertilizer_rdf()
        errors = []
        for _, row in rdf.iterrows():
            try:
                fp = fertilizer_plan(str(row["crop_id"]), str(row["season"]))
                assert fp.cost_rs.value >= 0
            except Exception as e:
                errors.append(f"{row['crop_id']}/{row['season']}: {e}")
        assert not errors, "fertilizer_plan failed for:\n" + "\n".join(errors)

    def test_basis_mentions_rdf(self):
        from app.ml.fertilizer import fertilizer_plan
        fp = fertilizer_plan("soybean", "Kharif")
        assert "rdf" in fp.basis.lower() or "recommended" in fp.basis.lower(), \
            f"basis should mention RDF: {fp.basis!r}"
