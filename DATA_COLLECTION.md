# AgriPulse — Data Collection Guide

> **For:** Teammate A (Environment & Water) and Teammate B (Economics, Crop Agronomy & AI keys)
> **Target state:** Maharashtra (backup: Karnataka). The code will treat the state as a setting, so any state that passes the Step 0 check can be used.

---

## 0. What we are building and why the data matters

AgriPulse tells a farmer **which crops to grow, on how much land, with how much water, fertilizer and money**, so that profit is highest and waste is lowest, even in a drought.

```
Farmer input (location, land, budget, water source)
        │
        ▼
Live data (weather, soil, groundwater, mandi prices)   ← YOU collect / connect these
        │
        ▼
1. Crop classifier ── which crops suit this soil + weather?
2. Yield model ────── how much will each crop produce here?
3. QP optimizer ───── how to split land / water / fertilizer / budget?
                      (run for Normal / Drought / Excess-rain scenarios)
4. AI agent ───────── explains the plan in Marathi / Hindi / English
        │
        ▼
Dashboard (recommended crops, allocation, yield, profit, water & fertilizer saved)
```

| Pipeline stage | Data it needs | Owner |
|---|---|---|
| Crop classifier | Soil N, P, K, pH + temperature, humidity, rainfall | A |
| Yield model | Historical district yields, weather history, fertilizer response | A + B |
| Water constraint | Rainfall (recent + forecast), groundwater, reservoirs, crop water need | A |
| Profit & budget | Mandi prices, cultivation costs, fertilizer & seed prices, MSP | B |
| Season filter | Crop calendar | B |
| AI agent + voice | Groq / Gemini API keys, Whisper | B |

### ⚠️ The #1 rule of this hackathon
**No mock data = no disqualification.** Hard-coded numbers, made-up values or fake JSON get us **disqualified instantly**. Every number must come from an **official dataset** or a **live API**, and we must be able to show where it came from.

---

## 1. Step 0: State data check (both teammates, ~2 hours, do this FIRST)

Before collecting anything in bulk, confirm that Maharashtra has every dataset in a usable form. Tick each item only if the data is:
- **available** (downloadable or reachable by API),
- **district-level** (or finer), and
- **≥ 5 years** of history where history is needed.

| # | Check | Owner | Critical? | ✓ |
|---|---|---|---|---|
| 1 | Open-Meteo forecast + archive return data for 3 Maharashtra district HQs | A | Yes | ☐ |
| 2 | SoilGrids returns pH / nitrogen for those 3 points | A | No (SHC is backup) | ☐ |
| 3 | Soil Health Card N, P, K for Maharashtra districts | A | Yes | ☐ |
| 4 | Groundwater level / block category for Maharashtra (CGWB / India-WRIS / GSDA) | A | Yes | ☐ |
| 5 | Recent district rainfall with % departure (IMD) | A | No (Open-Meteo is backup) | ☐ |
| 6 | Reservoir storage for Maharashtra regions | A | No | ☐ |
| 7 | Agmarknet API returns Maharashtra mandi prices today | B | Yes | ☐ |
| 8 | District-wise crop yield (area, production) for Maharashtra, 10+ years | B | Yes | ☐ |
| 9 | Cost of Cultivation for Maharashtra covers ≥ 6 of our crops | B | Yes | ☐ |
| 10 | Recommended fertilizer doses for our crops (agri university) | B | Yes | ☐ |
| 11 | Crop calendar (sowing/harvest windows) for Maharashtra | B | Yes | ☐ |
| 12 | Groq + Gemini keys work; output in Marathi/Hindi is readable | B | Yes | ☐ |

**Decision rule:** if **more than 2 critical items fail**, switch to **Karnataka** and repeat. Use this same table to qualify any other state later.

---

## 2. Shared rules (both teammates)

1. **Log every source.** Add a row to `data/SOURCES.md` for every file or API:
   `dataset ID | name | URL | publisher | license | download date | notes`
2. **Folder layout**
   ```
   data/
     raw/         ← original downloads, never edited
     processed/   ← cleaned CSVs used by the code
     samples/     ← one real JSON response saved from each API
     SOURCES.md
   ```
