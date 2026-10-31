# AgriPulse Frontend Integration Plan

**Backend is ready. This document tells you exactly:**
1. What endpoints exist and what they send
2. What every piece of data looks like
3. What each screen shows and how it maps to backend data
4. The build order to get a working demo as fast as possible

---

## Part 1 — Endpoints at a Glance

| Method | Path | Used by | Returns |
|---|---|---|---|
| `POST` | `/api/agent/chat` | S1 Home — mic/chat | SSE stream (see below) |
| `POST` | `/api/plan` | Direct plan call | `PlanResult` |
| `POST` | `/api/plans/{plan_id}/reoptimize` | Risk slider (S4) | `PlanResult` (version 2+) |
| `GET` | `/api/threads/{thread_id}` | Page reload restore | `{profile, messages, plan_result}` |
| `POST` | `/api/transcribe` | Mic button | `{transcript, language_code}` |
| `POST` | `/api/speak` | 🔊 play button | `{audio_base64, content_type}` |
| `POST` | `/api/prefetch` | Fires when a place is heard | `{status: "queued"}` |
| `GET` | `/api/locations/search?q=Beed` | Location picker | `[{name, district, ...}]` |
| `GET` | `/api/districts` | Map, picker | `{districts: [...36 rows...]}` |
| `GET` | `/api/districts/{district}/context` | Map popup | district soil, rain, groundwater |
| `GET` | `/api/sources` | Sources page (S6) | list of data sources |
| `GET` | `/api/sources/health` | Health dots (S6) | per-source status |
| `GET` | `/api/health` | Cold-start polling (S7/F18) | `{status: "ok"}` |

Base URL: `http://localhost:8000` dev · `VITE_API_URL` in production.

---

## Part 2 — E1: The SSE Chat Stream

This is the main endpoint. Send a message, get back a stream of events.

**Request**
```ts
POST /api/agent/chat
Content-Type: application/json

{
  "message": "Beed, 5 acres, 70000 rupees, borewell",
  "language": "mr",           // mr | hi | en
  "thread_id": "th_41d9",     // null on first turn
  "profile_patch": null       // { "land_acres": 6 } when user edits profile card
}
```

**SSE event types** — each arrives as `event: <type>\ndata: <json>\n\n`

| Event | When | Key fields |
|---|---|---|
| `thread` | First (always) | `{thread_id: "th_41d9"}` — save this, pass on every next turn |
| `profile` | Agent understood the farm | `FarmProfile` object (see below) |
| `trace` | Each agent step completes | `TraceEvent` (see below) — update the timeline live |
| `question` | Agent needs a missing field | `{question: "…", missing_fields: ["land_acres"]}` — show and speak |
| `plan` | Plan is ready | Full `PlanResult` (see Part 3) — render the dashboard |
| `done` | Stream ends | `{}` — hide the loading state |
| `error` | Something failed | `{code, message, user_message}` — show error state |

**Minimal SSE client (TypeScript)**
```ts
async function streamChat(body: ChatRequest, onEvent: (type: string, data: unknown) => void) {
  const res = await fetch('/api/agent/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let eventType = 'message';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop()!;
    for (const line of lines) {
      if (line.startsWith('event:')) eventType = line.slice(6).trim();
      else if (line.startsWith('data:')) {
        onEvent(eventType, JSON.parse(line.slice(5).trim()));
        eventType = 'message';
      }
    }
  }
}
```

---

## Part 3 — The PlanResult Object

This is what the whole dashboard renders. Arrives via the `plan` SSE event or directly from `POST /api/plan`.

```
PlanResult
├── plan_id: string          // "pl_8f3a2c" — save for reoptimize
├── thread_id: string        // "th_41d9" — save for reload and follow-up
├── version: number          // 1 on first plan, increments on reoptimize
├── previous_version: null | number
├── created_at: string       // "2026-11-02T09:15:00+05:30"
├── profile: FarmProfile     // what the agent understood (show in S2 card)
├── location: Location       // resolved district + lat/lon
├── season: Season           // Kharif | Rabi, sowing window dates
├── scenarios: Scenario[3]   // drought | normal | excess (for the toggle)
├── crops: CropOption[]      // recommended crops with full data
├── excluded_crops: []       // crops left out and why
├── water: WaterBudget       // need vs available per scenario
├── strategies: StrategyResult[4]  // traditional | LP | QP balanced | QP drought-safe
├── recommended_strategy: string   // "qp_balanced" — star this one
├── impact: Impact           // water saved %, fertilizer saved %, drought profit gain
├── infeasibility: null | Infeasibility  // if no plan fits, show this screen
├── explanation: Explanation // LLM text in farmer's language
├── warnings: Warning[]      // amber banners
└── data_status: {live, cached, official_dataset}  // the sources chip
```

