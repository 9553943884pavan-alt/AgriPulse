import { describe, it, expect, beforeEach } from 'vitest'
import type { FarmProfile, TraceEvent } from '@/api/types'
import {
  sanitizeTraceSummary,
  sortTraceEvents,
  traceDisplayName,
  TRACE_SUMMARY_MAX,
} from '@/utils/traceStatus'
import { isPlanStale } from '@/utils/planStale'
import {
  buildChatRequest,
  isPlaceholderProfile,
  isUsableProfile,
  MAX_MESSAGE_LENGTH,
  normalizeAgentText,
} from '@/utils/chatRequest'
import { createStreamGuard } from '@/utils/streamGuard'
import { MAX_PERSISTED_MESSAGES, useStore } from '@/state/store'

const profile = (over: Partial<FarmProfile> = {}): FarmProfile => ({
  location_text: 'Beed',
  land_acres: 2,
  budget_rs: 50000,
  water_source: 'borewell',
  borewell_count: 1,
  borewell_yield_lph: 3000,
  pump_hours_per_day: 6,
  canal_access: false,
  irrigation_method: 'drip',
  risk_appetite: 'balanced',
  soil_test: null,
  language: 'en',
  missing: [],
  defaults_used: [],
  ...over,
})

const ev = (over: Partial<TraceEvent>): TraceEvent => ({
  id: 'e1',
  node: 'n',
  step: 'llm',
  status: 'ok',
  started_at: '',
  duration_ms: 0,
  summary: '',
  source: null,
  fallback_used: null,
  ...over,
})

const THREAD = `th_${'a'.repeat(32)}`

describe('traceDisplayName', () => {
  it('prefers display_name from the backend', () => {
    expect(traceDisplayName(ev({ step: 'crop_recommender', display_name: 'Crop Recommendation' }))).toBe('Crop Recommendation')
  })
  it('maps known internal names', () => {
    expect(traceDisplayName(ev({ step: 'crop_recommender' }))).toBe('Crop Recommendation')
    expect(traceDisplayName(ev({ step: 'yield_predictor' }))).toBe('Yield Prediction')
    expect(traceDisplayName(ev({ step: 'market_price_service' }))).toBe('Market Price Analysis')
    expect(traceDisplayName(ev({ step: 'water_analyzer' }))).toBe('Water Availability Analysis')
    expect(traceDisplayName(ev({ step: 'cost_calculator' }))).toBe('Cultivation Cost Estimation')
    expect(traceDisplayName(ev({ step: 'optimizer' }))).toBe('Farm Plan Optimization')
  })
  it('falls back to tool_name, then a humanized step, never raw ids alone', () => {
    expect(traceDisplayName(ev({ step: 'unknown_step', tool_name: 'optimizer' }))).toBe('Farm Plan Optimization')
    expect(traceDisplayName(ev({ step: 'soil_data_lookup' }))).toBe('Soil Data Lookup')
    expect(traceDisplayName(ev({ step: 'llm' }))).not.toBe('llm')
    expect(traceDisplayName(ev({ step: 'check' }))).not.toBe('check')
    expect(traceDisplayName(ev({ step: 'complete' }))).not.toBe('complete')
    expect(traceDisplayName(ev({ step: '', node: '' }))).toBe('Working')
  })
})

describe('sanitizeTraceSummary', () => {
  it('keeps normal text and truncates long text', () => {
    expect(sanitizeTraceSummary('  Found 3 crops ')).toBe('Found 3 crops')
    const out = sanitizeTraceSummary('x'.repeat(500))
    expect(out.length).toBeLessThanOrEqual(TRACE_SUMMARY_MAX)
    expect(out.endsWith('…')).toBe(true)
  })
  it('hides tracebacks, exceptions, JSON and secrets', () => {
    expect(sanitizeTraceSummary('Traceback (most recent call last):\n  File "a.py", line 3')).toBe('')
    expect(sanitizeTraceSummary("KeyError: 'crop'")).toBe('')
    expect(sanitizeTraceSummary('{"a": 1}')).toBe('')
    expect(sanitizeTraceSummary('using sk-abcdef1234567890')).toBe('')
    expect(sanitizeTraceSummary('api_key=abc')).toBe('')
    expect(sanitizeTraceSummary(undefined)).toBe('')
  })
})

