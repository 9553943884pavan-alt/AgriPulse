# ML & AI SPECS: Models, Optimizer and Agent

**Owner:** ML & AI lead. The ML and agent code lives inside the backend tree (`backend/app/ml`, `backend/app/agent`) so it deploys as one service, but the **ML lead writes and owns it**. Ownership rule when something breaks across the boundary: whoever owns the file with the failing line fixes it; if that is unclear, the person whose test went red first opens the pull request and tags the other. The contract in `backend/app/schemas.py` is changed only with all three agreeing.

**Works with:** [`backend/SPECS.md`](../backend/SPECS.md) (hosts this code; data layer and API) and [`frontend/SPECS.md`](../frontend/SPECS.md) (shows these results)
**Stack:** Python · pandas · scikit-learn (gradient boosting) · SHAP · SciPy · CVXPY · LangGraph · **Sarvam AI** (the only model provider) · pytest

**Status:** ⬜ Not started · 🟨 In progress · ✅ Done · ⛔ Blocked · ➖ Dropped
Update the **Status** column in the same pull request that does the work.

---

## 1. Ground rules

- **No mock, hardcoded or dummy data.** Models train only on official datasets in `data/processed/`; live values come only from the backend services. Breaking this rule means instant disqualification.
- **Scoring this part supports:** *Technical Depth (20)*: yield model, climate scenarios, water need, QP optimizer · *AI Reasoning / Agentic (25)*: LangGraph agent, self-correction, memory, grounding · *Impact / USP (25)*: drought-safe plans, water and fertilizer saved.
- **Code rules:**
  1. **No invented numbers in code.** No default prices, costs, yields or crops. Missing data → the crop is excluded and the reason is returned. A **declared** default is different from a hidden one: an assumed irrigation method or borewell yield is allowed because it appears in `defaults_used` with its basis, carries an `assumption` badge and is listed in section 7A. A silent `price = 3000` is not.
  2. **Every value that reaches the farmer keeps its source** (`SourcedValue`, backend section 5.1).
  3. **No data leakage.** Never use `production` as a feature; history features use past years only; train/test split is by year.
  4. **Fixed seeds** (`random_state=42`) for every split and model.
  5. **Paths with `pathlib`**, console output ASCII-safe (`Rs.` instead of `₹` in logs).
  6. **Every experiment gets a report** in `ml/reports/` (section 9) and its model file is saved with a metadata JSON.
  7. **Tests ship with the code.**
- **Decisions already made:** no Kaggle classifier (suitability from real data, section 3) · optimizer = Quadratic Programming (CVXPY) with an LP baseline · hybrid agent: fixed graph for the main path, the LLM decides only at specific points · plain code handles API failures, retries, unit conversion, validation and impossible-yield clipping; the agent handles profile extraction, follow-up questions, fixing infeasible plans and explanations.
- **Decided (D1, D2): Sarvam AI only.** One Indian provider for everything the agent needs: reasoning, speech-to-text and text-to-speech. No Gemini, no Groq, no OpenAI. Reasons: the models are built for Indian languages (so Marathi and Hindi quality is the point, not an afterthought), one key and one bill, free credits cover the hackathon, and using an Indian provider fits a product for Indian farmers. **The risk of a single provider** is that there is no second vendor to fail over to, so the fallbacks in section 8.6 matter more: retry on a different Sarvam model, then the template answer, which needs no model at all. A plan is always produced, with or without a model.

---

## 2. Layout and data

```
ml/
├── data_prep/       cleaning scripts (ML.2)
├── experiments/     training scripts, one folder per experiment
├── models/          saved models + metadata JSON (**git-lfs, never git-ignored**: an ignored file is not in the repo, so it never reaches the deployed host)
├── reports/         EXP_<NN>_<name>.md (section 9)
└── SPECS.md
backend/app/ml/      runtime code the backend imports: suitability, yields, scenarios, water, fertilizer, optimizer
backend/app/agent/   LangGraph graph, tools, memory, prompts
```

**Training and lookup data (all official):**
| File | Rows / coverage | Used for |
|---|---|---|
| `yield_training.csv` | ~12,367 rows, 1997–2014, 34 districts, weather + soil + irrigation + groundwater + lag features | Yield model (ML.4) |
| `district_crop_yields.csv` | DES area, production, yield | Crop filter (ML.1), baseline (ML.3), traditional plan (OPT.3) |
| `district_climate_2010_2025.csv`, `district_rainfall_history.csv` | Season rainfall, ET₀, temperature | Climate scenarios (ML.5) |
| `crop_calendar.csv` | Sowing and harvest windows | Season filter, season-aligned features |
| `crop_water_coefficients.csv` | Kc, stage lengths | Crop water need (ML.7) |
| `fertilizer_rdf.csv`, `fertilizer_prices.csv`, `fertilizer_use_by_district.csv` | University recommended doses, MRPs, actual district fertilizer use | Fertilizer plan (ML.8) |
| `cost_of_cultivation.csv`, `seed.csv`, `msp.csv`, `price_history_monthly.csv` | Costs, seed, MSP, monthly prices | Optimizer inputs and risk |
| `groundwater_by_block.csv`, `reservoir_storage.csv`, `irrigation_by_district.csv`, `recent_rainfall.csv` | Water context | Water budget |

