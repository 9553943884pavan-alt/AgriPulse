# AgriPulse — Agent Implementation Plan: Full Analysis

**Files read:**  
- [`ml/AGENT_IMPLEMENTATION_PLAN.md`](file:///c:/Users/hp/Downloads/AgriPulse-main/ml/AGENT_IMPLEMENTATION_PLAN.md) (723 lines — the subject)  
- [`backend/SPECS.md`](file:///c:/Users/hp/Downloads/AgriPulse-main/backend/SPECS.md) (524 lines)  
- [`backend/IMPLEMENTATION_PLAN.md`](file:///c:/Users/hp/Downloads/AgriPulse-main/backend/IMPLEMENTATION_PLAN.md) (432 lines)  
- [`ml/SPECS.md`](file:///c:/Users/hp/Downloads/AgriPulse-main/ml/SPECS.md) (385 lines)  
- [`frontend/SPECS.md`](file:///c:/Users/hp/Downloads/AgriPulse-main/frontend/SPECS.md) (266 lines)  
- [`.env`](file:///c:/Users/hp/Downloads/AgriPulse-main/.env) (15 lines)

**Date:** 2026-10-31

---

## Overall Verdict

The Agent Implementation Plan is **well-structured, technically detailed, and consistent with the core decisions** (Sarvam-only, single orchestration path, analogue-year scenarios, deterministic relaxation ladder, SQLite checkpointer, grounding check, template fallback). The build-order graph is correct.

**However, 12 issues were found** — ranging from critical integration mismatches with the updated backend contract to missing items the ML lead needs to implement that are not yet in the plan.

---

## ✅ What Is Correctly Specified

| Area | Evidence |
|---|---|
| Sarvam-only (no Gemini/Groq) | §0 keys table + §7 `.env` snippet; fallback chain uses Sarvam models only |
| `.env` model IDs correct | `SARVAM_CHAT_MODEL=sarvam-105b`, `saaras:v4`, `bulbul:v3` — matches `.env` on disk |
| Correct Sarvam endpoints | `/v2/chat/completions`, `/speech-to-text`, `/text-to-speech` with correct auth header |
| 3 LLM calls max | `extract_profile` (1) + `explain` (1) + retry (1) — rule-based `route`/`ask_missing` |
| Deterministic relaxation ladder | §Phase A3 matches ml/SPECS §8.4a: 4 steps, code not LLM |
| Single orchestration path | Phase A8 explicitly wires agent to call `run_plan` via the same service functions |
| Grounding check with Devanagari | §Phase A4 `grounding_check` handles Devanagari digits, Indian grouping, number words |
| Template fallback (AG.10) | §Phase A6 with 3-language templates; tested with key removed |
| SQLite checkpointer (LangGraph) | §Phase A5 uses `SqliteSaver`, same `CACHE_DB_PATH` |
| Analogue-year scenarios | ML.5 `build_scenarios` correctly uses P10/P50/P90 + Rabi mixed index |
| All 8 ML function signatures | §7 shows all functions; `crop_price` correctly removed from `fertilizer_plan` |
| Constants in `constants.py` | §6 lists all 7A constants with values and status |
| Graph flow diagram | §Phase A3 matches ml/SPECS §8.1 exactly |
| AgentState schema | §4 is comprehensive; includes `all_year_samples`, `previous_version` chain |
| Demo districts | §8 checklist references Jalgaon/Pune/Ahilyanagar/Nashik (matches ml/SPECS §9A) |

---

## ❌ Issues Found

---

### ISSUE 1 — CRITICAL: `candidate_crops` signature mismatch between agent plan and backend contract

**Agent Plan (Phase M1, line 128):**
```python
def candidate_crops(
    profile: FarmProfile,
    location: LocationResult,   # uses LocationResult
    season: str,                # season as plain string
    water: WaterBudget,         # single WaterBudget, not list
) -> tuple[list[Candidate], list[ExcludedCrop]]
```

**Backend IMPLEMENTATION_PLAN §7 (authoritative ML interface contract):**
```python
def candidate_crops(
    profile: FarmProfile,
    location: Location,          # uses Location (the Pydantic model name)
    season: Season,              # Season object, not str
    water: list[WaterBudget],    # list of 3 WaterBudgets (one per scenario)
) -> tuple[list[Candidate], list[ExcludedCrop]]
```

**Action:** Update Phase M1 signature to use `Location`, `Season`, and `list[WaterBudget]`.

---

### ISSUE 2 — CRITICAL: `build_scenarios` signature uses `LocationResult`, not `Location`

**Agent Plan (Phase M3, line 211):**
```python
def build_scenarios(location: LocationResult, season: str) -> list[Scenario]
```

**Backend IMPLEMENTATION_PLAN §7:**
```python
def build_scenarios(location: Location, season: Season) -> list[Scenario]
```

**Action:** Use `Location` and `Season` types throughout the agent plan, not `LocationResult` or `str` for season.

---

### ISSUE 3 — CRITICAL: `tools.py` uses non-schema type names throughout Phase A2

Phase A2 (line 359–368) uses `LocationResult`, `WeatherForecast`, `SoilData`, `CropPrice`, `CropCost` — none of which are in the 25 Pydantic types defined in `backend/app/schemas.py` (C.1).

The correct type names from the schema are:
- `LocationResult` → `Location`
- `WeatherForecast` → not defined; weather data is returned as `dict[str, SourcedValue]` — need to clarify the return type
- `SoilData` → not in the 25 types; the plan must either add it or return a plain dict of `SourcedValue`s
- `CropPrice` / `CropCost` → not in the 25 types

**Action:** Align all tool return type annotations with the 25 types in `schemas.py`. For types not in the contract (weather, soil as intermediate types), define them explicitly and note they are internal (not API-facing).

---

### ISSUE 4 — CRITICAL: Phase A8 backend integration is incomplete — `run_plan` not called

The agent plan's Phase A8 (lines 540–571) shows the agent directly streaming from `graph.astream_events`. This is correct for the SSE endpoint, **but it does not show how the agent nodes call `run_plan`**.

The backend IMPLEMENTATION_PLAN cross-cutting rule (line 156) states:
> "The agent's `gather_data`, `recommend`, `predict_yield`, and `optimize` nodes call the **same** stage functions, never their own copies."

The agent plan shows the nodes calling `tools.py` wrappers, but does not explicitly state that these tool wrappers call the backend service functions (e.g. `services/prices.py`, `services/weather.py`) rather than reimplementing them.

**Action:** Add a paragraph to Phase A2/A8 explicitly stating:
> `tools.py` wrappers **do not duplicate service logic**. Each tool calls the corresponding function in `app/services/` or `app/ml/`. The agent and `/api/plan` are guaranteed to produce identical results because they call the same code paths.

---

### ISSUE 5 — MAJOR: `candidate_crops` Gate 3 water scenario ambiguous

`candidate_crops` Phase M1 (line 136): "crop water need fits available water" — but with 3 water budgets (drought/normal/excess), it's not stated which budget is used for Gate 3.

ml/SPECS §8.4a relaxation step 3 is "drop most water-hungry crop" — implying the drought budget is the conservative gate.

**Action:** Clarify in Phase M1:
> Gate 3 uses the **drought** `WaterBudget` (most conservative). A crop that fits drought water also fits normal and excess. Crops that fail only at drought are not excluded at gate 3; their water need is shown and the drought-safe strategy avoids them via the optimizer constraint.

---

### ISSUE 6 — MAJOR: Long-duration crop per-year normalization entirely missing

ml/SPECS §3A (line 80) says:
> "per-acre profit is also divided by `duration_days / 365`, so a 12-month crop is compared with a 4-month crop per acre per year. The response carries `duration_days` and `profit_rs_per_acre_per_year`."

The agent plan has **no mention** of this normalization — not in Phase M5 (Optimizer), not in Phase M1 (candidate filter), not in AgentState, not in the explain prompt. The backend schema `CropOption` type list in IMPLEMENTATION_PLAN §4 also lacks `profit_rs_per_acre_per_year`.

**Action:**
1. Add `profit_rs_per_acre_per_year` to the `CropOption` type in the agent plan §4 AgentState schema note, and flag it to the backend owner to add to `schemas.py`.
2. Add to Phase M5 (Optimizer): "For crops with `duration_days > 120`, normalize margin by `duration_days / 365` before adding to the objective; return `profit_rs_per_acre_per_year` alongside `profit_rs_per_acre`."
3. Add to the `explain` prompt note: "For sugarcane, state the per-year figure alongside the total."
4. Add `SINGLE_SEASON_COMPARISON` warning emission to Phase M5.

---

### ISSUE 7 — MAJOR: `ask_missing` is ambiguously described as LLM in ml/SPECS but correctly rule-based in agent plan

**ml/SPECS §8.4 table (line 248):** `ask_missing` — listed in the LLM calls table.  
**ml/SPECS §8.4 (line 263):** "route and ask_missing are rule-based."  
**Agent Plan Phase A3 (line 428):** Correctly states "rule-based, no LLM."

The ml/SPECS inconsistency creates a developer risk. The agent plan is correct.

**Action:** Add a bold note to Phase A3:
> ⚠️ `ask_missing` uses a **translated string template** per field (see `prompts.py`), **not an LLM call**. This is deliberately rule-based to stay within the 3-call LLM budget. ml/SPECS §8.4 table entry is a known inconsistency; the prose below the table is the authoritative decision.

---

### ISSUE 8 — MAJOR: `profile_patch` from E1 not handled in graph flow

**Backend SPECS §5.2 E1:**
```json
"profile_patch": null  // set when the farmer edits the profile card, e.g. { "land_acres": 3 }
```

The agent plan Phase A3 graph has only `route → new_plan / follow_up / question`. It does not handle the `profile_patch` path where there is no natural-language message — just a direct profile edit from the frontend card.

**Action:** Add `profile_patch: dict | None` to `AgentState` (§4), and add to the `route` node:
```
if profile_patch is set AND message is empty:
  → merge patch directly into profile (no LLM call)
  → route = follow_up
  → skip extract_profile
  → go to gather_data (cached, fast)
```

---

### ISSUE 9 — MAJOR: E3 reoptimize checkpointer write-back not covered in memory.py plan

**Backend SPECS §5.2 E3 and IMPLEMENTATION_PLAN API.3:**
> "writes risk back to agent checkpointer; bumps `version`; includes `previous_version`"

E3 is in `backend/app/api/plan.py` (not in the agent). After re-optimizing, it must write the changed `risk_appetite`, `budget_rs`, or `land_acres` back into the LangGraph checkpointer so the next chat turn starts from the correct state.

The agent plan Phase A5 only describes the forward (chat → memory) direction, not this external write.

**Action:** Add to Phase A5 (Memory):
```python
async def update_profile_fields(thread_id: str, patch: dict) -> None:
    """
    Called by E3 /api/plans/{id}/reoptimize to write the changed field
    (risk_appetite / budget_rs / land_acres / safety_scenario) back into
    the LangGraph SQLite checkpointer for thread_id.
    
    The next chat turn then reads the updated profile from memory, so the
    profile-card slider and the plan-slider can never disagree.
    
    Import and call from backend/app/api/plan.py after the re-optimize succeeds.
    """
    saver = SqliteSaver.from_conn_string(settings.CACHE_DB_PATH)
    # Load checkpoint → merge patch into profile → save back
```

---

### ISSUE 10 — MODERATE: `warnings[].code` literals missing from constants

After the backend SPECS update, `warnings[].code` now has 9 values including `SINGLE_SEASON_COMPARISON`. The agent plan §6 does not list the warning code set, so the optimizer author has no reference for what to emit.

**Action:** Add to `constants.py` in §6:
```python
# Emit these from the optimizer/pipeline; must match backend/SPECS §5.1 Literal
WARN_SINGLE_SEASON_COMPARISON = "SINGLE_SEASON_COMPARISON"  # sugarcane in any allocation
WARN_SINGLE_CROP_ELIGIBLE     = "SINGLE_CROP_ELIGIBLE"       # only one crop passed filters
WARN_OLD_COST_YEAR            = "OLD_COST_YEAR"              # DES costs are 2022-23
WARN_PRICE_NOT_ADJUSTED       = "PRICE_NOT_ADJUSTED"         # < 3 years for seasonal ratio
```

---

### ISSUE 11 — MODERATE: `CANAL_DUTY` constant missing from §6

ml/SPECS §7A lists `CANAL_DUTY` as an assumption constant. Agent plan §6 does not include it.

**Action:** Add to `constants.py` §6:
```python
CANAL_DUTY: float | None = None
# m3/acre/season for canal-irrigated farms; from Maharashtra WRD duty tables.
# Set to None until cited in SOURCES.md. When None, canal_share = 0 even
# when canal_access is True, and a ASSUMED_CANAL_DUTY warning is emitted.
```

---

### ISSUE 12 — MODERATE: `transcribe()` must not hardcode `audio/webm` — iOS sends `audio/mp4`

Phase A1 `SarvamClient.transcribe` accepts `content_type: str` but the plan body doesn't warn against hardcoding. Sarvam's multipart upload requires the correct MIME type for the file part; if the service hardcodes `audio/webm`, iOS judges cannot use the mic.

**Action:** Add to Phase A1 docstring:
```python
async def transcribe(self, audio_bytes: bytes, content_type: str, language: str | None) -> dict:
    """
    IMPORTANT: forward `content_type` verbatim as the multipart part's Content-Type.
    Never hardcode 'audio/webm'.
    
    Accepted MIME types (matches E5 contract):
      audio/webm, audio/ogg, audio/wav, audio/mpeg, audio/mp4
    
    iOS Safari (MediaRecorder) produces audio/mp4. Hardcoding webm breaks
    the mic for any judge on an iPhone.
    """
```

---

## Summary Table

| # | Severity | Issue | Phase to fix |
|---|---|---|---|
| 1 | 🔴 Critical | `candidate_crops` uses `LocationResult`/`str`/singular `WaterBudget` | Phase M1 |
| 2 | 🔴 Critical | `build_scenarios` uses `LocationResult`/`str` | Phase M3 |
| 3 | 🔴 Critical | `tools.py` uses non-schema types (`LocationResult`, `WeatherForecast`, etc.) | Phase A2 |
| 4 | 🔴 Critical | Phase A8 doesn't state that tools call backend service functions (not duplicates) | Phase A2/A8 |
| 5 | 🟠 Major | Gate 3 doesn't specify which of 3 water budgets to use | Phase M1 |
| 6 | 🟠 Major | Long-duration crop per-year normalization missing entirely | Phase M5 + §4 |
| 7 | 🟠 Major | `ask_missing` ambiguous (LLM vs rule-based) — agent plan is right, needs clarification note | Phase A3 |
| 8 | 🟠 Major | `profile_patch` not in AgentState or route node | Phase A3 + §4 |
| 9 | 🟠 Major | E3 reoptimize checkpointer write-back not in `memory.py` plan | Phase A5 |
| 10 | 🟡 Moderate | Warning code constants missing (including `SINGLE_SEASON_COMPARISON`) | §6 |
| 11 | 🟡 Moderate | `CANAL_DUTY` constant missing | §6 |
| 12 | 🟡 Moderate | `transcribe()` must not hardcode `audio/webm` | Phase A1 |