describe('sortTraceEvents', () => {
  it('orders by sequence when all events have one', () => {
    const out = sortTraceEvents([
      ev({ id: 'b', sequence: 2 }), ev({ id: 'a', sequence: 1 }), ev({ id: 'c', sequence: 3 }),
    ])
    expect(out.map((e) => e.id)).toEqual(['a', 'b', 'c'])
  })
  it('keeps arrival order when sequence is missing and does not mutate', () => {
    const input = [ev({ id: 'x' }), ev({ id: 'y', sequence: 1 }), ev({ id: 'z' })]
    expect(sortTraceEvents(input).map((e) => e.id)).toEqual(['x', 'y', 'z'])
    const seq = [ev({ id: 'b', sequence: 2 }), ev({ id: 'a', sequence: 1 })]
    sortTraceEvents(seq)
    expect(seq.map((e) => e.id)).toEqual(['b', 'a'])
  })
})

describe('isPlanStale', () => {
  it('is false for identical or missing profiles', () => {
    expect(isPlanStale(profile(), profile())).toBe(false)
    expect(isPlanStale(null, profile())).toBe(false)
    expect(isPlanStale(profile(), null)).toBe(false)
  })
  it('ignores case/whitespace in location and unrelated fields', () => {
    expect(isPlanStale(profile(), profile({ location_text: ' beed ', language: 'mr' }))).toBe(false)
  })
  it.each([
    { land_acres: 3 }, { budget_rs: 10 }, { location_text: 'Latur' }, { water_source: 'canal' },
    { borewell_count: 2 }, { borewell_yield_lph: 1 }, { pump_hours_per_day: 1 },
    { canal_access: true }, { irrigation_method: 'flood' }, { risk_appetite: 'safe' },
  ] as Partial<FarmProfile>[])('detects change %o', (change) => {
    expect(isPlanStale(profile(), profile(change))).toBe(true)
  })
})

describe('buildChatRequest', () => {
  it('sends the saved profile only for a new conversation', () => {
    const p = profile()
    const fresh = buildChatRequest({ threadId: null, message: 'hi', language: 'en', profile: p })
    expect(fresh.profile).toEqual(p)
    expect(fresh.thread_id).toBeNull()
    const existing = buildChatRequest({ threadId: THREAD, message: 'hi', language: 'en', profile: p })
    expect(existing.profile).toBeUndefined()
    expect(existing.thread_id).toBe(THREAD)
  })
  it('does not send unusable profiles', () => {
    for (const bad of [
      null,
      profile({ location_text: '' }),
      profile({ location_text: 'unknown' }),
      profile({ land_acres: 0 }),
      profile({ budget_rs: 0 }),
    ]) {
      expect('profile' in buildChatRequest({ threadId: null, message: 'hi', language: 'hi', profile: bad })).toBe(false)
    }
  })
  it('treats malformed thread ids as a new conversation and caps message length', () => {
    const req = buildChatRequest({ threadId: 'old-id', message: ` ${'a'.repeat(3000)} `, language: 'mr', profile: profile() })
    expect(req.thread_id).toBeNull()
    expect(req.profile).toBeDefined()
    expect(req.message.length).toBe(MAX_MESSAGE_LENGTH)
    expect(req.language).toBe('mr')
  })
  it('profile helpers', () => {
    expect(isUsableProfile(profile())).toBe(true)
    expect(isPlaceholderProfile(profile({ location_text: 'Unknown' }))).toBe(true)
    expect(isPlaceholderProfile(profile({ land_acres: -1 }))).toBe(true)
    expect(isPlaceholderProfile(profile({ budget_rs: 0 }))).toBe(false)
  })
  it('normalizeAgentText trims and rejects non-strings', () => {
    expect(normalizeAgentText('  hi \n')).toBe('hi')
    expect(normalizeAgentText('   ')).toBe('')
    expect(normalizeAgentText(null)).toBe('')
  })
})

describe('createStreamGuard', () => {
  it('only the latest request is current', () => {
    const g = createStreamGuard()
    const a = g.begin()
    expect(g.isCurrent(a)).toBe(true)
    const b = g.begin()
    expect(g.isCurrent(a)).toBe(false)
    expect(g.isCurrent(b)).toBe(true)
    g.invalidate()
    expect(g.isCurrent(b)).toBe(false)
  })
})

describe('store', () => {
  beforeEach(() => { useStore.getState().reset() })
  it('keeps trace events unique by id and in arrival order', () => {
    const { addTraceEvent } = useStore.getState()
    addTraceEvent(ev({ id: '1', status: 'running' }))
    addTraceEvent(ev({ id: '2' }))
    addTraceEvent(ev({ id: '1', status: 'ok' }))
    const events = useStore.getState().traceEvents
    expect(events.map((e) => `${e.id}:${e.status}`)).toEqual(['1:ok', '2:ok'])
  })
  it('caps persisted messages at 50', () => {
    expect(MAX_PERSISTED_MESSAGES).toBe(50)
  })
})
