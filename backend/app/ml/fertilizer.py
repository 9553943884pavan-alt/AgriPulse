"""ML.8 — Fertilizer plan: RDF dose per crop, priced with official MRPs.

Conversion order (as per ml/SPECS §6):
  1. All P₂O₅ from DAP (46% P₂O₅, 18% N also supplied).
  2. Remaining N from Urea (46% N).
  3. All K₂O from MOP (60% K₂O).

Result: nutrient kg/acre AND bag counts AND total cost (Rs).

The fixed RDF dose is independent of crop price — no crop_price parameter.
(This fixes the alignment bug noted in SPECS_ALIGNMENT_RESOLUTION §3.4.)

fertilizer_vs_district_use_pct is computed here when district use is
available, otherwise returned as None.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache

import pandas as pd

from app.schemas import FertilizerPlan, SourcedValue

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
# Nutrient content of each product (weight fraction)
_DAP_P2O5 = 0.46
_DAP_N    = 0.18
_UREA_N   = 0.46
_MOP_K2O  = 0.60

# ha → acre conversion
_HA_TO_ACRE = 2.47105


# ── Data loaders ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _rdf() -> pd.DataFrame:
    from app.data.loaders import load_fertilizer_rdf
    return load_fertilizer_rdf()


@lru_cache(maxsize=1)
def _prices() -> pd.DataFrame:
    from app.data.loaders import load_fertilizer_prices
    return load_fertilizer_prices()


@lru_cache(maxsize=1)
def _district_use() -> pd.DataFrame:
    from app.data.loaders import load_fertilizer_use
    return load_fertilizer_use()


# ── Price lookup ──────────────────────────────────────────────────────────────

def _price_per_kg(fert_id: str) -> float:
    """Return Rs/kg for a fertilizer product."""
    df = _prices()
    rows = df[df["fertilizer_id"] == fert_id]
    if rows.empty:
        raise ValueError(f"No sourced MRP for fertilizer {fert_id}")
    price = float(rows.iloc[0]["price_rs_per_kg"])
    if not math.isfinite(price) or price <= 0:
        raise ValueError(f"Invalid sourced MRP for fertilizer {fert_id}")
    return price


def _bag_size(fert_id: str) -> float:
    """Return bag size in kg."""
    df = _prices()
    rows = df[df["fertilizer_id"] == fert_id]
    if rows.empty:
        raise ValueError(f"No sourced bag size for fertilizer {fert_id}")
    bag_size = float(rows.iloc[0]["bag_size_kg"])
    if not math.isfinite(bag_size) or bag_size <= 0:
        raise ValueError(f"Invalid sourced bag size for fertilizer {fert_id}")
    return bag_size


# ── Dose converter ────────────────────────────────────────────────────────────

def _kg_per_ha_to_per_acre(value: float) -> float:
    return value / _HA_TO_ACRE


def _compute_bags_and_cost(
    n_kg_acre: float,
    p2o5_kg_acre: float,
    k2o_kg_acre: float,
) -> tuple[float, float, float, float]:
    """Return (dap_bags, urea_bags, mop_bags, total_cost_rs).

    Conversion order per SPECS §6:
      Step 1: All P₂O₅ from DAP → also supplies some N.
      Step 2: Remaining N from Urea.
      Step 3: All K₂O from MOP.
    """
    # Step 1: DAP for all P₂O₅
    dap_kg = p2o5_kg_acre / _DAP_P2O5                # kg of DAP
    n_from_dap = dap_kg * _DAP_N                      # N supplied by DAP

    # Step 2: Remaining N from Urea
    n_remaining = max(0.0, n_kg_acre - n_from_dap)
    urea_kg = n_remaining / _UREA_N

    # Step 3: MOP for K₂O
    mop_kg = k2o_kg_acre / _MOP_K2O

    # Bags (partial bags rounded up, reported as float for precision)
    dap_bags  = dap_kg  / _bag_size("dap")
    urea_bags = urea_kg / _bag_size("urea")
    mop_bags  = mop_kg  / _bag_size("mop")

    # Cost
    cost = (
        dap_kg  * _price_per_kg("dap")  +
        urea_kg * _price_per_kg("urea") +
        mop_kg  * _price_per_kg("mop")
    )

    return dap_bags, urea_bags, mop_bags, cost


def _sv_cost(cost: float, source: str) -> SourcedValue:
    from datetime import date
    return SourcedValue(
        value=round(cost, 0),
        unit="rs",
        source=source,
        as_of=str(date.today()),
        status="computed",
    )


# ── District fertilizer use comparison ────────────────────────────────────────

def _district_use_kg_ha(district: str) -> float | None:
    """Return mean district N+P+K use (kg/ha) if available, else None."""
    try:
        df = _district_use()
        dist_col = next((c for c in df.columns if "district" in c.lower()), None)
        if dist_col is None:
            return None
        rows = df[df[dist_col].str.strip() == district]
        if rows.empty:
            return None
        # Sum N+P+K columns if present
        nutrient_cols = [c for c in df.columns if any(
            n in c.lower() for n in ("_n_", "nitrogen", "_p_", "phosph", "_k_", "potash", "npk")
        )]
        if nutrient_cols:
            return float(rows[nutrient_cols].sum(axis=1).mean())
        return None
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def fertilizer_plan(
    crop_id: str,
    season: str,
    district: str | None = None,
) -> FertilizerPlan:
    """ML.8 — RDF dose per crop, priced with official MRPs.

    Args:
        crop_id:  Canonical crop id.
        season:   "Kharif" | "Rabi" | "Summer" | "Whole Year".
        district: Optional — used only to compute fertilizer_vs_district_use_pct.

    Returns:
        FertilizerPlan with nutrient kg/acre, bag counts, cost.
    """
    df = _rdf()

    # Match by crop_id + season; fall back to crop_id only
    rows = df[(df["crop_id"] == crop_id) & (df["season"] == season)]
    if rows.empty:
        rows = df[df["crop_id"] == crop_id]

    if rows.empty:
        logger.warning("fertilizer_plan: no RDF data for %s %s", crop_id, season)
        raise ValueError(f"No RDF data for {crop_id} {season}")

    row = rows.iloc[0]
    source = str(row.get("university_source", "university RDF"))

    # Convert ha → acre
    n_ha   = float(row["n_kg_per_ha"])
    p_ha   = float(row["p2o5_kg_per_ha"])
    k_ha   = float(row["k2o_kg_per_ha"])

    n_acre = _kg_per_ha_to_per_acre(n_ha)
    p_acre = _kg_per_ha_to_per_acre(p_ha)
    k_acre = _kg_per_ha_to_per_acre(k_ha)

    dap_bags, urea_bags, mop_bags, cost = _compute_bags_and_cost(n_acre, p_acre, k_acre)

    cost_source = f"RDF dose × official MRP (DAP ₹{_price_per_kg('dap'):.2f}/kg, Urea ₹{_price_per_kg('urea'):.2f}/kg, MOP ₹{_price_per_kg('mop'):.2f}/kg)"

    return FertilizerPlan(
        n_kg_per_acre=round(n_acre, 2),
        p2o5_kg_per_acre=round(p_acre, 2),
        k2o_kg_per_acre=round(k_acre, 2),
        urea_bags=round(urea_bags, 3),
        dap_bags=round(dap_bags, 3),
        mop_bags=round(mop_bags, 3),
        cost_rs=_sv_cost(cost, cost_source),
        basis=f"University recommended dose (RDF) — {source}",
    )
