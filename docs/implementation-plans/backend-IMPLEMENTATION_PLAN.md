# Backend Implementation Plan

**Derived from:** `backend/SPECS.md` · `ml/SPECS.md` · `frontend/SPECS.md` · `SPECS_ALIGNMENT_RESOLUTION.md`
**Date:** 2026-10-31
**All tasks status:** ⬜ Not started (nothing in the codebase exists yet)

This plan is the single source of build order for the backend. It references
frontend feature IDs (F1–F18) and ML task IDs (ML.x / OPT.x / AG.x) so all
three owners can track dependencies without drifting. Every alignment problem
found in `SPECS_ALIGNMENT_PROBLEMS.md` is resolved here; the fixes from
`SPECS_ALIGNMENT_RESOLUTION.md` are baked in.

---

## 1. Key decisions (already resolved, not re-opened here)

| Decision | Outcome |
|---|---|
| Model provider | **Sarvam AI only** — chat, STT, TTS. No Gemini, no Groq |
| Season detection | `plan_season(today)` from `crop_calendar.csv`; 7-day grace, 21-day "opens soon" |
| Climate scenarios | Analogue years at P10/P50/P90 of the water index, **not** per-feature percentiles |
| Yield lag features | Model A (shipped): no lags. Model B: reference only |
| Non-agricultural districts | Mumbai City + Mumbai Suburban → `DISTRICT_NOT_AGRICULTURAL` |
| Weather source | Open-Meteo ERA5 1997–2025, one pipeline, one definition per feature |
| Fertilizer cost precedence | RDF-at-MRP replaces the DES fertilizer line; `seed.csv` replaces the DES seed line |
| Relaxation ladder | Deterministic code, 4 steps, ≤ 3 LLM calls total per plan |
| Single orchestration path | `run_plan(profile)` — both `/api/plan` and the agent call it |
| Cache tables | `upstream_cache` (real API/file data only) · `plans` · `agent_memory` |
| Water budget | One `WaterBudget` per scenario (drought / normal / excess) |
| Fertilizer saving | Two separate fields: `fertilizer_saved_pct` (vs Traditional) and `fertilizer_vs_district_use_pct` |
| Farmer text | All `{code, params}` pairs — app translates. Only LLM `explanation.text` is free text |
| SSE types in OpenAPI | Published via `GET /api/schemas/sse-events` so generated TS types cover them |
| Source badge | `SourcedValue.status` ∈ `live | cached | official_dataset | model | computed | farmer_input | assumption` |

---

## 2. Folder layout to create

```
backend/
├── app/
│   ├── main.py              FastAPI app, CORS, middleware (timing, request id, size limit)
│   ├── config.py            pydantic-settings from .env
│   ├── schemas.py           ALL Pydantic types (section 4 of this file)
│   ├── core/
│   │   ├── http_client.py   async httpx singleton, per-call timeout + retry with backoff
│   │   ├── cache.py         in-memory TTL cache + SQLite persistence (3 tables)
│   │   ├── timing.py        per-stage timer → Server-Timing header
│   │   ├── errors.py        error codes + HTTPException helpers
│   │   └── units.py         ha↔acre, t↔quintal, mm→m3, Indian number formatting
│   ├── data/
│   │   ├── loaders.py       typed loaders for every CSV in SPECS section 4.1
│   │   └── resolver.py      any spelling → canonical district (name_variants)
│   ├── services/
│   │   ├── location.py      place → lat/lon + canonical district (Open-Meteo geocoding)
│   │   ├── weather.py       16-day forecast + recent rain (Open-Meteo)
│   │   ├── soil.py          district NPK (CSV) + SoilGrids live (optional)
│   │   ├── water.py         water budget per scenario (formula from ml/SPECS.md §6)
│   │   ├── prices.py        Agmarknet fallback chain; sugarcane at FRP; excludes if no real price
│   │   ├── costs.py         itemized cost per crop (DES + seed.csv + RDF override)
│   │   └── speech.py        Sarvam STT + TTS with browser fallback note
│   ├── pipeline.py          run_plan(profile) → PlanResult  ← single orchestration path
│   ├── api/
│   │   ├── agent.py         E1 SSE chat
│   │   ├── plan.py          E2 /api/plan, E3 reoptimize
│   │   ├── threads.py       E4 /api/threads/{thread_id}
│   │   ├── speech.py        E5 transcribe, E6 speak
│   │   ├── prefetch.py      E7 prefetch
│   │   ├── locations.py     E8 search, E9 districts, E10 context
│   │   ├── sources.py       E11 sources, E12 health
│   │   └── health.py        E13 health + warm-up
│   ├── ml/                  (ML lead owns; backend wires it in via pipeline.py)
│   │   ├── suitability.py
│   │   ├── yield_model.py
│   │   ├── scenarios.py
│   │   ├── water_need.py
│   │   ├── fertilizer.py
│   │   └── optimizer.py
│   └── agent/               (ML lead owns)
│       ├── graph.py
│       ├── tools.py
│       ├── memory.py
│       └── prompts.py
├── tests/
│   ├── test_data.py         DATA.3 checks
│   ├── test_services.py
│   ├── test_pipeline.py     E1 vs E2 equality test
│   └── test_api.py
├── requirements.txt
├── SPECS.md
└── IMPLEMENTATION_PLAN.md   ← this file
```

