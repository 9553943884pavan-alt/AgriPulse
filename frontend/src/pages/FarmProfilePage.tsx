/**
 * FarmProfilePage — view, edit, SAVE and then OPTIMIZE the farm profile.
 *
 * Workflow: edit -> "Save Changes" (PUT /api/profile, persists only) ->
 * "Optimize Plan" (agent run from the SAVED profile) -> redirect to /dashboard
 * only after a plan was generated AND persisted. Optimize is never available
 * for unsaved form values.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MapPin, CheckCircle2, Sparkles } from 'lucide-react'
import { Card, CardHeader } from '@/components/Card'
import { Button } from '@/components/Button'
import { Badge } from '@/components/Badge'
import { ErrorState } from '@/components/ErrorState'
import { TraceTimeline } from '@/features/trace/TraceTimeline'
import { useStore } from '@/state/store'
import { ApiClientError, NetworkError, apiFetch, saveProfile } from '@/api/client'
import { streamChat } from '@/api/sseClient'
import { useLocationSearch, usePrefetchLocation } from '@/api/queryHooks'
import { validateProfile } from '@/utils/profileValidation'
import { isValidThreadId, isPlaceholderProfile } from '@/utils/chatRequest'
import { createStreamGuard } from '@/utils/streamGuard'
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
  type OptimizeErrorInfo,
  type ProfileStatus,
} from '@/utils/profileWorkflow'
import type {
  ApiError,
  FarmProfile,
  IrrigationMethod,
  Language,
  PlanResult,
  RiskAppetite,
  ThreadResponse,
  TraceEvent,
  WaterSource,
} from '@/api/types'

const numText = (n: number | null | undefined) => (n && n > 0 ? String(n) : '')

const INITIAL_PROFILE: FarmProfile = {
  location_text: '',
  land_acres: 0,
  budget_rs: 0,
  water_source: 'borewell',
  irrigation_method: 'flood',
  risk_appetite: 'balanced',
  canal_access: false,
  borewell_count: 1,
  borewell_yield_lph: null,
  pump_hours_per_day: null,
  soil_test: null,
  language: 'en',
  missing: [],
  defaults_used: [],
}

/** Field names that have their own inline error slot in the form. */
const INLINE_FIELDS = new Set([
  'location_text', 'land_acres', 'budget_rs', 'water_source', 'borewell_count',
  'borewell_yield_lph', 'pump_hours_per_day', 'irrigation_method', 'risk_appetite',
])

type SaveError = { kind: 'network' } | { kind: 'api'; error: ApiError }

interface RunError {
  info: OptimizeErrorInfo
  apiError: ApiError | null
}

