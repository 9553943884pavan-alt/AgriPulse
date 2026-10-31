# Problems found across ml/SPECS.md, backend/SPECS.md and frontend/SPECS.md

Date of review: 31 Oct 2026.
Scope: only the three SPECS files. Anything they point to but that was not provided (data/SOURCES.md, data reports, CSV contents, DATA_FIXES.md, B-/A-numbered reports) was not checked.
This file lists problems only. It contains no proposed fixes.

Severity: **Blocker** = build or demo breaks or the rules are violated. **Major** = wrong or missing behaviour in a core flow. **Minor** = confusion, drift or polish.

---

## 1. Blockers

**1.1 The season in every example is not the season it is today.**
- The PlanResult example is Kharif (soybean, tur, jowar, sowing window 2026-06-10 to 2026-07-20) but is stamped 2026-11-02. Frontend S3 and the S4 mockup use the same Kharif crops and a 30 Oct price date.
- Today is 31 Oct 2026. A live plan is not Kharif. ML.1 ("sowable now") would exclude soybean, so the system cannot produce the output the spec shows.
- Demo stories (QA.3), the agent test sentences, the saved samples in `docs/api_examples/` and the slide deck all inherit this.
- No file defines how the season is chosen from today's date. ML section 12 lists "season from the month only" as a v1 mistake, but no replacement rule is written anywhere. Crops that span seasons or years are not covered either (sugarcane).

**1.2 The climate scenarios do not fit a non-Kharif season.**
- ML section 5 defines Drought / Normal / Excess as the P10 / P50 / P90 of season rainfall. Rabi rainfall in Maharashtra is small, so the three scenarios would be close to each other.
- Consequences: three nearly equal yields per crop, a near-singular risk matrix, "QP drought-safe" and "QP balanced" almost identical, and a "drought-year profit gain" headline that means little.
- A rainfall percentile does not fix the other features the model needs (longest dry spell, heat days, ET0, rainy days). The spec says each scenario "carries the matching season features" but never says how they are chosen. Taking each feature's own percentile creates combinations that never occurred in any year.

**1.3 The yield model's history features have no values at inference time.**
- Features include previous-year yield and a 3-year average. ML section 4 states yield data ends in 2014. For a 2026 prediction these have no defined source.
- The suitability score divides the prediction by "the crop's normal yield in the district (3-year average)". That average is from 2012-2014 at best, twelve years old, with no trend handling. Labels (good >= 1.05, poor < 0.9) are thresholds on that ratio.
- The split trains up to 2008 and tests on 2012-2014. The spec does not say whether the shipped model is retrained on all years, so the shipped model's validation is undefined.

**1.4 Training covers 34 districts, the app serves 36.**
- District is a model feature. The two uncovered districts have no defined prediction path. Backend E9 and the frontend map show all 36.
- ML.5 requires a scenario table "for all 36 districts" but ML.4 only trains on 34.

**1.5 The 2010-2025 climate check cannot be a yield metric.**
- ML section 4 says to "also check on 2010-2025 climate". There is no yield ground truth after 2014, so no error can be computed for those years.
- The 1997-2014 weather (B's file) and the 2010-2025 weather (A's file) come from different pipelines. The spec does not say they define ET0, heat-stress days, rainy days and dry spell the same way. The model is trained on one and run on the other.
- Backend section 4.1 describes the 2010-2025 file as "season rainfall, ET0, temperature". The model also needs rainy days, longest dry spell, heat days and humidity. Whether the file has them is not stated.

**1.6 "Every number has a source badge" contradicts the data contract.**
- Frontend rule 2 and F9 ("no number without a badge, a test checks this") and ML rule 2 ("every value that reaches the farmer keeps its source") require a source on every number.
- In the contract, `yield_quintal_per_acre`, `profit_rs_per_acre`, `water_need_m3_per_acre`, every `StrategyResult` total, `impact`, `fertilizer` doses and the cost sub-items are plain numbers with no `SourcedValue`.
- `SourcedValue.status` only allows `live | cached | official_dataset`. There is no status for model outputs, computed values, farmer-supplied values (land, budget) or assumptions (flood irrigation, scenario probabilities 0.2 / 0.6 / 0.2). The F9 test as written fails on the contract's own example.