---

## 3. Build phases

### Phase 0 — Setup (unblocks everyone)

| ID | Task | Done when | Dependency |
|---|---|---|---|
| P0.1 | Rotate the leaked data.gov.in key, push to GitHub, protect `main` | New key issued + old revoked **before** first push; direct push to `main` blocked | — |
| P0.2 | Data intake: Teammate-A + Teammate-B drive folders → `data/raw/`, `data/processed/`, `docs/data_reports/` | Intake checklist in `backend/SPECS.md §3` all ticked | P0.1 |
| P0.3 | Scrub key from all reports (`<DATA_GOV_IN_API_KEY>`) | `check_data.py` finds no key in any tracked file | P0.2 |
| P0.4 | Root `.gitignore` + `.env.example` (all env var names from SPECS §2) | `.env` ignored; no Gemini/Groq key name anywhere | P0.1 |
| P0.5 | Backend skeleton: `app/main.py`, `requirements.txt`, pytest, ruff | `pytest` green on an empty test; `ruff check` passes | P0.4 |
| P0.6 | GitHub Actions CI: lint + test on every PR | Green check on a PR | P0.5 |
| **C.1** | **`schemas.py`** with all 25 types (section 4 below) | Reviewed by all three owners; no type used without being defined | P0.5 |
| **C.2** | `docs/api_examples/contract/` hand-written examples; `docs/API_CONTRACT.md` from OpenAPI | Frontend can build every screen from day 1 | C.1 |
| **C.4** | `GET /api/schemas/sse-events` — each SSE payload as an OpenAPI response model | Generated TS types include every SSE payload | C.1 |
| **C.3** | Function stubs in `backend/app/ml/` raising `NotImplementedError` (signatures from ml/SPECS §10) | Merged before any ML code; backend compiles | C.1 |

**C.1, C.2, C.3, C.4 must land before any feature work starts.** They unblock the frontend (types from day 1), the ML lead (stubs to fill), and the backend (concrete shapes to code against).

### Phase 1 — Data layer

| ID | Task | Done when | Dependency |
|---|---|---|---|
| DATA.1 | Loaders for every CSV in SPECS §4.1: typed columns, units checked, cached in memory, returns `SourcedValue` where shown to the farmer | Each loader has a unit test | C.1, P0.2 |
| DATA.2 | District resolver: any spelling → canonical district via `name_variants` | Every district column in every file resolves (36 districts, all Agmarknet spellings) | DATA.1 |
| DATA.3 | Data tests: 36 districts, every file in `SOURCES.md`, value ranges, no API keys in `data/` or `docs/` | Green in CI | DATA.1, DATA.2 |

### Phase 2 — Core infrastructure

