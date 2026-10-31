"""SVC.8 — District context service for E9 (districts list) and E10 (district detail).

Provides groundwater category, reservoir storage %, recent rain departure,
and irrigation shares per district.
"""

from __future__ import annotations

import logging

from app.data.loaders import (
    load_districts,
    load_groundwater,
    load_irrigation,
    load_recent_rainfall,
    load_reservoir_storage,
)
from app.data.resolver import resolve_district
from app.schemas import SourcedValue

logger = logging.getLogger(__name__)

_GW_SOURCE = "CGWB block-level groundwater assessment (district average)"
_RESERVOIR_SOURCE = "CWC weekly bulletin (rsms.cwc.gov.in)"
_RAIN_SOURCE = "India Meteorological Department / Open-Meteo"
_IRR_SOURCE = "Minor Irrigation Census (MoJS 2017-18)"

_GW_STATUS_COLOR = {
    "safe": "green",
    "semi-critical": "amber",
    "critical": "orange",
    "over-exploited": "red",
}


def get_all_districts() -> list[dict]:
    """E9 — Return all 36 districts with coordinates, groundwater color, is_agricultural."""
    df = load_districts()
    gw_df = load_groundwater()
    result = []
    for _, row in df.iterrows():
        district = row["district"]
        category, _ = _district_gw_category(district, gw_df)
        color = _GW_STATUS_COLOR.get(category.lower(), "grey")
        result.append({
            "district": district,
            "names": {
                "en": district,
                "mr": row.get("name_mr", district),
                "hi": row.get("name_hi", district),
            },
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "groundwater_category": category,
            "status_color": color,
            "is_agricultural_district": bool(row.get("is_agricultural_district", True)),
        })
    return result


def get_district_context(district: str) -> dict:
    """E10 — Return groundwater, reservoirs, recent rain, irrigation for a district."""
    canonical = resolve_district(district) or district
    gw_df = load_groundwater()
    irr_df = load_irrigation()
    rain_df = load_recent_rainfall()
    res_df = load_reservoir_storage()

    category, extraction_pct = _district_gw_category(canonical, gw_df)
    depth = _district_gw_depth(canonical, gw_df)
    reservoirs = _district_reservoirs(canonical, res_df)
    rain = _district_rain(canonical, rain_df)
    irrigation = _district_irrigation(canonical, irr_df)

    def sv(val, unit, source, as_of, status="official_dataset") -> SourcedValue:
        return SourcedValue(value=val, unit=unit, source=source, source_url="", as_of=as_of, status=status)

    return {
        "district": canonical,
        "groundwater": {
            "category": sv(category, "category", _GW_SOURCE, "2022"),
            "extraction_pct": sv(extraction_pct, "pct", _GW_SOURCE, "2022"),
            "depth_post_monsoon_m": sv(depth, "m", _GW_SOURCE, "2022"),
        },
        "reservoirs": reservoirs,
        "recent_rain": rain,
        "irrigation": irrigation,
    }


def _district_gw_category(district: str, gw_df) -> tuple[str, float]:
    rows = gw_df[gw_df["district"].str.lower() == district.lower()]
    avg_rows = rows[rows["block"].str.contains("District Avg", case=False, na=False)]
    if avg_rows.empty:
        avg_rows = rows
    if avg_rows.empty:
        return "Semi-critical", 70.0
    r = avg_rows.iloc[0]
    category = str(r.get("category", "Semi-critical"))
    extraction = float(r.get("extraction_pct", 70.0) or 70.0)
    return category, extraction


def _district_gw_depth(district: str, gw_df) -> float:
    rows = gw_df[gw_df["district"].str.lower() == district.lower()]
    avg_rows = rows[rows["block"].str.contains("District Avg", case=False, na=False)]
    if avg_rows.empty:
        avg_rows = rows
    if avg_rows.empty:
        return 0.0
    r = avg_rows.iloc[0]
    return float(r.get("depth_post_monsoon_m", r.get("depth_m", 0)) or 0)


def _district_reservoirs(district: str, res_df) -> list[dict]:
    # districts_served is pipe-separated, e.g. "Pune|Satara|Solapur"
    mask = res_df["districts_served"].str.contains(district, case=False, na=False)
    rows = res_df[mask]
    result = []
    for _, r in rows.iterrows():
        pct = float(r.get("live_storage_pct_of_capacity", 0) or 0)
        obs = str(r.get("observation_date", "current"))
        result.append({
            "name": str(r.get("reservoir", "Unknown")),
            "live_storage_pct": SourcedValue(
                value=pct, unit="pct", source=_RESERVOIR_SOURCE,
                source_url="https://rsms.cwc.gov.in", as_of=obs, status="official_dataset",
            ),
        })
    return result


def _district_rain(district: str, rain_df) -> dict:
    rows = rain_df[rain_df["district"].str.lower() == district.lower()]
    if rows.empty:
        return {
            "last_90d_mm": None,
            "departure_90d_pct": None,
            "category": "Normal",
        }
    r = rows.iloc[0]
    as_of = str(r.get("as_of", r.get("date", "current")))
    rain_90 = float(r.get("rainfall_90d_mm", r.get("rain_90d", 0)) or 0)
    dep_90 = float(r.get("departure_90d_pct", r.get("departure_pct", 0)) or 0)
    if dep_90 < -19:
        category = "Deficient"
    elif dep_90 < -10:
        category = "Below Normal"
    elif dep_90 > 19:
        category = "Excess"
    elif dep_90 > 10:
        category = "Above Normal"
    else:
        category = "Normal"
    return {
        "last_90d_mm": SourcedValue(value=rain_90, unit="mm", source=_RAIN_SOURCE,
                                    source_url="", as_of=as_of, status="official_dataset"),
        "departure_90d_pct": SourcedValue(value=dep_90, unit="pct", source=_RAIN_SOURCE,
                                           source_url="", as_of=as_of, status="computed"),
        "category": category,
    }


def _district_irrigation(district: str, irr_df) -> dict:
    rows = irr_df[irr_df["district"].str.lower() == district.lower()]
    if rows.empty:
        return {"borewell_share_pct": None, "canal_share_pct": None, "drip_adoption_pct": None}
    r = rows.iloc[0]
    as_of = "2017-18"
    def sv(col, aliases=[]) -> SourcedValue | None:
        for c in [col] + aliases:
            if c in r.index:
                try:
                    return SourcedValue(value=float(r[c] or 0), unit="pct",
                                        source=_IRR_SOURCE, source_url="", as_of=as_of, status="official_dataset")
                except (ValueError, TypeError):
                    pass
        return None
    return {
        "borewell_share_pct": sv("borewell_tubewell_share_pct", ["borewell_share_pct"]),
        "canal_share_pct": sv("canal_surface_flow_share_pct", ["canal_share_pct"]),
        "drip_adoption_pct": sv("micro_irrigation_adoption_pct", ["drip_adoption_pct"]),
    }
