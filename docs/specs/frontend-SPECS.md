# Frontend SPECS: Design, Screens and Features

**Owner:** Teammate B · **Works with:** [`backend/SPECS.md`](../backend/SPECS.md) (the API this app calls, section 5) and [`ml/SPECS.md`](../ml/SPECS.md) (what the numbers mean)
**Stack:** React + Vite + Tailwind CSS · TanStack Query · Recharts · react-leaflet · i18next · Vitest + Testing Library · Playwright

**Status:** ⬜ Not started · 🟨 In progress · ✅ Done · ⛔ Blocked · ➖ Dropped
Update the **Status** column in the same pull request that does the work.

---

## 1. Ground rules

- **No mock, hardcoded or dummy data.** Every number on screen comes from the API and shows where it came from. Breaking this rule means instant disqualification.
- **Scoring this part supports:** *Impact / USP (25)*: voice in local languages, drought-safe plans, water saved · *AI Reasoning (25)*: the live agent trace · *Live Demo Robustness (30)*: no blank screens, clear errors, works on a phone.
- **Code rules for the frontend:**
  1. **No invented numbers in the UI.** If a value is missing, show "Not available" with the reason from the API, never a placeholder number. Assumed values (irrigation method, borewell yield) are allowed only when they arrive from the API in `defaults_used` and are shown with an orange `assumption` badge and an "assumed" chip; the app never invents one itself.
  2. **Every farmer-visible number has a source badge** showing one of `live | cached | official_dataset | model | computed | farmer_input | assumption` (backend section 5.1). Ids, counts, durations and version numbers are not farmer-visible and carry none. The automated test checks exactly that set.
  3. **Sample responses are for development only.** Day 1 uses `docs/api_examples/contract/` (the interface examples the three of us agree at C.1; an agreement, not product data). From M2 onward use `docs/api_examples/live/`, captured from a real backend run. Both are switched on by `VITE_USE_SAMPLES=true`, which lives **outside** `src/` and is imported through one module (`src/api/samples.ts`) that is tree-shaken away when the flag is off. The production build fails if the flag is set, and CI greps the built bundle for a known string from the sample files as a second check. The Playwright run (FE.T2) always runs with the flag off against the deployed backend.
  4. **Types come from the API.** Generate TypeScript types from the backend OpenAPI file; do not hand-write them.
  5. **No keys in the frontend.** The browser never calls Sarvam or data.gov.in directly; only our API. Sarvam is the only model provider and it is reached through the backend.
  6. **Tests ship with the code.**

---

## 2. Users and design principles

**Who uses it:** a smallholder farmer, often on a low-end Android phone (360 px wide), slow 3G/4G, sunlight on the screen, comfortable in Marathi or Hindi, maybe unable to read well. Second audience: hackathon judges on a laptop.

| Principle | What it means in the UI |
|---|---|
| **Talk first** | The mic is the biggest button on the first screen. Typing works the same way. |
| **Icons plus words** | Every action and every number has an icon and a short label in the farmer's language. |
| **Farmer units** | Acres, quintals, ₹ with Indian grouping (₹1,00,000). Never hectares, tonnes or "kg/ha". Water is shown as **tanker loads and inches of rain** next to the m3 figure (1 tanker = 10 m3), fertilizer as **bags** next to the kg, and soil values as Low / Medium / High next to the number, so no screen asks a farmer to read a scientific unit on its own. |
| **One thing per screen on a phone** | Summary first; details open on tap. |
| **Never a blank screen** | Skeletons while loading; the live trace shows progress; errors say what to do next. |
| **Trust** | Source badge on every number; the agent's steps are visible; cached data is clearly marked. |
| **Big and readable** | Body text ≥ 16 px, buttons ≥ 48 px tall, contrast ≥ 4.5:1. |

---

## 3. Design system

### Colors (Tailwind tokens)
| Token | Value | Used for |
|---|---|---|
| `primary` | `#2E7D32` (earth green) | Main buttons, recommended plan, "Normal" scenario |
| `primary-soft` | `#E8F5E9` | Cards of the recommended plan |
| `accent` | `#F9A825` (harvest amber) | Highlights, mic button ring |
| `drought` | `#EF6C00` | "Drought" scenario, warnings |
| `rain` | `#1565C0` | "Excess rain" scenario, water gauge |
| `danger` | `#C62828` | Errors, failed trace steps, "Over-exploited" groundwater |
| `ink` / `muted` | `#1F2933` / `#52606D` | Text |
| `surface` / `page` | `#FFFFFF` / `#F7F5EF` | Cards / background (warm off-white) |

