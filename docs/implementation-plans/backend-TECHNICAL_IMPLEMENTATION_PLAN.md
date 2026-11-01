# Technical Implementation Plan: Backend and ML Completion

**Scope:** `backend/`, `ml/`, their implementation plans/specifications, and the data-preparation interfaces those components use.

**Purpose:** Finish the remaining work in dependency order, close the gaps between checked markers and actual acceptance criteria, and prepare a verifiable release. Execution progress is recorded below; existing implementation-plan status markers remain unchanged until their acceptance criteria are met.

**Sources reviewed:** `backend/SPECS.md`, `backend/IMPLEMENTATION_PLAN.md`, `ml/SPECS.md`, `ml/AGENT_IMPLEMENTATION_PLAN.md`, `SPECS_ALIGNMENT_PROBLEMS.md`, `SPECS_ALIGNMENT_RESOLUTION.md`, the backend and ML implementation, tests, and data-preparation scripts.

## 1. Initial Verified Baseline

- At plan creation, backend tests: **140 passed** in 32.90 seconds; one Starlette deprecation warning.
- Ruff: passed for `backend/app/`.
- `ml/data_prep/check_data.py`: all checks passed, including processed-data checks and its tracked-text key scan.
- The current test suite does not prove that the plan pipeline supplies a populated water budget or that the agent and direct-plan endpoints return equivalent plans. Passing tests therefore do not close those behavioral requirements.
- The local `backend/.venv` is ignored by Git. Subsequent implementation work is present in the worktree and has not been committed.

## 2. Completion Rules

1. Treat the acceptance criteria in the specs as authoritative, not the current checkbox alone. A checked task that fails its acceptance test returns to `In progress` until repaired.
2. Do not mark a task `Done` until its focused automated test, required broader test, lint, and relevant manual/operational check pass.
3. Keep data provenance visible. Missing data must result in exclusion or a declared, sourced assumption, never a silent numeric substitute.
4. Preserve one shared planning implementation for E1 and E2. Agent-specific conversation handling may precede or follow it, but crop, water, price, cost, and optimization logic must not be copied into a second planner.
5. Any API/schema change requires coordinated backend, ML, and frontend review, updated OpenAPI output/examples, and contract tests.
6. This plan does not assume ownership beyond the ownership rules in the existing specs: backend services/API work goes to the backend owner, ML/agent work to the ML owner, and shared contract changes to all owners.

## 3. Work Plan

### Phase 0: Security and Tracker Reconciliation

| ID | Work | Acceptance criteria | Existing marker/action |
|---|---|---|---|
| SEC.1 | Revoke and replace every credential exposed in the `.env` attachment or older copies. Search tracked history, reports, plans, samples, and shared originals for complete credentials and fragments; keep secret values out of the remediation report. | Old credentials are revoked; replacement credentials are supplied only through local/host environment configuration; a secret scan and history review are recorded. | Backend P0.1/P0.3 remain open until verified. The agent implementation plan contains redacted credential fragments that still need cleanup. |
| SEC.2 | Verify repository protections and secret configuration. | `.env` remains ignored, `.env.example` contains names/placeholders only, `main` protection is verified, and CI does not contain real keys. | P0.4 is partially present (`.gitignore` and `.env.example` exist); close only after all criteria pass. |
| DOC.1 | Reconcile status cells across the specs and plans with the implementation and test evidence. Remove obsolete blanket claims such as “nothing in the codebase exists yet” and align the agent-plan checklist with the task tables. | Each status has a named evidence link/test or is changed to `In progress`/`Blocked`; duplicate trackers have one agreed owner. | Applies to `backend/IMPLEMENTATION_PLAN.md`, `backend/SPECS.md`, `ml/SPECS.md`, and `ml/AGENT_IMPLEMENTATION_PLAN.md`. |

### Phase 1: Canonical Data and API Contract

