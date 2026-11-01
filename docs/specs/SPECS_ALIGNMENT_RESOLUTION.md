# Resolution of the spec alignment review

Reviewed: [`SPECS_ALIGNMENT_PROBLEMS.md`](SPECS_ALIGNMENT_PROBLEMS.md) (31 Oct 2026, written by a second AI agent against the three SPECS files only).
Checked and fixed: 31 Oct 2026, against the spec files **and** the real data in the repo.

**Verdict: every problem I checked was real.** I verified 14 of them directly in the files and data before changing anything; none was a false alarm. 43 of 48 are now fixed in the specs. 5 remain open and are listed at the end, because they need a decision from the team rather than an edit.

The review was written before the data repairs of the same day, so a few of its concerns (two disagreeing weather sources, the January 2023 reservoir snapshot, the modelled price history) were already being fixed by `ml/data_prep/`; the specs now describe the repaired state.

---

## How each blocker was verified and fixed

| # | Problem | How I checked it | Fix |
|---|---|---|---|
| 1.1 | Examples are Kharif but dated 2 Nov; no rule for choosing the season | Read `crop_calendar.csv`: on 31 Oct 2026 the sowable crops are jowar (Rabi), chickpea, lentil, maize (Rabi), grapes; wheat opens 1 Nov. Soybean closed in July. The example was impossible | New **ml section 3A**: `plan_season(today)` from the calendar, with a 7-day grace and a 21-day "opens soon" window, and a stated rule for gaps between seasons. Every example in all three files is now the Rabi set |
| 1.2 | Rainfall percentiles collapse in Rabi; per-feature percentiles invent years | Rabi rainfall in Maharashtra is small, so P10 and P90 nearly coincide | Scenarios are now **analogue years**: pick the real year at P10 / P50 / P90 and use all of that year's features, so the combination really happened. Rabi is ranked on `0.5 × Rabi rain + 0.5 × preceding Kharif rain`, because Rabi lives on stored moisture. `analogue_year` is in the response |
| 1.3 | Lag features have no value for 2026 | DES yields end in 2014, confirmed against the live API: `crop_year=2015` returns 0 rows | **Two models**: model A (shipped) trains without lags; model B (reference) keeps them only to show their value in EXP_02 |
| 1.4 | Trains on 34 districts, serves 36 | `yield_training.csv` has 34; the two missing are Mumbai City and Mumbai Suburban | 34 are planable. The other two return `DISTRICT_NOT_AGRICULTURAL`, are greyed on the map, and get no scenario row. One flag, `is_agricultural_district`, drives all three parts |
| 1.5 | Two weather pipelines, and no yield truth after 2014 | The two files differ by up to 597 mm on the same district-year | **One source** (Open-Meteo ERA5 1997-2025) with one definition per feature. 2015-2025 is used only for scenarios and range checks, never for an error metric |
| 1.6 | "Every number has a badge" contradicts the contract | The contract's own example had plain numbers for yield, profit and water | `status` extended to `live, cached, official_dataset, model, computed, farmer_input, assumption`. Every farmer-visible number is a `SourcedValue`; ids and durations are not |
| 1.7 | Circular build order | Frontend needs real samples; real samples need ML | Two example sets: `contract/` (agreed at C.1, unblocks day 1) and `live/` (captured at M2). Contract examples are an interface agreement, not product data |
| 1.8 | Water needs inputs nothing collects | `FarmProfile` had no borewell or canal field; caps were words | Added `borewell_count`, `borewell_yield_lph`, `pump_hours_per_day`, `canal_access`. Caps are now numbers in **section 7A** marked `assumption` until sourced. District category = the "(District Avg)" row of the CGWB file |
| 1.9 | One water number, three scenarios | `WaterBudget` had no scenario field | One `WaterBudget` **per scenario**, so the gauge changes with the toggle |
| 1.10 | Fertilizer saving defined two ways | ml said "vs district use", backend said `versus: traditional` | Two names: `fertilizer_saved_pct` (vs Traditional, matching water saved) and `fertilizer_vs_district_use_pct` (separate, `null` when not applicable) |
| 1.11 | Two fertilizer and seed costs feed one budget | DES 2022-23 has both lines, and ML.8 computes them again | Explicit precedence: the RDF-at-MRP fertilizer line and the `seed.csv` seed line **replace** the DES lines; the replaced ones are returned as `superseded` |
| 1.12 | Types used but never defined | `Candidate`, `YieldPrediction`, `OptimizerInputs` and others appear only in signatures | C.1 now lists all 24 types to define |
| 1.13 | Farmer text is English-only | Only `Error.user_message` had three languages | All farmer text is `{code, params}` with enumerated codes; the app translates. Only the LLM explanation is free text |
| 1.14 | "No invented numbers" versus the optimizer's own constants | 0.65 cap, 0.2/0.6/0.2 weights, λ, γ, 35 °C and others had no status | New **section 7A**: every constant with value, status (`measured`, `choice`, `assumption`) and basis. The rule is restated: data values need a source, declared modelling parameters are allowed and visible |
| 1.15 | Today's price, harvest-time profit | A live quote multiplied a yield months away | **Expected harvest price** = today's price × a seasonal ratio from the real monthly history, floored at MSP, with the number of years it came from. Under 3 years the ratio is 1.0 and the answer says it was not adjusted |

