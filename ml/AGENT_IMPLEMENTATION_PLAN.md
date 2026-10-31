# AgriPulse LangGraph Agent — Technical Implementation Plan

**File owner:** ML & AI lead  
**Works with:** `backend/SPECS.md`, `backend/IMPLEMENTATION_PLAN.md`, `ml/SPECS.md`  
**Branch:** `backend`  
**Stack:** Python · LangGraph · Sarvam AI · CVXPY · scikit-learn · SHAP · pytest

---

## Changelog

| Version | What changed |
|---|---|
| v2 (current) | 14 bugs fixed: type names corrected against `schemas.py`, stub signatures aligned, Sarvam API params fixed from live docs, LangGraph API versions pinned, grounding tolerance fixed |
| v1 | Initial draft |

---

## 0. API Keys — status in `.env`

| Key | Variable | Status |
|---|---|---|
| Sarvam AI (chat, STT, TTS) | `SARVAM_API_KEY` | ✅ Present |
| data.gov.in (Agmarknet prices) | `DATA_GOV_IN_API_KEY` | ✅ Present |

Model IDs (now filled in `.env`):

```ini
SARVAM_CHAT_MODEL=sarvam-105b
SARVAM_STT_MODEL=saaras:v4
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_FALLBACK_MODELS=glm5.3-flash,deepseekv4.1-flash-1017
```

> `SARVAM_FALLBACK_MODELS` applies to **chat only**. STT always uses `SARVAM_STT_MODEL`;
> TTS always uses `SARVAM_TTS_MODEL`. Do not iterate `sarvam_fallback_list` in `speech.py`.

**Sarvam base URL:** `https://api.sarvam.ai`  
**Auth header:** `api-subscription-key: <SARVAM_API_KEY>`

### Sarvam endpoint reference (verified from live docs)

| Use | Method | URL | Key params |
|---|---|---|---|
| Chat | POST | `/v2/chat/completions` | `model`, `messages[]`, `stream`, `response_format`, `tools[]`, `temperature` |
| STT | POST | `/speech-to-text` | `file` (multipart), `model=saaras:v4`, `language_code` — **do NOT send `mode`** (only valid for saaras:v3) |
| TTS | POST | `/text-to-speech` | `text`, `language_code` (not `target_language_code`), `model=bulbul:v3`, `speaker`, `pace` |

**Sarvam chat structured output:**  
`response_format={"type": "json_schema", "json_schema": {...}}` — valid on `sarvam-105b`.  
Use `{"type": "json_object"}` for simpler JSON-only enforcement.

---

## 1. Directory layout

```
backend/app/
├── agent/
│   ├── __init__.py
│   ├── client.py           AG.1  Sarvam client (chat + fallback; STT/TTS delegate to speech.py)
│   ├── graph.py            AG.5  LangGraph StateGraph definition
│   ├── nodes.py            AG.3/4/5/6/8/9/10  All node functions
│   ├── tools.py            AG.2  Tool wrappers (one per backend service or ML fn)
│   ├── memory.py           AG.7  AsyncSqliteSaver checkpointer setup
│   ├── prompts.py                Prompt templates in mr / hi / en
│   ├── grounding.py        AG.9  Number grounding checker
│   └── templates.py        AG.10 No-LLM fallback explanation builder
├── ml/
│   ├── __init__.py
│   ├── stubs.py            ← C.3, already merged — replace per function below
│   ├── candidate.py        ML.1  Crop filter (implements stubs.candidate_crops)
│   ├── baseline.py         ML.3  Hierarchical median
│   ├── yield_model.py      ML.4  HistGradientBoosting + inference
│   ├── suitability.py      ML.4b SHAP suitability (implements stubs.suitability)
│   ├── scenarios.py        ML.5  Analogue-year scenarios (implements stubs.build_scenarios)
│   ├── water_need.py       ML.7  Kc × ET₀ water need (implements stubs.crop_water_need)
│   ├── fertilizer.py       ML.8  RDF plan (implements stubs.fertilizer_plan)
│   ├── optimizer.py        OPT.1–5 LP + QP (implements stubs.optimize, stubs.compare_strategies)
│   └── constants.py              All declared modelling constants (§6 below)
ml/
├── experiments/
│   ├── EXP_01_baseline/    train_baseline.py
│   ├── EXP_02_yield_model/ train_yield.py
│   ├── EXP_03_fertilizer/  eval_fertilizer.py
│   └── EXP_04_optimizer/   eval_optimizer.py
├── models/                 saved .pkl + _meta.json  (git-lfs)
└── reports/                EXP_01.md … EXP_04.md, language_review.md
```

---

## 2. Canonical type names (from `backend/app/schemas.py` — use exactly these)

> Bug class B1 in v1: plan used `LocationResult`, `InfeasibilityReport`, `WaterBudget` (singular).
> Correct names from schemas.py:

| v1 (wrong) | v2 (correct) | Defined in |
|---|---|---|
| `LocationResult` | `Location` | schemas.py line 37 |
| `InfeasibilityReport` | `Infeasibility` | schemas.py line ~290 |
| `WaterBudget` (singular in candidate_crops) | `list[WaterBudget]` | stubs.py signature |
| `NO_AREA_DATA` (ExcludedReasonCode) | `NOT_GROWN_IN_DISTRICT` | schemas.py line ~115 |
| `conditions: dict` in suitability | `conditions: Scenario` | stubs.py signature |
| `season: str` in build_scenarios | `season: Season` | stubs.py signature |

All ML function signatures must match **`backend/app/ml/stubs.py` exactly** — that file is the contract.

---

## 3. Build order (dependency chain)