---

## 3. Crop suitability (real data only, no Kaggle classifier)

Suitability is built from official data in three steps:

1. **Filter (ML.1).** Keep a crop only if it is (a) grown in the district (DES area above a threshold in recent years, per season), (b) sowable now (crop calendar) and (c) its water need fits the available water (ML.7 + water budget).
2. **Score (ML.4b).** The yield model predicts each remaining crop's yield under **this season's conditions**. Suitability = predicted yield ÷ the crop's normal yield in the district (3-year average). Above 1 means better than usual conditions. Labels: `good` ≥ 1.05, `average` 0.9–1.05, `poor` < 0.9.
3. **Explain (ML.4b).** SHAP (`TreeExplainer`) on the same yield model gives each factor's effect on the predicted yield. The top 3 factors per crop go to the API as `suitability.top_factors`, converted to quintals per acre. **`feature` is a fixed code**, never free text: one of `season_rainfall_mm`, `rainfall_departure_pct`, `rainy_days`, `max_dry_spell_days`, `mean_temp_c`, `max_temp_c`, `heat_stress_days`, `et0_total_mm`, `mean_humidity_pct`, `soil_n_kg_ha`, `soil_p_kg_ha`, `soil_k_kg_ha`, `soil_ph`, `organic_carbon_pct`, `irrigated_pct`, `fertilizer_use_kg_per_ha`. The **frontend** owns the sentence for each code in all three languages (one i18n key per code, with the value and direction filled in), so "why this crop" needs no LLM call and is translated like every other label. The agent may mention the same factors in its own explanation, but the card does not depend on it.

The optimizer then makes the final choice by profit, risk and water; suitability only narrows and explains the candidates. If the yield model is weak for a crop (out-of-time error above the threshold in ML.4), that crop falls back to the district's historical average yield, `fallback_used = true`, and the answer says so. SHAP shows what the model relied on, not true cause and effect, and the README says that.

---

## 3A. Which season a plan is for (rule; fixes the "season from the month only" v1 mistake)

`plan_season(today)` is plain code driven by `crop_calendar.csv`, never by the month alone:

1. A crop is **sowable** if `today` falls in `[sowing_start - 7 days, sowing_end]` of its calendar row. Rows are per crop *and* season: `jowar` (Rabi) and `jowar_kharif` are separate rows.
2. A crop is **opening soon** if `sowing_start` is within the next 21 days. It is included and flagged `opens_on`, so a farmer planning on 31 Oct still sees wheat (sowing opens 1 Nov).
3. The **plan season** is the season of that sowable + opening-soon set. When two seasons overlap in the window, both appear and each crop carries its own `season`; there is no single season for the whole plan.
4. If nothing is sowable or opening (a gap between seasons), the agent says so and offers the **next** season with its opening date, instead of returning an empty plan.

Worked example, the date these specs were written: **31 Oct 2026 gives Rabi.** Sowable: jowar (Rabi, window closes today), chickpea, lentil, maize (Rabi), grapes. Opening soon: wheat (1 Nov), onion (Rabi, 15 Nov). **Not** soybean, cotton, tur, bajra or Kharif rice: their windows closed in July. Every example in these specs and in the API contract uses this Rabi set, because a Kharif example cannot be reproduced on the demo day.

**Long-duration crops** (sugarcane 365 d, banana 330 d, orange 240 d, pomegranate 180 d): per-acre profit is also divided by `duration_days / 365`, so a 12-month crop is compared with a 4-month crop **per acre per year**. The response carries `duration_days` and `profit_rs_per_acre_per_year` beside the season figure, and the dashboard says the crop "occupies the land for N months". Without this, sugarcane wins every single-season comparison by construction.

---

## 4. Yield model

| Item | Spec |
|---|---|
| **Target** | `yield_t_per_ha` (converted to quintals per acre only at the API boundary) |
| **Row** | One district + crop + season + year |
| **Features** | Identity: district, crop, season, year · Weather over the crop's own growing window: season rainfall, rainfall departure, rainy days, longest dry spell, mean and max temperature, heat-stress days (> 35 °C), ET₀ total, humidity · Soil: N, P, K, pH, organic carbon · Water and inputs: irrigated %, groundwater category and extraction %, fertilizer use · History: previous-year yield, 3-year average (past years only) |
| **Never use** | `production`, `area_ha` as a way to derive the target, anything from the target year or later |
| **Two models, one shipped** | The lag features (`yield_prev_year`, `yield_3yr_avg`) have **no value for 2026**, because the DES yield series ends in 2014. So **model A (shipped)** is trained *without* lag features and is the only model used at inference, and **model B (reference)** adds the lags and exists only to show in EXP_02 how much signal they carry. Shipping model A closes the "what do we feed the lag at inference" hole. |
| **Shipped model training span** | Model A is retrained on **all** years (1997-2014) after the metrics are read off the time split. Reported metrics always come from the time-split run, never from the all-years fit, and the report states both. |
| **Cleaning (ML.2)** | Remove aggregate rows ("Total foodgrain", "Pulses total", "Other …"), impossible yields (e.g. Jowar 14.6 t/ha, near-zero values), mixed units (coconut in nuts); report counts per reason |
| **Split** | By year: train on early years, validate on the next, test on the latest years (for example train 1997–2008, validate 2009–2011, test 2012–2014); also check on 2010–2025 climate for the scenario use |
| **Models** | Baseline: hierarchical median lookup, district → state → crop (ML.3). Main: gradient boosting (`HistGradientBoostingRegressor` or LightGBM) (ML.4) |
| **Metrics** | Out-of-time MAE, RMSE, R², WAPE overall **and per crop**; per-crop table to find weak crops (the v1 XGBoost looked good overall but failed per crop) |
| **Guards** | Clip predictions to the district's historical maximum for that crop and flag it; inputs outside the training range are flagged |
| **Coverage: 34 of 36 districts** | The two with no DES crop data are **Mumbai City** and **Mumbai Suburban** (urban, no agricultural statistics). They are **not planable**: the API returns `DISTRICT_NOT_AGRICULTURAL` with a plain message, the map greys them, and no scenario row is built for them. `districts.csv` carries `is_agricultural_district`, so one flag drives all three parts. ML.5 therefore builds scenarios for the **34 agricultural districts**, not 36. |
| **Data limits to state honestly** | Yield data ends in 2014; soil, irrigation and groundwater are one value per district (see section 9, honest limits) |

