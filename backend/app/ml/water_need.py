"""ML.7 — Crop water need per crop, stage and scenario.

Formula (FAO-56):
    need_mm = Σ_stages max(0,  Kc_stage × ET₀_stage  −  effective_rain_stage)
    need_m3_per_acre = need_mm × 4.047 / irrigation_efficiency

This is a *net irrigation requirement*: effective rainfall has already been
subtracted.  Optimizers must compare it only to deliverable irrigation supply
(groundwater + canal), never to a total that adds rainfall again.

Stages: ini / dev / mid / late  (lengths from crop_water_coefficients.csv)
Kc:     kc_ini / (linear ramp) / kc_mid / kc_end

ET₀:
  - When a Scenario is given, its et0_mm field is used (from the Open-Meteo
    ERA5 archive for that analogue year). If et0_mm is None (weather data not
    yet available), falls back to the Maharashtra seasonal default (5 mm/day).
  - When ET₀ is per-season total rather than per-day, it is divided by the
    crop duration to get daily ET₀.

Effective rain:
  - From Scenario.rainfall_mm × EFFECTIVE_RAIN_FACTOR distributed uniformly
    across the crop duration. Falls back to Maharashtra average when missing.

Irrigation efficiency: from profile.irrigation_method or district average.

The result is returned as WaterNeed with one SourcedValue per scenario.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import pandas as pd

from app.ml.constants import EFFECTIVE_RAIN_FACTOR, SEASON_WINDOW_DAYS
from app.schemas import Scenario, Season, SourcedValue, WaterNeed

logger = logging.getLogger(__name__)

# ── Maharashtra climate defaults (used when weather data not yet available) ───
# Source: IMD normal season values for Maharashtra
_ET0_DEFAULT_MM_PER_DAY = 5.0        # assumption; cited in SOURCES.md after demo
_RAIN_DEFAULT_MM: dict[str, float] = {
    "Kharif":     750.0,   # mm seasonal; assumption
    "Rabi":       80.0,
    "Summer":     20.0,
    "Whole Year": 850.0,
}

# Irrigation efficiency by method (0–1); from FAO-56 and Minor Irrigation Census
_EFFICIENCY: dict[str, float] = {
    "flood": 0.60,
    "sprinkler": 0.75,
    "drip": 0.90,
}
_EFFICIENCY_DEFAULT = 0.60  # flood irrigation district average


# ── Data loader ───────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _coeff() -> pd.DataFrame:
    from app.data.loaders import load_crop_water_coefficients
    return load_crop_water_coefficients()


def _coefficient_crop_id(crop_id: str) -> str:
    """Normalize calendar-only seasonal IDs to a sourced coefficient ID.

    This resolves names such as ``maize_rabi`` to the coefficient table's
    ``maize`` row. Unknown identifiers stay unknown: callers exclude them
    rather than receiving an invented water requirement.
    """
    value = crop_id.strip().casefold()
    df = _coeff()
    source_ids = df["crop_id"].astype(str).str.casefold()
    for suffix in ("_kharif", "_rabi", "_summer"):
        if value.endswith(suffix):
            base = value[: -len(suffix)]
            if (source_ids == base).any():
                return base
    return value


def _coefficient_row(crop_id: str, season_name: str) -> pd.Series | None:
    """Find a sourced crop coefficient, including slash-separated seasons."""
    df = _coeff()
    canonical_id = _coefficient_crop_id(crop_id)
    rows = df[df["crop_id"].astype(str).str.casefold() == canonical_id]
    if rows.empty:
        return None

    exact = rows[rows["season"].astype(str).str.casefold() == season_name.casefold()]
    if not exact.empty:
        return exact.iloc[0]

    matching_season = rows[
        rows["season"].astype(str).map(
            lambda value: season_name.casefold()
            in {part.strip().casefold() for part in value.split("/")}
        )
    ]
    if not matching_season.empty:
        return matching_season.iloc[0]

    # The crop-specific coefficient remains sourced even when its source
    # season differs from the calendar record; no numerical default is used.
    return rows.iloc[0]


# ── ET₀ extraction ────────────────────────────────────────────────────────────

def _window_days(season_name: str, duration_days: float) -> float:
    """Length of the weather window the scenario totals were summed over."""
    return float(SEASON_WINDOW_DAYS.get(season_name, duration_days))


def _et0_daily(scenario: Scenario | None, season_name: str, duration_days: float) -> float:
    """Return ET₀ in mm/day (season-window total / days in that window).

    The scenario total covers the whole season window (e.g. Rabi = Nov 1-Mar 31, 151 days),
    not the crop's own duration, so dividing by the crop duration overstated daily ET₀.
    """
    if scenario is not None and scenario.et0_mm is not None:
        return float(scenario.et0_mm) / max(_window_days(season_name, duration_days), 1)
    return _ET0_DEFAULT_MM_PER_DAY


def _rain_mm(scenario: Scenario | None, season_name: str) -> float:
    """Return seasonal rainfall in mm."""
    if scenario is not None and scenario.rainfall_mm is not None:
        return float(scenario.rainfall_mm)
    return _RAIN_DEFAULT_MM.get(season_name, 500.0)


# ── Kc interpolation ─────────────────────────────────────────────────────────

def _kc_for_stage(row: pd.Series, stage: str) -> float:
    """Return Kc for ini/dev/mid/late stage (dev is linearly interpolated)."""
    if stage == "ini":
        return float(row["kc_ini"])
    if stage == "mid":
        return float(row["kc_mid"])
    if stage == "late":
        return float(row["kc_end"])
    # dev: linear ramp from kc_ini to kc_mid
    return (float(row["kc_ini"]) + float(row["kc_mid"])) / 2.0


# ── Per-stage need ────────────────────────────────────────────────────────────

def _stage_need_mm(
    row: pd.Series,
    et0_daily: float,
    rain_total_mm: float,
    window_days: float | None = None,
) -> float:
    """Compute total crop water need (mm) for one crop using 4-stage FAO-56.

    ETc = Kc × ET0 summed across all stage days.
    Effective rain distributed uniformly across total duration.
    need = max(0, ETc - effective_rain)
    """
    total_days = float(row.get("total_duration_days") or 120)
    # Rain fell over the whole season window, not only during the crop's own days.
    eff_rain_per_day = rain_total_mm * EFFECTIVE_RAIN_FACTOR / max(window_days or total_days, 1)

    stage_need = 0.0
    for stage, days_col in [
        ("ini",  "stage_ini_days"),
        ("dev",  "stage_dev_days"),
        ("mid",  "stage_mid_days"),
        ("late", "stage_late_days"),
    ]:
        days = float(row.get(days_col) or 0)
        if days <= 0:
            continue
        kc = _kc_for_stage(row, stage)
        etc_mm = kc * et0_daily * days
        eff_rain_mm = eff_rain_per_day * days
        stage_need += max(0.0, etc_mm - eff_rain_mm)

    return stage_need


def _sv(value: float, source: str, status: str) -> SourcedValue:
    from datetime import date
    return SourcedValue(
        value=round(value, 0),
        unit="m3_per_acre",
        source=source,
        as_of=str(date.today()),
        status=status,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def crop_water_need(
    crop_id: str,
    season: Season,
    scenarios: list[Scenario],
    efficiency: float | None = None,
) -> WaterNeed:
    """ML.7 — Return WaterNeed with drought/normal/excess in m3/acre.

    Args:
        crop_id:    Canonical crop id from crops_master.
        season:     Season object (name used for rain defaults).
        scenarios:  List of Scenario objects [drought, normal, excess].
                    Scenario.et0_mm and Scenario.rainfall_mm are used when set.
        efficiency: Irrigation efficiency (0-1). None → district default (flood).

    Returns:
        WaterNeed with one SourcedValue per scenario.
    """
    eff = efficiency if efficiency is not None else _EFFICIENCY_DEFAULT
    season_name = season.name

    resolved = _coefficient_row(crop_id, season_name)
    if resolved is None:
        logger.info("crop_water_need: no sourced Kc data for %s %s", crop_id, season_name)
        raise ValueError(f"No sourced crop water coefficient for {crop_id} ({season_name})")
    # Feed the existing exact-match selection the normalized sourced row. This
    # makes an unknown crop impossible to turn into a default numerical need.
    df = pd.DataFrame([resolved]).copy()
    df["crop_id"] = crop_id
    df["season"] = season_name
    # Match by crop_id and season; fall back to crop_id only
    row_df = df[(df["crop_id"] == crop_id) & (df["season"] == season_name)]
    if row_df.empty:
        row_df = df[df["crop_id"] == crop_id]

    if row_df.empty:
        logger.warning("crop_water_need: no Kc data for %s %s — using defaults", crop_id, season_name)
        # Return a reasonable assumption
        default_m3 = 1500.0
        sv = _sv(default_m3 / eff, f"assumption (no Kc data for {crop_id})", "assumption")
        return WaterNeed(drought=sv, normal=sv, excess=sv)

    row = row_df.iloc[0]
    duration = float(row.get("total_duration_days") or 120)

    # Build a lookup by scenario id
    scen_map: dict[str, Scenario] = {s.id: s for s in scenarios}
    drought_s = scen_map.get("drought")
    normal_s  = scen_map.get("normal")
    excess_s  = scen_map.get("excess")

    results: dict[str, SourcedValue] = {}
    for sid, scen in [("drought", drought_s), ("normal", normal_s), ("excess", excess_s)]:
        et0 = _et0_daily(scen, season_name, duration)
        rain = _rain_mm(scen, season_name)
        need_mm = _stage_need_mm(row, et0, rain, _window_days(season_name, duration))
        need_m3 = need_mm * 4.047 / eff

        stage_cols = ("stage_ini_days", "stage_dev_days", "stage_mid_days", "stage_late_days")
        if any(pd.isna(row.get(col)) for col in stage_cols):
            # FAO-56 lists no stage lengths for this crop, so no irrigation need
            # can be computed. 0 m³ is an assumption (residual soil moisture), not a result.
            source = f"No FAO-56 stage lengths for {crop_id}: irrigation need not estimated (assumes residual soil moisture)"
            status = "assumption"
        elif scen is not None and (scen.et0_mm or scen.rainfall_mm):
            source = f"FAO-56 Kc × ERA5 ET₀ (analogue year {scen.analogue_year})"
            status = "computed"
        else:
            source = f"FAO-56 Kc × {_ET0_DEFAULT_MM_PER_DAY} mm/day ET₀ assumption"
            status = "assumption"

        results[sid] = _sv(need_m3, source, status)

    return WaterNeed(
        drought=results["drought"],
        normal=results["normal"],
        excess=results["excess"],
    )


def efficiency_for_profile(irrigation_method: str | None) -> float:
    """Return irrigation efficiency (0-1) from profile irrigation method."""
    if irrigation_method is None:
        return _EFFICIENCY_DEFAULT
    return _EFFICIENCY.get(irrigation_method, _EFFICIENCY_DEFAULT)
