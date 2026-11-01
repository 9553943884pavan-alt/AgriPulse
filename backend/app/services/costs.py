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
import math

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
        logger.warning("No RDF data for crop_id=%s", crop_id)
        raise ValueError(f"No RDF data for {crop_id}")

    row = rdf_row.iloc[0]
    # RDF is in kg of nutrient per ha; convert to per acre
    from app.core.units import HA_PER_ACRE
    n_kg_ha = _required_nonnegative(row, "n_kg_per_ha")
    p_kg_ha = _required_nonnegative(row, "p2o5_kg_per_ha")
    k_kg_ha = _required_nonnegative(row, "k2o_kg_per_ha")

    n_kg_acre = round(n_kg_ha * HA_PER_ACRE * land_acres, 2)
    p_kg_acre = round(p_kg_ha * HA_PER_ACRE * land_acres, 2)
    k_kg_acre = round(k_kg_ha * HA_PER_ACRE * land_acres, 2)

    # Conversion: DAP (46% P2O5, 18% N) → MOP (60% K2O) → urea (46% N remainder)
    dap_kg = p_kg_acre / 0.46
    n_from_dap = dap_kg * 0.18
    urea_kg = max(0, n_kg_acre - n_from_dap) / 0.46
    mop_kg = k_kg_acre / 0.60

    # Prices
    prices = _get_fertilizer_mrps(fert_prices_df)
    bag_sizes = _get_fertilizer_bag_sizes(fert_prices_df)
    cost_rs = round(
        urea_kg * prices["urea_rs_per_kg"]
        + dap_kg * prices["dap_rs_per_kg"]
        + mop_kg * prices["mop_rs_per_kg"],
        2,
    )

    return FertilizerPlan(
        n_kg_per_acre=n_kg_acre,
        p2o5_kg_per_acre=p_kg_acre,
        k2o_kg_per_acre=k_kg_acre,
        urea_bags=round(urea_kg / bag_sizes["urea"], 2),
        dap_bags=round(dap_kg / bag_sizes["dap"], 2),
        mop_bags=round(mop_kg / bag_sizes["mop"], 2),
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
        logger.warning("No DES cost data for crop_id=%s", crop_id)
        raise ValueError(f"No DES cost data for {crop_id}")

    r = des_row.iloc[0]
    def _f(col: str) -> float:
        try:
            value = float(r[col])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"Missing or invalid DES cost field {col} for {crop_id}") from exc
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid DES cost field {col} for {crop_id}")
        return value

    # DES values (per hectare → per acre conversion)
    from app.core.units import HA_PER_ACRE
    scale = HA_PER_ACRE  # DES data is per ha; we serve per acre

    des_seed = _f("seed_rs_per_ha") * scale
    des_fert = _f("fertilizer_rs_per_ha") * scale

    # Seed from seed.csv (overrides DES)
    live_seed = _get_seed_cost(crop_id, seed_df)
    if live_seed is None:
        raise ValueError(f"No sourced seed cost for {crop_id}")
    seed_cost = live_seed

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
        direct_cost = float(r.get("seed_cost_rs_per_acre"))
        if math.isfinite(direct_cost) and direct_cost > 0:
            return round(direct_cost, 2)
    except (ValueError, TypeError):
        pass

    try:
        rate = float(r.get("seed_rate_kg_per_acre"))
        price = float(r.get("seed_price_rs_per_kg"))
        if rate > 0 and price > 0 and math.isfinite(rate * price):
            return round(rate * price, 2)
    except (ValueError, TypeError):
        pass

    try:
        rate = float(r.get("seed_rate_kg_per_ha"))
        price = float(r.get("price_rs_per_kg"))
        from app.core.units import HA_PER_ACRE
        if rate > 0 and price > 0 and math.isfinite(rate * price):
            return round(rate * price * HA_PER_ACRE, 2)
    except (ValueError, TypeError):
        pass
    return None


def _required_nonnegative(row, column: str) -> float:
    try:
        value = float(row[column])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError(f"Missing or invalid fertilizer RDF field {column}") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid fertilizer RDF field {column}")
    return value


def _get_fertilizer_mrps(fert_prices_df) -> dict[str, float]:
    def _price(product: str) -> float:
        col = "fertilizer_id" if "fertilizer_id" in fert_prices_df.columns else "fertilizer" if "fertilizer" in fert_prices_df.columns else "product"
        if col not in fert_prices_df.columns:
            raise ValueError("Fertilizer price source has no product identifier")
        row = fert_prices_df[fert_prices_df[col].astype(str).str.lower() == product.lower()]
        if row.empty:
            raise ValueError(f"No sourced MRP for fertilizer {product}")
        value = row.iloc[0].get("mrp_rs_per_kg", row.iloc[0].get("price_rs_per_kg"))
        try:
            price = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid sourced MRP for fertilizer {product}") from exc
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f"Invalid sourced MRP for fertilizer {product}")
        return price
    return {
        "urea_rs_per_kg": _price("urea"),
        "dap_rs_per_kg": _price("dap"),
        "mop_rs_per_kg": _price("mop"),
    }


def _get_fertilizer_bag_sizes(fert_prices_df) -> dict[str, float]:
    result = {}
    for product in ("urea", "dap", "mop"):
        rows = fert_prices_df[
            fert_prices_df["fertilizer_id"].astype(str).str.lower() == product
        ]
        if rows.empty:
            raise ValueError(f"No sourced bag size for fertilizer {product}")
        try:
            size = float(rows.iloc[0]["bag_size_kg"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid sourced bag size for fertilizer {product}") from exc
        if not math.isfinite(size) or size <= 0:
            raise ValueError(f"Invalid sourced bag size for fertilizer {product}")
        result[product] = size
    return result
