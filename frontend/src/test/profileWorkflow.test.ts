import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  canOptimize,
  canSave,
  createRunGuard,
  evaluateOptimizeRun,
  extractFieldErrors,
  failureCode,
  formatSavedTime,
  isProfileDirty,
  optimizeErrorInfo,
} from '@/utils/profileWorkflow'
import { useStore } from '@/state/store'
import { normalizeApiError } from '@/api/client'
import { streamChat, type SSEHandlers } from '@/api/sseClient'
import type { ApiError, FarmProfile, PlanResult } from '@/api/types'

const PROFILE: FarmProfile = {
  location_text: 'Nashik, Maharashtra',
  land_acres: 2,
  budget_rs: 200000,
  water_source: 'borewell',
  borewell_count: 1,
  borewell_yield_lph: 8000,
  pump_hours_per_day: 6,
  canal_access: false,
  irrigation_method: 'drip',
  risk_appetite: 'balanced',
  soil_test: null,
  language: 'en',
  missing: [],
  defaults_used: [],
}

const PLAN = { plan_id: 'p1' } as unknown as PlanResult

function apiError(code: string, extra: Partial<ApiError> = {}): ApiError {
  return {
    code,
    message: code,
    user_message: { en: 'English text', mr: 'Marathi text', hi: 'Hindi text' },
    retryable: false,
    details: {},
    ...extra,
  }
}

describe('isProfileDirty', () => {
  it('is dirty when nothing has been saved', () => {
    expect(isProfileDirty(PROFILE, null)).toBe(true)
  })

  it('is clean when the form equals the saved profile', () => {
    expect(isProfileDirty({ ...PROFILE }, PROFILE)).toBe(false)
  })

  it('ignores case and surrounding spaces in text', () => {
    expect(isProfileDirty({ ...PROFILE, location_text: '  nashik, MAHARASHTRA ' }, PROFILE)).toBe(false)
  })

  it('treats undefined and null optional numbers as the same', () => {
    const saved = { ...PROFILE, pump_hours_per_day: null }
    const form = { ...PROFILE, pump_hours_per_day: undefined } as unknown as FarmProfile
    expect(isProfileDirty(form, saved)).toBe(false)
  })

  it('is dirty after any meaningful edit', () => {
    expect(isProfileDirty({ ...PROFILE, land_acres: 3 }, PROFILE)).toBe(true)
    expect(isProfileDirty({ ...PROFILE, irrigation_method: 'flood' }, PROFILE)).toBe(true)
    expect(isProfileDirty({ ...PROFILE, borewell_yield_lph: 9000 }, PROFILE)).toBe(true)
    expect(isProfileDirty({ ...PROFILE, soil_test: { n: 1, p: 1, k: 1, ph: 6.5 } }, PROFILE)).toBe(true)
  })
})

describe('canSave / canOptimize', () => {
  it('enables Save only for a valid, dirty form that is not busy', () => {
    expect(canSave({ valid: true, dirty: true, status: 'idle' })).toBe(true)
    expect(canSave({ valid: false, dirty: true, status: 'idle' })).toBe(false)
    expect(canSave({ valid: true, dirty: false, status: 'saved' })).toBe(false)
    expect(canSave({ valid: true, dirty: true, status: 'saving' })).toBe(false)
    expect(canSave({ valid: true, dirty: true, status: 'optimizing' })).toBe(false)
  })

  it('enables Optimize only when saved, clean, valid and idle', () => {
    expect(canOptimize({ profileVersion: 3, dirty: false, valid: true, status: 'saved' })).toEqual({ enabled: true, needsSave: false })
  })

  it('disables Optimize with the save hint when never saved (legacy profile)', () => {
    expect(canOptimize({ profileVersion: null, dirty: false, valid: true, status: 'idle' })).toEqual({ enabled: false, needsSave: true })
  })

  it('disables Optimize with the save hint when the form is edited', () => {
    expect(canOptimize({ profileVersion: 3, dirty: true, valid: true, status: 'idle' })).toEqual({ enabled: false, needsSave: true })
  })

  it('disables Optimize while saving or optimizing', () => {
    expect(canOptimize({ profileVersion: 3, dirty: false, valid: true, status: 'saving' }).enabled).toBe(false)
    expect(canOptimize({ profileVersion: 3, dirty: false, valid: true, status: 'optimizing' }).enabled).toBe(false)
  })

  it('keeps Optimize enabled for a retry after an error when the profile is still clean', () => {
    expect(canOptimize({ profileVersion: 3, dirty: false, valid: true, status: 'error' }).enabled).toBe(true)
  })
})