**1.7 Build-order circularity.**
- Frontend rule 3 requires samples "captured from the running backend" (backend C.2). Backend C.3 stubs the ML functions with `NotImplementedError`.
- A real `PlanResult` cannot be produced until the ML code exists. C.2 is "done when the frontend can build every screen from it". Nothing in the three files makes a real end-to-end plan available early. FE.1-FE.14 all depend on that sample.
- Every task in all three files is still not started, so this ordering is unresolved.

**1.8 The water budget needs inputs that nothing collects.**
- ML section 6: "groundwater share = farmer's borewell capacity, capped by the CGWB category". `FarmProfile` has no borewell-capacity field. The agent never asks for one, `missing` can only contain location, land and budget, and the frontend profile card has no row for it.
- Canal access has no field either. The canal share is computed from reservoir storage "for canal-irrigated farms", but `water_source` is only a farmer's word with no command-area check.
- `water_source: null` has no defined behaviour.
- The category caps (Safe: no cap, Semi-critical: reduced, Critical: strongly reduced, Over-exploited: minimal) and the effective-rain factor are written as words with no numbers. The spec requires each to cite a source in `SOURCES.md`; none is named in these files. SVC.7 cannot be finished until they exist.
- The CGWB data is by **block** (`groundwater_by_block.csv`) but locations resolve only to **district** (`admin2` through `districts.csv`). How a district gets one category is not defined. The map colours a whole district by one category.
- Reservoir data is mapped to a "district served". A farm's village being inside a command area is not checked.

**1.9 `WaterBudget` is one number but the plan has three scenarios.**
- `available_m3` and `need_m3` have no scenario dimension. The QP drought-safe strategy needs `W(s*)` for the Drought scenario. The frontend toggle says all numbers on screen change per scenario, and the gauge (F7) matches `water`. The contract has no way to carry scenario-specific availability or need.
- Which scenario `need_m3.traditional_plan` and `recommended_plan` use is not stated.

**1.10 The fertilizer-saving definition conflicts in three places.**
- ML section 6: saving = district actual fertilizer use per hectare vs the RDF for the recommended crop mix, 0 where actual use is already below the RDF.
- ML section 7 and the frontend summary tile: saving = vs the **Traditional** plan. Backend `impact.versus` is "traditional".
- These are two different quantities. The schema shows `fertilizer_saved_pct` as a number with no allowance for "not available" or 0 reasons.

**1.11 Two cost numbers for fertilizer (and seed) feed one budget.**
- `CropOption.cost_per_acre.fertilizer` is the DES/CACP 2022-23 figure. ML.8 gives an RDF dose priced at current MRPs (SVC.6 says fertilizer cost uses the ML.8 dose).
- Seed appears in `cost_of_cultivation.csv` and in `seed.csv`.
- The spec never says which value enters the optimizer budget constraint or whether a line is double counted in `total_rs`. The frontend cost chart shows "seed, fertilizer" from the 2022-23 split.

**1.12 Internal and contract types are used but never defined.**
- Not defined anywhere: `Candidate`, `ExcludedCrop` (partly in the example), `YieldPrediction`, `WaterNeed`, `FertilizerPlan`, `OptimizerInputs`, `Scenario` (with its all-year samples), `Suitability`, `Condition(s)` argument, and `Allocation` (only in an example).
- ML section 10 says "types are the Pydantic models in `backend/app/schemas.py`". C.1 (the file that defines them) is itself not started and is a dependency for all three owners.

