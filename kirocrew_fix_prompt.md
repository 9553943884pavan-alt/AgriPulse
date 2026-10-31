# Kirocrew Prompt — Fix Backend SPECS & Implementation Plan

---

You are working inside the AgriPulse repository.
Root: `AgriPulse-main/`

Your job is to make **targeted edits** to two files:

- `backend/SPECS.md`
- `backend/IMPLEMENTATION_PLAN.md`

A verification review found **6 gaps, 4 minor divergences, and 5 still-open problems** between these two files. Fix every one of them as described below. Make no other changes. Do not touch any other file.

After every edit, re-read the edited section and confirm the fix is consistent with the surrounding context before moving on.

---

## FILE 1: `backend/SPECS.md`

### FIX S1 — Add `audio/mp4` to the Sarvam STT row in §4.2

In the table under **4.2 Live integrations**, find the **Sarvam speech** row.
The "Endpoint and key parameters" cell currently lists audio formats as `webm/ogg/wav/mp3`.

Change it to:

> `webm/ogg/wav/mp3/mp4` (mp4 = audio/mp4; required for iOS Safari, which has no webm support in MediaRecorder)

---

### FIX S2 — Fix the stale `"provider": "gemini"` value in §5.2 E1 event table

In section **5.2 Endpoints → E1 `POST /api/agent/chat`**, find the event table row for the `message` event. Its "Data" column contains:

```
{ "text": "…", "language": "mr", "provider": "gemini" }
```

Change `"gemini"` to `"sarvam-chat"` to reflect that Gemini was dropped (Sarvam AI is the only model provider per §1 ground rules).

---

### FIX S3 — Add CWC bulletin ID-probing description to §4.2

In the **CWC reservoirs** row of the §4.2 table, the "Endpoint and key parameters" cell currently ends with:

> `bulletin-DD-MM-YYYY-<id>.pdf`

Append the following sentence to that cell:

> The `<id>` part of the filename is unpredictable; `build_reservoir_from_bulletin.py` probes a small set of candidate ids for the most recent Thursday until one returns HTTP 200, then parses that PDF.

---

### FIX S4 — Add `analogue_year` and `all_year_samples` to the §5.1 `PlanResult.scenarios` example

In section **5.1 Shared types → PlanResult**, find the `"scenarios"` array in the JSON block:

```json
"scenarios": [ { "id": "drought", "label": "Drought", "season_rain_mm": {SourcedValue}, "probability": 0.2 },
               { "id": "normal",  "label": "Normal",  "season_rain_mm": {SourcedValue}, "probability": 0.6 },
               { "id": "excess",  "label": "Excess rain", "season_rain_mm": {SourcedValue}, "probability": 0.2 } ],
```

Replace it with:

```json
"scenarios": [ { "id": "drought", "label": "Drought", "season_rain_mm": {SourcedValue}, "probability": 0.2,
                 "analogue_year": 2002, "all_year_samples": [{SourcedValue}] },
               { "id": "normal",  "label": "Normal",  "season_rain_mm": {SourcedValue}, "probability": 0.6,
                 "analogue_year": 2019, "all_year_samples": [{SourcedValue}] },
               { "id": "excess",  "label": "Excess rain", "season_rain_mm": {SourcedValue}, "probability": 0.2,
                 "analogue_year": 2005, "all_year_samples": [{SourcedValue}] } ],
```

Then add a short paragraph after the PlanResult JSON block:

> `Scenario.analogue_year` is the real calendar year chosen as the P10 / P50 / P90 representative (Rabi ranked on `0.5 × Rabi rain + 0.5 × preceding Kharif rain`). `all_year_samples` is the list of all historical years' water-index values used to derive the percentile, returned as `SourcedValue` items with `status = official_dataset`. This field is ML-computed and API-visible so the frontend can show the analogue-year label on the scenario toggle.

---

### FIX S5 — Add `seasonal_ratio` as an explicit field on `CropOption` in §5.1

In section **5.1 → CropOption** JSON block, find:

```json
"expected_harvest_price": { "value": 4830, "unit": "rs_per_quintal", "source": "today's price × seasonal ratio 1.05 from 4 years of monthly history, floored at MSP", "as_of": "2026-10-31", "status": "computed" },
```

After that field, add:

```json
"seasonal_ratio": { "value": 1.05, "unit": "ratio",
                    "source": "4 years of monthly Agmarknet history (Beed, soybean)",
                    "as_of": "2026-10-31", "status": "computed",
                    "history_years": 4,
                    "note": "1.0 used and flagged when fewer than 3 years of history exist" },
```

---

### FIX S6 — Add `previous_version` to the §5.1 `PlanResult` example

In section **5.1 → PlanResult** JSON block, find:

```json
{ "plan_id": "pl_8f3a2c", "thread_id": "th_41d9", "version": 1,
```

Change it to:

```json
{ "plan_id": "pl_8f3a2c", "thread_id": "th_41d9", "version": 1, "previous_version": null,
```