### FarmProfile (shows in S2 card)
```
location_text: "Beed"
land_acres: 5
budget_rs: 70000
water_source: "borewell"     // rainfed | borewell | canal | both | null
borewell_count: 1
irrigation_method: "flood"   // flood | sprinkler | drip | null
risk_appetite: "balanced"    // safe | balanced | max_profit → maps to Risk slider
language: "mr"
missing: []                  // ["land_acres"] if still unknown — highlight in amber
defaults_used: [             // show "assumed" chip on each
  { field: "irrigation_method", value: "flood", basis: "district majority method" }
]
```

### Scenario (for the toggle chips)
```
id: "normal"                 // drought | normal | excess
label: "Normal"              // already in farmer's language from API
season_rain_mm: SourcedValue // show on toggle: "Normal (700 mm)"
probability: 0.6             // show as percentage
analogue_year: 2019          // "like 2019" label on the chip
```

### CropOption (one crop card)
```
crop_id: "soybean"
names: { en: "Soybean", mr: "सोयाबीन", hi: "सोयाबीन" }
season: "Kharif"
suitability: {
  score: 1.12,
  label: "good",             // good | average | poor → badge color
  top_factors: [             // "Why this crop?" section
    { feature: "season_rainfall_mm", value: 742, unit: "mm",
      effect_quintal_per_acre: 1.2, direction: "up" }
  ]
}
yield_quintal_per_acre: { drought: 3.1, normal: 4.4, excess: 3.8 }  // SourcedValue per scenario
price: SourcedValue          // today's mandi price
expected_harvest_price: SourcedValue  // at harvest time
msp: SourcedValue            // minimum support price
cost_per_acre: {
  total_rs: 21400, seed: 1950, fertilizer: 2200, manure: 860,
  labour: 9300, machine: 3900, irrigation: 500, pesticide: 1480,
  interest: 600, reference_year: "2022-23", source: "DES/CACP"
}
fertilizer: { n_kg_per_acre: 12, p2o5_kg_per_acre: 20, k2o_kg_per_acre: 8 }
water_need_m3_per_acre: { drought: 1900, normal: 1500, excess: 1100 }
profit_rs_per_acre: { drought: 4200, normal: 9800, excess: 7600 }
duration_days: 110
harvest_month: "2027-02"
opens_on: null               // "2026-11-01" if sowing hasn't opened yet → show chip
```

### StrategyResult (one row in the comparison table)
```
id: "qp_balanced"            // traditional | lp_max_profit | qp_balanced | qp_drought_safe
label: "QP balanced"
kind: "qp"
allocations: [
  { crop_id: "soybean", acres: 2.5, share_pct: 50,
    cost_rs: 53500, water_m3: 3750,
    profit_rs: { drought: 10500, normal: 24500, excess: 19000 } }
]
totals: { land_used_acres: 5, budget_used_rs: 66200,
          fertilizer_kg: { n: 61, p2o5: 98, k2o: 40 }, water_m3: 7100 }
profit_by_scenario_rs: { drought: 21000, normal: 52000, excess: 44000 }
expected_profit_rs: 45600
worst_case_profit_rs: 21000
feasible: true
binding_constraints: ["water"]
infeasibility: null
```

### SourcedValue (every farmer-visible number)
```
value: 4600
unit: "rs_per_quintal"
source: "Agmarknet (data.gov.in)"
source_url: "https://api.data.gov.in/resource/..."
as_of: "2026-10-31"
status: "live"   // live | cached | official_dataset | model | computed | farmer_input | assumption
```
**Rule: every `SourcedValue` renders a `<SourceBadge>`. No number appears bare.**

Badge colors:
- `live` → green dot
- `cached` → amber dot + "as of 30 Oct"
- `official_dataset` → blue dot + year
- `model` → purple dot
- `computed` → grey dot
- `farmer_input` → grey dot
- `assumption` → orange dot + "this is an estimate"

