# ML & AI SPECS: Models, Optimizer and Agent

**Owner:** ML & AI lead · **Works with:** [`backend/SPECS.md`](../backend/SPECS.md) (hosts this code; data layer and API) and [`frontend/SPECS.md`](../frontend/SPECS.md) (shows these results)
**Stack:** Python · pandas · scikit-learn (gradient boosting) · SHAP · SciPy · CVXPY · LangGraph · pytest

**Status:** ⬜ Not started · 🟨 In progress · ✅ Done · ⛔ Blocked · ➖ Dropped
Update the **Status** column in the same pull request that does the work.

---

## 1. Ground rules

- **No mock, hardcoded or dummy data.** Models train only on official datasets in `data/processed/`; live values come only from the backend services. Breaking this rule means instant disqualification.
- **Scoring this part supports:** *Technical Depth (20)*: yield model, climate scenarios, water need, QP optimizer · *AI Reasoning / Agentic (25)*: LangGraph agent, self-correction, memory, grounding · *Impact / USP (25)*: drought-safe plans, water and fertilizer saved.
- **Code rules:**
  1. **No invented numbers in code.** No default prices, costs, yields, crops. Missing data → the crop is excluded and the reason is returned.
  2. **Every value that reaches the farmer keeps its source** (`SourcedValue`, backend section 5.1).
  3. **No data leakage.** Never use `production` as a feature; history features use past years only; train/test split is by year.
  4. **Fixed seeds** (`random_state=42`) for every split and model.
  5. **Paths with `pathlib`**, console output ASCII-safe (`Rs.` instead of `₹` in logs).
  6. **Every experiment gets a report** in `ml/reports/` (section 9) and its model file is saved with a metadata JSON.
  7. **Tests ship with the code.**
- **Decisions already made:** no Kaggle classifier (suitability from real data, section 3) · optimizer = Quadratic Programming (CVXPY) with an LP baseline · hybrid agent: fixed graph for the main path, the LLM decides only at specific points · plain code handles API failures, retries, unit conversion, validation and impossible-yield clipping; the agent handles profile extraction, follow-up questions, fixing infeasible plans and explanations.
- **Open decisions affecting this file:** D1 agent LLM (default **Gemini** first, **Groq** and **Sarvam** as fallbacks, one setting `LLM_PROVIDER`; test Groq and Sarvam and switch if faster or better in Marathi).

---

## 2. Layout and data