export function FarmProfilePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const profile = useStore((s) => s.profile)
  const plan = useStore((s) => s.plan)
  const profileVersion = useStore((s) => s.profileVersion)
  const profileSavedAt = useStore((s) => s.profileSavedAt)
  const language = useStore((s) => s.language) as Language
  const traceEvents = useStore((s) => s.traceEvents)

  // Last server-confirmed profile. A stored profile without a version (legacy) counts as UNSAVED.
  const savedSnapshot = profileVersion !== null ? profile : null

  const [form, setForm] = useState<Partial<FarmProfile>>(profile ?? { ...INITIAL_PROFILE })
  const [landText, setLandText] = useState(numText(profile?.land_acres))
  const [budgetText, setBudgetText] = useState(numText(profile?.budget_rs))
  const [submitAttempted, setSubmitAttempted] = useState(false)
  const [touched, setTouched] = useState(false)
  const [locationFocused, setLocationFocused] = useState(false)
  const [status, setStatus] = useState<ProfileStatus>('idle')
  const [saveError, setSaveError] = useState<SaveError | null>(null)
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})
  const [runError, setRunError] = useState<RunError | null>(null)
  const [runAttempted, setRunAttempted] = useState(false)
  const [reloading, setReloading] = useState(false)
  // Set when the server told us the saved profile cannot be used (stale / missing / invalid).
  const [forceDirty, setForceDirty] = useState(false)

  const lastSyncedRef = useRef<FarmProfile | null>(profile)
  const mountedRef = useRef(true)
  const abortRef = useRef<AbortController | null>(null)
  const streamGuardRef = useRef(createStreamGuard())
  const [saveGuard] = useState(() => createRunGuard())
  const [optimizeGuard] = useState(() => createRunGuard())

  const locationQuery = form.location_text ?? ''
  const locationSearch = useLocationSearch(locationQuery)
  const prefetch = usePrefetchLocation()

  const applyProfileToForm = (p: FarmProfile | null) => {
    setForm(p ?? { ...INITIAL_PROFILE })
    setLandText(numText(p?.land_acres))
    setBudgetText(numText(p?.budget_rs))
  }

  const patchForm = (patch: Partial<FarmProfile>) => {
    setTouched(true)
    setForm((f) => ({ ...f, ...patch }))
  }

  // The form as the server would receive it.
  const currentProfile = useMemo<FarmProfile>(() => ({
    ...INITIAL_PROFILE,
    ...form,
    location_text: (form.location_text ?? '').trim(),
    land_acres: Number(landText) || 0,
    budget_rs: Number(budgetText) || 0,
  }), [form, landText, budgetText])

  const errors = validateProfile({
    location_text: form.location_text ?? '',
    land_acres: landText,
    budget_rs: budgetText,
  })
  const valid = Object.keys(errors).length === 0
  const showErrors = submitAttempted || touched
  const isDirty = forceDirty || isProfileDirty(currentProfile, savedSnapshot)
  const busy = status === 'saving' || status === 'optimizing'
  const saveEnabled = canSave({ valid, dirty: isDirty, status })
  const optimizeState = canOptimize({ profileVersion, dirty: isDirty, valid, status })

  // Keep the form in step with the store (e.g. a profile change made through chat),
  // but never throw away edits the farmer has made.
  useEffect(() => {
    if (!profile || profile === lastSyncedRef.current) return
    const previous = lastSyncedRef.current
    lastSyncedRef.current = profile
    const formIsClean = previous ? !isProfileDirty(currentProfile, previous) : !touched
    if (formIsClean && !isPlaceholderProfile(profile)) {
      setForm(profile)
      setLandText(numText(profile.land_acres))
      setBudgetText(numText(profile.budget_rs))
    }
  }, [profile, currentProfile, touched])

  // Server-side field errors belong to the values that produced them.
  useEffect(() => {
    setServerErrors({})
  }, [form, landText, budgetText])

  useEffect(() => {
    mountedRef.current = true
    const guard = streamGuardRef.current
    return () => {
      mountedRef.current = false
      guard.invalidate()
      abortRef.current?.abort()
    }
  }, [])

  const handleSave = async () => {
    setSubmitAttempted(true)
    if (!canSave({ valid, dirty: isDirty, status })) return
    if (!saveGuard.tryStart()) return
    setStatus('saving')
    setSaveError(null)
    setRunError(null)
    setServerErrors({})
    try {
      const submitted: FarmProfile = { ...currentProfile, language }
      const { threadId, setSavedProfile } = useStore.getState()
      const result = await saveProfile(isValidThreadId(threadId) ? threadId : null, submitted)
      if (typeof result.profile_version !== 'number') throw new NetworkError('Unexpected save response')
      const saved = result.profile ?? submitted
      setSavedProfile({
        thread_id: result.thread_id,
        profile: saved,
        profile_version: result.profile_version,
        saved_at: result.saved_at,
      })
      lastSyncedRef.current = saved
      if (mountedRef.current) {
        applyProfileToForm(saved)
        setForceDirty(false)
        setStatus('saved')
      }
    } catch (err) {
      if (!mountedRef.current) return
      setStatus('error')
      if (err instanceof ApiClientError) {
        const fields = extractFieldErrors(err.apiError, language)
        if (Object.keys(fields).length > 0) setServerErrors(fields)
        else setSaveError({ kind: 'api', error: err.apiError })
      } else {
        setSaveError({ kind: 'network' })
      }
    } finally {
      saveGuard.finish()
    }
  }

  const failRun = (code: string, apiError: ApiError | null) => {
    const info = optimizeErrorInfo(code)
    setRunError({ info, apiError })
    if (info.needsSave) setForceDirty(true)
    setStatus('error')
    optimizeGuard.finish()
    abortRef.current = null
  }

  const handleOptimize = () => {
    if (!optimizeState.enabled || optimizeGuard.running) return
    if (!optimizeGuard.tryStart()) return

    const { threadId, profileVersion: version, clearTrace, addTraceEvent, setThreadId, setProfile, setPlan, setProfileVersion } =
      useStore.getState()
    if (!isValidThreadId(threadId) || version === null) {
      failRun('NO_SAVED_PROFILE', null)
      return
    }

    setStatus('optimizing')
    setRunError(null)
    setSaveError(null)
    setRunAttempted(true)
    clearTrace()

    const token = streamGuardRef.current.begin()
    const isLive = () => mountedRef.current && streamGuardRef.current.isCurrent(token)
    const live = <A extends unknown[]>(fn: (...args: A) => void) => (...args: A) => {
      if (isLive()) fn(...args)
    }

    const run: {
      plan: PlanResult | null
      done: boolean
      doneVersion: number | null
      error: ApiError | null
      trace: Map<string, TraceEvent>
    } = { plan: null, done: false, doneVersion: null, error: null, trace: new Map() }

    abortRef.current = streamChat(
      { thread_id: threadId, language, intent: 'optimize', profile_version: version },
      {
        onThread: live((e) => { if (e.thread_id !== useStore.getState().threadId) setThreadId(e.thread_id) }),
        onProfile: live((e: FarmProfile) => { if (!isPlaceholderProfile(e)) setProfile(e) }),
        onQuestion: live(() => { /* an optimize run never asks; treated as incomplete on close */ }),
        onTrace: live((e) => {
          run.trace.set(e.id, e)
          addTraceEvent(e)
        }),
        onPlan: live((e: PlanResult) => { run.plan = e }),
        onMessage: live(() => { /* chat text is not shown here */ }),
        onError: live((e: ApiError) => { run.error ??= e }),
        onDone: live((e) => {
          run.done = true
          if (typeof e.profile_version === 'number') run.doneVersion = e.profile_version
        }),
        onClose: live(() => {
          const verdict = evaluateOptimizeRun({
            plan: run.plan,
            done: run.done,
            error: run.error,
            trace: Array.from(run.trace.values()),
          })
          if (!verdict.ok || !run.plan) {
            failRun(failureCode(verdict, run.error), run.error)
            return
          }
          // Plan generated AND persisted: only now adopt it and leave the page.
          setPlan(run.plan)
          if (run.doneVersion !== null) setProfileVersion(run.doneVersion)
          abortRef.current = null
          navigate('/dashboard')
        }),
      },
    )
  }

  const handleCancel = () => {
    streamGuardRef.current.invalidate()
    abortRef.current?.abort()
    abortRef.current = null
    optimizeGuard.finish()
    setRunError(null)
    setStatus('idle')
  }

  const handleReloadSaved = async () => {
    const { threadId } = useStore.getState()
    if (!isValidThreadId(threadId) || reloading) return
    setReloading(true)
    try {
      const thread = await apiFetch<ThreadResponse>(`/api/threads/${encodeURIComponent(threadId)}`)
      if (!mountedRef.current) return
      if (thread.profile && typeof thread.profile_version === 'number') {
        const { setProfile, setProfileVersion } = useStore.getState()
        setProfile(thread.profile)
        setProfileVersion(thread.profile_version, thread.profile_saved_at ?? null)
        lastSyncedRef.current = thread.profile
        applyProfileToForm(thread.profile)
        setForceDirty(false)
        setTouched(false)
        setRunError(null)
        setStatus('idle')
      } else {
        setRunError({ info: optimizeErrorInfo('NO_SAVED_PROFILE'), apiError: null })
      }
    } catch {
      if (mountedRef.current) setRunError({ info: optimizeErrorInfo(null), apiError: null })
    } finally {
      if (mountedRef.current) setReloading(false)
    }
  }

  const handleReset = () => {
    applyProfileToForm(savedSnapshot ?? profile)
    setTouched(false)
    setSubmitAttempted(false)
    setSaveError(null)
    setServerErrors({})
    setRunError(null)
    if (status === 'error' || status === 'saved') setStatus('idle')
  }

  const riskValue = form.risk_appetite === 'safe' ? 0 : form.risk_appetite === 'balanced' ? 50 : 100
  const savedTime = formatSavedTime(profileSavedAt)
  const showSavedNote = profileVersion !== null && !isDirty && !busy
  const unmappedErrors = Object.entries(serverErrors).filter(([field]) => !INLINE_FIELDS.has(field))
  const serverFieldError = (field: string) => (
    field in serverErrors ? (
      <p role="alert" className="mt-1 text-xs text-danger">
        {serverErrors[field] || t('profile_page.field_error_fallback')}
      </p>
    ) : null
  )

  return (
    <div className="h-full overflow-y-auto" style={{ scrollbarWidth: 'thin', scrollbarColor: '#16834A transparent' }}>
    <div className="max-w-5xl mx-auto px-4 lg:px-6 py-6">
      {/* Page header */}
      <div className="mb-6 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-sage-mist/70 text-forest flex items-center justify-center shadow-xs border border-sage-mist">
            <span className="text-xl" aria-hidden="true">📋</span>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-ink">{t('profile_page.title')}</h1>
            <p className="text-sm text-muted">{t('profile_page.subtitle')}</p>
          </div>
        </div>
        {/* Context hint */}
        <div className="hidden lg:flex items-center gap-2 text-sm text-forest bg-sage-mist/60 border border-sage-mist rounded-xl px-4 py-2.5 max-w-xs shadow-xs">
          <span aria-hidden="true">ℹ️</span>
          <span>{t('misc.profile_hint')}</span>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">

        {/* ── Form ─────────────────────────────────────────────── */}
        <div className="lg:col-span-2">
          <Card>
            <div className="p-6">
              <CardHeader
                icon={<span aria-hidden="true">🌱</span>}
                title={t('profile_page.basic_info')}
              />

              <fieldset disabled={busy} className="mt-6 space-y-5 min-w-0 border-0 p-0 m-0">
                {/* Location */}
                <div>
                  <label className="block text-sm font-semibold text-ink mb-1.5" htmlFor="location">
                    {t('profile_page.location_label')} <span className="text-danger">*</span>
                  </label>
                  <div className="relative">
                    <MapPin className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
                    <input
                      id="location"
                      type="text"
                      value={form.location_text ?? ''}
                      onChange={(e) => patchForm({ location_text: e.target.value })}
                      onFocus={() => setLocationFocused(true)}
                      onBlur={() => window.setTimeout(() => setLocationFocused(false), 150)}
                      autoComplete="off"
                      role="combobox"
                      aria-expanded={locationFocused && (locationSearch.data?.results.length ?? 0) > 0}
                      aria-controls="location-suggestions"
                      placeholder="e.g. Beed, Maharashtra"
                      aria-invalid={showErrors && !!errors.location_text}
                      className="w-full pl-9 pr-4 py-3 rounded-btn border border-gray-300 text-sm text-ink placeholder-muted focus:outline-none focus:ring-2 focus:ring-primary min-h-touch"
                    />
                    {locationFocused && (locationSearch.data?.results.length ?? 0) > 0 && (
                      <ul
                        id="location-suggestions"
                        role="listbox"
                        className="absolute z-20 top-full left-0 right-0 mt-1 rounded-xl border border-gray-200 bg-white shadow-lg overflow-hidden"
                      >
                        {locationSearch.data?.results.map((location) => (
                          <li key={`${location.district}-${location.latitude}-${location.longitude}`} role="option" aria-selected={false}>
                            <button
                              type="button"
                              onMouseDown={(event) => event.preventDefault()}
                              onClick={() => {
                                patchForm({ location_text: location.resolved_name })
                                setLocationFocused(false)
                                prefetch.mutate(location.resolved_name)
                              }}
                              className="w-full px-4 py-3 text-left text-sm hover:bg-green-50"
                            >
                              {location.resolved_name}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  {showErrors && errors.location_text && (
                    <p role="alert" className="mt-1 text-xs text-danger">{t(errors.location_text)}</p>
                  )}
                  {serverFieldError('location_text')}
                  {prefetch.isError && (
                    <p role="status" className="mt-1 text-xs text-amber-700">
                      {t('errors.prefetch_failed', 'Location cache could not be warmed; planning can still continue.')}
                    </p>
                  )}
                </div>

                {/* Land */}
                <div>
                  <label className="block text-sm font-semibold text-ink mb-1.5" htmlFor="land">
                    {t('profile_page.land_label')} <span className="text-danger">*</span>
                  </label>
                  <div className="flex gap-3">
                    <input
                      id="land"
                      type="number"
                      min={0}
                      step={0.5}
                      value={landText}
                      aria-invalid={showErrors && !!errors.land_acres}
                      onChange={(e) => { setTouched(true); setLandText(e.target.value) }}
                      className="flex-1 px-4 py-3 rounded-btn border border-gray-300 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary min-h-touch"
                    />
                    <div className="w-32 px-4 py-3 rounded-btn border border-gray-300 text-sm text-muted bg-gray-50 flex items-center">
                      {t('units.acres')}
                    </div>
                  </div>
                  {showErrors && errors.land_acres && (
                    <p role="alert" className="mt-1 text-xs text-danger">{t(errors.land_acres)}</p>
                  )}
                  {serverFieldError('land_acres')}
                </div>

                {/* Budget */}
                <div>
                  <label className="block text-sm font-semibold text-ink mb-1.5" htmlFor="budget">
                    {t('profile_page.budget_label')} <span className="text-danger">*</span>
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted text-sm pointer-events-none">₹</span>
                    <input
                      id="budget"
                      type="number"
                      min={0}
                      step={1000}
                      value={budgetText}
                      aria-invalid={showErrors && !!errors.budget_rs}
                      onChange={(e) => { setTouched(true); setBudgetText(e.target.value) }}
                      className="w-full pl-7 pr-4 py-3 rounded-btn border border-gray-300 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary min-h-touch"
                    />
                  </div>
                  {showErrors && errors.budget_rs && (
                    <p role="alert" className="mt-1 text-xs text-danger">{t(errors.budget_rs)}</p>
                  )}
                  {serverFieldError('budget_rs')}
                </div>

                {/* Water source */}
                <div>
                  <label className="block text-sm font-semibold text-ink mb-1.5" htmlFor="water">
                    {t('profile_page.water_label')} <span className="text-danger">*</span>
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-lg pointer-events-none" aria-hidden="true">💧</span>
                    <select
                      id="water"
                      value={form.water_source ?? 'borewell'}
                      onChange={(e) => {
                        const waterSource = e.target.value as WaterSource
                        patchForm({
                          water_source: waterSource,
                          canal_access: waterSource === 'canal' || waterSource === 'both',
                        })
                      }}
                      className="w-full pl-9 pr-4 py-3 rounded-btn border border-gray-300 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary min-h-touch appearance-none bg-white"
                    >
                      <option value="rainfed">{t('profile_page.water_rainfed')}</option>
                      <option value="borewell">{t('profile_page.water_borewell')}</option>
                      <option value="canal">{t('profile_page.water_canal')}</option>
                      <option value="both">{t('profile_page.water_both')}</option>
                    </select>
                  </div>
                  {serverFieldError('water_source')}
                </div>

                {(form.water_source === 'borewell' || form.water_source === 'both') && (
                  <div className="grid sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-sm font-semibold text-ink mb-1.5" htmlFor="borewell-count">
                        {t('profile_page.borewell_label')}
                      </label>
                      <input
                        id="borewell-count"
                        type="number"
                        min={1}
                        step={1}
                        value={form.borewell_count ?? ''}
                        onChange={(e) => patchForm({ borewell_count: e.target.value ? Number(e.target.value) : null })}
                        className="w-full px-3 py-3 rounded-btn border border-gray-300 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-semibold text-ink mb-1.5" htmlFor="borewell-yield">
                        {t('profile_page.borewell_yield_label', 'Yield (litres/hour)')}
                      </label>
                      <input
                        id="borewell-yield"
                        type="number"
                        min={0}
                        value={form.borewell_yield_lph ?? ''}
                        onChange={(e) => patchForm({ borewell_yield_lph: e.target.value ? Number(e.target.value) : null })}
                        className="w-full px-3 py-3 rounded-btn border border-gray-300 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-semibold text-ink mb-1.5" htmlFor="pump-hours">
                        {t('profile_page.pump_hours_label', 'Pump hours/day')}
                      </label>
                      <input
                        id="pump-hours"
                        type="number"
                        min={0}
                        max={24}
                        step={0.5}
                        value={form.pump_hours_per_day ?? ''}
                        onChange={(e) => patchForm({ pump_hours_per_day: e.target.value ? Number(e.target.value) : null })}
                        className="w-full px-3 py-3 rounded-btn border border-gray-300 text-sm"
                      />
                    </div>
                  </div>
                )}

                {/* Irrigation method */}
                <div>
                  <label className="block text-sm font-semibold text-ink mb-1.5" htmlFor="irrigation">
                    {t('profile_page.irrigation_label')} <span className="text-danger">*</span>
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-base pointer-events-none" aria-hidden="true">🚿</span>
                    <select
                      id="irrigation"
                      value={form.irrigation_method ?? 'flood'}
                      onChange={(e) => patchForm({ irrigation_method: e.target.value as IrrigationMethod })}
                      className="w-full pl-9 pr-4 py-3 rounded-btn border border-gray-300 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary min-h-touch appearance-none bg-white"
                    >
                      <option value="flood">{t('profile_page.irrigation_flood')}</option>
                      <option value="sprinkler">{t('profile_page.irrigation_sprinkler')}</option>
                      <option value="drip">{t('profile_page.irrigation_drip')}</option>
                    </select>
                  </div>
                  {serverFieldError('irrigation_method')}
                  {/* Assumption badge if this came from defaults */}
                  {profile?.defaults_used?.find((d) => d.field === 'irrigation_method') && (
                    <Badge variant="assumption" className="mt-1.5">
                      {t('profile_card.assumed')}: {profile.defaults_used.find((d) => d.field === 'irrigation_method')?.basis}
                    </Badge>
                  )}
                </div>

                {/* Risk preference slider */}
                <div>
                  <label className="block text-sm font-semibold text-ink mb-2" htmlFor="risk">
                    {t('profile_page.risk_label')} <span className="text-danger">*</span>
                  </label>
                  <div className="relative">
                    <input
                      id="risk"
                      type="range"
                      min={0}
                      max={100}
                      step={50}
                      value={riskValue}
                      onChange={(e) => {
                        const v = parseInt(e.target.value)
                        const appetite: RiskAppetite = v === 0 ? 'safe' : v === 50 ? 'balanced' : 'max_profit'
                        patchForm({ risk_appetite: appetite })
                      }}
                      className="w-full accent-primary"
                      aria-valuetext={t(`profile_page.risk_${form.risk_appetite ?? 'balanced'}`)}
                    />
                    <div className="flex justify-between text-xs text-muted mt-1">
                      <span>{t('profile_page.risk_safe')}</span>
                      <span>{t('profile_page.risk_balanced')}</span>
                      <span>{t('profile_page.risk_max')}</span>
                    </div>
                  </div>
                </div>

              </fieldset>

              {/* Save errors (field-level 422s are shown next to each field) */}
              {unmappedErrors.length > 0 && (
                <ul role="alert" className="mt-4 space-y-1 rounded-xl bg-red-50 border border-danger/20 p-4 text-sm text-danger">
                  {unmappedErrors.map(([field, message]) => (
                    <li key={field}>{message || t('profile_page.field_error_fallback')}</li>
                  ))}
                </ul>
              )}
              {saveError?.kind === 'network' && (
                <div className="mt-4">
                  <ErrorState
                    error={null}
                    isNetworkError
                    retryable
                    onRetry={() => void handleSave()}
                  />
                </div>
              )}
              {saveError?.kind === 'api' && (
                <div className="mt-4">
                  <ErrorState error={saveError.error} retryable={saveError.error.retryable} onRetry={() => void handleSave()} />
                </div>
              )}

              {/* Optimize errors: friendly, localized, never raw text */}
              {runError && (
                <div role="alert" className="mt-4 rounded-xl bg-red-50 border border-danger/20 p-4 text-sm text-ink">
                  <p className="font-medium">{t(runError.info.key)}</p>
                  {runError.info.key === 'profile_page.opt_err_validation' && runError.apiError?.user_message?.[language] && (
                    <p className="mt-1 text-muted">{runError.apiError.user_message[language]}</p>
                  )}
                  {runError.info.action === 'reload_profile' && (
                    <Button
                      className="mt-3"
                      variant="secondary"
                      size="sm"
                      loading={reloading}
                      onClick={() => void handleReloadSaved()}
                    >
                      {t('profile_page.reload_saved')}
                    </Button>
                  )}
                </div>
              )}

              {/* Save notice */}
              <div className="mt-6 p-4 bg-blue-50 rounded-xl flex items-center gap-3 text-sm text-rain">
                <span aria-hidden="true">ℹ️</span>
                <span>{t('profile_page.saving_note')}</span>
              </div>
            </div>

            {/* Save / optimize bar */}
            <div className="px-6 py-4 border-t border-gray-100 flex flex-wrap items-center justify-between gap-3">
              <div role="status" aria-live="polite" className="text-sm min-h-[1.25rem]">
                {showSavedNote && (
                  <span className="inline-flex items-center gap-1.5 text-forest font-medium">
                    <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                    {savedTime ? t('profile_page.saved_at', { time: savedTime }) : t('profile_page.saved')}
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center justify-end gap-3">
                <Button variant="secondary" onClick={handleReset} disabled={busy}>
                  {t('profile_page.reset')}
                </Button>
                <Button
                  variant={isDirty ? 'primary' : 'secondary'}
                  onClick={() => void handleSave()}
                  loading={status === 'saving'}
                  disabled={!saveEnabled}
                >
                  {t('profile_page.save')}
                </Button>
                {status === 'optimizing' && (
                  <Button variant="ghost" onClick={handleCancel}>
                    {t('profile_page.cancel')}
                  </Button>
                )}
                <Button
                  onClick={handleOptimize}
                  loading={status === 'optimizing'}
                  disabled={!optimizeState.enabled}
                  aria-describedby={optimizeState.needsSave && status !== 'optimizing' ? 'optimize-hint' : undefined}
                >
                  {status !== 'optimizing' && <Sparkles className="w-4 h-4" aria-hidden="true" />}
                  {status === 'optimizing' ? t('profile_page.optimizing') : t('profile_page.optimize')}
                </Button>
              </div>
              {optimizeState.needsSave && status !== 'optimizing' && (
                <p id="optimize-hint" className="basis-full text-right text-xs text-muted">
                  {t('profile_page.save_first')}
                </p>
              )}
            </div>
          </Card>

          {runAttempted && (
            <Card className="mt-6">
              <div className="p-6">
                <CardHeader
                  icon={<span aria-hidden="true">⚙️</span>}
                  title={t('profile_page.trace_title')}
                />
                <TraceTimeline className="mt-4" events={traceEvents} loading={status === 'optimizing'} />
              </div>
            </Card>
          )}
        </div>

        {/* ── Right: What happens next ──────────────────────────── */}
        <div className="space-y-4">
          <Card>
            <div className="p-5">
              <CardHeader icon={<span aria-hidden="true">💡</span>} title={t('profile_page.what_next')} />
              <ol className="mt-4 space-y-4">
                {[
                  t('profile_page.step1'),
                  t('profile_page.step2'),
                  t('profile_page.step3'),
                  t('profile_page.step4'),
                ].map((step, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="w-7 h-7 rounded-full bg-primary text-white text-sm font-bold flex items-center justify-center flex-shrink-0">
                      {i + 1}
                    </span>
                    <p className="text-sm text-ink leading-relaxed pt-0.5">{step}</p>
                  </li>
                ))}
              </ol>
            </div>
          </Card>

          {/* Current plan hint */}
          {plan && (
            <Card>
              <div className="p-5 text-center">
                <p className="text-sm text-muted mb-2">{t('misc.current_plan')}</p>
                <p className="font-semibold text-ink text-lg">{plan.location.district}</p>
                <p className="text-xs text-muted">{plan.season.name} · {plan.crops.length} {t('dashboard.num_crops').toLowerCase()}</p>
                <Link to="/dashboard" className="mt-3 inline-block text-sm text-primary font-medium hover:underline">
                  {t('misc.view_dashboard')}
                </Link>
              </div>
            </Card>
          )}
        </div>

      </div>
    </div>
    </div>
  )
}
