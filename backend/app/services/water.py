"""SVC.7 — Water budget service (one WaterBudget per scenario).

Formula (ml/SPECS §6):
  available(s) = effective_rain(s) + groundwater_share + canal_share

  effective_rain(s) = (rain_so_far + forecast + remaining_analogue(s))
                      × EFFECTIVE_RAIN_FACTOR × area_acres × MM_TO_M3

  groundwater_share = borewell_capacity × CATEGORY_CAP[category]
  canal_share = CANAL_DUTY × area × (reservoir_pct/100)  when canal_access

Constants from ml/SPECS §7A (all marked assumption until sourced):
  EFFECTIVE_RAIN_FACTOR = 0.75
  CATEGORY_CAP: Safe=1.0, Semi-critical=0.7, Critical=0.4, Over-exploited=0.15
  CANAL_DUTY = 3500 m3/acre/season (Maharashtra WRD, to be cited)
"""

from __future__ import annotations

import logging

from app.core.units import mm_to_m3_per_acre
from app.data.loaders import load_groundwater, load_irrigation, load_reservoir_storage
from app.data.resolver import resolve_district
from app.schemas import (
    FarmProfile,
    Location,
    Scenario,
    SourcedValue,
    WaterAvailable,
    WaterBasis,
    WaterBudget,
    WaterNeedSummary,
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
CANAL_DUTY_M3_PER_ACRE = 3500.0     # Maharashtra WRD — needs citation in SOURCES.md
DEFAULT_BOREWELL_LPH = 6000.0       # district median Minor Irrigation Census (assumption)
DEFAULT_PUMP_HOURS = 6.0
SEASON_DAYS = 120                   # typical Kharif/Rabi season length (assumption)


def _sv_assumption(value: float, unit: str, note: str) -> SourcedValue:
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
    remaining_rain_mm = max(0.0, scenario_rain_mm - rain_so_far_mm)
    total_effective_rain_mm = (rain_so_far_mm + remaining_rain_mm) * EFFECTIVE_RAIN_FACTOR
    rain_m3 = mm_to_m3_per_acre(total_effective_rain_mm) * area

    # ── Groundwater ────────────────────────────────────────────────────────
    gw_category, extraction_pct = _get_groundwater_info(district)
    cap = CATEGORY_CAP.get(gw_category.lower(), 0.15)
    capacity_m3 = _borewell_capacity(profile)
    gw_m3 = capacity_m3 * cap

    # ── Canal ──────────────────────────────────────────────────────────────
    if profile.canal_access:
        reservoir_pct = _get_reservoir_pct(district)
        canal_m3 = CANAL_DUTY_M3_PER_ACRE * area * (reservoir_pct / 100.0)
    else:
        canal_m3 = 0.0
        reservoir_pct = 0.0

    total_m3 = rain_m3 + gw_m3 + canal_m3

    # ── Irrigation efficiency ──────────────────────────────────────────────
    efficiency_pct = _get_efficiency(profile, district)

    return WaterBudget(
        scenario=scenario.id,
        analogue_year=scenario.analogue_year,
        available_m3=WaterAvailable(
            rain=_sv_computed(rain_m3, "m3", "effective_rain × area"),
            groundwater=_sv_computed(gw_m3, "m3", "borewell_capacity × category_cap"),
            canal=_sv_computed(canal_m3, "m3", "canal_duty × area × reservoir_pct"),
            total=_sv_computed(total_m3, "m3", "rain + groundwater + canal"),
        ),
        basis=WaterBasis(
            groundwater_category=_sv_official(
                0, gw_category,
                "CGWB (Central Ground Water Board) block data — district average",
                "2022",
            ),
            category_cap=_sv_assumption(cap, "fraction", "CGWB category cap — needs GSDA citation"),
            effective_rain_factor=_sv_assumption(
                EFFECTIVE_RAIN_FACTOR, "fraction",
                "FAO-56 effective rainfall factor — needs citation in SOURCES.md",
            ),
            reservoir_storage_pct=_sv_official(reservoir_pct, "pct", "CWC weekly bulletin", "current"),
            rain_so_far_mm=SourcedValue(
                value=rain_so_far_mm, unit="mm",
                source="Open-Meteo forecast (past_days=92)",
                source_url="https://api.open-meteo.com",
                as_of="current", status="live" if rain_sv else "cached",
            ),
        ),
        irrigation_method=profile.irrigation_method or "flood",
        efficiency_pct=_sv_official(efficiency_pct, "pct", "Minor Irrigation Census (MoJS)", "2017-18"),
        need_m3=WaterNeedSummary(
            traditional_plan=_sv_computed(0, "m3", "set by pipeline after traditional plan is built"),
            recommended_plan=_sv_computed(0, "m3", "set by pipeline after recommended plan is built"),
        ),
    )


def _borewell_capacity(profile: FarmProfile) -> float:
    """Total borewell water available this season (m3)."""
    count = profile.borewell_count or 0
    if count == 0 or profile.water_source == "rainfed":
        return 0.0
    yield_lph = profile.borewell_yield_lph or DEFAULT_BOREWELL_LPH   # assumption if unknown
    hours = profile.pump_hours_per_day or DEFAULT_PUMP_HOURS
    capacity_m3 = count * yield_lph * hours * SEASON_DAYS / 1000.0  # litres → m3
    return capacity_m3


def _get_groundwater_info(district: str) -> tuple[str, float]:
    """Return (category, extraction_pct) for the district average block row."""
    df = load_groundwater()
    canonical = resolve_district(district) or district
    rows = df[df["district"].str.lower() == canonical.lower()]
    avg_rows = rows[rows["block"].str.contains("District Avg", case=False, na=False)]
    if avg_rows.empty:
        avg_rows = rows  # fallback to first row
    if avg_rows.empty:
        return "Semi-critical", 70.0  # conservative assumption
    r = avg_rows.iloc[0]
    category = str(r.get("category", "Semi-critical"))
    extraction = float(r.get("extraction_pct", 70.0) or 70.0)
    return category, extraction


def _get_reservoir_pct(district: str) -> float:
    """Return average live storage % for reservoirs serving the district."""
    try:
        df = load_reservoir_storage()
        canonical = resolve_district(district) or district
        rows = df[df["district"].str.lower() == canonical.lower()]
        if rows.empty:
            return 60.0  # assumption: 60% full if no data
        col = next((c for c in ["live_storage_pct", "storage_pct", "live_pct"] if c in rows.columns), None)
        if col:
            return float(rows[col].mean())
    except Exception as exc:
        logger.warning("Reservoir lookup failed for %s: %s", district, exc)
    return 60.0


def _get_efficiency(profile: FarmProfile, district: str) -> float:
    """Return irrigation efficiency (%) for the farmer's method."""
    method = profile.irrigation_method or "flood"
    try:
        df = load_irrigation()
        canonical = resolve_district(district) or district
        rows = df[df["district"].str.lower() == canonical.lower()]
        if not rows.empty:
            col = f"{method}_efficiency_pct"
            if col in rows.columns:
                val = rows.iloc[0].get(col)
                if val and float(val) > 0:
                    return float(val)
    except Exception:
        pass
    # Defaults from Minor Irrigation Census
    return {"flood": 60.0, "sprinkler": 75.0, "drip": 90.0}.get(method, 60.0)
