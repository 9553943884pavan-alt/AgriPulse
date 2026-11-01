"""SVC.3 — Weather service.

Fetches 16-day forecast + past_days=92 (recent rain) from Open-Meteo.
Fields: precipitation_sum, et0_fao_evapotranspiration, temperature_2m_max,
        temperature_2m_min, relative_humidity_2m_mean (daily mean of hourly),
        forecast_days=16, past_days=92, timezone=Asia/Kolkata.

Fallback: last cached response, labelled status='cached'.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx

from app.core.cache import TTL_WEATHER, get_cache
from app.core.http_client import fetch
from app.schemas import Location, SourcedValue

logger = logging.getLogger(__name__)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_WEATHER_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=2.0)
_OPEN_METEO_SOURCE = "Open-Meteo forecast API"
_OPEN_METEO_URL = "https://api.open-meteo.com"


def _cache_key(location: Location) -> str:
    return f"weather:{location.district}"


async def get_weather(location: Location) -> dict[str, SourcedValue]:
    """Return the latest 16-day forecast + 92-day recent rain for the location.

    Returns a dict of SourcedValue keyed by field name:
      precipitation_recent_mm, et0_recent_mm, temp_max_c, temp_min_c,
      humidity_pct, forecast_rain_mm, as_of
    """
    cache = await get_cache()
    key = _cache_key(location)
    today = date.today().isoformat()

    try:
        resp = await fetch(
            _FORECAST_URL,
            params={
                "latitude": location.latitude,
                "longitude": location.longitude,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration",
                "hourly": "relative_humidity_2m",
                "forecast_days": 16,
                "past_days": 92,
                "timezone": "Asia/Kolkata",
            },
            timeout=_WEATHER_TIMEOUT,
            retries=2,
        )
        raw = resp.json()
        await cache.set_upstream(key, raw, ttl=TTL_WEATHER)
        return _parse_weather(raw, status="live", as_of=today)

    except Exception as exc:
        logger.warning("Weather live call failed for %s: %s", location.district, exc)
        stale = await cache.get_upstream_stale(key)
        if stale:
            stale_date = stale.get("daily", {}).get("time", [today])[-1]
            logger.info("Weather: serving stale cache for %s (as_of=%s)", location.district, stale_date)
            return _parse_weather(stale, status="cached", as_of=stale_date)
        # Return empty dict — caller must handle
        logger.error("Weather: no data at all for %s", location.district)
        return {}


def _parse_weather(raw: dict, status: str, as_of: str) -> dict[str, SourcedValue]:
    """Parse Open-Meteo daily response into SourcedValues."""
    daily = raw.get("daily", {})
    times = daily.get("time", [])
    if not times:
        return {}

    precip = daily.get("precipitation_sum", [])
    et0 = daily.get("et0_fao_evapotranspiration", [])
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])

    # Relative humidity comes from hourly; compute daily mean per day
    hourly = raw.get("hourly", {})
    rh_hourly = hourly.get("relative_humidity_2m", [])
    rh_daily = []
    if rh_hourly:
        # 24 hourly values per day
        for i in range(len(times)):
            chunk = rh_hourly[i * 24:(i + 1) * 24]
            values = [value for value in chunk if value is not None]
            rh_daily.append(sum(values) / len(values) if values else None)

    def sv(value: float | None, unit: str, source: str = _OPEN_METEO_SOURCE) -> SourcedValue:
        return SourcedValue(
            value=round(value, 2) if value is not None else 0.0,
            unit=unit,
            source=source,
            source_url=_OPEN_METEO_URL,
            as_of=as_of,
            status=status,  # type: ignore[arg-type]
        )

    def _sum(lst: list) -> float:
        return sum(v for v in lst if v is not None)

    def _mean(lst: list) -> float:
        vals = [v for v in lst if v is not None]
        return sum(vals) / len(vals) if vals else 0.0

    # Split past (92 days) vs forecast (16 days)
    past = [t for t in times if t <= as_of]
    forecast_idx = len(past)

    precip_past = precip[:forecast_idx]
    precip_fc = precip[forecast_idx:]
    et0_all = et0[:forecast_idx]
    tmax_all = tmax[:forecast_idx]
    tmin_all = tmin[:forecast_idx]
    rh_all = rh_daily[:forecast_idx] if rh_daily else []

    return {
        "precipitation_recent_mm": sv(_sum(precip_past), "mm"),
        "precipitation_forecast_mm": sv(_sum(precip_fc), "mm"),
        "et0_mm": sv(_sum(et0_all), "mm"),
        "temp_max_c": sv(_mean(tmax_all), "celsius"),
        "temp_min_c": sv(_mean(tmin_all), "celsius"),
        "humidity_pct": sv(
            _mean(rh_all) if rh_all else None,
            "pct",
            "Open-Meteo ERA5, daily mean of hourly relative humidity",
        ),
        "as_of": sv(0, "date", as_of),  # marker; actual date in as_of field
    }
