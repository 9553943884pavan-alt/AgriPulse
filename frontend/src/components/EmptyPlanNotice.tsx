/**
 * Shown instead of charts/gauges when the optimizer returned no allocation
 * (e.g. infeasibility.suggestion_code = "NO_POSITIVE_ALLOCATION"). Lists the
 * evaluated crops with their real profit so the farmer sees why.
 */

import { useTranslation } from 'react-i18next'
import { Card, CardHeader } from '@/components/Card'
import { MoneyText } from '@/components/MoneyText'
import { SourceBadge } from '@/components/SourceBadge'
import { getCropEmoji } from '@/utils/cropEmoji'
import type { Language, PlanResult, ScenarioId } from '@/api/types'

export function isEmptyPlan(plan: PlanResult): boolean {
  return (
    // Traditional is a comparison baseline and may contain allocations even
    // when every optimized recommendation is empty. It must not make the UI
    // look as if an actionable crop plan was generated.
    !plan.strategies.some(
      (strategy) => strategy.id !== 'traditional' && (strategy.allocations ?? []).length > 0,
    )
  )
}

export function PlanWarnings({ plan }: { plan: PlanResult }) {
  const { t } = useTranslation()
  if (plan.warnings.length === 0) return null
  return (
    <div className="space-y-2">
      {plan.warnings.map((w, i) => (
        <div key={i} className="flex items-start gap-3 bg-orange-50 border border-drought/20 rounded-xl px-4 py-3 text-sm text-drought">
          <span aria-hidden="true">⚠️</span>
          <span>{t(`warning_codes.${w.code}`, w.params as Record<string, string>)}</span>
        </div>
      ))}
    </div>
  )
}

interface Props {
  plan: PlanResult
  scenario: ScenarioId
  lang: Language
}

export function EmptyPlanNotice({ plan, scenario, lang }: Props) {
  const { t } = useTranslation()
  const code = plan.infeasibility?.suggestion_code ?? null
  const reasonKey = code && code === 'NO_POSITIVE_ALLOCATION'
    ? 'empty_plan.reason_no_positive_allocation'
    : 'empty_plan.reason_generic'

  return (
    <div className="space-y-4">
      <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-4 text-amber-900">
        <p className="font-semibold">{t('empty_plan.title')}</p>
        <p className="text-sm mt-1">{t(reasonKey)}</p>
      </div>

      {plan.crops.length > 0 && (
        <Card>
          <div className="p-5">
            <CardHeader icon={<span aria-hidden="true">🌾</span>} title={t('empty_plan.crops_title')} />
            <ul className="mt-3 divide-y divide-sage-mist/60">
              {plan.crops.map((crop) => {
                const profit = crop.profit_rs_per_acre[scenario]
                const yieldQ = crop.yield_quintal_per_acre[scenario]
                const revenue = crop.revenue_rs_per_acre?.[scenario]
                  ?? profit + crop.cost_per_acre.total_rs
                return (
                  <li key={crop.crop_id} className="py-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span>{getCropEmoji(crop.crop_id)} {crop.names[lang] ?? crop.crop_id}</span>
                      <span className={profit < 0 ? 'text-danger font-semibold' : 'font-semibold'}>
                        <MoneyText value={profit} /> {t('empty_plan.per_acre')}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
                      <span>Yield {yieldQ.toFixed(1)} quintal/acre</span>
                      <span className="inline-flex items-center gap-1">
                        Harvest price {'₹'}{Math.round(crop.expected_harvest_price.value).toLocaleString('en-IN')}/quintal
                        <SourceBadge sourced={crop.expected_harvest_price} compact />
                      </span>
                      <span>Revenue {'₹'}{Math.round(revenue).toLocaleString('en-IN')}/acre</span>
                      <span className="inline-flex items-center gap-1">
                        Cost {'₹'}{Math.round(crop.cost_per_acre.total_rs).toLocaleString('en-IN')}/acre
                        <SourceBadge sourced={{ value: crop.cost_per_acre.total_rs, unit: 'rs/acre', source: crop.cost_per_acre.source, as_of: crop.cost_per_acre.reference_year, status: crop.cost_per_acre.status }} compact />
                      </span>
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        </Card>
      )}

      {plan.excluded_crops.length > 0 && (
        <Card>
          <div className="p-5">
            <CardHeader icon={<span aria-hidden="true">⚠️</span>} title={t('dashboard.excluded')} />
            <ul className="mt-3 space-y-1">
              {plan.excluded_crops.map((exc) => (
                <li key={exc.crop_id} className="text-sm text-muted">
                  {t(`excluded_reasons.${exc.reason_code}`, { crop_id: exc.crop_id, ...exc.params })}
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}

      <PlanWarnings plan={plan} />
    </div>
  )
}
