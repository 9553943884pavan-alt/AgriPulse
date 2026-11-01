"""E11 GET /api/sources
E12 GET /api/sources/health
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.http_client import fetch
from app.services.source_registry import SOURCES

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

# Use the reconciled registry above the legacy list retained here for historical
# context.  This endpoint must only return sources that the application consumes.
_SOURCES = SOURCES

# Simple in-process cache for health checks (60 s)
_health_cache: dict = {}
_health_cache_time: float = 0.0
_HEALTH_TTL = 60.0

# ids MUST match the ids in _SOURCES above (the Sources page joins on id).
_HEALTH_CHECKS = [
    {"id": "open_meteo_forecast", "name": "Open-Meteo Forecast", "url": "https://api.open-meteo.com/v1/forecast?latitude=18.99&longitude=75.91&current=temperature_2m"},
    {"id": "open_meteo_archive", "name": "Open-Meteo ERA5 Archive", "url": "https://archive-api.open-meteo.com/v1/archive?latitude=18.99&longitude=75.91&start_date=2024-01-01&end_date=2024-01-02&daily=precipitation_sum"},
    {"id": "agmarknet", "name": "Agmarknet (data.gov.in)", "url": "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070", "needs_key": "DATA_GOV_IN_API_KEY"},
    {"id": "open_meteo_geocoding", "name": "Open-Meteo geocoding", "url": "https://geocoding-api.open-meteo.com/v1/search?name=Pune&count=1"},
    {"id": "soilgrids", "name": "SoilGrids", "url": "https://rest.isric.org/soilgrids/v2.0/properties/query?lon=75.91&lat=18.99&property=phh2o&depth=0-5cm&value=mean"},
    {"id": "cwc", "name": "CWC", "url": "https://rsms.cwc.gov.in"},
]
_SLOW_MS = 3000
_HEALTH_TIMEOUT = 8.0


def _runtime_status(source: dict) -> tuple[str, str]:
    """Honest per-source status: (status, evidence).

    status is one of live | cached | historical | official_dataset | unavailable.
    ``mode`` in the registry says how the app *intends* to use a source; this says
    what is true right now, from configuration and the last health probe.
    """
    from app.config import settings

    mode = source.get("mode")
    sid = source["id"]
    if mode == "historical":
        return "historical", f"Local processed dataset ({source.get('as_of', '')}); not fetched at run time."
    if mode == "static":
        return "official_dataset", f"Local official dataset ({source.get('as_of', '')}); not refreshed at run time."
    if sid == "sarvam":
        if not settings.SARVAM_API_KEY:
            return "unavailable", "SARVAM_API_KEY is not set; the assistant falls back to templates and browser speech."
        return "live", "API key configured. Not probed (calls are billable); failures fall back to templates."
    if sid == "agmarknet" and not settings.DATA_GOV_IN_API_KEY:
        return "cached", "DATA_GOV_IN_API_KEY is not set; prices come from local history / dated cache."
    probe = next((p for p in _health_cache.get("sources", []) if p["id"] == sid), None)
    if probe is None:
        return "cached", "No health probe has completed yet (call /api/sources/health); each value is still labelled live only when a request succeeds."
    if probe["status"] in ("green", "amber"):
        return "live", f"Last probe OK ({probe['latency_ms']} ms) at {probe['last_ok']}."
    return "cached", f"Last probe failed ({probe['note']}); cached or local fallback data is used."


@router.get("/sources")
async def list_sources() -> dict:
    """E11 — All datasets and APIs with name, publisher, licence, date, type (F12).

    ``mode`` is the registry's intended use; ``status``/``status_evidence`` are the
    truthful runtime classification (live / cached / historical / official_dataset /
    unavailable), derived from configuration and the most recent health probe.
    """
    out = []
    for source in _SOURCES:
        status, evidence = _runtime_status(source)
        out.append({**source, "status": status, "status_evidence": evidence})
    return {"sources": out}


@router.get("/sources/health")
async def sources_health() -> dict:
    """E12 — Live health status of each external API, cached for 60 s (F12)."""
    global _health_cache, _health_cache_time
    now = time.time()
    if now - _health_cache_time < _HEALTH_TTL and _health_cache:
        return _health_cache

    import asyncio

    import httpx

    from app.config import settings

    def _red(source: dict, note: str) -> dict:
        return {"id": source["id"], "name": source["name"], "status": "red", "latency_ms": -1, "last_ok": "", "note": note}

    async def _check(source: dict) -> dict:
        params = None
        if source.get("needs_key"):
            key = getattr(settings, source["needs_key"], "")
            if not key:
                return _red(source, f"{source['needs_key']} is not set")
            # The key is sent as a query param but never logged or returned.
            params = {"api-key": key, "format": "json", "limit": 1}
        start = time.perf_counter()
        try:
            await fetch(source["url"], params=params, timeout=httpx.Timeout(_HEALTH_TIMEOUT), retries=0)
            latency = int((time.perf_counter() - start) * 1000)
            note = "slow response" if latency > _SLOW_MS else ""
            if source["id"] == "cwc":
                # The probe only proves the CWC website answers; the app reads a local snapshot.
                note = (note + "; " if note else "") + "website reachable; app uses a local bulletin snapshot, not a live feed"
            return {
                "id": source["id"], "name": source["name"],
                "status": "amber" if latency > _SLOW_MS else "green",
                "latency_ms": latency,
                "last_ok": datetime.now(tz=timezone.utc).isoformat(),
                "note": note,
            }
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in (401, 403):
                return _red(source, f"HTTP {code}: API key rejected")
            return _red(source, f"HTTP {code}: provider is down or overloaded; cached data is used")
        except httpx.TimeoutException:
            return _red(source, "timed out; cached data is used")
        except Exception as exc:
            return _red(source, f"unreachable ({type(exc).__name__}); cached data is used")

    results = await asyncio.gather(*[_check(s) for s in _HEALTH_CHECKS])

    response = {
        "checked_at": datetime.now(tz=timezone.utc).isoformat(),
        "sources": list(results),
    }
    _health_cache = response
    _health_cache_time = now
    return response
