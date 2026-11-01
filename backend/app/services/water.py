"""SVC.7 — Water budget service (one WaterBudget per scenario).

Optimizer contract (Phase 2):
  crop_water_need_m3_per_acre(s) is *net irrigation demand*.  It has already
  subtracted effective rainfall in ``app.ml.water_need``.  Therefore the
  optimizer's available-water limit is only deliverable irrigation supply:

  irrigation_available(s) = groundwater_share + canal_share

Effective rainfall is retained as a sourced diagnostic quantity in
``available_m3.rain`` so the UI can explain the demand calculation; it is not
included in ``available_m3.total``.  Adding it there would credit rainfall
twice.

  groundwater_share = borewell_capacity × CATEGORY_CAP[category]
  canal_share = CANAL_DUTY × area × (reservoir_pct/100)  when canal_access

Constants from ml/SPECS §7A (all marked assumption until sourced):
  EFFECTIVE_RAIN_FACTOR = 0.75
  CATEGORY_CAP: Safe=1.0, Semi-critical=0.7, Critical=0.4, Over-exploited=0.15
  CANAL_DUTY = unavailable until a source is added
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.core.units import mm_to_m3_per_acre
from app.data.loaders import load_groundwater, load_irrigation, load_reservoir_storage
from app.data.resolver import resolve_district
from app.schemas import (
    DefaultUsed,
    FarmProfile,
    Location,
    Scenario,
    SourcedValue,
    WaterAvailable,
    WaterBasis,
    WaterBudget,
    WaterNeedSummary,
    Warning,
)

logger = logging.getLogger(__name__)

# ── Modelling constants (assumption — see ml/SPECS §7A) ──────────────────────
EFFECTIVE_RAIN_FACTOR = 0.75
CATEGORY_CAP: dict[str, float] = {
    "safe": 1.0,
    "semi-critical": 0.7,
    "critical": 0.4,
    "over-exploited": 0.15,
}
CANAL_DUTY_M3_PER_ACRE: float | None = None  # Do not credit canal water until a duty is sourced.
SEASON_DAYS = 120                   # typical Kharif/Rabi season length (assumption)


def _sv_assumption(value: float | int | str, unit: str, note: str) -> SourcedValue:
    return SourcedValue(
        value=value, unit=unit,
        source=f"Modelling assumption — {note}",
        source_url="", as_of="2024",
        status="assumption",
    )


def _sv_computed(value: float, unit: str, formula: str) -> SourcedValue:
    return SourcedValue(
        value=round(value, 1), unit=unit,
        source=f"Computed: {formula}",
        source_url="", as_of="current",
        status="computed",
    )


def _sv_official(value: float, unit: str, source: str, as_of: str) -> SourcedValue:
    return SourcedValue(value=round(value, 2), unit=unit, source=source, source_url="", as_of=as_of, status="official_dataset")


def build_water_budgets(
    profile: FarmProfile,
    location: Location,
    scenarios: list[Scenario],
    weather: dict,
) -> list[WaterBudget]:
    """Return one WaterBudget per scenario (3 items)."""
    budgets = []
    for scenario in scenarios:
        budgets.append(_build_one(profile, location, scenario, weather))
    return budgets


def _build_one(
    profile: FarmProfile,
    location: Location,
    scenario: Scenario,
    weather: dict,
) -> WaterBudget:
    area = profile.land_acres
    district = location.district

    # ── Rain so far (observed) ─────────────────────────────────────────────
    rain_sv = weather.get("precipitation_recent_mm")
    rain_so_far_mm = float(rain_sv.value) if rain_sv else 0.0

    # ── Scenario remaining rain (analogue year) ────────────────────────────
    scenario_rain_mm = float(scenario.season_rain_mm.value) if scenario.season_rain_mm else 0.0
    forecast_sv = weather.get("precipitation_forecast_mm")
    forecast_rain_mm = float(forecast_sv.value) if forecast_sv else 0.0
    remaining_rain_mm = max(0.0, scenario_rain_mm - rain_so_far_mm - forecast_rain_mm)
    total_effective_rain_mm = (
        rain_so_far_mm + forecast_rain_mm + remaining_rain_mm
    ) * EFFECTIVE_RAIN_FACTOR
    rain_m3 = mm_to_m3_per_acre(total_effective_rain_mm) * area

    # ── Groundwater ────────────────────────────────────────────────────────
    gw_category, extraction_pct = _get_groundwater_info(district)
    cap = CATEGORY_CAP.get(gw_category.lower())
    capacity_m3 = _borewell_capacity(profile)
    gw_m3 = capacity_m3 * cap if cap is not None else 0.0
    groundwater_value = _sv_computed(
        gw_m3,
        "m3",
        "borewell_capacity × category_cap",
    )
    has_borewell = profile.water_source in {"borewell", "both"}
    has_borewell_capacity_inputs = (
        profile.borewell_count is not None
        and profile.borewell_count > 0
        and profile.borewell_yield_lph is not None
        and profile.pump_hours_per_day is not None
    )
    if has_borewell and not has_borewell_capacity_inputs:
        groundwater_value = _sv_assumption(
            0.0,
            "m3",
            "No farmer-supplied borewell yield/pump hours or sourced district median; "
            "groundwater is not credited",
        )
    elif cap is None:
        groundwater_value = _sv_assumption(
            0.0,
            "m3",
            "District-average groundwater category unavailable; groundwater is not credited",
        )

    # ── Canal ──────────────────────────────────────────────────────────────
    reservoir_info = _get_reservoir_info(district)
    reservoir_pct = reservoir_info[0] if reservoir_info else None
    reservoir_as_of = reservoir_info[1] if reservoir_info else "unavailable"
    if (
        profile.canal_access
        and reservoir_pct is not None
        and CANAL_DUTY_M3_PER_ACRE is not None
    ):
        canal_m3 = CANAL_DUTY_M3_PER_ACRE * area * (reservoir_pct / 100.0)
        canal_value = _sv_computed(canal_m3, "m3", "sourced canal duty × area × reservoir storage")
    elif profile.canal_access:
        canal_m3 = 0.0
        canal_value = _sv_assumption(
            0.0,
            "m3",
            "Canal water not credited because canal duty or current reservoir data is unavailable",
        )
    else:
        canal_m3 = 0.0
        canal_value = SourcedValue(
            value=0.0,
            unit="m3",
            source="Farmer reports no canal access",
            source_url="",
            as_of="current",
            status="farmer_input",
        )

    # ``crop_water_need`` is already net of effective rainfall.  The water
    # constraint must consequently use irrigation supply only; rain_m3 stays
    # in the response as a diagnostic/provenance value, not a second supply.
    total_m3 = gw_m3 + canal_m3

    # ── Irrigation efficiency ──────────────────────────────────────────────
    efficiency_pct = _get_efficiency(profile, district)

    return WaterBudget(
        scenario=scenario.id,
        analogue_year=scenario.analogue_year,
        available_m3=WaterAvailable(
            rain=_sv_computed(rain_m3, "m3", "effective_rain × area"),
            groundwater=groundwater_value,
            canal=canal_value,
            total=_sv_computed(
                total_m3,
                "m3",
                "groundwater + canal; effective rainfall is already netted in crop demand",
            ),
        ),
        basis=WaterBasis(
            groundwater_category=(
                SourcedValue(
                    value=gw_category,
                    unit="category",
                    source="CGWB (Central Ground Water Board) block data — district average",
                    source_url="https://cgwb.gov.in",
                    as_of="2022",
                    status="official_dataset",
                )
                if gw_category in {"Safe", "Semi-critical", "Critical", "Over-exploited"}
                else _sv_assumption(gw_category, "category", "District-average groundwater category unavailable")
            ),
            category_cap=(
                _sv_assumption(cap, "fraction", "CGWB category cap — needs GSDA citation")
                if cap is not None
                else _sv_assumption(
                    "unavailable",
                    "fraction",
                    "Groundwater category unavailable; no category cap applied",
                )
            ),
            effective_rain_factor=_sv_assumption(
                EFFECTIVE_RAIN_FACTOR, "fraction",
                "FAO-56 effective rainfall factor — needs citation in SOURCES.md",
            ),
            reservoir_storage_pct=(
                _sv_official(
                    reservoir_pct,
                    "pct",
                    "CWC weekly bulletin",
                    reservoir_as_of,
                )
                if reservoir_pct is not None
                else _sv_assumption(0.0, "pct", "No current reservoir observation available")
            ),
            rain_so_far_mm=SourcedValue(
                value=rain_so_far_mm, unit="mm",
                source="Open-Meteo forecast (past_days=92)",
                source_url="https://api.open-meteo.com",
                as_of=rain_sv.as_of if rain_sv else "unavailable",
                status=rain_sv.status if rain_sv else "assumption",
            ),
        ),
        irrigation_method=profile.irrigation_method or "flood",
        efficiency_pct=_sv_official(efficiency_pct, "pct", "Minor Irrigation Census (MoJS)", "2017-18"),
        need_m3=WaterNeedSummary(
            traditional_plan=_sv_computed(0, "m3", "set by pipeline after traditional plan is built"),
            recommended_plan=_sv_computed(0, "m3", "set by pipeline after recommended plan is built"),
        ),
    )


def wants_borewell_capacity(profile: FarmProfile) -> bool:
    """True when the farmer has a borewell but gave no yield / pump hours."""
    return profile.water_source in ("borewell", "both") and (
        profile.borewell_yield_lph is None or profile.pump_hours_per_day is None
    )


def normalise_borewell(profile: FarmProfile) -> FarmProfile:
    """Yield and pump hours given but borewell count missing -> assume ONE borewell, disclosed.

    Shared by /api/plan and the agent so both build the same water budget.
    """
    if (
        profile.water_source in ("borewell", "both")
        and not profile.borewell_count
        and profile.borewell_yield_lph
        and profile.pump_hours_per_day
    ):
        return profile.model_copy(update={
            "borewell_count": 1,
            "defaults_used": [
                *[d for d in profile.defaults_used if d.field != "borewell_count"],
                DefaultUsed(
                    field="borewell_count",
                    value=1,
                    basis="Farmer gave borewell yield and pump hours but not the number of borewells; assumed 1",
                ),
            ],
        })
    return profile


def borewell_disclosure(profile: FarmProfile) -> tuple[FarmProfile, list[Warning]]:
    """Same disclosure run_plan makes: borewell declared but capacity unknown -> 0 m3
    groundwater credited, with an ASSUMED_BOREWELL warning and a defaults_used entry."""
    if profile.water_source in ("borewell", "both") and not (
        profile.borewell_count and profile.borewell_yield_lph and profile.pump_hours_per_day
    ):
        profile = profile.model_copy(update={"defaults_used": [
            *[d for d in profile.defaults_used if d.field != "borewell_capacity"],
            DefaultUsed(
                field="borewell_capacity",
                value=0,
                basis="Borewell yield / pump hours not provided; groundwater not counted in the water budget",
            ),
        ]})
        return profile, [Warning(code="ASSUMED_BOREWELL", params={"groundwater_credited_m3": 0})]
    return profile, []


def _borewell_capacity(profile: FarmProfile) -> float:
    """Total borewell water available this season (m3)."""
    count = profile.borewell_count or 0
    # Only a borewell farm draws groundwater; leftover borewell numbers on a
    # canal-only or rainfed profile (e.g. "now I have canal water instead") count 0.
    if count == 0 or profile.water_source not in ("borewell", "both"):
        return 0.0
    if profile.borewell_yield_lph is None or profile.pump_hours_per_day is None:
        return 0.0
    yield_lph = profile.borewell_yield_lph
    hours = profile.pump_hours_per_day
    capacity_m3 = count * yield_lph * hours * SEASON_DAYS / 1000.0  # litres → m3
    return capacity_m3


def _get_groundwater_info(district: str) -> tuple[str, float]:
    """Return (category, extraction_pct) for the district average block row."""
    df = load_groundwater()
    canonical = resolve_district(district) or district
    rows = df[df["district"].str.lower() == canonical.lower()]
    avg_rows = rows[rows["block"].str.contains("District Avg", case=False, na=False)]
    if avg_rows.empty:
        return "Unavailable", 0.0
    r = avg_rows.iloc[0]
    category = str(r.get("category", "Unavailable"))
    if category.lower() not in CATEGORY_CAP:
        return "Unavailable", 0.0
    extraction_value = r.get("extraction_pct")
    extraction = float(extraction_value) if extraction_value is not None else 0.0
    return category, extraction


def _get_reservoir_info(district: str) -> tuple[float, str] | None:
    """Return current storage for serving reservoirs, rejecting stale bulletins."""
    try:
        df = load_reservoir_storage()
        canonical = resolve_district(district) or district
        served_col = "districts_served" if "districts_served" in df.columns else "district"

        def serves_district(value: object) -> bool:
            names = ("" if value is None else str(value)).split("|")
            return any(
                (resolve_district(name.strip()) or name.strip()).casefold() == canonical.casefold()
                for name in names
                if name.strip()
            )

        rows = df[df[served_col].map(serves_district)]
        if rows.empty or "observation_date" not in rows.columns:
            return None

        today = date.today()
        dated_indexes = []
        parsed_dates = {}
        for index, value in rows["observation_date"].items():
            try:
                observation_date = date.fromisoformat(str(value)[:10])
            except ValueError:
                continue
            if today - timedelta(days=7) <= observation_date <= today:
                dated_indexes.append(index)
                parsed_dates[index] = observation_date
        if not dated_indexes:
            return None
        latest_date = max(parsed_dates.values())
        rows = rows.loc[
            [index for index in dated_indexes if parsed_dates[index] == latest_date]
        ]

        col = next((
            name for name in (
                "live_storage_pct_of_capacity",
                "live_storage_pct",
                "storage_pct",
                "live_pct",
            ) if name in rows.columns
        ), None)
        if rows.empty or col is None:
            return None

        values = []
        for value in rows[col]:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if 0 <= number <= 100:
                values.append(number)
        if not values:
            return None

        return sum(values) / len(values), latest_date.isoformat()
    except Exception as exc:
        logger.warning("Reservoir lookup failed for %s: %s", district, exc)
    return None


def _get_efficiency(profile: FarmProfile, district: str) -> float:
    """Return irrigation efficiency (%) for the farmer's method."""
    method = profile.irrigation_method or "flood"
    try:
        df = load_irrigation()
        canonical = resolve_district(district) or district
        rows = df[df["district"].str.lower() == canonical.lower()]
        if not rows.empty:
            col = f"efficiency_{method}_pct"
            if col in rows.columns:
                val = rows.iloc[0].get(col)
                if val and float(val) > 0:
                    return float(val)
    except Exception:
        pass
    # Defaults from Minor Irrigation Census
    return {"flood": 60.0, "sprinkler": 75.0, "drip": 90.0}.get(method, 60.0)