```
ML data layer first — agent depends on it, not vice versa

ML.2  clean yield_training.csv
  └─ ML.3  baseline  (EXP_01)
       └─ ML.4  yield model  (EXP_02)
            ├─ ML.4b suitability + SHAP
            └─ ML.5  scenarios
                 └─ ML.6  scenario yields  (calls predict_yield per scenario)

ML.7  crop water need  (independent — only needs crop_water_coefficients.csv)
ML.8  fertilizer plan  (independent — only needs fertilizer_rdf.csv + fertilizer_prices.csv)

ML.1  candidate_crops  (needs ML.4b water_need for gate 3)

OPT.1  LP baseline  (HiGHS)
  └─ OPT.2  QP  (CVXPY)
       └─ OPT.3  four strategies  (EXP_04)
            └─ OPT.4  infeasibility report
                 └─ OPT.5  impact vs Traditional

AG.1  Sarvam client  ← needs SARVAM_API_KEY + model IDs in .env
AG.2  tools          ← needs ML.1–OPT.5 all done
AG.3  extract_profile
AG.4  ask_missing    ← rule-based, no LLM
AG.5  graph          ← needs AG.1–AG.4
AG.6  relax ladder   ← code, no LLM
AG.7  memory
AG.8  explain        ← needs AG.1
AG.9  grounding_check
AG.10 template fallback

Backend integration: replace stub in app/api/agent.py with graph.astream_events()
```

---

## 4. Phase-by-phase implementation

### Phase M1 — Data cleaning and baseline

**`ml/experiments/EXP_01_baseline/train_baseline.py`**
- Load `yield_training.csv`.
- Remove aggregate rows ("Total foodgrain", "Pulses total"), impossible yields (jowar > 10 t/ha), coconut rows (mixed units).
- Record removal counts per reason → `ml/reports/EXP_01_yield_baseline.md`.
- Compute district+crop+season median yields → `ml/models/baseline_medians.pkl + _meta.json`.
- Report out-of-time MAE/RMSE per crop (train 1997–2008, test 2012–2014).

**`backend/app/ml/baseline.py`** — implements the inference half:

```python
def hierarchical_median(crop_id: str, district: str, season: str) -> YieldPrediction:
    """District median → state median → crop median.
    Returns YieldPrediction with status='official_dataset', fallback_used=True
    when district-level data was absent.
    Never returns None — crop-level median always exists.
    """
```

---

### Phase M2 — Yield model + SHAP

**`ml/experiments/EXP_02_yield_model/train_yield.py`**

Model A (shipped — no lag features):
```
features:
  identity:  district (label-encoded), crop (label-encoded), season (label-encoded), year
  weather:   season_rainfall_mm, rainfall_departure_pct, rainy_days, max_dry_spell_days,
             mean_temp_c, max_temp_c, heat_stress_days, et0_total_mm, mean_humidity_pct
  soil:      soil_n_kg_ha, soil_p_kg_ha, soil_k_kg_ha, soil_ph, organic_carbon_pct
  water:     irrigated_pct, gw_category_code, gw_extraction_pct, fertilizer_use_kg_ha
target: yield_t_per_ha

split: train 1997-2008 / val 2009-2011 / test 2012-2014  (by year, not random)
seed: random_state=42
model: HistGradientBoostingRegressor
```

Model B (reference only, not shipped — adds `yield_prev_year`, `yield_3yr_avg`).

Metrics must be from the time-split run, not the all-years fit. Both are reported.

**`backend/app/ml/yield_model.py`**

```python
class YieldModelA:
    """Load ml/models/yield_model_a.pkl at import time (lru_cache on load).
    Never retrain at inference.
    """
    def predict(self, crop_id: str, location: Location, season: Season,
                conditions: Scenario) -> YieldPrediction:
        """
        - Encode inputs exactly as training pipeline.
        - Clip to district historical max; set clipped=True and add out_of_training_range.
        - Returns YieldPrediction(t_per_ha=SourcedValue(status='model'), clipped, out_of_training_range).
        """
```

**`backend/app/ml/suitability.py`** — implements `stubs.suitability`:

```python
def suitability(
    crop_id: str,
    location: Location,      # NOT LocationResult
    season: Season,          # NOT str
    conditions: Scenario,    # NOT dict
) -> Suitability:
    """
    score = predicted_t_per_ha / 3yr_district_average_t_per_ha
    label = 'good' if score >= 1.05 else 'average' if score >= 0.90 else 'poor'
    top_factors: top-3 SHAP values from TreeExplainer
      - feature must be one of the 16 SuitabilityFeature literals in schemas.py
      - effect_quintal_per_acre = shap_value_t_per_ha × 10 × 0.404686
      - verify: baseline + sum(shap) ≈ prediction (TreeSHAP identity)
    fallback_used=True when per-crop out-of-time RMSE exceeds threshold → use baseline.
    """
```

---

### Phase M3 — Scenarios

**`backend/app/ml/scenarios.py`** — implements `stubs.build_scenarios`:

```python
def build_scenarios(
    location: Location,   # NOT LocationResult
    season: Season,       # NOT str
) -> list[Scenario]:
    """
    Source: district_rainfall_history.csv + district_climate_2010_2025.csv
    
    Water index per year:
      Kharif / Summer / Whole Year: season_rainfall_mm
      Rabi: 0.5 × rabi_rain + 0.5 × preceding_kharif_rain  (RABI_WATER_INDEX)
    
    Rank all years → P10=drought, P50=normal, P90=excess.
    
    Each Scenario carries:
      analogue_year (int), all_year_samples (list[SourcedValue]),
      probability (default 0.2/0.6/0.2; status='assumption'),
      ALL weather features for that year's season (rainfall_mm, et0_mm,
      rainy_days, max_dry_spell_days, mean_temp_c, max_temp_c,
      heat_stress_days, mean_humidity_pct).
    
    Probability adjustment: if current-season rain < drought analogue rain,
      shift weights toward Drought and set status='computed'.
    
    Raises AppError('DISTRICT_NOT_AGRICULTURAL') for
      'Mumbai City' and 'Mumbai Suburban' (NON_AGRICULTURAL_DISTRICTS constant).
    """
```

---

### Phase M4 — Water need and fertilizer

**`backend/app/ml/water_need.py`** — implements `stubs.crop_water_need`:

