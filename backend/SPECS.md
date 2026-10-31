# Backend SPECS: Data Layer, Services and API

**Owner:** Teammate A. Note that `backend/app/ml` and `backend/app/agent` sit in this tree but are **written and owned by the ML lead**; everything else here is Teammate A's. Whoever owns the file with the failing line fixes it; if that is unclear, the person whose test went red first opens the pull request and tags the other.

**Works with:** [`frontend/SPECS.md`](../frontend/SPECS.md) (consumes this API) and [`ml/SPECS.md`](../ml/SPECS.md) (models, optimizer and agent that this backend hosts)
**Stack:** Python · FastAPI · Pydantic v2 · httpx (async) · SQLite · pytest · ruff

**Status:** ⬜ Not started · 🟨 In progress · ✅ Done · ⛔ Blocked · ➖ Dropped
Update the **Status** column in the same pull request that does the work.

---

## 1. Ground rules

- **No mock, hardcoded or dummy data.** Every number comes from a live API or an official dataset, with its source and date. Breaking this rule means instant disqualification.
- **Scoring this part supports:** *Live Demo Robustness (30)*: cached real data when an API fails, fast responses, clear errors · *Technical Depth (20)*: async data layer, caching, water budget.
- **Code rules (checked in every pull request):**
  1. **No invented numbers in code.** No default prices, costs, yields or fallback crop lists. If real data is missing, the crop is **left out** and the response says why (`excluded_crops`).
  2. **Every value carries its source:** `SourcedValue = {value, unit, source, source_url, as_of, status}`, `status` ∈ `live | cached | official_dataset | model | computed | farmer_input | assumption`. There is no `mock` status: `assumption` is for a declared modelling constant (ml/SPECS.md section 7A), never for invented data.
  3. **Old real data is fine, labelled.** If a live API fails, serve the last real response as `cached` with its `as_of` date.
  4. **Keys only in `.env`.** Never in code, reports, samples or commits. `.env.example` lists the names.
  5. **`pathlib` paths relative to the file.** No `C:\Users\...`.
  6. **Fixed random seeds** (`random_state=42`) wherever randomness is used.
  7. **Tests ship with the code.** Saved real API responses in `data/samples/` may be used in tests, never at runtime.
- **Decided: Sarvam AI is the only model provider** (reasoning, speech-to-text, text-to-speech). No Gemini, no Groq. The browser voice stays only as a last-resort fallback for text-to-speech. **Open: D4 hosting** (default **Hugging Face Spaces** with a persistent volume, plus a warm-up ping before judging).

---

## 2. Responsibilities and layout

The backend does four things: (1) load and serve the official data, (2) fetch live data and cache it, (3) host the ML models, optimizer and the LangGraph agent (written by the ML lead), (4) expose the API the frontend uses.

```
backend/
├── app/
│   ├── main.py            FastAPI app, CORS, middleware (timing, request id, size limits)
│   ├── config.py          settings from .env (pydantic-settings)
│   ├── schemas.py         all Pydantic models = the API contract (section 5)
│   ├── core/              http client, TTL + SQLite cache, timing, errors, units
│   ├── data/              loaders for data/processed/*.csv + district resolver
│   ├── services/          location, weather, soil, water, prices, costs, speech
│   ├── pipeline.py        run_plan(profile) -> PlanResult
│   ├── api/               routers: agent, plan, speech, context, sources, health
│   ├── ml/ ...            (owned by ML lead) models, scenarios, optimizer
│   └── agent/ ...         (owned by ML lead) LangGraph graph, tools, memory, prompts
├── tests/
├── requirements.txt
└── SPECS.md
```

### Environment variables (`.env.example`)
| Name | Used for |
|---|---|
| `STATE` | Pilot state, default `Maharashtra` |
| `DATA_GOV_IN_API_KEY` | Agmarknet mandi prices, CWC reservoirs |
| `SARVAM_API_KEY` | **The only model provider**: agent reasoning, speech-to-text and text-to-speech |
| `SARVAM_CHAT_MODEL`, `SARVAM_STT_MODEL`, `SARVAM_TTS_MODEL` | Model ids from the B10 test, so a renamed model is a config change, not a code change |
| `SARVAM_FALLBACK_MODELS` | Comma-separated chat models to try if the first errors or times out |
| `CORS_ORIGINS` | Allowed frontend origins |
| `CACHE_DB_PATH` | SQLite file for cached real responses and agent memory |

---

## 3. Phase 0: Setup and data intake

| ID | Task | Owner | Done when | Status |
|---|---|---|---|---|
| P0.1 | **Rotate the leaked data.gov.in key first**, then `git init`, push to GitHub, protect `main` (pull requests only). The old key is in the teammates' reports and in their Drive copies, so pushing before rotating puts it in git history forever | Key owner, then ML | New key issued and old one revoked **before** the first push; direct pushes to `main` blocked | ⬜ |
| P0.2 | **Data intake**: put the teammates' Drive folders into `data/` and `docs/data_reports/` using the checklist below | ML | Checklist all ticked | ⬜ |
| P0.3 | Scrub the key text out of every report (`<DATA_GOV_IN_API_KEY>`), including the Drive originals | A + B | `check_data.py` finds no key in any tracked file | ⬜ |
| P0.4 | Root `.gitignore` and `.env.example` (`SARVAM_API_KEY`, the three Sarvam model ids, `SARVAM_FALLBACK_MODELS`, `DATA_GOV_IN_API_KEY`, `STATE`, `CORS_ORIGINS`, `CACHE_DB_PATH`) | A | `.env` ignored, names listed, no Gemini or Groq key anywhere | ⬜ |
| P0.5 | Backend skeleton as in section 2: pytest, ruff, `requirements.txt` | A | `pytest` green on an empty test | ⬜ |
| P0.6 | CI: GitHub Actions runs backend and frontend tests on every pull request | A | PR shows a green check | ⬜ |