| ID | Task | Done when | Dependency |
|---|---|---|---|
| SVC.1a | `core/http_client.py`: async httpx singleton, per-call timeout, retry with exponential backoff | Tests for timeout, retry, and connection error | P0.5 |
| SVC.1b | `core/cache.py`: in-memory TTL cache + SQLite backend; **3 tables** — `upstream_cache` (real API/file responses only), `plans` (24 h), `agent_memory` (LangGraph checkpointer); stale fallback on TTL miss | Tests for expiry, stale fallback, table isolation | SVC.1a |
| SVC.1c | `core/timing.py`: per-stage timer; assembles `Server-Timing` header | Header present in every response | P0.5 |
| SVC.1d | `core/errors.py`: all error codes from SPECS §5.1 as typed exceptions; `user_message` in mr/hi/en | Every `HTTPException` carries the right code | C.1 |
| SVC.1e | `core/units.py`: ha↔acre (÷2.47105), tonne↔quintal (×10), mm→m3 (×4.047), Indian number grouping | Unit round-trip tests | P0.5 |

### Phase 3 — Services

Build in dependency order. Each service wraps one or more external APIs and returns `SourcedValue`-annotated results.

| ID | Task | Returns | Fallback | Done when |
|---|---|---|---|---|
| SVC.2 | `services/location.py`: place text → lat/lon + canonical district (Open-Meteo geocoding → `districts.csv` `admin2` match) | `Location` | Cached place; else ask the farmer for the district | Works for 10 sample villages incl. renamed districts (Ahilyanagar, Chhatrapati Sambhajinagar, Dharashiv) |
| SVC.3 | `services/weather.py`: 16-day forecast + `past_days=92` recent rain (Open-Meteo). Fields: `precipitation_sum`, `et0_fao_evapotranspiration`, `temperature_2m_max`, `temperature_2m_min`, `relative_humidity_2m_mean` (derived as the daily mean of the hourly `relative_humidity_2m` series from Open-Meteo; stored as its own `SourcedValue` with `source = "Open-Meteo ERA5, daily mean of hourly relative humidity"`), `forecast_days=16`, `timezone=Asia/Kolkata` | `SourcedValue`s per field | Last cached response, status `cached` | Returns all fields; `as_of` set |
| SVC.4 | `services/soil.py`: district NPK from `soil_npk_by_district.csv`; SoilGrids live optional (pH÷10, N÷100, SOC÷10); farmer soil test overrides both | Soil values with source | Skip SoilGrids; use district CSV | Missing fields returned as "unavailable", never a guess |
| SVC.5 | `services/prices.py`: Agmarknet live (data.gov.in resource `9ef84268...`), fallback chain: district → state → nearest mandi → last cached quote → **crop excluded**. Sugarcane priced at official FRP from `msp.csv`, never at jaggery prices | `SourcedValue` price per crop | See chain above | Never returns an invented price; sugarcane FRP correct |
| SVC.6 | `services/costs.py`: itemized cost per acre — fertilizer = RDF-at-MRP (overrides DES line), seed = `seed.csv` price (overrides DES line), all other lines from `cost_of_cultivation.csv`. Replaced DES lines returned as `superseded`. `total_rs` = sum of the live lines only | `CostBreakdown` | DES 2022-23 for non-overridden lines | Itemized cost per crop; reference year shown |
| SVC.7 | `services/water.py`: water budget per scenario. Formula: `effective_rain(s) + groundwater_share + canal_share`. Uses `borewell_count`, `borewell_yield_lph`, `pump_hours_per_day` from `FarmProfile`; falls back to district median borewell yield (Minor Irrigation Census) marked `assumption`. `canal_access` from farmer statement. Groundwater cap = CATEGORY_CAP[district avg from `groundwater_by_block.csv`]. Returns **one `WaterBudget` per scenario** | `list[WaterBudget]` (3 items) | See SPECS §7A for all assumption values | Unit-tested; each part returned with its source and status |
| SVC.8 | `services/` district context for E9 + E10: groundwater category, reservoir %, recent rain departure, irrigation shares | E9/E10 contract shapes | — | Matches the API contract |
| SVC.8b | `ml/data_prep/build_reservoir_from_bulletin.py` (ML lead writes; backend runs weekly and on demo morning): CWC weekly bulletin PDF → `data/processed/reservoir_storage.csv` | — | Last table with its `observation_date` | Table dated within the last 8 days at demo time |
| SVC.9 | `services/speech.py`: Sarvam STT + TTS. Headers: `api-subscription-key`. STT formats: webm/ogg/wav/mp3 + **audio/mp4** (iOS Safari). TTS → `audio/wav`. Fallbacks: STT → ask to type; TTS → 503 (frontend uses browser `speechSynthesis`) | Transcription / audio bytes | See above | Marathi and Hindi samples work; iOS mp4 accepted |

