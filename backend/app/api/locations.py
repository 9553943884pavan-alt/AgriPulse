"""E7  POST /api/prefetch
E8  GET  /api/locations/search
E9  GET  /api/districts
E10 GET  /api/districts/{district}/context
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.core.errors import AppError
from app.data.resolver import is_agricultural, resolve_district
from app.services import location as loc_svc
from app.services import weather as wx_svc
from app.services.district_context import get_all_districts, get_district_context

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/prefetch")
async def prefetch(body: dict) -> dict:
    """E7 — Warm caches for a location while the farmer is still talking (F16).
    Failure here NEVER blocks a plan.
    """
    location_text = body.get("location_text", "")
    stages: dict[str, str] = {}
    district = None
    try:
        loc = await loc_svc.locate(location_text)
        district = loc.district
        stages["geocoding"] = "ready"
        # Warm weather cache
        try:
            await wx_svc.get_weather(loc)
            stages["weather"] = "ready"
        except Exception:
            stages["weather"] = "failed"
    except Exception:
        stages["geocoding"] = "failed"
    return {"status": "warmed", "district": district, "stages": stages}


@router.get("/locations/search")
async def search_locations(
    q: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=10),
) -> dict:
    """E8 — Place autocomplete → district suggestions (F17)."""
    results = await loc_svc.search_locations(q, limit)
    return {"results": [r.model_dump() for r in results]}


@router.get("/districts")
async def list_districts() -> dict:
    """E9 — All 36 districts with coordinates, groundwater color, is_agricultural (F11 map)."""
    return {"districts": get_all_districts()}


@router.get("/districts/{district}/context")
async def district_context(district: str) -> dict:
    """E10 — Groundwater, reservoirs, recent rain, irrigation for a district (F11 popup)."""
    canonical = resolve_district(district)
    if not canonical:
        raise AppError("LOCATION_NOT_FOUND", {"district": district})
    if not is_agricultural(canonical):
        raise AppError("DISTRICT_NOT_AGRICULTURAL", {"district": canonical})
    return get_district_context(canonical)
