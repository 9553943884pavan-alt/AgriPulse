"""ML.1 — Candidate crop filter (gates 1 and 2).

Gate 1: Crop is grown in the district (DES area above threshold in recent years,
        per season). Uses district_crop_yields.csv.
Gate 2: Crop is sowable today or opens within OPENS_SOON_DAYS days.
        Uses crop_calendar.csv + today's date.
Gate 3: Water feasibility — checked later by ml.water_need once ET0 is available;
        ML.1 does NOT exclude on water (see SPECS §3). Water-hungry crops are
        flagged and handed to the optimizer to handle via the drought-safe strategy.

Excluded crops carry exactly one reason code:
  NOT_GROWN_IN_DISTRICT  — gate 1 failed
  NOT_SOWABLE_NOW        — gate 2 failed (calendar window closed AND not opening soon)

Crop names come from crops_master.csv (mr/hi/en display names).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd

from app.ml.constants import (
    NON_AGRICULTURAL_DISTRICTS,
    OPENS_SOON_DAYS,
    SOWABLE_GRACE_DAYS,
)
from app.schemas import (
    Candidate,
    ExcludedCrop,
    FarmProfile,
    Location,
    Season,
    SourcedValue,
    WaterBudget,
)

logger = logging.getLogger(__name__)

# Minimum mean area (ha) in recent years for a crop to be "grown in district"
_AREA_THRESHOLD_HA = 100.0
# How many recent years to use for the area average
_RECENT_YEARS = 5


# ── Data helpers ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _yields() -> pd.DataFrame:
    from app.data.loaders import load_district_crop_yields
    return load_district_crop_yields()


@lru_cache(maxsize=1)
def _calendar() -> pd.DataFrame:
    from app.data.loaders import load_crop_calendar
    return load_crop_calendar()


@lru_cache(maxsize=1)
def _crops_master() -> pd.DataFrame:
    from app.data.loaders import load_crops_master
    return load_crops_master()


@lru_cache(maxsize=1)
def _water_coeff() -> pd.DataFrame:
    from app.data.loaders import load_crop_water_coefficients
    return load_crop_water_coefficients()


# ── Month-name → month-number parser ─────────────────────────────────────────

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _month_day_to_date(month_str: str, day: int, year: int) -> date:
    """Parse 'June 15' → date(year, 6, 15)."""
    parts = month_str.strip().split()
    month_num = _MONTH_MAP.get(parts[0].lower(), 1)
    day_num = int(parts[1]) if len(parts) > 1 else day
    try:
        return date(year, month_num, day_num)
    except ValueError:
        return date(year, month_num, 1)


def _sowing_window(row: pd.Series, ref_date: date) -> tuple[date, date]:
    """Return (sowing_start, sowing_end) dates anchored to ref_date's year.

    If the end month < start month, the window spans a year boundary
    (e.g. cotton Kharif: June–July with harvest in Jan) — keep same year.
    """
    y = ref_date.year
    start = _month_day_to_date(str(row["sowing_start"]), 1, y)
    end = _month_day_to_date(str(row["sowing_end"]), 28, y)
    # If end < start (calendar wraps), try next year for end
    if end < start:
        end = _month_day_to_date(str(row["sowing_end"]), 28, y + 1)
    return start, end


# ── Gate 1: grown in district ─────────────────────────────────────────────────

def _grown_in_district(district: str, season: str) -> set[str]:
    """Return crop_ids with mean area > threshold in recent years for this district+season.

    Uses DES `des_crop_name` → `crop_id` mapping from crops_master.
    """
    df = _yields()
    cm = _crops_master()

    # Build des_crop_name → crop_id map
    des_map = {
        str(r["des_crop_name"]).strip().lower(): str(r["crop_id"]).strip()
        for _, r in cm.iterrows()
        if pd.notna(r.get("des_crop_name")) and pd.notna(r.get("crop_id"))
    }

    # Filter to district + season, recent years
    max_year = int(df["year"].max())
    recent = df[
        (df["district"].str.strip() == district) &
        (df["year"] >= max_year - _RECENT_YEARS)
    ]

    # Handle combined seasons ("Kharif/Rabi" matches both)
    if season in ("Kharif", "Rabi", "Summer", "Whole Year"):
        season_mask = recent["season"].str.contains(season, case=False, na=False)
    else:
        season_mask = recent["season"] == season
    recent = recent[season_mask]

    mean_area = recent.groupby("crop")["area_ha"].mean()

    grown = set()
    for crop_name, area in mean_area.items():
        if area >= _AREA_THRESHOLD_HA:
            cid = des_map.get(str(crop_name).strip().lower())
            if cid:
                grown.add(cid)

    return grown


# ── Gate 2: sowable now ───────────────────────────────────────────────────────

def _sowable_crops(today: date) -> dict[str, dict]:
    """Return {crop_id: {"sowable": bool, "opens_on": date|None, "season": str}}
    for all calendar entries that are currently sowable or opening soon.
    """
    cal = _calendar()
    result: dict[str, dict] = {}

    for _, row in cal.iterrows():
        cid = str(row["crop_id"]).strip()
        season = str(row["season"]).strip()

        try:
            start, end = _sowing_window(row, today)
        except Exception:
            continue

        # Sowable: today within [start - GRACE, end]
        window_start = start - timedelta(days=SOWABLE_GRACE_DAYS)
        if window_start <= today <= end:
            result[cid] = {"sowable": True, "opens_on": None, "season": season}

        # Opening soon: start within next OPENS_SOON_DAYS days
        elif 0 < (start - today).days <= OPENS_SOON_DAYS:
            result[cid] = {"sowable": True, "opens_on": start, "season": season}

    return result


# ── Water need placeholder (m3/acre) ─────────────────────────────────────────

def _rough_water_need(crop_id: str, season: str) -> float | None:
    """Rough water need in m3/acre from water coefficients."""
    wc = _water_coeff()
    rows = wc[(wc["crop_id"] == crop_id) & (wc["season"] == season)]
    if rows.empty:
        rows = wc[wc["crop_id"] == crop_id]
    if rows.empty:
        return None
    row = rows.iloc[0]
    et0_assumed = 5.0
    kc_mid = float(row.get("kc_mid", 1.0) or 1.0)
    duration = float(row.get("total_duration_days", 120) or 120)
    if not (kc_mid > 0 and duration > 0):
        return 1500.0  # safe default
    need_mm = kc_mid * et0_assumed * duration
    result = need_mm * 4.047
    # Guard against NaN/Inf from bad CSV values
    import math
    return result if math.isfinite(result) and result > 0 else 1500.0


def _sv_water(value: float, unit: str = "m3_per_acre") -> SourcedValue:
    from datetime import date as _date
    return SourcedValue(
        value=round(value, 0),
        unit=unit,
        source="FAO-56 Kc × 5 mm/day ET₀ assumption",
        as_of=str(_date.today()),
        status="assumption",
    )


# ── Public API ────────────────────────────────────────────────────────────────

def candidate_crops(
    profile: FarmProfile,
    location: Location,
    season: Season,
    water: list[WaterBudget],
    today: date | None = None,
) -> tuple[list[Candidate], list[ExcludedCrop]]:
    """ML.1 — Two-gate filter returning (candidates, excluded_crops).

    Gate 1: Crop grown in district (DES area threshold).
    Gate 2: Crop sowable today or opening within 21 days.

    Water (gate 3) is NOT applied here — the optimizer handles water via
    strategy constraints. The Candidate includes a rough water need so the
    optimizer inputs can be populated even before ML.7 runs.

    After ML.7 is implemented, the pipeline replaces water_need_m3_per_acre
    with the per-scenario values from crop_water_need().
    """
    if today is None:
        today = date.today()

    district = location.district
    season_name = season.name

    if district in NON_AGRICULTURAL_DISTRICTS:
        logger.warning("candidate_crops called for non-agricultural district: %s", district)
        return [], []

    # Gate 1
    grown = _grown_in_district(district, season_name)
    logger.debug("Gate 1: %d crops grown in %s %s", len(grown), district, season_name)

    # Gate 2
    sowable = _sowable_crops(today)
    logger.debug("Gate 2: %d crops sowable on %s", len(sowable), today)

    # Crop names map
    cm = _crops_master()
    names_map: dict[str, dict[str, str]] = {}
    for _, row in cm.iterrows():
        cid = str(row["crop_id"]).strip()
        names_map[cid] = {
            "en": str(row.get("display_name_en", cid)),
            "mr": str(row.get("display_name_mr", cid)),
            "hi": str(row.get("display_name_hi", cid)),
        }

    candidates: list[Candidate] = []
    excluded: list[ExcludedCrop] = []

    # All crops that appear in either gate
    all_crop_ids = grown | set(sowable.keys())

    for cid in sorted(all_crop_ids):
        sw = sowable.get(cid)

        # Gate 1 check
        if cid not in grown:
            excluded.append(ExcludedCrop(
                crop_id=cid,
                reason_code="NOT_GROWN_IN_DISTRICT",
                params={"district": district, "season": season_name},
            ))
            continue

        # Gate 2 check
        if sw is None:
            excluded.append(ExcludedCrop(
                crop_id=cid,
                reason_code="NOT_SOWABLE_NOW",
                params={"district": district, "today": str(today)},
            ))
            continue

        # Passes both gates — build Candidate
        rough_water = _rough_water_need(cid, sw["season"])
        water_sv = _sv_water(rough_water if rough_water is not None else 1500.0)

        candidates.append(Candidate(
            crop_id=cid,
            names=names_map.get(cid, {"en": cid, "mr": cid, "hi": cid}),
            season=sw["season"],
            water_need_m3_per_acre=water_sv,
            opens_on=str(sw["opens_on"]) if sw.get("opens_on") else None,
        ))

    logger.info(
        "candidate_crops(%s, %s, %s): %d candidates, %d excluded",
        district, season_name, today, len(candidates), len(excluded),
    )
    return candidates, excluded