### Phase 4 — Pipeline (single orchestration path)

| ID | Task | Done when | Dependency |
|---|---|---|---|
| SVC.10 | `pipeline.py` — `run_plan(profile: FarmProfile) -> PlanResult`. Stages in order: location → weather → soil → prices → costs → water → ML (candidate crops, yield, suitability, scenarios, optimizer) → impact metrics → explanation template. **Both `/api/plan` (E2) and the agent call exactly this function.** Test asserts that E1 and E2 return identical `strategies` for a fixed profile | One end-to-end test on a real sample; E1-vs-E2 equality test | SVC.2–SVC.9, C.3 (stubs), DATA.1–DATA.2 |
| SVC.11 | `core/cache.py` plan store: keep `plan_id` → inputs for 24 h so E3 and E4 work without external calls | Re-optimize makes no external calls | SVC.1b |

**Cross-cutting rule for `run_plan`:** data is fetched once per plan, results cached in the `plans` table, and re-optimization (E3) reads from that cache. The agent's `gather_data`, `recommend`, `predict_yield`, and `optimize` nodes call the same stage functions, never their own copies.

### Phase 5 — API endpoints

Build in the order the frontend needs them (see frontend SPECS §7.2 build order).

| ID | Endpoint | Frontend feature | Done when | Dependency |
|---|---|---|---|---|
| API.9 | `GET /api/health` (E13) | F18 server waking up | First request after cold start is fast; `models_loaded` accurate | SVC.10 stubs |
| API.7a | `GET /api/districts` (E9) | F11 map | 36 districts with `is_agricultural_district`, coordinates, groundwater color | DATA.1, SVC.8 |
| API.7b | `GET /api/districts/{district}/context` (E10) | F11 map popup | Matches contract | SVC.8 |
| API.7c | `GET /api/locations/search` (E8) | F17 location picker | 5 suggestions per query | SVC.2 |
| API.2 | `POST /api/plan` (E2) | F5 plan dashboard (dev/test) | Warm response under 5 s; identical to E1 plan output | SVC.10 |
| API.1 | `POST /api/agent/chat` SSE (E1) | F1 voice+chat, F3 profile, F4 trace, F5 plan | Event order: `thread → profile → trace… → plan → message → done`; heartbeat every 10 s; cancel on disconnect | SVC.10, ML agent (AG.5) |
| API.3 | `POST /api/plans/{id}/reoptimize` (E3) | F8 risk slider | Under 1.5 s; no external calls; writes risk back to agent checkpointer; bumps `version`; includes `previous_version` | SVC.11 |
| API.4 | `GET /api/threads/{thread_id}` (E4) | F14 reload | Profile + last plan + messages restored | SVC.1b agent_memory |
| API.5 | `POST /api/transcribe` (E5), `POST /api/speak` (E6) | F1 mic, F10 spoken reply | Size/duration limits enforced; iOS `audio/mp4` accepted | SVC.9 |
| API.6 | `POST /api/prefetch` (E7) | F16 prefetch | Failure never blocks a plan; returns stage status | SVC.2, SVC.3, SVC.5 |
| API.8 | `GET /api/sources` (E11), `GET /api/sources/health` (E12) | F12 sources page | Health cached 60 s | DATA.1, SVC.1a |
| API.10 | Cross-cutting: CORS, size limits, rate limiting, error format | All features | Every error follows SPECS §5.1; rate limit by `X-Forwarded-For` first, then `thread_id`; JSON ≤ 64 KB, audio ≤ 10 MB | API.1–API.9 |