```python
def crop_water_need(
    crop_id: str,
    season: Season,
    scenario: Scenario,
    efficiency: float,
) -> WaterNeed:
    """
    Formula: need_mm = Σ_stages ( Kc_stage × ET0_stage − eff_rain_stage )⁺ / efficiency
    need_m3_per_acre = need_mm × 4.047

    Data sources:
      Kc + stage lengths: crop_water_coefficients.csv
      ET0 per stage: derived from scenario.et0_mm proportional to stage length
      Effective rain per stage: scenario.rainfall_mm × EFFECTIVE_RAIN_FACTOR
                                distributed proportionally by stage length
      Efficiency: irrigation_by_district.csv by method (flood/sprinkler/drip)

    Returns WaterNeed(
        drought=SourcedValue(need for drought scenario, m3/acre),
        normal=SourcedValue(...),
        excess=SourcedValue(...),
    )
    All three SourcedValues use status='computed'.
    """
```

> Note: `water_need.py` not `water.py` — matches the stubs.py `raise NotImplementedError` message.

**`backend/app/ml/fertilizer.py`** — implements `stubs.fertilizer_plan`:

```python
def fertilizer_plan(
    crop_id: str,
    fertilizer_prices: dict,   # {"dap_mrp": float, "urea_mrp": float, "mop_mrp": float}
) -> FertilizerPlan:
    """
    Step 1: Load N, P2O5, K2O kg/ha from fertilizer_rdf.csv. Convert to per acre (÷ 2.471).
    Step 2: Fixed conversion order:
              dap_bags  = p2o5_per_acre / (0.46 × 50)   (DAP: 46% P2O5, bag=50kg)
              n_from_dap = dap_bags × 50 × 0.18          (DAP also has 18% N)
              urea_bags = (n_per_acre - n_from_dap) / (0.46 × 50)  (Urea: 46% N)
              mop_bags  = k2o_per_acre / (0.60 × 50)    (MOP: 60% K2O)
    Step 3: cost_rs = dap_bags×dap_mrp + urea_bags×urea_mrp + mop_bags×mop_mrp
    Step 4: saving_vs_district_use_pct:
              district_n_p_k = fertilizer_use_by_district.csv for this district
              saving = (district_n_p_k - rdf_n_p_k) / district_n_p_k × 100
              Returns None (not 0) when district use is already below RDF.

    Returns FertilizerPlan with n_kg_per_acre, p2o5_kg_per_acre, k2o_kg_per_acre,
    urea_bags, dap_bags, mop_bags, cost_rs (SourcedValue, status='computed').
    NOTE: crop_price is NOT a parameter — RDF is fixed before optimization.
    """
```

---

### Phase M5 — Candidate crops

**`backend/app/ml/candidate.py`** — implements `stubs.candidate_crops`:

```python
def candidate_crops(
    profile: FarmProfile,
    location: Location,          # NOT LocationResult
    season: Season,
    water: list[WaterBudget],    # NOT singular WaterBudget
    today: date | None = None,
) -> tuple[list[Candidate], list[ExcludedCrop]]:
    """Three-gate filter (ML.1):

    Gate 1 — grown in district:
      DES area from district_crop_yields.csv > threshold in recent years
      for this season. Exclude with ExcludedReasonCode = 'NOT_GROWN_IN_DISTRICT'.

    Gate 2 — sowable now:
      crop_calendar.csv row for this crop+season:
        sowable if today in [sowing_start - 7d, sowing_end]
        opening_soon if sowing_start is within 21 days → set Candidate.opens_on
      Exclude with ExcludedReasonCode = 'NOT_SOWABLE_NOW'.

    Gate 3 — water-feasible:
      Call crop_water_need(crop_id, season, normal_scenario, efficiency).
      Compare need vs available water in normal WaterBudget.
      Exclude with ExcludedReasonCode = 'WATER_INFEASIBLE'.

    Also exclude with 'NO_REAL_PRICE' when price_history_monthly.csv has never
    had a real quote for this crop in this district or state (fallback chain exhausted).
    And 'NO_YIELD_DATA' when both yield model and baseline return no data for this crop.

    Long-duration crops (sugarcane 365d, banana 330d, orange 240d, pomegranate 180d):
      Add duration_days and profit_rs_per_acre_per_year to Candidate.
      Compare per-acre per-year, not per-season.

    Mumbai City / Mumbai Suburban: raise AppError('DISTRICT_NOT_AGRICULTURAL')
      before any gate runs.
    """
```

**Valid `ExcludedReasonCode` values** (from schemas.py — use only these):
```
NOT_GROWN_IN_DISTRICT  |  NOT_SOWABLE_NOW  |  WATER_INFEASIBLE
NO_REAL_PRICE  |  NO_YIELD_DATA  |  OVER_BUDGET
```

---

### Phase M6 — Optimizer

**`backend/app/ml/optimizer.py`** — implements `stubs.optimize` and `stubs.compare_strategies`:

