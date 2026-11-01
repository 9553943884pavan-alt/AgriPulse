/**
 * CONTRACT EXAMPLES — development only.
 *
 * This module is imported ONLY when VITE_USE_SAMPLES=true.
 * The production Vite build throws an error if that flag is set (see vite.config.ts).
 * CI greps the built bundle for "__CONTRACT_EXAMPLE__" and fails if found.
 *
 * These examples are hand-written against backend/SPECS.md section 5.1.
 * They are an interface agreement, not product data — they never appear at runtime.
 *
 * TODO (FE.0c): replace this with live-captured examples from docs/api_examples/live/
 * once the backend hits milestone M2.
 */

// __CONTRACT_EXAMPLE__ — marker string; DO NOT remove this comment

import type { PlanResult, FarmProfile, TraceEvent, NumericSourcedValue, ScenarioId, WaterBudget } from './types'

export const SAMPLE_PROFILE: FarmProfile = {
  location_text: 'Beed',
  land_acres: 5,
  budget_rs: 70000,
  water_source: 'borewell',
  borewell_count: 1,
  borewell_yield_lph: null,
  pump_hours_per_day: null,
  canal_access: false,
  irrigation_method: 'flood',
  risk_appetite: 'balanced',
  soil_test: null,
  language: 'mr',
  missing: [],
  defaults_used: [
    { field: 'risk_appetite', value: 'balanced', basis: 'default' },
    { field: 'irrigation_method', value: 'flood', basis: 'district majority method (Minor Irrigation Census)' },
  ],
}

export const SAMPLE_TRACE_EVENTS: TraceEvent[] = [
  {
    id: 'ev_01',
    node: 'extract_profile',
    step: 'understand_farm',
    status: 'ok',
    started_at: '2026-10-31T12:00:00+05:30',
    duration_ms: 800,
    summary: 'Understood your farm',
    source: null,
    fallback_used: null,
  },
  {
    id: 'ev_02',
    node: 'gather_data',
    step: 'get_weather',
    status: 'ok',
    started_at: '2026-10-31T12:00:01+05:30',
    duration_ms: 310,
    summary: 'Open-Meteo forecast fetched',
    source: { name: 'Open-Meteo', url: 'https://api.open-meteo.com', status: 'live' },
    fallback_used: null,
  },
  {
    id: 'ev_03',
    node: 'gather_data',
    step: 'get_prices',
    status: 'cached',
    started_at: '2026-10-31T12:00:01+05:30',
    duration_ms: 90,
    summary: 'Agmarknet prices (last quote 30 Oct)',
    source: { name: 'Agmarknet (data.gov.in)', url: 'https://api.data.gov.in', status: 'cached' },
    fallback_used: 'last real quote, 2026-10-30',
  },
]

const sampleValue = (value: number | string, unit: string, source: string, status: NumericSourcedValue['status'] = 'computed'): NumericSourcedValue => ({
  value: Number(value),
  unit,
  source,
  source_url: '',
  as_of: '2026-10-31',
  status,
})

const sampleWaterBudget = (scenario: ScenarioId, analogueYear: number, availableM3: number, needM3: number): WaterBudget => ({
  scenario,
  analogue_year: analogueYear,
  available_m3: {
    rain: sampleValue(availableM3, 'm3', 'Open-Meteo + ERA5', 'live'),
    groundwater: sampleValue(0, 'm3', 'Farmer borewell capacity unavailable; not credited', 'assumption'),
    canal: sampleValue(0, 'm3', 'Farmer reports no canal access', 'farmer_input'),
    total: sampleValue(availableM3, 'm3', 'effective rain + groundwater + canal'),
  },
  basis: {
    groundwater_category: {
      value: 'Safe',
      unit: 'category',
      source: 'CGWB',
      source_url: '',
      as_of: '2022',
      status: 'official_dataset',
    },
    category_cap: sampleValue(1, 'fraction', 'Modelling assumption', 'assumption'),
    effective_rain_factor: sampleValue(0.75, 'fraction', 'Modelling assumption', 'assumption'),
    reservoir_storage_pct: sampleValue(0, 'pct', 'No canal access', 'assumption'),
    rain_so_far_mm: sampleValue(142, 'mm', 'Open-Meteo', 'live'),
  },
  irrigation_method: 'flood',
  efficiency_pct: sampleValue(60, 'pct', 'irrigation_by_district.csv', 'official_dataset'),
  need_m3: {
    traditional_plan: sampleValue(needM3 + 1000, 'm3', 'Computed water requirement'),
    recommended_plan: sampleValue(needM3, 'm3', 'Computed water requirement'),
  },
})

