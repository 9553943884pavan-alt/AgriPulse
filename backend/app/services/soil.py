"""SVC.4 — Soil service.

Priority (highest wins):
  1. Farmer's own soil test (FarmProfile.soil_test)
  2. SoilGrids live API (optional; pH÷10, N÷100, SOC÷10 unit conversions)
  3. District N/P/K from soil_npk_by_district.csv

Missing values returned as None — never a guess.
"""

from __future__ import annotations

import logging
import time

import httpx

from app.core.cache import TTL_SOIL, get_cache
from app.core.http_client import fetch
from app.data.loaders import load_soil_npk
from app.data.resolver import resolve_district
from app.schemas import FarmProfile, Location, SourcedValue

logger = logging.getLogger(__name__)

_SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
_SOILGRIDS_TIMEOUT = httpx.Timeout(connect=6.0, read=6.0, write=6.0, pool=2.0)
_NPK_SOURCE = "Soil Health Card Survey (ICAR/State Agriculture Depts)"
_SOILGRIDS_SOURCE = "SoilGrids v2 (ISRIC)"


async def get_soil(profile: FarmProfile, location: Location) -> dict[str, SourcedValue | None]:
    """Return soil N, P, K, pH, organic_carbon as SourcedValues.

    Returns dict with keys: n, p, k, ph, organic_carbon.
    Any value may be None if the source is unavailable.
    """
    # ── 1. Farmer's own soil test overrides everything ────────────────────────
    if profile.soil_test:
        st = profile.soil_test
        def _farmer(val: float, unit: str) -> SourcedValue:
            return SourcedValue(
                value=val, unit=unit, source="Farmer soil test",
                source_url="", as_of="current", status="farmer_input",
            )
        return {
            "n": _farmer(st.n, "kg_per_ha"),
            "p": _farmer(st.p, "kg_per_ha"),
            "k": _farmer(st.k, "kg_per_ha"),
            "ph": _farmer(st.ph, "pH"),
            "organic_carbon": None,
        }

    # ── 2. SoilGrids live (optional) ─────────────────────────────────────────
    soilgrids = await _fetch_soilgrids(location)
    if soilgrids:
        # Merge: district CSV fills any gaps SoilGrids doesn't cover (N, P, K)
        district_csv = _load_district_soil(location.district)
        return {
            "n": district_csv.get("n"),       # SoilGrids doesn't have N; use CSV
            "p": district_csv.get("p"),       # ditto P
            "k": district_csv.get("k"),       # ditto K
            "ph": soilgrids.get("ph") or district_csv.get("ph"),
            "organic_carbon": soilgrids.get("organic_carbon"),
        }

    # ── 3. District CSV fallback ──────────────────────────────────────────────
    return _load_district_soil(location.district)


def _load_district_soil(district: str) -> dict[str, SourcedValue | None]:
    df = load_soil_npk()
    # Filter Maharashtra
    mh = df[df["state"].str.upper() == "MAHARASHTRA"]
    # Try canonical district, then resolver
    match = mh[mh["district"].str.lower() == district.lower()]
    if match.empty:
        canonical = resolve_district(district)
        if canonical:
            match = mh[mh["district"].str.lower() == canonical.lower()]
    if match.empty:
        logger.warning("No soil data for district: %s", district)
        return {"n": None, "p": None, "k": None, "ph": None, "organic_carbon": None}

    row = match.iloc[0]
    as_of = "2019"   # Soil Health Card survey year
    def sv(col: str, unit: str) -> SourcedValue | None:
        val = row.get(col)
        if val is None or (hasattr(val, '__class__') and str(val) == "nan"):
            return None
        try:
            fval = float(val)
        except (ValueError, TypeError):
            return None
        return SourcedValue(
            value=fval, unit=unit, source=_NPK_SOURCE,
            source_url="", as_of=as_of, status="official_dataset",
        )

    return {
        "n": sv("n_kg_per_ha", "kg_per_ha"),
        "p": sv("p_kg_per_ha", "kg_per_ha"),
        "k": sv("k_kg_per_ha", "kg_per_ha"),
        "ph": sv("ph", "pH"),
        "organic_carbon": sv("organic_carbon_pct", "pct"),
    }


_SOILGRIDS_COOLDOWN_S = 300.0
_soilgrids_down_until: float = 0.0


async def _fetch_soilgrids(location: Location) -> dict[str, SourcedValue] | None:
    """Try SoilGrids live; return None on any failure (0 retries per SPECS)."""
    global _soilgrids_down_until
    cache = await get_cache()
    key = f"soilgrids:{location.latitude:.4f},{location.longitude:.4f}"
    cached = await cache.get_upstream(key)
    if cached:
        return _parse_soilgrids(cached, status="cached")
    if time.monotonic() < _soilgrids_down_until:
        return None
    try:
        resp = await fetch(
            _SOILGRIDS_URL,
            params={
                "lon": location.longitude,
                "lat": location.latitude,
                "property": ["phh2o", "nitrogen", "soc"],  # repeated param per ISRIC docs
                "depth": "0-30cm",
                "value": "mean",
            },
            timeout=_SOILGRIDS_TIMEOUT,
            retries=0,
        )
        raw = resp.json()
        await cache.set_upstream(key, raw, ttl=TTL_SOIL)
        return _parse_soilgrids(raw, status="live")
    except Exception as exc:
        _soilgrids_down_until = time.monotonic() + _SOILGRIDS_COOLDOWN_S
        logger.info("SoilGrids unavailable (skipping for %ds): %s", int(_SOILGRIDS_COOLDOWN_S), exc)
        return None


def _parse_soilgrids(raw: dict, status: str) -> dict[str, SourcedValue]:
    result = {}
    layers = raw.get("properties", {}).get("layers", [])
    for layer in layers:
        name = layer.get("name", "")
        val = (
            layer.get("depths", [{}])[0]
            .get("values", {})
            .get("mean")
        )
        if val is None:
            continue
        if name == "phh2o":
            result["ph"] = SourcedValue(
                value=round(val / 10, 2), unit="pH",
                source=_SOILGRIDS_SOURCE, source_url=_SOILGRIDS_URL,
                as_of="2023", status=status,  # type: ignore[arg-type]
            )
        elif name == "nitrogen":
            result["n_soilgrids"] = SourcedValue(
                value=round(val / 100, 2), unit="g_per_kg",
                source=_SOILGRIDS_SOURCE, source_url=_SOILGRIDS_URL,
                as_of="2023", status=status,  # type: ignore[arg-type]
            )
        elif name == "soc":
            result["organic_carbon"] = SourcedValue(
                value=round(val / 10, 2), unit="g_per_kg",
                source=_SOILGRIDS_SOURCE, source_url=_SOILGRIDS_URL,
                as_of="2023", status=status,  # type: ignore[arg-type]
            )
    return result