### TraceEvent (live timeline row)
```
id: "ev_07"
node: "gather_data"
step: "get_prices"
status: "ok"              // running | ok | cached | failed | skipped
started_at: "..."
duration_ms: 812
summary: "Agmarknet: 6 crops priced (Beed mandi)"
source: { name: "Agmarknet", url: "...", status: "live" }
fallback_used: null       // "last real quote, 2026-10-30" when cached
```

---

## Part 4 — Other Endpoints

### E2: Direct plan (no chat)
Use this for testing or if you want to skip the agent chat.
```ts
POST /api/plan
{ location_text, land_acres, budget_rs, water_source, language }
→ PlanResult
```

### E3: Reoptimize (risk slider)
Call when the user moves the risk slider or edits profile fields.
```ts
POST /api/plans/{plan_id}/reoptimize
{ risk_appetite: "safe" }   // or land_acres, budget_rs
→ PlanResult  (version: 2, previous_version: 1)
```
Animate the profit/water numbers changing. Under 2 s.

### E4: Restore thread (page reload)
```ts
GET /api/threads/{thread_id}
→ { profile, messages, plan_result }
```
Save `thread_id` to `localStorage`. On page load, if present, call this and restore the plan without re-running.

### E5: Transcribe voice
```ts
POST /api/transcribe
Content-Type: audio/mp4     // or audio/webm, audio/ogg, audio/wav
Body: raw audio bytes
→ { transcript: "Beed, 5 acres...", language_code: "mr-IN" }
```
**iOS Safari sends `audio/mp4`. Must check `MediaRecorder.isTypeSupported` first.**
```ts
const mimeType = ['audio/webm;codecs=opus','audio/mp4','audio/aac']
  .find(t => MediaRecorder.isTypeSupported(t)) ?? 'audio/mp4';
```

### E6: Speak (TTS)
```ts
POST /api/speak
{ text: "तुमच्या शेतासाठी...", language_code: "mr-IN" }
→ { audio_base64: "...", content_type: "audio/mpeg" }
```
Decode base64 and play in an `<audio>` element. Fallback: `window.speechSynthesis`.

### E7: Prefetch
Fire-and-forget. Call as soon as you resolve a district name.
```ts
POST /api/prefetch
{ location_text: "Beed" }
→ { status: "queued" }
```

### E8: Location search
```ts
GET /api/locations/search?q=Beed
→ [ { name, district, state, latitude, longitude } ]
```

### E9: All districts (for the map)
```ts
GET /api/districts
→ { districts: [ { district, latitude, longitude, is_agricultural_district } ] }
```

### E10: District context (map popup)
```ts
GET /api/districts/Beed/context
→ { district, groundwater_category, season_rain_mm, soil_npk, reservoir_storage_pct }
```

### E11 + E12: Sources and health
```ts
GET /api/sources         → list of all data sources with name, url, type, date
GET /api/sources/health  → per-source live status dot
```

### E13: Health (cold-start polling)
```ts
GET /api/health
→ { status: "ok", version: "1.0.0" }
```
Poll this every 3 s when you get a 503, show "AgriPulse is waking up…" banner.

---

## Part 5 — Screen → API Mapping

### S1: Home (Voice/Chat)

```
User speaks
  → MediaRecorder (check isTypeSupported for iOS!)
  → POST /api/transcribe (audio bytes)
  → get { transcript, language_code }
  → POST /api/agent/chat { message: transcript, language, thread_id: null }
  → SSE stream:
      "thread"  → save thread_id to localStorage + state
      "profile" → show S2 FarmProfileCard
      "trace"   → append row to S3 TraceTimeline (live)
      "question"→ show question text, speak it via E6
      "plan"    → render S4 dashboard
      "done"    → hide spinner
      "error"   → show S7 error state
```

### S2: Farm Profile Card

Renders `PlanResult.profile`. Each row maps to one field:
- 📍 `location_text` / `location.resolved_name`
- 🌱 `land_acres` (acres)
- 💰 `budget_rs` (₹ Indian format)
- 💧 `water_source`
- 🚿 `irrigation_method` — if in `defaults_used`, show orange "assumed" chip
- ⚖️ `risk_appetite` → maps to the Risk slider position