```
ml/
├── data_prep/       cleaning scripts (ML.2)
├── experiments/     training scripts, one folder per experiment
├── models/          saved models + metadata JSON (git-lfs or ignored if large)
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
| `fertilizer_response.csv`, `fertilizer_rdf.csv`, `fertilizer_prices.csv` | Dose-response trials, university doses, MRPs | Fertilizer curve (ML.8) |
| `cost_of_cultivation.csv`, `seed.csv`, `msp.csv`, `price_history_monthly.csv` | Costs, seed, MSP, monthly prices | Optimizer inputs and risk |
| `groundwater_by_block.csv`, `reservoir_storage.csv`, `irrigation_by_district.csv`, `recent_rainfall.csv` | Water context | Water budget |

---

## 3. Crop suitability (real data only, no Kaggle classifier)

Suitability is built from official data in three steps:

1. **Filter (ML.1).** Keep a crop only if it is (a) grown in the district (DES area above a threshold in recent years, per season), (b) sowable now (crop calendar) and (c) its water need fits the available water (ML.7 + water budget).
2. **Score (ML.4b).** The yield model predicts each remaining crop's yield under **this season's conditions**. Suitability = predicted yield ÷ the crop's normal yield in the district (3-year average). Above 1 means better than usual conditions. Labels: `good` ≥ 1.05, `average` 0.9–1.05, `poor` < 0.9.
3. **Explain (ML.4b).** SHAP (`TreeExplainer`) on the same yield model gives each factor's effect on the predicted yield (rainfall, dry spell, heat days, soil, irrigation). The top 3 factors per crop go to the API as `suitability.top_factors`, converted to quintals per acre. The agent turns them into one plain sentence.

The optimizer then makes the final choice by profit, risk and water; suitability only narrows and explains the candidates. If the yield model is weak for a crop (out-of-time error above the threshold in ML.4), that crop falls back to the district's historical average yield, `fallback_used = true`, and the answer says so. SHAP shows what the model relied on, not true cause and effect, and the README says that.

---

## 4. Yield model

| Item | Spec |
|---|---|
| **Target** | `yield_t_per_ha` (converted to quintals per acre only at the API boundary) |
| **Row** | One district + crop + season + year |
| **Features** | Identity: district, crop, season, year · Weather over the crop's own growing window: season rainfall, rainfall departure, rainy days, longest dry spell, mean and max temperature, heat-stress days (> 35 °C), ET₀ total, humidity · Soil: N, P, K, pH, organic carbon · Water and inputs: irrigated %, groundwater category and extraction %, fertilizer use · History: previous-year yield, 3-year average (past years only) |
| **Never use** | `production`, `area_ha` as a way to derive the target, anything from the target year or later |
| **Cleaning (ML.2)** | Remove aggregate rows ("Total foodgrain", "Pulses total", "Other …"), impossible yields (e.g. Jowar 14.6 t/ha, near-zero values), mixed units (coconut in nuts); report counts per reason |
| **Split** | By year: train on early years, validate on the next, test on the latest years (for example train 1997–2008, validate 2009–2011, test 2012–2014); also check on 2010–2025 climate for the scenario use |
| **Models** | Baseline: hierarchical median lookup, district → state → crop (ML.3). Main: gradient boosting (`HistGradientBoostingRegressor` or LightGBM) (ML.4) |
| **Metrics** | Out-of-time MAE, RMSE, R², WAPE overall **and per crop**; per-crop table to find weak crops (the v1 XGBoost looked good overall but failed per crop) |
| **Guards** | Clip predictions to the district's historical maximum for that crop and flag it; inputs outside the training range are flagged |
| **Data limits to state honestly** | Yield data ends in 2014 and covers 34 districts; soil values come from recent Soil Health Card cycles and are fixed per district |

---

## 5. Climate scenarios

For each district and season, from the 2010–2025 climate data:
- **Drought** = 10th percentile of season rainfall, **Normal** = median, **Excess** = 90th percentile; probability weights default to 0.2 / 0.6 / 0.2.
- Each scenario carries the matching season features (rainfall, dry spell, heat days, ET₀) so the yield model gives a **yield per crop per scenario** (ML.6).
- **Every historical year is kept** as a sample: the optimizer's risk matrix is estimated from all years, not from three points.
- The current season's observed rain so far (`recent_rainfall.csv` and the live forecast) shifts which scenario is most likely; the API shows the scenarios and probabilities used.

---

## 6. Water, crop water need and fertilizer

**Water budget** (inputs from backend services, formula owned here)
```
available water (m³) = effective rain  +  groundwater share  +  canal share
  effective rain      = (recent observed + 16-day forecast + scenario remainder) × effective-rain factor × area
  groundwater share   = farmer's borewell capacity, capped by the CGWB block category
                        (Safe: no cap · Semi-critical: reduced · Critical: strongly reduced · Over-exploited: minimal)
  canal share         = from reservoir live storage % for canal-irrigated farms
```
The category caps and the effective-rain factor must each cite a source in `SOURCES.md`; they are not guessed.

**Crop water need (ML.7)** per crop, stage and scenario
```
need (mm) = Σ over stages ( Kc × ET₀ − effective rain )⁺  ÷  irrigation efficiency
```
Efficiency by method (flood, sprinkler, drip) comes from `irrigation_by_district.csv`. Need in m³ per acre = mm × 4.047.

**Fertilizer response (ML.8)**
- Fit `yield = a + b·f − c·f²` per crop with `scipy.optimize.curve_fit` on `fertilizer_response.csv`; report the fit quality.
- Optimal dose `f* = (b − p_f / p_crop) / (2c)`, where `p_f` is the fertilizer price per kg of nutrient and `p_crop` is the crop price per the same yield unit; capped at the university RDF. Computed **before** the optimizer so the problem stays convex.
- If a crop has no response data, use its university RDF as the dose and mark the source.

---

## 7. Optimizer

Decision variable `xᵢ` = acres of crop `i`.

```
maximize   Σ_s p_s · Σ_i m(i,s) · xᵢ      expected profit over Drought / Normal / Excess
         − λ · xᵀ Σ x                     risk: Σ = covariance of per-acre profit across historical years and price history
         − Σ_i γᵢ · xᵢ²                   market saturation (small for one farm)
subject to Σ xᵢ ≤ L                         land
           Σ costᵢ(f*) · xᵢ ≤ B             budget (seed, fertilizer at f*, labour, irrigation, pesticide, interest)
           Σ water(i,s*) · xᵢ ≤ W(s*)       water in the chosen safety scenario s*
           xᵢ ≤ 0.65 · L                    diversification (when more than one crop)
           xᵢ ≥ 0