**1.13 Farmer-facing messages are English-only in the contract.**
- `warnings[].message`, `excluded_crops[].message`, `relaxations_applied[].change`, `trace[].summary` and `source` names are single English strings in the examples. Only `Error.user_message` has mr / hi / en.
- Frontend S3 says a relaxed step shows "one plain sentence" and S4 shows "Onion not included: ..." in the farmer's language. The frontend i18n JSON has no way to translate free text it receives.
- `reason_code` (excluded crops) and `warnings[].code` have no defined list of values.

**1.14 The "no invented numbers" rule conflicts with the optimizer's own constants.**
- ML rule 1 forbids invented numbers in code. The spec itself fixes: scenario weights 0.2 / 0.6 / 0.2, the 0.65 diversification cap, the suitability thresholds 1.05 / 0.9, the 35 C heat threshold, the 10th / 90th percentile choice, the PSD ridge, `lambda` per risk appetite (only "high / medium / ~0"), and `gamma_i` ("small for one farm", no value, no source).
- None has a source or a stated status as a modelling choice. The contract example shows `risk_lambda: 0.5` with no definition of where it comes from.

**1.15 Prices are for today, profits are for harvest.**
- `CropOption.price` is a single live Agmarknet quote. Profit per acre multiplies it by a yield that is realised months later.
- `price_history_monthly.csv` is described only as "price risk". How a harvest-time price is formed for expected profit (and for the three scenarios) is not stated. The risk matrix is built from "historical years and price history" with no stated method for combining a yield from each past year with a price from each past year.
- Per-year profit samples for the covariance require a yield per past year, but yield data ends in 2014 and the climate years are 2010-2025.

---

## 2. Major

**2.1 The "Traditional" baseline is undefined under constraints.**
- It is the DES area-share mix for the **whole district**, scaled to the farmer's land. It includes crops that may be excluded for no price, not sowable now, or outside the budget.
- The example shows traditional water need (11,800 m3) above available water (7,600 m3), so Traditional is infeasible by design. Impact numbers (water saved, drought-year gain) then compare a feasible plan against an infeasible one. Whether Traditional is checked against land, budget, water or the cap is not stated.
- District area shares include crops of other seasons.

**2.2 LP max-profit baseline.**
- Section 7 says the water constraint is "in the chosen safety scenario s*", but LP is described as "expected profit only" with "same water". Which scenario's water limit LP uses is not stated, so "lambda = 0 reproduces the LP result" (a required test) is not guaranteed to hold.

**2.3 The cap `x_i <= 0.65 L` with one eligible crop.**
- "when more than one crop" is the only condition. If filters leave one crop, the cap is skipped and the plan is 100% one crop. If filters leave two crops with a budget or water limit, the cap can make the problem infeasible.

**2.4 Infeasibility has no end state and no payload.**
- AG.6 relaxes up to 3 times. What the farmer sees if the plan is still infeasible after 3 tries is not defined.
- `NO_ELIGIBLE_CROPS` is "200 with `excluded_crops`", but `PlanResult` requires `strategies` (x4), `recommended_strategy`, `impact` and `crops`. A shape with none of these is not defined.
- The OPT.4 infeasibility report (violated and binding constraints, amounts) has no field in the contract. The agent can read it, but the frontend and API cannot show it.

**2.5 Follow-up and re-optimization identity.**
- E1 follow-ups say "re-runs the plan". Whether the result has a new `plan_id` or `version + 1` is not stated. E3 keeps the same `plan_id` and bumps `version`.
- Frontend F13 "diff chips" ("Profit -Rs.4,000") need the previous plan. The SSE `plan` event carries only the new one.
- E3 changes risk, budget and land outside the agent. The agent's checkpointer (ML section 8.5) is not updated, so a later chat follow-up can start from a stale profile and plan inputs.
- The risk setting is controlled in two places: the profile-card slider (through the agent) and the plan slider (through E3).
- E3 returns a **template** explanation. The language of the page text can change provider mid-session without notice.

