"""SVC.6 — Costs service.

Itemized cost per acre per crop. Precedence (SPECS §5.1, ml/SPECS §6):
  - fertilizer: RDF dose × current MRP  (overrides DES 2022-23 line)
  - seed: seed.csv price × seed rate     (overrides DES 2022-23 line)
  - all other lines: DES/CACP 2022-23

DES lines that were replaced are returned in CostBreakdown.superseded so the
frontend can show what changed.
"""

from __future__ import annotations

import logging

from app.data.loaders import (
    load_cost_of_cultivation,
    load_fertilizer_prices,
    load_fertilizer_rdf,
    load_seed_prices,
)
from app.schemas import CostBreakdown, FertilizerPlan, SourcedValue, SupersededLines

logger = logging.getLogger(__name__)

_DES_SOURCE = "DES/CACP Cost of Cultivation 2022-23"
_SEED_SOURCE = "Mahabeej seed price (seed.csv)"
_FERT_SOURCE = "University Recommended Dose × official MRP"
_REF_YEAR = "2022-23"


def get_fertilizer_plan(crop_id: str, land_acres: float = 1.0) -> FertilizerPlan:
    """Compute RDF dose, product bags and cost for crop_id on land_acres."""
    rdf_df = load_fertilizer_rdf()
    fert_prices_df = load_fertilizer_prices()

    rdf_row = rdf_df[rdf_df["crop_id"] == crop_id]
    if rdf_row.empty:
        # Try by crop name
        rdf_row = rdf_df[rdf_df["crop"].str.lower() == crop_id.lower()]
    if rdf_row.empty:
        # No RDF found — return zeros (crop will still be included; fertilizer cost = 0)
        logger.warning("No RDF data for crop_id=%s", crop_id)
        return _zero_fertilizer_plan()

    row = rdf_row.iloc[0]
    # RDF is in kg of nutrient per ha; convert to per acre
    from app.core.units import HA_PER_ACRE
    n_kg_ha = float(row.get("n_kg_per_ha", 0) or 0)
    p_kg_ha = float(row.get("p2o5_kg_per_ha", 0) or 0)
    k_kg_ha = float(row.get("k2o_kg_per_ha", 0) or 0)

    n_kg_acre = round(n_kg_ha * HA_PER_ACRE * land_acres, 2)
    p_kg_acre = round(p_kg_ha * HA_PER_ACRE * land_acres, 2)
    k_kg_acre = round(k_kg_ha * HA_PER_ACRE * land_acres, 2)

    # Conversion: DAP (46% P2O5, 18% N) → MOP (60% K2O) → urea (46% N remainder)
    dap_bags = round(p_kg_acre / 0.46 / 50, 2)        # 50 kg bags
    n_from_dap = dap_bags * 50 * 0.18
    remaining_n = max(0, n_kg_acre - n_from_dap)
    urea_bags = round(remaining_n / 0.46 / 50, 2)
    mop_bags = round(k_kg_acre / 0.60 / 50, 2)

    # Prices
    prices = _get_fertilizer_mrps(fert_prices_df)
    cost_rs = round(
        urea_bags * 50 * prices["urea_rs_per_kg"]
        + dap_bags * 50 * prices["dap_rs_per_kg"]
        + mop_bags * 50 * prices["mop_rs_per_kg"],
        2,
    )

    return FertilizerPlan(
        n_kg_per_acre=n_kg_acre,
        p2o5_kg_per_acre=p_kg_acre,
        k2o_kg_per_acre=k_kg_acre,
        urea_bags=urea_bags,
        dap_bags=dap_bags,
        mop_bags=mop_bags,
        cost_rs=SourcedValue(
            value=cost_rs, unit="rs_per_acre",
            source=_FERT_SOURCE, source_url="",
            as_of="2024-25", status="computed",
        ),
        basis="university recommended dose (RDF)",
    )


