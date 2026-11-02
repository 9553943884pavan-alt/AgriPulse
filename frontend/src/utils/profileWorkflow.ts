/**
 * Pure helpers for the Farm Profile -> Save -> Optimize workflow.
 * Everything here is UI-framework free so it can be unit tested.
 */

import type { ApiError, FarmProfile, Language, PlanResult, TraceEvent } from '@/api/types'
import { isPlanStale } from '@/utils/planStale'

export type ProfileStatus = 'idle' | 'saving' | 'saved' | 'optimizing' | 'error'

/** True when the form differs from the last server-confirmed profile (or nothing is saved yet). */
export function isProfileDirty(
  form: FarmProfile | null | undefined,
  saved: FarmProfile | null | undefined,
): boolean {
  if (!saved || !form) return true
  if (isPlanStale(saved, form)) return true
  return JSON.stringify(form.soil_test ?? null) !== JSON.stringify(saved.soil_test ?? null)
}

export function canSave(input: { valid: boolean; dirty: boolean; status: ProfileStatus }): boolean {
  return input.valid && input.dirty && input.status !== 'saving' && input.status !== 'optimizing'
}

export interface OptimizeAvailability {
  enabled: boolean
  /** Why the button is disabled because of unsaved work (drives the "Save your changes first" hint). */
  needsSave: boolean
}

export function canOptimize(input: {
  profileVersion: number | null
  dirty: boolean
  valid: boolean
  status: ProfileStatus
}): OptimizeAvailability {
  const needsSave = input.profileVersion === null || input.dirty
  const busy = input.status === 'saving' || input.status === 'optimizing'
  return { enabled: !needsSave && input.valid && !busy, needsSave }
}

/** Repeated-click guard: only the first tryStart() succeeds until finish() is called. */
export interface RunGuard {
  tryStart(): boolean
  finish(): void
  readonly running: boolean
}

export function createRunGuard(): RunGuard {
  let running = false
  return {
    tryStart: () => {
      if (running) return false
      running = true
      return true
    },
    finish: () => {
      running = false
    },
    get running() {
      return running
    },
  }
}

export type OptimizeFailure = 'no_plan' | 'no_done' | 'error' | 'plan_not_saved'

export type OptimizeVerdict = { ok: true } | { ok: false; reason: OptimizeFailure }

/**
 * A run succeeds only when a plan AND a done event arrived, no error event was
 * seen, and (if present) the 'plan_saved' trace step finished 'ok'.
 */
export function evaluateOptimizeRun(run: {
  plan: PlanResult | null
  done: boolean
  error: ApiError | null
  trace: readonly Pick<TraceEvent, 'tool_name' | 'status'>[]
}): OptimizeVerdict {
  if (run.error) return { ok: false, reason: 'error' }
  const saveSteps = run.trace.filter((e) => e.tool_name === 'plan_saved')
  if (saveSteps.some((e) => e.status === 'failed')) return { ok: false, reason: 'plan_not_saved' }
  if (!run.plan) return { ok: false, reason: 'no_plan' }
  if (!run.done) return { ok: false, reason: 'no_done' }
  if (saveSteps.length > 0 && !saveSteps.some((e) => e.status === 'ok')) {
    return { ok: false, reason: 'plan_not_saved' }
  }
  return { ok: true }
}

export type OptimizeErrorAction = 'reload_profile' | null

export interface OptimizeErrorInfo {
  /** i18n key for the friendly message. */
  key: string
  action: OptimizeErrorAction
  /** The saved profile can no longer be trusted: Optimize stays disabled until the user saves/reloads. */
  needsSave: boolean
}

/** Maps a backend error code (or failure reason) to a friendly message key. Never exposes raw text. */
export function optimizeErrorInfo(code: string | null | undefined): OptimizeErrorInfo {
  switch (code) {
    case 'PROFILE_STALE':
      return { key: 'profile_page.opt_err_stale', action: 'reload_profile', needsSave: true }
    case 'RUN_IN_PROGRESS':
      return { key: 'profile_page.opt_err_in_progress', action: null, needsSave: false }
    case 'NO_SAVED_PROFILE':
      return { key: 'profile_page.opt_err_no_saved', action: null, needsSave: true }
    case 'VALIDATION_ERROR':
    case 'LOCATION_NOT_FOUND':
      return { key: 'profile_page.opt_err_validation', action: null, needsSave: true }
    case 'PLAN_NOT_SAVED':
      return { key: 'profile_page.opt_err_plan_not_saved', action: null, needsSave: false }
    case 'INCOMPLETE':
      return { key: 'profile_page.opt_err_incomplete', action: null, needsSave: false }
    default:
      return { key: 'profile_page.opt_err_generic', action: null, needsSave: false }
  }
}

/** Translates a failed verdict (and the error that caused it, if any) into an error code for optimizeErrorInfo. */
export function failureCode(verdict: OptimizeVerdict, error: ApiError | null): string {
  if (verdict.ok) return ''
  if (verdict.reason === 'error') return error?.code ?? 'INTERNAL'
  if (verdict.reason === 'plan_not_saved') return 'PLAN_NOT_SAVED'
  return 'INCOMPLETE'
}

/**
 * Pulls per-field messages out of a 422 envelope's details.fields.
 * Falls back to the localized top-level message when a field value is not a string.
 */
export function extractFieldErrors(error: ApiError | null | undefined, language: Language): Record<string, string> {
  const out: Record<string, string> = {}
  const fields = error?.details && typeof error.details === 'object'
    ? (error.details as { fields?: unknown }).fields
    : undefined
  if (fields && typeof fields === 'object' && !Array.isArray(fields)) {
    for (const [field, value] of Object.entries(fields as Record<string, unknown>)) {
      if (typeof value === 'string' && value.trim()) out[field] = value
      else if (Array.isArray(value) && typeof value[0] === 'string') out[field] = value[0]
    }
  }
  if (error?.code === 'LOCATION_NOT_FOUND' && !out.location_text) {
    out.location_text = error.user_message?.[language] ?? error.user_message?.en ?? ''
  }
  return out
}

/** "HH:MM" in the viewer's locale; '' when the timestamp is missing or invalid. */
export function formatSavedTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
