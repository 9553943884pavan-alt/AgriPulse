# AgriPulse LangGraph Agent — Technical Implementation Plan

**File owner:** ML & AI lead  
**Works with:** `backend/SPECS.md`, `backend/IMPLEMENTATION_PLAN.md`, `ml/SPECS.md`  
**Branch:** `backend`  
**Stack:** Python · LangGraph · Sarvam AI · CVXPY · scikit-learn · SHAP · pytest

---

## 0. API Keys — status in `.env`

| Key | Variable | Status |
|---|---|---|
| Sarvam AI (chat, STT, TTS) | `SARVAM_API_KEY` | ✅ Present in `.env` |
| data.gov.in (Agmarknet prices) | `DATA_GOV_IN_API_KEY` | ✅ Present in `.env` |

Three model-ID slots are **empty** and must be filled before AG.1 can run:

```ini
# Correct Sarvam model IDs from docs (fill these in .env):
SARVAM_CHAT_MODEL=sarvam-105b
SARVAM_STT_MODEL=saaras:v4
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_FALLBACK_MODELS=glm5.3-flash,deepseekv4.1-flash-1017
```

**Why these values:**
- `sarvam-105b` — flagship 105B chat model, highest Indic quality, 128K context.
- `saaras:v4` — latest STT, auto language detection, supports WAV/MP3/MP4/WebM/OGG.
- `bulbul:v3` — stable TTS, 30+ voices, supports `mr-IN`, `hi-IN`, `en-IN`.
- Fallbacks — 1M-context flash models; fast, cheap, good Indic support.

**Sarvam API base URL:** `https://api.sarvam.ai`  
**Auth header:** `api-subscription-key: <SARVAM_API_KEY>`

### Sarvam endpoint reference (from live docs)

| Use | Method | URL | Key params |
|---|---|---|---|
| Chat | POST | `/v2/chat/completions` | `model`, `messages[]`, `stream`, `response_format`, `tools[]` |
| STT | POST | `/speech-to-text` | `file` (multipart), `model=saaras:v4`, `language_code`, `mode=transcribe` |
| TTS | POST | `/text-to-speech` | `text`, `language_code`, `model=bulbul:v3`, `speaker=meera` |

---

## 1. Directory layout

```
backend/app/
├── agent/                    ← everything in this section
│   ├── __init__.py
│   ├── client.py             AG.1  Sarvam API client (chat + fallback)
│   ├── graph.py              AG.5  LangGraph graph definition
│   ├── nodes.py              AG.3/4/5/6/8/9/10  All node functions
│   ├── tools.py              AG.2  Tool wrappers for services and ML
│   ├── memory.py             AG.7  SQLite checkpointer setup
│   ├── prompts.py                  System and user prompt templates (all 3 languages)
│   ├── grounding.py          AG.9  Number grounding checker
│   └── templates.py          AG.10 No-LLM fallback explanation builder
├── ml/
│   ├── __init__.py
│   ├── candidate.py          ML.1  Crop filter
│   ├── baseline.py           ML.3  Hierarchical median baseline
│   ├── yield_model.py        ML.4  Gradient boosting yield model + inference
│   ├── suitability.py        ML.4b SHAP suitability scoring
│   ├── scenarios.py          ML.5  Climate scenario builder
│   ├── water.py              ML.7  Crop water need (Kc × ET₀)
│   ├── fertilizer.py         ML.8  RDF fertilizer plan
│   └── optimizer.py          OPT.1–5  LP + QP + 4 strategies
ml/
├── experiments/
│   ├── EXP_01_baseline/      train_baseline.py
│   ├── EXP_02_yield_model/   train_yield.py
│   ├── EXP_03_fertilizer/    train_fertilizer.py
│   └── EXP_04_optimizer/     eval_optimizer.py
├── models/                   saved .pkl + _meta.json (git-lfs)
└── reports/                  EXP_01.md ... EXP_04.md, language_review.md
```

---

## 2. Build order (dependency chain)