**Strategy colors** (same everywhere: chart, table, chips): Traditional `#78909C` · LP max-profit `#1565C0` · QP balanced `#2E7D32` · QP drought-safe `#00897B`.
**Source status badges:** `live` green dot · `cached` amber dot (shows "as of <date>") · `official dataset` blue dot (shows year).
Dark mode is optional (Tailwind `dark:` classes) and not required for the demo.

### Typography and shape
- Fonts: **Noto Sans Devanagari** (Marathi, Hindi) + **Inter** (English and numbers), self-hosted; body 16 px, headings 20–28 px, numbers in tabular style.
- Radius 16 px on cards, 12 px on buttons; shadows soft; spacing in multiples of 4 px.
- Icons: Lucide (wheat, droplets, cloud-rain, mic, volume-2, map-pin, badge-check).

### Layout breakpoints
`< 640 px` phone (single column, bottom navigation) · `640–1024 px` tablet · `> 1024 px` desktop (two columns: conversation left, dashboard right).

---

## 4. Screens

### S1. Home: talk to AgriPulse (phone)
```
┌──────────────────────────────┐
│ 🌾 AgriPulse        [मराठी ▾] │  ← language picker (mr / hi / en)
├──────────────────────────────┤
│  Namaskar! Tell me about     │
│  your farm.                  │
│  "I have 5 acres near Beed,  │
│   ₹70,000, a borewell"       │
│                              │
│        ╭───────────╮         │
│        │    🎤     │         │  ← big mic button (hold or tap to talk)
│        ╰───────────╯         │
│      Tap and speak           │
│  ┌────────────────────────┐  │
│  │ or type here…        ➤ │  │  ← chat box, same behaviour as voice
│  └────────────────────────┘  │
├──────────────────────────────┤
│  Farm profile (what I heard) │  ← S2 card appears here after the first turn
└──────────────────────────────┘
```
States: idle · recording (waveform + timer, "Release to send") · transcribing · agent thinking (trace, S3) · asking a question (the agent's question shown large + spoken, mic ready) · error (message + retry).

### S2. Farm profile card
```
┌──────────────────────────────┐
│ 📍 Beed, Maharashtra    ✏️    │
│ 🌱 Land      5 acres     ✏️    │
│ 💰 Budget    ₹70,000     ✏️    │
│ 💧 Water     Borewell    ✏️    │
│ 🚿 Irrigation  Flood (assumed) │  ← "assumed" chip for each default the agent used
│ ⚖️ Risk   Safe ○──●──○ Max    │
└──────────────────────────────┘
```
Each row editable by tapping ✏️ (inline input or choice chips) or by saying "no, it's 3 acres". Missing required fields are highlighted in amber and asked by the agent. Editing re-runs the plan.

### S3. Agent trace (live)
A collapsible timeline under the conversation, driven by `trace` events:
```
✔ Understood your farm                    0.8 s
✔ Weather  Open-Meteo        ● live       0.3 s
✔ Soil     Soil Health Card  ● official   0.0 s
⚠ Prices   Agmarknet         ● cached     0.9 s   "last quote 30 Oct"
✔ Water budget  CGWB + CWC               0.1 s
✔ Crops    5 Rabi candidates              0.2 s
… Optimizing 4 strategies
```
Rows: icon by status (spinner running, ✔ ok, ⚠ cached, ✖ failed in red with the fallback used, – skipped in grey with the reason), tool name, source badge, duration. A failed or relaxed step shows one plain sentence ("Water limit was too low, so I reduced the area by 0.4 acre").

> **Every example on this page is a Rabi plan** (chickpea, jowar, wheat, lentil, grapes), because the specs were written on 31 Oct 2026 and those are the crops sowable or opening then (ml/SPECS.md section 3A). Screens must never be mocked up with crops that cannot be sown on the day of the demo. A crop whose sowing window has not opened yet shows an "opens 1 Nov" chip.

### S4. Plan dashboard
**Desktop (> 1024 px)**
```
┌────────────────────────────────────────────────────────────────────────────┐
│ SUMMARY   Expected profit ₹45,600 │ Worst-year profit ₹21,000 │ Water −40% │ Fertilizer −22% │
├───────────────────────────────┬────────────────────────────────────────────┤
│ SCENARIO  (Normal) (Drought) (Excess rain)      Risk slider: Safe ─●─ Max profit │
├───────────────────────────────┼────────────────────────────────────────────┤
│ LAND PLAN  donut: acres/crop  │ STRATEGY COMPARISON                         │
│ Chickpea 2.5 ac  Jowar 1.5 ac │ grouped bars: profit in Drought/Normal/Excess│
│ Wheat 1.0 ac (sowing opens 1 Nov) │ table: Traditional | LP | QP balanced ★ | QP drought-safe │
├───────────────────────────────┼────────────────────────────────────────────┤
│ WATER GAUGE  need vs available│ COSTS  stacked bar per crop: seed, fertilizer, │
│ rain / groundwater / canal    │ labour, irrigation, pesticide, interest       │
├───────────────────────────────┴────────────────────────────────────────────┤
│ CROP CARDS  (one per crop)  ▸ why this crop (SHAP factors)  ▸ price, yield, profit │
├────────────────────────────────────────────────────────────────────────────┤
│ MAP  Beed ● groundwater: Over-exploited (red)                │ SOURCES  ● 14 live ● 2 cached ● 31 official │
└────────────────────────────────────────────────────────────────────────────┘
```
**Phone:** the same blocks as a vertical stack with the summary pinned at the top, sections collapsed behind headings, and a bottom bar: **Plan · Compare · Water · Chat**.

Block details
| Block | Content | Data (backend section 5.1) |
|---|---|---|
| **Summary** | Four tiles: expected profit, worst-year profit, water saved %, fertilizer saved % (vs Traditional). Each with a source badge | `impact`, recommended `strategies[]` |
| **Scenario toggle** | Normal / Drought / Excess rain chips (colors from the design system). Switching changes all numbers on screen to that scenario and shows the season rainfall used | `scenarios`, `profit_by_scenario_rs`, `CropOption.*_by_scenario` |
| **Risk slider** | Safe ↔ Balanced ↔ Max profit; on release calls reoptimize and animates the change | E3 `reoptimize` |
| **Land plan** | Donut and list: crop, acres, share, cost. Recommended strategy by default | `strategies[].allocations` |
| **Strategy comparison** | Table + grouped bar chart of the four strategies: expected profit, worst-year profit, water, fertilizer, cost. The recommended one is starred. Tap a column to switch the land plan to that strategy | `strategies` |
| **Water gauge** | Semicircle gauge: water needed vs available, split into rain / groundwater / canal. Under it: groundwater category badge and "Traditional plan needs X m³ more" | `water` |
| **Costs** | Stacked bar per crop with the itemized split and "reference year 2022-23" | `CropOption.cost_per_acre` |
| **Crop cards** | Crop name (local language) · suitability label (good / average / poor) · yield in quintals per acre by scenario · today's price, expected harvest price and MSP · profit per acre · "occupies the land N months" for long-duration crops. **"Why this crop?"** renders `suitability.top_factors`: each `feature` is a fixed code (ml/SPECS.md section 3), and **the frontend owns one i18n sentence per code in mr / hi / en**, filled with the value and direction (↑ rainfall 742 mm, ↓ long dry spell). No LLM is involved, so this card is always translated and always consistent | `CropOption` |
| **Excluded crops** | One line: "Onion not included: no real market price found." | `excluded_crops` |
| **Map** | react-leaflet: farm pin, district colored by groundwater category (green safe → red over-exploited), tap for reservoir, rain departure | E9, E10 |
| **Sources chip** | "● 14 live ● 2 cached ● 31 official dataset", opens S6 | `data_status` |
| **Warnings** | Amber banner for `warnings` (for example "Prices are from 30 Oct") | `warnings` |

### S5. Conversation and follow-ups
Chat thread under or beside the dashboard. The agent's answer: text, a 🔊 play button (spoken reply) and 3–4 key points with icons. Suggested follow-up chips are built from the farmer's own plan, never from literals: "What if I had 30% less money?" renders with the farmer's actual budget (₹49,000 for a ₹70,000 budget), "Show the drought year", "Use drip irrigation". The amount in a chip is always derived from `profile`, so no invented number appears in the UI. A follow-up re-runs the plan and highlights what changed (diff chips: "Profit −₹4,000", "Water −12%").

### S6. Sources and data health
List of all datasets and APIs: name, publisher, link, licence, date, type, and a live health dot (green, amber, red) with latency and "serving cached data" notes. Header: "No mock data: every number comes from these sources".

### S7. Error and empty states
No internet · location not found (map to pick it) · speech not understood ("Please try again or type") · no eligible crops ("We could not find real prices for any suitable crop") · server waking up (retry banner) · everything uses a farmer-language message from the API's `user_message`.

---

## 5. Frontend architecture

```
frontend/
├── src/
│   ├── api/            generated types, fetch client, SSE client (EventSource over fetch), query hooks
│   ├── features/
│   │   ├── chat/       Mic, ChatBox, MessageList, FollowUpChips, useRecorder, useSpeech
│   │   ├── profile/    FarmProfileCard, EditableRow
│   │   ├── trace/      TraceTimeline, TraceRow
│   │   ├── plan/       Summary, ScenarioToggle, RiskSlider, LandPlan, StrategyCompare,
│   │   │               WaterGauge, CostBreakdown, CropCard, ExcludedCrops, Warnings
│   │   ├── map/        DistrictMap
│   │   └── sources/    SourcesPage, HealthDot
│   ├── components/     SourceBadge, MoneyText, QuintalText, Skeleton, ErrorState, Icon
│   ├── i18n/           mr.json, hi.json, en.json
│   ├── state/          thread, plan, language (Zustand) + TanStack Query cache
│   └── pages/          Home, Plan, Sources
├── public/
└── SPECS.md
```
- **Server state:** TanStack Query. **UI state:** small Zustand store (thread id, language, selected scenario and strategy).
- **Streaming:** `POST /api/agent/chat` read as a stream; each SSE event updates the trace, profile or plan in the store.
- **Audio:** `MediaRecorder` with a format check, because **iOS Safari records `audio/mp4`, not webm**: the app picks the first of `audio/webm;codecs=opus`, `audio/mp4`, `audio/aac` that `isTypeSupported` accepts, and sends that. A judge on an iPhone must be able to use the mic, so FE.T3 includes one iOS check. Then `POST /api/transcribe`; reply audio from `POST /api/speak` played in an `<audio>` element; if speak fails, use the browser's `speechSynthesis`.
- **Formatting helpers:** Indian number grouping (`en-IN`), ₹, acres, quintals; Devanagari digits optional per language.
- **i18n:** all labels from JSON files; the language comes from the farmer's speech (API `language`) and can be changed in the picker; plan text comes from the API already in that language.
- **Performance:** route-level code splitting (the map and charts load only on the plan page); mobile Lighthouse performance ≥ 85; first paint under 2 s on 4G.
- **Accessibility:** labels for icon buttons, focus states, keyboard use on desktop, `aria-live` for trace and agent messages, no information by color alone.

---

## 6. Features

| ID | Feature | What the user sees | Done when | Data (backend) | Status |
|---|---|---|---|---|---|
| F1 | **Voice and chat home** | S1 with big mic, typing, states; mic permission help | Works on a 360 px phone; recording ≤ 60 s | E5, E1 | ⬜ |
| F2 | **Language picker + translations** | mr / hi / en for every label. The language follows the farmer's speech and can be changed at any time. Backend messages arrive as `{code, params}` (backend 5.1), so warnings, excluded-crop reasons, relaxation steps and trace summaries are translated **in the app**, not sent as English. Changing the picker re-renders all of them instantly; the one piece that cannot change without a new request is the LLM `explanation.text`, so the app shows a "translate this answer" button that asks for it in the new language | All labels and every message code translated in three languages; native-speaker review | `language`, message codes | ⬜ |
| F3 | **Farm profile card** | S2 with editable rows, "assumed" chips, missing fields highlighted | Edit re-runs the plan; voice correction works | `profile` event, `profile_patch` | ⬜ |
| F4 | **Agent trace** | S3 live timeline with sources and durations | Rows appear as events stream; failures in red with fallback | `trace` events | ⬜ |
| F5 | **Plan dashboard** | S4: summary, land plan, costs, crop cards with "why this crop", excluded crops | Every field from `PlanResult` shown; phone and desktop layouts | E1 `plan`, E2 | ⬜ |
| F6 | **Scenario toggle + strategy comparison** | Normal / Drought / Excess chips; 4-strategy chart and table | Numbers change with the scenario; recommended strategy starred | `scenarios`, `strategies` | ⬜ |
| F7 | **Water gauge** | Need vs available split by source; "water saved vs traditional" | Matches `water` and `impact` | `water`, `impact` | ⬜ |
| F8 | **Risk slider** | Safe ↔ Max profit, live re-solve with an animated change | Under 2 s per change; keeps the scenario selected | E3 | ⬜ |
| F9 | **Source badge on every number** | Coloured dot per status (live, cached, official dataset, model, computed, farmer input, **assumption**) + tap for source, link and date. Assumption badges carry a short "this is our estimate, not a measurement" line | Every farmer-visible number has a badge (a test walks the rendered plan and fails on a bare number) | `SourcedValue` | ⬜ |
| F10 | **Spoken reply** | 🔊 button on each answer, plays in the farmer's language; text always shown | Plays in mr and hi; falls back to browser speech | E6 | ⬜ |
| F11 | **District map** | Farm pin, groundwater color, tap for context | Colors from the API; popup works on touch | E9, E10 | ⬜ |
| F12 | **Sources and health page** | S6 with live status dots | Shows all datasets and APIs | E11, E12 | ⬜ |
| F13 | **Follow-up chat** | S5 chips and chat; diff chips after a follow-up | "What if ₹50,000?" updates the plan and shows the change | E1 with `thread_id` | ⬜ |
| F14 | **Reload without losing the farm** | Same plan after refresh | State restored from the thread | E4 | ⬜ |
| F15 | **Errors, empty and offline states** | S7 | Every API error code has a farmer-language message | `Error.user_message` | ⬜ |
| F16 | **Prefetch trigger** | Invisible: as soon as a place is heard, warm the caches | Called once per new location; failure ignored | E7 | ⬜ |
| F17 | **Location picker** | When a place is not found or is ambiguous, show suggestions to tap, and a map pin as the last resort | Farmer can always reach a valid district; non-agricultural districts (Mumbai City / Suburban) say so plainly instead of failing | E8, E9 | ⬜ |
| F18 | **Server waking up** | On a cold start or a 503, poll health and show "waking up, a few seconds" with a retry, never a dead screen | Cold start on the deployed backend shows this, then the plan | E13 | ⬜ |

---

## 7. Tasks

### 7.1 Setup
| ID | Task | Done when | Status |
|---|---|---|---|
| FE.0a | Vite + React + Tailwind skeleton with the folder layout in section 5, ESLint, Vitest | `npm run dev` and `npm test` work | ⬜ |
| FE.0b | Design tokens (section 3), fonts, base components (`SourceBadge`, `MoneyText`, `QuintalText`, `Skeleton`, `ErrorState`) | Storybook-style demo page shows all of them | ⬜ |
| FE.0c | Generate types from the backend OpenAPI; fetch + SSE client; `VITE_USE_SAMPLES` switch that fails the production build | Types compile; build fails when the flag is on | ⬜ |
| FE.0d | i18n setup with mr / hi / en and an Indian-format number helper | Language switch changes all labels | ⬜ |
| FE.0e | CI step: lint, tests and build on every pull request | Green check on PR | ⬜ |

### 7.2 Build order (each task = one feature in section 6)
| ID | Task | Needs from backend | Done when | Status |
|---|---|---|---|---|
| FE.1 | F1 Voice and chat home | E1, E5 (or samples) | Feature done criteria in section 6 | ⬜ |
| FE.2 | F3 Farm profile card | `profile` event | as above | ⬜ |
| FE.3 | F4 Agent trace | `trace` events | as above | ⬜ |
| FE.4 | F5 Plan dashboard (summary, land plan, costs, crop cards) | `PlanResult` | as above | ⬜ |
| FE.5 | F6 Scenario toggle and strategy comparison | `strategies`, `scenarios` | as above | ⬜ |
| FE.6 | F7 Water gauge | `water`, `impact` | as above | ⬜ |
| FE.7 | F9 Source badges everywhere | `SourcedValue` | as above | ⬜ |
| FE.8 | F8 Risk slider | E3 | as above | ⬜ |
| FE.9 | F10 Spoken reply | E6 | as above | ⬜ |
| FE.10 | F13 Follow-up chat with diff chips | E1 | as above | ⬜ |
| FE.11 | F11 District map | E9, E10 | as above | ⬜ |
| FE.12 | F12 Sources and health page | E11, E12 | as above | ⬜ |
| FE.13 | F2 Translations and native-speaker review | n/a | All labels in mr and hi reviewed | ⬜ |
| FE.14 | F14, F15, F16 Reload, error states, prefetch | E4, E7 | as above | ⬜ |

### 7.3 Quality and delivery
| ID | Task | Done when | Status |
|---|---|---|---|
| FE.T1 | Unit tests for formatting, badges ("no number without a badge"), SSE parsing, stores | Green in CI | ⬜ |
| FE.T2 | End-to-end test (Playwright) of the demo story: speak → question → plan → scenario toggle → follow-up | Passes against the deployed backend | ⬜ |
| FE.T3 | Phone check on a real low-end Android: touch sizes, readability in sunlight, 4G speed | Checklist signed off | ⬜ |
| FE.T4 | Accessibility check (axe) and Lighthouse mobile ≥ 85 | Reports saved | ⬜ |
| DD.2 | Deploy frontend to Vercel with `VITE_API_URL` set to the backend | Public URL works from a phone | ⬜ |
| DD.3 | Record the 2–3 minute demo video from the rehearsed script | Uploaded | ⬜ |
| DD.4 | Screenshots for the README and slides (phone and desktop, three languages) | Added to `docs/` | ⬜ |