**Rate limiting note:** behind Hugging Face Spaces the socket address is the proxy's IP. Use the first entry of `X-Forwarded-For` (trusting only the known proxy) as the client identifier, falling back to `thread_id`. This prevents judges sharing one network from sharing one limit.

### Phase 6 — Quality and deployment

| ID | Task | Done when |
|---|---|---|
| QA.1 | Benchmark script: latency per stage on 5 saved real profiles | Warm plan under 5 s |
| QA.2 | Failure drills: disable each external API in turn | App answers with cached real data + `CACHED_*` warnings |
| DD.1 | Deploy backend (Hugging Face Spaces + **persistent volume** for `CACHE_DB_PATH`); secrets in host config; warm-up ping before judging; model files via git-lfs (never git-ignored) | Public URL works from a phone; `/api/health` → `models_loaded: true`; restart keeps the cache |

---

## 4. All 25 Pydantic types for `schemas.py`

These must be defined at C.1, before any other work starts. All 25 are used
across the ML interfaces, the pipeline, and the API contract.

```
SourcedValue        value, unit, source, source_url, as_of, status
FarmProfile         location_text, land_acres, budget_rs, water_source,
                    borewell_count, borewell_yield_lph, pump_hours_per_day,
                    canal_access, irrigation_method, risk_appetite,
                    soil_test, language, missing[], defaults_used[]
Location            input, resolved_name, district, state, latitude, longitude
Season              name, sowing_window{start,end}, status
Scenario            id, label, season_rain_mm (SourcedValue), probability,
                    analogue_year, all_year_samples[]
Candidate           crop_id, names{en,mr,hi}, season, water_need_m3_per_acre
ExcludedCrop        crop_id, reason_code, params
Suitability         score, label, top_factors[], fallback_used
SuitabilityFactor   feature (fixed code), value, unit, effect_quintal_per_acre, direction
YieldPrediction     t_per_ha (SourcedValue), clipped, out_of_training_range
WaterNeed           drought, normal, excess (each SourcedValue in m3/acre)
WaterBudget         scenario, analogue_year, available_m3{rain,groundwater,canal,total},
                    basis{...}, irrigation_method, efficiency_pct, need_m3{traditional,recommended}
FertilizerPlan      n_kg_per_acre, p2o5_kg_per_acre, k2o_kg_per_acre,
                    urea_bags, dap_bags, mop_bags, cost_rs (SourcedValue), basis
CostBreakdown       total_rs, seed, fertilizer, manure, labour, machine,
                    irrigation, pesticide, interest, superseded{seed_des,fertilizer_des},
                    reference_year, source, status
CropOption          crop_id, names, season, suitability, yield_quintal_per_acre{drought,normal,excess},
                    price, expected_harvest_price, seasonal_ratio, duration_days, harvest_month,
                    msp, cost_per_acre, fertilizer, water_need_m3_per_acre, profit_rs_per_acre
Allocation          crop_id, acres, share_pct, cost_rs, water_m3, profit_rs{drought,normal,excess}
OptimizerInputs     profile, location, season, candidates[], water_budgets[], scenario_weights,
                    price_history_years
StrategyResult      id, label, kind, risk_lambda, safety_scenario, allocations[],
                    totals, profit_by_scenario_rs, expected_profit_rs, worst_case_profit_rs,
                    feasible, binding_constraints[], relaxations_applied[], solver
Infeasibility       binding[], violated[], detail[], relaxations_tried[], suggestion_code, suggestion_params
Impact              water_saved_pct, fertilizer_saved_pct, fertilizer_vs_district_use_pct,
                    drought_profit_gain_rs, versus, traditional_exceeds[]
PlanResult          plan_id, thread_id, version, previous_version, created_at,
                    profile, location, season, scenarios[], crops[], excluded_crops[],
                    water (list[WaterBudget] — one per scenario), strategies[], recommended_strategy,
                    impact, infeasibility, explanation, warnings[], data_status
TraceEvent          id, node, step, status, started_at, duration_ms, summary, source, fallback_used
ChatMessage         role, text, language, at
Message             code, params   (all farmer-facing text except explanation.text)
Error               error{code, message, user_message{mr,hi,en}, retryable, details}
```

