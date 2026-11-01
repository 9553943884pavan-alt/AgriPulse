"""Typed CSV loaders for every processed file (backend/SPECS.md §4.1).

Rules:
  - Each loader is called once and the result cached in memory (process lifetime).
  - Typed columns checked at load time; bad rows logged and dropped.
  - Returns SourcedValue where values are shown to the farmer
    (status = official_dataset, as_of = dataset year).
  - No invented defaults; missing values returned as None.
  - pathlib paths relative to this file -- no absolute C:\\... paths.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# ── Root paths ────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parents[3]          # AgriPulse-main/
_PROC = _REPO / "data" / "processed"


def _load(path: Path, **read_kwargs) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    return pd.read_csv(path, encoding="utf-8", **read_kwargs)


# ── districts.csv (Teammate-A) ────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_districts() -> pd.DataFrame:
    """36 Maharashtra districts with coordinates, name variants, is_agricultural."""
    df = _load(_PROC / "districts.csv")
    required = {"district", "state", "latitude", "longitude", "is_agricultural_district", "name_variants"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"districts.csv missing columns: {missing}")
    df["is_agricultural_district"] = df["is_agricultural_district"].astype(bool)
    df["latitude"] = df["latitude"].astype(float)
    df["longitude"] = df["longitude"].astype(float)
    df["name_variants"] = df["name_variants"].fillna("")
    logger.info("Loaded districts: %d rows", len(df))
    return df


# ── district_crop_yields.csv (Teammate-B) ─────────────────────────────────────

@lru_cache(maxsize=1)
def load_district_crop_yields() -> pd.DataFrame:
    """DES area, production, yield by district / crop / season / year."""
    df = _load(_PROC / "district_crop_yields.csv")
    df["yield_tonnes_per_ha"] = pd.to_numeric(df["yield_tonnes_per_ha"], errors="coerce")
    df["area_ha"] = pd.to_numeric(df["area_ha"], errors="coerce")
    df = df.dropna(subset=["yield_tonnes_per_ha"])
    logger.info("Loaded district_crop_yields: %d rows", len(df))
    return df


# ── crop_calendar.csv (Teammate-B) ────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_crop_calendar() -> pd.DataFrame:
    """Sowing windows, harvest windows, duration_days per crop+season."""
    df = _load(_PROC / "crop_calendar.csv")
    df["sowing_start_month"] = pd.to_numeric(df["sowing_start_month"], errors="coerce")
    df["sowing_end_month"] = pd.to_numeric(df["sowing_end_month"], errors="coerce")
    df["harvest_start_month"] = pd.to_numeric(df["harvest_start_month"], errors="coerce")
    df["harvest_end_month"] = pd.to_numeric(df["harvest_end_month"], errors="coerce")
    df["duration_days"] = pd.to_numeric(df["duration_days"], errors="coerce")
    logger.info("Loaded crop_calendar: %d rows", len(df))
    return df


# ── crops_master.csv (Teammate-B) ─────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_crops_master() -> pd.DataFrame:
    """Crop names in en/mr/hi plus source-name joins (des_crop_name etc.)."""
    df = _load(_PROC / "crops_master.csv")
    logger.info("Loaded crops_master: %d rows", len(df))
    return df


# ── soil_npk_by_district.csv (Teammate-A, all-India 757 districts) ───────────

@lru_cache(maxsize=1)
def load_soil_npk() -> pd.DataFrame:
    """District N, P, K, pH, organic_carbon_pct for all India."""
    df = _load(_PROC / "soil_npk_by_district.csv")
    for col in ("n_kg_per_ha", "p_kg_per_ha", "k_kg_per_ha", "ph"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    logger.info("Loaded soil_npk: %d rows", len(df))
    return df


# ── groundwater_by_block.csv (Teammate-A) ─────────────────────────────────────

@lru_cache(maxsize=1)
def load_groundwater() -> pd.DataFrame:
    """Block-level groundwater category, extraction %, depths.
    The row where block contains 'District Avg' is used for plan-level budget."""
    df = _load(_PROC / "groundwater_by_block.csv")
    if "extraction_pct" in df.columns:
        df["extraction_pct"] = pd.to_numeric(df["extraction_pct"], errors="coerce")
    logger.info("Loaded groundwater: %d rows", len(df))
    return df


# ── irrigation_by_district.csv (Teammate-A) ───────────────────────────────────

@lru_cache(maxsize=1)
def load_irrigation() -> pd.DataFrame:
    """Source shares, efficiency by method per district."""
    df = _load(_PROC / "irrigation_by_district.csv")
    logger.info("Loaded irrigation: %d rows", len(df))
    return df


# ── recent_rainfall.csv (Teammate-A) ─────────────────────────────────────────

@lru_cache(maxsize=1)
def load_recent_rainfall() -> pd.DataFrame:
    """30/60/90-day rainfall snapshot (static; used when live call fails)."""
    df = _load(_PROC / "recent_rainfall.csv")
    logger.info("Loaded recent_rainfall: %d rows", len(df))
    return df


# ── reservoir_storage.csv (Teammate-A) ────────────────────────────────────────

@lru_cache(maxsize=1)
def load_reservoir_storage() -> pd.DataFrame:
    """Live storage % per reservoir and district served (CWC bulletin)."""
    df = _load(_PROC / "reservoir_storage.csv")
    logger.info("Loaded reservoir_storage: %d rows", len(df))
    return df


# ── crop_water_coefficients.csv (Teammate-A) ─────────────────────────────────

@lru_cache(maxsize=1)
def load_crop_water_coefficients() -> pd.DataFrame:
    """Kc and stage lengths per crop (used by ML.7 water-need calculation)."""
    df = _load(_PROC / "crop_water_coefficients.csv")
    logger.info("Loaded crop_water_coefficients: %d rows", len(df))
    return df


# ── cost_of_cultivation.csv (Teammate-B) ─────────────────────────────────────

@lru_cache(maxsize=1)
def load_cost_of_cultivation() -> pd.DataFrame:
    """Itemized DES/CACP costs per crop (reference year 2022-23)."""
    df = _load(_PROC / "cost_of_cultivation.csv")
    logger.info("Loaded cost_of_cultivation: %d rows", len(df))
    return df


# ── seed.csv (Teammate-B) ─────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_seed_prices() -> pd.DataFrame:
    """Seed rates and Mahabeej prices per crop (overrides DES seed line)."""
    df = _load(_PROC / "seed.csv")
    logger.info("Loaded seed_prices: %d rows", len(df))
    return df


# ── fertilizer_rdf.csv (Teammate-B) ──────────────────────────────────────────

@lru_cache(maxsize=1)
def load_fertilizer_rdf() -> pd.DataFrame:
    """University recommended dose (N, P2O5, K2O kg/ha) per crop."""
    df = _load(_PROC / "fertilizer_rdf.csv")
    logger.info("Loaded fertilizer_rdf: %d rows", len(df))
    return df


# ── fertilizer_prices.csv (Teammate-B) ───────────────────────────────────────

@lru_cache(maxsize=1)
def load_fertilizer_prices() -> pd.DataFrame:
    """Official MRPs for urea, DAP, MOP."""
    df = _load(_PROC / "fertilizer_prices.csv")
    logger.info("Loaded fertilizer_prices: %d rows", len(df))
    return df


# ── fertilizer_use_by_district.csv (Teammate-B) ──────────────────────────────

@lru_cache(maxsize=1)
def load_fertilizer_use() -> pd.DataFrame:
    """Actual fertilizer use kg/ha per district (for the vs-district saving)."""
    df = _load(_PROC / "fertilizer_use_by_district.csv")
    logger.info("Loaded fertilizer_use: %d rows", len(df))
    return df


# ── msp.csv (Teammate-B) ──────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_msp() -> pd.DataFrame:
    """Minimum Support Price and FRP per crop, per year."""
    df = _load(_PROC / "msp.csv")
    logger.info("Loaded msp: %d rows", len(df))
    return df


# ── price_history_monthly.csv (Teammate-B) ────────────────────────────────────

@lru_cache(maxsize=1)
def load_price_history() -> pd.DataFrame:
    """Monthly modal Agmarknet prices per district / crop / month."""
    df = _load(_PROC / "price_history_monthly.csv")
    logger.info("Loaded price_history_monthly: %d rows", len(df))
    return df


@lru_cache(maxsize=1)
def load_price_history_state() -> pd.DataFrame:
    """Monthly state medians derived from district Agmarknet price history."""
    df = _load(_PROC / "price_history_state_monthly.csv")
    logger.info("Loaded state price history: %d rows", len(df))
    return df


# ── district_rainfall_history.csv (Teammate-B / rebuilt by build_yield_training.py)

@lru_cache(maxsize=1)
def load_rainfall_history() -> pd.DataFrame:
    """Season rainfall, ET0, temperature history 1997-2014 per district."""
    df = _load(_PROC / "district_rainfall_history.csv")
    logger.info("Loaded district_rainfall_history: %d rows", len(df))
    return df


# ── yield_training.csv (Teammate-B) ───────────────────────────────────────────

@lru_cache(maxsize=1)
def load_yield_training() -> pd.DataFrame:
    """Full training table (used by ML training only, never at runtime)."""
    df = _load(_PROC / "yield_training.csv")
    logger.info("Loaded yield_training: %d rows", len(df))
    return df


# ── Convenience: reload all (used in startup warm-up) ────────────────────────

def load_all() -> int:
    """Eagerly load every CSV into memory. Returns count of files loaded."""
    loaders = [
        load_districts, load_district_crop_yields, load_crop_calendar,
        load_crops_master, load_soil_npk, load_groundwater, load_irrigation,
        load_recent_rainfall, load_reservoir_storage, load_crop_water_coefficients,
        load_cost_of_cultivation, load_seed_prices, load_fertilizer_rdf,
        load_fertilizer_prices, load_fertilizer_use, load_msp,
        load_price_history, load_price_history_state, load_rainfall_history,
    ]
    count = 0
    for fn in loaders:
        try:
            fn()
            count += 1
        except FileNotFoundError as exc:
            logger.warning("Skipping missing data file: %s", exc)
    return count
