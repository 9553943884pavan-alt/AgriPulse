"""E11 GET /api/sources
E12 GET /api/sources/health
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.http_client import fetch

router = APIRouter()

_SOURCES = [
    {"id": "agmarknet", "name": "Agmarknet (data.gov.in)", "publisher": "Directorate of Marketing and Inspection", "url": "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070", "license": "Government Open Data License - India", "verified_on": "2026-10-31", "type": "live_api", "used_for": "Mandi prices per crop/district"},
    {"id": "open_meteo_forecast", "name": "Open-Meteo Forecast", "publisher": "Open-Meteo", "url": "https://api.open-meteo.com", "license": "CC BY 4.0", "verified_on": "2026-10-31", "type": "live_api", "used_for": "16-day weather forecast + recent rain"},
    {"id": "open_meteo_archive", "name": "Open-Meteo ERA5 Archive", "publisher": "Open-Meteo / ECMWF", "url": "https://archive-api.open-meteo.com", "license": "CC BY 4.0", "verified_on": "2026-10-31", "type": "live_api", "used_for": "Historical weather 1997-2025 (climate scenarios)"},
    {"id": "soilgrids", "name": "SoilGrids v2", "publisher": "ISRIC — World Soil Information", "url": "https://rest.isric.org/soilgrids/v2.0", "license": "CC BY 4.0", "verified_on": "2026-10-31", "type": "live_api", "used_for": "Soil pH, organic carbon (optional, supplements CSV)"},
    {"id": "des_yields", "name": "DES District Crop Statistics", "publisher": "Directorate of Economics and Statistics, Maharashtra", "url": "https://mahadbt.maharashtra.gov.in", "license": "Government Open Data", "verified_on": "2026-10-31", "type": "official_dataset", "used_for": "District crop area, production, yield 1997-2014"},
    {"id": "des_costs", "name": "CACP Cost of Cultivation", "publisher": "Commission for Agricultural Costs and Prices", "url": "https://cacp.dacnet.nic.in", "license": "Government Open Data", "verified_on": "2026-10-31", "type": "official_dataset", "used_for": "Itemized cost per crop (reference year 2022-23)"},
    {"id": "cgwb", "name": "CGWB Block Groundwater Assessment", "publisher": "Central Ground Water Board", "url": "https://cgwb.gov.in", "license": "Government Open Data", "verified_on": "2026-10-31", "type": "official_dataset", "used_for": "Groundwater category and extraction % per block"},
    {"id": "cwc", "name": "CWC Weekly Reservoir Bulletin", "publisher": "Central Water Commission", "url": "https://rsms.cwc.gov.in", "license": "Government Open Data", "verified_on": "2026-10-31", "type": "official_dataset", "used_for": "Reservoir live storage % (updated weekly)"},
    {"id": "icar_soil", "name": "Soil Health Card Survey (ICAR)", "publisher": "ICAR / State Agriculture Departments", "url": "https://soilhealth.dac.gov.in", "license": "Government Open Data", "verified_on": "2026-10-31", "type": "official_dataset", "used_for": "District-level N, P, K, pH"},
    {"id": "msp", "name": "CACP MSP / FRP", "publisher": "Commission for Agricultural Costs and Prices", "url": "https://cacp.dacnet.nic.in", "license": "Government Open Data", "verified_on": "2026-10-31", "type": "official_dataset", "used_for": "Minimum Support Price and sugarcane FRP"},
    {"id": "sarvam", "name": "Sarvam AI", "publisher": "Sarvam AI", "url": "https://api.sarvam.ai", "license": "Commercial", "verified_on": "2026-10-31", "type": "live_api", "used_for": "Agent reasoning, speech-to-text, text-to-speech"},
]

# Simple in-process cache for health checks (60 s)
_health_cache: dict = {}
_health_cache_time: float = 0.0
_HEALTH_TTL = 60.0

_HEALTH_CHECKS = [
    {"id": "open_meteo", "name": "Open-Meteo Forecast", "url": "https://api.open-meteo.com/v1/forecast?latitude=18.99&longitude=75.91&current=temperature_2m"},
    {"id": "agmarknet", "name": "Agmarknet (data.gov.in)", "url": "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070?format=json&limit=1"},
    {"id": "soilgrids", "name": "SoilGrids", "url": "https://rest.isric.org/soilgrids/v2.0/properties/query?lon=75.91&lat=18.99&property=phh2o&depth=0-30cm&value=mean"},
    {"id": "cwc", "name": "CWC", "url": "https://rsms.cwc.gov.in"},
]


@router.get("/sources")
async def list_sources() -> dict:
    """E11 — All datasets and APIs with name, publisher, licence, date, type (F12)."""
    return {"sources": _SOURCES}


@router.get("/sources/health")
async def sources_health() -> dict:
    """E12 — Live health status of each external API, cached for 60 s (F12)."""
    global _health_cache, _health_cache_time
    now = time.time()
    if now - _health_cache_time < _HEALTH_TTL and _health_cache:
        return _health_cache

    import asyncio
    import httpx
    results = []
    async def _check(source: dict) -> dict:
        start = time.perf_counter()
        try:
            resp = await fetch(source["url"], timeout=httpx.Timeout(5.0), retries=0)  # noqa: F841
            latency = int((time.perf_counter() - start) * 1000)
            return {"id": source["id"], "name": source["name"], "status": "green", "latency_ms": latency, "last_ok": datetime.now(tz=timezone.utc).isoformat(), "note": ""}
        except Exception:
            return {"id": source["id"], "name": source["name"], "status": "red", "latency_ms": -1, "last_ok": "", "note": "unavailable"}

    tasks = [_check(s) for s in _HEALTH_CHECKS]
    results = await asyncio.gather(*tasks)

    response = {
        "checked_at": datetime.now(tz=timezone.utc).isoformat(),
        "sources": list(results),
    }
    _health_cache = response
    _health_cache_time = now
    return response
