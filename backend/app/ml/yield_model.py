"""ML.4 — Gradient Boosting Yield Prediction (Model A Inference).

Loads trained Model A (HistGradientBoostingRegressor) and predicts
yield (t/ha) under the given Scenario conditions.

Implements historical maximum clipping, out-of-range guards, and
hierarchical baseline fallback (ML.3).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.data import loaders
from app.data.resolver import resolve_district
from app.ml.yield_baseline import get_yield_baseline
from app.schemas import Location, Scenario, Season, SourcedValue, YieldPrediction

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = REPO_ROOT / "ml" / "models" / "yield_model_a.joblib"


@lru_cache(maxsize=1)
def load_trained_model() -> dict[str, Any] | None:
    """Load the trained Model A artifact from disk."""
    if not MODEL_PATH.exists():
        logger.warning("Yield model artifact not found at %s; will use hierarchical baseline", MODEL_PATH)
        return None
    try:
        artifact = joblib.load(MODEL_PATH)
        logger.info("Loaded yield model from %s", MODEL_PATH)
        return artifact
    except Exception as exc:
        logger.warning("Failed to load yield model: %s; falling back to baseline", exc)
        return None


def get_district_features(district: str) -> dict[str, Any]:
    """Retrieve static soil, groundwater, irrigation, and fertilizer features for a district."""
    dist = resolve_district(district)

    # 1. Soil
    soil_df = loaders.load_soil_npk()
    soil_row = soil_df[soil_df["district"] == dist]
    if not soil_row.empty:
        r = soil_row.iloc[0]
        n_kg = float(r.get("n_kg_per_ha", 180.0))
        p_kg = float(r.get("p_kg_per_ha", 22.0))
        k_kg = float(r.get("k_kg_per_ha", 280.0))
        ph = float(r.get("ph", 7.2))
        oc = float(r.get("organic_carbon_pct", 0.55))
    else:
        n_kg, p_kg, k_kg, ph, oc = 180.0, 22.0, 280.0, 7.2, 0.55

    # 2. Groundwater
    gw_df = loaders.load_groundwater()
    gw_row = gw_df[(gw_df["district"] == dist) & gw_df["block"].str.contains("District Avg", case=False, na=False)]
    if gw_row.empty:
        gw_row = gw_df[gw_df["district"] == dist]
    if not gw_row.empty:
        g = gw_row.iloc[0]
        gw_cat = str(g.get("category", "Safe"))
        gw_ext = float(g.get("extraction_pct", 65.0))
    else:
        gw_cat, gw_ext = "Safe", 65.0

    # 3. Irrigation
    irr_df = loaders.load_irrigation()
    irr_row = irr_df[irr_df["district"] == dist]
    irr_pct = float(irr_row.iloc[0].get("net_irrigated_area_pct", 30.0)) if not irr_row.empty else 30.0

    # 4. Fertilizer
    fert_df = loaders.load_fertilizer_use()
    fert_row = fert_df[fert_df["district"] == dist]
    fert_use = float(fert_row.iloc[0].get("fertilizer_use_kg_per_ha", 120.0)) if not fert_row.empty else 120.0

    return {
        "district": dist,
        "groundwater_category": gw_cat,
        "groundwater_extraction_pct": gw_ext,
        "soil_n_kg_ha": n_kg,
        "soil_p_kg_ha": p_kg,
        "soil_k_kg_ha": k_kg,
        "soil_ph": ph,
        "organic_carbon_pct": oc,
        "irrigated_pct": irr_pct,
        "fertilizer_use_kg_per_ha": fert_use,
    }


def predict_yield(
    crop_id: str,
    location: Location,
    season: Season,
    conditions: Scenario,
) -> YieldPrediction:
    """Predict yield (t/ha) using Model A with historical max clipping and baseline fallback."""
    district = resolve_district(location.district)
    crop = crop_id.lower().strip()
    szn = season.name if hasattr(season, "name") else str(season)
    szn_title = szn.title().strip()

    baseline = get_yield_baseline()
    base_res = baseline.lookup(district, crop, szn_title)

    artifact = load_trained_model()
    model_used = False
    predicted_yield = base_res.yield_t_per_ha
    out_of_range = False

    if artifact is not None:
        try:
            model = artifact["model"]
            encoder = artifact["encoder"]
            cat_cols = artifact["cat_cols"]
            num_cols = artifact["num_cols"]

            # Context features
            ctx = get_district_features(district)

            # Scenario features
            rf = float(conditions.rainfall_mm or (conditions.season_rain_mm.value if hasattr(conditions.season_rain_mm, "value") else 200.0))
            et0 = float(conditions.et0_mm or 450.0)
            rain_days = int(conditions.rainy_days or 20)
            dry_spell = int(conditions.max_dry_spell_days or 15)
            mean_temp = float(conditions.mean_temp_c or 26.0)
            max_temp = float(conditions.max_temp_c or 34.0)
            heat_stress = int(conditions.heat_stress_days or 5)
            humidity = float(conditions.mean_humidity_pct or 60.0)
            # Estimate departure against 300 mm baseline normal
            departure = round((rf - 300.0) / 300.0 * 100.0, 2)

            feature_dict = {
                "district": district,
                "crop_id": crop,
                "season": szn_title,
                "groundwater_category": ctx["groundwater_category"],
                "season_rainfall_mm": rf,
                "rainfall_departure_pct": departure,
                "rainy_days": rain_days,
                "max_dry_spell_days": dry_spell,
                "mean_temp_c": mean_temp,
                "max_temp_c": max_temp,
                "heat_stress_days": heat_stress,
                "et0_total_mm": et0,
                "mean_humidity_pct": humidity,
                "soil_n_kg_ha": ctx["soil_n_kg_ha"],
                "soil_p_kg_ha": ctx["soil_p_kg_ha"],
                "soil_k_kg_ha": ctx["soil_k_kg_ha"],
                "soil_ph": ctx["soil_ph"],
                "organic_carbon_pct": ctx["organic_carbon_pct"],
                "irrigated_pct": ctx["irrigated_pct"],
                "groundwater_extraction_pct": ctx["groundwater_extraction_pct"],
                "fertilizer_use_kg_per_ha": ctx["fertilizer_use_kg_per_ha"],
            }

            cats_df = pd.DataFrame([{col: feature_dict[col] for col in cat_cols}])
            encoded_cats = encoder.transform(cats_df)

            num_vals = np.array([[feature_dict[col] for col in num_cols]])
            X = np.hstack([encoded_cats, num_vals])

            raw_pred = float(model.predict(X)[0])
            predicted_yield = max(0.05, raw_pred)
            model_used = True

            # Out of range guard
            if rf > 3000 or rf < 0 or max_temp > 50 or min(ctx["soil_ph"], 7.0) < 4.0:
                out_of_range = True

        except Exception as exc:
            logger.warning("Yield model inference failed for %s in %s: %s; using baseline", crop, district, exc)
            predicted_yield = base_res.yield_t_per_ha

    # Apply historical maximum clipping guard
    max_allowed = 1.25 * base_res.max_yield_t_per_ha
    clipped = False
    if predicted_yield > max_allowed:
        predicted_yield = max_allowed
        clipped = True

    final_val = round(float(predicted_yield), 3)

    return YieldPrediction(
        t_per_ha=SourcedValue(
            value=final_val,
            unit="t/ha",
            source="AgriPulse Yield Model A (HistGradientBoostingRegressor)" if model_used else f"DES Historical Baseline ({base_res.tier})",
            as_of="2026",
            status="model" if model_used else "official_dataset",
        ),
        clipped=clipped,
        out_of_training_range=out_of_range,
    )