```
ML data layer first — agent depends on it, not vice versa

ML.2 clean data
  └─ ML.3 baseline (EXP_01)
       └─ ML.4 yield model (EXP_02)
            ├─ ML.4b suitability + SHAP
            └─ ML.5 scenarios
                 └─ ML.6 scenario yields
ML.7 crop water need (independent)
ML.8 fertilizer plan (independent)
OPT.1 LP baseline
  └─ OPT.2 QP
       └─ OPT.3 four strategies (EXP_04)
            └─ OPT.4 infeasibility report
                 └─ OPT.5 impact vs Traditional

AG.1 Sarvam client      ← needs SARVAM_API_KEY + model IDs
AG.2 tools              ← needs ML.1–ML.8 + OPT
AG.3 extract_profile
AG.4 ask_missing
AG.5 graph
AG.6 relax_constraint
AG.7 memory
AG.8 explain
AG.9 grounding_check
AG.10 template fallback

Backend integration: replace stub in app/api/agent.py with real graph call
```

---

## 3. Phase-by-phase implementation

### Phase M1 — Data cleaning and baseline (`ml/`)

**File:** `backend/app/ml/candidate.py`

```python
def candidate_crops(
    profile: FarmProfile,
    location: LocationResult,
    season: str,
    water: WaterBudget,
    today: date | None = None,
) -> tuple[list[Candidate], list[ExcludedCrop]]:
    """ML.1 — Three-gate filter.

    Gate 1: district has DES area > threshold in recent years for that season.
    Gate 2: crop calendar — sowable today or opening within 21 days.
    Gate 3: crop water need (from ML.7) fits available water.
    Excluded crops carry a reason code: NO_AREA_DATA | OUT_OF_SEASON | WATER_INFEASIBLE.
    """
```

**File:** `backend/app/ml/baseline.py`

```python
def hierarchical_median(
    crop_id: str, district: str, season: str
) -> YieldPrediction:
    """ML.3 — District median → state median → crop median.

    Fallback order ensures a value always exists; fallback_used=True when
    district data is absent. Uses yield_training.csv, grouped by district+crop+season.
    """
```

**File:** `ml/experiments/EXP_01_baseline/train_baseline.py`
- Loads `yield_training.csv`, computes hierarchical medians, writes `ml/models/baseline_meta.json`.
- Report: out-of-time MAE/RMSE per crop → `ml/reports/EXP_01_yield_baseline.md`.

---

### Phase M2 — Yield model + SHAP (`ml/`)

**File:** `backend/app/ml/yield_model.py`

```python
class YieldModelA:
    """ML.4 — HistGradientBoostingRegressor, no lag features (Model A).

    Features: district, crop, season, year,
              weather over growing window (rainfall, rainy_days, dry_spell,
              mean_temp, max_temp, heat_stress_days, et0, humidity),
              soil (N, P, K, pH, organic_carbon),
              water inputs (irrigated_pct, gw_category_code, gw_extraction_pct,
              fertilizer_use_kg_ha).

    Training: time-split 1997–2008 train / 2009–2011 val / 2012–2014 test.
    Shipped: retrained on all years after metrics confirmed.
    Saved: ml/models/yield_model_a.pkl + yield_model_a_meta.json.
    """

    def predict(self, crop_id, district, season, conditions) -> YieldPrediction:
        """Clips to district historical max; sets clipped=True and warns."""
```

**File:** `backend/app/ml/suitability.py`

```python
def suitability(
    crop_id: str, district: str, season: str, conditions: dict
) -> Suitability:
    """ML.4b — Yield ratio + SHAP top-3 factors.

    score = predicted_yield / 3yr_district_average.
    label = good(>=1.05) / average(0.9-1.05) / poor(<0.9).
    top_factors: list of {feature: <code>, effect_qt_per_acre: float, direction: up|down}.
    feature codes are fixed (see ML SPECS §3) — never free text.
    Weak crops (per-crop RMSE above threshold) fall back to baseline; fallback_used=True.
    """
```

