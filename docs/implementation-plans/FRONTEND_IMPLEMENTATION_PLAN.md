# AgriPulse — Frontend Implementation Plan

> **React + Vite + Tailwind CSS**
> Visual reference: four screenshots (Home, Farm Profile, Dashboard, Strategy Comparison) used for design language only — not reproduced.
> Backend authority: `backend/SPECS.md`, `ml/SPECS.md`, `frontend/SPECS.md`.
> **DO NOT start coding until this plan is reviewed and approved.**

---

## Table of Contents

1. [Project and Backend Analysis](#1-project-and-backend-analysis)
2. [Page Structure and Navigation](#2-page-structure-and-navigation)
3. [React Component Architecture](#3-react-component-architecture)
4. [Design System](#4-design-system)
5. [Page-wise UI Implementation](#5-page-wise-ui-implementation)
6. [Backend API Integration Strategy](#6-backend-api-integration-strategy)
7. [Loading, Error, and Empty States](#7-loading-error-and-empty-states)
8. [Responsive Design](#8-responsive-design)
9. [Testing and Validation](#9-testing-and-validation)
10. [Implementation Order and Dependencies](#10-implementation-order-and-dependencies)

---

## 1. Project and Backend Analysis

### 1.1 Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| State (server) | TanStack Query v5 |
| State (UI) | Zustand |
| Charts | Recharts |
| Map | react-leaflet |
| i18n | i18next + react-i18next |
| Testing | Vitest + Testing Library + Playwright |
| Icons | Lucide React |
| Audio | MediaRecorder API + browser SpeechSynthesis fallback |

### 1.2 Backend Capabilities (from `backend/SPECS.md`)

Every frontend feature must map to a real backend endpoint. The table below is the canonical mapping.

| Endpoint | Method | What it returns | Frontend uses it for |
|---|---|---|---|
| `E1 /api/agent/chat` | POST (SSE stream) | `thread`, `profile`, `question`, `trace`, `plan`, `message`, `done`, `error` events | All of Home page — voice, chat, trace, plan preview |
| `E2 /api/plan` | POST | `PlanResult` | Demo fallback; direct plan from a complete profile |
| `E3 /api/plans/{id}/reoptimize` | POST | `PlanResult` (same id, version+1) | Risk slider, scenario switch |
| `E4 /api/threads/{id}` | GET | profile + plan + messages | Page reload / session restore |
| `E5 /api/transcribe` | POST (multipart) | `{ text, language, duration_s }` | Mic button → text |
| `E6 /api/speak` | POST | `audio/wav` bytes | Spoken reply |
| `E7 /api/prefetch` | POST | `{ status, district, stages }` | Warm caches as soon as a place is heard |
| `E8 /api/locations/search` | GET `?q=` | location suggestions | Location autocomplete, ambiguous place picker |
| `E9 /api/districts` | GET | 36 districts + coords + groundwater status color | District map layer |
| `E10 /api/districts/{district}/context` | GET | groundwater, reservoirs, rain, irrigation | Map popup, water detail |
| `E11 /api/sources` | GET | all datasets + APIs with metadata | Sources page |
| `E12 /api/sources/health` | GET | live status dot per source | Sources page health |
| `E13 /api/health` | GET | `{ status, models_loaded, data_files }` | Cold-start / server waking up screen |

### 1.3 Key Data Types (from `backend/SPECS.md` section 5.1)

These types drive every component's props. TypeScript types are **generated from the backend OpenAPI file** — never hand-written (frontend rule 4).

| Type | Used in |
|---|---|
| `SourcedValue` | Every farmer-visible number — carries `value`, `unit`, `source`, `source_url`, `as_of`, `status` |
| `FarmProfile` | Home profile card, Farm Profile page |
| `CropOption` | Crop cards — yield, price, cost, suitability, SHAP factors |
| `StrategyResult` | Strategy comparison — allocations, profit by scenario, water, fertilizer |
| `PlanResult` | Dashboard, Home preview — the full answer |
| `TraceEvent` | Agent trace timeline |
| `WaterBudget` | Water gauge (one per scenario) |
| `Error` | Every error state (`code`, `user_message` in mr/hi/en) |

### 1.4 Source Status Values

Every farmer-visible number has a `SourceBadge`. The seven statuses from the contract:

| Status | Color | Meaning |
|---|---|---|
| `live` | Green dot | Fetched from an API just now |
| `cached` | Amber dot | Last real API response; shows "as of \<date\>" |
| `official_dataset` | Blue dot | From `data/` files; shows year |
| `model` | Purple dot | Our yield/suitability model output |
| `computed` | Grey dot | Arithmetic over other sourced values |
| `farmer_input` | Grey dot | The farmer said it |
| `assumption` | Orange dot | Declared modelling constant; never a measurement |

### 1.5 Farmer Units (display rules)

All of these come from the backend already converted; the frontend only formats them.

| Quantity | Display | Never show |
|---|---|---|
| Land | acres | hectares |
| Yield | quintals/acre | kg/ha |
| Water | tanker loads + litres/m³ | m³ alone |
| Fertilizer | bags + kg | kg/ha alone |
| Money | ₹ with Indian grouping (₹1,00,000) | plain integers |
| Soil | Low/Medium/High + number | number alone |

### 1.6 Constraints That Affect the UI

- **No mock/invented data ever.** If a value is missing, show "Not available" with the reason from the API.
- **`assumption` badge** on orange for every default the agent used (irrigation method, borewell yield) — these come from `profile.defaults_used`.
- **Backend sends i18n codes, not English sentences.** `warnings[]`, `excluded_crops[].reason_code`, `relaxations_applied[]`, and `trace[].summary` all arrive as `{ code, params }`. The frontend holds one i18n key per code.
- **`explanation.text`** is the only free-text field; it is already in the farmer's language.
- **iOS Safari records `audio/mp4`, not webm.** `useRecorder` must pick the first supported format.
- **`VITE_USE_SAMPLES=true`** fails the production build. CI greps the built bundle for sample strings. This flag is only for development against contract examples.

---

## 2. Page Structure and Navigation

### 2.1 Application Shell

```
AppShell
├── Sidebar (desktop ≥ 1024 px) / BottomNav (mobile < 640 px)
├── TopBar (logo, language picker, profile icon)
│   └── AgriPulse wordmark + leaf icon (top-left)
│   └── Language selector: mr / hi / en (top-right)
└── MainContent (routed pages)
```

The sidebar is always visible on desktop, collapsed to a bottom navigation bar on mobile. The sidebar contains:

| Nav item | Icon | Route | Backed by |
|---|---|---|---|
| Home | `home` | `/` | E1, E5, E6 |
| Farm Profile | `clipboard-list` | `/profile` | E1 profile_patch, E2 |
| Dashboard | `bar-chart-2` | `/dashboard` | E3, PlanResult in store |
| Comparison | `git-compare` | `/comparison` | E3, strategies in PlanResult |
| Sources | `database` | `/sources` | E11, E12 |

### 2.2 Routing

```
/                   → HomePage
/profile            → FarmProfilePage
/dashboard          → DashboardPage
/comparison         → ComparisonPage
/sources            → SourcesPage
```

Route-level code splitting: the map and Recharts chart bundles load only on `/dashboard` and `/comparison`. The map loads only on `/dashboard`.

### 2.3 Global State (Zustand store)

```
store
├── thread_id          string | null
├── plan               PlanResult | null
├── profile            FarmProfile | null
├── language           "mr" | "hi" | "en"
├── selectedScenario   "drought" | "normal" | "excess"
├── selectedStrategy   "traditional" | "lp_max_profit" | "qp_balanced" | "qp_drought_safe"
└── actions            setThread, setPlan, setProfile, setLanguage, setScenario, setStrategy
```

Server state (API responses, cache, loading flags) lives in TanStack Query. UI state lives in Zustand.

---

## 3. React Component Architecture

### 3.1 Folder Layout

```
frontend/
└── src/
    ├── api/
    │   ├── client.ts           fetch wrapper (JSON + error normalisation)
    │   ├── sseClient.ts        SSE stream reader, parses E1 events
    │   ├── queryHooks.ts       TanStack Query hooks per endpoint
    │   ├── samples.ts          CONTRACT EXAMPLES ONLY — tree-shaken in prod
    │   └── types.ts            re-export from generated OpenAPI types
    ├── components/             purely presentational, no API calls
    │   ├── SourceBadge.tsx     coloured dot + tooltip (source, url, as_of)
    │   ├── MoneyText.tsx       ₹ Indian grouping
    │   ├── QuintalText.tsx     quintals + optional bags
    │   ├── AcreText.tsx        acres display
    │   ├── WaterText.tsx       litres + tanker-load equivalent
    │   ├── Skeleton.tsx        loading placeholder shapes
    │   ├── ErrorState.tsx      farmer-language error card
    │   ├── EmptyState.tsx      "no eligible crops" / "not available" card
    │   ├── Icon.tsx            Lucide wrapper with accessible label
    │   ├── Badge.tsx           pill chip (suitability, assumption, etc.)
    │   ├── Card.tsx            rounded-2xl shadow container
    │   ├── Button.tsx          primary / secondary / ghost variants
    │   ├── Slider.tsx          risk preference slider (Safe ↔ Max profit)
    │   ├── ScenarioToggle.tsx  Normal / Drought / Excess chips
    │   └── LanguagePicker.tsx  mr / hi / en selector
    ├── features/
    │   ├── chat/
    │   │   ├── MicButton.tsx
    │   │   ├── ChatBox.tsx
    │   │   ├── MessageList.tsx
    │   │   ├── FollowUpChips.tsx
    │   │   ├── useRecorder.ts  (format check: webm → mp4 → aac)
    │   │   └── useSpeech.ts    (E6 speak + browser SpeechSynthesis fallback)
    │   ├── profile/
    │   │   ├── FarmProfileCard.tsx   inline summary card (from SSE profile event)
    │   │   ├── FarmProfileForm.tsx   full edit form (Farm Profile page)
    │   │   └── EditableRow.tsx
    │   ├── trace/
    │   │   ├── TraceTimeline.tsx
    │   │   └── TraceRow.tsx
    │   ├── plan/
    │   │   ├── SummaryTiles.tsx
    │   │   ├── LandPlan.tsx          donut chart (Recharts PieChart)
    │   │   ├── StrategyCompare.tsx   4-strategy table + grouped bar (Recharts BarChart)
    │   │   ├── WaterGauge.tsx        semicircle gauge (Recharts RadialBarChart)
    │   │   ├── CostBreakdown.tsx     stacked bar per crop (Recharts BarChart)
    │   │   ├── CropCard.tsx          per-crop card with "why this crop"
    │   │   ├── ExcludedCrops.tsx     excluded reason list
    │   │   ├── Warnings.tsx          amber banner list
    │   │   └── PlanPreview.tsx       4-tile mini summary for Home sidebar
    │   ├── map/
    │   │   └── DistrictMap.tsx       react-leaflet, lazy-loaded
    │   └── sources/
    │       ├── SourcesPage.tsx
    │       └── HealthDot.tsx
    ├── i18n/
    │   ├── mr.json
    │   ├── hi.json
    │   └── en.json
    ├── state/
    │   └── store.ts            Zustand store
    ├── pages/
    │   ├── HomePage.tsx
    │   ├── FarmProfilePage.tsx
    │   ├── DashboardPage.tsx
    │   ├── ComparisonPage.tsx
    │   └── SourcesPage.tsx
    ├── layouts/
    │   ├── AppShell.tsx
    │   ├── Sidebar.tsx
    │   ├── TopBar.tsx
    │   └── BottomNav.tsx
    └── main.tsx
```

### 3.2 Component Principles

- Every component is typed with generated types from OpenAPI — no inline type definitions for API data.
- `SourceBadge` is co-located with every number. The badge test (`FE.T1`) renders a full `PlanResult` and fails if any farmer-visible number lacks one.
- All i18n keys come from JSON files. Free-text from the API (`explanation.text`) is rendered as-is; everything else is a translated code.
- Chart data is transformed in a `useMemo` hook inside the component — no transformation outside.

---

## 4. Design System

### 4.1 Color Tokens (Tailwind config)

```js
// tailwind.config.js
colors: {
  primary:     { DEFAULT: '#2E7D32', soft: '#E8F5E9' },
  accent:      '#F9A825',   // harvest amber, mic ring
  drought:     '#EF6C00',   // drought scenario, warnings
  rain:        '#1565C0',   // excess rain scenario, water gauge
  danger:      '#C62828',   // errors, over-exploited groundwater
  ink:         '#1F2933',   // body text
  muted:       '#52606D',   // secondary text
  surface:     '#FFFFFF',   // cards
  page:        '#F7F5EF',   // warm off-white background
  // Strategy colors — fixed everywhere: chart, table, chip
  strategy: {
    traditional:    '#78909C',
    lp:             '#1565C0',
    qp_balanced:    '#2E7D32',
    qp_drought:     '#00897B',
  }
}
```

### 4.2 Typography

| Role | Font | Size | Weight |
|---|---|---|---|
| Body | Inter + Noto Sans Devanagari (self-hosted) | 16 px | 400 |
| Heading 1 | Inter | 28 px | 700 |
| Heading 2 | Inter | 24 px | 600 |
| Heading 3 | Inter | 20 px | 600 |
| Label / badge | Inter | 12 px | 500 |
| Numbers (tabular) | Inter (tabular-nums) | context | 600 |

Noto Sans Devanagari is loaded for `mr` and `hi` only via a conditional class on `<html>`.

### 4.3 Spacing, Radius, Shadow

- Spacing unit: 4 px (`p-1 = 4px`, `p-4 = 16px`, `p-6 = 24px`).
- Card radius: `rounded-2xl` (16 px).
- Button radius: `rounded-xl` (12 px).
- Card shadow: `shadow-sm` (soft, 1 dp).
- Minimum button height: 48 px (`min-h-12`).
- Minimum touch target: 48 × 48 px.

### 4.4 Layout Breakpoints

| Name | Width | Layout |
|---|---|---|
| Mobile | < 640 px | Single column, bottom nav |
| Tablet | 640–1023 px | Single column, sidebar hidden |
| Desktop | ≥ 1024 px | Two columns: sidebar (240 px fixed) + content |

### 4.5 Visual Design Language (from screenshots — inspirational only)

- **Header banner**: a subtle landscape illustration strip at the top (warm greens and sky tones). Pure CSS gradient is acceptable; no external image dependencies needed.
- **Sidebar**: white background with a left border accent on the active item (`border-l-4 border-primary`), icon + label per item.
- **Cards**: white `rounded-2xl shadow-sm`, internal padding `p-6`. Section headers inside cards use `text-ink font-semibold text-lg`.
- **Stat tiles** (summary row): icon in a coloured circle (amber for profit, blue for water, green for crops), large number below, small "vs traditional" delta in green/red.
- **Charts**: Recharts with the strategy color tokens. No grid lines visible by default; x-axis and y-axis labels in `muted`.
- **Farmer mascot illustration** (bottom-left of sidebar on desktop): a static SVG of a farmer in the field; decorative only, no interaction.

---

## 5. Page-wise UI Implementation

### 5.1 HomePage (`/`)

**Purpose:** the main conversation interface. A farmer speaks or types; the agent responds in real time.

**Layout (desktop):**
```
┌─ Sidebar ─┬──────────── Chat panel (55%) ────────────┬──── Right panel (45%) ────┐
│  Home ●   │  Talk to AgriPulse                       │  Agent Execution Trace     │
│  Profile  │  ┌──────────────────────────────────┐    │  (live timeline)           │
│  Dashboard│  │  Message list (scrollable)        │    ├───────────────────────────┤
│  Comparison│ │  • Agent greeting                 │    │  Current Plan Preview      │
│  Sources  │  │  • Farm Profile card (inline)     │    │  (4 summary tiles)         │
│           │  │  • Follow-up chips                │    ├───────────────────────────┤
│           │  └──────────────────────────────────┘    │  Top Crop Recommendations  │
│           │  ┌────────────── Input bar ──────────┐   │  (3 crop mini-cards)       │
│ [mascot]  │  │  🎤  Type your message here…   ➤  │   └───────────────────────────┘
└───────────┴──────────────────────────────────────┴────────────────────────────────┘
```

**Mobile:** single column. Mic button centred and large. Trace collapsible below the chat. Plan preview + crop cards collapse behind a "View Plan" button.

**Components needed:**

| Component | What it does | API |
|---|---|---|
| `MicButton` | Idle / recording / transcribing states; holds the mic to talk, tap to toggle. Format check on mount via `useRecorder` | E5 transcribe |
| `ChatBox` | Textarea with send button; same path as voice input | E1 chat SSE |
| `MessageList` | Renders agent messages (text + 🔊 + key points with icons) and farmer messages. Auto-scrolls to latest | E1 `message` event |
| `FarmProfileCard` (inline) | Summary of what the agent heard — location, land, budget, water, irrigation, risk. Each row has an edit ✏️. Assumption rows have an orange chip. Missing required fields highlighted amber | E1 `profile` event; `profile_patch` on edit |
| `FollowUpChips` | 3–4 chips derived from the farmer's own plan (never literals). Amounts derived from `profile` | E1 with thread_id |
| `TraceTimeline` | Live stream of `trace` SSE events — step, source badge, duration, status icon. Collapsible. | E1 `trace` event |
| `PlanPreview` | 4 stat tiles: estimated profit, crop area, water requirement, no. of crops. Each has a `SourceBadge` and a delta vs traditional | PlanResult in store |
| `CropMiniCard` | Crop image placeholder, name, acres, profit, water. Links to full crop card on Dashboard | `strategies[].allocations` |

**SSE event handling in `HomePage`:**

```
thread  → store.setThread(id)
profile → store.setProfile(profile); show FarmProfileCard
question → show large question bubble, activate mic, pause further SSE
trace   → append to TraceTimeline
plan    → store.setPlan(plan); update PlanPreview + CropMiniCards
message → append to MessageList; show 🔊 button
done    → set loading = false
error   → show ErrorState with user_message
```

**States:**
- Idle (greeting shown, mic big)
- Recording (waveform animation + timer)
- Transcribing (spinner on mic)
- Agent thinking (trace streaming, progress bar)
- Asking a question (agent's question shown large, mic activated)
- Plan ready (right panel populated)
- Error (ErrorState component)

### 5.2 FarmProfilePage (`/profile`)

**Purpose:** view and edit the farm profile. Editing re-runs the plan.

**Layout (desktop):** two columns — form on the left (65%), "What happens next?" info panel on the right (35%).

**Components needed:**

| Component | What it does | API |
|---|---|---|
| `FarmProfileForm` | Full editable form — location (autocomplete from E8), land acres, budget ₹, water source dropdown, irrigation method dropdown, borewell count/yield (conditional on water source), risk preference slider, soil test (optional) | E2 plan (on Save); E8 location search |
| `LocationAutocomplete` | Text field + dropdown suggestions from E8. Shows "not agricultural" note for Mumbai City/Suburban (error code `DISTRICT_NOT_AGRICULTURAL`) | E8 |
| `RiskSlider` | Three-point slider: Safe — Balanced — Max profit | profile.risk_appetite |
| `AssumptionBadge` | Orange chip on any field populated from `defaults_used` (e.g. "assumed: flood irrigation") | FarmProfile.defaults_used |
| `SaveBar` | Sticky bottom bar: "Changing any detail will update your recommendations." + Reset + Save buttons | E2 or E3 on save |

**Form fields and their backend mapping:**

| Field | `FarmProfile` field | Validation |
|---|---|---|
| Location | `location_text` | Required; must resolve via E8 |
| Total land | `land_acres` | Required; number > 0 |
| Budget | `budget_rs` | Required; number > 0; shown as ₹ |
| Water source | `water_source` | Required; rainfed \| borewell \| canal \| both |
| Irrigation method | `irrigation_method` | Required; flood \| sprinkler \| drip |
| Borewell count | `borewell_count` | Conditional on water_source |
| Risk preference | `risk_appetite` | Required; safe \| balanced \| max_profit |
| Soil test | `soil_test.n/p/k/ph` | Optional |

**On Save:** call `E2 /api/plan` with the full profile (or `E3 /api/plans/{id}/reoptimize` if a plan_id exists). Navigate to Dashboard on success.

**On Reset:** restore the stored `profile` from Zustand without an API call.

### 5.3 DashboardPage (`/dashboard`)

**Purpose:** the full plan view — summary, crop allocation, water, costs, crop cards, map.

**Layout (desktop):** two columns inside the content area, with a full-width summary row at the top.

```
┌── Summary tiles (full width — 4 tiles) ──────────────────────────────┐
├── Scenario toggle (Normal / Drought / Excess) + context text ─────────┤
├─── Left column (55%) ──────────────┬──── Right column (45%) ──────────┤
│  Crop Allocation (donut chart)     │  Expected Profit (grouped bars)   │
│  Top Crop Recommendations          │  Water Usage Comparison (bars)    │
│  Cost Breakdown (stacked bar)      │  Water Gauge (semicircle)         │
├────────────────────────────────────┴───────────────────────────────────┤
│  District Map (react-leaflet, lazy-loaded, full width)                 │
├────────────────────────────────────────────────────────────────────────┤
│  Excluded Crops list                                                    │
│  Warnings                                                               │
│  Sources chip → /sources                                                │
└────────────────────────────────────────────────────────────────────────┘
```

**Components needed:**

| Component | What it does | Data |
|---|---|---|
| `SummaryTiles` | 4 tiles: expected profit, crop area, water requirement, no. of crops. Each with `SourceBadge`, delta vs traditional | `impact`, recommended `strategies[]` |
| `ScenarioToggle` | Three chips: Normal / Drought / Excess. Switching re-runs all numbers on screen. Color: drought=orange, rain=blue, normal=green | `scenarios`; updates `selectedScenario` in store; calls E3 |
| `LandPlan` | Recharts PieChart (donut). One slice per crop; legend with crop name, acres, share. Default = recommended strategy | `strategies[recommended].allocations` |
| `StrategyCompare` (summary bars) | Two bar charts: Expected Profit across 4 strategies; Water Usage across 4 strategies. Recommended strategy labeled | `strategies` |
| `WaterGauge` | Recharts RadialBarChart semicircle. Rain / groundwater / canal segments. Below: "Traditional plan needs X m³ more" | `water[selectedScenario]` |
| `CostBreakdown` | Stacked bar per crop: seed, fertilizer, manure, labour, machine, irrigation, pesticide, interest. "Reference year 2022-23" note | `crops[].cost_per_acre` |
| `CropCard` | Per-crop card: name (local lang), suitability label (good/average/poor), yield quintal/acre by scenario, today's price + expected harvest price + MSP, profit/acre, duration months. "Why this crop?" expands SHAP factors (i18n key per feature code) | `CropOption` |
| `ExcludedCrops` | One line per excluded crop: "Onion not included: \<translated reason\>" | `excluded_crops[].reason_code + params` |
| `Warnings` | Amber banner per warning. Translated from `code + params` | `warnings[]` |
| `DistrictMap` | react-leaflet (lazy). Farm pin, district fill by `status_color` from E9. Tap → popup with E10 context data | E9, E10 |
| `SourcesChip` | "● 14 live ● 2 cached ● 31 official" — links to /sources | `data_status` |

**Scenario toggle interaction:** on change, call `E3 /api/plans/{id}/reoptimize` with `{ safety_scenario: selectedScenario }`. All `SourcedValue`s update. The `WaterBudget` is per-scenario from the backend so no extra call is needed for the water gauge.

### 5.4 ComparisonPage (`/comparison`)

**Purpose:** side-by-side comparison of the four strategies with scenario and risk controls.

**Layout:**
```
┌── Weather Scenario chips + Risk Preference slider (full width) ──┐
├── Four strategy cards (side by side on desktop, stacked on phone) ┤
│   Each card: strategy name, description, Expected Profit,         │
│   Worst-Year Profit, Water Usage, Fertilizer Usage                │
├── Four bar charts (2×2 grid on desktop) ─────────────────────────┤
│   Expected Profit | Worst-Year Profit | Water Usage | Fertilizer  │
├── Strategy Insights (bullet list — translated from strategy data) ┤
└── Scenario Summary table (selected strategy × 3 scenarios) ───────┘
```

**Components needed:**

| Component | What it does | Data |
|---|---|---|
| `StrategyCard` | One per strategy (Traditional / LP / QP Balanced ★ / QP Drought-Safe). Shows the four key metrics. Recommended card has a star and slightly highlighted border | `strategies[]` |
| `StrategyCompare` (full) | 4 grouped bar charts: Expected Profit, Worst-Year Profit, Water Usage (lakh L), Fertilizer Usage (kg). Each bar uses the fixed strategy color | `strategies[]` |
| `ScenarioSummaryTable` | Selected strategy × 3 scenarios: Expected Profit, Worst-Year Profit, Water, Fertilizer. Scenario column headers colored | `strategies[selectedStrategy].profit_by_scenario_rs`, `water` |
| `StrategyInsights` | Auto-generated bullet list: e.g. "QP Balanced gives a good trade-off between profit and water." These are **derived from data comparisons**, not free text. Compare metrics across strategies programmatically. | `strategies[]`, `impact` |
| `RiskSlider` | Same component as Farm Profile page — changes `risk_appetite`. On release, calls E3 reoptimize | E3 |

**Risk slider interaction:** on release, call `E3 /api/plans/{id}/reoptimize` with `{ risk_appetite }`. Backend writes the new risk back to agent memory (E3 spec). Animate number changes.

### 5.5 SourcesPage (`/sources`)

**Purpose:** show where every number comes from. Transparency page for farmers and judges.

**Components needed:**

| Component | What it does | Data |
|---|---|---|
| `SourcesPage` | Header: "No mock data: every number comes from these sources." List of all datasets + APIs | E11 |
| `HealthDot` | Green / amber / red dot + latency + "serving cached data" note | E12 |
| Source row | Name, publisher, URL link, licence, date, type (live_api / official_dataset) | `sources[]` |

### 5.6 Error and Empty Pages

| State | Component | Trigger |
|---|---|---|
| No eligible crops | `EmptyState` with crop icon + translated reason per `excluded_crops` | `crops: []` in PlanResult |
| No feasible plan | `InfeasibleState` — shows binding constraint + suggestion | `infeasibility` filled, strategies `feasible: false` |
| Server waking up | `WakingUpBanner` — polls E13 every 3 s, shows "waking up, a few seconds…" progress dots | 503 on any endpoint |
| Location not found | Inline in form: "We could not find this place" + map pin fallback | error code `LOCATION_NOT_FOUND` |
| Non-agricultural district | Inline: "Mumbai City has no agricultural statistics" | error code `DISTRICT_NOT_AGRICULTURAL` |
| No internet | `OfflineBanner` | `navigator.onLine` false |
| Speech not understood | Inline mic: "Please try again or type" + retry button | error code `STT_FAILED` |

---

## 6. Backend API Integration Strategy

### 6.1 Type Generation

Types are generated from the backend OpenAPI file. The generation script runs as part of setup (`FE.0c`):

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/openapi.d.ts
```

`src/api/types.ts` re-exports only what the frontend needs. Types are never hand-written.

The SSE payloads (`TraceEvent`, `PlanResult`, `question`, `message`, `done`) are in the OpenAPI file via the `GET /api/schemas/sse-events` endpoint (backend task `C.4`). The generation step picks them up automatically.

### 6.2 Sample Switch (development only)

During development, until the real backend is running:

```ts
// src/api/samples.ts  — ONLY imported when VITE_USE_SAMPLES=true
export const samplePlan: PlanResult = { /* contract example JSON */ }
```

`src/api/queryHooks.ts` checks the flag at the module level and returns the sample data instead of making a fetch call. When `VITE_USE_SAMPLES` is off this module is tree-shaken. The production Vite build has a plugin that throws an error if the flag is set.

### 6.3 Fetch Client (`src/api/client.ts`)

```ts
async function apiFetch<T>(path: string, options?): Promise<T>
```

- Base URL from `import.meta.env.VITE_API_URL`.
- JSON body, JSON response.
- On non-2xx: parse the backend `Error` shape and throw a typed `ApiError`.
- On network failure: throw `NetworkError`.
- 64 KB request size limit enforced client-side (mirrors backend rule).

### 6.4 SSE Client (`src/api/sseClient.ts`)

```ts
function streamChat(body: ChatRequest, handlers: {
  onThread(e: ThreadEvent): void
  onProfile(e: FarmProfile): void
  onQuestion(e: QuestionEvent): void
  onTrace(e: TraceEvent): void
  onPlan(e: PlanResult): void
  onMessage(e: MessageEvent): void
  onError(e: ApiError): void
  onDone(e: DoneEvent): void
}): AbortController
```

Reads `Content-Type: text/event-stream` via `fetch` + `ReadableStream`. Returns an `AbortController` so the caller can cancel (on unmount or user cancel).

### 6.5 Query Hooks (TanStack Query)

| Hook | Endpoint | Stale time |
|---|---|---|
| `usePlan(planId)` | E2 POST | 24 h (matches backend plan store TTL) |
| `useThread(threadId)` | E4 GET | 24 h |
| `useDistricts()` | E9 GET | 1 h |
| `useDistrictContext(district)` | E10 GET | 1 h |
| `useSources()` | E11 GET | 10 min |
| `useSourcesHealth()` | E12 GET | 1 min (matches backend 60 s cache) |
| `useHealth()` | E13 GET | 30 s (used for cold-start polling) |

The chat stream (E1) and reoptimize (E3) are imperative calls, not query hooks, because they mutate state and stream results.

### 6.6 Audio Handling

**Recording (`useRecorder`):**
1. On mount, test `MediaRecorder.isTypeSupported` in order: `audio/webm;codecs=opus`, `audio/mp4`, `audio/aac`.
2. Use the first supported format. Store `mimeType` in a ref.
3. Max recording: 60 seconds (auto-stop with a countdown).
4. On stop, send the blob to `E5 POST /api/transcribe` as `multipart/form-data` with the `language_hint` from the store.

**Playback (`useSpeech`):**
1. Call `E6 POST /api/speak` with the answer text and language.
2. On success, play `audio/wav` in an `<audio>` element.
3. On `503 UPSTREAM_UNAVAILABLE`: fall back to `window.speechSynthesis.speak()` with the browser's voices for the target language.
4. Text is always shown regardless of playback state.

---

## 7. Loading, Error, and Empty States

### 7.1 Loading States

Every data-bearing component has a skeleton placeholder that matches its final shape:

| Component | Skeleton |
|---|---|
| `SummaryTiles` | 4 rounded rectangles, same height as tiles |
| `LandPlan` | Circle outline + 4 legend lines |
| `CropCard` | Card-shaped placeholder with 5 line stubs |
| `TraceTimeline` | 6 rows with spinner icon + two line stubs each |
| `DistrictMap` | Grey rectangle with a faint map grid |
| `StrategyCard` | Card outline with 4 metric line stubs |

While the SSE stream is running, the trace timeline shows live rows and the rest of the right panel shows skeletons until the `plan` event arrives.

### 7.2 Error States

All errors come from the backend `Error` shape: `{ code, user_message: { mr, hi, en } }`.

```tsx
<ErrorState
  code={error.code}
  message={error.user_message[language]}
  retryable={error.retryable}
  onRetry={retry}
/>
```

The `ErrorState` component never invents its own message — it always uses `user_message` from the API. The one exception is a `NetworkError` (no response at all), which shows a generic "No internet connection" message from the i18n file.

### 7.3 Empty States

| Scenario | What to show |
|---|---|
| `crops: []` | Icon + "We could not find crops with real prices for your area" + per-crop reasons from `excluded_crops` (translated) |
| `strategies: []` | Same crop-empty state |
| `infeasibility` filled | "We could not build a plan with your current constraints." + binding constraint detail + suggestion (translated from `suggestion_code + params`) |
| No plan yet (new session) | Home page greeting state — mic large, chat prompt visible |

### 7.4 Server Waking Up (F18)

When any endpoint returns `503` with code `UPSTREAM_UNAVAILABLE`:
1. Show `WakingUpBanner`: "AgriPulse is starting up, a few seconds…" with animated dots.
2. Poll `E13 GET /api/health` every 3 seconds.
3. When `{ status: "ok", models_loaded: true }` is returned, auto-retry the original request.
4. Never show a dead / blank screen.

### 7.5 Offline State

Listen to `window.addEventListener('offline')`. Show a top banner: "No internet connection — showing last saved data." Hide it when `'online'` fires. Cached TanStack Query data continues to render.

---

## 8. Responsive Design

### 8.1 Mobile (< 640 px)

- Single-column layout.
- `Sidebar` replaced by `BottomNav` (4 icon tabs: Home, Profile, Dashboard, Comparison).
- `TopBar` shows logo only; language picker moves into a Settings sheet.
- `MicButton` is the largest element on Home — minimum 80 × 80 px, centered.
- Summary tiles stack 2×2.
- Charts: horizontal scroll on overflow, no truncation.
- `CropCard` collapses to a summary row; tapping expands to full detail.
- `DistrictMap` height = 200 px (scrollable context).
- Bottom bar on FarmProfilePage: Reset + Save sticky at viewport bottom.
- Touch targets ≥ 48 × 48 px everywhere.
- Body text ≥ 16 px; contrast ≥ 4.5:1.

### 8.2 Tablet (640–1023 px)

- Single column, no sidebar, top navigation tabs.
- Charts side by side (2 per row).
- Farm profile form full width, info panel stacked below.

### 8.3 Desktop (≥ 1024 px)

- Fixed 240 px sidebar + content area.
- Home: 55/45 split (chat / trace + preview).
- Dashboard: two-column content inside the content area.
- Comparison: four strategy cards in a row; 2×2 chart grid.

### 8.4 Accessibility

- All icon buttons have `aria-label` in the active language.
- `aria-live="polite"` on the TraceTimeline and MessageList (new items announced).
- Focus management: after voice recording ends, focus returns to the chat input.
- No information conveyed by color alone (source badge also shows a text label in the tooltip).
- Keyboard navigation works on desktop (Tab order matches reading order).
- Lighthouse mobile accessibility score target ≥ 90.

---

## 9. Testing and Validation

### 9.1 Unit Tests (Vitest + Testing Library)

| Test | What it checks |
|---|---|
| `SourceBadge.test.tsx` | Renders one of the 7 statuses; tooltip shows source + as_of |
| `MoneyText.test.tsx` | Indian grouping: 70000 → ₹70,000; 100000 → ₹1,00,000 |
| `QuintalText.test.tsx` | 12.5 → "12.5 quintals / 4.1 bags" |
| `WaterText.test.tsx` | 18000 litres → "18,000 L / 1.8 tanker loads" |
| `sseClient.test.ts` | Parses all 8 event types; handles partial chunks; handles disconnect |
| `store.test.ts` | setScenario updates selectedScenario; setPlan stores plan_id |
| **`badgeTest.tsx` (critical)** | Renders a full `PlanResult` fixture and asserts every farmer-visible number has a `SourceBadge` with an allowed status. Fails the build if any number lacks one. |
| `useRecorder.test.ts` | Picks `audio/mp4` when webm is not supported |
| `i18n.test.ts` | All message codes have translations in mr, hi, en |
| `WaterGauge.test.tsx` | Shows assumption badge when `category_cap.status === "assumption"` |

### 9.2 End-to-End Tests (Playwright — `FE.T2`)

Always runs with `VITE_USE_SAMPLES=false` against the **deployed backend**.

```
Demo story 1 — Jalgaon (groundwater-stressed):
  speak "I have 5 acres near Jalgaon, ₹80,000, borewell"
  → profile card appears with correct fields
  → trace shows 6+ steps
  → plan loads with drought-safe recommendation
  → switch to Drought scenario → numbers update
  → ask "What if I only had ₹50,000?" → diff chips appear

Demo story 2 — Pune (richest data):
  type profile → plan → open Dashboard → verify all 4 strategies shown

Demo story 3 — Ahilyanagar (follow-up):
  speak profile → plan → tap "What if drip irrigation?" → updated plan
```

### 9.3 Phone Check (`FE.T3`)

Manual checklist on a real low-end Android (360 px):
- [ ] Mic button: tap to record, release to send
- [ ] iOS Safari: audio recording uses mp4 format (one device check)
- [ ] All touch targets ≥ 48 × 48 px
- [ ] Body text readable in simulated sunlight (high-contrast mode)
- [ ] 4G: first plan loads in under 5 seconds after typing
- [ ] Charts scroll horizontally without breaking layout
- [ ] Bottom navigation visible without scrolling

### 9.4 Accessibility + Performance (`FE.T4`)

- Run `axe` in Playwright on each page; zero critical violations allowed.
- Lighthouse mobile: Performance ≥ 85, Accessibility ≥ 90.
- First Contentful Paint < 2 s on 4G (Lighthouse simulated throttling).
- Route-level code split: verify that the map bundle is not loaded on `/profile`.

### 9.5 Production Build Guard

```bash
# CI step — fails if samples leak into the bundle
npm run build
grep -r "contract_example_marker" dist/ && exit 1 || exit 0
```

The sample JSON files each contain a known string `"__CONTRACT_EXAMPLE__"`. The grep fails the CI step if this string appears in the production bundle.

---

## 10. Implementation Order and Dependencies

### 10.1 Critical Dependency (Gate for All Frontend Work)

Before any build work can start, the backend must deliver:

| What | Backend task | Blocks |
|---|---|---|
| `backend/app/schemas.py` with all types | `C.1` | TypeScript type generation |
| `docs/api_examples/contract/` example JSON | `C.2` | Sample mode development |
| SSE payloads in OpenAPI (`/api/schemas/sse-events`) | `C.4` | Correct SSE type generation |

If these slip, **raise it immediately**. Do not hand-write types.

### 10.2 Sequential Build Order

```
Phase 0 — Setup (no backend needed)
  FE.0a  Vite + React + TS + Tailwind skeleton, ESLint, Vitest
  FE.0b  Design tokens, self-hosted fonts, base components (SourceBadge, MoneyText, etc.)
  FE.0c  Generate types from OpenAPI; fetch client; SSE client; sample switch + prod guard
  FE.0d  i18n: mr/hi/en JSON files, Indian number helper, SHAP feature code keys
  FE.0e  CI: lint + test + build + sample-leak grep on every PR

Phase 1 — Shell and navigation (no backend needed)
  AppShell, Sidebar, TopBar, BottomNav, routing, Zustand store

Phase 2 — Home page — chat, profile, trace (samples)
  FE.1   MicButton, ChatBox, MessageList (F1 — voice and chat home)
  FE.2   FarmProfileCard, EditableRow, inline assumption badges (F3)
  FE.3   TraceTimeline, TraceRow, SSE event dispatch (F4)

Phase 3 — Dashboard (samples)
  FE.4   SummaryTiles, LandPlan donut, CropCard with "why this crop" (F5)
  FE.5   ScenarioToggle, StrategyCompare table + bars (F6)
  FE.6   WaterGauge semicircle (F7)

Phase 4 — Source badges (samples)
  FE.7   SourceBadge on every number + badge unit test (F9)
         ← This is the quality gate. No phase-5 work starts until the badge test passes.

Phase 5 — Interactive controls (needs real E3)
  FE.8   RiskSlider → E3 reoptimize, animated change (F8)
  FE.9   Spoken reply → E6 speak + browser fallback (F10)

Phase 6 — Follow-up and diff (needs real E1 with thread_id)
  FE.10  FollowUpChips, diff chips from version delta (F13)

Phase 7 — Map and sources (needs real E9–E12)
  FE.11  DistrictMap, lazy-load, E10 popup (F11)
  FE.12  SourcesPage, HealthDot (F12)

Phase 8 — Translations and polish
  FE.13  All message codes in mr/hi/en; language picker re-renders all; native review (F2)

Phase 9 — Resilience (needs real E4, E7, E13)
  FE.14  Reload from thread (F14); error/empty/infeasible states (F15); prefetch (F16)
         LocationPicker, non-agricultural district message (F17)
         WakingUpBanner, E13 polling (F18)

Phase 10 — Comparison page
         ComparisonPage, StrategyCard, StrategyCompare (full), ScenarioSummaryTable,
         StrategyInsights (derived from data, not free text), RiskSlider

Phase 11 — Quality, deploy
  FE.T1  Unit tests green in CI
  FE.T2  Playwright e2e against deployed backend (VITE_USE_SAMPLES=false)
  FE.T3  Phone checklist
  FE.T4  Axe + Lighthouse mobile ≥ 85
  DD.2   Deploy to Vercel (VITE_API_URL → backend)
  DD.3   Record 2–3 min demo video
  DD.4   Screenshots for README (phone + desktop, 3 languages)
```

### 10.3 Dependency Graph (simplified)

```
C.1 + C.2 + C.4
    │
    ▼
FE.0c (types + sample switch)
    │
    ├──► Phase 2 (Home — chat/profile/trace)
    │         │
    │         ▼
    │    Phase 3 (Dashboard blocks)
    │         │
    │         ▼
    │    Phase 4 (Badge gate) ──── must pass before Phase 5
    │                                    │
    │                      ┌────────────┤
    │                      ▼            ▼
    │              Phase 5 (E3)   Phase 6 (E1)
    │                      │            │
    │                      └─────┬──────┘
    │                            ▼
    │                    Phase 7 (E9–E12)
    │                            │
    │                    Phase 8 (translations)
    │                            │
    │                    Phase 9 (E4, E7, E13)
    │                            │
    └──────────────────► Phase 10 (Comparison)
                                 │
                         Phase 11 (QA + deploy)
```

### 10.4 Completion Criteria Summary

| Phase | Exit condition |
|---|---|
| Phase 0 | `npm run dev`, `npm test`, `npm run build` all pass; CI green |
| Phase 1 | Routes render; Sidebar + BottomNav visible; Zustand store initialises |
| Phase 2 | Home works end-to-end on samples; mic records; trace streams; profile card editable |
| Phase 3 | Dashboard renders all blocks from sample `PlanResult`; scenario toggle switches numbers |
| Phase 4 | Badge unit test passes; every farmer-visible number has a `SourceBadge` |
| Phase 5 | Risk slider calls E3, animates change in < 2 s; spoken reply plays and falls back |
| Phase 6 | Follow-up re-runs plan; diff chips show delta |
| Phase 7 | Map shows district colors; popup shows E10 data; sources page shows all datasets |
| Phase 8 | Language switch re-renders all labels; native speaker review signed off |
| Phase 9 | Refresh restores plan; every error code has a farmer-language message; cold-start shows waking-up |
| Phase 10 | All 4 strategy cards; charts; scenario summary table; risk slider |
| Phase 11 | Playwright passes against deployed backend; Lighthouse mobile ≥ 85; demo video recorded |

---

*This plan is a companion to `frontend/SPECS.md`. Where the two disagree, `frontend/SPECS.md` wins — update this plan to match.*
*Do not start coding until this plan is reviewed.*
