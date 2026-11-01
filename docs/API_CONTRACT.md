# AgriPulse API Contract & Specification (Spec C.2)

> **Status**: Verified against live ML pipeline & backend endpoints.  
> **Base URL (Dev)**: `http://localhost:8000`  
> **OpenAPI Schema**: [`docs/openapi.json`](openapi.json)  
> **Live Fixture Examples**: [`docs/api_examples/live/`](api_examples/live/)

---

## 1. Overview & Ground Rules

1. **No Mock or Synthetic Data**: Every returned value originates from official datasets (DES, CACP, CGWB, CWC, Soil Health Card, Agmarknet) or verified models (Model A HistGradientBoosting, FAO-56 crop water coefficients, CVXPY/HiGHS optimizer).
2. **Provenance on Every Farmer-Visible Value**: Numerical figures carry a `SourcedValue` envelope with a `status` tag:
   - `live`: Fetched live from an official API within the last 24 hours (e.g. Open-Meteo, Agmarknet).
   - `cached`: Retrieved from local TTL SQLite cache when external API is rate-limited or offline.
   - `official_dataset`: Sourced from official state/national statistical publications.
   - `model`: Output of a trained, validated machine learning model (e.g. AgriPulse Model A).
   - `computed`: Deterministic mathematical calculation from other verified parameters.
   - `farmer_input`: Provided directly by the farmer.
   - `assumption`: Standardized agronomic baseline constant (e.g. drip efficiency = 0.90).
3. **Consistent Units**:
   - Land: Acres
   - Crop Yield: Quintals per acre (and tonnes per hectare internally)
   - Water: Cubic meters (m³) and tanker loads (1 tanker load = 10 m³)
   - Currency: Indian Rupees (₹)
   - Fertilizer: Bag counts (Urea 45 kg, DAP 50 kg, MOP 50 kg) and elemental kg/acre

---

## 2. API Endpoints Summary

| Method | Endpoint | Description | Response Model |
|---|---|---|---|
| `POST` | `/api/agent/chat` | Conversational multi-turn planning via Server-Sent Events | SSE Stream |
| `POST` | `/api/plan` | Direct non-streaming plan generation | `PlanResult` |
| `POST` | `/api/plans/{plan_id}/reoptimize` | Fast risk/parameter reoptimization | `PlanResult` |
| `GET` | `/api/threads/{thread_id}` | Retrieve saved conversation and plan state | `ThreadResponse` |
| `POST` | `/api/transcribe` | Sarvam ASR voice speech-to-text | `TranscriptionResponse` |
| `POST` | `/api/speak` | Sarvam TTS text-to-speech synthesis | `SpeechResponse` |
| `POST` | `/api/prefetch` | Fire-and-forget data prefetch on location resolution | `PrefetchResponse` |
| `GET` | `/api/locations/search?q={query}` | Geocoding location autocomplete | `list[LocationSearchResult]` |
| `GET` | `/api/districts` | 36 Maharashtra districts with agricultural status flag | `DistrictsResponse` |
| `GET` | `/api/districts/{district}/context` | District agro-climatic context popup | `DistrictContext` |
| `GET` | `/api/sources` | Catalog of official datasets and APIs | `SourcesResponse` |
| `GET` | `/api/sources/health` | Upstream service availability & latency monitoring | `SourcesHealthResponse` |
| `GET` | `/api/health` | Service health, model warm-up status, and data file count | `HealthResponse` |
| `GET` | `/api/schemas/sse-events` | Schema discovery for TypeScript SSE client generator | `SSEEventExamples` |

---

## 3. Core Payload Schemas

### 3.1 `SourcedValue`
```typescript
interface SourcedValue {
  value: number;
  unit: string;
  source: string;
  source_url?: string;
  as_of?: string;
  status: "live" | "cached" | "official_dataset" | "model" | "computed" | "farmer_input" | "assumption";
  history_years?: number;
  note?: string;
}
```

### 3.2 `FarmProfile`
```typescript
interface FarmProfile {
  location_text: string;
  land_acres: number;
  budget_rs: number;
  water_source: "rainfed" | "borewell" | "canal" | "both" | null;
  borewell_count?: number;
  borewell_yield_lph?: number;
  pump_hours_per_day?: number;
  canal_access?: boolean;
  irrigation_method?: "flood" | "sprinkler" | "drip" | null;
  risk_appetite?: "safe" | "balanced" | "max_profit";
  language?: "mr" | "hi" | "en";
  missing?: string[];
  defaults_used?: Array<{ field: string; value: any; basis: string }>;
}
```

### 3.3 `CropOption`
```typescript
interface CropOption {
  crop_id: string;
  names: { en: string; mr: string; hi: string };
  season: string;
  suitability: {
    score: number;
    label: "good" | "average" | "poor";
    top_factors: Array<{
      feature: string;
      value: number;
      unit: string;
      effect_quintal_per_acre: number;
      direction: "up" | "down";
    }>;
    fallback_used: boolean;
  };
  yield_quintal_per_acre: {
    drought: number;
    normal: number;
    excess: number;
  };
  price: SourcedValue;
  expected_harvest_price: SourcedValue;
  cost_per_acre: {
    total_rs: number;
    seed: number;
    fertilizer: number;
    manure: number;
    labour: number;
    machine: number;
    irrigation: number;
    pesticide: number;
    interest: number;
  };
  fertilizer: {
    n_kg_per_acre: number;
    p2o5_kg_per_acre: number;
    k2o_kg_per_acre: number;
    urea_bags: number;
    dap_bags: number;
    mop_bags: number;
    cost_rs: SourcedValue;
  };
  water_need_m3_per_acre: {
    drought: number;
    normal: number;
    excess: number;
  };
  profit_rs_per_acre: {
    drought: number;
    normal: number;
    excess: number;
  };
}
```

### 3.4 `StrategyResult`
```typescript
interface StrategyResult {
  id: "traditional" | "lp_max_profit" | "qp_balanced" | "qp_drought_safe";
  label: string;
  kind: "traditional" | "lp" | "qp";
  risk_lambda: number;
  allocations: Array<{
    crop_id: string;
    acres: number;
    share_pct: number;
    cost_rs: number;
    water_m3: number;
    profit_rs: { drought: number; normal: number; excess: number };
  }>;
  totals: {
    land_used_acres: number;
    budget_used_rs: number;
    water_m3: { drought: number; normal: number; excess: number };
    cost_rs: number;
  };
  profit_by_scenario_rs: {
    drought: number;
    normal: number;
    excess: number;
  };
  expected_profit_rs: number;
  worst_case_profit_rs: number;
  feasible: boolean;
  binding_constraints: string[];
}
```

---

## 4. Live Example Files

Real payloads captured from the running backend and ML engine are stored in [`docs/api_examples/live/`](api_examples/live/):
- **`plan_pune.json`**: 5.0 acres, Borewell + Drip, Balanced risk appetite.
- **`plan_jalgaon.json`**: 8.0 acres, Canal + Sprinkler, Safe risk appetite.
- **`plan_ahilyanagar.json`**: 4.0 acres, Borewell + Flood, Balanced risk appetite.
- **`districts.json`**: 36 Maharashtra districts with coordinates, soil status, and agricultural flags.
- **`sources.json`**: Catalog of 10+ official data providers and update frequencies.
- **`sources_health.json`**: Real-time latency and connection status of upstream services.
- **`district_context_pune.json`**: Soil, rainfall, and groundwater metrics for Pune district.