**File:** `ml/experiments/EXP_02_yield_model/train_yield.py`
- Trains Model A and Model B (with lags).
- Computes per-crop metrics, SHAP values, feature importances.
- Report: `ml/reports/EXP_02_yield_model.md`.

---

### Phase M3 — Scenarios (`ml/`)

**File:** `backend/app/ml/scenarios.py`

```python
def build_scenarios(location: LocationResult, season: str) -> list[Scenario]:
    """ML.5 — P10/P50/P90 analogue year scenarios.

    Rabi water index = 0.5 * rabi_rain + 0.5 * preceding_kharif_rain.
    Other seasons = season rainfall only.

    Returns drought / normal / excess each with:
      analogue_year, season features (rain, rainy_days, dry_spell, temp, et0, humidity),
      probability (default 0.2/0.6/0.2; shifts toward drought when current season
      rain < drought analogue), all_year_samples (SourcedValue list).

    Mumbai City and Mumbai Suburban: raises DISTRICT_NOT_AGRICULTURAL.
    """
```

---

### Phase M4 — Water, fertilizer (`ml/`)

**File:** `backend/app/ml/water.py`

```python
def crop_water_need(
    crop_id: str, season: str, scenario: Scenario, efficiency: float
) -> WaterNeed:
    """ML.7 — Penman-Monteith crop water need.

    need_mm = Σ stages ( Kc_stage × ET0_stage − effective_rain_stage )⁺ / efficiency
    need_m3_per_acre = need_mm × 4.047
    Uses crop_water_coefficients.csv for Kc and stage lengths.
    efficiency from irrigation_by_district.csv by method (flood/sprinkler/drip).
    """
```

**File:** `backend/app/ml/fertilizer.py`

```python
def fertilizer_plan(crop_id: str, fertilizer_prices: dict) -> FertilizerPlan:
    """ML.8 — RDF dose to bags to cost.

    Source: fertilizer_rdf.csv (N, P2O5, K2O kg/ha).
    Conversion fixed order:
      P2O5 entirely from DAP (46% P2O5, 18% N)
      remaining N from Urea (46% N)
      K2O from MOP (60% K2O)
    Cost = bags × MRP from fertilizer_prices.csv.
    Returns: nutrient_kg, bag_counts, cost_rs, saving_vs_district_use_pct (or null).
    """
```

---

### Phase M5 — Optimizer (`backend/app/ml/optimizer.py`)

```python
class Optimizer:
    """OPT.1–5.

    Four strategies on identical inputs:
      Traditional  — DES district mix, season+price filtered, not forced feasible
      LP max-profit — SciPy HiGHS, expected profit only
      QP balanced  — CVXPY Clarabel/OSQP, λ from risk_appetite
      QP drought-safe — QP with water limit from drought scenario

    Decision variable: x_i = acres of crop_i
    Objective: Σ_s p_s * Σ_i margin(i,s) * x_i  −  λ * x'Σx  −  Σ γ_i * x_i²
    Constraints: land, budget, water (safety scenario), diversification cap

    Diversification cap adapts: n=1→1.0, n=2→0.80, n≥3→0.65
    Risk lambda: safe=1.0, balanced=0.3, max_profit=0.0
    PSD ridge: 1e-6 × trace(Σ)

    Relaxation ladder (code, not LLM — 8.4a):
      1. Lift diversification cap to 1.0
      2. Reduce planned area to budget-feasible maximum
      3. Drop most water-hungry crop, re-solve
      4. Move water limit from safety to Normal scenario (plan no longer drought-safe)
      → Still infeasible: return feasible=False, allocations=[], full infeasibility report
    """

    def optimize(self, strategy: str, inputs: OptimizerInputs) -> StrategyResult: ...
    def compare_strategies(self, inputs: OptimizerInputs) -> list[StrategyResult]: ...
    def infeasibility_report(self, inputs: OptimizerInputs) -> InfeasibilityReport: ...
    def impact_vs_traditional(self, recommended: StrategyResult, traditional: StrategyResult) -> ImpactMetrics: ...
```

---