3. **File format:** CSV, UTF-8, `snake_case` column names, **unit in the column name**
   (e.g. `modal_price_rs_per_quintal`, `rainfall_mm`, `area_ha`).
4. **API keys:** only in the `.env` file, which is **never committed to GitHub**. Keep the key *names* (no values) in `.env.example`.
5. **For every API, write down:** the exact URL/parameters used, the rate limit, how long a call takes, and what happens when it fails (error code, empty result, timeout).
6. **District names:** sources spell them differently (`Ahmednagar` / `Ahmadnagar` / `Ahilyanagar`, `Beed` / `Bid`, `Raigad` / `Raigarh`). Keep **one canonical list of 36 Maharashtra districts** in `data/processed/districts.csv` with a `name_variants` column. Every other file must join to it.
7. **Don't clean away the truth.** If a value is missing, leave it empty. Never fill it with a guess.

---

## 3. Notes on the dataset we already have (Kaggle "Crop Recommendation")

**Columns:** `N, P, K, temperature, humidity, ph, rainfall, label` (22 crops, ~2,200 rows).

| Column | Unit | Filled live by |
|---|---|---|
| N, P, K | soil nutrient ratio (kg/ha scale) | Soil Health Card (A4) |
| ph | pH | SoilGrids (A3) / Soil Health Card (A4) |
| temperature | °C | Open-Meteo (A1) |
| humidity | % | Open-Meteo (A1) |
| rainfall | mm (period unclear) | Open-Meteo (A1/A2): we must decide the matching period (e.g. seasonal total) |

**Known issues (please read):**
- The dataset is **partly synthetic**. We use it **only to train the classifier**, and we check its results against real district yields (B3).
- **Missing major Maharashtra crops:** no **soybean, sugarcane, jowar, wheat, onion, tur (it has pigeonpeas)**. Teammate B should note in B3 which of these have good real data, so we can decide whether to add them through the yield data.
- **Not relevant for Maharashtra:** apple, coffee, jute. We will filter them out.

---

## 4. Teammate A: Environment & Water

**Your mission:** everything about **weather, soil and water**. Your data decides *which crops can grow* and *how much water the farmer really has*.

### A1. Weather forecast (live API)
- **Source:** Open-Meteo Forecast API, `https://api.open-meteo.com/v1/forecast` (free, **no key**)
- **Specs:** by `latitude`, `longitude`; daily `temperature_2m_max`, `temperature_2m_min`, `precipitation_sum`, `et0_fao_evapotranspiration`; hourly `relative_humidity_2m`; `forecast_days=16`; `timezone=Asia/Kolkata`
- **Test:**
  ```
  https://api.open-meteo.com/v1/forecast?latitude=19.88&longitude=75.34&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration&hourly=relative_humidity_2m&forecast_days=16&timezone=Asia/Kolkata
  ```
- **Why:** gives the classifier its temperature, humidity and rainfall. **ET₀** (water evaporating from soil + plants) is the base of the crop water-need calculation.

### A2. Historical weather, 10+ years (live API)
- **Source:** Open-Meteo Historical API, `https://archive-api.open-meteo.com/v1/archive` (free, no key)
- **Specs:** daily `precipitation_sum`, `et0_fao_evapotranspiration`, `temperature_2m_max/min` for **each district HQ**, `start_date=2010-01-01` to last year
- **Why:** builds our **three climate scenarios**:
  - **Normal** = median monsoon rainfall
  - **Drought** = a dry year (e.g. 10th–20th percentile)
  - **Excess** = a wet year (e.g. 80th–90th percentile)

  The optimizer uses these to find a plan that **stays profitable even in a bad year**. This is our main USP.
- **Deliverable:** `processed/district_rainfall_history.csv` → `district, year, season, rainfall_mm, et0_mm`

### A3. Soil properties (live API)
- **Source:** SoilGrids REST API (ISRIC), `https://rest.isric.org/soilgrids/v2.0/properties/query` (free, no key)
- **Specs:** `lon`, `lat`; properties `phh2o, nitrogen, soc, clay, sand, silt`; depths `0-5cm, 5-15cm, 15-30cm`; value `mean`
- **⚠️ Unit conversions (important):**
  | Property | SoilGrids unit | Convert to |
  |---|---|---|
  | phh2o | pH × 10 | ÷ 10 → pH |
  | nitrogen | cg/kg | ÷ 100 → g/kg |
  | soc | dg/kg | ÷ 10 → g/kg |
  | clay / sand / silt | g/kg | ÷ 10 → % |
