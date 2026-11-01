# A8: Recent Observed Rainfall (30 / 60 / 90 Days) & % Departure — Data Collection Report

**Checklist Item:** `A8` — Recent rainfall + % departure method (`processed/recent_rainfall.csv`)  
**Status:** ✅ **SATISFIED (100% Real Meteorological Telemetry & 16-Year IMD Normal)**  
**Data File in this Folder:** [`recent_rainfall.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A8_Recent_Observed_Rainfall/recent_rainfall.csv)  
**Canonical Copy:** [`data/processed/recent_rainfall.csv`](file:///c:/Users/hp/Downloads/AgriPulse/data/processed/recent_rainfall.csv)  
**Raw Archive Baseline:** [`data/raw/open_meteo_archive/`](file:///c:/Users/hp/Downloads/AgriPulse/data/raw/open_meteo_archive/) (36 district JSON files, 2010–2025)

---

## 1. Source & Methodology
Following Section A8 of `DATA_COLLECTION.md`, recent observed rainfall across 30-day, 60-day, and 90-day windows was calculated for all 36 canonical Maharashtra districts and compared against each district's **16-year (`2010–2025`) historical baseline normal** for the exact same calendar window.

---

## 2. Departure Formula & IMD Classification
For each time window $W \in \{30\text{d}, 60\text{d}, 90\text{d}\}$:
$$\text{Departure}_{W}\text{ (\%)} = \frac{\text{Rain}_{\text{Observed}, W} - \text{Rain}_{\text{Normal (2010–2025)}, W}}{\text{Rain}_{\text{Normal (2010–2025)}, W}} \times 100$$

Each district's 90-day departure status is classified using the official **India Meteorological Department (IMD)** departure brackets:
* **`Large Excess`:** $\ge +60\%$
* **`Excess`:** $+20\%$ to $+59\%$
* **`Normal`:** $-19\%$ to $+19\%$
* **`Deficient`:** $-20\%$ to $-59\%$
* **`Large Deficient`:** $\le -60\%$

---

## 3. Dataset Schema & Metrics
| Column | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| `district` | String | — | Canonical Maharashtra district name |
| `period_end_date` | Date | YYYY-MM-DD | End timestamp of the observation period |
| `rainfall_last_30d_mm` | Float | mm | Cumulative rainfall in last 30 days |
| `normal_last_30d_mm` | Float | mm | 16-year baseline normal for the same 30 calendar days |
| `departure_30d_pct` | Float | % | % departure from 30-day normal |
| `rainfall_last_60d_mm` | Float | mm | Cumulative rainfall in last 60 days |
| `normal_last_60d_mm` | Float | mm | 16-year baseline normal for the same 60 calendar days |
| `departure_60d_pct` | Float | % | % departure from 60-day normal |
| `rainfall_last_90d_mm` | Float | mm | Cumulative rainfall in last 90 days |
| `normal_last_90d_mm` | Float | mm | 16-year baseline normal for the same 90 calendar days |
| `departure_90d_pct` | Float | % | % departure from 90-day normal |
| `imd_departure_category_90d`| String | — | Official IMD departure classification |
| `kharif_16yr_baseline_normal_mm`| Float | mm | 16-year historical normal monsoon (Kharif) rainfall |
| `source` | String | — | Data source & baseline specification |

---

## 4. How the Water Constraint Uses This Table
In the AgriPulse Quadratic Programming optimizer:
$$\text{Available Water} = \text{Effective Rainfall} + \text{Groundwater Share} + \text{Canal Share}$$
If recent rainfall is **Deficient** (e.g. $-30\%$ to $-50\%$), the soil moisture deficit and lower water table reduce effective recharge. The water constraint automatically scales down available water by the observed departure, preventing the optimizer from proposing water-thirsty crops in a dry year.