### Phase A1 — Sarvam client (`backend/app/agent/client.py`)

```python
"""AG.1 — Sarvam API client.

Endpoint: POST https://api.sarvam.ai/v2/chat/completions
Auth: api-subscription-key header
Models: SARVAM_CHAT_MODEL → SARVAM_FALLBACK_MODELS (in order)
Timeout: 15 s per model; on timeout or 5xx, try next model.
Rate limit (429): exponential backoff, max 3 retries, then raise.
Final fallback: raise SarvamAllModelsFailed — caller uses template answer.

TTS: POST https://api.sarvam.ai/text-to-speech
  model=bulbul:v3, speaker=meera (Marathi default), returns base64 WAV
  language_code: mr-IN / hi-IN / en-IN

STT: POST https://api.sarvam.ai/speech-to-text  (multipart/form-data)
  model=saaras:v4, file=<bytes>, language_code or unknown for auto-detect
  Returns: transcript (str), language_code (str)
"""

import httpx
from app.config import settings

SARVAM_BASE = "https://api.sarvam.ai"

class SarvamClient:
    def __init__(self):
        self._headers = {"api-subscription-key": settings.SARVAM_API_KEY}

    async def chat(
        self,
        messages: list[dict],
        response_format: dict | None = None,  # {"type": "json_schema", "json_schema": {...}}
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> dict:
        """Try SARVAM_CHAT_MODEL, then each SARVAM_FALLBACK_MODELS in order.
        Returns OpenAI-compatible response dict.
        """

    async def transcribe(self, audio_bytes: bytes, content_type: str, language: str | None) -> dict:
        """POST /speech-to-text multipart.
        Returns {"transcript": str, "language_code": str}.
        """

    async def speak(self, text: str, language: str = "mr") -> bytes:
        """POST /text-to-speech.
        Returns raw WAV bytes.
        """
```

---

### Phase A2 — Tools (`backend/app/agent/tools.py`)

Each tool wraps a backend service or ML function. All return `SourcedValue`-bearing dicts.

```python
# AG.2 — one tool per service / ML function
get_location(location_text: str) -> LocationResult
get_weather(district: str) -> WeatherForecast
get_soil(district: str) -> SoilData
get_water_budget(profile: FarmProfile, location: LocationResult, scenarios: list[Scenario]) -> list[WaterBudget]
get_prices(district: str, crop_ids: list[str]) -> dict[str, CropPrice]
get_costs(district: str, crop_ids: list[str]) -> dict[str, CropCost]
recommend_crops(profile, location, season, water) -> tuple[list[Candidate], list[ExcludedCrop]]  # ML.1+ML.4b
predict_yield(crop_id, location, season, conditions) -> YieldPrediction           # ML.4
optimize_plan(strategy, inputs: OptimizerInputs) -> StrategyResult
compare_strategies(inputs: OptimizerInputs) -> list[StrategyResult]
```

Every tool logs its call duration into the trace; `gather_data` runs them in parallel via `asyncio.gather`.

---

### Phase A3 — LangGraph graph (`backend/app/agent/graph.py`)

#### 8.1 Flow (exact)

```
START
  │
  ▼
route ──────────────────────────────► answer_from_memory (follow-up / plan question)
  │ new plan                                     │
  ▼                                              ▼
extract_profile                              respond (SSE)
  │
  ├── missing fields? ──► ask_missing ──► END TURN (question event)
  │
  ▼
gather_data (all tools in parallel)
  │
  ├── no real data for any crop? ──► explain_missing ──► respond ──► END
  │
  ▼
recommend_crops (ML.1 + ML.4b)
  │
  ▼
predict_yield (3 scenarios via ML.5 + ML.6)
  │
  ▼
optimize (4 strategies via OPT.1–5)
  │
  ▼
check_feasibility
  │
  ├── infeasible? ──► relax_constraint (code ladder, max 3) ──► optimize (loop)
  │                        │
  │                        └── still infeasible after 4 steps ──► respond(no-alloc plan)
  ▼
explain (Sarvam LLM call — at most once, retry once on grounding failure)
  │
  ▼
grounding_check
  │
  ├── fail twice? ──► use template_explanation (AG.10)
  │
  ▼
respond (SSE: thread→profile→trace×N→plan→message→done)
  │
  ▼
save_memory (SQLite checkpointer)
```

