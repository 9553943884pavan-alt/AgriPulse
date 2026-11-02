/**
 * API types for AgriPulse frontend.
 *
 * These interfaces mirror backend/app/schemas.py and the endpoint response
 * shapes. Keep them in sync with the backend OpenAPI contract.
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
  value: number | string
  unit: string
  source: string
  source_url?: string
  as_of: string           // ISO date string
  status: SourceStatus
  history_years?: number | null
  note?: string | null
}

export type NumericSourcedValue = Omit<SourcedValue, 'value'> & { value: number }

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
  superseded?: { seed_des: number | null; fertilizer_des: number | null }
  reference_year: string
  source: string
  status: SourceStatus
}

export interface FertilizerPlan {
  n_kg_per_acre: number
  p2o5_kg_per_acre: number
  k2o_kg_per_acre: number
  urea_bags: number
  dap_bags: number
  mop_bags: number
  cost_rs: NumericSourcedValue
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
  price: NumericSourcedValue
  expected_harvest_price: NumericSourcedValue
  seasonal_ratio: NumericSourcedValue
  duration_days: number
  harvest_month: string        // "2027-02"
  opens_on?: string | null
  msp: NumericSourcedValue | null
  cost_per_acre: CostPerAcre
  fertilizer: FertilizerPlan
  water_need_m3_per_acre: Record<ScenarioId, NumericSourcedValue>
  profit_rs_per_acre: Record<'drought' | 'normal' | 'excess', number>
  revenue_rs_per_acre?: Record<'drought' | 'normal' | 'excess', number> | null
  yield_uncertainty?: UncertaintyBand | null
  price_uncertainty?: UncertaintyBand | null
  risk_note?: string | null
}

/** A reported interval. Its absence means the source cannot support one. */
export interface UncertaintyBand {
  lower: number
  expected: number
  upper: number
  unit: string
  basis: string
  status: SourceStatus
}

// ---------------------------------------------------------------------------
// Water budget
// ---------------------------------------------------------------------------

export type ScenarioId = 'drought' | 'normal' | 'excess'

export interface WaterAvailable {
  rain: NumericSourcedValue
  groundwater: NumericSourcedValue
  canal: NumericSourcedValue
  total: NumericSourcedValue
}

export interface WaterBudgetBasis {
  groundwater_category: SourcedValue
  category_cap: NumericSourcedValue
  effective_rain_factor: NumericSourcedValue
  reservoir_storage_pct: NumericSourcedValue
  rain_so_far_mm: NumericSourcedValue
}

export interface WaterNeed {
  traditional_plan: NumericSourcedValue
  recommended_plan: NumericSourcedValue
}

export interface WaterBudget {
  scenario: ScenarioId
  analogue_year: number
  available_m3: WaterAvailable
  basis: WaterBudgetBasis
  irrigation_method: IrrigationMethod
  efficiency_pct: NumericSourcedValue
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
  revenue_rs?: Record<ScenarioId, number> | null
}

export interface StrategyTotals {
  land_used_acres: number
  budget_used_rs: number
  fertilizer_kg: { n: number; p2o5: number; k2o: number }
  water_m3: number
}

/** Portfolio finance calculated from the same allocation inputs as the solver. */
export interface FinanceSummary {
  investment_rs: NumericSourcedValue
  expected_yield_quintal: NumericSourcedValue
  expected_revenue_rs: NumericSourcedValue
  expected_profit_rs: NumericSourcedValue
  roi_pct: NumericSourcedValue | null
  break_even_price_rs_per_quintal: NumericSourcedValue | null
}