**2.6 The agent's flow and its LLM budget disagree.**
- ML section 8.4 says "at most 4 LLM calls per plan". The nodes that use the LLM are `extract_profile`, `relax_constraint` (up to 3), `explain` (plus one retry on a failed grounding check). That is at least 5, and 6 in the worst case.
- The `route` node (new plan / follow-up / question) has no stated mechanism. If it is an LLM call it is a further call not in the table.
- The 15 s provider timeout times three providers per call, times up to 6 calls, is far beyond the "warm plan under 5 s" target and the 3-minute demo.

**2.7 Two orchestration paths.**
- `run_plan(profile)` (backend SVC.10) and the LangGraph graph (ML section 8) both do gather -> predict -> optimize -> feasibility. ML AG.2 says the tools wrap services. Nowhere is it stated that the graph nodes call `run_plan` or the same functions. E2 and E1 can return different plans for the same profile.
- ML owns both `backend/app/ml` and `backend/app/agent` inside the backend repo tree; a failing ML function breaks `/api/plan` and the agent.

**2.8 The grounding check cannot handle the languages it must serve.**
- "Every number in the answer text must appear in the tool outputs (after unit formatting)." Marathi and Hindi answers may use Devanagari digits, Indian digit grouping (1,00,000), and number words ("hazar"). Only "unit formatting" is mentioned.
- The numbers in tool outputs are tonnes per hectare internally and quintals per acre at the boundary; the answer may round. The comparison rule is not defined.

**2.9 "Why this crop" is owned twice and by neither.**
- ML says the agent turns SHAP factors into "one plain sentence". The frontend says it renders factors as plain sentences with arrows from `top_factors`. The agent has no LLM slot for it (section 8.4). The contract has `feature` as a free string with no enumerated values.
- The cross-language sentence for each feature is therefore unowned.

**2.10 SSE is not representable in the generated types.**
- FE.0c generates TypeScript types from the FastAPI OpenAPI file. OpenAPI does not describe SSE event payloads. `TraceEvent`, `PlanResult` inside the `plan` event, `question`, `message`, `done` are used by the frontend stream parser but are not request or response models of any endpoint, so they will not appear in the generated types. Rule 4 ("do not hand-write types") then cannot hold for the main endpoint.

**2.11 The sample-data flag.**
- `VITE_USE_SAMPLES` must fail the production build. Playwright test FE.T2 runs "against the deployed backend". The spec does not say how the dev-only samples directory is kept out of the build.

**2.12 Lessons-learned contradictions.**
- Both lessons sections say "do not repeat hidden defaults", but `FarmProfile.defaults_used` already defaults risk appetite and irrigation method, and the efficiency (60%) for flood. The profile card shows "assumed" chips; the water-saving percentage rests on that assumed efficiency.

**2.13 The yield model sees district-level irrigation, soil and groundwater only.**
- Irrigation, soil values and groundwater category are fixed per district. A rainfed farmer and a borewell farmer in the same district get identical predicted yields per scenario, while the water budget and cost differ. The plan's yield per crop does not respond to `water_source`, `irrigation_method`, or the farmer's soil test (`soil_test` override).
- Soil values are constant per district, so within the model they are indistinguishable from the district feature.
- Features like `fertilizer use` in the model use district use, while the plan uses the RDF dose; the yield is not conditioned on the dose the plan recommends.

**2.14 Same quantity from two sources.**
- Recent rainfall exists as `recent_rainfall.csv` (static snapshot) and as live Open-Meteo `past_days=92`. ML section 5 says to use both. Which wins, and how a static snapshot stays current, is not stated.

**2.15 Sugarcane and other multi-season crops.**
- Sugarcane is priced at FRP (SVC.5), runs 12-18 months, and is compared against single-season crops on per-acre profit for one season. The yield model is per season. The spec has no duration handling.