`missing` array: highlight those rows in amber. Agent will ask for them.

Edit flow: user taps ✏️ → inline input → on confirm send:
```ts
POST /api/agent/chat {
  message: "",
  thread_id: saved_thread_id,
  profile_patch: { land_acres: 6.0 }
}
```

### S3: Agent Trace

Driven by `trace` SSE events. One `<TraceRow>` per event:

```
status icon  |  step name  |  source badge  |  duration
spinner      |  gather_data: get_weather  |  ● live  |  0.3 s
✔            |  gather_data: get_prices   |  ● cached "30 Oct"  |  0.9 s
✖ (red)      |  gather_data: get_soil     |  — failed  |  failed: using district average
```

Map `status` to icon:
- `running` → spinner
- `ok` → ✔ green
- `cached` → ⚠ amber
- `failed` → ✖ red + show `fallback_used`
- `skipped` → – grey

### S4: Plan Dashboard — Block by Block

#### Summary Bar (4 tiles)
```
source: PlanResult.impact

Expected profit     → impact.drought_profit_gain_rs is NOT this.
                      Use strategies[recommended_strategy].expected_profit_rs
Worst-year profit   → strategies[recommended_strategy].worst_case_profit_rs
Water saved %       → impact.water_saved_pct.value  (vs Traditional)
Fertilizer saved %  → impact.fertilizer_saved_pct.value
```
Each tile has a `<SourceBadge status="computed">`.

#### Scenario Toggle (3 chips)
```
source: PlanResult.scenarios[0..2]

For each: { label, analogue_year, season_rain_mm.value, probability }

Render: (Normal ● 2019 · 700 mm · 60%)
        (Drought ● 2002 · 410 mm · 20%)
        (Excess rain ● 2005 · 920 mm · 20%)

Selected scenario → all profit_rs, yield, water figures change to that column.
```

#### Risk Slider
```
Maps profile.risk_appetite → slider position:
  safe = 0, balanced = 1, max_profit = 2

On change:
  POST /api/plans/{plan_id}/reoptimize { risk_appetite: "safe" }
  → new PlanResult → animate number changes
```

#### Land Plan (Donut + List)
```
source: strategies[selected_strategy].allocations

Donut: each crop = one segment, size = acres
List row per crop:
  crop name (in farmer's language: names[language])
  acres
  share_pct %
  cost_rs ₹
  water_m3 → show as tanker loads (÷10) AND m3
  profit_rs[selected_scenario] ₹

If opens_on is set: show chip "Sowing opens 1 Nov"
```

#### Strategy Comparison Table + Chart
```
source: PlanResult.strategies[4]

Table columns: Strategy | Expected profit | Worst-year | Water m3 | Budget used | Feasible
Rows: traditional | lp_max_profit | qp_balanced ★ | qp_drought_safe

Strategy color codes:
  traditional:     #78909C (grey)
  lp_max_profit:   #1565C0 (blue)
  qp_balanced:     #2E7D32 (green) ← recommended, starred
  qp_drought_safe: #00897B (teal)

Grouped bar chart: x = strategy, bars = drought/normal/excess profit
Tap a strategy row → switch land plan to that strategy
```

#### Water Gauge
```
source: PlanResult.water (WaterBudget, one per scenario)

Semicircle gauge:
  total arc = available_m3.total.value
  fill = need_m3.recommended_plan.value
  color = fill > total → danger red, else primary green

Below the gauge:
  Rain:         water.available_m3.rain.value m3        ● live/cached
  Groundwater:  water.available_m3.groundwater.value m3 ● computed
  Canal:        water.available_m3.canal.value m3       ● computed

Groundwater badge: water.basis.groundwater_category.value
  "Over-exploited" → red  |  "Safe" → green  |  "Semi-critical" → amber

"Traditional plan needs X m3 more" = need_m3.traditional_plan.value - need_m3.recommended_plan.value
```

#### Cost Breakdown
```
source: crops[].cost_per_acre

Stacked bar per crop:
  segments: seed | fertilizer | manure | labour | machine | irrigation | pesticide | interest
  Show reference year "2022–23" from cost_per_acre.reference_year

Convert fertilizer to bags:
  DAP bags = fertilizer.p2o5_kg_per_acre / 23   (1 bag DAP = 23 kg P2O5)
  Urea bags = fertilizer.n_kg_per_acre / 18.4    (1 bag Urea = 18.4 kg N after subtracting DAP contribution)
  MOP bags = fertilizer.k2o_kg_per_acre / 25     (1 bag MOP = 25 kg K2O)
```

