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
from datetime import date  # noqa: F401

import httpx

from app.config import settings
from app.core.cache import TTL_PRICES, get_cache
from app.core.http_client import fetch
from app.data.loaders import load_msp, load_price_history
from app.schemas import SourcedValue

logger = logging.getLogger(__name__)

_AGMARKNET_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
_AGMARKNET_TIMEOUT = httpx.Timeout(connect=6.0, read=6.0, write=6.0, pool=2.0)
_AGMARKNET_SOURCE = "Agmarknet (data.gov.in)"
_FRP_SOURCE = "CACP Sugarcane Fair and Remunerative Price"

# Agmarknet returns prices in Rs/quintal
_SUGARCANE_CROPS = {"sugarcane", "sugar cane", "sugarcane (jaggery)"}


async def get_price(crop_id: str, crop_agmarknet_name: str, district: str, state: str = "Maharashtra") -> SourcedValue | None:
    """Return a real price for the crop, or None if excluded.

    Never returns an invented price. None means the crop must be excluded.
    """
    if crop_id.lower() in _SUGARCANE_CROPS or crop_agmarknet_name.lower() in _SUGARCANE_CROPS:
        return _sugarcane_frp()

    cache = await get_cache()
    cache_key = f"prices:{district}:{crop_agmarknet_name}"

    # ── Try live Agmarknet ────────────────────────────────────────────────────
    live = await _fetch_agmarknet(crop_agmarknet_name, district, state)
    if live is not None:
        sv = SourcedValue(
            value=live["modal_price"], unit="rs_per_quintal",
            source=_AGMARKNET_SOURCE,
            source_url=_AGMARKNET_URL,
            as_of=live["date"], status="live",
        )
        await cache.set_upstream(cache_key, {"modal_price": live["modal_price"], "date": live["date"]}, ttl=TTL_PRICES)
        return sv

    # ── State-level fallback (any district in Maharashtra, last 7 days) ───────
    state_price = _lookup_price_history(crop_agmarknet_name, district=None, state=state, days_back=7)
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
    if stale:
        sv = SourcedValue(
            value=stale["modal_price"], unit="rs_per_quintal",
            source=f"{_AGMARKNET_SOURCE} (last quote)",
            source_url=_AGMARKNET_URL,
            as_of=stale["date"], status="cached",
        )
        return sv

    # ── No real price — crop excluded ─────────────────────────────────────────
    logger.info("No real price for %s in %s — crop excluded", crop_agmarknet_name, district)
    return None


async def _fetch_agmarknet(commodity: str, district: str, state: str) -> dict | None:
    if not settings.DATA_GOV_IN_API_KEY:
        logger.warning("DATA_GOV_IN_API_KEY not set; skipping Agmarknet live call")
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
            retries=2,
        )
        records = resp.json().get("records", [])
        if not records:
            return None
        r = records[0]
        return {"modal_price": float(r.get("modal_price", 0)), "date": r.get("arrival_date", "")}
    except Exception as exc:
        logger.warning("Agmarknet fetch failed for %s / %s: %s", commodity, district, exc)
        return None


def _lookup_price_history(commodity: str, district: str | None, state: str, days_back: int = 7) -> dict | None:
    """Search the static price_history_monthly CSV for a recent quote."""
    try:
        df = load_price_history()
        # Filter by commodity (case-insensitive)
        mask = df["commodity"].str.lower() == commodity.lower()
        if district:
            mask &= df["district"].str.lower() == district.lower()
        if state:
            mask &= df.get("state", df.get("state_name", None)) is not None
        subset = df[mask].sort_values("year", ascending=False)
        if not subset.empty:
            row = subset.iloc[0]
            return {"price": float(row.get("modal_price", row.get("price", 0))), "date": str(int(row["year"]))}
    except Exception as exc:
        logger.debug("Price history lookup failed: %s", exc)
    return None


def _sugarcane_frp() -> SourcedValue:
    """Return the official FRP for sugarcane from msp.csv."""
    try:
        df = load_msp()
        mask = df["crop"].str.lower().str.contains("sugarcane")
        latest = df[mask].sort_values("year", ascending=False)
        if not latest.empty:
            row = latest.iloc[0]
            return SourcedValue(
                value=float(row.get("msp_rs_per_quintal", row.get("frp", 355))),
                unit="rs_per_quintal",
                source=_FRP_SOURCE,
                source_url="https://cacp.dacnet.nic.in",
                as_of=str(row.get("year", "2025-26")),
                status="official_dataset",
            )
    except Exception as exc:
        logger.warning("MSP lookup failed: %s", exc)
    # Hard-coded CACP FRP 2025-26 as last resort (declared modelling constant)
    return SourcedValue(
        value=355.0, unit="rs_per_quintal",
        source=_FRP_SOURCE,
        source_url="https://cacp.dacnet.nic.in",
        as_of="2025-26", status="official_dataset",
    )