```python
class Optimizer:
    """OPT.1–5.

    Four strategies on identical inputs (same land / budget / water / diversification):
      'traditional'      — DES district crop mix (season+price filtered); NOT forced feasible
      'lp_max_profit'    — SciPy HiGHS, expected profit only (λ=0)
      'qp_balanced'      — CVXPY Clarabel/OSQP, λ from profile.risk_appetite
      'qp_drought_safe'  — QP with water limit from drought WaterBudget

    Decision variable: x_i = acres of crop_i  (x_i ≥ 0)
    Objective (QP):
      max  Σ_s p_s · Σ_i margin(i,s) · x_i  −  λ · x'Σx  −  Σ_i γ_i · x_i²
      margin(i,s) = yield(i,s) [quintal/acre] × expected_harvest_price_i − cost_per_acre_i

    Constraints:
      Σ x_i ≤ L                              (land)
      Σ cost_i · x_i ≤ B                     (budget — seed+fertilizer+labour+…)
      Σ water_need(i, s*) · x_i ≤ W(s*)      (water in safety scenario s*)
      x_i ≤ CAP_n · L  for all i             (diversification; n = count of eligible crops)

    Diversification cap (adapts, never causes silent infeasibility):
      n=1 → 1.0 (only one crop; the answer says so)
      n=2 → 0.80
      n≥3 → 0.65

    Risk lambda: safe=1.0 / balanced=0.3 / max_profit≈0.0
    Saturation gamma: 0.0 (single farm; market saturation negligible)
    PSD ridge: add (PSD_RIDGE × trace(Σ)) × I to Σ before solving

    Risk matrix Σ:
      Rows/columns = crops. Entry (i,j) = cov of per-acre profit across all 29 historical years.
      Per-year yield from the model applied to each year's weather (1997-2025).
      Per-year price from real monthly history for the harvest month.
      Crops with < MIN_RISK_YEARS samples: variance taken from crop-group average.

    LP baseline (OPT.1): SciPy linprog / HiGHS with same constraints, λ=0, γ=0.
    Verify: optimize('lp_max_profit', inputs) must equal QP with λ=0.

    Relaxation ladder (code — not LLM — 8.4a, called from graph.py):
      Tried in this fixed order until feasible:
      1. CAP_TO_1: lift diversification cap to 1.0
      2. REDUCE_AREA: reduce planned area to max budget allows
      3. DROP_WATER_HUNGRY_CROP: remove crop with highest water_need, re-solve
      4. USE_NORMAL_SCENARIO_WATER: move water limit from drought→normal scenario
      → Still infeasible: feasible=False, allocations=[], full Infeasibility payload

    Traditional plan (OPT.3):
      DES area shares × farmer land, filtered to plan season + crops with real prices.
      NOT constrained to satisfy budget or water — if it exceeds them, report which
      limit it breaks and by how much in traditional_exceeds[].
    """

    def optimize(self, strategy: str, inputs: OptimizerInputs) -> StrategyResult: ...
    def compare_strategies(self, inputs: OptimizerInputs) -> list[StrategyResult]: ...
    def infeasibility_report(self, inputs: OptimizerInputs) -> Infeasibility: ...
    # Infeasibility (NOT InfeasibilityReport — that name does not exist in schemas.py)

    def impact_vs_traditional(
        self, recommended: StrategyResult, traditional: StrategyResult
    ) -> Impact: ...
    # Impact (NOT ImpactMetrics — that name does not exist in schemas.py)
```

---

### Phase A1 — Sarvam client (`backend/app/agent/client.py`)

```python
"""AG.1 — Sarvam chat client with model fallback.

Scope: chat completions ONLY.
STT and TTS remain in app/services/speech.py (already correct after v1 fix).
Do NOT add STT/TTS here — it would duplicate the service layer.

Chat endpoint: POST https://api.sarvam.ai/v2/chat/completions
Auth: api-subscription-key: <SARVAM_API_KEY>
Model order: SARVAM_CHAT_MODEL → each model in sarvam_fallback_list
Timeout per model: 15 s
On 5xx or timeout: try next model
On 429: exponential backoff (1s, 2s, 4s), max 3 retries per model
All models failed: raise SarvamAllModelsFailed — caller uses template answer
"""

from __future__ import annotations
import asyncio
import logging
import httpx
from app.config import settings

SARVAM_CHAT_URL = "https://api.sarvam.ai/v2/chat/completions"
_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=2.0)

class SarvamAllModelsFailed(Exception):
    pass

class SarvamClient:
    def __init__(self):
        self._headers = {
            "api-subscription-key": settings.SARVAM_API_KEY,
            "Content-Type": "application/json",
        }

    def _model_order(self) -> list[str]:
        """Primary model first, then fallbacks. Empty models are skipped."""
        models = [settings.SARVAM_CHAT_MODEL] + settings.sarvam_fallback_list
        return [m for m in models if m]

    async def chat(
        self,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> dict:
        """Try each model in order. Returns the full OpenAI-compatible response dict.

        response_format examples:
          {"type": "json_object"}              — valid JSON guaranteed
          {"type": "json_schema", "json_schema": {...}}  — structured output (sarvam-105b)
        """
        last_exc: Exception | None = None
        for model in self._model_order():
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                        resp = await client.post(
                            SARVAM_CHAT_URL,
                            headers=self._headers,
                            json={
                                "model": model,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": max_tokens,
                                **({"response_format": response_format} if response_format else {}),
                            },
                        )
                    if resp.status_code == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    resp.raise_for_status()
                    return resp.json()
                except httpx.TimeoutException as exc:
                    last_exc = exc
                    break   # timeout → try next model immediately
                except Exception as exc:
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
        raise SarvamAllModelsFailed(f"All Sarvam chat models failed: {last_exc}")
```

---

### Phase A2 — LangGraph graph (`backend/app/agent/graph.py`)

```python
"""AG.5 — LangGraph StateGraph.

LangGraph version: 0.2.x
Checkpointer: AsyncSqliteSaver (NOT SqliteSaver — the graph is async)
Import: from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

astream_events version: use version="v1" (default in LangGraph 0.2).
"v2" requires explicit opt-in and is not stable in 0.2.x.
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("route", route_node)
    graph.add_node("extract_profile", extract_profile_node)
    graph.add_node("ask_missing", ask_missing_node)
    graph.add_node("gather_data", gather_data_node)
    graph.add_node("recommend_crops", recommend_crops_node)
    graph.add_node("predict_yield", predict_yield_node)
    graph.add_node("optimize", optimize_node)
    graph.add_node("check_feasibility", check_feasibility_node)
    graph.add_node("relax_constraint", relax_constraint_node)
    graph.add_node("explain", explain_node)
    graph.add_node("grounding_check", grounding_check_node)
    graph.add_node("respond", respond_node)
    graph.add_node("answer_from_memory", answer_from_memory_node)
    graph.add_node("save_memory", save_memory_node)

    graph.set_entry_point("route")
    # Edges defined separately — see §4.3 full graph

    return graph

async def get_compiled_graph(db_path: str):
    """Call once at startup; reuse the compiled graph for all requests."""
    checkpointer = AsyncSqliteSaver.from_conn_string(db_path)
    return build_graph().compile(checkpointer=checkpointer)
```