#### LLM calls budget: at most 3 per plan
- `extract_profile` (1 call) — structured output, JSON schema enforced
- `explain` (1 call, 1 retry on grounding fail) — generates text only
- `route` and `ask_missing` — rule-based, no LLM

---

### Phase A4 — Node implementations (`backend/app/agent/nodes.py`)

#### `extract_profile` (AG.3)

```python
async def extract_profile(state: AgentState) -> AgentState:
    """LLM call 1 of 3.

    Prompt: structured output with JSON schema for FarmProfile.
    Model: SARVAM_CHAT_MODEL (sarvam-105b).
    Response format: {"type": "json_schema", "json_schema": FarmProfile.model_json_schema()}.
    
    Post-LLM normalization (plain code, not LLM):
      - Unit conversion: guntha → acres (1 guntha = 0.025 acres)
                         hectare → acres (1 ha = 2.471 acres)
      - Number words: "70 हजार" → 70000, "५ एकर" → 5 (Devanagari → int)
      - Never guesses a missing number: missing fields go to state.missing[].
    """
```

#### `explain` (AG.8)

```python
async def explain(state: AgentState) -> AgentState:
    """LLM call 2 of 3 (plus 1 retry on grounding failure).

    System prompt (language-specific):
      - You are an agricultural advisor. Explain in {language} only.
      - Use ONLY numbers from the tool outputs below. No invented figures.
      - Speak to the farmer directly: "आपण" (Marathi) / "आप" (Hindi) / "you" (English).
      - Mention: best crop, why (top SHAP factor), expected profit, water saved vs traditional.
      - Round to 2 significant figures for yield (quintals/acre), nearest 100 for money.
      - Max 120 words.

    User prompt: formatted tool outputs (optimizer results, water, prices, SHAP factors).
    Response format: {"type": "json_object"} → {"text": str, "language": str}.
    """
```

#### `grounding_check` (AG.9)

```python
def grounding_check(explanation_text: str, tool_outputs: dict) -> bool:
    """Every number in explanation must appear in tool_outputs.

    Normalization before matching:
      - Devanagari digits → ASCII
      - Strip Indian digit grouping: "1,00,000" → 100000
      - Expand words: hazar/हजार → ×1000, lakh/लाख → ×100000, crore/करोड → ×10000000
      - Match in the units the answer uses (quintals/acre, rupees, acres, m3).
      - Allow rounding: match passes if |answer_number - source_number| / source_number ≤ 0.01.
    Returns True if all numbers match; False if any do not.
    """
```

---

### Phase A5 — Memory (`backend/app/agent/memory.py`)

```python
"""AG.7 — LangGraph SQLite checkpointer.

Uses LangGraph's built-in SqliteSaver, keyed by thread_id.
Stores: profile, last plan inputs, message list.
Location: settings.CACHE_DB_PATH (same DB, separate table managed by LangGraph).

Follow-up handling:
  A follow-up like "what if I only have ₹50,000?" passes through extract_profile
  with the changed field only; gather_data reuses upstream cache, so re-runs are fast.
"""
from langgraph.checkpoint.sqlite import SqliteSaver
```

---

### Phase A6 — Template fallback (`backend/app/agent/templates.py`)

```python
"""AG.10 — No-LLM plan explanation in all 3 languages.

When all Sarvam models fail or grounding fails twice, this builds
an explanation from the optimizer output using string templates.
Never produces an empty answer.

Templates per language × strategy × crop count (one/two/three+):
  MR: "तुमच्या {land_acres} एकर जमिनीसाठी {crop_1} ({crop_1_acres} एकर) आणि ..."
  HI: "आपकी {land_acres} एकड़ जमीन के लिए {crop_1} ({crop_1_acres} एकड़) ..."
  EN: "For your {land_acres}-acre farm, {crop_1} ({crop_1_acres} ac) ..."
"""
```