- **Limitation:** SoilGrids has **no Phosphorus (P) or Potassium (K)**. Those come from A4. The service is also sometimes slow or down, so note how often it fails.
- **Why:** soil pH and texture (clay/sand) decide which crops suit the land and how well the soil holds water.

### A4. Soil N, P, K (Soil Health Card)
- **Source:** Soil Health Card portal (`soilhealth.dac.gov.in`) / `data.gov.in` (search "Soil Health Card")
- **Specs:** **district-level average** N, P, K (kg/ha) and pH; also the *Low / Medium / High* fertility status if available
- **Why:** fills the **P and K** the classifier needs, and is the backup for pH when SoilGrids is down. It also tells the optimizer how much fertilizer the soil *already* supplies.
- **Deliverable:** `processed/soil_npk_by_district.csv` → `district, n_kg_per_ha, p_kg_per_ha, k_kg_per_ha, ph, source_year`

### A5. Crop water coefficients (FAO-56)
- **Source:** FAO Irrigation and Drainage Paper No. 56, *Crop Evapotranspiration* (official FAO publication: Table 11 stage lengths, Table 12 Kc values)
- **Specs:** per crop: `kc_ini, kc_mid, kc_end`, stage lengths in days (`initial, development, mid, late`), total duration
- **Why:** turns weather into **crop water need**:
  > **Crop water need = Kc × ET₀ − effective rainfall**

  This is a real agronomy formula, so our water numbers are calculated, not guessed. Record the FAO table/page number for every value in `SOURCES.md`.
- **Deliverable:** `processed/crop_water_coefficients.csv`

### A6. District coordinates
- **Source:** OpenStreetMap Nominatim (`https://nominatim.openstreetmap.org/search?q=<district>,Maharashtra&format=json`) or an official district list
- **Specs:** 36 district HQ: `district, hq_name, latitude, longitude`
- **Why:** default map points, and the locations we use to test every API.
- **Deliverable:** add to `processed/districts.csv` (the canonical district list)

### A7. Groundwater level and status ⭐ (water constraint)
- **Sources:**
  - **CGWB "Dynamic Ground Water Resources of India"** assessment (block/taluka category)
  - **India-WRIS** (`indiawris.gov.in`): groundwater levels, including telemetry stations
  - **GSDA Maharashtra** (Groundwater Surveys and Development Agency): observation-well levels
- **Specs:**
  - **depth to water level** (metres below ground level, *m bgl*), pre-monsoon and post-monsoon, latest + 5-year trend
  - **block/taluka category:** `Safe / Semi-critical / Critical / Over-exploited`
  - stage of groundwater extraction (%)
- **Why:** the optimizer must not plan crops that need more water than the ground can give. In an **over-exploited** area we cap the groundwater share strictly, which pushes the plan toward **water-saving crops** like pulses and millets instead of sugarcane. This is a strong real-world impact point for the judges.
- **Deliverable:** `processed/groundwater_by_block.csv` → `district, block, category, extraction_pct, depth_pre_monsoon_m, depth_post_monsoon_m, assessment_year`

### A8. Recent observed rainfall ⭐ (water constraint)
- **Source:** **IMD** district-wise rainfall (actual vs. normal, % departure; weekly/monthly district reports). **Fallback:** Open-Meteo `past_days=92` on the forecast API.
- **Specs:** last 30 / 60 / 90 days rainfall (mm), normal for the same period, % departure
- **Why:** if this season's rain is 40% below normal, the soil and wells are already dry, so the farmer has less water than usual. This makes the water constraint reflect **this year**, not an average year.
- **Note:** IMD data is often published as reports, not an API. Write down exactly how to get it (URL, file type, update frequency).

### A9. Reservoir and canal storage
- **Sources:** **Maharashtra Water Resources Department** dam storage reports; **CWC (Central Water Commission) weekly reservoir bulletin**; India-WRIS reservoir module
- **Specs:** `reservoir, region/district served, live_storage_pct_of_capacity, date`
- **Why:** canal-irrigated farmers depend on dam water. Low storage means a smaller canal share in the water constraint.