| ID | Work | Acceptance criteria | Dependencies |
|---|---|---|---|
| DATA.1 | Decide and document the canonical data layout. Either complete the documented intake into `data/raw`, `data/processed`, and `docs/data_reports`, or explicitly revise all specs/loaders to use the current `Teammate-A` and `Teammate-B` locations. Remove duplicate/stale copies only after consumers are migrated. | A clean checkout has one documented copy of each dataset; every loader, script, report, and CI check resolves the same paths. `SOURCES.md` maps each processed file to its dataset/source. | SEC.1; agreement by data owners. |
| DATA.2 | Finish source-report intake and scrub. Move/merge `DATA_FIXES.md` and source reports to the paths named by the specs; reconcile the two `SOURCES.md` files. | Required reports exist at the documented paths; source URLs, licenses, dates, and limitations are recorded; `check_data.py` and a repository-wide secret scan pass. | DATA.1, SEC.1. |
| DATA.3 | Resolve data coverage and freshness gaps. Reconcile scenario weather coverage (the processed table currently validates through 2024 while the specs say 1997-2025), rice/tur price-history coverage, and weekly reservoir refresh behavior. | Each output's observed year/date range is tested and reported; price aliases are tested against source spellings; reservoir refresh finds the latest available bulletin without relying on a manually guessed ID and records `observation_date`. | DATA.1, DATA.2. |
| CON.1 | Reconcile farmer-visible numeric fields with the `SourcedValue` rule, including yield, profit, optimizer totals, fertilizer doses, and cost lines. | Contract tests recursively reject un-sourced farmer-visible numbers; each source/status and `as_of` is accurate. Schema changes are approved by all owners. | DATA.2; shared contract review. |
| CON.2 | Complete C.2: generate `docs/API_CONTRACT.md` and add contract and live example sets. Make the SSE schema endpoint expose actual response models in OpenAPI. | Type generation includes every SSE payload; examples validate against the current schemas; no sample data is bundled into production builds. | CON.1. |

### Phase 2: Backend Service Correctness

| ID | Work | Acceptance criteria | Dependencies |
|---|---|---|---|
| SVC.1 | Repair the water-budget integration. `run_plan` correctly calls the synchronous builder, but the agent tool wrapper incorrectly awaits it; align the wrapper and ensure errors cannot silently produce a plan without water constraints. | The agent tool returns all three scenario budgets; every successful plan has exactly three scenario budgets; each solver strategy uses the matching water cap; an integration test fails if budgets are absent or a water constraint is exceeded. | CON.1, DATA.1. |
| SVC.2 | Correct water accounting and assumptions. Include observed rain, forecast rain, and analogue-year remaining rainfall without double counting; validate borewell/canal inputs, source dates, district-average groundwater, reservoir freshness, and irrigation efficiency. Remove unsupported fallback values or return them as disclosed assumptions. | Unit tests cover each water term, missing-source cases, all three scenarios, units, and stale/live statuses; farmer-visible defaults appear in `defaults_used` with their basis. | SVC.1, DATA.3. |
| SVC.3 | Repair the price fallback chain and price-history integration. Align loader column names/units; implement date-bounded state/nearest-market fallbacks; reject zero/invalid prices; use official MSP/FRP data or exclude the crop. Remove generic fallback prices. | Tests cover live quote, state/nearest fallback, stale cache, unsupported crop, no data, and stale dates; no fallback returns an invented price. | DATA.1-DATA.3, CON.1. |
| SVC.4 | Repair cost and fertilizer sourcing. Ensure RDF, MRP, seed, and DES precedence is consistent; missing RDF or prices must not silently become zero-cost inputs. Make source and units correct for every line. | Cost components sum to the reported total; superseded DES lines are preserved; missing required data excludes the crop or is explicitly reported; no hardcoded MRP fallback. | DATA.1-DATA.2, CON.1. |
| SVC.5 | Make errors and request controls match the API contract. Standardize the non-2xx response shape; enforce JSON limits even when `Content-Length` is absent; enforce audio size and duration; add per-client rate limits using trusted proxy configuration; populate per-stage `Server-Timing`. | Tests assert exact error JSON/status, chunked/oversized bodies, duration limits, `Retry-After`, proxy identity handling, and timing headers. | CON.1, CON.2. |
| SVC.6 | Correct API health/source behavior and the source of district context. Avoid reporting healthy/up-to-date sources without a meaningful check; surface observation dates and missing data honestly. | API tests validate health-cache TTL, upstream failure status, data-file count, and source dates. | DATA.2-DATA.3, SVC.5. |

### Phase 3: ML and Optimizer Integrity