---

### Phase A7 — Prompts (`backend/app/agent/prompts.py`)

System prompts for `extract_profile` and `explain` in Marathi, Hindi and English. Rules:

1. Every prompt ends with: "Output ONLY the JSON object. No markdown. No extra text."
2. `explain` prompt lists all numbers from tool outputs inline so the model cannot invent them.
3. `extract_profile` prompt includes: "If the farmer did not say a number, leave the field null."
4. Language is determined by the `language_code` from Sarvam STT or the frontend `language` param.

---

### Phase A8 — Backend integration (replace stub)

**File to edit:** `backend/app/api/agent.py`

Replace the current `run_plan()` stub with:

```python
from app.agent.graph import get_graph

@router.post("/agent/chat")
async def agent_chat(body: dict):
    graph = get_graph()
    thread_id = body.get("thread_id") or f"th_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    async def _stream():
        yield {"event": "thread", "data": json.dumps({"thread_id": thread_id})}
        async for event in graph.astream_events(
            {"message": body.get("message", ""), "language": body.get("language", "mr")},
            config=config,
            version="v2",
        ):
            # Map LangGraph node events to SSE events
            # profile → "profile" event
            # trace step → "trace" event
            # plan ready → "plan" event
            # explain done → "message" event
            sse = _langgraph_event_to_sse(event)
            if sse:
                yield sse
        yield {"event": "done", "data": json.dumps({"ms": 0})}

    return EventSourceResponse(_stream(), ping=10)
```

The `_langgraph_event_to_sse` mapper translates LangGraph's `on_chain_end` / `on_tool_end` events to the SSE schema in `backend/SPECS.md §5.2 E1`.

---

## 4. AgentState schema

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    thread_id: str
    message: str
    language: str                        # mr / hi / en
    profile: FarmProfile | None
    missing: list[str]                   # missing required profile fields
    location: LocationResult | None
    weather: WeatherForecast | None
    soil: SoilData | None
    scenarios: list[Scenario]
    water: list[WaterBudget]             # one per scenario
    candidates: list[Candidate]
    excluded: list[ExcludedCrop]
    prices: dict
    costs: dict
    scenario_yields: dict                # crop_id → {drought/normal/excess: YieldPrediction}
    strategies: list[StrategyResult]
    feasibility: InfeasibilityReport | None
    relaxations: list[str]               # log of relaxation steps taken
    explanation: str
    trace: list[TraceEvent]
    messages: Annotated[list, add_messages]
    route: str                           # new_plan / follow_up / question