---

## 5. Climate scenarios (analogue years, not per-feature percentiles)

A scenario is **one real historical year**, not a mix of percentiles. Taking the 10th percentile of each feature separately would build a year that never happened, for example the driest rainfall together with the mildest heat.

For each district and season, over the single weather series 1997-2025 (`ml/data_prep/fetch_weather.py`, see section 2):

1. Rank the years by the **season water index**. Kharif, Summer and Whole Year use that season's rainfall. **Rabi uses `0.5 x Rabi rainfall + 0.5 x the preceding Kharif rainfall`,** because a Rabi crop lives on soil moisture and reservoir water stored during the monsoon. Ranking Rabi on its own small rainfall would make the three scenarios nearly identical, which is exactly the failure this rule prevents.
2. **Drought** = the year at the 10th percentile of that index, **Normal** = the median year, **Excess** = the 90th percentile year. The response carries the year actually used (`analogue_year: 2015`), so every scenario is auditable and every feature combination is one that really occurred.
3. The scenario carries **all** of that year's season features (rainfall, rainy days, longest dry spell, mean and max temperature, heat-stress days, ET0, humidity) exactly as recorded.
4. **Probability weights** default to 0.2 / 0.6 / 0.2. They are a stated modelling choice (section 7A), not a forecast. If the rain observed so far this season is already below the drought analogue, the weights shift toward Drought and the response says so.
5. The **risk matrix** uses **all 29 years**, not the three scenarios: three points cannot estimate a covariance.

**One weather source.** Everything above, and every weather feature used in training, comes from the Open-Meteo ERA5 archive 1997-2025, aggregated by `ml/data_prep/build_yield_training.py` with one definition per feature (rainy day >= 2.5 mm, heat-stress day > 35 C, dry spell = longest run of days under 2.5 mm, ET0 = FAO-56 Penman-Monteith sum). The old split (Teammate B 1997-2014 from one pipeline, Teammate A 2010-2025 from another, differing by up to 597 mm on the same district-year) is gone, so the model is no longer trained on one definition and run on another.

**There is no yield ground truth after 2014**, so no error metric can be computed for 2015-2025. Those years are used **only** to build scenarios and to check that live feature values fall inside the training range; a value outside it is flagged `out_of_training_range` on the prediction.

**Recent rainfall has one owner.** The live Open-Meteo call (`past_days=92`) is the source for "rain so far this season". `recent_rainfall.csv` is a dated snapshot used **only** when that live call fails, and it is then labelled `cached` with its own date.

---

## 6. Water, crop water need and fertilizer

**Water budget** (inputs from the backend services, formula owned here). It is computed **per scenario**, because the rain term differs by scenario, so the API carries one `WaterBudget` per scenario.
```
available water (m3, scenario s) = effective rain(s) + groundwater share + canal share
  effective rain(s)  = (rain already observed this season + 16-day forecast + remaining rain of analogue year s)
                       x EFFECTIVE_RAIN_FACTOR x area
  groundwater share  = farmer capacity x CATEGORY_CAP[district groundwater category]
  canal share        = CANAL_DUTY x area x (reservoir live storage % / 100), only when canal_access is true
```

*Farmer capacity.* `FarmProfile` carries `borewell_count` and, when the farmer knows them, `borewell_yield_lph` and `pump_hours_per_day`. Capacity = count x yield x hours x season days. **When the farmer does not know**, the agent does not keep asking: code uses the district median borewell yield from the Minor Irrigation Census and marks the value `assumption`. `water_source = null` is treated as **rainfed**, the safe case, and the answer says so.

*Groundwater category per district.* CGWB data is by block, but a location resolves to a district, so the plan uses the **"(District Avg)" row** of `groundwater_by_block.csv` that Teammate A already provides. The individual block rows appear on the map and in the district context, and the response states that the category is a district average, not the farmer's own block.

*Canal.* `canal_access` is the farmer's statement; we have no command-area boundaries. It only decides whether the canal term is non-zero, it is capped by the live storage of the reservoirs serving that district, and the term is labelled `farmer_input`.

