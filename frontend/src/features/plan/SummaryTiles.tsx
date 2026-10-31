/**
 * SummaryTiles — Detailed impact and performance tiles.
 * Designed to match the rich card style of Plan Preview:
 * full readable numbers, comparison pills, clear source indicators, and no awkward truncation.
 */

import { TrendingUp, TrendingDown, Wheat, Droplets, Leaf, IndianRupee, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { PlanResult, ScenarioId } from '@/api/types'
import { SourceBadge } from '@/components/SourceBadge'
import { SummaryTileSkeleton } from '@/components/Skeleton'

interface SummaryTilesProps {
  plan: PlanResult | null
  scenario: ScenarioId
  loading?: boolean
  compact?: boolean
}

export function SummaryTiles({ plan, scenario, loading, compact = false }: SummaryTilesProps) {
  const { t } = useTranslation()

  if (loading || !plan) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3.5">
        {[1, 2, 3, 4].map((i) => <SummaryTileSkeleton key={i} />)}
      </div>
    )
  }

  const recommended = plan.strategies.find((s) => s.id === plan.recommended_strategy)
  const traditional = plan.strategies.find((s) => s.id === 'traditional')

  const expectedProfit = recommended?.profit_by_scenario_rs[scenario] ?? 0
  const tradProfit = traditional?.profit_by_scenario_rs[scenario] ?? 0
  const profitDeltaPct = tradProfit > 0 ? Math.round(((expectedProfit - tradProfit) / tradProfit) * 100) : null
  const profitDeltaRs = expectedProfit - tradProfit

  const waterNeedM3 = plan.water.need_m3.recommended_plan.value
  const tradWaterM3 = plan.water.need_m3.traditional_plan.value
  const waterDeltaPct = tradWaterM3 > 0 ? Math.round(((waterNeedM3 - tradWaterM3) / tradWaterM3) * 100) : null

  const cropCount = recommended?.allocations.length ?? plan.crops.length
  const waterLitres = waterNeedM3 * 1000
  const waterLakhL = (waterLitres / 100_000).toFixed(1)

  const tiles = [
    {
      id: 'profit',
      icon: <IndianRupee className="w-5 h-5 text-[#C89326]" strokeWidth={2.4} aria-hidden="true" />,
      iconBg: 'bg-sunrise-gold/25 border border-sunrise-gold/40',
      label: t('dashboard.estimated_profit'),
      value: `₹${Math.round(expectedProfit).toLocaleString('en-IN')}`,
      unit: '',
      subtext: profitDeltaRs > 0
        ? `+₹${Math.round(profitDeltaRs).toLocaleString('en-IN')} gain vs traditional`
        : 'Projected net farm income',
      delta: profitDeltaPct !== null ? {
        text: profitDeltaPct > 0 ? `+${profitDeltaPct}% vs traditional` : `${profitDeltaPct}% vs traditional`,
        positive: profitDeltaPct >= 0,
        neutral: profitDeltaPct === 0,
      } : null,
      sourceName: 'Agmarknet & CEDA',
      sourced: plan.impact?.drought_profit_gain_rs ?? plan.water.need_m3.recommended_plan,
    },
    {
      id: 'land',
      icon: <Wheat className="w-5 h-5 text-forest" strokeWidth={2.2} aria-hidden="true" />,
      iconBg: 'bg-sage-mist/70 border border-sage-mist',
      label: t('dashboard.crop_area'),
      value: `${plan.profile.land_acres}`,
      unit: t('units.acres'),
      subtext: '100% of registered acreage allocated',
      delta: {
        text: 'Optimal Multi-Crop Plot',
        positive: true,
        neutral: false,
      },
      sourceName: 'Farmer Profile',
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
      id: 'water',
      icon: <Droplets className="w-5 h-5 text-blue-600" strokeWidth={2.2} aria-hidden="true" />,
      iconBg: 'bg-blue-50 border border-blue-200 text-blue-600',
      label: t('dashboard.water_req'),
      value: `${waterLakhL}`,
      unit: t('misc.lakh_l'),
      subtext: `${Math.round(waterNeedM3).toLocaleString('en-IN')} m³ total consumption`,
      delta: waterDeltaPct !== null ? {
        text: waterDeltaPct < 0
          ? `${Math.abs(waterDeltaPct)}% Water Saved`
          : waterDeltaPct === 0
            ? 'Optimal baseline'
            : `+${waterDeltaPct}% water needed`,
        positive: waterDeltaPct <= 0,
        neutral: waterDeltaPct === 0,
      } : null,
      sourceName: 'FAO-56 & CGWB',
      sourced: plan.water.need_m3.recommended_plan,
    },
    {
      id: 'crops',
      icon: <Leaf className="w-5 h-5 text-fresh-leaf" strokeWidth={2.2} aria-hidden="true" />,
      iconBg: 'bg-fresh-leaf/15 border border-fresh-leaf/30',
      label: t('dashboard.num_crops'),
      value: `${cropCount}`,
      unit: 'Recommended',
      subtext: 'Hedged against rainfall and price dips',
      delta: {
        text: 'Risk-Diversified',
        positive: true,
        neutral: false,
      },
      sourceName: 'QP Optimizer',
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
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3.5">
      {tiles.map((tile) => (
        <div
          key={tile.id}
          className="bg-[#FAFFF8] rounded-xl p-3.5 border border-sage-mist/80 shadow-xs flex flex-col justify-between transition-all hover:shadow-md hover:border-sage-mist"
        >
          {/* Top Row: Icon + Source Pill */}
          <div className="flex items-center justify-between gap-2 mb-2.5">
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${tile.iconBg}`}>
              {tile.icon}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-medium text-muted bg-white border border-sage-mist/80 px-2 py-0.5 rounded-full shadow-2xs">
                {tile.sourceName}
              </span>
              <SourceBadge sourced={tile.sourced} compact />
            </div>
          </div>

          {/* Middle: Label & Full Readable Metric */}
          <div className="mb-2">
            <p className="text-xs font-semibold text-muted leading-tight mb-1">
              {tile.label}
            </p>
            <div className="flex items-baseline gap-1.5 flex-wrap">
              <span className="text-xl font-extrabold text-ink tracking-tight font-tabular-nums">
                {tile.value}
              </span>
              {tile.unit && (
                <span className="text-xs font-semibold text-muted">
                  {tile.unit}
                </span>
              )}
            </div>
          </div>

          {/* Bottom: Comparison Delta Pill & Subtext */}
          <div className="pt-2 border-t border-sage-mist/50 flex flex-col gap-1">
            {tile.delta && (
              <div
                className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-md w-fit ${
                  tile.delta.neutral
                    ? 'bg-gray-100 text-muted'
                    : tile.delta.positive
                      ? 'bg-fresh-leaf/10 text-fresh-leaf border border-fresh-leaf/25'
                      : 'bg-red-50 text-danger border border-red-200'
                }`}
              >
                {tile.delta.positive && !tile.delta.neutral ? (
                  <TrendingUp className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
                ) : !tile.delta.neutral ? (
                  <TrendingDown className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
                ) : (
                  <ShieldCheck className="w-3 h-3 flex-shrink-0 text-muted" aria-hidden="true" />
                )}
                <span>{tile.delta.text}</span>
              </div>
            )}
            <p className="text-[10px] text-muted leading-tight mt-0.5">
              {tile.subtext}
            </p>
          </div>
        </div>
      ))}
    </div>
  )
}