### A10. Irrigation source and efficiency
- **Sources:** **Minor Irrigation Census** / district land-use statistics (irrigated area by source); FAO / ICAR irrigation efficiency figures
- **Specs:** per district: irrigated area by `borewell/tubewell, open well, canal, tank`; efficiency % for **flood, sprinkler, drip**
- **Why:** gives sensible defaults when the farmer doesn't know their water details, and powers the **"water saved with drip"** number on the dashboard.

### 💧 How A7–A10 become the water constraint
```
Available water (per season) =
      effective rainfall   (A8 recent  +  A1 forecast  +  A2 scenario)
    + groundwater share    (farmer's borewell input, capped by A7 category)
    + canal share          (A9 reservoir storage, if canal-irrigated)

Crop water need = Σ (Kc × ET₀ − effective rain) × acres     (A5 + A1/A2)

Constraint:  total crop water need  ≤  available water
```
The farmer enters their **own** water source (number of borewells, pump size, canal yes/no). The official area data (A7, A9) **checks and caps** that input.

### ✅ Teammate A checklist
| ID | Item | Status | File | Source logged |
|---|---|---|---|---|
| A1 | Forecast API tested, sample saved | ☐ | `samples/open_meteo_forecast.json` | ☐ |
| A2 | 10+ yrs rainfall/ET₀ for 36 districts | ☐ | `processed/district_rainfall_history.csv` | ☐ |
| A3 | SoilGrids tested + unit conversions noted | ☐ | `samples/soilgrids.json` | ☐ |
| A4 | District N, P, K, pH | ☐ | `processed/soil_npk_by_district.csv` | ☐ |
| A5 | Kc table for all our crops | ☐ | `processed/crop_water_coefficients.csv` | ☐ |
| A6 | 36 districts + coordinates + name variants | ☐ | `processed/districts.csv` | ☐ |
| A7 | Groundwater category + levels | ☐ | `processed/groundwater_by_block.csv` | ☐ |
| A8 | Recent rainfall + % departure method | ☐ | `processed/recent_rainfall.csv` | ☐ |
| A9 | Reservoir storage | ☐ | `processed/reservoir_storage.csv` | ☐ |
| A10 | Irrigation source + efficiency | ☐ | `processed/irrigation_by_district.csv` | ☐ |

---

## 5. Teammate B: Economics, Crop Agronomy & AI

**Your mission:** everything about **money, crops and the AI**. Your data decides *how much profit each plan makes* and *how the agent talks to the farmer*.

### B1. Live mandi prices (live API)
- **Source:** `data.gov.in` → dataset **"Current Daily Price of Various Commodities from Various Markets (Mandi)"** (Agmarknet). **Register for a free API key** on data.gov.in.
- **Specs:** filters `state=Maharashtra`, `district`, `commodity`; fields `market, commodity, variety, arrival_date, min_price, max_price, modal_price` (**₹ per quintal**, 1 quintal = 100 kg)
- **Why:** **revenue = yield × price**. This is the live price that makes our profit numbers real.
- **Note:** not every mandi reports every day. Record how often prices are missing and use the nearest mandi or the last reported date. **Never invent a price.**

### B2. Historical prices (3–5 years)
- **Source:** `agmarknet.gov.in` price reports (commodity-wise, market-wise, date range)
- **Specs:** monthly **modal price** per crop for Maharashtra, 3–5 years
- **Why:** prices go up and down. The QP optimizer uses this **price variation (risk)** and the **market saturation** effect ("if everyone grows onion, the price falls") to avoid risky all-in plans.
- **Deliverable:** `processed/price_history_monthly.csv` → `commodity, district, year, month, modal_price_rs_per_quintal`

### B3. District crop yields (historical)
- **Source:** **DES (Directorate of Economics & Statistics), Ministry of Agriculture**, district-wise crop production statistics, via `data.gov.in` / **UPAg portal** (`upag.gov.in`) / `desagri.gov.in`
- **Specs:** `district, crop, season (Kharif/Rabi/Whole year), year, area_ha, production_tonnes, yield_tonnes_per_ha`, 10+ years
- **Why (three uses):**
  1. **Training data** for the yield model (real, official, not synthetic)
  2. **Sanity bounds:** if the model predicts more than the district's historical max, the code replaces it with the district average
  3. **"Traditional plan" baseline:** the district's current crop mix, which we compare against to show *"AgriPulse saves X% water and earns ₹Y more"*