**Constants are listed in section 7A with their status.** `EFFECTIVE_RAIN_FACTOR = 0.75` and the category caps (Safe 1.0, Semi-critical 0.7, Critical 0.4, Over-exploited 0.15 of farmer capacity) are **modelling assumptions** until a citation is added to `SOURCES.md`. Every value they produce is returned with `status: "assumption"` and the dashboard shows that badge. They are never presented as measured data.

**Crop water need (ML.7)** per crop, stage and scenario
```
need (mm) = Σ over stages ( Kc × ET₀ − effective rain )⁺  ÷  irrigation efficiency
```
Efficiency by method (flood, sprinkler, drip) comes from `irrigation_by_district.csv`. Need in m³ per acre = mm × 4.047.

**Fertilizer plan (ML.8)**
- **No response curve.** The earlier `fertilizer_response.csv` was generated from a formula, not measured in field trials, so it was removed (see `docs/data_reports/DATA_FIXES.md`). Published trials found by web search report only a few treatments per paper and cannot be assembled into a real dose-response table.
- Dose per crop = the university **recommended dose of fertilizer (RDF)** from `fertilizer_rdf.csv` (N, P₂O₅, K₂O kg per ha), converted to fertilizer bags and priced with the official MRPs in `fertilizer_prices.csv`. The dose is fixed before the optimizer runs, so the problem stays convex.
- **Two different savings, two different names.** `fertilizer_saved_pct` (the dashboard headline, `impact.versus = "traditional"`) compares the RDF cost of the **recommended** mix with the RDF cost of the **Traditional** mix on the same land, so it means the same thing as `water_saved_pct`. `fertilizer_vs_district_use_pct` is a **separate, optional** figure comparing the plan's N+P+K per hectare with the district average use (B11); it is `null` when district use is already below the RDF, never a 0 that looks like a real saving.
- **Cost precedence, so no line is counted twice.** One cost per acre per crop is assembled in this order, and the response shows each line with its own source: **fertilizer** = RDF dose x current MRP (this *replaces* the DES 2022-23 fertilizer line); **seed** = seed rate x Mahabeej price from `seed.csv` (this *replaces* the DES 2022-23 seed line); **every other line** (manure, human / bullock / machine labour, irrigation, pesticide, interest) comes from DES/CACP 2022-23. `total_rs` is the sum of exactly these lines. The two replaced DES lines are returned separately as `superseded`, so the farmer and the judges can see what changed.
- **Dose to bags to rupees.** The RDF is in kg of nutrient (N, P2O5, K2O). Code converts it to the three products in `fertilizer_prices.csv` in a fixed order: all P2O5 from DAP (46% P2O5, which also supplies 18% N), the remaining N from urea (46% N), all K2O from MOP (60% K2O). Cost = bags x MRP. The response carries the nutrient kg **and** the bag count, so a farmer can actually buy it.
- If a real dose-response dataset is found later, a curve can be added as an extension; it needs real plot data with source citations.

---

## 7. Optimizer

Decision variable `xᵢ` = acres of crop `i`.

```
maximize   Σ_s p_s · Σ_i m(i,s) · xᵢ      expected profit over Drought / Normal / Excess
         − λ · xᵀ Σ x                     risk: Σ = covariance of per-acre profit across historical years and price history
         − Σ_i γᵢ · xᵢ²                   market saturation (small for one farm)
subject to Σ xᵢ ≤ L                         land
           Σ costᵢ(f*) · xᵢ ≤ B             budget (seed, fertilizer at the RDF, labour, irrigation, pesticide, interest)
           Σ water(i,s*) · xᵢ ≤ W(s*)       water in the chosen safety scenario s*
           xᵢ ≤ DIVERSIFICATION_CAP · L   diversification; see the rule below
           xᵢ ≥ 0
```
`m(i,s)` = yield(i,s) × **expected harvest price** − cost per acre.

**The diversification cap adapts to the number of eligible crops**, so it can never make the problem infeasible or force 100% of one crop silently:
`n = 1` cap 1.0 (and the answer says only one crop is eligible and why) - `n = 2` cap 0.80 - `n >= 3` cap 0.65. If the cap still makes the problem infeasible, it is the **first** constraint the relaxation ladder (section 8.4a) lifts, and the response records that.

