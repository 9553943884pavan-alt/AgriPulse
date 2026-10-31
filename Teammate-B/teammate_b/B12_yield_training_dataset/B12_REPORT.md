# B12 — Crop Yield Training Dataset (Assembled Table)

## Methodology & Feature Engineering
- **Dataset ID:** B12
- **Purpose:** Training dataset for the Yield Regressor (LightGBM/XGBoost/HistGradientBoosting) predicting `yield_t_per_ha`.
- **Row Grain:** 1 row = 1 district + 1 crop + 1 season + 1 year (12,367 rows).
- **Features Assembled (25 total columns):**
  - **Identity:** `state`, `district`, `crop`, `season`, `year`, `area_ha` (DES API).
  - **Season-Aligned Agroclimatology:** `season_rainfall_mm`, `rainfall_departure_pct`, `rainy_days`, `max_dry_spell_days`, `mean_temp_c`, `max_temp_c`, `heat_stress_days`, `et0_total_mm`, `mean_humidity_pct` (Computed strictly over each crop's growing window from daily satellite/reanalysis feeds).
  - **Soil Baseline:** `soil_n_kg_ha`, `soil_p_kg_ha`, `soil_k_kg_ha`, `soil_ph`, `organic_carbon_pct` (Joined from official Soil Health Card database).
  - **Groundwater Stress:** `groundwater_category`, `groundwater_extraction_pct` (Joined from CGWB Dynamic Resources).
  - **Strictly-Past History Features:** `yield_prev_year` (t-1 lag) and `yield_3yr_avg` (rolling average of t-3 to t-1). No future data leakage.
  - **Target Variable:** `yield_t_per_ha` (`production_tonnes` is excluded so the model cannot cheat).