### B4. Cost of cultivation, itemized ⭐
- **Source:** **DES / CACP "Cost of Cultivation / Production"** data for **Maharashtra** (CACP price policy reports and DES cost-of-cultivation tables)
- **Specs:** per hectare, **per crop**, with each item separate:
  | Item | Column |
  |---|---|
  | Seed | `seed_rs_per_ha` |
  | Fertilizer | `fertilizer_rs_per_ha` |
  | Manure | `manure_rs_per_ha` |
  | Human labour | `human_labour_rs_per_ha` |
  | Bullock labour | `bullock_labour_rs_per_ha` |
  | Machine labour | `machine_labour_rs_per_ha` |
  | Irrigation | `irrigation_rs_per_ha` |
  | Pesticides / insecticides | `pesticide_rs_per_ha` |
  | Interest on working capital | `interest_rs_per_ha` |
  | Totals | `cost_a2_fl_rs_per_ha`, `cost_c2_rs_per_ha` |
- **Why:** **profit = revenue − cost**, and the **budget constraint** ("plan must cost ≤ ₹80,000") needs real costs. The itemized split powers the **cost-breakdown chart** on the dashboard.
- **Note:** this data has a lag of 2–3 years. Record the reference year.

### B5. Fertilizer prices, doses and yield response ⚠️ (highest-risk item)
- **Sources:**
  - **Department of Fertilizers (Govt. of India):** official MRPs for **urea, DAP, MOP** (and common NPK complexes)
  - **State agricultural universities:** **MPKV Rahuri, VNMKV Parbhani, Dr. PDKV Akola, Dr. BSKKV Dapoli** for the **recommended dose of fertilizer (RDF)** per crop (kg N : P₂O₅ : K₂O per ha)
  - **ICAR** fertilizer trials / long-term fertilizer experiments for **yield-vs-dose** results
- **Specs:**
  - prices: `fertilizer, bag_size_kg, mrp_rs, nutrient_pct` (urea 46% N; DAP 18% N + 46% P₂O₅; MOP 60% K₂O)
  - RDF: `crop, n_kg_per_ha, p2o5_kg_per_ha, k2o_kg_per_ha`
  - response: `crop, dose_kg_per_ha, yield_kg_per_ha` (at least 3–4 dose levels per crop)
- **Why:** yield doesn't keep rising with more fertilizer. It rises, flattens, then can fall. We fit this curve:
  > **yield = a + b·f − c·f²**

  This curve is the **"quadratic" in our Quadratic Programming optimizer**. It lets AgriPulse recommend the dose where *extra fertilizer stops paying for itself*, which is how we reduce fertilizer waste.
- **⚠️ Risk:** yield-vs-dose data is the hardest to find. **Start this one first.** If you find only RDF and no response trials, tell the team early so we can plan the fallback.

### B6. MSP (Minimum Support Price)
- **Source:** **CACP** / Ministry of Agriculture MSP announcements
- **Specs:** `crop, year, msp_rs_per_quintal` (Kharif + Rabi crops)
- **Why:** a **price floor and sanity check**. If a live mandi price looks far below MSP, the agent can warn the farmer.

### B7. Crop calendar ⭐
- **Source:** state agricultural universities (above) / ICAR crop calendars / Maharashtra Agriculture Department
- **Specs:** `crop, season (Kharif/Rabi/Summer), sowing_start, sowing_end, harvest_start, harvest_end, duration_days`
- **Why:** AgriPulse must **only recommend crops that can be sown now**. Recommending a Rabi crop in July would embarrass us in the demo.

### B8. Seed rate and seed price
- **Sources:** agri university *package of practices* (seed rate); **Mahabeej** (Maharashtra State Seeds Corporation) price lists
- **Specs:** `crop, seed_rate_kg_per_acre, seed_price_rs_per_kg, variety`
- **Why:** a precise **seed cost** line, so the farmer sees exactly what they must buy.