### Data intake checklist (P0.2)
- [ ] Data in `data/raw/`, `data/processed/`, `data/samples/`; reports in `docs/data_reports/teammate_a/` and `teammate_b/`
- [ ] Only one copy of each file (report folders contained duplicates of `processed/` files)
- [ ] **Do not take** B's old branch layout that deleted the app folder; take only data and reports
- [ ] `districts.csv`: A's 36 districts + Nominatim coordinates, plus B's LGD `district_code`; current names (Ahilyanagar, Chhatrapati Sambhajinagar, Dharashiv) as `district`; every old name and the Agmarknet spellings ("Amarawati", "Chattrapati Sambhajinagar") in `name_variants`
- [ ] `district_rainfall_history.csv` = B's version (1997–2014, matches `yield_training.csv`); A's 2010–2025 version saved as `district_climate_2010_2025.csv`
- [ ] `soil_npk_by_district.csv` = A's all-India version (757 districts)
- [ ] In every report: data.gov.in key → `<DATA_GOV_IN_API_KEY>`; `file:///c:/Users/...` links → repo paths
- [ ] One merged `data/SOURCES.md` with a "processed file → dataset ID" table
- [ ] `Teammate-B/data/DATA_FIXES.md` moved to `docs/data_reports/DATA_FIXES.md` (the path the three specs cite)
- [ ] Data tests (DATA.3) pass

---

## 4. Data layer and external integrations

### 4.1 Processed files the backend serves (`data/processed/`)
| File | Loader returns | Used by |
|---|---|---|
| `districts.csv` | 36 districts, coordinates, name variants | District resolver, map, every join |
| `district_crop_yields.csv` | DES area, production, yield by district, crop, season, year | Crop filter, traditional plan, yield sanity bounds |
| `yield_training.csv` | Cleaned training table (cleaning is ML.2) | ML training only |
| `district_climate_2010_2025.csv`, `district_rainfall_history.csv` | Season rainfall, ET₀, temperature history | Climate scenarios |
| `soil_npk_by_district.csv` | District N, P, K, pH (all-India) | Soil service, profile defaults |
| `groundwater_by_block.csv` | Category, extraction %, depths | Water budget cap, map colour |
| `reservoir_storage.csv` | Live storage % per reservoir and district served | Canal share |
| `irrigation_by_district.csv` | Source shares, efficiency by method | Water defaults, "water saved" |
| `recent_rainfall.csv` | 30/60/90-day rainfall and % departure | Water budget |
| `crop_water_coefficients.csv` | Kc and stage lengths per crop | Crop water need (ML) |
| `cost_of_cultivation.csv`, `seed.csv`, `fertilizer_*.csv` | Itemized costs, seed and fertilizer prices, university recommended doses (RDF), district fertilizer use | Cost service, fertilizer plan (ML) |
| `price_history_monthly.csv`, `msp.csv` | Monthly modal prices, MSP | Price risk, price floor |
| `crop_calendar.csv`, `crops_master.csv` | Sowing windows; crop names (en/mr/hi) and all source-name joins | Season filter, display names |

Every loader: typed columns, units checked, loaded once and cached in memory, returns `SourcedValue` where a value is shown to the farmer (`status = official_dataset`, `as_of` = dataset year).

### 4.2 Live integrations
| Integration | Endpoint and key parameters | Timeout / retry | If it fails |
|---|---|---|---|
| **Open-Meteo forecast** | `api.open-meteo.com/v1/forecast` with `daily=temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration`, `hourly=relative_humidity_2m`, `forecast_days=16`, `past_days=92`, `timezone=Asia/Kolkata` | 5 s, 2 retries | Last cached response, status `cached` |
| **Open-Meteo archive** | `archive-api.open-meteo.com/v1/archive` (only if a scenario year is missing from the dataset) | 8 s, 1 retry | Use the dataset in `data/processed` |
| **Geocoding** | Open-Meteo geocoding (`countryCode=IN`), then resolve `admin2` through `districts.csv` | 5 s, 1 retry | Cached place; else ask the farmer for the district |
| **SoilGrids** | `rest.isric.org/soilgrids/v2.0/properties/query`; convert pH ÷ 10, nitrogen ÷ 100, soc ÷ 10 | 6 s, 0 retries | Skip; use Soil Health Card district values |
| **Agmarknet prices** | data.gov.in resource `9ef84268-d588-465a-a308-a864a43d0070`, filters `state`, `district`, `commodity`; prices in ₹/quintal | 6 s, 2 retries | District → state → nearest mandi → last cached quote with date → **crop excluded** |
| **CWC reservoirs** | Official CWC weekly bulletin PDF (`rsms.cwc.gov.in/admin/storage/bulletins/bulletin-DD-MM-YYYY-<id>.pdf`, every Thursday), read by `ml/data_prep/build_reservoir_from_bulletin.py` into `data/processed/reservoir_storage.csv`. (data.gov.in only serves January 2023.) Refresh weekly and before the demo | n/a (file) | Last table, shown with its `observation_date` |
| **Sarvam speech** | speech-to-text and text-to-speech endpoints; model ids from the B10 report | 10 s | STT: ask the farmer to type; TTS: the browser voice on the frontend |
| **Sarvam models** | Chat, speech-to-text and text-to-speech, header `api-subscription-key`. One provider for all three | 15 s | Next model in `SARVAM_FALLBACK_MODELS`; then the template answer (ML AG.10), which needs no model |