#### 4.3 Full graph flow

```
START → route
route → "answer_from_memory" (if route == "follow_up" or "question")
route → "extract_profile"    (if route == "new_plan")

answer_from_memory → respond → save_memory → END

extract_profile → "ask_missing"  (if state.missing is not empty)
extract_profile → "gather_data"  (if state.missing is empty)

ask_missing → END   (emits question SSE event; turn ends here)

gather_data → "recommend_crops"
  └─ no_data edge: gather_data → respond → save_memory → END
                   (when no services returned real data for any crop)

recommend_crops → predict_yield
predict_yield   → optimize
optimize        → check_feasibility

check_feasibility → explain              (if feasible and relaxations < 4)
check_feasibility → relax_constraint     (if not feasible and relaxations < 4)
check_feasibility → respond              (if still not feasible after 4 relaxations)

relax_constraint → optimize   (loop; max 3 iterations before check_feasibility gives up)

explain → grounding_check
grounding_check → respond                (if grounded or retry_count >= 2)
grounding_check → explain                (if not grounded and retry_count < 2)

respond → save_memory → END
```

---

### Phase A3 — AgentState schema

```python
from __future__ import annotations
from typing import Annotated, Literal
from langgraph.graph.message import add_messages
from app.schemas import (
    FarmProfile, Location, Season, Scenario, WaterBudget,
    Candidate, ExcludedCrop, StrategyResult, Infeasibility,
    TraceEvent, ChatMessage,
)

class AgentState(TypedDict):
    # Conversation identity
    thread_id: str
    message: str
    language: Literal["mr", "hi", "en"]
    route: Literal["new_plan", "follow_up", "question"]  # NOT bare str

    # Profile
    profile: FarmProfile | None
    missing: list[str]           # missing required fields

    # Data gathering
    location: Location | None    # NOT LocationResult
    weather: dict | None
    soil: dict | None
    scenarios: list[Scenario]
    water: list[WaterBudget]     # one per scenario (3 total)
    prices: dict                 # crop_id → CropPrice data
    costs: dict                  # crop_id → CostBreakdown data

    # ML results
    candidates: list[Candidate]
    excluded: list[ExcludedCrop]
    scenario_yields: dict        # crop_id → {"drought": YieldPrediction, ...}

    # Optimizer results
    strategies: list[StrategyResult]
    feasibility: Infeasibility | None   # NOT InfeasibilityReport
    relaxations: list[str]              # log of RelaxationApplied step codes
    relaxation_count: int               # 0–4; stops the relax loop

    # Explanation
    explanation_text: str
    explanation_grounded: bool
    grounding_retry_count: int   # 0–2

    # Output
    trace: list[TraceEvent]
    messages: Annotated[list, add_messages]
```

---

### Phase A4 — Node implementations (`backend/app/agent/nodes.py`)

#### `route` (rule-based)

```python
def route_node(state: AgentState) -> AgentState:
    """Decide: new_plan / follow_up / question.

    new_plan:   required profile fields are not all known yet, OR message contains
                a location or land/budget number.
    follow_up:  a plan exists in memory AND message contains a changed fact
                (number, water_source, risk word, crop name).
    question:   a plan exists AND message is a question about it (no changed fact).

    This is entirely rule-based — no LLM call.
    """
```

#### `extract_profile` (AG.3, LLM call 1)

```python
async def extract_profile_node(state: AgentState) -> AgentState:
    """LLM call 1 of 3 (max).

    Use SarvamClient.chat() with:
      model: SARVAM_CHAT_MODEL (sarvam-105b)
      response_format: {"type": "json_object"}
      temperature: 0.1  (low — structured extraction)
      System prompt from prompts.EXTRACT_PROFILE_SYSTEM[state["language"]]
      User prompt: state["message"]

    Parse JSON → FarmProfile fields.
    Post-LLM normalization (plain code):
      1 guntha   = 0.025 acres
      1 hectare  = 2.471 acres
      "70 हजार"  = 70000  (hazar/हजार × 1000)
      "५ एकर"    = 5      (Devanagari → int via unicodedata)
      Devanagari digits: map ०→0 … ९→9

    Missing required fields → state["missing"] (never invented).
    On SarvamAllModelsFailed: parse state["message"] with regex fallback
      (extract numbers for land/budget, first capitalised word for location).
    """
```

#### `gather_data` (parallel tools, no LLM)

```python
async def gather_data_node(state: AgentState) -> AgentState:
    """Run all data services in parallel with asyncio.gather.

    Services called (each from app/services/):
      location.locate(profile.location_text)  → state["location"]
      weather.get_weather(location)            → state["weather"]
      soil.get_soil(location)                  → state["soil"]

    Then sequentially (depends on location):
      scenarios.build_scenarios(location, season)      → state["scenarios"]
      water_svc.build_water_budgets(profile, location, scenarios, weather)
                                                        → state["water"]
      prices.get_prices(location.district, crop_ids)   → state["prices"]
      costs.get_costs(location.district, crop_ids)     → state["costs"]

    Every call is wrapped in try/except; failures emit a trace event
    with status='failed' and add the appropriate Warning code.
    No data for any crop → set a "no_data" flag in state; the graph
    routes to respond with an explanation of what is missing.
    """
```

#### `explain` (AG.8, LLM call 2)

```python
async def explain_node(state: AgentState) -> AgentState:
    """LLM call 2 of 3 (max; +1 retry on grounding failure).

    System prompt from prompts.EXPLAIN_SYSTEM[state["language"]] which includes:
      'You are an agricultural advisor. Reply in {language} only.'
      'Use ONLY the numbers listed below. Do not invent any figure.'
      'Address the farmer directly: आपण (Marathi) / आप (Hindi) / you (English).'
      'Mention: best crop, why (top SHAP factor), expected profit, water saved.'
      'Round yield to 2 significant figures (quintals/acre). Round money to nearest 100.'
      'Max 120 words. Output JSON: {"text": str, "language": str}.'

    User prompt: formatted dump of:
      best strategy allocations, profit by scenario, water saved %, SHAP top factors.
    All source numbers listed inline → model cannot invent values.

    response_format: {"type": "json_object"}
    temperature: 0.3
    max_tokens: 300

    On SarvamAllModelsFailed → use templates.build_template_explanation().
    """
```

