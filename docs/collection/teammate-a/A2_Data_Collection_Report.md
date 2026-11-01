# A2: Historical Weather (16 Years, 2010–2025) — Data Collection & Methodology Report

**Checklist Item:** `A2` — 10+ yrs rainfall/ET₀ for 36 districts (`processed/district_rainfall_history.csv`)  
**Status:** ✅ **SATISFIED (100% Real Meteorological Telemetry via Open-Meteo Archive API)**  
**Data File in this Folder:** [`district_rainfall_history.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A2_Historical_Weather_10Yrs/district_rainfall_history.csv)  
**Canonical Copy:** [`data/processed/district_rainfall_history.csv`](file:///c:/Users/hp/Downloads/AgriPulse/data/processed/district_rainfall_history.csv)  
**Raw API Cache:** [`data/raw/open_meteo_archive/`](file:///c:/Users/hp/Downloads/AgriPulse/data/raw/open_meteo_archive/) (36 district JSON files, 5,844 daily records each)

---

## 1. Source & Live API Used
* **Provider:** Open-Meteo Historical Weather API (ERA5 / ERA5-Land Reanalysis, ECMWF).
* **Endpoint:** `https://archive-api.open-meteo.com/v1/archive`.
* **Spatial Resolution:** Exact OSM Nominatim geocoded coordinates for each of the **36 canonical Maharashtra districts**.
* **Temporal Coverage:** 16 full calendar years (`2010-01-01` to `2025-12-31`), yielding **5,844 daily records per district** and **210,384 daily meteorological observations** across the state.
* **Volume:** **2,304 rows** in `district_rainfall_history.csv` covering Annual, Kharif, Rabi, and Summer seasons across all 16 years.

---

## 2. Exact API Query Executed
```http
GET https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date=2010-01-01&end_date=2025-12-31&daily=precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max,temperature_2m_min&timezone=Asia/Kolkata
```

---

## 3. Seasonal Aggregation Methodology
Daily weather observations are aggregated into India's standard agricultural seasons and annual totals:
* **`Annual`:** Full calendar year (January 1 to December 31).
* **`Kharif`:** Southwest Monsoon season (June 1 to October 31).
* **`Rabi`:** Winter cropping season (November 1 to February 28/29).
* **`Summer`:** Pre-monsoon / Zaid season (March 1 to May 31).

For each `(district, year, season)` combination:
* **`rainfall_mm`:** Cumulative rainfall ($\sum \text{precipitation\_sum}$).
* **`et0_mm`:** Cumulative FAO-56 Penman-Monteith reference evapotranspiration ($\sum \text{et0\_fao\_evapotranspiration}$).
* **`rainy_days`:** Days with precipitation $\ge 2.5\text{ mm}$ (official IMD threshold for a rainy day).
* **`temp_max_avg_c`:** Mean daily maximum temperature.
* **`temp_min_avg_c`:** Mean daily minimum temperature.

---

## 4. How AgriPulse Uses This Table (Climate Scenarios)
1. **Three Climate Scenarios for Robust Optimization:**
   - **Normal:** Median Kharif rainfall across the 16-year baseline.
   - **Drought:** Dry year ($10\text{th}–20\text{th}$ percentile of rainfall).
   - **Excess:** Wet year ($80\text{th}–90\text{th}$ percentile of rainfall).
2. **Crop Yield Training (`yield_training.csv`):** Supplies historical rainfall, ET₀, rainy days, and temperature regimes directly into the yield regression models.
