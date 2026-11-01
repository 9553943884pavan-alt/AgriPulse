"""SVC.2 — Location service.

place text → lat/lon + canonical district (Open-Meteo geocoding → districts.csv).

Fallback chain (SPECS §4.2):
  1. Open-Meteo geocoding API (free, no key)
  2. Cached result from a previous call
  3. Ask the farmer for the district name
"""

from __future__ import annotations

import logging

import httpx

from app.core.cache import TTL_GEOCODING, get_cache
from app.core.errors import AppError
from app.core.http_client import fetch
from app.data.resolver import resolve_district
from app.schemas import Location

logger = logging.getLogger(__name__)

_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_GEOCODING_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=2.0)


_GEOCODING_GET_URL = "https://geocoding-api.open-meteo.com/v1/get"


_DEVANAGARI_ALIASES = {
    "नासिक": "नाशिक",
    "कोल्हापुर": "कोल्हापूर",
    "सोलापुर": "सोलापूर",
}


async def _geocode(text: str, count: int) -> list[dict]:
    """Open-Meteo geocoding results with ENGLISH names.

    The English index returns nothing for Devanagari input (Marathi/Hindi farmers
    type 'नाशिक'), and the district resolver only knows Latin spellings. So for
    non-ASCII text: search in Marathi, then re-read each hit by id in English.
    """
    ascii_text = text.isascii()
    # Common Hindi spellings that the geocoder indexes under the Marathi spelling.
    text = _DEVANAGARI_ALIASES.get(text.strip(), text)
    resp = await fetch(
        _GEOCODING_URL,
        params={"name": text, "count": count, "language": "en" if ascii_text else "mr", "countryCode": "IN"},
        timeout=_GEOCODING_TIMEOUT,
        retries=1,
    )
    results = resp.json().get("results", []) or []
    if ascii_text:
        return results
    english: list[dict] = []
    for hit in [r for r in results if r.get("country_code") == "IN"][:3]:
        try:
            got = await fetch(
                _GEOCODING_GET_URL,
                params={"id": hit["id"], "language": "en"},
                timeout=_GEOCODING_TIMEOUT,
                retries=1,
            )
            english.append(got.json())
        except Exception as exc:
            logger.warning("Geocoding id lookup failed for %s: %s", hit.get("id"), exc)
    return english


async def locate(location_text: str) -> Location:
    """Resolve free-text place to a canonical Location.

    Raises AppError("LOCATION_NOT_FOUND") if geocoding fails and no cache exists.
    Raises AppError("DISTRICT_NOT_AGRICULTURAL") for Mumbai City / Suburban.
    """
    cache = await get_cache()
    cache_key = f"geocoding:{location_text.strip().lower()}"

    # ── Try live geocoding ────────────────────────────────────────────────────
    try:
        results = await _geocode(location_text, 5)
        location = _pick_maharashtra(results, location_text)
        if location:
            payload = location.model_dump(mode="json")
            await cache.set_upstream(cache_key, payload, ttl=TTL_GEOCODING)
            return location
    except Exception as exc:
        logger.warning("Geocoding live call failed for %r: %s", location_text, exc)

    # ── Stale cache fallback ─────────────────────────────────────────────────
    cached = await cache.get_upstream_stale(cache_key)
    if cached:
        logger.info("Geocoding: serving stale cache for %r", location_text)
        return Location(**cached)

    # ── Direct district resolver (handles exact district names without geocoding)
    district = resolve_district(location_text)
    if district:
        from app.data.loaders import load_districts
        df = load_districts()
        row = df[df["district"] == district].iloc[0]
        return Location(
            input=location_text,
            resolved_name=f"{district}, Maharashtra",
            district=district,
            state="Maharashtra",
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
        )

    raise AppError("LOCATION_NOT_FOUND", {"location_text": location_text})


def _pick_maharashtra(results: list[dict], original: str) -> Location | None:
    """Pick the best Maharashtra result from geocoding results."""
    for r in results:
        admin1 = r.get("admin1", "")
        country_code = r.get("country_code", "")
        if country_code != "IN":
            continue
        if "Maharashtra" not in admin1:
            # Try to match via district resolver directly
            pass
        admin2 = r.get("admin2", "") or r.get("admin1", "")
        district = resolve_district(admin2) or resolve_district(r.get("name", ""))
        if not district:
            continue
        from app.data.resolver import is_agricultural
        if not is_agricultural(district):
            raise AppError("DISTRICT_NOT_AGRICULTURAL", {"district": district})
        return Location(
            input=original,
            resolved_name=f"{district}, Maharashtra",
            district=district,
            state="Maharashtra",
            latitude=float(r["latitude"]),
            longitude=float(r["longitude"]),
        )
    return None


async def search_locations(q: str, limit: int = 5) -> list[Location]:
    """E8 — autocomplete: return up to `limit` place suggestions."""
    try:
        results = await _geocode(q, limit * 2)
        locations = []
        for r in results:
            if r.get("country_code") != "IN":
                continue
            admin2 = r.get("admin2", "") or r.get("admin1", "")
            district = resolve_district(admin2) or resolve_district(r.get("name", ""))
            if not district:
                continue
            locations.append(Location(
                input=q,
                resolved_name=f"{district}, Maharashtra",
                district=district,
                state="Maharashtra",
                latitude=float(r["latitude"]),
                longitude=float(r["longitude"]),
            ))
            if len(locations) >= limit:
                break
        return locations
    except Exception as exc:
        logger.warning("Location search failed for %r: %s", q, exc)
        return []