**2.16 Cost and policy years are older than the plan date.**
- Costs are 2022-23. The example MSP is "2025-26". SVC.5 states the sugarcane FRP as Rs. 355/q "for 2025-26". On 31 Oct 2026 the 2026-27 year is in progress. The budget (current rupees) is compared with costs from 2022-23, and the plan reports profit with no inflation adjustment or caveat in the honest-limits list.

**2.17 Unresolved decisions block build.**
- D1 (LLM provider) is "default Gemini, test Groq and Sarvam and switch". D2 (speech) and D4 (hosting) have defaults, D3 does not exist in any file. Sarvam Marathi quality is unverified, but prompts, native-speaker review and tests (AG.8, FE.13) depend on the provider.

---

## 3. Contract and interface mismatches

**3.1 Wrong section references.**
- Backend C.3 says the ML signatures are in `ml/SPECS.md` section 8. They are in section 10 (section 8 is the agent).
- Backend section 6 uses frontend task numbers that do not match the frontend file:
  - Profile card: backend says FE.3, frontend FE.2.
  - Agent trace: backend FE.4, frontend FE.3.
  - Plan view, "why this crop", excluded crops: backend FE.5, frontend FE.4.
  - Scenario toggle and comparison: backend FE.6, frontend FE.5.
  - Water gauge: backend FE.7, frontend FE.6.
  - Source badges and cached-data warning: backend FE.9, frontend FE.7.
  - Spoken reply: backend FE.10, frontend FE.9.
  - Reload without losing the farm: backend FE.1, frontend FE.14.
- `ml/SPECS.md` cites `Teammate-B/data/DATA_FIXES.md`. After data intake (backend P0.2) the reports live in `docs/data_reports/teammate_b/`; that path will not exist.
- Dataset IDs (A9, B1, B10, B11) are used in the three files and defined only in a file not provided.

**3.2 Endpoint usage gaps.**
- E8 (location search) is not used by any frontend feature in section 6, although S7 says the "location not found" state offers "a map to pick it".
- E13 (health) is not used by the frontend, although S7 has a "server waking up" state.
- The trace status `skipped` has no UI in S3 (spinner, check, cached, failed only).

**3.3 Icon names.**
- Contract key icons are e.g. `"water"`; the frontend uses Lucide names (`droplets`, `wheat`, `cloud-rain`). No list of allowed values.

**3.4 Fertilizer plan signature.**
- `fertilizer_plan(crop_id, fertilizer_prices, crop_price)` takes `crop_price`, a leftover from the removed response curve. With a fixed RDF dose the price of the crop has no use in the described computation.
- ML section 6 says the dose is "converted to fertilizer bags"; the contract only has kg of N, P2O5, K2O. The fertilizer product (urea, DAP, MOP) to bag mapping is not defined.

**3.5 Units.**
- ML section 6 gives water need as mm and m3 per acre via `x 4.047`. 1 mm over 1 acre = 4.047 m3 is correct, but the efficiency adjustment is applied to mm before conversion while `water_need_m3_per_acre` in the contract is a single number per scenario with no stage detail.
- Frontend rule: acres, quintals, rupees only. Soil values, rainfall (mm) and `water` (m3) appear on screen; there is no farmer-unit rule for them.

**3.6 Language handling.**
- The spec says the plan text arrives in the farmer's language and the UI language can be changed in the picker. If the farmer changes the picker language after the plan is made, the existing explanation, `key_points`, warnings and trace sentences stay in the old language. No endpoint regenerates them without re-running E3 (template) or a new chat turn.
- The audio formats E5 accepts are webm / ogg / wav / mp3. The frontend records with `MediaRecorder` (webm/opus). iOS Safari records audio/mp4 and has no webm support in the same API, so a judge on an iPhone cannot use the mic.
- Sarvam text-to-speech input limits are not stated; the explanation text is unbounded in the contract (`explanation.text`) except by the "length limits" mentioned for LLM output.

