/**
 * SummaryTiles — 4 summary tiles on Dashboard and Home preview.
 * Each tile has a SourceBadge. No bare numbers.
 */

import { TrendingUp, TrendingDown, Wheat, Droplets, Leaf } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { PlanResult, ScenarioId } from '@/api/types'
import { MoneyText } from '@/components/MoneyText'
import { SourceBadge } from '@/components/SourceBadge'
import { SummaryTileSkeleton } from '@/components/Skeleton'

interface SummaryTilesProps {
  plan: PlanResult | null
  scenario: ScenarioId
  loading?: boolean
  compact?: boolean   // Home preview = compact
}

export function SummaryTiles({ plan, scenario, loading, compact = false }: SummaryTilesProps) {
  const { t } = useTranslation()

  if (loading || !plan) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => <SummaryTileSkeleton key={i} />)}
      </div>
    )
  }

  const recommended = plan.strategies.find((s) => s.id === plan.recommended_strategy)
  const traditional = plan.strategies.find((s) => s.id === 'traditional')

  const expectedProfit = recommended?.profit_by_scenario_rs[scenario] ?? 0
  const tradProfit = traditional?.profit_by_scenario_rs[scenario] ?? 0
  const profitDeltaPct = tradProfit > 0 ? Math.round(((expectedProfit - tradProfit) / tradProfit) * 100) : null

  const waterNeedM3 = plan.water.need_m3.recommended_plan.value
  const tradWaterM3 = plan.water.need_m3.traditional_plan.value
  const waterDeltaPct = tradWaterM3 > 0 ? Math.round(((waterNeedM3 - tradWaterM3) / tradWaterM3) * 100) : null

  const cropCount = recommended?.allocations.length ?? 0

  // Format water as "X.X lakh L" to keep the tile compact
  const waterLitres = waterNeedM3 * 1000
  const waterLakhL = (waterLitres / 100_000).toFixed(1)

  const tiles = [
    {
      icon: <span className="text-xl font-bold">₹</span>,
      iconBg: 'bg-amber-100',
      label: t('dashboard.estimated_profit'),
      value: <MoneyText value={expectedProfit} className="text-lg font-bold text-ink leading-tight" />,
      delta: profitDeltaPct !== null ? {
        pct: profitDeltaPct,
        positive: profitDeltaPct > 0,
      } : null,
      sourced: plan.impact?.drought_profit_gain_rs ?? plan.water.need_m3.recommended_plan,
    },
    {
      icon: <Wheat className="w-5 h-5 text-primary" aria-hidden="true" />,
      iconBg: 'bg-primary-soft',
      label: t('dashboard.crop_area'),
      value: (
        <span className="text-lg font-bold text-ink leading-tight">
          {plan.profile.land_acres} <span className="text-sm font-semibold">{t('units.acres')}</span>
        </span>
      ),
      delta: null,
      sourced: {
        value: plan.profile.land_acres,
        unit: 'acres',
        source: 'farmer_input',
        source_url: '',
        as_of: '',
        status: 'farmer_input' as const,
      },
    },
    {
      icon: <Droplets className="w-5 h-5 text-rain" aria-hidden="true" />,
      iconBg: 'bg-blue-100',
      label: t('dashboard.water_req'),
      value: (
        <span className="text-lg font-bold text-ink leading-tight">
          {waterLakhL} <span className="text-sm font-semibold">{t('misc.lakh_l')}</span>
        </span>
      ),
      delta: waterDeltaPct !== null ? {
        pct: waterDeltaPct,
        positive: waterDeltaPct < 0,
      } : null,
      sourced: plan.water.need_m3.recommended_plan,
    },
    {
      icon: <Leaf className="w-5 h-5 text-primary" aria-hidden="true" />,
      iconBg: 'bg-primary-soft',
      label: t('dashboard.num_crops'),
      value: (
        <span className="text-lg font-bold text-ink leading-tight">
          {cropCount} <span className="text-sm font-semibold">{t('dashboard.num_crops').toLowerCase()}</span>
        </span>
      ),
      delta: null,
      sourced: {
        value: cropCount,
        unit: 'count',
        source: 'computed from recommended strategy',
        source_url: '',
        as_of: plan.created_at,
        status: 'computed' as const,
      },
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {tiles.map((tile, i) => (
        <div key={i} className="bg-surface rounded-card shadow-card p-4 flex flex-col gap-2 min-w-0">
          <div className="flex items-start justify-between gap-1">
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${tile.iconBg}`}>
              {tile.icon}
            </div>
            <SourceBadge sourced={tile.sourced} compact />
          </div>

          <div className="min-w-0">
            <p className="text-[11px] text-muted font-medium mb-1 line-clamp-2 leading-tight">{tile.label}</p>
            <div className="truncate">{tile.value}</div>
          </div>

          {tile.delta && (
            <div className={`flex items-center gap-1 text-xs font-medium flex-wrap ${tile.delta.positive ? 'text-primary' : 'text-danger'}`}>
              {tile.delta.positive ? (
                <TrendingUp className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
              ) : (
                <TrendingDown className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
              )}
              <span>{Math.abs(tile.delta.pct)}% {t('dashboard.vs_traditional')}</span>
            </div>
          )}

          {!compact && (
            <p className="text-xs text-primary flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-badge-live inline-block flex-shrink-0" aria-hidden="true" />
              {t('misc.live_data')}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}
