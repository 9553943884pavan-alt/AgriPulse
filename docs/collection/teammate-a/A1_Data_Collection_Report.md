# A1: Weather Forecast API — Data Collection & Verification Report

**Checklist Item:** `A1` — Forecast API tested, sample saved  
**Status:** ✅ **SATISFIED**  
**Data File in this Folder:** [`open_meteo_forecast.json`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A1_Weather_Forecast/open_meteo_forecast.json)  
**Canonical Copy:** [`data/samples/open_meteo_forecast.json`](file:///c:/Users/hp/Downloads/AgriPulse/data/samples/open_meteo_forecast.json)

---

## 1. Source & Endpoint Details
* **Provider:** Open-Meteo Forecast API (ECMWF IFS / GFS Global Forecast Models)
* **Base URL:** `https://api.open-meteo.com/v1/forecast`
* **Authentication:** Free for non-commercial/open-source use (`No API Key required`)
* **Rate Limit:** `10,000` requests/day, `600` requests/minute
* **Average Response Latency:** `~180–350 ms` per request (supports batching up to 50 comma-separated coordinates per call)

## 2. Exact Query Tested (Chhatrapati Sambhajinagar HQ, Maharashtra)
```http
GET https://api.open-meteo.com/v1/forecast?latitude=19.88&longitude=75.34&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration&hourly=relative_humidity_2m&forecast_days=16&timezone=Asia/Kolkata
```

## 3. Variables Extracted & Units
| Variable | API Parameter | Unit | Purpose in AgriPulse Pipeline |
| :--- | :--- | :--- | :--- |
| Daily Max Temp | `temperature_2m_max` | `°C` | Crop classifier thermal suitability & heat-stress alerts (`> 35°C`) |
| Daily Min Temp | `temperature_2m_min` | `°C` | Frost / cold-spell detection for Rabi crops |
| Daily Rainfall | `precipitation_sum` | `mm` | Effective rainfall input for water constraint & spray scheduling |
| Reference Evapotranspiration | `et0_fao_evapotranspiration` | `mm/day` | FAO-56 Penman-Monteith base water demand ($\text{Crop Water Need} = K_c \times ET_0 - \text{Rain}_{\text{eff}}$) |
| Relative Humidity | `relative_humidity_2m` | `%` | Crop classifier feature + fungal/pest outbreak risk indicator |

## 4. Failure & Edge-Case Handling
* **SSL / Timeout Handling:** When querying in bulk across 757 Indian districts, batch size is capped at `25–50` coordinate pairs per request with exponential backoff retry (`3` retries, `15s` timeout).
