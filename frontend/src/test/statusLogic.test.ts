import { describe, it, expect } from 'vitest'
import { validateProfile } from '@/utils/profileValidation'
import { aiStatus, dataStatus } from '@/utils/topBarStatus'
import { traceState } from '@/utils/traceStatus'
import type { SourceHealth } from '@/api/types'

const src = (status: SourceHealth['status']): SourceHealth => ({
  id: status, name: status, status, latency_ms: 1, last_ok: '', note: null,
})

describe('validateProfile', () => {
  it('rejects empty and zero values', () => {
    const e = validateProfile({ location_text: ' ', land_acres: '', budget_rs: '0' })
    expect(Object.keys(e).sort()).toEqual(['budget_rs', 'land_acres', 'location_text'])
  })
  it('accepts valid values', () => {
    expect(validateProfile({ location_text: 'Beed', land_acres: '2.5', budget_rs: '50000' })).toEqual({})
  })
})

describe('TopBar status', () => {
  it('data: checking, ok, degraded, down', () => {
    expect(dataStatus({ isError: false })).toBe('checking')
    expect(dataStatus({ isError: false, data: [src('green')] })).toBe('ok')
    expect(dataStatus({ isError: false, data: [src('green'), src('amber')] })).toBe('degraded')
    expect(dataStatus({ isError: true })).toBe('down')
  })
  it('ai: only ok when status ok and models loaded', () => {
    const h = { status: 'ok', models_loaded: true, data_files: 1, version: '1' }
    expect(aiStatus({ isError: false })).toBe('checking')
    expect(aiStatus({ isError: false, data: h })).toBe('ok')
    expect(aiStatus({ isError: false, data: { ...h, models_loaded: false } })).toBe('degraded')
    expect(aiStatus({ isError: true })).toBe('down')
  })
})

describe('traceState', () => {
  const base = { isStreaming: false, hasError: false, traceCount: 0, lastTurnWasQuestion: false }
  it('covers each state', () => {
    expect(traceState({ ...base, isStreaming: true })).toBe('live')
    expect(traceState({ ...base, hasError: true, traceCount: 3 })).toBe('failed')
    expect(traceState({ ...base, traceCount: 3 })).toBe('done')
    expect(traceState({ ...base, lastTurnWasQuestion: true })).toBe('waiting')
    expect(traceState(base)).toBe('idle')
  })
})