```

---

## 5. Tests required (per ML SPECS §9)

### ML tests
| Test | File |
|---|---|
| ML.1 — never suggests apple/coffee/jute for Maharashtra | `tests/ml/test_candidate.py` |
| ML.3 — baseline MAE reported, no data leakage | `tests/ml/test_baseline.py` |
| ML.4 — time split, clipping to district max | `tests/ml/test_yield_model.py` |
| ML.4b — SHAP contributions sum to prediction | `tests/ml/test_suitability.py` |
| ML.5 — Rabi uses mixed index; all 34 districts | `tests/ml/test_scenarios.py` |
| ML.7 — hand-checked water need example | `tests/ml/test_water.py` |
| ML.8 — fertilizer cost, saving only from real district data | `tests/ml/test_fertilizer.py` |

### Optimizer tests
| Test | Condition |
|---|---|
| λ=0 QP == LP result | `tests/ml/test_optimizer.py` |
| Land/budget/water constraints never exceeded | same |
| QP drought-safe never exceeds drought water limit | same |
| PSD check on covariance matrix Σ | same |
| Infeasible input → report, not plan | same |

### Agent tests
| Test | Condition |
|---|---|
| 10 sentences × 3 languages → correct profile | `tests/agent/test_extract_profile.py` |
| Missing budget field → ask_missing fires | same |
| Infeasible case ends feasible and explained | `tests/agent/test_graph.py` |
| Follow-up "₹50,000" re-runs with one change | same |
| Injected wrong number fails grounding check | `tests/agent/test_grounding.py` |
| Devanagari digits in explanation — grounding still works | same |
| All models down → template answer (not empty) | `tests/agent/test_fallback.py` |
| Sarvam key removed → template answer | same |

---

## 6. Constants to declare (§7A — all must be in `constants.py`, never in code)

```python
# backend/app/ml/constants.py
SCENARIO_PERCENTILES = (10, 50, 90)          # P10/P50/P90
SCENARIO_WEIGHTS_DEFAULT = (0.2, 0.6, 0.2)
RABI_WATER_INDEX = (0.5, 0.5)               # rabi_rain_weight, kharif_rain_weight
EFFECTIVE_RAIN_FACTOR = 0.75                 # assumption; needs FAO-56 citation
CATEGORY_CAP = {                             # assumption; needs CGWB citation
    "Safe": 1.0, "Semi-critical": 0.7,
    "Critical": 0.4, "Over-exploited": 0.15,
}
DIVERSIFICATION_CAP = {1: 1.0, 2: 0.80}    # n>=3 → 0.65
DIVERSIFICATION_CAP_DEFAULT = 0.65
RISK_LAMBDA = {"safe": 1.0, "balanced": 0.3, "max_profit": 0.0}
SATURATION_GAMMA = 0.0                       # negligible for single farm
SUITABILITY_LABELS = {"good": 1.05, "average": 0.90}  # thresholds (lower bound)
RAIN_DAY_MM = 2.5                            # IMD definition
HEAT_STRESS_C = 35                           # common threshold
PSD_RIDGE = 1e-6                             # multiplied by trace(Σ)
MIN_PRICE_YEARS = 3                          # for seasonal ratio
MIN_RISK_YEARS = 5                           # for crop risk term
NON_AGRICULTURAL_DISTRICTS = {"Mumbai City", "Mumbai Suburban"}
```

---

## 7. `.env` — fill these before starting AG.1

```ini
SARVAM_CHAT_MODEL=sarvam-105b
SARVAM_STT_MODEL=saaras:v4
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_FALLBACK_MODELS=glm5.3-flash,deepseekv4.1-flash-1017
```

Both keys (`SARVAM_API_KEY`, `DATA_GOV_IN_API_KEY`) are already present in `.env`. No other keys are needed — Sarvam is the only model provider.

---

## 8. Task checklist (status mirrors ml/SPECS.md §11)

### ML + data
- [ ] ML.1 candidate crop filter
- [ ] ML.2 clean yield_training.csv
- [ ] ML.3 baseline (EXP_01)
- [ ] ML.4 yield model (EXP_02)
- [ ] ML.4b SHAP suitability
- [ ] ML.5 climate scenarios
- [ ] ML.6 scenario yields
- [ ] ML.7 crop water need
- [ ] ML.8 fertilizer plan (EXP_03)
- [ ] ML.9 experiment reports

### Optimizer
- [ ] OPT.1 LP baseline
- [ ] OPT.2 QP
- [ ] OPT.3 four strategies (EXP_04)
- [ ] OPT.4 infeasibility report
- [ ] OPT.5 impact vs Traditional

### Agent
- [ ] AG.1 Sarvam client
- [ ] AG.2 tool wrappers
- [ ] AG.3 extract_profile
- [ ] AG.4 ask_missing
- [ ] AG.5 graph
- [ ] AG.6 self-correction ladder
- [ ] AG.7 memory (SQLite checkpointer)
- [ ] AG.8 explain (Sarvam LLM)
- [ ] AG.9 grounding check
- [ ] AG.10 template fallback
- [ ] Replace stub in `backend/app/api/agent.py`

### Delivery
- [ ] QA.3 demo script (Jalgaon, Pune, Ahilyanagar, Nashik backup)
- [ ] language_review.md signed off
- [ ] DD.5 README final setup steps
- [ ] DD.6 5–7 slide deck
