# A5: Crop Water Coefficients (FAO-56) — Data Collection & Methodology Report

**Checklist Item:** `A5` — Kc table for all our crops (`processed/crop_water_coefficients.csv`)  
**Status:** ✅ **SATISFIED (100% Real FAO Scientific Publication & ICAR Extension)**  
**Data File in this Folder:** [`crop_water_coefficients.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A5_Crop_Water_Coefficients_FAO56/crop_water_coefficients.csv)  
**Canonical Copy:** [`data/processed/crop_water_coefficients.csv`](file:///c:/Users/hp/Downloads/AgriPulse/data/processed/crop_water_coefficients.csv)  
**Raw Source Document:** [`data/raw/fao56/ch6.htm`](file:///c:/Users/hp/Downloads/AgriPulse/data/raw/fao56/ch6.htm) (Official Chapter 6 FAO document)

---

## 1. Official Scientific Reference & Provenance
* **Publication:** Allen, R.G., Pereira, L.S., Raes, D., & Smith, M. (1998). *Crop Evapotranspiration — Guidelines for Computing Crop Water Requirements*, **FAO Irrigation and Drainage Paper No. 56**, Food and Agriculture Organization of the United Nations (FAO), Rome.
* **Official FAO Web Repository:** `https://www.fao.org/3/x0490e/x0490e0b.htm` (Chapter 6: Single Crop Coefficient $K_c$).
* **Exact Tables Extracted via `build_a5_real.py`:**
  - **Table 11:** *Lengths of crop development stages for various planting periods and climatic regions* (days in initial, development, mid-season, and late-season stages).
  - **Table 12:** *Single (time-averaged) crop coefficients, $K_{c}$, and mean maximum plant heights for non-stressed, well-managed crops in subhumid climates* ($K_{c\text{ ini}}$, $K_{c\text{ mid}}$, $K_{c\text{ end}}$).

---

## 2. Crop Matching & Provenance Audit
Every single crop row is explicitly attributed with its `match_type`, `fao56_table12_row`, and `fao56_table11_row_and_region`:
* **Exact FAO-56 Matches (21 crops):** `rice`, `wheat`, `maize`, `jowar` (Sorghum), `bajra` (Millet), `kidneybeans` (Dry beans), `chickpea` (Chick pea), `lentil`, `soybean`, `groundnut`, `cotton`, `sugarcane`, `onion` (dry), `banana`, `grapes`, `watermelon`, `muskmelon` (Cantaloupe), `orange` (Citrus), `papaya`, `coffee`, `apple`.
* **Agronomic Proxies (4 crops):**
  - `pigeonpeas` (Tur) & `mungbean` (Moong) & `blackgram` (Urad) & `mothbeans` (Matki): Pulses mapped to FAO-56 Table 12 "Dry beans / pulses (Vigna / Phaseolus)" with standard Indian semi-arid stage lengths.
* **Indian Horticulture Extensions (4 crops):**
  - `pomegranate`, `mango`, `coconut`, `jute`: Sourced from ICAR / MPKV Rahuri / Dr. BSKKV Dapoli published water requirement bulletins.

---

## 3. Dataset Schema & Metrics
| Column | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| `crop_id` | String | — | Standardized machine-readable crop slug |
| `crop_name` | String | — | Common English and Indian crop title |
| `season` | String | — | Typical cropping season (`Kharif`, `Rabi`, `Perennial`, etc.) |
| `kc_ini` | Float | — | Crop coefficient during initial growth stage |
| `kc_mid` | Float | — | Crop coefficient during mid-season (peak vegetative / flowering) |
| `kc_end` | Float | — | Crop coefficient at harvest / late season |
| `stage_ini_days` | Integer | days | Duration of initial stage |
| `stage_dev_days` | Integer | days | Duration of crop development stage |
| `stage_mid_days` | Integer | days | Duration of mid-season stage |
| `stage_late_days` | Integer | days | Duration of late-season stage |
| `total_duration_days` | Integer | days | Total crop life cycle in days |
| `match_type` | String | — | `exact` (direct FAO-56 row), `proxy`, or `extension` |
| `fao56_table12_row` | String | — | Verbatim row heading in FAO-56 Table 12 |
| `fao56_table11_row_and_region` | String | — | Verbatim row heading & climatic region in FAO-56 Table 11 |
| `note` | String | — | Detailed calculation / range conversion notes |
| `source` | String | — | Source citation |

---

## 4. How the Water Constraint Uses This Table
Net irrigation water requirement ($ET_c$) across the crop lifecycle is computed as:
$$\text{ET}_{c}(t) = K_{c}(t) \times \text{ET}_{0}(t)$$
$$\text{Net Crop Water Need (mm)} = \max\left(0,\; \sum_{t=1}^{\text{duration}} \left(K_{c}(t) \times \text{ET}_{0}(t)\right) - \text{Effective Rainfall}(t)\right)$$
This formula is evaluated dynamically using the Penman-Monteith reference evapotranspiration ($ET_0$) from Open-Meteo (`A1` forecast and `A2` historical baseline).