**Count note:** The 25th type is `Error` — it is an API-facing response schema and must be defined in `schemas.py` alongside the other 24 domain types. The original "24 types" label predated its addition as an explicit Pydantic model.

**Validation rules baked into the models:**
- `SourcedValue.status` is a `Literal` of the 7 allowed values — no `mock`
- `ExcludedCrop.reason_code` is a `Literal` of the 6 allowed values
- `warnings[].code` is a `Literal` of the 9 allowed values
- `relaxations_applied[].step` is a `Literal` of the 4 allowed steps
- `SuitabilityFactor.feature` is a `Literal` of the 16 fixed feature codes
- `Error.code` is a `Literal` of the 9 allowed error codes
- `WaterBudget` is always a list of 3 on `PlanResult` (one per scenario)

---

## 5. Environment variables (`.env.example`)

```
STATE=Maharashtra
DATA_GOV_IN_API_KEY=
SARVAM_API_KEY=
SARVAM_CHAT_MODEL=
SARVAM_STT_MODEL=
SARVAM_TTS_MODEL=
SARVAM_FALLBACK_MODELS=
CORS_ORIGINS=
CACHE_DB_PATH=
```

No Gemini, no Groq key name. Model IDs come from Teammate B's B10 test report.

---

## 6. Cross-cutting rules (enforced in every PR)

1. **No invented numbers.** No default prices, costs, yields or crop lists in code. Missing real data → crop excluded, reason returned.
2. **Every farmer-visible number is a `SourcedValue`.** Plain `int` / `float` only for ids, counts, `duration_ms`, `version`.
3. **Keys only in `.env`.** Never in code, logs, samples or commits.
4. **`pathlib` paths relative to the file.** No `C:\Users\...` anywhere in `app/`.
5. **`random_state=42`** wherever randomness is used.
6. **`run_plan` is the only orchestration path.** No parallel implementation in the agent.
7. **Farmer-facing text is `{code, params}`.** Only `explanation.text` (Sarvam output) is free text.
8. **Tests ship with the code.** A PR without tests for new logic is not merged.
9. **No stack traces in responses.** All errors use the `Error` schema.
10. **Structured logs** with a request ID; no secrets in logs.

---

## 7. Interface contracts with ML (signatures from ml/SPECS §10)

The stubs in `backend/app/ml/` must match these exactly. The ML lead fills them in.

```python
# All in backend/app/ml/
def candidate_crops(
    profile: FarmProfile,
    location: Location,
    season: Season,
    water: list[WaterBudget],
) -> tuple[list[Candidate], list[ExcludedCrop]]: ...

def predict_yield(
    crop_id: str,
    location: Location,
    season: Season,
    conditions: Scenario,       # carries all weather features for the analogue year
) -> YieldPrediction: ...       # t/ha + clipped + out_of_training_range flags

def suitability(
    crop_id: str,
    location: Location,
    season: Season,
    conditions: Scenario,
) -> Suitability: ...           # score, label, top_factors (fixed feature codes), fallback_used

def build_scenarios(
    location: Location,
    season: Season,
) -> list[Scenario]: ...        # drought / normal / excess + weights + all-year samples

def crop_water_need(
    crop_id: str,
    season: Season,
    scenario: Scenario,
    efficiency: float,          # from irrigation_by_district.csv for the farmer's irrigation method
) -> WaterNeed: ...             # mm and m3/acre per scenario

def fertilizer_plan(
    crop_id: str,
    fertilizer_prices: dict,    # MRPs from fertilizer_prices.csv
    # NOTE: crop_price removed — fixed RDF dose does not depend on crop price
) -> FertilizerPlan: ...        # RDF kg N/P2O5/K2O, product bags (urea/DAP/MOP), cost

def optimize(
    strategy: str,              # traditional | lp_max_profit | qp_balanced | qp_drought_safe
    inputs: OptimizerInputs,
) -> StrategyResult: ...

def compare_strategies(
    inputs: OptimizerInputs,
) -> list[StrategyResult]: ...  # all 4 strategies + impact
```