All outgoing calls: async `httpx`, per-call timeout, retry with backoff, and per-stage timing recorded for the trace and `Server-Timing`.

### 4.3 Caching
| Data | TTL | Stale rule |
|---|---|---|
| Geocoding | 7 days | Serve stale on failure |
| Forecast and recent rain | 6 hours | Serve stale on failure, labelled `cached` |
| Mandi prices | 6 hours | Serve last real quote with its date |
| SoilGrids | 30 days | Serve stale |
| Static CSV data | process lifetime | n/a |
| Plans (`plan_id`) | 24 hours | Needed for re-optimize and reload |

Cache = in-memory TTL cache in front of SQLite. The database holds **three separate tables** with different rules:
* `upstream_cache`: only real API or file responses, so a cached value shown to the farmer is always something a source really returned.
* `plans`: our own generated plans, kept 24 h so re-optimize and reload work. Generated, clearly not a data source, and never served as if it were one.
* `agent_memory`: the LangGraph checkpointer (profile, messages, last plan inputs).

The "never store anything that did not come from a real API or file" rule applies to `upstream_cache` only. **Persistence**: Hugging Face Spaces loses the file on restart unless a persistent volume is attached, so DD.1 must attach one. Without it, a cold start has nothing to fall back on, which is exactly when the demo is most exposed.

---

## 5. API contract

Base path `/api`. JSON over HTTPS. UTF-8 (Marathi and Hindi text in every string). Times in ISO 8601 with `+05:30`. Money in rupees (number), land in acres, yield in quintals per acre for farmers (the data stays in tonnes per hectare internally; conversion 1 ha = 2.47105 acres, 1 tonne = 10 quintals).
Interactive docs at `/docs` (FastAPI OpenAPI). The Pydantic models in `schemas.py` are the single source of truth; the frontend generates its TypeScript types from the OpenAPI file.

### 5.1 Shared types

**SourcedValue**: every number the farmer sees.
```json
{ "value": 2150, "unit": "rs_per_quintal",
  "source": "Agmarknet (data.gov.in)", "source_url": "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070",
  "as_of": "2026-11-02", "status": "live" }
```
`status` tells the farmer where a number came from, and **every** number the farmer sees carries one:

| `status` | Meaning | Badge |
|---|---|---|
| `live` | Fetched from an API just now | green |
| `cached` | The last real response from that API; `as_of` shows when | amber |
| `official_dataset` | A file in `data/`; `as_of` is the dataset year | blue |
| `model` | Our own model output (yield, suitability); `source` names the model and its version | purple |
| `computed` | Arithmetic over other sourced values (profit, totals, impact); `source` names the formula | grey |
| `farmer_input` | The farmer said it (land, budget, borewells) | grey |
| `assumption` | A declared modelling constant (ml/SPECS.md 7A), not a measurement | orange |

**Every farmer-visible number is a `SourcedValue`.** That includes `yield_quintal_per_acre` (`model`), `profit_rs_per_acre` and every `StrategyResult` total (`computed`), `water_need_m3_per_acre` (`computed`, or `assumption` when it rests on a 7A constant), `impact` (`computed`), the `fertilizer` doses (`official_dataset`, the university RDF) and each `cost_per_acre` line (its own source). The frontend test "no number without a badge" therefore passes on the contract itself. Numbers that are **not** farmer-visible (ids, counts, `duration_ms`, `version`) are plain.

**FarmProfile**: what the agent understood from the farmer.
```json
{ "location_text": "Beed", "land_acres": 5, "budget_rs": 70000,
  "water_source": "borewell",           // rainfed | borewell | canal | both | null (null is treated as rainfed)
  "borewell_count": 1,                  // null if not said; capacity then uses the district median (assumption)
  "borewell_yield_lph": null,           // litres per hour, if the farmer knows it
  "pump_hours_per_day": null,
  "canal_access": false,                // farmer's own statement; no command-area check exists
  "irrigation_method": "flood",         // flood | sprinkler | drip | null
  "risk_appetite": "balanced",          // safe | balanced | max_profit
  "soil_test": null,                    // or { "n": 210, "p": 24, "k": 260, "ph": 7.2 }
  "language": "mr",                     // mr | hi | en
  "missing": [],                        // required fields still unknown: location_text | land_acres | budget_rs
  "defaults_used": [                    // every assumed value, with what was assumed and why
    { "field": "risk_appetite", "value": "balanced", "basis": "default" },
    { "field": "irrigation_method", "value": "flood", "basis": "district majority method (Minor Irrigation Census)" } ] }
```

**Location**
```json
{ "input": "Beed", "resolved_name": "Beed, Maharashtra", "district": "Beed", "state": "Maharashtra",
  "latitude": 18.9918, "longitude": 75.9098 }
```