export interface StrategyResult {
  id: StrategyId
  label: string
  kind: 'traditional' | 'lp' | 'qp'
  risk_lambda: number
  safety_scenario: ScenarioId
  allocations: Allocation[]
  totals: StrategyTotals
  finance?: FinanceSummary | null
  profit_by_scenario_rs: Record<ScenarioId, number>
  expected_profit_rs: number
  worst_case_profit_rs: number
  feasible: boolean
  binding_constraints: string[]
  relaxations_applied: Array<{ step: string; params: Record<string, unknown> }>
  solver: { name: string; status: string; ms: number } | null
  infeasibility: Infeasibility | null
  traditional_exceeds: string[]
}

// ---------------------------------------------------------------------------
// Plan result
// ---------------------------------------------------------------------------

export interface Scenario {
  id: ScenarioId
  label: string
  season_rain_mm: NumericSourcedValue
  probability: number
  analogue_year?: number
  rainfall_mm?: number
  et0_mm?: number
  rainy_days?: number
  max_dry_spell_days?: number
  mean_temp_c?: number
  max_temp_c?: number
  heat_stress_days?: number
  mean_humidity_pct?: number
  all_year_samples?: SourcedValue[]
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
  water_saved_pct: NumericSourcedValue
  fertilizer_saved_pct: NumericSourcedValue
  fertilizer_vs_district_use_pct: NumericSourcedValue | null
  drought_profit_gain_rs: NumericSourcedValue
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
  suggestion_code: string | null
  suggestion_params: Record<string, unknown>
}

export interface PlanResult {
  plan_id: string
  thread_id: string
  version: number
  previous_version?: number | null
  created_at: string
  profile: FarmProfile
  location: Location
  season: { name: string; sowing_window: { start: string; end: string }; status: SourceStatus }
  scenarios: Scenario[]
  crops: CropOption[]
  excluded_crops: ExcludedCrop[]
  water: WaterBudget[]      // one budget per scenario
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

export type TraceStatus = 'pending' | 'running' | 'ok' | 'cached' | 'failed' | 'skipped'

export interface TraceEvent {
  id: string
  node: string
  step: string
  status: TraceStatus
  started_at: string
  duration_ms: number
  summary: string
  source: { name: string; url: string; status: string } | null
  fallback_used: string | null
  // Optional fields added by newer backends; older payloads omit them.
  run_id?: string
  sequence?: number
  tool_name?: string
  display_name?: string
  completed_at?: string
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
  status_color: 'green' | 'amber' | 'orange' | 'red' | 'grey'
  is_agricultural_district: boolean
}

export interface LocationSearchResult {
  results: Location[]
}

export interface DistrictContext {
  district: string
  groundwater: {
    category: SourcedValue
    extraction_pct: NumericSourcedValue
    depth_post_monsoon_m: NumericSourcedValue
  }
  reservoirs: Array<{
    name: string
    live_storage_pct: NumericSourcedValue
  }>
  recent_rain: {
    last_90d_mm: NumericSourcedValue | null
    departure_90d_pct: NumericSourcedValue | null
    category: string
  }
  irrigation: {
    borewell_share_pct: NumericSourcedValue | null
    canal_share_pct: NumericSourcedValue | null
    drip_adoption_pct: NumericSourcedValue | null
  }
}

// ---------------------------------------------------------------------------
// Source / health (E11, E12)
// ---------------------------------------------------------------------------

export interface DataSource {
  id: string
  category: string
  name: string
  publisher: string
  url: string
  license: string
  mode: 'live' | 'cached' | 'historical' | 'static'
  as_of: string
  methodology: string
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
  thread_id?: string | null
  message: string
  language: Language
  profile_patch?: Partial<FarmProfile>
  /** Saved farm profile; sent only when starting a brand-new conversation. */
  profile?: FarmProfile
}

export interface PrefetchResponse {
  status: string
  district: string | null
  stages: Record<string, string>
}

export interface TranscriptionResponse {
  text: string
  language: Language
  duration_s: number
  provider: string
}

export interface HealthResponse {
  status: string
  models_loaded: boolean
  data_files: number
  version: string
}

export interface SseSchemasResponse {
  note: string
}
