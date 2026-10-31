/**
 * API types for AgriPulse frontend.
 *
 * In production these are GENERATED from backend/app/schemas.py via the
 * OpenAPI file.  During Phase 0 (before the backend OpenAPI is available)
 * we declare them here by hand so the rest of the frontend can be built.
 *
 * TODO (FE.0c): once the backend ships `GET /openapi.json`, replace this
 * file with:
 *   npx openapi-typescript http://localhost:8000/openapi.json -o src/api/openapi.d.ts
 * and re-export only what the frontend uses.
 *
 * IMPORTANT: Do NOT invent fields.  Every field here maps 1-to-1 to a
 * field in backend/SPECS.md section 5.1.
 */

// ---------------------------------------------------------------------------
// Shared building block
// ---------------------------------------------------------------------------

export type SourceStatus =
  | 'live'
  | 'cached'
  | 'official_dataset'
  | 'model'
  | 'computed'
  | 'farmer_input'
  | 'assumption'

export interface SourcedValue {
  value: number
  unit: string
  source: string
  source_url: string
  as_of: string           // ISO date string
  status: SourceStatus
}

// ---------------------------------------------------------------------------
// Farm profile
// ---------------------------------------------------------------------------

export type WaterSource = 'rainfed' | 'borewell' | 'canal' | 'both' | null
export type IrrigationMethod = 'flood' | 'sprinkler' | 'drip' | null
export type RiskAppetite = 'safe' | 'balanced' | 'max_profit'
export type Language = 'mr' | 'hi' | 'en'

export interface DefaultUsed {
  field: string
  value: string | number
  basis: string
}

export interface SoilTest {
  n: number
  p: number
  k: number
  ph: number
}

export interface FarmProfile {
  location_text: string
  land_acres: number
  budget_rs: number
  water_source: WaterSource
  borewell_count: number | null
  borewell_yield_lph: number | null
  pump_hours_per_day: number | null
  canal_access: boolean
  irrigation_method: IrrigationMethod
  risk_appetite: RiskAppetite
  soil_test: SoilTest | null
  language: Language
  missing: string[]            // required fields still unknown
  defaults_used: DefaultUsed[] // every assumed value
}

// ---------------------------------------------------------------------------
// Location
// ---------------------------------------------------------------------------

export interface Location {
  input: string
  resolved_name: string
  district: string
  state: string
  latitude: number
  longitude: number
}

// ---------------------------------------------------------------------------
// Crop option
// ---------------------------------------------------------------------------

export interface SuitabilityFactor {
  feature: string              // fixed code — see ml/SPECS.md section 3
  value: number
  unit: string
  effect_quintal_per_acre: number
  direction: 'up' | 'down'
}

export interface Suitability {
  score: number
  label: 'good' | 'average' | 'poor'
  top_factors: SuitabilityFactor[]
  fallback_used: boolean
}

export interface CostPerAcre {
  total_rs: number
  seed: number
  fertilizer: number
  manure: number
  labour: number
  machine: number
  irrigation: number
  pesticide: number
  interest: number
  reference_year: string
  source: string
  status: SourceStatus
}

export interface FertilizerPlan {
  n_kg_per_acre: number
  p2o5_kg_per_acre: number
  k2o_kg_per_acre: number
  basis: string
}

export interface CropNames {
  en: string
  mr: string
  hi: string
}

export interface CropOption {
  crop_id: string
  names: CropNames
  season: string
  suitability: Suitability
  yield_quintal_per_acre: Record<'drought' | 'normal' | 'excess', number>
  price: SourcedValue
  expected_harvest_price: SourcedValue
  duration_days: number
  harvest_month: string        // "2027-02"
  msp: SourcedValue
  cost_per_acre: CostPerAcre
  fertilizer: FertilizerPlan
  water_need_m3_per_acre: Record<'drought' | 'normal' | 'excess', number>
  profit_rs_per_acre: Record<'drought' | 'normal' | 'excess', number>
}

// ---------------------------------------------------------------------------
// Water budget
// ---------------------------------------------------------------------------

export type ScenarioId = 'drought' | 'normal' | 'excess'

export interface WaterAvailable {
  rain: SourcedValue
  groundwater: SourcedValue
  canal: SourcedValue
  total: SourcedValue
}

export interface WaterBudgetBasis {
  groundwater_category: SourcedValue
  category_cap: SourcedValue
  effective_rain_factor: SourcedValue
  reservoir_storage_pct: SourcedValue
  rain_so_far_mm: SourcedValue
}

export interface WaterNeed {
  traditional_plan: SourcedValue
  recommended_plan: SourcedValue
}

export interface WaterBudget {
  scenario: ScenarioId
  analogue_year: number
  available_m3: WaterAvailable
  basis: WaterBudgetBasis
  irrigation_method: IrrigationMethod
  efficiency_pct: SourcedValue
  need_m3: WaterNeed
}

// ---------------------------------------------------------------------------
// Strategy / optimizer result
// ---------------------------------------------------------------------------

export type StrategyId =
  | 'traditional'
  | 'lp_max_profit'
  | 'qp_balanced'
  | 'qp_drought_safe'