describe('evaluateOptimizeRun', () => {
  const okTrace = [{ tool_name: 'optimizer', status: 'ok' as const }, { tool_name: 'plan_saved', status: 'ok' as const }]

  it('succeeds with plan + done + no error + plan_saved ok', () => {
    expect(evaluateOptimizeRun({ plan: PLAN, done: true, error: null, trace: okTrace })).toEqual({ ok: true })
  })

  it('succeeds when the backend sends no plan_saved trace item', () => {
    expect(evaluateOptimizeRun({ plan: PLAN, done: true, error: null, trace: [] })).toEqual({ ok: true })
  })

  it('fails without a plan, without done, or with an error', () => {
    expect(evaluateOptimizeRun({ plan: null, done: true, error: null, trace: okTrace })).toEqual({ ok: false, reason: 'no_plan' })
    expect(evaluateOptimizeRun({ plan: PLAN, done: false, error: null, trace: okTrace })).toEqual({ ok: false, reason: 'no_done' })
    expect(evaluateOptimizeRun({ plan: PLAN, done: true, error: apiError('INTERNAL'), trace: okTrace })).toEqual({ ok: false, reason: 'error' })
  })

  it('fails when plan_saved failed or never finished', () => {
    const failed = [{ tool_name: 'plan_saved', status: 'failed' as const }]
    const running = [{ tool_name: 'plan_saved', status: 'running' as const }]
    expect(evaluateOptimizeRun({ plan: PLAN, done: true, error: null, trace: failed })).toEqual({ ok: false, reason: 'plan_not_saved' })
    expect(evaluateOptimizeRun({ plan: PLAN, done: true, error: null, trace: running })).toEqual({ ok: false, reason: 'plan_not_saved' })
  })

  it('maps verdicts to error codes', () => {
    const err = apiError('PROFILE_STALE')
    expect(failureCode({ ok: false, reason: 'error' }, err)).toBe('PROFILE_STALE')
    expect(failureCode({ ok: false, reason: 'plan_not_saved' }, null)).toBe('PLAN_NOT_SAVED')
    expect(failureCode({ ok: false, reason: 'no_done' }, null)).toBe('INCOMPLETE')
  })
})

describe('optimizeErrorInfo', () => {
  it('maps backend codes to friendly message keys', () => {
    expect(optimizeErrorInfo('PROFILE_STALE')).toMatchObject({ key: 'profile_page.opt_err_stale', action: 'reload_profile' })
    expect(optimizeErrorInfo('RUN_IN_PROGRESS').key).toBe('profile_page.opt_err_in_progress')
    expect(optimizeErrorInfo('NO_SAVED_PROFILE')).toMatchObject({ key: 'profile_page.opt_err_no_saved', needsSave: true })
    expect(optimizeErrorInfo('VALIDATION_ERROR')).toMatchObject({ key: 'profile_page.opt_err_validation', needsSave: true })
    expect(optimizeErrorInfo('LOCATION_NOT_FOUND').key).toBe('profile_page.opt_err_validation')
  })

  it('falls back to a generic retry message for anything else', () => {
    expect(optimizeErrorInfo('INTERNAL')).toMatchObject({ key: 'profile_page.opt_err_generic', needsSave: false, action: null })
    expect(optimizeErrorInfo(undefined).key).toBe('profile_page.opt_err_generic')
  })
})

describe('createRunGuard (repeated clicks)', () => {
  it('lets only the first start through until finished', () => {
    const guard = createRunGuard()
    expect(guard.tryStart()).toBe(true)
    expect(guard.tryStart()).toBe(false)
    expect(guard.running).toBe(true)
    guard.finish()
    expect(guard.running).toBe(false)
    expect(guard.tryStart()).toBe(true)
  })
})

