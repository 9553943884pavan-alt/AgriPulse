"""SVC.5 — Prices service.

Agmarknet (data.gov.in) live prices with fallback chain:
  1. Today's district quote
  2. Any district in Maharashtra in the last 7 days
  3. Nearest reporting mandi
  4. Last cached real quote with date
  5. Crop excluded (no invented price ever)

Sugarcane: priced at official FRP from msp.csv, never at jaggery prices.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import date, timedelta
from statistics import median

import httpx

from app.config import settings
from app.core.cache import TTL_PRICES, get_cache
from app.core.http_client import fetch
from app.data.loaders import (
    load_crops_master,
    load_msp,
    load_price_history,
    load_price_history_state,
)
from app.ml.constants import MIN_PRICE_YEARS
from app.schemas import SourcedValue

logger = logging.getLogger(__name__)

_AGMARKNET_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
_AGMARKNET_TIMEOUT = httpx.Timeout(connect=6.0, read=6.0, write=6.0, pool=2.0)
_AGMARKNET_SOURCE = "Agmarknet (data.gov.in)"
_FRP_SOURCE = "CACP Sugarcane Fair and Remunerative Price"

# Agmarknet returns prices in Rs/quintal
_SUGARCANE_CROPS = {"sugarcane", "sugar cane", "sugarcane (jaggery)"}
PRICE_HISTORY_MAX_AGE_DAYS = 365

# Circuit breaker: data.gov.in is often slow/502 (a call can hang for a minute).
# After one failure skip live calls for a few minutes so a plan does not wait
# crop-by-crop; the labelled "cached" fallbacks below are used instead.
_LIVE_COOLDOWN_S = 300.0
_live_down_until: float = 0.0


def reset_agmarknet_breaker() -> None:
    global _live_down_until
    _live_down_until = 0.0


async def get_price(crop_id: str, district: str, state: str = "Maharashtra") -> SourcedValue | None:
    """Return a real price for the crop, or None if excluded.

    Never returns an invented price. None means the crop must be excluded.
    """
    if crop_id.lower() in _SUGARCANE_CROPS:
        return _sugarcane_frp()

    commodity = _agmarknet_commodity(crop_id)
    if commodity is None:
        logger.info("No Agmarknet commodity mapping for %s — crop excluded", crop_id)
        return None

    cache = await get_cache()
    cache_key = f"prices:{district}:{commodity}"

    # ── Try live Agmarknet ────────────────────────────────────────────────────
    live = await _fetch_agmarknet(commodity, district, state)
    if live is not None:
        sv = SourcedValue(
            value=live["modal_price"], unit="rs_per_quintal",
            source=_AGMARKNET_SOURCE,
            source_url=_AGMARKNET_URL,
            as_of=live["date"], status="live",
        )
        await cache.set_upstream(cache_key, {"modal_price": live["modal_price"], "date": live["date"]}, ttl=TTL_PRICES)
        return sv

    # Monthly source data is bounded to one year; prefer the requested district.
    district_price = _lookup_price_history(commodity, district=district, state=state)
    if district_price:
        return SourcedValue(
            value=district_price["price"], unit="rs_per_quintal",
            source="Agmarknet historical monthly dataset (district)",
            source_url=_AGMARKNET_URL,
            as_of=district_price["date"], status="cached",
        )

    # ── State-level fallback using recent monthly data ────────────────────────
    state_price = _lookup_price_history(commodity, district=None, state=state)
    if state_price:
        sv = SourcedValue(
            value=state_price["price"], unit="rs_per_quintal",
            source=f"{_AGMARKNET_SOURCE} (state level)",
            source_url=_AGMARKNET_URL,
            as_of=state_price["date"], status="cached",
        )
        return sv

    # ── Stale cache (last real quote from this district) ─────────────────────
    stale = await cache.get_upstream_stale(cache_key)
    if stale and _positive_price(stale.get("modal_price")) and stale.get("date"):
        sv = SourcedValue(
            value=stale["modal_price"], unit="rs_per_quintal",
            source=f"{_AGMARKNET_SOURCE} (last quote)",
            source_url=_AGMARKNET_URL,
            as_of=stale["date"], status="cached",
        )
        return sv

    # ── No real price — crop excluded ─────────────────────────────────────────
    logger.info("No real price for %s in %s — crop excluded", commodity, district)
    return None


def _agmarknet_commodity(crop_id: str) -> str | None:
    try:
        df = load_crops_master()
        rows = df[df["crop_id"].astype(str).str.strip().str.casefold() == crop_id.casefold()]
        if rows.empty:
            return None
        value = rows.iloc[0].get("agmarknet_commodity")
        if value is None or not str(value).strip() or str(value).strip().lower() == "nan":
            return None
        return str(value).strip()
    except Exception as exc:
        logger.warning("Agmarknet commodity lookup failed for %s: %s", crop_id, exc)
        return None


def _positive_price(value: object) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and price > 0 else None


async def _fetch_agmarknet(commodity: str, district: str, state: str) -> dict | None:
    if not settings.DATA_GOV_IN_API_KEY:
        logger.warning("DATA_GOV_IN_API_KEY not set; skipping Agmarknet live call")
        return None
    global _live_down_until
    if time.monotonic() < _live_down_until:
        return None
    try:
        resp = await fetch(
            _AGMARKNET_URL,
            params={
                "api-key": settings.DATA_GOV_IN_API_KEY,
                "format": "json",
                "filters[state]": state,
                "filters[district]": district,
                "filters[commodity]": commodity,
                "limit": 1,
                "sort[arrival_date]": "desc",
            },
            timeout=_AGMARKNET_TIMEOUT,
            retries=0,
        )
        records = resp.json().get("records", [])
        if not records:
            return None
        r = records[0]
        price = _positive_price(r.get("modal_price"))
        arrival_date = str(r.get("arrival_date", "")).strip()
        if price is None or not arrival_date:
            return None
        return {"modal_price": price, "date": arrival_date}
    except Exception as exc:
        _live_down_until = time.monotonic() + _LIVE_COOLDOWN_S
        logger.warning("Agmarknet fetch failed for %s / %s: %s (live calls paused %ds)",
                       commodity, district, type(exc).__name__, int(_LIVE_COOLDOWN_S))
        return None


def _lookup_price_history(
    commodity: str,
    district: str | None,
    state: str,
    max_age_days: int = PRICE_HISTORY_MAX_AGE_DAYS,
) -> dict | None:
    """Find the newest positive monthly quote within the supported age window."""
    try:
        if district:
            df = load_price_history()
            price_column = "modal_price_rs_per_quintal"
            required = {"commodity", "district", "year", "month", price_column}
            if not required.issubset(df.columns):
                return None
            mask = (
                df["commodity"].astype(str).str.strip().str.casefold()
                == commodity.strip().casefold()
            ) & (
                df["district"].astype(str).str.strip().str.casefold()
                == district.strip().casefold()
            )
        else:
            if state.strip().casefold() != "maharashtra":
                return None
            df = load_price_history_state()
            price_column = "median_modal_rs_per_quintal"
            required = {"commodity", "year", "month", price_column}
            if not required.issubset(df.columns):
                return None
            mask = (
                df["commodity"].astype(str).str.strip().str.casefold()
                == commodity.strip().casefold()
            )

        today = date.today()
        oldest_date = today - timedelta(days=max_age_days)
        recent_quotes = []
        for _, row in df[mask].iterrows():
            price = _positive_price(row.get(price_column))
            if price is None:
                continue
            try:
                quote_date = date(int(row["year"]), int(row["month"]), 1)
            except (TypeError, ValueError, OverflowError):
                continue
            if oldest_date <= quote_date <= today:
                quote_district = str(row["district"]) if "district" in row else state
                recent_quotes.append((quote_date, price, quote_district))
        if recent_quotes:
            quote_date, price, quote_district = max(recent_quotes, key=lambda quote: quote[0])
            return {
                "price": price,
                "date": quote_date.strftime("%Y-%m"),
                "district": quote_district,
            }
    except Exception as exc:
        logger.debug("Price history lookup failed: %s", exc)
    return None


def quote_month(as_of: str | None, fallback: int) -> int:
    """Calendar month a price quote refers to ("YYYY-MM", "YYYY-MM-DD" or "dd/mm/yyyy").

    The seasonal ratio must be anchored on the quote's own month: a May quote
    adjusted with a November-based ratio double-counts the seasonal swing.
    """
    text = (as_of or "").strip()
    try:
        if "/" in text:
            month = int(text.split("/")[1])
        else:
            month = int(text.split("-")[1])
    except (IndexError, ValueError):
        return fallback
    return month if 1 <= month <= 12 else fallback


def seasonal_price_ratio(
    crop_id: str,
    district: str,
    current_month: int,
    harvest_month: int,
) -> tuple[float, int, str]:
    """Return a real monthly-history ratio, or an explicit unadjusted value."""
    commodity = _agmarknet_commodity(crop_id)
    if commodity is None:
        return 1.0, 0, "No Agmarknet commodity mapping"

    try:
        df = load_price_history()
        district_rows = df[
            (df["commodity"].astype(str).str.strip().str.casefold() == commodity.casefold())
            & (df["district"].astype(str).str.strip().str.casefold() == district.strip().casefold())
        ]
        if not district_rows.empty:
            rows = district_rows
            price_column = "modal_price_rs_per_quintal"
            source = f"Agmarknet monthly price history ({district})"
        else:
            rows = load_price_history_state()
            rows = rows[
                rows["commodity"].astype(str).str.strip().str.casefold() == commodity.casefold()
            ]
            price_column = "median_modal_rs_per_quintal"
            source = "Agmarknet state median monthly price history"
        required = {"commodity", "year", "month", price_column}
        if not required.issubset(rows.columns):
            return 1.0, 0, "Monthly price history is missing required columns"

        prices_by_period: dict[tuple[int, int], float] = {}
        for _, row in rows.iterrows():
            try:
                year = int(row["year"])
                month = int(row["month"])
            except (TypeError, ValueError):
                continue
            price = _positive_price(row.get(price_column))
            if price is not None and 1 <= month <= 12:
                prices_by_period[(year, month)] = price

        harvest_year_offset = 1 if harvest_month <= current_month else 0
        ratios = []
        for (year, month), current_price in prices_by_period.items():
            if month != current_month:
                continue
            harvest_price = prices_by_period.get((year + harvest_year_offset, harvest_month))
            if harvest_price is not None:
                ratios.append(harvest_price / current_price)
    except Exception as exc:
        logger.warning("Seasonal price history lookup failed for %s: %s", crop_id, exc)
        return 1.0, 0, "Monthly price history unavailable"

    if len(ratios) < MIN_PRICE_YEARS:
        return 1.0, len(ratios), f"Insufficient seasonal price history ({len(ratios)} years)"
    return (
        float(median(ratios)),
        len(ratios),
        f"{source} ({len(ratios)} years)",
    )


def get_msp(crop_id: str, season: str | None = None) -> SourcedValue | None:
    """Return the latest official crop MSP, when the dataset has one."""
    try:
        df = load_msp()
        if "crop_id" not in df.columns or "msp_rs_per_quintal" not in df.columns:
            return None
        rows = df[df["crop_id"].astype(str).str.strip().str.casefold() == crop_id.casefold()]
        if season and "season" in rows.columns:
            season_rows = rows[
                rows["season"].astype(str).str.strip().str.casefold() == season.casefold()
            ]
            if not season_rows.empty:
                rows = season_rows
        if rows.empty:
            return None
        latest = rows.sort_values("year", ascending=False).iloc[0]
        price = _positive_price(latest.get("msp_rs_per_quintal"))
        if price is None:
            return None
        return SourcedValue(
            value=price,
            unit="rs_per_quintal",
            source=f"Official MSP: {latest.get('source_notification', 'MSP dataset')}",
            source_url="https://cacp.dacnet.nic.in",
            as_of=str(latest["year"]),
            status="official_dataset",
        )
    except Exception as exc:
        logger.warning("MSP lookup failed for %s: %s", crop_id, exc)
        return None


def _sugarcane_frp() -> SourcedValue | None:
    """Return the official FRP for sugarcane, or None when no value is sourced."""
    try:
        df = load_msp()
        mask = df["crop"].str.lower().str.contains("sugarcane")
        latest = df[mask].sort_values("year", ascending=False)
        if not latest.empty:
            row = latest.iloc[0]
            price = _positive_price(row.get("msp_rs_per_quintal"))
            if price is None:
                return None
            return SourcedValue(
                value=price,
                unit="rs_per_quintal",
                source=f"{_FRP_SOURCE}: {row.get('source_notification', 'official dataset')}",
                source_url="https://cacp.dacnet.nic.in",
                as_of=str(row["year"]),
                status="official_dataset",
            )
    except Exception as exc:
        logger.warning("MSP lookup failed: %s", exc)
    return None