export interface Allocation {
  crop_id: string
  acres: number
  share_pct: number
  cost_rs: number
  water_m3: number
  profit_rs: Record<ScenarioId, number>
}

export interface StrategyTotals {
  land_used_acres: number
  budget_used_rs: number
  fertilizer_kg: { n: number; p2o5: number; k2o: number }
  water_m3: number
}

export interface StrategyResult {
  id: StrategyId
  label: string
  kind: string
  risk_lambda: number
  safety_scenario: ScenarioId
  allocations: Allocation[]
  totals: StrategyTotals
  profit_by_scenario_rs: Record<ScenarioId, number>
  expected_profit_rs: number
  worst_case_profit_rs: number
  feasible: boolean
  binding_constraints: string[]
  relaxations_applied: Array<{ constraint: string; change: string }>
  solver: { name: string; status: string; ms: number }
}

// ---------------------------------------------------------------------------
// Plan result
// ---------------------------------------------------------------------------

export interface Scenario {
  id: ScenarioId
  label: string
  season_rain_mm: SourcedValue
  probability: number
  analogue_year?: number
}

export interface ExcludedCrop {
  crop_id: string
  reason_code: string
  params: Record<string, string>
}

export interface Warning {
  code: string
  params: Record<string, string | number>
}

export interface ImpactResult {
  water_saved_pct: SourcedValue
  fertilizer_saved_pct: SourcedValue
  fertilizer_vs_district_use_pct: SourcedValue | null
  drought_profit_gain_rs: SourcedValue
  versus: string
  traditional_exceeds: string[]
}

export interface Explanation {
  language: Language
  text: string
  key_points: Array<{ icon: string; text: string }>
  grounded: boolean
  provider: string
}

export interface DataStatus {
  live: number
  cached: number
  official_dataset: number
}

export interface ConstraintDetail {
  constraint: string
  required_rs?: number
  available_rs?: number
  shortfall_rs?: number
  required_m3?: number
  available_m3?: number
  shortfall_m3?: number
}

export interface Infeasibility {
  binding: string[]
  violated: string[]
  detail: ConstraintDetail[]
  relaxations_tried: Array<{ step: string; result: string }>
  suggestion_code: string
  suggestion_params: Record<string, string | number>
}

export interface PlanResult {
  plan_id: string
  thread_id: string
  version: number
  previous_version?: number
  created_at: string
  profile: FarmProfile
  location: Location
  season: { name: string; sowing_window: { start: string; end: string }; status: SourceStatus }
  scenarios: Scenario[]
  crops: CropOption[]
  excluded_crops: ExcludedCrop[]
  water: WaterBudget        // backend returns one per scenario; we store the current scenario's
  strategies: StrategyResult[]
  recommended_strategy: StrategyId | null
  impact: ImpactResult | null
  infeasibility: Infeasibility | null
  explanation: Explanation
  warnings: Warning[]
  data_status: DataStatus
}

// ---------------------------------------------------------------------------
// SSE / streaming events
// ---------------------------------------------------------------------------

export interface ThreadEvent { thread_id: string }
export interface QuestionEvent { text: string; field: string; language: Language }
export interface MessageEvent { text: string; language: Language; provider: string }
export interface DoneEvent { ms: number }

export interface TraceEvent {
  id: string
  node: string
  step: string
  status: 'running' | 'ok' | 'cached' | 'failed' | 'skipped'
  started_at: string
  duration_ms: number
  summary: string
  source: { name: string; url: string; status: SourceStatus } | null
  fallback_used: string | null
}

// ---------------------------------------------------------------------------
// API error
// ---------------------------------------------------------------------------

export interface ApiError {
  code: string
  message: string
  user_message: Record<Language, string>
  retryable: boolean
  details: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Thread (E4 response)
// ---------------------------------------------------------------------------

export interface ThreadMessage {
  role: 'farmer' | 'agent'
  text: string
  language: Language
  at: string
}

export interface ThreadResponse {
  thread_id: string
  profile: FarmProfile | null
  plan: PlanResult | null
  messages: ThreadMessage[]
}

// ---------------------------------------------------------------------------
// District (E9)
// ---------------------------------------------------------------------------

export interface District {
  district: string
  names: CropNames
  latitude: number
  longitude: number
  groundwater_category: string
  status_color: 'green' | 'amber' | 'red' | 'grey'
  is_agricultural_district: boolean
}

// ---------------------------------------------------------------------------
// Source / health (E11, E12)
// ---------------------------------------------------------------------------

export interface DataSource {
  id: string
  name: string
  publisher: string
  url: string
  license: string
  verified_on: string
  type: 'live_api' | 'official_dataset'
  used_for: string
}

export interface SourceHealth {
  id: string
  name: string
  status: 'green' | 'amber' | 'red'
  latency_ms: number
  last_ok: string
  note: string | null
}

// ---------------------------------------------------------------------------
// Chat request (E1 body)
// ---------------------------------------------------------------------------

export interface ChatRequest {
  thread_id?: string
  message: string
  language: Language
  profile_patch?: Partial<FarmProfile>
}