#### Crop Cards
```
source: PlanResult.crops[] (CropOption)

One card per crop:
  Header:  name (farmer language) · suitability label badge (good=green/average=amber/poor=red)
  Yield:   yield_quintal_per_acre[selected_scenario] quintal/acre  ● model badge
  Prices:  today price · expected harvest price · MSP  (each ● badge)
  Profit:  profit_rs_per_acre[selected_scenario] per acre  ● computed
  Water:   water_need_m3_per_acre[selected_scenario] → show as inches of rain too
           (1 inch = 2.54 mm · 1 mm/acre ≈ 4.05 m3 → 1 m3 ≈ 0.247 mm)
  Duration: duration_days → "X months" (round up)
            If duration_days > 120 → show "occupies land X months" warning + per-year profit

  "Why this crop?" expandable section (suitability.top_factors):
    Each factor has a fixed feature code. Map it to a label:
      season_rainfall_mm → "Seasonal rainfall"
      heat_stress_days   → "Heat stress days"
      soil_n             → "Soil nitrogen"
      soil_ph            → "Soil pH"
      district_yield_avg → "District average yield"
    Show: "↑ Seasonal rainfall 742 mm adds +1.2 quintal/acre"
```

#### Excluded Crops
```
source: PlanResult.excluded_crops[]

reason_code i18n map:
  NO_REAL_PRICE          → "No market price found for {district}"
  NO_YIELD_DATA          → "No yield data for {district}"
  NOT_SOWABLE_NOW        → "Cannot be sown right now"
  NOT_GROWN_IN_DISTRICT  → "Not grown in {district}"
  WATER_INFEASIBLE       → "Needs more water than available"
  OVER_BUDGET            → "Costs more than your budget"
```

#### Map (react-leaflet)
```
source: E9 districts list + E10 context per district

Farm pin: location.latitude, location.longitude
District fill color: groundwater_category from E10
  safe          → #2E7D32 green
  semi_critical → #F9A825 amber
  critical      → #EF6C00 orange
  over_exploited→ #C62828 red
  dark_zone     → #880000 dark red

Popup on click: district name, rain, groundwater category, reservoir %
```

#### Warnings Banner
```
source: PlanResult.warnings[]

code i18n map:
  CACHED_PRICES         → "Market prices are from {as_of}"
  CACHED_WEATHER        → "Weather data is from {as_of}"
  ASSUMED_IRRIGATION    → "Irrigation method assumed: {method}"
  ASSUMED_BOREWELL      → "Borewell capacity is an estimate"
  DISTRICT_AVERAGE_SOIL → "Soil values are district averages"
  OLD_COST_YEAR         → "Cost data is from 2022–23"
  PRICE_NOT_ADJUSTED    → "Price history less than 3 years"
  SINGLE_CROP_ELIGIBLE  → "Only one crop met all criteria"
  SINGLE_SEASON_COMPARISON → "Sugarcane occupies land 12 months; profit shown per season"
```

#### Sources Chip
```
source: PlanResult.data_status
"● 14 live  ● 2 cached  ● 31 official dataset"
Tap → open S6 Sources page
```

---

## Part 6 — Build Order (Fastest Path to Demo)

Build in this order. Each step produces something you can show.

### Day 1: Skeleton + data flow
1. **FE.0a–d**: Vite + React + Tailwind, folder layout, design tokens, i18n (mr/hi/en), type generation from `/docs` OpenAPI
2. **FE.0c**: SSE client + fetch client wrapping all endpoints
3. **F18**: Cold-start screen — poll `/api/health`, show "waking up" banner on 503

### Day 2: Voice → Plan (the core loop)
4. **F1**: Mic button (check `isTypeSupported` for iOS) → `POST /api/transcribe` → display transcript
5. **F4**: `POST /api/agent/chat` → SSE → live trace timeline (S3) from `trace` events
6. **F3**: Farm profile card (S2) from `profile` SSE event, editable rows, assumed chips
7. **F5 basic**: Render `PlanResult` when `plan` SSE event arrives — summary bar + crop cards only