#### `grounding_check` (AG.9)

```python
def grounding_check_node(state: AgentState) -> AgentState:
    """Check every number in explanation_text appears in the tool outputs.

    Normalise before matching:
      1. Devanagari digits → ASCII: ०→0 … ९→9
      2. Strip Indian digit grouping: '1,00,000' → 100000
      3. Expand written numbers:
           hazar / हजार     × 1000
           lakh  / लाख      × 100000
           crore / करोड     × 10000000
      4. Extract all numbers from normalised text (regex r'\\d+\\.?\\d*').
      5. For each extracted number, check if there exists a source number sv such that
           abs(extracted - sv) / max(sv, 1) ≤ GROUNDING_TOLERANCE
         where GROUNDING_TOLERANCE = 0.05  (5% — not 1%)
         Rationale: 'nearest 100' rounding on money values of e.g. 50,000
         gives up to 0.2% variance; '2 sig figs' on yields of e.g. 8.3 qt/acre
         gives up to 5% variance. 5% covers both.
      6. A number that matches nothing → grounding fails.

    state["explanation_grounded"] = True | False
    state["grounding_retry_count"] += 1
    """
```

---

### Phase A5 — Memory (`backend/app/agent/memory.py`)

```python
"""AG.7 — Async LangGraph SQLite checkpointer.

LangGraph 0.2 requires AsyncSqliteSaver for async graphs.
SqliteSaver (sync) will deadlock when called from async code.

Correct import:
  from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  ← use this
  NOT: from langgraph.checkpoint.sqlite import SqliteSaver       ← sync, wrong

The checkpointer manages its own tables inside settings.CACHE_DB_PATH.
LangGraph state is keyed by thread_id via config["configurable"]["thread_id"].

Follow-up: a message with a changed fact passes through extract_profile again
  with the changed field patched onto the existing profile from checkpointer.
  gather_data reuses upstream_cache (same district), so re-runs complete in < 2 s.
"""
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
```

---

### Phase A6 — Template fallback (`backend/app/agent/templates.py`)

```python
"""AG.10 — No-LLM explanation builder.

Triggered when: SarvamAllModelsFailed raised OR grounding fails twice.
Never returns an empty answer — the demo never shows a blank screen.

Template selects by: language × crop_count (1 / 2 / 3+).
Uses only optimizer allocations and profit numbers (already in state).

Marathi (1 crop):
  "तुमच्या {land:.1f} एकर जमिनीसाठी {crop} ({acres:.1f} एकर) लावणे सर्वोत्तम आहे.
   अपेक्षित नफा: Rs.{profit:,.0f}. पाणी बचत: {water_saved:.0f}%."

Hindi (1 crop):
  "आपकी {land:.1f} एकड़ जमीन के लिए {crop} ({acres:.1f} एकड़) सबसे अच्छा है.
   अनुमानित लाभ: Rs.{profit:,.0f}. पानी की बचत: {water_saved:.0f}%."

English (1 crop):
  "For your {land:.1f}-acre farm, {crop} ({acres:.1f} ac) gives the best return.
   Expected profit: Rs.{profit:,.0f}. Water saved: {water_saved:.0f}%."

2-crop and 3+ templates follow the same pattern with "and" / "आणि" / "और".
provider field in Explanation is set to "template".
grounded is set to False.
"""
```

---

### Phase A7 — Prompts (`backend/app/agent/prompts.py`)

```python
"""Prompt constants for extract_profile and explain.

Rules that apply to every prompt:
1. Ends with exactly: "Output ONLY the JSON object. No markdown, no prose."
2. extract_profile: lists every FarmProfile field with its type and unit.
   Includes: "If the farmer did not mention a number, output null for that field."
3. explain: lists all source numbers inline in the user prompt, so the model
   sees them and cannot hallucinate different values.
4. Language variable is injected per call — prompts are templates, not hardcoded strings.
"""

EXTRACT_PROFILE_SYSTEM: dict[str, str] = {
    "mr": "...",   # Marathi system prompt
    "hi": "...",   # Hindi
    "en": "...",   # English
}

EXPLAIN_SYSTEM: dict[str, str] = {
    "mr": "...",
    "hi": "...",
    "en": "...",
}
```

---

### Phase A8 — Backend integration

**File to edit:** `backend/app/api/agent.py`

Replace the `run_plan()` stub with the real graph call:

```python
from app.agent.graph import get_compiled_graph

# Compiled graph is initialised once at startup (in lifespan) and stored on app.state
# app.state.agent_graph = await get_compiled_graph(settings.CACHE_DB_PATH)

@router.post("/agent/chat")
async def agent_chat(request: Request, body: dict):
    graph = request.app.state.agent_graph
    thread_id = body.get("thread_id") or f"th_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: dict = {
        "message": body.get("message", ""),
        "language": body.get("language", "mr"),
        "thread_id": thread_id,
        "missing": [],
        "scenarios": [],
        "water": [],
        "candidates": [],
        "excluded": [],
        "scenario_yields": {},
        "strategies": [],
        "relaxations": [],
        "relaxation_count": 0,
        "explanation_text": "",
        "explanation_grounded": False,
        "grounding_retry_count": 0,
        "trace": [],
        "messages": [],
        "route": "new_plan",   # route node will overwrite this
    }

    async def _stream():
        yield {"event": "thread", "data": json.dumps({"thread_id": thread_id})}
        try:
            async for event in graph.astream_events(
                initial_state,
                config=config,
                version="v1",   # LangGraph 0.2 default — NOT "v2"
            ):
                sse = _langgraph_event_to_sse(event)
                if sse:
                    yield sse
        except Exception as exc:
            logger.exception("Agent stream error")
            yield {"event": "error", "data": json.dumps({
                "error": {"code": "INTERNAL", "message": str(exc),
                          "user_message": {"mr": "त्रुटी झाली.", "hi": "त्रुटि हुई.", "en": "An error occurred."},
                          "retryable": True, "details": {}}})}
        yield {"event": "done", "data": json.dumps({"ms": 0})}

    return EventSourceResponse(_stream(), ping=10)


def _langgraph_event_to_sse(event: dict) -> dict | None:
    """Map LangGraph astream_events output to the SPECS §5.2 E1 SSE schema.

    LangGraph event kinds used:
      on_chain_start / on_chain_end  → trace events per node
      on_custom_event                → explicit SSE payloads emitted by nodes
        Nodes emit custom events via: langgraph_sdk or via state fields
        watched in the stream mapper.

    SSE events the frontend expects (in order):
      thread    → emitted before graph starts (above)
      profile   → after extract_profile node
      trace     → after each gather_data sub-tool, recommend_crops, optimize, explain
      plan      → after respond node constructs the PlanResult
      message   → after explain node completes
      done      → after graph ends (above)
    """
```