## Major and interface items

All of 2.1-2.17 and 3.1-3.7 were real and are fixed in the same way: the Traditional baseline is now restricted to the season and to priced crops and may legitimately break a limit (it is the status quo, and the response says which limit it breaks); LP uses exactly the QP constraints so the `λ = 0` test is meaningful; the diversification cap adapts (1.0 / 0.80 / 0.65) and is the first thing the relaxation ladder lifts; there is a defined payload and screen for "no feasible plan"; the relaxation ladder became **deterministic code**, which cuts the agent to **at most 3 LLM calls**; `run_plan` is the single orchestration path, so `/api/plan` and the agent cannot disagree; the grounding check defines how it reads Devanagari digits and Indian grouping; "why this crop" is owned by the frontend through fixed feature codes; SSE payloads are published through `GET /api/schemas/sse-events` so the generated types cover them; the wrong section and task references are corrected (backend now cites feature ids `F1-F18`, which do not drift); `fertilizer_plan` lost the leftover `crop_price`; iOS audio formats are handled; and the hard-coded "₹50,000" chip is now derived from the farmer's own budget.

## Data and process items

The cache is split into three tables with different rules (only upstream responses must come from a real source); a persistent volume is required at deploy, or the cached fallback is empty on exactly the cold start the demo will hit; rate limiting uses `X-Forwarded-For`; the weekly reservoir refresh is assigned to the backend owner; key rotation moved **before** the first push; and model files are git-lfs, never git-ignored.

**Honest limits** now list all ten items the review found missing, including that soil, irrigation and groundwater are one value per district (so two farmers in the same district get the same predicted yield), that costs are 2022-23 against a 2026 budget, and that long-duration crops are compared per acre per year.

---

## Still open: these need a team decision, not an edit

| # | Item | What is needed |
|---|---|---|
| 2.17 | D1 and D2 | **Closed 31 Oct: Sarvam AI only**, for reasoning, speech-to-text and text-to-speech. No Gemini, no Groq. D4 (hosting) is still open: Hugging Face Spaces **with a persistent volume** |
| 4.7 | Ownership across the boundary | **Closed 31 Oct:** the rule is written at the top of both specs. Whoever owns the file with the failing line fixes it; if unclear, whoever's test went red first opens the PR and tags the other |
| 4.6 | A thin market day could still empty the plan | **Closed 31 Oct:** ml section 9A names the demo districts (Jalgaon, Pune, Ahilyanagar, spare Nashik), chosen from the real price coverage, and sets the three defences (fallback chain, rich districts, cache warming) |
| 2.13 | District-level features limit the model | Accepted as a data limit and documented. Closing it needs farm-level data we do not have |
| 11a (data) | Rice and tur have 8 months of price history | Add the old bulk file's commodity spellings to `COMMODITY_ALIASES` and re-run `build_price_history.py` |