def get_cost_breakdown(crop_id: str) -> CostBreakdown:
    """Return itemized cost per acre for crop_id from DES 2022-23 + live overrides."""
    des_df = load_cost_of_cultivation()
    seed_df = load_seed_prices()
    fert_plan = get_fertilizer_plan(crop_id)

    des_row = des_df[des_df["crop_id"] == crop_id] if "crop_id" in des_df.columns else des_df[des_df["crop"].str.lower() == crop_id.lower()]
    if des_row.empty:
        logger.warning("No DES cost data for crop_id=%s; returning zeros", crop_id)
        return _zero_cost_breakdown(fert_plan)

    r = des_row.iloc[0]
    def _f(col: str) -> float:
        try:
            return float(r.get(col, 0) or 0)
        except (ValueError, TypeError):
            return 0.0

    # DES values (per hectare → per acre conversion)
    from app.core.units import HA_PER_ACRE
    scale = HA_PER_ACRE  # DES data is per ha; we serve per acre

    des_seed = _f("seed_rs_per_ha") * scale
    des_fert = _f("fertilizer_rs_per_ha") * scale

    # Seed from seed.csv (overrides DES)
    live_seed = _get_seed_cost(crop_id, seed_df)
    seed_cost = live_seed if live_seed is not None else des_seed

    # Fertilizer from RDF plan (overrides DES)
    fert_cost = float(fert_plan.cost_rs.value)

    other_lines = {
        "manure": _f("manure_rs_per_ha") * scale,
        "labour": (_f("human_labour_rs_per_ha") + _f("bullock_labour_rs_per_ha")) * scale,
        "machine": _f("machine_labour_rs_per_ha") * scale,
        "irrigation": _f("irrigation_rs_per_ha") * scale,
        "pesticide": _f("pesticide_rs_per_ha") * scale,
        "interest": _f("interest_rs_per_ha") * scale,
    }
    total = round(seed_cost + fert_cost + sum(other_lines.values()), 2)

    return CostBreakdown(
        total_rs=total,
        seed=round(seed_cost, 2),
        fertilizer=round(fert_cost, 2),
        manure=round(other_lines["manure"], 2),
        labour=round(other_lines["labour"], 2),
        machine=round(other_lines["machine"], 2),
        irrigation=round(other_lines["irrigation"], 2),
        pesticide=round(other_lines["pesticide"], 2),
        interest=round(other_lines["interest"], 2),
        superseded=SupersededLines(seed_des=round(des_seed, 2), fertilizer_des=round(des_fert, 2)),
        reference_year=_REF_YEAR,
        source=_DES_SOURCE,
        status="official_dataset",
    )


def _get_seed_cost(crop_id: str, seed_df) -> float | None:
    row = seed_df[seed_df["crop_id"] == crop_id] if "crop_id" in seed_df.columns else seed_df[seed_df["crop"].str.lower() == crop_id.lower()]
    if row.empty:
        return None
    r = row.iloc[0]
    try:
        rate = float(r.get("seed_rate_kg_per_ha", 0) or 0)
        price = float(r.get("price_rs_per_kg", 0) or 0)
        from app.core.units import HA_PER_ACRE
        return round(rate * price * HA_PER_ACRE, 2)
    except (ValueError, TypeError):
        return None


def _get_fertilizer_mrps(fert_prices_df) -> dict[str, float]:
    def _price(product: str) -> float:
        row = fert_prices_df[fert_prices_df["product"].str.lower() == product.lower()]
        if row.empty:
            return 0.0
        return float(row.iloc[0].get("mrp_rs_per_kg", row.iloc[0].get("price_rs_per_kg", 0)) or 0)
    return {
        "urea_rs_per_kg": _price("urea") or 5.36,       # NFMS 2024 controlled price
        "dap_rs_per_kg": _price("dap") or 27.0,
        "mop_rs_per_kg": _price("mop") or 17.0,
    }


def _zero_fertilizer_plan() -> FertilizerPlan:
    return FertilizerPlan(
        n_kg_per_acre=0, p2o5_kg_per_acre=0, k2o_kg_per_acre=0,
        urea_bags=0, dap_bags=0, mop_bags=0,
        cost_rs=SourcedValue(value=0, unit="rs_per_acre", source="unavailable",
                             source_url="", as_of="", status="official_dataset"),
    )


def _zero_cost_breakdown(fert_plan: FertilizerPlan) -> CostBreakdown:
    return CostBreakdown(
        total_rs=0, seed=0, fertilizer=float(fert_plan.cost_rs.value),
        manure=0, labour=0, machine=0, irrigation=0, pesticide=0, interest=0,
        reference_year=_REF_YEAR, source=_DES_SOURCE, status="official_dataset",
    )
