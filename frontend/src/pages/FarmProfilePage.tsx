/**
 * FarmProfilePage — view and edit farm profile.
 * Editing saves and re-runs the plan via E2 or E3.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MapPin, CheckCircle2 } from 'lucide-react'
import { Card, CardHeader } from '@/components/Card'
import { Button } from '@/components/Button'
import { Badge } from '@/components/Badge'
import { ErrorState } from '@/components/ErrorState'
import { useStore } from '@/state/store'
import { apiPost } from '@/api/client'
import type { FarmProfile, PlanResult, IrrigationMethod, WaterSource, RiskAppetite, ApiError } from '@/api/types'

export function FarmProfilePage() {
  const { t } = useTranslation()
  const { profile, plan, setProfile, setPlan } = useStore()

  const [form, setForm] = useState<Partial<FarmProfile>>(profile ?? {
    location_text: '',
    land_acres: 0,
    budget_rs: 0,
    water_source: 'borewell',
    irrigation_method: 'flood',
    risk_appetite: 'balanced',
    canal_access: false,
    borewell_count: 1,
    language: 'en',
    missing: [],
    defaults_used: [],
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [saved, setSaved] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const result = await apiPost<PlanResult>('/api/plan', form)
      setPlan(result)
      setProfile(form as FarmProfile)
      setSaved(true)
    } catch (err) {
      const apiErr = (err as { apiError?: ApiError }).apiError
      setError(apiErr ?? null)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => {
    setForm(profile ?? {})
    setError(null)
    setSaved(false)
  }

  const riskValue = form.risk_appetite === 'safe' ? 0 : form.risk_appetite === 'balanced' ? 50 : 100

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

              <div className="mt-6 space-y-5">
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
                      onChange={(e) => setForm((f) => ({ ...f, location_text: e.target.value }))}
                      placeholder="e.g. Beed, Maharashtra"
                      className="w-full pl-9 pr-4 py-3 rounded-btn border border-gray-300 text-sm text-ink placeholder-muted focus:outline-none focus:ring-2 focus:ring-primary min-h-touch"
                    />
                  </div>
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
                      value={form.land_acres ?? ''}
                      onChange={(e) => setForm((f) => ({ ...f, land_acres: parseFloat(e.target.value) || 0 }))}
                      className="flex-1 px-4 py-3 rounded-btn border border-gray-300 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary min-h-touch"
                    />
                    <div className="w-32 px-4 py-3 rounded-btn border border-gray-300 text-sm text-muted bg-gray-50 flex items-center">
                      {t('units.acres')}
                    </div>
                  </div>
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
                      value={form.budget_rs ?? ''}
                      onChange={(e) => setForm((f) => ({ ...f, budget_rs: parseInt(e.target.value) || 0 }))}
                      className="w-full pl-7 pr-4 py-3 rounded-btn border border-gray-300 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary min-h-touch"
                    />
                  </div>
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
                      onChange={(e) => setForm((f) => ({ ...f, water_source: e.target.value as WaterSource }))}
                      className="w-full pl-9 pr-4 py-3 rounded-btn border border-gray-300 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary min-h-touch appearance-none bg-white"
                    >
                      <option value="rainfed">{t('profile_page.water_rainfed')}</option>
                      <option value="borewell">{t('profile_page.water_borewell')}</option>
                      <option value="canal">{t('profile_page.water_canal')}</option>
                      <option value="both">{t('profile_page.water_both')}</option>
                    </select>
                  </div>
                </div>

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
                      onChange={(e) => setForm((f) => ({ ...f, irrigation_method: e.target.value as IrrigationMethod }))}
                      className="w-full pl-9 pr-4 py-3 rounded-btn border border-gray-300 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary min-h-touch appearance-none bg-white"
                    >
                      <option value="flood">{t('profile_page.irrigation_flood')}</option>
                      <option value="sprinkler">{t('profile_page.irrigation_sprinkler')}</option>
                      <option value="drip">{t('profile_page.irrigation_drip')}</option>
                    </select>
                  </div>
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
                        setForm((f) => ({ ...f, risk_appetite: appetite }))
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

              </div>

              {/* Error */}
              {error && (
                <div className="mt-4">
                  <ErrorState error={error} retryable={false} />
                </div>
              )}

              {/* Save notice */}
              <div className="mt-6 p-4 bg-blue-50 rounded-xl flex items-center gap-3 text-sm text-rain">
                <span aria-hidden="true">ℹ️</span>
                <span>{t('profile_page.saving_note')}</span>
              </div>
            </div>

            {/* Save / reset bar */}
            <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-end gap-3">
              <Button variant="secondary" onClick={handleReset} disabled={saving}>
                {t('profile_page.reset')}
              </Button>
              <Button onClick={() => void handleSave()} loading={saving}>
                {saved && <CheckCircle2 className="w-4 h-4" aria-hidden="true" />}
                {t('profile_page.save')}
              </Button>
            </div>
          </Card>
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