```
`m(i,s)` = yield(i,s) × price − cost per acre. **Keep it convex:** Σ positive semi-definite (add a tiny ridge), never multiply two decision variables, fertilizer dose fixed before solving. Solver: CVXPY with Clarabel or OSQP.

**Four strategies on the same inputs**
| Strategy | Definition |
|---|---|
| **Traditional** | The district's current crop mix from DES area shares, scaled to the farmer's land |
| **LP max-profit** | SciPy HiGHS, expected profit only, same land, budget, water and cap constraints |
| **QP balanced** | The QP above with λ from the farmer's `risk_appetite` (`safe` high, `balanced` medium, `max_profit` ≈ 0) |
| **QP drought-safe** | The QP with the water limit taken from the **Drought** scenario |

**Outputs per strategy:** allocations, profit in each scenario, expected profit, worst-case profit, water and fertilizer used, cost, binding constraints, solver status and time.
**Impact vs Traditional:** water saved %, fertilizer saved %, drought-year profit difference.
**Infeasibility report (OPT.4):** which constraints are violated or binding and by how much (land, budget, water, cap), so the agent can decide what to relax. Infeasible plans are **never** silently replaced by an even split.

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
| `relax_constraint` | Read the infeasibility report and choose one relaxation: reduce area to what the budget allows, swap to cheaper or less water-hungry crops, accept a smaller water share; log the reason | `relaxations[]` |
| `explain` / `answer_from_memory` | Explain the plan in mr / hi / en using only tool outputs; answer follow-ups from stored state | `explanation` |

**Provider order:** `LLM_PROVIDER` first, then the others, automatic on error or timeout (15 s). **Language:** the reply language equals the farmer's detected language unless they change it.

### 8.5 Memory
LangGraph checkpointer on SQLite, keyed by `thread_id`, storing profile, last plan inputs and the message list. A follow-up such as "what if I only have ₹50,000?" passes through `extract_profile` with the changed fact only, and re-runs the plan from `gather_data` (cached data is reused, so it is fast).

### 8.6 Guards
- **Grounding check:** every number in the answer text must appear in the tool outputs (after unit formatting). On failure, retry once; if it fails again use the **template explanation** built from the optimizer result. A test injects a wrong number and expects the check to fail.
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
| **Experiments planned** | EXP_01 yield baseline (ML.3) · EXP_02 gradient-boosting yield model with SHAP (ML.4, ML.4b) · EXP_03 fertilizer response curves (ML.8) · EXP_04 optimizer comparison on saved real profiles (OPT.3) |
| **Optimizer tests** | Land, budget, water and cap are never exceeded · λ = 0 reproduces the LP result · QP drought-safe never exceeds the drought water limit · PSD check on Σ · infeasible inputs produce a report, not a plan |
| **Agent tests** | 10 sentences per language → correct profile · missing budget asks for the budget · infeasible case ends feasible and explained · follow-up re-runs with one change · injected wrong number fails grounding · all-LLMs-down returns the template answer |
| **Honest metrics (DD.5)** | Show real out-of-time yield results; state the limits (yield data ends in 2014, 34 districts, SHAP is attribution not causation) in the deck and README |

---

## 10. Interfaces with the backend (signatures to implement)

Stubs are merged first (backend C.3) so the backend and frontend can proceed.
```python
def candidate_crops(profile, location, season, water) -> tuple[list[Candidate], list[ExcludedCrop]]
def predict_yield(crop_id, location, season, conditions) -> YieldPrediction          # t/ha + clipped flag
def suitability(crop_id, location, season, conditions) -> Suitability                # score, label, top_factors, fallback_used
def build_scenarios(location, season) -> list[Scenario]                              # drought / normal / excess + weights + all-year samples
def crop_water_need(crop_id, season, scenario, efficiency) -> WaterNeed              # mm and m3 per acre
def fertilizer_plan(crop_id, fertilizer_prices, crop_price) -> FertilizerPlan        # f*, kg N/P2O5/K2O per acre, basis
def optimize(strategy, inputs: OptimizerInputs) -> StrategyResult
def compare_strategies(inputs: OptimizerInputs) -> list[StrategyResult]              # the four strategies + impact
```
Types are the Pydantic models in `backend/app/schemas.py`. Every function returns values with the source information the backend needs for `SourcedValue`.

---

## 11. Tasks

### 11.1 Data and yield model
| ID | Task | Done when | Status |
|---|---|---|---|
| ML.1 | Candidate crop filter: grown in the district ∩ sowable now ∩ water-feasible | Never suggests apple / coffee / jute; covers soybean, sugarcane, jowar, wheat, onion | ⬜ |
| ML.2 | Clean `yield_training.csv`: aggregate rows, impossible yields, units | Cleaning report with counts per reason | ⬜ |
| ML.3 | Yield baseline: hierarchical median lookup | Out-of-time MAE reported (EXP_01) | ⬜ |
| ML.4 | Yield model: gradient boosting, time-based split, clipped to district max | Beats ML.3 per crop, or ML.3 stays primary for that crop (EXP_02) | ⬜ |
| ML.4b | Suitability score and SHAP on the ML.4 model; fallback for weak crops | Score + top factors for every candidate; SHAP contributions add up to the prediction | ⬜ |
| ML.5 | Climate scenarios per district (P10 / P50 / P90, weights, all-year samples) | Scenario table for all 36 districts | ⬜ |
| ML.6 | Scenario yields: yield per crop per scenario | 3 yields per candidate crop | ⬜ |
| ML.7 | Crop water need per stage and scenario | Matches a hand-checked example | ⬜ |
| ML.8 | Fertilizer response curve and optimal dose per crop | Curve, `f*` and fit quality per crop (EXP_03) | ⬜ |
| ML.9 | Experiment reports for ML.3, ML.4 / ML.4b, ML.8 | One report per experiment in `ml/reports/` | ⬜ |

### 11.2 Optimizer
| ID | Task | Done when | Status |
|---|---|---|---|
| OPT.1 | LP baseline (HiGHS) with land, budget, water, cap | Constraints never exceeded | ⬜ |
| OPT.2 | QP (CVXPY) as in section 7, λ from `risk_appetite` | λ = 0 gives the LP result; PSD check | ⬜ |
| OPT.3 | Four strategies and comparison on the same inputs | Each returns profit per scenario, worst case, water, fertilizer, cost (EXP_04) | ⬜ |
| OPT.4 | Infeasibility report | The agent can read it and propose a fix | ⬜ |
| OPT.5 | Impact metrics vs Traditional | Water saved, fertilizer saved, drought-year profit difference | ⬜ |

### 11.3 Agent
| ID | Task | Done when | Status |
|---|---|---|---|
| AG.1 | LLM provider switch with fallback order and timeouts | Fallback tested | ⬜ |
| AG.2 | Tools wrapping services and ML functions | Each tool has a test | ⬜ |
| AG.3 | Profile extraction and normalization | 10 sentences each in mr / hi / en extracted correctly | ⬜ |
| AG.4 | Ask-missing loop | Missing-budget sample asks for the budget | ⬜ |
| AG.5 | Graph with the fixed main path and SSE trace events | End-to-end run on a real sample | ⬜ |
| AG.6 | Self-correction (relax and re-optimize, max 3, logged) | Infeasible case ends feasible and explained | ⬜ |
| AG.7 | Memory (SQLite checkpointer) and follow-ups | "What if ₹50,000?" test passes | ⬜ |
| AG.8 | Explanations in mr / hi / en from tool outputs only | Reviewed by a native speaker | ⬜ |
| AG.9 | Grounding check | Injected wrong number fails the check | ⬜ |
| AG.10 | No-LLM template fallback | Demo never shows an empty answer | ⬜ |

### 11.4 Delivery
| ID | Task | Done when | Status |
|---|---|---|---|
| QA.3 | Demo script: 3 farmer stories (drought district, canal-irrigated, follow-up) rehearsed 3× with the whole team | Under 3 minutes | ⬜ |
| DD.5 | README final setup steps, architecture diagram, honest metrics | Fresh clone runs following the README | ⬜ |
| DD.6 | 5–7 slide deck (problem, solution, architecture, agent, results, impact) | Reviewed by all | ⬜ |

---

## 12. Lessons from the old prototype (v1)
**Re-create:** TreeSHAP with a check that baseline + contributions equals the model output · yield lookup hierarchy (district → state → crop) as baseline and sanity bound · 65% diversification cap · strict validation of LLM output.
**Do not repeat:** XGBoost yield model with `area` / `production` features (circular leakage; R² collapsed on real tests) · coconut yields in nut counts mixed with tonnes · season from the month only · Kaggle classifier (partly synthetic, missing the main Maharashtra crops, suggested apple / coffee / jute) · an LP that silently fell back to an even land split · hidden defaults for cost, price and yield.
