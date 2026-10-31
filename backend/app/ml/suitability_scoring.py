"""ML.4b — Crop Suitability Scoring & SHAP Feature Attribution.

Computes:
  1. Suitability score: predicted_yield / district_normal_yield (3-year baseline).
  2. Classification: good (>=1.05), average (0.90 - 1.05), poor (<0.90).
  3. Feature attribution: SHAP TreeExplainer decomposing predicted yield into
     effects on yield (converted to quintals/acre).
  4. Top 3 factors mapped to standardized contract feature codes.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

import numpy as np
import pandas as pd
import shap

from app.data.resolver import resolve_district
from app.ml.yield_baseline import get_yield_baseline
from app.ml.yield_model import get_district_features, load_trained_model, predict_yield
from app.schemas import (
    Location,
    Scenario,
    Season,
    Suitability,
    SuitabilityFactor,
    SuitabilityLabel,
)

logger = logging.getLogger(__name__)

FEATURE_UNITS: dict[str, str] = {
    "season_rainfall_mm": "mm",
    "rainfall_departure_pct": "%",
    "rainy_days": "days",
    "max_dry_spell_days": "days",
    "mean_temp_c": "°C",
    "max_temp_c": "°C",
    "heat_stress_days": "days",
    "et0_total_mm": "mm",
    "mean_humidity_pct": "%",
    "soil_n_kg_ha": "kg/ha",
    "soil_p_kg_ha": "kg/ha",
    "soil_k_kg_ha": "kg/ha",
    "soil_ph": "pH",
    "organic_carbon_pct": "%",
    "irrigated_pct": "%",
    "fertilizer_use_kg_per_ha": "kg/ha",
}

VALID_FEATURES = set(FEATURE_UNITS.keys())


@lru_cache(maxsize=1)
def get_shap_explainer() -> shap.TreeExplainer | None:
    """Create and cache SHAP TreeExplainer for Model A."""
    artifact = load_trained_model()
    if artifact is None:
        return None
    try:
        model = artifact["model"]
        return shap.TreeExplainer(model)
    except Exception as exc:
        logger.warning("Failed to initialize TreeExplainer: %s", exc)
        return None


def suitability(
    crop_id: str,
    location: Location,
    season: Season,
    conditions: Scenario,
) -> Suitability:
    """Calculate crop suitability score, rating label, and top contributing SHAP factors."""
    district = resolve_district(location.district)
    crop = crop_id.lower().strip()
    szn = season.name if hasattr(season, "name") else str(season)
    szn_title = szn.title().strip()

    # 1. Predicted yield & baseline normal
    yp = predict_yield(crop, location, season, conditions)
    pred_val = float(yp.t_per_ha.value)

    baseline = get_yield_baseline()
    normal_val = baseline.get_3yr_normal_yield(district, crop, szn_title)
    if normal_val <= 0:
        normal_val = max(0.1, pred_val)

    ratio = pred_val / normal_val
    score = round(float(ratio), 3)

    # 2. Determine rating label
    if ratio >= 1.05:
        label: SuitabilityLabel = "good"
    elif ratio >= 0.90:
        label = "average"
    else:
        label = "poor"

    # 3. SHAP attribution
    top_factors: list[SuitabilityFactor] = []
    fallback_used = False

    artifact = load_trained_model()
    explainer = get_shap_explainer()

    if artifact is not None and explainer is not None:
        try:
            encoder = artifact["encoder"]
            cat_cols = artifact["cat_cols"]
            num_cols = artifact["num_cols"]
            ctx = get_district_features(district)

            rf = float(conditions.rainfall_mm or (conditions.season_rain_mm.value if hasattr(conditions.season_rain_mm, "value") else 200.0))
            et0 = float(conditions.et0_mm or 450.0)
            rain_days = int(conditions.rainy_days or 20)
            dry_spell = int(conditions.max_dry_spell_days or 15)
            mean_temp = float(conditions.mean_temp_c or 26.0)
            max_temp = float(conditions.max_temp_c or 34.0)
            heat_stress = int(conditions.heat_stress_days or 5)
            humidity = float(conditions.mean_humidity_pct or 60.0)
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

            # SHAP values: shape (1, num_features)
            shap_vals = explainer.shap_values(X)[0]
            feature_names = list(cat_cols) + list(num_cols)

            candidates: list[tuple[float, SuitabilityFactor]] = []
            for name, shap_v in zip(feature_names, shap_vals):
                if name in VALID_FEATURES:
                    val = float(feature_dict[name])
                    unit = FEATURE_UNITS.get(name, "")
                    # Convert t/ha effect to quintals/acre: 1 t/ha = 10 q/ha = 4.047 q/acre
                    effect_q = round(float(shap_v) * 4.04686, 2)
                    direction: Literal["up", "down"] = "up" if effect_q >= 0 else "down"

                    candidates.append((
                        abs(effect_q),
                        SuitabilityFactor(
                            feature=name,  # type: ignore[arg-type]
                            value=round(val, 2),
                            unit=unit,
                            effect_quintal_per_acre=effect_q,
                            direction=direction,
                        )
                    ))

            candidates.sort(key=lambda t: t[0], reverse=True)
            top_factors = [factor for _, factor in candidates[:3]]

        except Exception as exc:
            logger.warning("SHAP attribution failed for %s in %s: %s; using heuristic factors", crop, district, exc)
            fallback_used = True

    if not top_factors:
        fallback_used = True
        # Heuristic factors fallback
        top_factors = [
            SuitabilityFactor(
                feature="season_rainfall_mm",
                value=round(float(conditions.rainfall_mm or 250.0), 1),
                unit="mm",
                effect_quintal_per_acre=round((ratio - 1.0) * 1.5, 2),
                direction="up" if ratio >= 1.0 else "down",
            ),
            SuitabilityFactor(
                feature="soil_ph",
                value=7.2,
                unit="pH",
                effect_quintal_per_acre=0.35,
                direction="up",
            ),
            SuitabilityFactor(
                feature="irrigated_pct",
                value=35.0,
                unit="%",
                effect_quintal_per_acre=0.20,
                direction="up",
            ),
        ]

    return Suitability(
        score=score,
        label=label,
        top_factors=top_factors,
        fallback_used=fallback_used,
    )