**CropOption**: one candidate crop.
```json
{ "crop_id": "soybean",
  "names": { "en": "Soybean", "mr": "सोयाबीन", "hi": "सोयाबीन" },
  "season": "Kharif",
  "suitability": { "score": 1.12, "label": "good",            // good (>=1.05) | average | poor (<0.9)
    "top_factors": [ { "feature": "season_rainfall_mm", "value": 742, "unit": "mm",
                       "effect_quintal_per_acre": 1.2, "direction": "up" } ],
    "fallback_used": false },
  "yield_quintal_per_acre": { "drought": 3.1, "normal": 4.4, "excess": 3.8 },
  "price": { "value": 4600, "unit": "rs_per_quintal", "source": "Agmarknet (data.gov.in)", "source_url": "…", "as_of": "2026-10-31", "status": "live" },
  "expected_harvest_price": { "value": 4830, "unit": "rs_per_quintal", "source": "today's price × seasonal ratio 1.05 from 4 years of monthly history, floored at MSP", "as_of": "2026-10-31", "status": "computed" },
  "duration_days": 110, "harvest_month": "2027-02",
  "msp": { "value": 4892, "unit": "rs_per_quintal", "source": "CACP", "source_url": "…", "as_of": "2025-26", "status": "official_dataset" },
  "cost_per_acre": { "total_rs": 21400, "seed": 1950, "fertilizer": 2200, "manure": 860, "labour": 9300,
                     "machine": 3900, "irrigation": 500, "pesticide": 1480, "interest": 600,
                     "reference_year": "2022-23", "source": "DES/CACP Cost of Cultivation", "status": "official_dataset" },
  "fertilizer": { "n_kg_per_acre": 12, "p2o5_kg_per_acre": 20, "k2o_kg_per_acre": 8, "basis": "university recommended dose (RDF)" },
  "water_need_m3_per_acre": { "drought": 1900, "normal": 1500, "excess": 1100 },
  "profit_rs_per_acre": { "drought": 4200, "normal": 9800, "excess": 7600 } }
```

**WaterBudget**: one entry **per scenario**, because the rain term differs by scenario.
```json
{ "scenario": "normal",                  // drought | normal | excess
  "analogue_year": 2019,
  "available_m3": { "rain": {SourcedValue}, "groundwater": {SourcedValue}, "canal": {SourcedValue}, "total": {SourcedValue} },
  "basis": { "groundwater_category": {SourcedValue, "value": "Over-exploited", "note": "district average, not your block"},
             "category_cap": {SourcedValue, "value": 0.15, "status": "assumption"},
             "effective_rain_factor": {SourcedValue, "value": 0.75, "status": "assumption"},
             "reservoir_storage_pct": {SourcedValue}, "rain_so_far_mm": {SourcedValue} },
  "irrigation_method": "flood", "efficiency_pct": {SourcedValue, "value": 60},
  "need_m3": { "traditional_plan": {SourcedValue}, "recommended_plan": {SourcedValue} } }
```
`need_m3` is always computed **in the scenario of its own entry**, so the dashboard gauge changes with the scenario toggle like every other number.

**StrategyResult**: one plan from one strategy.
```json
{ "id": "qp_balanced",                     // traditional | lp_max_profit | qp_balanced | qp_drought_safe
  "label": "QP balanced", "kind": "qp", "risk_lambda": 0.5, "safety_scenario": "normal",
  "allocations": [ { "crop_id": "soybean", "acres": 2.5, "share_pct": 50, "cost_rs": 53500,
                     "water_m3": 3750, "profit_rs": { "drought": 10500, "normal": 24500, "excess": 19000 } } ],
  "totals": { "land_used_acres": 5, "budget_used_rs": 66200,
              "fertilizer_kg": { "n": 61, "p2o5": 98, "k2o": 40 }, "water_m3": 7100 },
  "profit_by_scenario_rs": { "drought": 21000, "normal": 52000, "excess": 44000 },
  "expected_profit_rs": 45600, "worst_case_profit_rs": 21000,
  "feasible": true, "binding_constraints": ["water"],
  "relaxations_applied": [ { "constraint": "budget", "change": "Reduced planned area from 5.0 to 4.6 acres" } ],
  "solver": { "name": "CLARABEL", "status": "optimal", "ms": 38 } }
```

**PlanResult**: the full answer.
```json
{ "plan_id": "pl_8f3a2c", "thread_id": "th_41d9", "version": 1,
  "created_at": "2026-11-02T09:15:00+05:30",
  "profile": { FarmProfile },
  "location": { Location },
  "season": { "name": "Kharif", "sowing_window": { "start": "2026-06-10", "end": "2026-07-20" }, "status": "official_dataset" },
  "scenarios": [ { "id": "drought", "label": "Drought", "season_rain_mm": {SourcedValue}, "probability": 0.2 },
                 { "id": "normal", "label": "Normal", "season_rain_mm": {SourcedValue}, "probability": 0.6 },
                 { "id": "excess", "label": "Excess rain", "season_rain_mm": {SourcedValue}, "probability": 0.2 } ],
  "crops": [ {CropOption}, ... ],
  "excluded_crops": [ { "crop_id": "onion", "reason_code": "no_real_price", "message": "No Agmarknet price found for Beed or nearby mandis." } ],
  "water": { WaterBudget },
  "strategies": [ {StrategyResult} x4 ],
  "recommended_strategy": "qp_balanced",
  "impact": { "water_saved_pct": {SourcedValue}, "fertilizer_saved_pct": {SourcedValue},
              "fertilizer_vs_district_use_pct": null,     // separate figure; null when district use is already below the RDF
              "drought_profit_gain_rs": {SourcedValue}, "versus": "traditional",
              "traditional_exceeds": ["water"] },         // limits the status-quo mix breaks, so the comparison stays honest
  "infeasibility": null,                                  // set when no feasible plan exists; see below
  "explanation": { "language": "mr", "text": "…", "key_points": [ { "icon": "droplets", "text": "…" } ],   // icon ∈ wheat | droplets | cloud-rain | sun | coins | trending-up | trending-down | map-pin | alert-triangle | badge-check (Lucide names, so the frontend needs no mapping)
                   "grounded": true, "provider": "sarvam-chat" },  // provider: the Sarvam model id used, or "template" when no model answered
  "warnings": [ { "code": "cached_data", "message": "Mandi prices are from 2026-10-30." } ],
  "data_status": { "live": 14, "cached": 2, "official_dataset": 31 } }
```