| ID | Work | Acceptance criteria | Dependencies |
|---|---|---|---|
| ML.1 | Finish ML.2 cleaning evidence and reproducible training. Use a documented time split with validation, report rows removed by reason, train the shipped artifact consistently, and verify feature transforms match inference. | Cleaned-data report and training metadata include dataset/version, split years, seed, features, artifacts, and overall/per-crop metrics. The experiment is reproducible from a clean environment. | DATA.1-DATA.3. |
| ML.2 | Use per-crop evaluation to select Model A or the hierarchical baseline at inference. Remove guessed inference features; handle missing/out-of-training-range inputs explicitly; align clipping with the spec. | Tests cover crops where the baseline beats Model A, unsupported categories, missing features, out-of-range values, and prediction bounds. Metadata and report match runtime selection. | ML.1, CON.1. |
| ML.3 | Complete analogue-year scenario contract and crop metadata. Make the supported year range explicit, include the required features for each selected analogue year, and carry actual crop duration/calendar data into candidates/options. | Scenario tests verify P10/P50/P90 selection, Rabi water-index ranking, all-year samples, probabilities/status, and documented year coverage; long-duration crop tests use source calendar duration, not a fallback. | DATA.3, ML.1. |
| OPT.1 | Implement risk covariance from historical annual per-crop profit samples and real price history rather than the three displayed scenarios. Define minimum-sample behavior and verify positive semidefiniteness. | A fixture with known annual samples produces a known covariance; insufficient-history cases follow the declared fallback and are reported. | ML.1-ML.3, SVC.3-SVC.4. |
| OPT.2 | Make solver constraints and the deterministic relaxation ladder correct. Apply the forced diversification cap, reduce area using actual constraints, record the effective safety scenario, and validate feasibility after each retry. | Property-style tests verify land, budget, water, and crop caps after every successful solve/relaxation; infeasible cases return complete reports and no allocations. `lambda=0` agrees with LP under identical constraints. | OPT.1. |
| OPT.3 | Correct Traditional crop shares and impact calculations. Join DES crop names to canonical crop IDs, compare only eligible plan-season crops, and compute fertilizer savings according to the agreed definition and units. | Tests verify baseline allocation mapping, totals, and sourced impact values; cases with no comparable baseline return an explicit unavailable result rather than a misleading zero. | CON.1, OPT.2. |
| ML.4 | Finish ML.9 reports and reconcile EXP_03/EXP_04 claims with current constants and implementation. | Reports contain required methods, source limits, per-crop results, artifacts, and next steps; every value agrees with committed metadata and code. | ML.1-ML.3, OPT.1-OPT.3. |

### Phase 4: Shared Pipeline, Agent, and API Integration

| ID | Work | Acceptance criteria | Dependencies |
|---|---|---|---|
| INT.1 | Make `run_plan` the single source of crop, data, water, ML, and optimizer results. Agent conversation nodes may extract/patch profiles and ask missing-field questions, then invoke the shared planner; they must not construct a second plan. | For the same normalized profile, E1 and E2 return equal crops, scenarios, water budgets, strategies, impacts, and warnings. Any divergence fails CI. | SVC.1-SVC.6, ML.1-ML.4, OPT.1-OPT.3. |
| AG.1 | Repair routing, follow-up, and profile patch flow. Load previous thread state, merge changes, replan changed facts, answer plan questions from stored state, and persist memory across process restart using the configured SQLite persistence. | Tests cover new plan, missing-field question, card edit, changed-fact follow-up/versioning, question-only turn, restart/reload, and reoptimize write-back. No assumed acreage/budget is injected. | INT.1. |
| AG.2 | Build valid PlanResult/SSE outputs. Convert candidates to full CropOptions before response construction; preserve infeasibility/no-crop states; emit `thread -> profile -> trace -> plan -> message -> done` and errors in the declared format. | Contract tests parse every event and payload against OpenAPI schemas; event order and heartbeat/cancel behavior pass; no missing `message` or profile event. | CON.1-CON.2, AG.1. |
| AG.3 | Verify explanations, grounding, and no-model templates against the final plan output and three supported languages. | Injected ungrounded values fail; rounding/unit tests cover rupees, acres, crop yield, Devanagari digits and number words; template answers never claim unsupported numbers; native-speaker review is recorded. | AG.2, OPT.3. |

### Phase 5: Release Evidence and Operations

| ID | Work | Acceptance criteria | Dependencies |
|---|---|---|---|
| QA.1 | Add missing regression coverage at the owning abstraction boundaries. Tests may use saved real API responses or controlled service fakes; runtime must not use mock data. Fix the portability issue in `backend/test_agent_full.py` and make all documented test commands work from a clean clone. | Backend tests include the scenarios listed above; no machine-specific absolute paths; tests do not depend on live third-party services unless explicitly designated as smoke tests. | Phases 1-4. |
| QA.2 | Complete QA.1 benchmark and QA.2 failure drills. Benchmark five saved real profiles and disable each external dependency in turn. | Warm plan under 5 seconds and reoptimization under 1.5 seconds on the declared host; cached fallbacks preserve source/date and warnings; results are committed as a report. | QA.1, SVC.1-SVC.6, INT.1. |
| REL.1 | Deploy to the selected host with persistent `CACHE_DB_PATH`, model artifacts, configured secrets, correct CORS, and a warm-up check. Verify the weekly reservoir update and cache behavior across restart. | Public endpoint works from a phone; `/api/health` reports data/model readiness accurately; restart preserves cache/thread data; no secret is committed. | SEC.1, DATA.3, QA.2. |
| REL.2 | Complete QA.3, DD.5, and DD.6: demo stories, fresh-clone README/setup, honest limitations, and the reviewed slide deck. | Three rehearsed stories under three minutes; blocked-upstream dry run succeeds; README reproduces setup; metrics and limitations match reports and UI. | REL.1, QA.2, ML.4. |