describe('extractFieldErrors', () => {
  it('reads details.fields from a 422 envelope', () => {
    const err = normalizeApiError({
      error: {
        code: 'VALIDATION_ERROR',
        user_message: { en: 'Check the details.', mr: 'x', hi: 'y' },
        details: { fields: { land_acres: 'Must be greater than 0', budget_rs: 'Too small' } },
      },
    }, 422)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(extractFieldErrors(err, 'en')).toEqual({ land_acres: 'Must be greater than 0', budget_rs: 'Too small' })
  })

  it('maps LOCATION_NOT_FOUND onto the location field using the localized message', () => {
    const err = apiError('LOCATION_NOT_FOUND')
    expect(extractFieldErrors(err, 'hi')).toEqual({ location_text: 'Hindi text' })
  })

  it('returns nothing when there are no field details', () => {
    expect(extractFieldErrors(apiError('INTERNAL'), 'en')).toEqual({})
    expect(extractFieldErrors(null, 'en')).toEqual({})
  })
})

describe('formatSavedTime', () => {
  it('returns an HH:MM string for a valid timestamp and empty otherwise', () => {
    expect(formatSavedTime('2026-11-02T10:05:00Z')).toMatch(/\d{1,2}[:.]\d{2}/)
    expect(formatSavedTime('not a date')).toBe('')
    expect(formatSavedTime(null)).toBe('')
  })
})

describe('store.setSavedProfile', () => {
  beforeEach(() => {
    useStore.getState().reset()
  })

  it('adopts profile, thread and version without clearing the plan', () => {
    useStore.setState({ plan: PLAN })
    useStore.getState().setSavedProfile({
      thread_id: 'th_' + 'a'.repeat(32),
      profile: PROFILE,
      profile_version: 4,
      saved_at: '2026-11-02T10:05:00Z',
    })
    const state = useStore.getState()
    expect(state.plan).toBe(PLAN)
    expect(state.profile).toEqual(PROFILE)
    expect(state.threadId).toBe('th_' + 'a'.repeat(32))
    expect(state.profileVersion).toBe(4)
    expect(state.profileSavedAt).toBe('2026-11-02T10:05:00Z')
  })

  it('starts with no profile version (legacy profiles count as unsaved)', () => {
    expect(useStore.getState().profileVersion).toBeNull()
  })

  it('setProfileVersion keeps the saved-at stamp when none is given', () => {
    useStore.getState().setProfileVersion(2, 'stamp')
    useStore.getState().setProfileVersion(3)
    expect(useStore.getState().profileVersion).toBe(3)
    expect(useStore.getState().profileSavedAt).toBe('stamp')
  })
})

describe('optimize stream surfaces pre-stream HTTP errors and done.profile_version', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const handlers = (): SSEHandlers => ({
    onThread: vi.fn(), onProfile: vi.fn(), onQuestion: vi.fn(), onTrace: vi.fn(), onPlan: vi.fn(),
    onMessage: vi.fn(), onError: vi.fn(), onDone: vi.fn(), onClose: vi.fn(),
  })

  it('passes a 409 PROFILE_STALE envelope without a message field to onError', async () => {
    const h = handlers()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'PROFILE_STALE', user_message: { en: 'Stale', mr: 'm', hi: 'h' }, details: {} },
    }), { status: 409, headers: { 'Content-Type': 'application/json' } })))
    streamChat({ thread_id: 'th_' + 'a'.repeat(32), language: 'en', intent: 'optimize', profile_version: 2 }, h)
    await vi.waitFor(() => expect(h.onClose).toHaveBeenCalledOnce())
    expect(h.onError).toHaveBeenCalledWith(expect.objectContaining({ code: 'PROFILE_STALE' }))
  })

  it('reports profile_version on the done event when present', async () => {
    const h = handlers()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      ['event: done', 'data: {"ms":5,"profile_version":7}', '', ''].join('\n'),
      { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
    )))
    streamChat({ thread_id: null, language: 'en', intent: 'optimize', profile_version: 7 }, h)
    await vi.waitFor(() => expect(h.onClose).toHaveBeenCalledOnce())
    expect(h.onDone).toHaveBeenCalledWith({ ms: 5, profile_version: 7 })
  })
})