**TraceEvent**: one step of the agent, streamed live.
```json
{ "id": "ev_07", "node": "gather_data", "step": "get_prices",
  "status": "ok",                           // running | ok | cached | failed | skipped
  "started_at": "2026-11-02T09:15:02+05:30", "duration_ms": 812,
  "summary": "Agmarknet: 6 crops priced (Beed mandi)",
  "source": { "name": "Agmarknet (data.gov.in)", "url": "…", "status": "live" },
  "fallback_used": null }                   // e.g. "last real quote, 2026-10-30"
```

**Farmer-facing text is a code plus parameters, never an English sentence.** `warnings[]`, `excluded_crops[]`, `relaxations_applied[]`, `trace[].summary` and the suggestions all carry `{code, params}`; the frontend holds one i18n key per code in mr / hi / en and fills the parameters. Only `explanation.text` (written by the LLM in the farmer's language) and `source` names (proper nouns such as "Agmarknet") are free text.

```json
"excluded_crops": [ { "crop_id": "onion", "reason_code": "NO_REAL_PRICE", "params": { "district": "Beed" } } ],
"warnings":       [ { "code": "CACHED_PRICES", "params": { "as_of": "2026-10-30" } } ]
```
`reason_code` ∈ `NO_REAL_PRICE | NO_YIELD_DATA | NOT_SOWABLE_NOW | NOT_GROWN_IN_DISTRICT | WATER_INFEASIBLE | OVER_BUDGET`.
`warnings[].code` ∈ `CACHED_PRICES | CACHED_WEATHER | ASSUMED_IRRIGATION | ASSUMED_BOREWELL | DISTRICT_AVERAGE_SOIL | OLD_COST_YEAR | PRICE_NOT_ADJUSTED | SINGLE_CROP_ELIGIBLE`.
`relaxations_applied[].step` ∈ `CAP_TO_1 | REDUCE_AREA | DROP_WATER_HUNGRY_CROP | USE_NORMAL_SCENARIO_WATER`.

**Error** (every non-2xx response)
```json
{ "error": { "code": "LOCATION_NOT_FOUND", "message": "We could not find this place in India.",
             "user_message": { "mr": "…", "hi": "…", "en": "…" }, "retryable": false, "details": {} } }
```
Codes: `VALIDATION_ERROR` 422 · `LOCATION_NOT_FOUND` 422 · `DISTRICT_NOT_AGRICULTURAL` 422 (Mumbai City, Mumbai Suburban: no crop statistics exist) · `PLAN_NOT_FOUND` 404 · `AUDIO_TOO_LARGE` 413 · `STT_FAILED` 502 · `UPSTREAM_UNAVAILABLE` 503 · `RATE_LIMITED` 429 · `INTERNAL` 500. Never return a stack trace.

**Two outcomes are a 200 `PlanResult`, not an error**, because the farmer still gets an answer:

* **No eligible crop.** `crops: []`, `strategies: []`, `recommended_strategy: null`, `impact: null`, `excluded_crops` filled with one reason per crop, and `explanation` saying what is missing and what the farmer could do.
* **No feasible plan after the relaxation ladder** (ml/SPECS.md 8.4a). Each strategy has `feasible: false` and `allocations: []`, and `infeasibility` is filled:
```json
"infeasibility": { "binding": ["budget"], "violated": ["budget"],
  "detail": [ { "constraint": "budget", "required_rs": 62000, "available_rs": 70000, "shortfall_rs": 0 },
              { "constraint": "water", "required_m3": 11800, "available_m3": 7600, "shortfall_m3": 4200 } ],
  "relaxations_tried": [ { "step": "cap_to_1.0", "result": "still infeasible" },
                         { "step": "reduce_area", "result": "feasible at 4.1 acres" } ],
  "suggestion_code": "PLANT_LESS_LAND", "suggestion_params": { "feasible_acres": 4.1 } }
```
The frontend has a defined screen for both; neither is ever a blank page.

### 5.2 Endpoints

| # | Method and path | Purpose | Used by (frontend) |
|---|---|---|---|
| E1 | `POST /api/agent/chat` | One conversation turn with the agent, streamed (SSE) | Chat, trace, profile card, plan |
| E2 | `POST /api/plan` | Plan from a complete profile, no agent | Demo backup, tests |
| E3 | `POST /api/plans/{plan_id}/reoptimize` | Re-solve with a new risk, budget or scenario, using the same fetched data | Risk slider |
| E4 | `GET /api/threads/{thread_id}` | Profile + last plan + messages | Reload the page |
| E5 | `POST /api/transcribe` | Audio → text + language | Mic button |
| E6 | `POST /api/speak` | Text → audio | Spoken reply |
| E7 | `POST /api/prefetch` | Warm the caches for a location | As soon as a place is heard |
| E8 | `GET /api/locations/search?q=` | Place suggestions → district | Location confirm, map |
| E9 | `GET /api/districts` | 36 districts with coordinates and status colour | Map |
| E10 | `GET /api/districts/{district}/context` | Groundwater category, reservoir %, recent rain departure, irrigation shares | Map popup, water page |
| E11 | `GET /api/sources` | Every dataset and API: name, URL, publisher, licence, date | Sources page |
| E12 | `GET /api/sources/health` | Live status of each external API | Sources page |
| E13 | `GET /api/health` | App is up; model and data files loaded | Deployment check, warm-up ping |

#### E1 `POST /api/agent/chat` (Server-Sent Events)
Request:
```json
{ "thread_id": "th_41d9",            // omit on the first turn; the response creates one
  "message": "माझ्याकडे बीडजवळ ५ एकर जमीन आहे, ७० हजार रुपये आहेत, बोअरवेल आहे",
  "language": "mr",                  // from speech-to-text or the language picker
  "profile_patch": null }            // set when the farmer edits the profile card, e.g. { "land_acres": 3 }
```
Response `Content-Type: text/event-stream`. Each event: `event: <name>` + `data: <json>`.

| Event | Data | When |
|---|---|---|
| `thread` | `{ "thread_id": "th_41d9" }` | First event of the first turn |
| `profile` | `FarmProfile` | After the profile is extracted or edited |
| `question` | `{ "text": "तुमच्याकडे शेतीसाठी किती पैसे आहेत?", "field": "budget_rs", "language": "mr" }` | Required field missing; the turn ends after this |
| `trace` | `TraceEvent` | Every tool call and graph step (running, then ok/failed) |
| `plan` | `PlanResult` | When the plan is ready (and after every relaxation attempt, flagged in `trace`) |
| `message` | `{ "text": "…", "language": "mr", "provider": "gemini" }` | The agent's answer text |
| `error` | `Error` | A failure the agent could not handle |
| `done` | `{ "ms": 4180 }` | Always the last event |

Order for a full plan: `thread` → `profile` → many `trace` → `plan` → `message` → `done`.
Heartbeat comment line every 10 s. Client may close the connection to cancel.

#### E2 `POST /api/plan`
Request: `FarmProfile` (all required fields present). Response: `PlanResult`. Same pipeline as the agent without LLM calls; `explanation.provider = "template"`. Target: warm response under 5 s.

#### E3 `POST /api/plans/{plan_id}/reoptimize`
Request (any subset): `{ "risk_appetite": "safe", "budget_rs": 50000, "land_acres": 4, "safety_scenario": "drought" }`.
Response: `PlanResult` with the same `plan_id`, `version` + 1, new `strategies`, `impact` and `explanation` (template, in the farmer's language). Uses the stored inputs; no external API calls. Target: under 1.5 s.

**Identity and state rules, so the two paths cannot drift apart:**
* A chat follow-up that changes a fact also keeps the same `plan_id` and bumps `version`. A new `plan_id` is created only for a new location or a new season. `previous_version` is included so the frontend can show "Profit − Rs. 4,000" without storing the old plan itself.
* E3 **writes back** the changed field into the agent checkpointer for that `thread_id`. A later chat turn then starts from the same risk, budget and land the farmer set with the slider, so the two controls can never disagree.
* The risk setting has **one** owner: the profile. Both the profile card and the plan slider write that one field.

#### E4 `GET /api/threads/{thread_id}`
Response: `{ "thread_id", "profile": FarmProfile, "plan": PlanResult | null, "messages": [ { "role": "farmer|agent", "text", "language", "at" } ] }`.

#### E5 `POST /api/transcribe`
`multipart/form-data`: `audio` (webm/ogg/wav/mp3, at most 10 MB, at most 60 s), `language_hint` (`mr` | `hi` | `en`, optional).
Response: `{ "text": "…", "language": "mr", "duration_s": 6.4, "provider": "sarvam" }`.

#### E6 `POST /api/speak`
Request: `{ "text": "…", "language": "mr", "speed": 1.0 }`. Response: `audio/wav` bytes (or `503` with `UPSTREAM_UNAVAILABLE`; the frontend then uses browser speech).

#### E7 `POST /api/prefetch`
Request: `{ "location_text": "Beed" }`. Response: `{ "status": "warmed", "district": "Beed", "stages": { "geocoding": "ready", "weather": "ready", "prices": "cached" } }`. Never blocks a plan if it fails.

#### E8 `GET /api/locations/search?q=bee&limit=5`
Response: `{ "results": [ { "resolved_name": "Beed, Maharashtra", "district": "Beed", "state": "Maharashtra", "latitude": 18.99, "longitude": 75.91 } ] }`.

#### E9 `GET /api/districts`
Response: `{ "districts": [ { "district": "Beed", "names": { "mr": "बीड", "hi": "बीड", "en": "Beed" }, "latitude": 18.99, "longitude": 75.91, "groundwater_category": "Over-exploited", "status_color": "red" } ] }`.

#### E10 `GET /api/districts/{district}/context`
Response: `{ "district", "groundwater": { "category": {SourcedValue}, "extraction_pct": {SourcedValue}, "depth_post_monsoon_m": {SourcedValue} }, "reservoirs": [ { "name", "live_storage_pct": {SourcedValue} } ], "recent_rain": { "last_90d_mm": {SourcedValue}, "departure_90d_pct": {SourcedValue}, "category": "Deficient" }, "irrigation": { "borewell_share_pct": {SourcedValue}, "canal_share_pct": {SourcedValue}, "drip_adoption_pct": {SourcedValue} } }`.

#### E11 `GET /api/sources`
Response: `{ "sources": [ { "id": "B1", "name": "…", "publisher": "…", "url": "…", "license": "…", "verified_on": "2026-10-30", "type": "live_api | official_dataset", "used_for": "…" } ] }` (built from `data/SOURCES.md`).

#### E12 `GET /api/sources/health`
Response: `{ "checked_at": "…", "sources": [ { "id": "open_meteo", "name": "Open-Meteo", "status": "green|amber|red", "latency_ms": 310, "last_ok": "…", "note": "serving cached data" } ] }`. Checked at most every 60 s (cached).

#### E13 `GET /api/health`
Response: `{ "status": "ok", "models_loaded": true, "data_files": 21, "version": "…" }`. Used for the warm-up ping.

### 5.3 Cross-cutting rules
- **CORS:** only `CORS_ORIGINS`. **Request size:** JSON ≤ 64 KB, audio ≤ 10 MB.
- **Rate limit:** 30 requests/min per client on `/api/agent/chat` and `/api/plan`; 429 with `Retry-After`. Behind the hosting proxy the socket address is the proxy, so the client is identified by the first entry of `X-Forwarded-For` (trusting only the known proxy), falling back to `thread_id`. Judges sharing one network must not share one limit.
- **Language:** every farmer-facing message in the farmer's `language`; error `user_message` has all three.
- **Idempotent GETs.** `thread_id` and `plan_id` are random, unguessable ids. No personal data stored beyond the profile.
- **Observability:** `Server-Timing` header with per-stage times, structured logs with a request id, no secrets in logs.

---

## 6. Features designed for the frontend (what the backend must provide)

Rows reference the **feature ids** `F1`-`F18` in [`frontend/SPECS.md`](../frontend/SPECS.md) section 6. (Its task ids `FE.x` are a different numbering; using feature ids keeps the two files from drifting.)

| Frontend feature | Backend provides |
|---|---|
| F1 Mic and chat input | E5 transcribe, E1 chat |
| F2 Language picker and translations | `language` on every response; all farmer text as `{code, params}` so the app can translate it |
| F3 Farm profile card with edit | `profile` SSE event, `profile_patch` on E1, `defaults_used` with the basis of each assumption |
| F4 Live agent trace | `trace` SSE events, including `skipped` steps with a reason |
| F5 Plan view, per-crop details, "why this crop", excluded crops | `PlanResult.crops` with `suitability.top_factors` (fixed feature codes), `strategies[].allocations`, `excluded_crops[].reason_code` |
| F6 Scenario toggle and 4-strategy comparison | `scenarios` (with `analogue_year`), `profit_by_scenario_rs`, per-crop yield and profit by scenario, `strategies` |
| F7 Water gauge | `water`: **one `WaterBudget` per scenario**, so the gauge changes with the toggle |
| F8 Risk slider | E3 reoptimize (writes the new risk back into the agent memory) |
| F9 Source badge on every farmer-visible number | `SourcedValue` everywhere, with the seven `status` values |
| F10 Spoken reply | E6 speak |
| F11 Map with groundwater colours | E9 (incl. `is_agricultural_district`), E10 |
| F12 Sources and health page | E11, E12 |
| F13 Follow-up chat with diff chips | E1 with `thread_id`; `version` and `previous_version` on `PlanResult` |
| F14 Reload without losing the farm | E4 threads |
| F15 Errors, empty and infeasible states | `Error.user_message`, the 200 no-crop and infeasible shapes in 5.1 |
| F16 Prefetch | E7 |
| F17 Location picker | E8, E9 (a non-agricultural district returns `DISTRICT_NOT_AGRICULTURAL`) |
| F18 Server waking up | E13 health |

## 7. Tasks

### 7.1 Contracts
| ID | Task | Done when | Status |
|---|---|---|---|
| C.1 | `schemas.py` with every type in section 5.1 **and** every type the ML interface uses, so nothing is referenced but undefined: `SourcedValue`, `FarmProfile`, `Location`, `Season`, `Scenario` (incl. `analogue_year` and the all-year samples), `Candidate`, `ExcludedCrop`, `CropOption`, `Suitability`, `SuitabilityFactor`, `YieldPrediction`, `WaterNeed`, `WaterBudget`, `FertilizerPlan`, `CostBreakdown`, `Allocation`, `OptimizerInputs`, `StrategyResult`, `Infeasibility`, `Impact`, `PlanResult`, `TraceEvent`, `ChatMessage`, `Message` (code + params), `Error` | Reviewed by all three; no type is used anywhere without being defined here | ⬜ |
| C.2 | `docs/API_CONTRACT.md` generated from the OpenAPI file, **plus two example sets**: `docs/api_examples/contract/` (hand-written by the three of us at C.1 time, so the frontend is never blocked) and `docs/api_examples/live/` (captured from a real run as soon as M2 lands, and then the only set the frontend uses). Contract examples are an interface agreement, not product data, so they do not break the no-mock-data rule; they must never be bundled into a build | Frontend can build every screen from the contract set on day 1, and switches to the live set at M2 | ⬜ |
| C.4 | **SSE payloads are in the OpenAPI file too.** `TraceEvent`, `PlanResult`, `question`, `message` and `done` are declared as response models of a documented, non-streaming endpoint `GET /api/schemas/sse-events` that returns one example of each. OpenAPI cannot describe a stream, so without this the frontend would have to hand-write the types it parses, which its rule 4 forbids | The generated TypeScript types include every SSE payload | ⬜ |
| C.3 | Function stubs for ML calls (signatures in [`ml/SPECS.md`](../ml/SPECS.md) section 10) that raise `NotImplementedError` | Merged before ML code | ⬜ |

### 7.2 Data layer
| ID | Task | Done when | Status |
|---|---|---|---|
| DATA.1 | Loaders for every file in 4.1 (typed, units checked, cached in memory) | Each loader has a test | ⬜ |
| DATA.2 | District resolver: any spelling → canonical district through `name_variants` | Every district column in every file resolves | ⬜ |
| DATA.3 | Data tests: 36 districts, every file in `SOURCES.md`, value ranges, no API keys in `data/` or `docs/` | Green in CI | ⬜ |

### 7.3 Services
| ID | Task | Done when | Status |
|---|---|---|---|
| SVC.1 | Core: async `httpx` client, TTL + SQLite cache with stale fallback, per-stage timing, error types | Tests for expiry, stale fallback, timeout | ⬜ |
| SVC.2 | Location: place → lat/lon + canonical district | Works for 10 sample villages, incl. renamed districts | ⬜ |
| SVC.3 | Weather: 16-day forecast with ET₀ + recent rain | Returns `SourcedValue`s | ⬜ |
| SVC.4 | Soil: Soil Health Card district N, P, K, pH (data) + SoilGrids pH and texture (live, optional); farmer soil test overrides both | Missing → "unavailable", never a guess | ⬜ |
| SVC.5 | Prices: Agmarknet live with the fallback chain in 4.2; crop excluded if no real price. **Sugarcane** is sold to sugar mills, not at mandis: price it at the official FRP in `msp.csv` (₹355/q for 2025-26), never at jaggery prices | Never returns an invented price | ⬜ |
| SVC.6 | Costs: itemized cost per acre from `cost_of_cultivation.csv`, seed from `seed.csv`, fertilizer at the dose from ML.8; reference year shown | Itemized cost per acre | ⬜ |
| SVC.7 | Water budget: rain (recent + forecast + scenario) + groundwater share (capped by CGWB category) + canal share (reservoir %); formula in [`ml/SPECS.md`](../ml/SPECS.md) section 6 | Unit-tested; returns each part with its source | ⬜ |
| SVC.8 | District context service for E9 and E10 | Matches the contract | ⬜ |
| SVC.8b | **Reservoir refresh is a backend duty, not an ML one.** `ml/data_prep/build_reservoir_from_bulletin.py` reads the CWC weekly bulletin PDF (data.gov.in has no CWC data after Jan 2023). The bulletin URL carries an unguessable id, so the script probes the ids for the most recent Thursday. A: run it weekly and on demo morning, and keep the `observation_date` visible in the UI | Table dated within the last 8 days at demo time | ⬜ |
| SVC.9 | Speech service: Sarvam speech-to-text and text-to-speech with the fallbacks in 4.2 | Marathi and Hindi samples work | ⬜ |
| SVC.10 | Pipeline `run_plan(profile) -> PlanResult`: services → ML → optimizer → impact metrics. **This is the only orchestration path.** The agent's `gather_data`, `recommend`, `predict_yield` and `optimize` nodes call the *same* functions through `run_plan`'s stages, so `/api/plan` and `/api/agent/chat` can never return different plans for the same profile. A test asserts the two are identical for a fixed profile | One end-to-end test on a real sample, plus the E1-vs-E2 equality test | ⬜ |
| SVC.11 | Plan store: keep inputs of each plan for E3 and E4 (24 h) | Re-optimize makes no external calls | ⬜ |

### 7.4 API
| ID | Task | Done when | Status |
|---|---|---|---|
| API.1 | E1 SSE chat with the event order in 5.2, heartbeat and cancel | Matches C.2; tested with a fake agent first | ⬜ |
| API.2 | E2 `/api/plan` | Warm response under 5 s | ⬜ |
| API.3 | E3 reoptimize | Under 1.5 s, no external calls | ⬜ |
| API.4 | E4 threads | Reload restores profile and plan | ⬜ |
| API.5 | E5 transcribe and E6 speak | Size and duration limits enforced | ⬜ |
| API.6 | E7 prefetch | Failure never blocks a plan | ⬜ |
| API.7 | E8 to E10 locations, districts, context | Matches the contract | ⬜ |
| API.8 | E11 sources and E12 health | Health cached for 60 s | ⬜ |
| API.9 | E13 health + warm-up (load models and data at startup) | First request after start is fast | ⬜ |
| API.10 | Error format, CORS, size limits, rate limits | Every error follows 5.1; tested | ⬜ |

### 7.5 Quality and deployment
| ID | Task | Done when | Status |
|---|---|---|---|
| QA.1 | Benchmark script: latency per stage on 5 saved real profiles | Warm plan under 5 s | ⬜ |
| QA.2 | Failure drills: turn off each external API in turn | App still answers with cached real data and clear warnings | ⬜ |
| DD.1 | Deploy backend (D4); secrets set in the host, not in code; warm-up ping scheduled before judging. **Attach a persistent volume** for `CACHE_DB_PATH` (otherwise the cached-real-data fallback is empty after every restart, exactly when the demo needs it), and make sure the model files are actually deployed: they are committed with git-lfs, never git-ignored, because an ignored file never reaches the host | Public URL works from a phone; a restart keeps the cache; `/api/health` reports `models_loaded: true` | ⬜ |

---

## 8. Lessons from the old prototype (v1)
**Re-create:** cache with stale fallback · per-stage timing (`Server-Timing`) · prefetch while the farmer is still talking · unit conversions (1 ha = 2.47105 acres, 1 tonne = 10 quintals, ₹/quintal) · strict validation of LLM output.
**Do not repeat:** mock soil, mock prices or hardcoded costs as fallbacks · hidden defaults (cost, price, yield, default crop list) · one 340-line endpoint doing everything · district names that failed to join (Aurangabad → Chhatrapati Sambhajinagar) · a "simulated plan" banner (not needed: there is no mock data).