**`fertilizer_plan` fix:** the `crop_price` parameter was removed (leftover from the
dropped response-curve approach). A fixed RDF dose has no dependency on the current
crop price.

---

## 8. Frontend contract alignment checklist

These are the specific points where backend output must match frontend
expectations exactly, verified at C.1 time.

| # | Requirement | Backend field |
|---|---|---|
| B-F1 | `SourcedValue.status` has 7 values including `model`, `computed`, `farmer_input`, `assumption` | `schemas.py` Literal |
| B-F2 | `SuitabilityFactor.feature` is one of 16 fixed codes (not free text) | `schemas.py` Literal + ml/SPECS §3 list |
| B-F3 | `TraceEvent.status` includes `skipped` (frontend S3 needs to render it) | `schemas.py` Literal |
| B-F4 | Icon names in `explanation.key_points` use Lucide names: `wheat \| droplets \| cloud-rain \| sun \| coins \| trending-up \| trending-down \| map-pin \| alert-triangle \| badge-check` | `schemas.py` Literal |
| B-F5 | `WaterBudget` is a `list` of 3 on `PlanResult` (one per scenario, not a single object) | `PlanResult.water: list[WaterBudget]` |
| B-F6 | `impact` has two separate fertilizer fields: `fertilizer_saved_pct` (vs Traditional) and `fertilizer_vs_district_use_pct` (vs district, nullable) | `Impact` schema |
| B-F7 | `excluded_crops[].reason_code` is one of 6 fixed codes; `warnings[].code` is one of 8 fixed codes | `schemas.py` Literals |
| B-F8 | `CropOption.profit_rs_per_acre` has `drought`, `normal`, `excess` sub-fields (not a single value) | `CropOption` schema |
| B-F9 | `PlanResult.version` and `previous_version` both present (frontend diff chips need the old plan reference) | `PlanResult` schema |
| B-F10 | `GET /api/schemas/sse-events` exposes every SSE payload as an OpenAPI response model | C.4 task |
| B-F11 | All farmer-facing strings are `{code, params}` pairs except `explanation.text`; no English-only `message` strings in `warnings`, `excluded_crops`, `relaxations_applied`, or `trace.summary` | `Message` schema used everywhere |
| B-F12 | `districts.csv` carries `is_agricultural_district` flag; E9 exposes it | `DATA.1`, `API.7a` |
| B-F13 | Follow-up chips derived from `profile` fields, never hard-coded values | Agent `answer_from_memory` node |
| B-F14 | `CropOption.cost_per_acre` has `superseded{seed_des, fertilizer_des}` to show what the RDF override replaced | `CostBreakdown` schema |

---

## 9. Alignment issues resolved in this plan

Every item from `SPECS_ALIGNMENT_PROBLEMS.md` that affected the backend is
resolved above. For the record:

| Problem ID | Resolution |
|---|---|
| 1.1 Season examples | All examples use Rabi (31 Oct 2026). `plan_season()` rule in ml/SPECS §3A |
| 1.2 Scenario collapse | Analogue-year scenarios; Rabi uses combined water index |
| 1.3 Lag features | Model A shipped without lags |
| 1.4 34 vs 36 districts | `DISTRICT_NOT_AGRICULTURAL` for Mumbai City + Suburban |
| 1.5 Two weather pipelines | One source (ERA5); 2015-2025 for scenarios + range checks only |
| 1.6 Badges on all numbers | All 7 `SourcedValue.status` values defined; all farmer-visible numbers wrapped |
| 1.7 Build-order circularity | `contract/` examples day 1; `live/` examples at M2 |
| 1.8 Water inputs missing | `borewell_*`, `canal_access` in `FarmProfile`; CATEGORY_CAP in §7A |
| 1.9 Water single vs per-scenario | `PlanResult.water: list[WaterBudget]` (3 items) |
| 1.10 Fertilizer saving defined twice | Two fields: `fertilizer_saved_pct` + `fertilizer_vs_district_use_pct` |
| 1.11 Double-counted costs | Explicit precedence in SVC.6; `superseded` in `CostBreakdown` |
| 1.12 Undefined types | All 25 types listed in section 4 of this plan |
| 1.13 English-only messages | All farmer text is `{code, params}`; codes enumerated |
| 1.14 "No invented numbers" vs constants | Section 7A in ml/SPECS; constants declared with status |
| 1.15 Today's price vs harvest price | `expected_harvest_price` = today × seasonal ratio, floored at MSP |
| 2.1 Traditional baseline | Restricted to current season + priced crops; may break limits (shows which) |
| 2.4 Infeasibility payload | `Infeasibility` schema; 200 response with `feasible: false` and full detail |
| 2.5 Re-opt identity | E3 writes back to agent checkpointer; `version` + `previous_version` on `PlanResult` |
| 2.6 LLM budget | ≤ 3 calls: `extract_profile`, `explain`, one retry |
| 2.7 Two orchestration paths | `run_plan` is the only path; agent calls it |
| 2.10 SSE types | `GET /api/schemas/sse-events` (C.4) |
| 3.1 Wrong section references | This plan uses feature IDs F1–F18 throughout |
| 3.2 E8/E13 not wired | E8 listed under F17; E13 listed under F18 |
| 3.3 Icon names | `key_points[].icon` Literal with 10 Lucide names |
| 3.4 `fertilizer_plan` signature | `crop_price` parameter removed |
| 4.1 Cache rule contradiction | Three-table split; `upstream_cache` = real API/file only |
| 4.2 Persistent volume | DD.1 requires a persistent volume for `CACHE_DB_PATH` |
| 4.3 Rate limiting behind proxy | `X-Forwarded-For` first, `thread_id` fallback |

---

## 10. Definition of done per task

A task is **done** when:
1. The code is merged to `main` via a PR (not direct push).
2. `pytest` passes on the new tests in CI.
3. `ruff check` passes.
4. The status cell in the relevant SPECS table is updated to ✅ in the same PR.
5. For any task that changes the API contract: the contract examples in
   `docs/api_examples/contract/` are updated to match.

---

## 11. Known open issues (team decision required before demo)

These accepted limitations must be made user-visible before demo day.
Track each in the project board under label `open-issue`.

| ID | Issue | Accepted limitation | Required action |
|---|---|---|---|
| OI-1 | **District-level yield features** -- rainfed and borewell farmers in the same district get identical predicted yields | Accepted; farm-level data does not exist | Surface in E10 district context popup and E11 sources page; add to honest-limits list |
| OI-2 | **Sugarcane single-season comparison** -- 12-18 month crop compared per-acre with single-season crops | Accepted; noted in §8 lessons | Add `SINGLE_SEASON_COMPARISON` to `warnings[].code` literals; emit it whenever sugarcane appears in any strategy allocation |
| OI-3 | **Short price history for rice and tur** -- fewer than 3 years of Agmarknet history in some districts; `seasonal_ratio` defaults to 1.0 | Fix: add commodity spelling aliases to `COMMODITY_ALIASES` in `build_price_history.py` and re-run | `seasonal_ratio.note` must say "ratio not adjusted: N years" when N < 3; emit `PRICE_NOT_ADJUSTED` warning |
| OI-4 | **Soil and rainfall units on-screen** -- mm (rainfall) and m³ (water volume) appear on the water and district pages alongside the farmer-unit rule (acres / quintals / rupees) | Accepted; mm and m³ are standard for those quantities | Clarify in frontend SPECS §2 that mm and m³ are allowed farmer-facing units for rainfall and water volume |
| OI-5 | **Language picker post-plan** -- changing the picker does not re-translate `explanation.text` or trace summaries | Accepted; re-translation requires a new LLM call | Add a UI note in the picker: "The farm plan summary stays in [language]. Start a new conversation to change it." No new backend endpoint needed |