### Day 3: Full dashboard
8. **F6**: Scenario toggle chips + strategy comparison table
9. **F7**: Water gauge semicircle
10. **F9**: `<SourceBadge>` on every `SourcedValue` — run the "no bare number" test
11. **F5 complete**: Land plan donut, cost stacked bars, excluded crops, warnings, sources chip

### Day 4: Interactions + polish
12. **F8**: Risk slider → `POST /api/plans/{id}/reoptimize` → animate number diff
13. **F10**: 🔊 button → `POST /api/speak` → play audio, fallback to `speechSynthesis`
14. **F13**: Follow-up chat (pass `thread_id`), diff chips showing what changed
15. **F14**: Page reload → `GET /api/threads/{thread_id}` → restore plan from localStorage thread_id

### Day 5: Map + sources + edge cases
16. **F11**: react-leaflet district map, groundwater colors, E9 + E10
17. **F12**: Sources page (S6) from E11 + E12 health dots
18. **F15**: Every error code → farmer-language message + retry action
19. **F17**: Location picker from E8 when place not found
20. **F16**: Prefetch fire-and-forget on district resolve

### Day 6: Quality
21. **FE.T1**: Unit tests — formatting, badge coverage, SSE parsing
22. **FE.T4**: Lighthouse ≥ 85 mobile, axe accessibility
23. **FE.T3**: Real phone check (Android, 360 px, 4G)
24. **DD.2**: Deploy to Vercel with `VITE_API_URL`

---

## Part 7 — TypeScript Types to Generate

Run this once to get all types from the running backend:

```bash
curl http://localhost:8000/openapi.json -o openapi.json
npx openapi-typescript openapi.json -o src/api/types.ts
```

Key generated types you will use everywhere:
- `PlanResult` — the main object
- `FarmProfile` — S2 card
- `StrategyResult` — comparison table
- `CropOption` — crop cards
- `WaterBudget` — water gauge
- `Scenario` — toggle chips
- `SourcedValue` — every number + badge
- `TraceEvent` — live timeline
- `Warning` — amber banners
- `Infeasibility` — no-plan screen

---

## Part 8 — State Architecture

```
Zustand store (src/state/store.ts):
  threadId: string | null      ← from "thread" SSE event, persist to localStorage
  planId: string | null        ← from PlanResult.plan_id
  language: "mr" | "hi" | "en"← from farmer speech or language picker
  selectedScenario: "drought" | "normal" | "excess"  ← toggle state
  selectedStrategy: string     ← "qp_balanced" default, changes on table click
  plan: PlanResult | null      ← the full current plan
  profile: FarmProfile | null  ← live updates from SSE
  traceEvents: TraceEvent[]    ← grows as stream arrives
  isStreaming: boolean

TanStack Query (src/api/queries.ts):
  useDistricts()          → GET /api/districts    (long cache)
  useDistrictContext(d)   → GET /api/districts/{d}/context
  useSources()            → GET /api/sources
  useSourcesHealth()      → GET /api/sources/health  (30s refetch)
  useThread(id)           → GET /api/threads/{id}   (restore on load)
```

---

## Part 9 — CORS and Dev Setup

The backend already has CORS enabled. Add `VITE_API_URL=http://localhost:8000` to your frontend `.env`.

**Start both together:**
```bash
# Terminal 1 — backend
cd AgriPulse-main/backend
.\venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (once you create the frontend)
cd AgriPulse-main/frontend
npm run dev
```

**The backend is live** — `GET http://localhost:8000/api/health` returns `{"status":"ok"}` right now. You can start building against it immediately.

---

## Part 10 — Key Constraints to Not Break

1. **No invented numbers** — every value must come from the API. If `SourcedValue` is null, show "Not available".
2. **Every farmer-visible number needs a `<SourceBadge>`** — the "no bare number" test will fail your CI if you miss one.
3. **iOS mic** — always check `MediaRecorder.isTypeSupported` before recording.
4. **Indian number format** — use `new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR'})`.
5. **Farmer units** — acres (not ha), quintals (not kg), ₹ (not USD). Water as tanker loads + m3. Fertilizer as bags + kg.
6. **No blank screens** — skeletons while loading, S7 error state for every failure, "server waking up" for 503.
7. **Thread persistence** — save `thread_id` to `localStorage` so reload restores the farm.