**Expected harvest price (prices are for today, profit is realised at harvest).** A single live quote would be the wrong multiplier for a yield harvested months later. For each crop:
1. `harvest_month` = sowing date + `duration_days` from the crop calendar.
2. `seasonal_ratio` = the median, across the years available in the real monthly history, of (that crop's price in the harvest month) / (its price in the current month) for the same year.
3. `expected_harvest_price = live price today x seasonal_ratio`, floored at the MSP where an MSP exists for the crop.
The response carries `price` (today, live), `seasonal_ratio`, `expected_harvest_price` and the number of years the ratio came from, so the farmer sees that the profit uses a harvest-time price and where the adjustment came from. When a crop has **fewer than 3 years** of history for that month pair, `seasonal_ratio = 1.0`, the status is `assumption`, and the answer says the price was not adjusted.

**Per-year profit samples for the risk matrix.** Yield comes from the model applied to each historical year's weather (1997-2025), so a yield exists for every year even though observed yields stop in 2014. Price comes from the real monthly history for the harvest month of that year; for years before the price history starts, the crop's own price series is used at its earliest available year and the sample is marked. The number of usable year samples per crop is reported with the risk matrix, and a crop with fewer than 5 samples carries no risk term of its own (its variance is taken from its crop group). **Keep it convex:** Σ positive semi-definite (add a tiny ridge), never multiply two decision variables, fertilizer dose fixed before solving. Solver: CVXPY with Clarabel or OSQP.

**Every constant the optimizer and the models use is listed in section 7A**, each with its value, its status (`measured` from a dataset, or `choice` made by us) and where it came from. The "no invented numbers" rule in section 1 is about **data values** (prices, yields, costs, rainfall): those must always come from a source. Modelling parameters are allowed, but only when they are declared here, visible in the response and never presented as measurements.

**Four strategies on the same inputs**
| Strategy | Definition |
|---|---|
| **Traditional** | The district's current crop mix from DES area shares, **restricted to crops of the plan season and to crops that have a real price**, then scaled to the farmer's land. It is reported as the farmer's realistic status quo, so it is **not** forced to satisfy the budget or water constraints: when it exceeds them the response says which limit it breaks and by how much (`traditional_exceeds: ["water"]`). The comparison is then honest: "your usual mix would need 11,800 m3, you have 7,600". It is never presented as a feasible plan |
| **LP max-profit** | SciPy HiGHS, expected profit only, with **exactly the same** land, budget, water (same safety scenario) and diversification constraints as the QP. Identical constraints are what makes the required test `lambda = 0 reproduces the LP result` meaningful |
| **QP balanced** | The QP above with λ from the farmer's `risk_appetite` (`safe` high, `balanced` medium, `max_profit` ≈ 0) |
| **QP drought-safe** | The QP with the water limit taken from the **Drought** scenario |

**Outputs per strategy:** allocations, profit in each scenario, expected profit, worst-case profit, water and fertilizer used, cost, binding constraints, solver status and time.
**Impact vs Traditional:** water saved %, fertilizer saved %, drought-year profit difference.
**Infeasibility report (OPT.4):** which constraints are violated or binding and by how much (land, budget, water, cap), so the agent can decide what to relax. Infeasible plans are **never** silently replaced by an even split.

---

## 7A. Modelling constants (declared, not hidden)

| Constant | Value | Status | Basis / what must still be done |
|---|---|---|---|
| `SCENARIO_PERCENTILES` | P10 / P50 / P90 | choice | Common practice for dry / normal / wet analogue years |
| `SCENARIO_WEIGHTS` | 0.2 / 0.6 / 0.2 | choice | A default, **not** a forecast. Shifts toward Drought when the season so far is below the drought analogue |
| `RABI_WATER_INDEX` | 0.5 Rabi rain + 0.5 preceding Kharif rain | choice | Rabi depends on stored moisture; to be checked against district reservoir filling |
| `EFFECTIVE_RAIN_FACTOR` | 0.75 | assumption | Needs a citation (FAO-56 effective-rainfall method) in `SOURCES.md` before the demo |
| `CATEGORY_CAP` | Safe 1.0, Semi-critical 0.7, Critical 0.4, Over-exploited 0.15 | assumption | Needs a CGWB / GSDA citation. Shown with an `assumption` badge until then |
| `CANAL_DUTY` | m3 per acre per season for canal commands | assumption | From the Maharashtra WRD duty tables; not yet sourced |
| `DIVERSIFICATION_CAP` | 1.0 / 0.80 / 0.65 for n = 1 / 2 / >= 3 | choice | Risk spreading; first constraint relaxed if infeasible |
| `RISK_LAMBDA` | safe 1.0, balanced 0.3, max_profit 0.0 | choice | Calibrated so that `safe` visibly lifts worst-case profit on the demo profiles; recorded in EXP_04 |
| `SATURATION_GAMMA` | 0 for a single farm | choice | Market saturation is negligible for one farm. Non-zero only in a future village / FPO mode, and then it must be fitted from the price history |
| `SUITABILITY_LABELS` | good >= 1.05, average 0.9-1.05, poor < 0.9 | choice | Presentation thresholds on the yield ratio, not agronomic classes |
| `RAIN_DAY_MM` | 2.5 mm | measured | IMD definition of a rainy day |
| `HEAT_STRESS_C` | 35 C | choice | Common threshold for flowering damage; to be checked per crop |
| `PSD_RIDGE` | 1e-6 x trace | choice | Numerical only, so the risk matrix stays solvable; no effect on the result |
| `MIN_PRICE_YEARS` | 3 for a seasonal ratio, 5 for a risk term | choice | Below this the figure is not trustworthy, so it is not used |
| `DEMO_DISTRICTS` | Jalgaon, Pune, Ahilyanagar (backup Nashik) | choice | Chosen from the real data: see section 9A |

Any value in this table that is still `assumption` at demo time appears in the "honest limits" slide and carries an `assumption` badge in the UI.

---

## 8. Agent (LangGraph)

### 8.1 Flow
```
START → route (new plan / follow-up / question about the plan)
  → extract_profile → (ask_missing ↺ end turn) → gather_data (tools in parallel)
  → (no real data for any crop → explain what is missing)
  → recommend_crops → predict_yield (3 scenarios) → optimize (4 strategies) → check_feasibility
  → (relax_constraint ↺ optimize, max 3 tries) → explain → grounding_check → respond
```
`answer_from_memory` handles questions about the current plan; `respond` streams the result and saves memory.

### 8.2 State
`thread_id` · `profile` (FarmProfile) · `location` · `data` (services output as SourcedValues) · `candidates` · `scenario_yields` · `strategies` · `feasibility` · `relaxations[]` · `explanation` · `trace[]` · `language`.

### 8.3 Tools (each wraps a backend service or ML function; plain code, tested)
`get_location` · `get_weather` · `get_soil` · `get_water_budget` · `get_prices` · `get_costs` · `recommend_crops` (ML.1, ML.4b) · `predict_yield` (ML.4, ML.6) · `optimize_plan(strategy, scenario, risk)` · `compare_strategies`.

### 8.4 LLM calls (at most 4 per plan)
| Node | LLM job | Output |
|---|---|---|
| `extract_profile` | Turn the farmer's sentence into a `FarmProfile` (structured output). Plain code then normalizes units and number words: guntha / acre / hectare, "70 हजार" → 70000, "५ एकर" → 5. The agent **never guesses** a number the farmer did not say | `FarmProfile`, `missing[]` |
| `ask_missing` | One short question in the farmer's language for the first missing required field | `question` event |
| (`relax_constraint` is **not** an LLM call any more, see 8.4a) | | |
| `explain` / `answer_from_memory` | Explain the plan in mr / hi / en using only tool outputs; answer follow-ups from stored state | `explanation` |

### 8.4a The relaxation ladder is code, not an LLM decision

Letting the LLM pick a relaxation cost up to 3 extra calls and made the result unpredictable. The ladder is now deterministic, tried in this fixed order until the plan is feasible, and every step is logged in the trace and explained in words by the single `explain` call:

1. Lift the diversification cap to 1.0.
2. Plant less land: reduce the planned area to what the budget allows, keeping the land the farmer owns unchanged.
3. Drop the most water-hungry crop and re-solve.
4. Move the water limit from the safety scenario to the Normal scenario, and say clearly that the plan is then not drought-safe.

If it is still infeasible after step 4, the response is a **plan with no allocation**: `feasible: false`, `allocations: []`, the full `infeasibility` payload (which constraint, by how much), and an explanation of what the farmer would need (for example "with 5 acres you would need at least Rs. 62,000; with Rs. 70,000 you can plant 4.1 acres"). The frontend has a defined state for this; it is never an empty screen.

**LLM budget: at most 3 calls per plan.** `extract_profile` (1), `explain` (1), plus at most one retry of `explain` when the grounding check fails. `route` and `ask_missing` are rule-based: `route` looks at whether the required profile fields are already known and whether the message contains a number or a changed fact, and `ask_missing` uses a translated template per field. With a 15 s provider timeout this keeps the worst case inside the latency target.

**Model order (all Sarvam):** `SARVAM_CHAT_MODEL` first, and on an error or a 15 s timeout the next model in `SARVAM_FALLBACK_MODELS`, then the template answer. Model ids come from Teammate B's B10 test and live in `.env`, never in code, so a renamed model is a config change. **Language:** the reply language equals the farmer's detected language unless they change it.

### 8.5 Memory
LangGraph checkpointer on SQLite, keyed by `thread_id`, storing profile, last plan inputs and the message list. A follow-up such as "what if I only have ₹50,000?" passes through `extract_profile` with the changed fact only, and re-runs the plan from `gather_data` (cached data is reused, so it is fast).

### 8.6 Guards
- **Grounding check:** every number in the answer must appear in the tool outputs. The comparison is defined, not approximate: the checker normalises Devanagari digits to ASCII, strips Indian digit grouping (`1,00,000` -> `100000`), expands the number words the prompts allow (`hazar` / `lakh` / `crore`), and then matches each number against the tool values **in the units the answer uses** (quintals per acre, rupees, acres, m3), allowing the rounding the prompt permits (2 significant decimals, or the nearest rupee for money). A number that matches nothing fails the check. On failure, retry once; if it fails again, use the **template explanation**. A test injects a wrong number, and another test writes the same answer in Marathi with Devanagari digits, and both must behave correctly.
- **No-LLM fallback:** if every provider fails, return the template explanation in the farmer's language. The demo never shows an empty answer.
- **Strict output validation:** reuse the v1 idea: JSON schemas for every LLM output, every crop covered, no extra crops, length limits.
- **Latency:** the trace streams every step; target warm plan under 5 s end to end.

### 8.7 Languages
Explanations in Marathi, Hindi and English. Native-speaker review of the prompts and 10 sample answers per language before the demo. Speech-to-text and text-to-speech are handled by the backend (Sarvam); the agent receives text and a language code.

---

## 9. Evaluation and reports

| Item | Spec |
|---|---|
| **Report per experiment** | `ml/reports/EXP_<NN>_<name>.md` with: overview, dataset and shape, model and features, hyperparameters, split and seed, metrics (per crop for yield), feature importance / SHAP, artifacts (model path, script path, figures), findings and next steps |
| **Experiments planned** | EXP_01 yield baseline (ML.3) · EXP_02 gradient-boosting yield model with SHAP (ML.4, ML.4b) · EXP_03 fertilizer plan and savings vs district use (ML.8) · EXP_04 optimizer comparison on saved real profiles (OPT.3) |
| **Optimizer tests** | Land, budget, water and cap are never exceeded · λ = 0 reproduces the LP result · QP drought-safe never exceeds the drought water limit · PSD check on Σ · infeasible inputs produce a report, not a plan |
| **Agent tests** | 10 sentences per language → correct profile · missing budget asks for the budget · infeasible case ends feasible and explained · follow-up re-runs with one change · injected wrong number fails grounding · all-LLMs-down returns the template answer |
| **Honest metrics (DD.5)** | Show the real out-of-time yield results and state **all** of these limits in the deck, the README and the in-app "limits" panel: (1) yield data ends in 2014, so the model is validated on 2012-2014; (2) 34 of 36 districts are planable, Mumbai City and Mumbai Suburban have no agricultural data; (3) SHAP is model attribution, not causation; (4) **soil, irrigation and groundwater are one value per district**, so two farmers in the same district get the same predicted yield even with different wells, and the farmer's own soil test changes the suitability filter but not the yield model; (5) costs are DES/CACP **2022-23** compared against a 2026 budget, with no inflation adjustment; (6) scenario probabilities are fixed defaults, not a forecast; (7) prices are today's quotes adjusted by a historical seasonal ratio, not a forecast of the harvest price; (8) the Traditional plan is a district average, not this farmer's own practice; (9) the water category caps and the effective-rain factor are assumptions until sourced; (10) long-duration crops are compared per acre per year, not per season |

---

## 9A. Demo districts, and what a "thin market day" means

**The problem in one sentence:** Agmarknet mandis do not report every crop every day. A district may publish prices for 15 crops on Tuesday and 3 on Wednesday (a holiday, no auction, or simply no arrivals). Because a crop with no real price is **excluded** rather than given an invented one, a bad day can leave the optimizer with too few crops, or none. That would be a poor moment to discover live on stage.

**Three defences, in order:**
1. **Price fallback chain** (backend SVC.5): today's district quote, then any district in the state in the last 7 days, then the nearest reporting mandi, then the last real cached quote with its date. Only when a crop has *never* had a real quote is it excluded.
2. **Pick districts that report richly.** From the 19,361 real price rows now in `price_history_monthly.csv`, the per-district crop coverage is known, so the demo uses districts at the top of that list, not the bottom.
3. **Warm the cache on demo morning** (QA.3): run each demo profile once, so even a dead upstream serves real cached prices.

**Chosen demo districts**, each picked for a different story and all with wide price coverage:

| District | Priced crops | Rabi crops | Groundwater | Irrigated | Why this one |
|---|---|---|---|---|---|
| **Jalgaon** | 20 | 11 | **Semi-critical, 78.6% extraction** (the most stressed district average in the state) | 34.6% | The water story: the groundwater cap bites, so the drought-safe plan visibly differs from the max-profit plan |
| **Pune** | **22** (joint best) | 13 | Safe, 63.2% | 38.6%, 24.5% canal | The canal story and the richest data, so nothing is missing on stage |
| **Ahilyanagar** | 21 | 13 | Semi-critical, 76.8% | 32.8% | The follow-up story ("what if I had less money?"): many crops to switch between |
| *Nashik (backup)* | 21 | 12 | Safe, 65.4% | 33.4% | Spare, in case a demo district has a quiet market day |

**Do not demo in** Ratnagiri (only 2 priced crops), Gadchiroli (7), or Bhandara / Gondia / Hingoli (9). They work in the product, but a live demo there risks a very short crop list.

**Honest note for the deck:** no *district average* in Maharashtra is Critical or Over-exploited; those categories appear at **block** level. The demo therefore says "Semi-critical district, with over-exploited blocks inside it", which is what the CGWB data actually shows.

---

## 10. Interfaces with the backend (signatures to implement)

Stubs are merged first (backend C.3) so the backend and frontend can proceed.
```python
def candidate_crops(profile, location, season, water) -> tuple[list[Candidate], list[ExcludedCrop]]
def predict_yield(crop_id, location, season, conditions) -> YieldPrediction          # t/ha + clipped flag
def suitability(crop_id, location, season, conditions) -> Suitability                # score, label, top_factors, fallback_used
def build_scenarios(location, season) -> list[Scenario]                              # drought / normal / excess + weights + all-year samples
def crop_water_need(crop_id, season, scenario, efficiency) -> WaterNeed              # mm and m3 per acre
def fertilizer_plan(crop_id, fertilizer_prices) -> FertilizerPlan                   # RDF kg N/P2O5/K2O per acre, product bags, cost
def optimize(strategy, inputs: OptimizerInputs) -> StrategyResult
def compare_strategies(inputs: OptimizerInputs) -> list[StrategyResult]              # the four strategies + impact
```
Types are the Pydantic models in `backend/app/schemas.py`. Every function returns values with the source information the backend needs for `SourcedValue`.

---

## 11. Tasks

### 11.1 Data and yield model
| ID | Task | Done when | Status |
|---|---|---|---|
| ML.1 | Candidate crop filter: grown in the district ∩ sowable now ∩ water-feasible | Never suggests apple / coffee / jute; covers soybean, sugarcane, jowar, wheat, onion | ✅ |
| ML.2 | Clean `yield_training.csv`: aggregate rows, impossible yields, units | Cleaning report with counts per reason | ⬜ |
| ML.3 | Yield baseline: hierarchical median lookup | Out-of-time MAE reported (EXP_01) | ⬜ |
| ML.4 | Yield model: gradient boosting, time-based split, clipped to district max | Beats ML.3 per crop, or ML.3 stays primary for that crop (EXP_02) | ⬜ |
| ML.4b | Suitability score and SHAP on the ML.4 model; fallback for weak crops | Score + top factors for every candidate; SHAP contributions add up to the prediction | ⬜ |
| ML.5 | Climate scenarios per district (P10 / P50 / P90, weights, all-year samples) | Scenario table for all 36 districts | ⬜ |
| ML.6 | Scenario yields: yield per crop per scenario | 3 yields per candidate crop | 🟨 |
| ML.7 | Crop water need per stage and scenario | Matches a hand-checked example | ✅ |
| ML.8 | Fertilizer plan: RDF dose per crop, priced with official MRPs, saving vs district use (no response curve) | Dose, cost and saving per crop; savings use only real district data (EXP_03) | ✅ |
| ML.9 | Experiment reports for ML.3, ML.4 / ML.4b, ML.8 | One report per experiment in `ml/reports/` | ⬜ |

### 11.2 Optimizer
| ID | Task | Done when | Status |
|---|---|---|---|
| OPT.1 | LP baseline (HiGHS) with land, budget, water, cap | Constraints never exceeded | ✅ |
| OPT.2 | QP (CVXPY) as in section 7, λ from `risk_appetite` | λ = 0 gives the LP result; PSD check | ✅ |
| OPT.3 | Four strategies and comparison on the same inputs | Each returns profit per scenario, worst case, water, fertilizer, cost (EXP_04) | ✅ |
| OPT.4 | Infeasibility report | The agent can read it and propose a fix | ✅ |
| OPT.5 | Impact metrics vs Traditional | Water saved, fertilizer saved, drought-year profit difference | ✅ |

### 11.3 Agent
| ID | Task | Done when | Status |
|---|---|---|---|
| AG.1 | Sarvam client: chat, speech-to-text and text-to-speech behind one module, with the model fallback order, timeouts and a recorded rate-limit budget. One `SARVAM_API_KEY` | Fallback tested by forcing a model error; no other provider appears anywhere in the code | ✅ |
| AG.2 | Tools wrapping services and ML functions | Each tool has a test | ✅ |
| AG.3 | Profile extraction and normalization | 10 sentences each in mr / hi / en extracted correctly | ✅ |
| AG.4 | Ask-missing loop | Missing-budget sample asks for the budget | ✅ |
| AG.5 | Graph with the fixed main path and SSE trace events | End-to-end run on a real sample | ✅ |
| AG.6 | Self-correction (relax and re-optimize, max 3, logged) | Infeasible case ends feasible and explained | ✅ |
| AG.7 | Memory (SQLite checkpointer) and follow-ups | "What if ₹50,000?" test passes | ✅ |
| AG.8 | Explanations in mr / hi / en from tool outputs only, using Sarvam | A Marathi speaker reviews 10 real answers per language and signs off in `ml/reports/language_review.md` | ✅ |
| AG.9 | Grounding check | Injected wrong number fails the check | ✅ |
| AG.10 | No-model template fallback: the plan is written from the optimizer result by code, in all three languages. This is the safety net for a single-provider stack | Demo never shows an empty answer, tested with the Sarvam key removed | ✅ |

### 11.4 Delivery
| ID | Task | Done when | Status |
|---|---|---|---|
| QA.3 | Demo script: 3 farmer stories using the districts chosen in section 9A, **Jalgaon** (groundwater-stressed), **Pune** (canal, richest data) and **Ahilyanagar** (follow-up question), with **Nashik** as the spare. Each written out as profile → expected screens → spoken lines, warmed into the cache on demo morning, and rehearsed 3× with the whole team | Recorded run under 3:00, with each story timed, and a dry run done with the network to data.gov.in blocked | ⬜ |
| DD.5 | README final setup steps, architecture diagram, honest metrics | Fresh clone runs following the README | ⬜ |
| DD.6 | 5–7 slide deck (problem, solution, architecture, agent, results, impact) | Reviewed by all | ⬜ |

---

## 12. Lessons from the old prototype (v1)
**Re-create:** TreeSHAP with a check that baseline + contributions equals the model output · yield lookup hierarchy (district → state → crop) as baseline and sanity bound · 65% diversification cap · strict validation of LLM output.
**Do not repeat:** XGBoost yield model with `area` / `production` features (circular leakage; R² collapsed on real tests) · coconut yields in nut counts mixed with tonnes · season from the month only · Kaggle classifier (partly synthetic, missing the main Maharashtra crops, suggested apple / coffee / jute) · an LP that silently fell back to an even land split · hidden defaults for cost, price and yield.