Then add a note below the PlanResult JSON block:

> `previous_version` is `null` on the first version of a plan and on any version produced by E2 `/api/plan` directly. It is the integer previous version number on re-optimised plans (E3) and on chat follow-ups that change a fact. The frontend uses it to compute diff chips ("Profit − Rs. 4,000") without storing the old plan itself.

---

### FIX S7 — Add `is_agricultural_district` to the §5.2 E9 response example

In section **5.2 → E9 `GET /api/districts`**, find:

```json
{ "districts": [ { "district": "Beed", "names": { "mr": "बीड", "hi": "बीड", "en": "Beed" }, "latitude": 18.99, "longitude": 75.91, "groundwater_category": "Over-exploited", "status_color": "red" } ] }
```

Replace it with:

```json
{ "districts": [ { "district": "Beed", "names": { "mr": "बीड", "hi": "बीड", "en": "Beed" },
                   "latitude": 18.99, "longitude": 75.91,
                   "groundwater_category": "Over-exploited", "status_color": "red",
                   "is_agricultural_district": true } ] }
```

Add a sentence below the example:

> `is_agricultural_district` is `false` for Mumbai City and Mumbai Suburban (no DES crop statistics exist). The frontend map greys those two districts; the backend returns `DISTRICT_NOT_AGRICULTURAL` 422 if the farmer selects one.

---

### FIX S8 — Add a Dependency column to §7.1 Contracts table

In section **7.1 Contracts**, the table currently has columns `ID | Task | Done when | Status`.

Add a **Dependency** column as the 4th column (before Status):

| ID | Dependency |
|---|---|
| C.1 | P0.5 |
| C.2 | C.1 |
| C.3 | C.1 |
| C.4 | C.1 |

After the table add:

> C.2, C.3 and C.4 may be done in parallel after C.1 merges. No feature work may start before all four land.

---

### FIX S9 — Add Honest limits subsection to §8

Section **8. Lessons from the old prototype (v1)** ends with the "Do not repeat" list.

Append:

```
### Honest limits — must be visible in the UI and on the sources page

The following are known limitations. Each must appear in `warnings[]` or on the sources
page (E11), not hidden in internal docs only.

| Limitation | Where to surface |
|---|---|
| Costs are 2022-23 compared against a 2026 budget; no inflation adjustment | `OLD_COST_YEAR` warning on every plan |
| Soil, irrigation and groundwater are one value per district; two farmers in the same district get the same predicted yield | District context popup (E10) and sources page |
| Scenario probabilities (0.2 / 0.6 / 0.2) are fixed modelling defaults, not weather forecasts | `assumption` status on `Scenario.probability` |
| Prices shown are today's Agmarknet quotes; harvest-time price is estimated via seasonal ratio | `seasonal_ratio` field on `CropOption`; `computed` status on `expected_harvest_price` |
| Sugarcane and other multi-season crops are compared on a single-season per-acre basis | `SINGLE_SEASON_COMPARISON` warning when sugarcane is in any allocation |
| Rice and tur may have fewer than 3 years of price history in some districts; seasonal ratio defaults to 1.0 | `seasonal_ratio.note` field; `PRICE_NOT_ADJUSTED` warning |
| Changing the language picker after a plan is generated does not re-translate `explanation.text` or trace summaries; a new conversation is required | UI note in the language picker |
```

Also update the `warnings[].code` literal list in §5.1 (the line that begins `warnings[].code ∈`) to add `SINGLE_SEASON_COMPARISON`:

Find:
```
`warnings[].code` ∈ `CACHED_PRICES | CACHED_WEATHER | ASSUMED_IRRIGATION | ASSUMED_BOREWELL | DISTRICT_AVERAGE_SOIL | OLD_COST_YEAR | PRICE_NOT_ADJUSTED | SINGLE_CROP_ELIGIBLE`.
```

Replace with:
```
`warnings[].code` ∈ `CACHED_PRICES | CACHED_WEATHER | ASSUMED_IRRIGATION | ASSUMED_BOREWELL | DISTRICT_AVERAGE_SOIL | OLD_COST_YEAR | PRICE_NOT_ADJUSTED | SINGLE_CROP_ELIGIBLE | SINGLE_SEASON_COMPARISON`.
```

---

## FILE 2: `backend/IMPLEMENTATION_PLAN.md`

### FIX I1 — Add `audio/mp4` note to SVC.9

In **Phase 3 — Services**, find the `SVC.9` row. In the task description, find:

> `STT formats: webm/ogg/wav/mp3`

Change to:

> `STT formats: webm/ogg/wav/mp3 + **audio/mp4** (iOS Safari — MediaRecorder on iOS only produces audio/mp4; judges on iPhones must not lose mic access)`

---

### FIX I2 — Clarify `relative_humidity_2m_mean` as a derived daily field in SVC.3

