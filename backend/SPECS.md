# Backend SPECS: Data Layer, Services and API

**Owner:** Teammate A · **Works with:** [`frontend/SPECS.md`](../frontend/SPECS.md) (consumes this API) and [`ml/SPECS.md`](../ml/SPECS.md) (models, optimizer and agent that this backend hosts)
**Stack:** Python · FastAPI · Pydantic v2 · httpx (async) · SQLite · pytest · ruff

**Status:** ⬜ Not started · 🟨 In progress · ✅ Done · ⛔ Blocked · ➖ Dropped
Update the **Status** column in the same pull request that does the work.

---

## 1. Ground rules

- **No mock, hardcoded or dummy data.** Every number comes from a live API or an official dataset, with its source and date. Breaking this rule means instant disqualification.
- **Scoring this part supports:** *Live Demo Robustness (30)*: cached real data when an API fails, fast responses, clear errors · *Technical Depth (20)*: async data layer, caching, water budget.
- **Code rules (checked in every pull request):**
  1. **No invented numbers in code.** No default prices, costs, yields or fallback crop lists. If real data is missing, the crop is **left out** and the response says why (`excluded_crops`).
  2. **Every value carries its source:** `SourcedValue = {value, unit, source, source_url, as_of, status}`, `status` ∈ `live | cached | official_dataset`. There is no `mock` status.
  3. **Old real data is fine, labelled.** If a live API fails, serve the last real response as `cached` with its `as_of` date.
  4. **Keys only in `.env`.** Never in code, reports, samples or commits. `.env.example` lists the names.
  5. **`pathlib` paths relative to the file.** No `C:\Users\...`.
  6. **Fixed random seeds** (`random_state=42`) wherever randomness is used.
  7. **Tests ship with the code.** Saved real API responses in `data/samples/` may be used in tests, never at runtime.
- **Open decisions affecting this file:** D2 speech provider (default **Sarvam**: speech-to-text and text-to-speech; browser speech as a fallback) · D4 hosting (default **Hugging Face Spaces**, plus a warm-up ping before judging).

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
| `SARVAM_API_KEY` | Speech-to-text, text-to-speech (and optional Sarvam LLM) |
| `GEMINI_API_KEY`, `GROQ_API_KEY` | Agent LLMs |
| `LLM_PROVIDER` | `gemini` / `groq` / `sarvam`: the first to try; the others are fallbacks |
| `CORS_ORIGINS` | Allowed frontend origins |
| `CACHE_DB_PATH` | SQLite file for cached real responses and agent memory |

---

## 3. Phase 0: Setup and data intake

| ID | Task | Owner | Done when | Status |
|---|---|---|---|---|
| P0.1 | `git init`, push to GitHub, protect `main` (pull requests only) | ML | Repo online; direct pushes blocked | ⬜ |
| P0.2 | **Data intake**: put the teammates' Drive folders into `data/` and `docs/data_reports/` using the checklist below | ML | Checklist all ticked | ⬜ |
| P0.3 | **Replace the leaked data.gov.in key.** It was written in A's checklist, the A9 report, the B1 report and `data_gov_in_api_report.md` | Key owner | New key issued, old key revoked | ⬜ |
| P0.4 | Root `.gitignore` and `.env.example` | A | `.env` ignored, names listed | ⬜ |
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
| `cost_of_cultivation.csv`, `seed.csv`, `fertilizer_*.csv` | Itemized costs, seed and fertilizer prices, RDF, response trials | Cost service, fertilizer curve (ML) |
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
| **CWC reservoirs** | data.gov.in resource `1531a095-fcf4-430a-965a-d835a75a824c` | 6 s, 1 retry | Dataset in `data/processed/reservoir_storage.csv` |
| **Sarvam speech** | speech-to-text and text-to-speech endpoints, header `api-subscription-key`; model names per the B10 report | 10 s | STT: ask the farmer to type; TTS: browser speech on the frontend |
| **LLMs** | Gemini / Groq / Sarvam, in the order of `LLM_PROVIDER` | 15 s | Next provider; then template answer (ML AG.10) |

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