export const SAMPLE_PLAN: PlanResult = {
  plan_id: 'pl_sample01',
  thread_id: 'th_sample01',
  version: 1,
  created_at: '2026-10-31T12:00:05+05:30',
  profile: SAMPLE_PROFILE,
  location: {
    input: 'Beed',
    resolved_name: 'Beed, Maharashtra',
    district: 'Beed',
    state: 'Maharashtra',
    latitude: 18.9918,
    longitude: 75.9098,
  },
  season: {
    name: 'Rabi',
    sowing_window: { start: '2026-10-15', end: '2026-11-30' },
    status: 'official_dataset',
  },
  scenarios: [
    { id: 'drought', label: 'Drought', probability: 0.2, season_rain_mm: { value: 420, unit: 'mm', source: 'ERA5 P10', source_url: '', as_of: '2026', status: 'official_dataset' } },
    { id: 'normal', label: 'Normal', probability: 0.6, season_rain_mm: { value: 630, unit: 'mm', source: 'ERA5 P50', source_url: '', as_of: '2026', status: 'official_dataset' } },
    { id: 'excess', label: 'Excess rain', probability: 0.2, season_rain_mm: { value: 880, unit: 'mm', source: 'ERA5 P90', source_url: '', as_of: '2026', status: 'official_dataset' } },
  ],
  crops: [
    {
      crop_id: 'chickpea',
      names: { en: 'Chickpea', mr: 'हरभरा', hi: 'चना' },
      season: 'Rabi',
      suitability: {
        score: 1.12,
        label: 'good',
        top_factors: [
          { feature: 'season_rainfall_mm', value: 630, unit: 'mm', effect_quintal_per_acre: 1.2, direction: 'up' },
        ],
        fallback_used: false,
      },
      yield_quintal_per_acre: { drought: 4.2, normal: 5.8, excess: 4.9 },
      price: { value: 5400, unit: 'rs_per_quintal', source: 'Agmarknet', source_url: '', as_of: '2026-10-30', status: 'cached' },
      expected_harvest_price: { value: 5670, unit: 'rs_per_quintal', source: 'today price × seasonal ratio 1.05', source_url: '', as_of: '2026-10-30', status: 'computed' },
      seasonal_ratio: { value: 1.05, unit: 'ratio', source: 'Historical monthly price ratio', source_url: '', as_of: '2026-10-30', status: 'computed', history_years: 5 },
      duration_days: 110,
      harvest_month: '2027-02',
      opens_on: null,
      msp: { value: 5440, unit: 'rs_per_quintal', source: 'CACP', source_url: '', as_of: '2025-26', status: 'official_dataset' },
      cost_per_acre: {
        total_rs: 18200,
        seed: 1600,
        fertilizer: 1800,
        manure: 700,
        labour: 8200,
        machine: 3200,
        irrigation: 500,
        pesticide: 1200,
        interest: 0,
        reference_year: '2022-23',
        source: 'DES/CACP Cost of Cultivation',
        status: 'official_dataset',
      },
      fertilizer: {
        n_kg_per_acre: 8,
        p2o5_kg_per_acre: 16,
        k2o_kg_per_acre: 0,
        urea_bags: 0.4,
        dap_bags: 0.64,
        mop_bags: 0,
        cost_rs: sampleValue(1800, 'Rs/acre', 'Fertilizer RDF × official MRP'),
        basis: 'university RDF',
      },
      water_need_m3_per_acre: {
        drought: sampleValue(1600, 'm3/acre', 'Computed crop water requirement'),
        normal: sampleValue(1200, 'm3/acre', 'Computed crop water requirement'),
        excess: sampleValue(900, 'm3/acre', 'Computed crop water requirement'),
      },
      profit_rs_per_acre: { drought: 4888, normal: 14706, excess: 9553 },
    },
  ],
  excluded_crops: [
    { crop_id: 'onion', reason_code: 'NO_REAL_PRICE', params: { district: 'Beed' } },
  ],
  water: [
    sampleWaterBudget('drought', 1999, 9000, 8000),
    sampleWaterBudget('normal', 2019, 12000, 6000),
    sampleWaterBudget('excess', 2010, 16000, 4500),
  ],
  strategies: [
    {
      id: 'qp_balanced',
      label: 'QP Balanced',
      kind: 'qp',
      risk_lambda: 0.3,
      safety_scenario: 'normal',
      allocations: [
        { crop_id: 'chickpea', acres: 5, share_pct: 100, cost_rs: 91000, water_m3: 6000, profit_rs: { drought: 24440, normal: 73530, excess: 47765 } },
      ],
      totals: { land_used_acres: 5, budget_used_rs: 61200, fertilizer_kg: { n: 40, p2o5: 80, k2o: 0 }, water_m3: 6000 },
      profit_by_scenario_rs: { drought: 24440, normal: 73530, excess: 47765 },
      expected_profit_rs: 57600,
      worst_case_profit_rs: 24440,
      feasible: true,
      binding_constraints: [],
      relaxations_applied: [],
      solver: { name: 'CLARABEL', status: 'optimal', ms: 38 },
      infeasibility: null,
      traditional_exceeds: [],
    },
  ],
  recommended_strategy: 'qp_balanced',
  impact: {
    water_saved_pct: { value: 33, unit: 'pct', source: 'computed vs traditional', source_url: '', as_of: '2026-10-31', status: 'computed' },
    fertilizer_saved_pct: { value: 18, unit: 'pct', source: 'computed vs traditional', source_url: '', as_of: '2026-10-31', status: 'computed' },
    fertilizer_vs_district_use_pct: null,
    drought_profit_gain_rs: { value: 12000, unit: 'rs', source: 'computed vs traditional drought year', source_url: '', as_of: '2026-10-31', status: 'computed' },
    versus: 'traditional',
    traditional_exceeds: [],
  },
  infeasibility: null,
  explanation: {
    language: 'mr',
    text: 'तुमच्या ५ एकर शेतीसाठी हरभरा हा सर्वोत्तम पर्याय आहे.',
    key_points: [
      { icon: 'wheat', text: 'Chickpea suits your soil and season.' },
      { icon: 'droplets', text: '33% less water than traditional plan.' },
    ],
    grounded: true,
    provider: 'sarvam-chat',
  },
  warnings: [
    { code: 'CACHED_PRICES', params: { as_of: '2026-10-30' } },
  ],
  data_status: { live: 8, cached: 3, official_dataset: 22 },
}