In the `SVC.3` row, find `relative_humidity_2m_mean` in the fields list.

Add a parenthetical immediately after it:

> `relative_humidity_2m_mean` (derived as the daily mean of the hourly `relative_humidity_2m` series from Open-Meteo; stored as its own `SourcedValue` with `source = "Open-Meteo ERA5, daily mean of hourly relative humidity"`)

---

### FIX I3 — Fix the type count from 24 to 25 throughout

Make all three of the following changes:

1. Change the `§4` heading:
   - From: `## 4. All 24 Pydantic types for `schemas.py``
   - To:   `## 4. All 25 Pydantic types for `schemas.py``

2. Change the opening paragraph of §4:
   - From: `These must be defined at C.1, before any other work starts. All 24 are used`
   - To:   `These must be defined at C.1, before any other work starts. All 25 are used`

3. Change the C.1 row in the Phase 0 table:
   - From: `**`schemas.py`** with all 24 types (section 4 below)`
   - To:   `**`schemas.py`** with all 25 types (section 4 below)`

Then, after the closing ` ``` ` of the type list and before the **Validation rules** block, add:

> **Count note:** The 25th type is `Error` — it is an API-facing response schema and must be defined in `schemas.py` alongside the other 24 domain types. The original "24 types" label predated its addition as an explicit Pydantic model.

---

### FIX I4 — Add §11 Open Issues section

After **§10. Definition of done per task**, append:

```markdown
---

## 11. Known open issues (team decision required before demo)

These accepted limitations must be made user-visible before demo day.
Track each in the project board under label `open-issue`.

| ID | Issue | Accepted limitation | Required action |
|---|---|---|---|
| OI-1 | **District-level yield features** — rainfed and borewell farmers in the same district get identical predicted yields | Accepted; farm-level data does not exist | Surface in E10 district context popup and E11 sources page; add to honest-limits list |
| OI-2 | **Sugarcane single-season comparison** — 12-18 month crop compared per-acre with single-season crops | Accepted; noted in §8 lessons | Add `SINGLE_SEASON_COMPARISON` to `warnings[].code` literals; emit it whenever sugarcane appears in any strategy allocation |
| OI-3 | **Short price history for rice and tur** — fewer than 3 years of Agmarknet history in some districts; `seasonal_ratio` defaults to 1.0 | Fix: add commodity spelling aliases to `COMMODITY_ALIASES` in `build_price_history.py` and re-run | `seasonal_ratio.note` must say "ratio not adjusted: N years" when N < 3; emit `PRICE_NOT_ADJUSTED` warning |
| OI-4 | **Soil and rainfall units on-screen** — mm (rainfall) and m³ (water volume) appear on the water and district pages alongside the farmer-unit rule (acres / quintals / rupees) | Accepted; mm and m³ are standard for those quantities | Clarify in frontend SPECS §2 that mm and m³ are allowed farmer-facing units for rainfall and water volume |
| OI-5 | **Language picker post-plan** — changing the picker does not re-translate `explanation.text` or trace summaries | Accepted; re-translation requires a new LLM call | Add a UI note in the picker: "The farm plan summary stays in [language]. Start a new conversation to change it." No new backend endpoint needed |
```

---

## Verification checklist — run after all edits

1. `backend/SPECS.md` §4.2 Sarvam STT row contains `mp4`.
2. `backend/SPECS.md` §5.2 E1 `message` event shows `"provider": "sarvam-chat"`.
3. `backend/SPECS.md` §4.2 CWC row describes the ID-probing logic.
4. `backend/SPECS.md` §5.1 `PlanResult.scenarios` entries each have `analogue_year` and `all_year_samples`.
5. `backend/SPECS.md` §5.1 `CropOption` has a `seasonal_ratio` field after `expected_harvest_price`.
6. `backend/SPECS.md` §5.1 `PlanResult` JSON has `"previous_version": null`.
7. `backend/SPECS.md` §5.2 E9 response has `"is_agricultural_district": true`.
8. `backend/SPECS.md` §7.1 table has a Dependency column; C.2/C.3/C.4 depend on C.1.
9. `backend/SPECS.md` §8 has a new "Honest limits" subsection with 7 rows.
10. `backend/SPECS.md` §5.1 `warnings[].code` literal includes `SINGLE_SEASON_COMPARISON`.
11. `backend/IMPLEMENTATION_PLAN.md` SVC.9 mentions `audio/mp4` and iOS Safari.
12. `backend/IMPLEMENTATION_PLAN.md` SVC.3 has a parenthetical explaining `relative_humidity_2m_mean`.
13. `backend/IMPLEMENTATION_PLAN.md` §4 heading, opening paragraph, and C.1 row all say "25 types".
14. `backend/IMPLEMENTATION_PLAN.md` §11 exists with 5 open-issue rows (OI-1 through OI-5).

**Do not modify any other file. Do not change any task status (all remain ⬜). Do not alter any code, CSV, .env, or data file.**
