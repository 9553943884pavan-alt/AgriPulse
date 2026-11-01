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

    nan = float("nan")  # missing static data -> model sees NaN, never an invented number

    def _num(row, col):
        value = pd.to_numeric(row.get(col), errors="coerce")
        return nan if pd.isna(value) else float(value)

    # 1. Soil
    soil_df = loaders.load_soil_npk()
    soil_row = soil_df[soil_df["district"] == dist]
    if not soil_row.empty:
        r = soil_row.iloc[0]
        n_kg, p_kg, k_kg = _num(r, "n_kg_per_ha"), _num(r, "p_kg_per_ha"), _num(r, "k_kg_per_ha")
        ph, oc = _num(r, "ph"), _num(r, "organic_carbon_pct")
    else:
        n_kg = p_kg = k_kg = ph = oc = nan

    # 2. Groundwater
    gw_df = loaders.load_groundwater()
    gw_row = gw_df[(gw_df["district"] == dist) & gw_df["block"].str.contains("District Avg", case=False, na=False)]
    if gw_row.empty:
        gw_row = gw_df[gw_df["district"] == dist]
    if not gw_row.empty:
        g = gw_row.iloc[0]
        gw_cat = str(g.get("category", "")) or "Unknown"
        gw_ext = _num(g, "extraction_pct")
    else:
        gw_cat, gw_ext = "Unknown", nan

    # 3. Irrigation
    irr_df = loaders.load_irrigation()
    irr_row = irr_df[irr_df["district"] == dist]
    irr_pct = _num(irr_row.iloc[0], "net_irrigated_area_pct") if not irr_row.empty else nan

    # 4. Fertilizer
    fert_df = loaders.load_fertilizer_use()
    fert_row = fert_df[fert_df["district"] == dist]
    fert_use = _num(fert_row.iloc[0], "fertilizer_use_kg_per_ha") if not fert_row.empty else nan

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


def _baseline_source(res) -> str:
    """Source label for a baseline yield; spells out thin history instead of hiding it."""
    label = f"DES Historical Baseline ({res.tier})"
    if res.n_years:
        years = "year" if res.n_years == 1 else "years"
        label += f": median of {res.n_years} DES {years}, latest {res.last_year}"
        if res.n_years < 5:
            label += " - sparse history"
    return label


def preceding_kharif_rain_mm(district: str, analogue_year: int | None) -> float:
    """Kharif (Jun-Oct) rainfall of the analogue crop-year, or NaN when it is not on record.

    Rabi/Summer crops live on stored soil moisture from the monsoon that came before them
    (the same reason the Rabi scenarios are ranked by a Rabi+Kharif water index).
    """
    nan = float("nan")
    if analogue_year is None:
        return nan
    hist = loaders.load_rainfall_history()
    row = hist[
        (hist["district"] == district)
        & (hist["season"] == "Kharif")
        & (hist["year"] == int(analogue_year))
    ]
    return nan if row.empty else float(row.iloc[0]["rainfall_mm"])


def build_feature_dict(district: str, crop: str, szn_title: str, conditions: Scenario) -> dict[str, Any]:
    """Model A input row for one (district, crop, season, scenario).

    Every weather feature comes from the scenario's analogue year; anything missing is NaN
    (never an invented number). Shared by yield inference and SHAP attribution so both see
    exactly the same input.
    """
    ctx = get_district_features(district)
    nan = float("nan")

    def _f(v):
        return nan if v is None else float(v)

    rf_raw = conditions.rainfall_mm
    if rf_raw is None and hasattr(conditions.season_rain_mm, "value"):
        rf_raw = conditions.season_rain_mm.value
    rf = _f(rf_raw)
    # Departure from the district's own mean season rainfall, from the sourced analogue samples.
    samples = [float(x.value) for x in (conditions.all_year_samples or [])]
    if samples and sum(samples) > 0 and rf == rf:
        mean_rf = sum(samples) / len(samples)
        departure = round((rf - mean_rf) / mean_rf * 100.0, 2)
    else:
        departure = nan

    return {
        "district": district,
        "crop_id": crop,
        "season": szn_title,
        "groundwater_category": ctx["groundwater_category"],
        "season_rainfall_mm": rf,
        "rainfall_departure_pct": departure,
        "rainy_days": _f(conditions.rainy_days),
        "max_dry_spell_days": _f(conditions.max_dry_spell_days),
        "mean_temp_c": _f(conditions.mean_temp_c),
        "max_temp_c": _f(conditions.max_temp_c),
        "heat_stress_days": _f(conditions.heat_stress_days),
        "et0_total_mm": _f(conditions.et0_mm),
        "mean_humidity_pct": _f(conditions.mean_humidity_pct),
        "soil_n_kg_ha": ctx["soil_n_kg_ha"],
        "soil_p_kg_ha": ctx["soil_p_kg_ha"],
        "soil_k_kg_ha": ctx["soil_k_kg_ha"],
        "soil_ph": ctx["soil_ph"],
        "organic_carbon_pct": ctx["organic_carbon_pct"],
        "irrigated_pct": ctx["irrigated_pct"],
        "groundwater_extraction_pct": ctx["groundwater_extraction_pct"],
        "fertilizer_use_kg_per_ha": ctx["fertilizer_use_kg_per_ha"],
        "kharif_rain_mm": preceding_kharif_rain_mm(district, conditions.analogue_year),
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

    # The model only knows (crop, season) pairs that exist in the DES training rows. A crop DES
    # reports only as "Whole Year" (onion, ...) has no Rabi weather-window training data, so the
    # sourced district median is used instead of extrapolating the model to an unseen season.
    if artifact is not None and not baseline.has_season(crop, szn_title):
        logger.info("No %s/%s training rows; using DES baseline (%s)", crop, szn_title, base_res.tier)
        artifact = None

    if artifact is not None:
        try:
            model = artifact["model"]
            encoder = artifact["encoder"]
            cat_cols = artifact["cat_cols"]
            num_cols = artifact["num_cols"]

            feature_dict = build_feature_dict(district, crop, szn_title, conditions)
            ctx = feature_dict
            rf = feature_dict["season_rainfall_mm"]
            max_temp = feature_dict["max_temp_c"]

            cats_df = pd.DataFrame([{col: feature_dict[col] for col in cat_cols}])
            encoded_cats = encoder.transform(cats_df)

            num_vals = np.array([[feature_dict[col] for col in num_cols]])
            X = np.hstack([encoded_cats, num_vals])

            raw_pred = float(model.predict(X)[0])
            predicted_yield = max(0.05, raw_pred)
            model_used = True

            # Out of range guard
            if (rf == rf and (rf > 3000 or rf < 0)) or (max_temp == max_temp and max_temp > 50) or (ctx["soil_ph"] == ctx["soil_ph"] and ctx["soil_ph"] < 4.0):
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
            source="AgriPulse Yield Model A (HistGradientBoostingRegressor)" if model_used else _baseline_source(base_res),
            as_of="2026",
            status="model" if model_used else "official_dataset",
        ),
        clipped=clipped,
        out_of_training_range=out_of_range,
    )