## 4. Marker Reconciliation

The following markers need explicit reconciliation in the existing documents; this plan does not change them automatically.

### Execution progress (2026-11-01)

| Work area | Verified progress | Remaining acceptance work |
|---|---|---|
| SVC.1-SVC.2 water | Agent water-budget wrapper no longer awaits the sync builder; the plan requires three budgets. Forecast rain, humidity aggregation, district-average groundwater matching, and 7-day reservoir freshness have regression coverage. Missing borewell yield/pump hours are explicitly marked as an assumption and contribute zero groundwater; the focused regression passes. | Borewell yield/pump-hour median is not present in either teammate data folder. |
| SVC.3 prices | District price-history schema/alias/date filtering now match the processed CSV; state fallback uses the actual state-median file. Seasonal ratios use real monthly history, insufficient history is explicitly unadjusted, and expected harvest price is floored at sourced MSP. | No mandi coordinate dataset exists, so a nearest-market fallback cannot be computed. Rice/tur coverage and live-upstream behavior still need acceptance tests. |
| SVC.4 costs | Missing fertilizer RDF/MRP/bag-size and seed-cost source rows fail closed. Candidate exclusions surface source-data gaps with a localized `DATA_UNAVAILABLE` reason. | Complete cost-line provenance/units review and shared contract review remain open. |
| ML.3 / optimizer | Candidate duration now comes from the crop calendar. QP risk is scaled to the Rs objective unit; empty solutions are not returned as feasible plans; solver results are checked against land, budget, water, and crop caps, including the forced-cap relaxation. | Historical-year risk covariance, Traditional crop-name mapping, and fertilizer savings by RDF cost remain open. |
| SVC.5 errors | AppError responses from API routes now use the top-level error contract rather than FastAPI's nested `detail` shape. | Request-body limits without `Content-Length`, rate limiting, complete timing, and API/client contract tests remain open. |
| Verification | User's unrestricted Windows run: **172 passed** in 18.95 seconds, including the loop-scoped HTTP-client regression and deterministic end-to-end planning test; one Starlette deprecation warning. Full `backend/app/` Ruff check, `ml/data_prep/check_data.py`, and `git diff --check` pass in the current worktree. Prior locale JSON checks passed. | API/server live smoke tests and acceptance work listed above remain open. |

### Open markers to retain until acceptance

- Backend: P0.1-P0.4, C.2, QA.1, QA.2, and DD.1.
- ML: ML.2, ML.9, QA.3, DD.5, and DD.6.
- Alignment resolution follow-up: remaining rice/tur price-history alias/coverage work and the accepted district-level feature limitation. The latter is a disclosed product limitation, not a code-completion blocker.

### Checked markers requiring revalidation

- Backend SVC.7 and SVC.10; API.1, API.5, and API.10; SVC.8b reservoir refresh.
- ML.4/ML.4b, ML.5, ML.7/ML.8, OPT.1-OPT.5, and AG.2-AG.10.
- The current `backend/IMPLEMENTATION_PLAN.md` header claims no code exists; the ML agent-plan checklist still shows implementation tasks unchecked. These trackers must be reconciled with `backend/SPECS.md` and `ml/SPECS.md` after owners agree on the source of truth.

## 5. Required Verification Commands

Run from the repository root on Windows after implementation:

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend/app/
backend\.venv\Scripts\python.exe -m pytest backend/tests/ -v --tb=short --no-header
python ml/data_prep/check_data.py
```

Also run the documented live/deployment smoke tests separately; their external-network and credential requirements must be stated, and their output must never print secret values.

## 6. Definition of Complete

The remaining work is complete only when:

- No exposed credential remains active or appears in tracked files/history without an approved incident decision.
- The documented data layout and source registry work from a clean checkout.
- A normal plan always has three populated scenario water budgets, sourced farmer-visible values, and solver-verified constraints.
- E1 and E2 use the same planning stages and produce equivalent plan payloads for equivalent profiles.
- Model/optimizer reports match the actual shipped behavior and all open limitations are visible to users.
- The expanded tests, Ruff, data integrity gate, benchmark, failure drills, deployment restart check, and demo rehearsal pass.
- Specs and implementation-plan markers are updated with the evidence in the same change that closes each task.