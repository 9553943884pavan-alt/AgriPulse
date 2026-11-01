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
from app.ml.yield_model import build_feature_dict, load_trained_model, predict_yield
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


# Features that change between analogue seasons.  Categorical and district
# context features (soil, irrigation, groundwater) are identical for every
# season of one district/crop, so their Shapley value against a same-district
# background is exactly zero and they are held fixed.
WEATHER_FEATURES: tuple[str, ...] = (
    "season_rainfall_mm",
    "rainfall_departure_pct",
    "rainy_days",
    "max_dry_spell_days",
    "mean_temp_c",
    "max_temp_c",
    "heat_stress_days",
    "et0_total_mm",
    "mean_humidity_pct",
    "kharif_rain_mm",
)
SHAP_ADDITIVITY_TOL_T_HA = 1e-3


def _nan_to_none(v):
    return None if v is None or pd.isna(v) else float(v)


def _background_feature_dicts(
    district: str, crop: str, szn_title: str, conditions: Scenario
) -> list[dict]:
    """Model rows for every recorded season of this district (same crop/season).

    Built with ``build_feature_dict`` from the same Open-Meteo history that
    defines the scenarios, so background and explained row are constructed
    identically.
    """
    from app.data.loaders import load_rainfall_history

    hist = load_rainfall_history()
    rows = hist[(hist["district"] == district) & (hist["season"] == szn_title)]
    out: list[dict] = []
    for _, r in rows.iterrows():
        rain = _nan_to_none(r.get("rainfall_mm"))
        sc = conditions.model_copy(update={
            "analogue_year": int(r["year"]),
            "rainfall_mm": rain,
            "season_rain_mm": conditions.season_rain_mm.model_copy(update={"value": rain}),
            "et0_mm": _nan_to_none(r.get("et0_mm")),
            "rainy_days": _nan_to_none(r.get("rainy_days")),
            "max_dry_spell_days": _nan_to_none(r.get("max_dry_spell_days")),
            "mean_temp_c": _nan_to_none(r.get("mean_temp_c")),
            "max_temp_c": _nan_to_none(r.get("max_temp_c")),
            "heat_stress_days": _nan_to_none(r.get("heat_stress_days")),
            "mean_humidity_pct": _nan_to_none(r.get("mean_humidity_pct")),
        })
        out.append(build_feature_dict(district, crop, szn_title, sc))
    return out


def _weather_shap(
    artifact: dict,
    feature_dict: dict,
    district: str,
    crop: str,
    szn_title: str,
    conditions: Scenario,
) -> tuple[list[str], np.ndarray] | None:
    """Exact Shapley values of the trained model's prediction over weather features.

    ``shap.TreeExplainer`` mis-parses HistGradientBoosting *native categorical*
    splits (``crop_id``/``district`` are categorical in Model A), which made it
    return the same attribution for every crop and broke additivity.  This
    uses ``shap.explainers.Exact`` on the model's own ``predict`` with the
    district's recorded seasons as the background distribution.
    """
    model = artifact["model"]
    encoder = artifact["encoder"]
    cat_cols = list(artifact["cat_cols"])
    num_cols = list(artifact["num_cols"])

    def to_x(d: dict) -> np.ndarray:
        cats = encoder.transform(pd.DataFrame([{c: d[c] for c in cat_cols}]))
        nums = np.array([[d[c] for c in num_cols]], dtype=float)
        return np.hstack([cats, nums])[0]

    weather = [c for c in WEATHER_FEATURES if c in num_cols]
    if not weather:
        return None
    w_idx = [len(cat_cols) + num_cols.index(c) for c in weather]

    background = _background_feature_dicts(district, crop, szn_title, conditions)
    if not background:
        return None
    x_fg = to_x(feature_dict)
    bg = np.array([to_x(d)[w_idx] for d in background], dtype=float)

    def f(z: np.ndarray) -> np.ndarray:
        X = np.repeat(x_fg[None, :], len(z), axis=0)
        X[:, w_idx] = z
        return model.predict(X)

    masker = shap.maskers.Independent(bg, max_samples=len(bg))
    explanation = shap.explainers.Exact(f, masker)(x_fg[w_idx][None, :])
    values = np.asarray(explanation.values[0], dtype=float)
    base = float(np.ravel(explanation.base_values)[0])
    pred = float(model.predict(x_fg[None, :])[0])
    if abs(base + values.sum() - pred) > SHAP_ADDITIVITY_TOL_T_HA:
        logger.warning("SHAP additivity failed for %s/%s (%.4f vs %.4f)", crop, district, base + values.sum(), pred)
        return None
    return weather, values


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
    # Model SHAP may only explain a yield the model actually produced.  Crops
    # whose yield is the DES baseline (e.g. no training rows for this season)
    # get no model factors: an empty list with fallback_used=True is honest.
    model_used = yp.t_per_ha.status == "model"

    if artifact is not None and model_used:
        try:
            feature_dict = build_feature_dict(district, crop, szn_title, conditions)
            attribution = _weather_shap(artifact, feature_dict, district, crop, szn_title, conditions)
            if attribution is None:
                raise ValueError("no historical background seasons for SHAP")
            feature_names, shap_vals = attribution

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
        # No SHAP attribution available: report none rather than invent factor values.
        fallback_used = True

    return Suitability(
        score=score,
        label=label,
        top_factors=top_factors,
        fallback_used=fallback_used,
    )