Cache = in-memory TTL cache in front of a SQLite table of real responses (key, payload, fetched_at). Never store anything that did not come from a real API or file.

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
`status`: `live` (fetched now) · `cached` (last real response; `as_of` shows when) · `official_dataset` (a file in `data/`, `as_of` = dataset year).

**FarmProfile**: what the agent understood from the farmer.
```json
{ "location_text": "Beed", "land_acres": 5, "budget_rs": 70000,
  "water_source": "borewell",           // rainfed | borewell | canal | both | null
  "irrigation_method": "flood",         // flood | sprinkler | drip | null
  "risk_appetite": "balanced",          // safe | balanced | max_profit
  "soil_test": null,                    // or { "n": 210, "p": 24, "k": 260, "ph": 7.2 }
  "language": "mr",                     // mr | hi | en
  "missing": [],                        // required fields still unknown: location_text | land_acres | budget_rs
  "defaults_used": ["risk_appetite", "irrigation_method"] }
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
  "price": { "value": 4600, "unit": "rs_per_quintal", "source": "Agmarknet (data.gov.in)", "source_url": "…", "as_of": "2026-11-02", "status": "live" },
  "msp": { "value": 4892, "unit": "rs_per_quintal", "source": "CACP", "source_url": "…", "as_of": "2025-26", "status": "official_dataset" },
  "cost_per_acre": { "total_rs": 21400, "seed": 1950, "fertilizer": 2200, "manure": 860, "labour": 9300,
                     "machine": 3900, "irrigation": 500, "pesticide": 1480, "interest": 600,
                     "reference_year": "2022-23", "source": "DES/CACP Cost of Cultivation", "status": "official_dataset" },
  "fertilizer": { "n_kg_per_acre": 12, "p2o5_kg_per_acre": 20, "k2o_kg_per_acre": 8, "basis": "optimal dose on response curve, capped at university RDF" },
  "water_need_m3_per_acre": { "drought": 1900, "normal": 1500, "excess": 1100 },
  "profit_rs_per_acre": { "drought": 4200, "normal": 9800, "excess": 7600 } }
```

**WaterBudget**
```json
{ "available_m3": { "rain": 5200, "groundwater": 2400, "canal": 0, "total": 7600 },
  "parts": { "rain": {SourcedValue}, "groundwater_category": {SourcedValue, "value": "Over-exploited"},
             "reservoir_storage_pct": {SourcedValue}, "recent_rain_departure_pct": {SourcedValue} },
  "irrigation_method": "flood", "efficiency_pct": 60,
  "need_m3": { "traditional_plan": 11800, "recommended_plan": 7100 } }
```

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
  "impact": { "water_saved_pct": 40, "fertilizer_saved_pct": 22, "drought_profit_gain_rs": 17000, "versus": "traditional" },
  "explanation": { "language": "mr", "text": "…", "key_points": [ { "icon": "water", "text": "…" } ],
                   "grounded": true, "provider": "gemini" },       // provider: gemini | groq | sarvam | template
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

**Error** (every non-2xx response)
```json
{ "error": { "code": "LOCATION_NOT_FOUND", "message": "We could not find this place in India.",
             "user_message": { "mr": "…", "hi": "…", "en": "…" }, "retryable": false, "details": {} } }
```
Codes: `VALIDATION_ERROR` 422 · `LOCATION_NOT_FOUND` 422 · `NO_ELIGIBLE_CROPS` 200 (with `excluded_crops`) · `PLAN_NOT_FOUND` 404 · `AUDIO_TOO_LARGE` 413 · `STT_FAILED` 502 · `UPSTREAM_UNAVAILABLE` 503 · `RATE_LIMITED` 429 · `INTERNAL` 500. Never return a stack trace.

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
Response: `PlanResult` with the same `plan_id`, `version` + 1, new `strategies`, `impact` and `explanation` (template). Uses the stored inputs; no external API calls. Target: under 1.5 s.

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
- **Rate limit:** 30 requests/min per IP on `/api/agent/chat` and `/api/plan`; 429 with `Retry-After`.
- **Language:** every farmer-facing message in the farmer's `language`; error `user_message` has all three.
- **Idempotent GETs.** `thread_id` and `plan_id` are random, unguessable ids. No personal data stored beyond the profile.
- **Observability:** `Server-Timing` header with per-stage times, structured logs with a request id, no secrets in logs.