---

## 5. Tests required (per ML SPECS §9)

### ML tests (`backend/tests/ml/`)

| ID | File | Condition |
|---|---|---|
| ML.1 | `test_candidate.py` | Never suggests apple/coffee/jute for any Maharashtra district |
| ML.1 | same | Mumbai City → AppError('DISTRICT_NOT_AGRICULTURAL') |
| ML.2 | `test_cleaning.py` | Removal counts by reason; no aggregate rows remain |
| ML.3 | `test_baseline.py` | Out-of-time MAE reported; no data leakage (no future years in train) |
| ML.4 | `test_yield_model.py` | Time-split used; predictions clipped to district max |
| ML.4b | `test_suitability.py` | SHAP baseline + contributions ≈ prediction (TreeSHAP identity) |
| ML.4b | same | All top_factors use a valid `SuitabilityFeature` literal |
| ML.5 | `test_scenarios.py` | Rabi uses 0.5/0.5 mixed index; P10/P50/P90 verified on known district |
| ML.5 | same | All 34 agricultural districts return 3 scenarios |
| ML.7 | `test_water_need.py` | Hand-checked example (Chickpea Rabi, Beed): need within ±5% of reference |
| ML.8 | `test_fertilizer.py` | Bag counts reproduce by hand; saving_vs_district is null when district < RDF |

### Optimizer tests (`backend/tests/ml/test_optimizer.py`)

| Condition |
|---|
| λ=0 QP produces the same allocation as LP (within 0.1 acres) |
| Land / budget / water constraints never exceeded |
| QP drought-safe never exceeds drought WaterBudget |
| PSD check: `np.linalg.eigvalsh(Σ) >= -1e-8` after ridge |
| Infeasible input (budget=0) → `Infeasibility`, not exception or silent plan |
| Traditional plan exceeds constraints → `traditional_exceeds` reports which |

### Agent tests (`backend/tests/agent/`)

| ID | File | Condition |
|---|---|---|
| AG.3 | `test_extract_profile.py` | 10 sentences × mr/hi/en → correct FarmProfile fields |
| AG.3 | same | "70 हजार" → budget_rs=70000; "५ एकर" → land_acres=5; "2 गुंठे" → 0.05 acres |
| AG.4 | `test_extract_profile.py` | Missing budget in message → missing=["budget_rs"] |
| AG.6 | `test_graph.py` | Infeasible profile → relaxation tried → feasible plan returned |
| AG.7 | `test_graph.py` | "what if ₹50,000?" follow-up updates only budget_rs; other fields unchanged |
| AG.9 | `test_grounding.py` | Injected wrong number in explanation → grounding_check returns False |
| AG.9 | same | Same test with Devanagari digits → also False |
| AG.9 | same | Correct number rounded to 2 sig figs → True |
| AG.10 | `test_fallback.py` | SarvamAllModelsFailed → template answer in correct language, not empty |
| AG.10 | `test_fallback.py` | SARVAM_API_KEY="" → template answer (no crash) |

---

## 6. Constants file (`backend/app/ml/constants.py`)

All values declared here, never inline in code:

```python
from typing import Final

# Scenario building (ML.5)
SCENARIO_PERCENTILES: Final = (10, 50, 90)        # P10 / P50 / P90
SCENARIO_WEIGHTS_DEFAULT: Final = (0.2, 0.6, 0.2) # drought / normal / excess
RABI_WATER_INDEX: Final = (0.5, 0.5)              # rabi_weight / kharif_weight

# Water budget (§6 water formula)
EFFECTIVE_RAIN_FACTOR: Final = 0.75               # assumption; cite FAO-56 before demo
CATEGORY_CAP: Final[dict] = {                     # assumption; cite CGWB/GSDA before demo
    "Safe": 1.0,
    "Semi-critical": 0.7,
    "Critical": 0.4,
    "Over-exploited": 0.15,
}
CANAL_DUTY_M3_PER_ACRE: Final = 1200.0            # assumption; cite MH WRD tables

# Optimizer
DIVERSIFICATION_CAP: Final[dict] = {1: 1.0, 2: 0.80}
DIVERSIFICATION_CAP_DEFAULT: Final = 0.65         # for n >= 3
RISK_LAMBDA: Final[dict] = {
    "safe": 1.0, "balanced": 0.3, "max_profit": 0.0
}
SATURATION_GAMMA: Final = 0.0
PSD_RIDGE: Final = 1e-6                            # multiplied by trace(Σ)

# Suitability (ML.4b)
SUITABILITY_THRESHOLD_GOOD: Final = 1.05
SUITABILITY_THRESHOLD_AVERAGE: Final = 0.90

# Data quality
RAIN_DAY_MM: Final = 2.5                           # IMD definition of rainy day
HEAT_STRESS_C: Final = 35.0                        # flowering damage threshold
MIN_PRICE_YEARS: Final = 3                         # for seasonal_ratio
MIN_RISK_YEARS: Final = 5                          # for per-crop risk term
GROUNDING_TOLERANCE: Final = 0.05                  # 5% — covers 2 sig figs + nearest-100 rounding

# Crop calendar
SOWABLE_GRACE_DAYS: Final = 7
OPENS_SOON_DAYS: Final = 21

# Non-agricultural districts (no DES crop data)
NON_AGRICULTURAL_DISTRICTS: Final[frozenset] = frozenset({
    "Mumbai City", "Mumbai Suburban"
})

# Demo districts (section 9A of ml/SPECS.md)
DEMO_DISTRICTS: Final = ("Jalgaon", "Pune", "Ahilyanagar")
DEMO_DISTRICT_BACKUP: Final = "Nashik"
```