**3.7 Hard-coded demo chips.**
- Frontend S5 shows chips "What if I only have Rs. 50,000?" and "Use drip irrigation". Frontend rule 1 forbids invented numbers in the UI. The amount is a literal.

---

## 4. Data and process problems

**4.1 Caching rule contradicts what is cached.**
- Backend 4.3: "Never store anything that did not come from a real API or file." The same table caches **plans** (24 h, SVC.11 plan store), and `CACHE_DB_PATH` also holds agent memory (messages, profiles). Those are generated, not fetched.

**4.2 Free-tier hosting and the cache.**
- D4 default is Hugging Face Spaces. Unless persistent storage is attached, the SQLite file (cache and agent memory) is lost on restart. The "serve the last real response as `cached`" fallback then has nothing to serve on a cold start, which is when the demo is most likely to hit a failed upstream call.
- `ml/SPECS.md` section 2: model files are "git-lfs or ignored if large". Ignored files are not in the repo, so they are not on the host.

**4.3 Rate limiting by IP behind a proxy.**
- 30 requests/min per IP on `/api/agent/chat` and `/api/plan`. Behind a hosting proxy the client IP is the proxy's address unless forwarded headers are used; many judges or devices behind one network share one limit. The spec does not mention forwarded headers.

**4.4 Manual dependency in a live system.**
- Reservoir storage comes from a weekly PDF parsed by a script (`ml/data_prep/build_reservoir_from_bulletin.py`) that lives in the ML folder but is a backend runtime data source. Its owner is not clear, and the PDF URL includes an unpredictable `<id>`, so the filename is not constructible. The data is refreshed by hand "weekly and before the demo".

**4.5 Order of setup tasks and the leaked API key.**
- P0.1 pushes the repo to GitHub, P0.2 takes in the reports that contain the data.gov.in key, and P0.3 replaces and revokes it. Between P0.2 and P0.3 the key can enter git history; the checklist for P0.2 replaces the key in reports but the original Drive copies keep it until revoked.

**4.6 Price availability can empty the plan.**
- The price fallback ends in "crop excluded" (SVC.5). Crops that are sown now but have few mandi arrivals now (and that Agmarknet does not list for a district) are removed. For a small district this can leave zero crops, which then runs into 2.4 (no payload for that state). The spec does not state how many eligible crops are expected on a typical day.

**4.7 Ownership.**
- Owners are "Teammate A" (backend), "Teammate B" (frontend) and "ML lead". P0.1 and P0.2 are assigned to "ML". Teammate A and B also produced the data and the data reports. The same people are named as owners of the data, the reports and two of the three components. Backend and ML code share the same repo tree (`backend/app/ml`, `backend/app/agent`) with split ownership and no stated rule for who fixes failures that cross the boundary.

**4.8 Test and acceptance gaps.**
- Several "done when" items cannot be verified from the spec: "Matches a hand-checked example" (ML.7: no example given), "Reviewed by a native speaker" (no named reviewer), "Checklist signed off" (FE.T3: no checklist), "Under 3 minutes" (QA.3).
- The Lighthouse target (>= 85) and the "warm plan under 5 s" target are set for different layers with no combined budget (plan latency + transcription + speech).

---

## 5. Honesty and limitation statements that are missing

The "honest metrics" lists (ML section 4, section 9, DD.5) state: yield data ends 2014, 34 districts, SHAP is attribution not causation. They do not mention:
- Costs are from 2022-23 and are compared to a 2026 budget.
- District-level soil, irrigation and groundwater are used for every farmer in the district (block-level variation and the farmer's own conditions are not in the yield prediction).
- Scenario probabilities (0.2 / 0.6 / 0.2) are fixed defaults, not forecasts.
- Prices are today's quotes, not harvest-time prices.
- Fertilizer saving is measured against district average use, not against this farmer.
- The traditional plan is a district average, not this farmer's practice.
- Water budget category caps and the effective-rain factor are assumptions until sourced.
- Sugarcane and other long-duration crops are compared on a single-season basis.