---

## 6. Features designed for the frontend (what the backend must provide)

| Frontend feature ([`frontend/SPECS.md`](../frontend/SPECS.md)) | Backend provides |
|---|---|
| Mic and chat input (FE.1) | E5 transcribe, E1 chat |
| Farm profile card with edit (FE.3) | `profile` SSE event; `profile_patch` in E1 |
| Live agent trace (FE.4) | `trace` SSE events |
| Plan view, per-crop details (FE.5) | `PlanResult.crops`, `strategies[].allocations` |
| Scenario toggle (FE.6) | `scenarios`, `profit_by_scenario_rs`, per-crop `yield` and `profit` by scenario |
| Strategy comparison (FE.6) | `strategies` (4) with expected and worst-case profit, water, fertilizer |
| Water gauge (FE.7) | `water` (WaterBudget) |
| "Why this crop" with SHAP (FE.5) | `CropOption.suitability.top_factors` |
| Risk slider (FE.8) | E3 reoptimize |
| Source badges (FE.9) | `SourcedValue` on every number |
| Spoken reply (FE.10) | E6 speak |
| Map with groundwater colours (FE.11) | E9, E10 |
| Sources page with live health (FE.12) | E11, E12 |
| Excluded crops note (FE.5) | `excluded_crops[].message` |
| Cached-data warning (FE.9) | `warnings`, `data_status` |
| Reload without losing the farm (FE.1) | E4 threads |

---

## 7. Tasks

### 7.1 Contracts
| ID | Task | Done when | Status |
|---|---|---|---|
| C.1 | `schemas.py` with every type in section 5.1, reviewed by all three | Reviewed by all three | ⬜ |
| C.2 | `docs/API_CONTRACT.md` generated from the OpenAPI file, with one **real** example response saved per endpoint in `docs/api_examples/` (captured from the running backend) | Frontend can build every screen from it | ⬜ |
| C.3 | Function stubs for ML calls (signatures in [`ml/SPECS.md`](../ml/SPECS.md) section 8) that raise `NotImplementedError` | Merged before ML code | ⬜ |

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
| SVC.5 | Prices: Agmarknet live with the fallback chain in 4.2; crop excluded if no real price | Never returns an invented price | ⬜ |
| SVC.6 | Costs: itemized cost per acre from `cost_of_cultivation.csv`, seed from `seed.csv`, fertilizer at the dose from ML.8; reference year shown | Itemized cost per acre | ⬜ |
| SVC.7 | Water budget: rain (recent + forecast + scenario) + groundwater share (capped by CGWB category) + canal share (reservoir %); formula in [`ml/SPECS.md`](../ml/SPECS.md) section 6 | Unit-tested; returns each part with its source | ⬜ |
| SVC.8 | District context service for E9 and E10 | Matches the contract | ⬜ |
| SVC.9 | Speech service: Sarvam speech-to-text and text-to-speech with the fallbacks in 4.2 | Marathi and Hindi samples work | ⬜ |
| SVC.10 | Pipeline `run_plan(profile) -> PlanResult`: services → ML → optimizer → impact metrics; also used by the agent tools | One end-to-end test on a real sample | ⬜ |
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
| DD.1 | Deploy backend (D4); secrets set in the host, not in code; warm-up ping scheduled before judging | Public URL works from a phone | ⬜ |

---

## 8. Lessons from the old prototype (v1)
**Re-create:** cache with stale fallback · per-stage timing (`Server-Timing`) · prefetch while the farmer is still talking · unit conversions (1 ha = 2.47105 acres, 1 tonne = 10 quintals, ₹/quintal) · strict validation of LLM output.
**Do not repeat:** mock soil, mock prices or hardcoded costs as fallbacks · hidden defaults (cost, price, yield, default crop list) · one 340-line endpoint doing everything · district names that failed to join (Aurangabad → Chhatrapati Sambhajinagar) · a "simulated plan" banner (not needed: there is no mock data).