---

## 7. Bug index (all 14 fixed in this version)

| # | Bug | Where in v1 | Fix in v2 |
|---|---|---|---|
| B1 | `LocationResult` doesn't exist | all phases | Replaced with `Location` (schemas.py line 37) |
| B2 | `InfeasibilityReport` doesn't exist | Phase M6, AgentState | Replaced with `Infeasibility` (schemas.py) |
| B3 | `ImpactMetrics` doesn't exist | Phase M6 | Replaced with `Impact` (schemas.py) |
| B4 | `NO_AREA_DATA` is not a valid ExcludedReasonCode | Phase M5 | Replaced with `NOT_GROWN_IN_DISTRICT` |
| B5 | `candidate_crops` takes `water: WaterBudget` (singular) | Phase M5 | Corrected to `water: list[WaterBudget]` (matches stubs.py) |
| B6 | `build_scenarios` takes `season: str` | Phase M3 | Corrected to `season: Season` (matches stubs.py) |
| B7 | `suitability` takes `conditions: dict` | Phase M3 | Corrected to `conditions: Scenario` (matches stubs.py) |
| B8 | TTS iterates `sarvam_fallback_list` (chat models) | Phase A1, speech.py | TTS uses only `SARVAM_TTS_MODEL`; fallback list is chat-only |
| B9 | STT sends `mode=transcribe` with saaras:v4 | speech.py | `mode` removed — only valid for saaras:v3 per Sarvam docs |
| B10 | TTS sends `target_language_code` | speech.py | Corrected to `language_code` (Sarvam TTS field name) |
| B11 | Uses `SqliteSaver` (sync) for async graph | Phase A5 | Replaced with `AsyncSqliteSaver` from `langgraph.checkpoint.sqlite.aio` |
| B12 | `astream_events(version="v2")` | Phase A8 | Changed to `version="v1"` (LangGraph 0.2 default) |
| B13 | `route: str` in AgentState | §4 AgentState | Changed to `Literal["new_plan", "follow_up", "question"]` |
| B14 | `GROUNDING_TOLERANCE = 0.01` (too tight) | Phase A4 grounding | Changed to `0.05` (5%) — covers 2 sig fig rounding |

---

## 8. `.env` — required before AG.1

```ini
SARVAM_API_KEY=sk_xqo3hlac_...        # ✅ already present
DATA_GOV_IN_API_KEY=579b464d...        # ✅ already present
SARVAM_CHAT_MODEL=sarvam-105b          # ✅ filled
SARVAM_STT_MODEL=saaras:v4             # ✅ filled
SARVAM_TTS_MODEL=bulbul:v3             # ✅ filled
SARVAM_FALLBACK_MODELS=glm5.3-flash,deepseekv4.1-flash-1017  # ✅ filled
```

No other keys needed. Sarvam is the sole model provider.

---

## 9. Task checklist

### ML + data
- [ ] ML.2 clean yield_training.csv (aggregate rows, impossible yields, units)
- [ ] ML.3 baseline — `baseline.py` + EXP_01 report
- [ ] ML.4 yield model — `yield_model.py` + EXP_02 report
- [ ] ML.4b SHAP suitability — `suitability.py`
- [ ] ML.5 scenarios — `scenarios.py`
- [ ] ML.6 scenario yields (predict_yield per scenario per candidate)
- [ ] ML.7 crop water need — `water_need.py`
- [ ] ML.8 fertilizer plan — `fertilizer.py` + EXP_03 report
- [ ] ML.9 experiment reports (EXP_01–04)
- [ ] constants.py — all §6 constants

### Candidate + optimizer
- [ ] ML.1 candidate filter — `candidate.py`
- [ ] OPT.1 LP baseline (HiGHS)
- [ ] OPT.2 QP (CVXPY Clarabel/OSQP)
- [ ] OPT.3 four strategies — `optimizer.py` + EXP_04 report
- [ ] OPT.4 infeasibility report (`Infeasibility` type)
- [ ] OPT.5 impact vs Traditional (`Impact` type)

### Agent
- [ ] AG.1 `client.py` — Sarvam chat client with fallback
- [ ] AG.2 `tools.py` — tool wrappers
- [ ] AG.3 `nodes.py extract_profile_node` — LLM call + code normalization
- [ ] AG.4 `nodes.py ask_missing_node` — rule-based, no LLM
- [ ] AG.5 `graph.py` — full StateGraph with all edges
- [ ] AG.6 `nodes.py relax_constraint_node` — code ladder, max 4 steps
- [ ] AG.7 `memory.py` — `AsyncSqliteSaver`
- [ ] AG.8 `nodes.py explain_node` — LLM call with grounded prompt
- [ ] AG.9 `grounding.py` — 5% tolerance, Devanagari normalisation
- [ ] AG.10 `templates.py` — 3 languages × crop count
- [ ] `prompts.py` — EXTRACT_PROFILE_SYSTEM + EXPLAIN_SYSTEM per language
- [ ] Replace stub in `backend/app/api/agent.py`

### Delivery
- [ ] QA.3 demo script (Jalgaon / Pune / Ahilyanagar / Nashik backup)
- [ ] `ml/reports/language_review.md` signed off by native-speaker reviewer
- [ ] DD.5 README final setup steps + architecture diagram
- [ ] DD.6 5–7 slide deck