### B9. Crop name master table (joins everything)
- **Built by you** from all the sources above
- **Specs:** `crop_id, display_name_en, display_name_mr, display_name_hi, kaggle_label, agmarknet_commodity, des_crop_name, season`
  - e.g. `rice` ↔ `Paddy(Dhan)(Common)` ↔ `Rice`; `pigeonpeas` ↔ `Arhar (Tur/Red Gram)(Whole)` ↔ `Arhar/Tur`
- **Why:** every source names crops differently. Without this table, nothing joins.

### B10. AI API keys + language test ⭐
- **Groq** (`console.groq.com`): create an API key
  - test 2–3 chat models: give each the **same sample crop plan** and ask for an explanation in **Marathi, Hindi and English**
  - test **Whisper** (`whisper-large-v3` / `whisper-large-v3-turbo`) with a short **Marathi** and **Hindi** voice clip
- **Google Gemini** (`aistudio.google.com`): create an API key and run the same language test (this is our **backup** if Groq hits its rate limit)
- **Record:** free-tier rate limits (requests per minute/day, tokens per minute), response time, and a **language quality score (1–5)** for each model. A Marathi speaker should judge the score if possible.
- **Why:** the agent explains plans and handles follow-up questions. If Groq fails during judging, the code switches to Gemini automatically.
- **Store keys in `.env` only:**
  ```
  GROQ_API_KEY=
  GEMINI_API_KEY=
  DATA_GOV_IN_API_KEY=
  ```

### ✅ Teammate B checklist
| ID | Item | Status | File | Source logged |
|---|---|---|---|---|
| B1 | Agmarknet API key + Maharashtra test | ☐ | `samples/agmarknet_today.json` | ☐ |
| B2 | 3–5 yrs monthly prices | ☐ | `processed/price_history_monthly.csv` | ☐ |
| B3 | 10+ yrs district yields | ☐ | `processed/district_crop_yields.csv` | ☐ |
| B4 | Itemized cultivation cost | ☐ | `processed/cost_of_cultivation.csv` | ☐ |
| B5 | Fertilizer prices + RDF + response | ☐ | `processed/fertilizer_*.csv` | ☐ |
| B6 | MSP | ☐ | `processed/msp.csv` | ☐ |
| B7 | Crop calendar | ☐ | `processed/crop_calendar.csv` | ☐ |
| B8 | Seed rate + price | ☐ | `processed/seed.csv` | ☐ |
| B9 | Crop name master table | ☐ | `processed/crops_master.csv` | ☐ |
| B10 | Groq + Gemini keys, language test results | ☐ | `samples/llm_language_test.md` | ☐ |
| B11 | District fertilizer consumption (kg/ha) for yield model, see section 5A | ☐ | `processed/fertilizer_use_by_district.csv` | ☐ |
| B12 | Yield training table assembled (section 5A) | ☐ | `processed/yield_training.csv` | ☐ |

---

## 5A. Crop yield training dataset: features for the yield regressor

**Owner:** Teammate B assembles it (B12), using weather and soil data from Teammate A.
**Target (what we predict):** `yield_t_per_ha` (tonnes per hectare).
**One row = one district + one crop + one season + one year.**

### 1. Identity features (from DES yield data, B3)
| Feature | Example | Why |
|---|---|---|
| `district` | Beed | Each district has its own conditions |
| `crop` | Soybean | Each crop yields differently |
| `season` | Kharif / Rabi | Same crop yields differently by season |
| `year` | 2018 | Captures the slow rise in yield over time (better seeds, methods) |
| `area_ha` | 52,000 | Large-area crops are usually well-established in that district |

### 2. Weather features (from Open-Meteo history, A2), the most important group
**Important:** compute these **only for that crop's growing period** (sowing → harvest, from the crop calendar B7), not the whole year.

| Feature | Why |
|---|---|
| `season_rainfall_mm` | Total water from rain |
| `rainfall_departure_pct` | Below or above normal for that district |
| `rainy_days` | Spread-out rain is better than one heavy downpour |
| `max_dry_spell_days` | A long gap without rain damages crops, even when the total rain is normal |
| `mean_temp_c`, `max_temp_c` | Growth speed |
| `heat_stress_days` (days > 35 °C) | Heat damages flowering and grain filling |
| `et0_total_mm` | How much water the crop loses to evaporation |
| `mean_humidity_pct` | Affects pests and disease |

### 3. Soil features (from Soil Health Card A4 and SoilGrids A3)
`soil_n`, `soil_p`, `soil_k`, `soil_ph`, `organic_carbon`, `clay_pct`, `sand_pct`
→ how fertile the soil is and how well it holds water.

### 4. Water and input features
| Feature | Source | Why |
|---|---|---|
| `irrigated_pct` | Irrigation statistics (A10) | Irrigated crops depend less on rain |
| `groundwater_category` | CGWB (A7) | Water stress in that area |
| `fertilizer_use_kg_per_ha` | District fertilizer consumption, FAI / data.gov.in (B11) | Links yield to fertilizer, which the optimizer needs |

### 5. History features (built from the yield data itself)
| Feature | Why |
|---|---|
| `yield_prev_year` | Last year's yield is a strong signal |
| `yield_3yr_avg` | The district's "normal" yield for that crop |

### ⚠️ Mistakes to avoid
1. **Never use `production` as a feature.** Yield = production ÷ area, so the model would be "cheating" and look perfect in testing but fail in real use.
2. **History features must only use past years.** For 2018, `yield_prev_year` must come from 2017, never from 2018 or later.
3. **Split train and test by year, not randomly.** Train on 2010–2019 and test on 2020–2022. This shows how the model predicts a *future* year.
4. **Align weather to the crop season.** Kharif soybean (June–Oct) needs June–Oct rain, not January–December.
5. **Remove impossible rows:** yield = 0, area = 0, or clear typos (e.g. 50 t/ha rice). Note how many rows were removed, and why, in `SOURCES.md`.
6. **Use the canonical district names** (`districts.csv`) so weather, soil and yield rows join correctly.

### Minimum to start training
If time is short, begin with:
`district, crop, season, year, season_rainfall_mm, max_dry_spell_days, mean_temp_c, heat_stress_days, soil_n, soil_p, soil_k, soil_ph, irrigated_pct, yield_3yr_avg` → `yield_t_per_ha`

Add the remaining features later if they improve accuracy.

**Model tip:** gradient boosting (XGBoost, LightGBM, or scikit-learn's `HistGradientBoostingRegressor`) works well on this kind of table and trains on a laptop in seconds.

**Deliverable:** `processed/yield_training.csv`

---

## 6. Sync points, priorities and risks

### Shared file: `crops_master.csv`
One row per crop that **both** teammates fill:
- **B:** names (B9), season and calendar (B7), price (B1/B2), costs (B4), fertilizer (B5), seed (B8)
- **A:** Kc values and duration (A5), water need

### Suggested order
| Priority | Teammate A | Teammate B |
|---|---|---|
| 1 (first hours) | Step 0 checks, A6 district list, A1 + A3 API tests | Step 0 checks, B10 keys, B1 API test, **start B5** |
| 2 | A2 rainfall history, A4 soil NPK, A5 Kc table | B3 yields, B4 costs, B9 crop master |
| 3 | A7 groundwater, A8 recent rain | B2 price history, B7 calendar |
| 4 | A9 reservoirs, A10 irrigation | B6 MSP, B8 seed |

### Known risks: tell the team early if any of these hit
| Risk | Impact | Fallback |
|---|---|---|
| No fertilizer yield-response data (B5) | Quadratic curve can't be fitted | Fit from RDF + published trial results in agri-university papers; flag to the team |
| SoilGrids slow/down (A3) | Missing pH/texture | Soil Health Card (A4) |
| IMD / WRD / GSDA give reports, not APIs (A7–A9) | Can't fetch live | Document the download method + update frequency; refresh before the demo |
| Mandi has no price today (B1) | Missing revenue | Nearest mandi or last reported date (show the date) |
| District spelling mismatches | Joins fail silently | Canonical `districts.csv` with name variants (rule 6) |
| Kaggle dataset missing soybean / sugarcane / jowar | Can't recommend key crops | Check real yield data (B3) for these; team decides |

### Definition of done
- Every dataset ID above has a file, a saved sample (for APIs) and a row in `SOURCES.md`.
- **No value in any file was typed by hand from memory.** Every value traces to a source.
