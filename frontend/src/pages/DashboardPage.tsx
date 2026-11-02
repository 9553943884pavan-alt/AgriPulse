/**
 * DashboardPage — full plan view with charts, crop cards, map.
 * Charts load via lazy imports (route-level code split).
 */

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useStore } from '@/state/store'
import { SummaryTiles } from '@/features/plan/SummaryTiles'
import { FinancialSummary } from '@/features/plan/FinancialSummary'
import { StalePlanNotice } from '@/components/StalePlanNotice'
import { ScenarioToggle } from '@/components/ScenarioToggle'
import { SourceBadge } from '@/components/SourceBadge'
import { MoneyText } from '@/components/MoneyText'
import { QuintalText } from '@/components/QuintalText'
import { Badge } from '@/components/Badge'
import { Card, CardHeader } from '@/components/Card'
import { EmptyPlanNotice, PlanWarnings, isEmptyPlan } from '@/components/EmptyPlanNotice'
import { DistrictMap } from '@/features/districts/DistrictMap'
import type { Language } from '@/api/types'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import { getCropEmoji } from '@/utils/cropEmoji'

// Strategy colors — fixed everywhere
const STRATEGY_COLORS: Record<string, string> = {
  traditional:    '#78909C',
  lp_max_profit:  '#1E88E5',
  qp_balanced:    '#2E7D32',
  qp_drought_safe:'#00897B',
}

// Crop allocation slice palette — green/blue/teal/orange
const ALLOC_COLORS = ['#78909C', '#1E88E5', '#2E7D32', '#FB8C00', '#00897B', '#8E24AA']

// Cost stacked bar palette — matches reference: seed=green, fertilizer=amber, labour=blue, irrigation=orange, other=purple
const COST_COLORS = ['#43A047', '#FBC02D', '#1E88E5', '#FB8C00', '#8E24AA']
const COST_KEYS   = ['seed', 'fertilizer', 'labour', 'irrigation', 'other'] as const

export function DashboardPage() {
  const { t } = useTranslation()
  const { plan, selectedScenario, selectedStrategy, language } = useStore()
  const lang = language as Language

  if (!plan) {
    return (
      <div className="max-w-6xl mx-auto px-4 lg:px-6 py-6 flex flex-col items-center justify-center gap-4 min-h-64">
        <span className="text-5xl" aria-hidden="true">🌾</span>
        <p className="text-muted text-center">{t('misc.no_plan_home')}</p>
        <Link to="/" className="text-primary font-medium hover:underline">{t('misc.go_home')}</Link>
      </div>
    )
  }

  if (isEmptyPlan(plan)) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="max-w-6xl mx-auto px-4 lg:px-6 py-6 space-y-4">
          <h1 className="text-2xl font-bold text-ink">{t('dashboard.title')}</h1>
          <ScenarioToggle scenarios={['normal', 'drought', 'excess']} />
          <EmptyPlanNotice plan={plan} scenario={selectedScenario} lang={lang} />
        </div>
      </div>
    )
  }

  const recommended = plan.strategies.find((s) => s.id === plan.recommended_strategy)
  const activeStrategy = plan.strategies.find((s) => s.id === (selectedStrategy ?? plan.recommended_strategy)) ?? recommended
  const activeWater = plan.water.find((budget) => budget.scenario === selectedScenario)

  if (!activeWater) {
    return (
      <div role="alert" className="max-w-6xl mx-auto px-4 py-8 text-center text-danger">
        {t('errors.water_budget_missing', 'The selected scenario has no water budget. Please generate the plan again.')}
        <Link to="/" className="ml-2 font-medium text-primary underline">{t('misc.go_home')}</Link>
      </div>
    )
  }

  // Donut chart data
  const donutData = (activeStrategy?.allocations ?? []).map((a) => {
    const crop = plan.crops.find((c) => c.crop_id === a.crop_id)
    return { name: crop?.names[lang] ?? a.crop_id, value: a.acres }
  })

  // Strategy comparison bar data
  const strategyBarData = plan.strategies.map((s) => ({
    name: t(`strategies.${s.id}`),
    profit: s.profit_by_scenario_rs[selectedScenario],
    water: Math.round(s.totals.water_m3 / 1000),
    color: STRATEGY_COLORS[s.id] ?? '#78909C',
    recommended: s.id === plan.recommended_strategy,
  }))

  // Cost breakdown stacked bar data
  const costData: Array<{ name: string; seed: number; fertilizer: number; labour: number; irrigation: number; other: number }> = (activeStrategy?.allocations ?? []).map((a) => {
    const crop = plan.crops.find((c) => c.crop_id === a.crop_id)
    const c = crop?.cost_per_acre
    return {
      name: crop?.names[lang] ?? a.crop_id,
      seed: (c?.seed ?? 0) * a.acres,
      fertilizer: (c?.fertilizer ?? 0) * a.acres,
      labour: (c?.labour ?? 0) * a.acres,
      irrigation: (c?.irrigation ?? 0) * a.acres,
      other: ((c?.manure ?? 0) + (c?.machine ?? 0) + (c?.pesticide ?? 0)) * a.acres,
    }
  })

  // Water gauge data
  const waterAvail = activeWater.available_m3
  const waterGaugeData = [
    { name: 'Rain', value: waterAvail.rain.value, fill: '#1565C0' },
    { name: 'Groundwater', value: waterAvail.groundwater.value, fill: '#2E7D32' },
    { name: 'Canal', value: waterAvail.canal.value, fill: '#F9A825' },
  ].filter((d) => d.value > 0)

  return (
    <div className="h-full overflow-y-auto" style={{ scrollbarWidth: 'thin', scrollbarColor: '#86efac transparent' }}>
    <div className="max-w-6xl mx-auto px-4 lg:px-6 py-6 space-y-6">

      <StalePlanNotice />

      {/* Page header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-primary-soft flex items-center justify-center">
            <span className="text-xl" aria-hidden="true">📊</span>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-ink">{t('dashboard.title')}</h1>
            <p className="text-sm text-muted">{t('dashboard.subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <ScenarioToggle scenarios={['normal', 'drought', 'excess']} />
        </div>
      </div>

      {(activeStrategy?.allocations ?? []).length === 0 && (
        <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          The selected strategy found no profitable crop allocation for this farm. Choose another strategy to see a crop plan.
        </div>
      )}

      {/* Summary tiles */}
      <SummaryTiles plan={plan} scenario={selectedScenario} />

      {/* Values are derived from allocation-level optimizer inputs. The card
          reports unavailable rather than synthesising revenue or ROI. */}
      <FinancialSummary
        strategy={activeStrategy}
        crops={plan.crops}
        scenario={selectedScenario}
        createdAt={plan.created_at}
      />

      {/* ── Analytics grid ── */}
      <div className="grid lg:grid-cols-2 gap-6">

        {/* ── 1. Crop Allocation — doughnut + side legend ── */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-start justify-between mb-1">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-xl bg-green-50 flex items-center justify-center text-lg">🌿</div>
              <div>
                <h2 className="font-bold text-[15px] text-gray-800">{t('dashboard.crop_allocation')}</h2>
                <p className="text-xs text-gray-400">{t('dashboard.subtitle')}</p>
              </div>
            </div>
            <div className="flex items-center gap-1 bg-green-50 rounded-lg px-3 py-1.5 text-xs font-semibold text-green-700">
              🌾 {t('units.total_area')} {activeStrategy?.totals?.land_used_acres ?? (activeStrategy?.allocations ?? []).reduce((s, a) => s + a.acres, 0)} {t('units.acres')}
            </div>
          </div>

          <div className="flex items-center gap-2 mt-3">
            {/* Doughnut */}
            <div className="w-44 h-44 flex-shrink-0 relative">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={donutData}
                    cx="50%" cy="50%"
                    innerRadius={48} outerRadius={72}
                    dataKey="value"
                    startAngle={90} endAngle={-270}
                    label={false} labelLine={false}
                    stroke="none"
                  >
                    {donutData.map((_, i) => (
                      <Cell key={i} fill={ALLOC_COLORS[i % ALLOC_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: any, name: any) => [`${v} ac`, name]}
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                  />
                </PieChart>
              </ResponsiveContainer>
              {/* Centre label */}
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-xl font-bold text-gray-800">
                  {(activeStrategy?.allocations ?? []).reduce((s, a) => s + a.acres, 0)}
                </span>
                <span className="text-xs text-gray-400">{t('units.acres')}</span>
              </div>
            </div>

            {/* Side crop rows */}
            <div className="flex-1 space-y-2 min-w-0">
              {donutData.map((d, i) => {
                const total = donutData.reduce((s, x) => s + x.value, 0)
                const pct   = total > 0 ? Math.round((d.value / total) * 100) : 0
                const color = ALLOC_COLORS[i % ALLOC_COLORS.length]
                const cropId = activeStrategy?.allocations[i]?.crop_id ?? ''
                return (
                  <div key={d.name} className="flex items-center gap-2">
                    <span className="text-base w-6 text-center flex-shrink-0">{getCropEmoji(cropId)}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-center">
                        <span className="text-xs font-semibold text-gray-700 truncate">{d.name}</span>
                        <span className="text-xs font-bold ml-1" style={{ color }}>{pct}%</span>
                      </div>
                      <p className="text-[10px] text-gray-400 mb-0.5">{d.value} {t('units.acres')}</p>
                      <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* ── 2. Expected Profit — bar chart ── */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-start justify-between mb-1">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center text-lg">📈</div>
              <div>
                <h2 className="font-bold text-[15px] text-gray-800">{t('dashboard.expected_profit')}</h2>
                <p className="text-xs text-gray-400">{t('dashboard.profit_subtitle', 'Comparison across strategies')}</p>
              </div>
            </div>
          </div>

          <div className="mt-3 h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={strategyBarData} margin={{ top: 20, right: 8, left: 4, bottom: 0 }} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                <Tooltip
                  formatter={(v: any) => [`₹${(v as number).toLocaleString('en-IN')}`, t('dashboard.expected_profit')]}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                  cursor={{ fill: '#f9fafb' }}
                />
                <Bar dataKey="profit" radius={[6, 6, 0, 0]}
                  label={{ position: 'top', fontSize: 11, fill: '#374151', formatter: (v: number) => `₹${(v / 1000).toFixed(0)}k` }}
                >
                  {strategyBarData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Best strategy insight */}
          {(() => {
            const best = [...strategyBarData].sort((a, b) => b.profit - a.profit)[0]
            const base = strategyBarData.find(s => s.name === t('strategies.traditional'))
            const uplift = base && base.profit > 0 ? Math.round(((best.profit - base.profit) / base.profit) * 100) : null
            return (
              <div className="mt-3 flex items-start gap-2 bg-green-50 rounded-xl px-3 py-2">
                <span className="text-green-600 text-sm mt-0.5">📈</span>
                <p className="text-xs text-green-800">
                  <span className="font-semibold">{best.name}</span> {t('dashboard.gives_highest_profit', 'gives the highest expected profit')}
                  {uplift !== null && uplift > 0 && `, ~${uplift}% ${t('dashboard.higher_than_traditional', 'higher than traditional')}.`}
                </p>
              </div>
            )
          })()}
        </div>

        {/* ── 3. Water Budget — semi-circle gauge + stats ── */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center text-lg">💧</div>
            <div>
              <h2 className="font-bold text-[15px] text-gray-800">{t('misc.water_budget')}</h2>
              <p className="text-xs text-gray-400">{t('dashboard.water_subtitle', 'Available sources vs plan requirement')}</p>
            </div>
          </div>

          <div className="flex items-center gap-4 mt-3">
            {/* Semi-circle gauge via PieChart startAngle/endAngle */}
            <div className="relative w-40 h-24 flex-shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                  {/* Background track */}
                  <Pie
                    data={[{ value: 1 }]}
                    cx="50%" cy="100%"
                    startAngle={180} endAngle={0}
                    innerRadius={48} outerRadius={62}
                    dataKey="value" stroke="none"
                  >
                    <Cell fill="#F3F4F6" />
                  </Pie>
                  {/* Filled arc — proportional to available/max */}
                  <Pie
                    data={waterGaugeData}
                    cx="50%" cy="100%"
                    startAngle={180} endAngle={0}
                    innerRadius={48} outerRadius={62}
                    dataKey="value" stroke="none"
                    label={false} labelLine={false}
                  >
                    {waterGaugeData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: any, name: any) => {
                      const lakh = ((v as number) * 1000) / 100000
                      return [`${lakh.toFixed(1)} lakh L`, name]
                    }}
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                  />
                </PieChart>
              </ResponsiveContainer>
              {/* Centre number */}
              <div className="absolute bottom-0 left-0 right-0 flex flex-col items-center">
                <span className="text-base font-bold text-gray-800 leading-none">
                  {((activeWater.available_m3.total.value * 1000) / 100000).toFixed(1)}
                </span>
                <span className="text-[10px] text-gray-400">lakh L</span>
              </div>
            </div>

            {/* Stats column */}
            <div className="flex-1 space-y-2">
              <div className="bg-blue-50 rounded-xl px-3 py-2">
                <p className="text-[10px] text-blue-500 font-medium">{t('dashboard.total_requirement', 'Total Requirement')}</p>
                <p className="text-sm font-bold text-gray-800">
                  {((activeWater.need_m3.recommended_plan.value * 1000) / 100000).toFixed(1)} lakh L
                </p>
              </div>
              <div className="bg-green-50 rounded-xl px-3 py-2">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[10px] text-green-600 font-medium">{t('dashboard.available_water', 'Available Water')}</p>
                    <p className="text-sm font-bold text-gray-800">
                      {((activeWater.available_m3.total.value * 1000) / 100000).toFixed(1)} lakh L
                    </p>
                  </div>
                  {(() => {
                    const need  = activeWater.need_m3.recommended_plan.value
                    const avail = activeWater.available_m3.total.value
                    const pct   = need > 0 ? Math.round((avail / need) * 100) : 0
                    return (
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${pct >= 100 ? 'bg-green-200 text-green-800' : 'bg-orange-200 text-orange-800'}`}>
                        {pct}%
                      </span>
                    )
                  })()}
                </div>
              </div>
              {(() => {
                const surplus = activeWater.available_m3.total.value - activeWater.need_m3.recommended_plan.value
                return surplus > 0 ? (
                  <div className="bg-teal-50 rounded-xl px-3 py-2">
                    <p className="text-[10px] text-teal-600 font-medium">{t('dashboard.surplus', 'Surplus')}</p>
                    <p className="text-sm font-bold text-teal-700">
                      {((surplus * 1000) / 100000).toFixed(1)} lakh L
                    </p>
                  </div>
                ) : null
              })()}
            </div>
          </div>

          {/* Source dots */}
          <div className="flex items-center gap-4 mt-3 flex-wrap">
            {waterGaugeData.map((d) => (
              <span key={d.name} className="flex items-center gap-1.5 text-xs text-gray-500">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: d.fill }} />
                {d.name} {((d.value * 1000) / 100000).toFixed(1)} lakh L
              </span>
            ))}
          </div>

          {/* Info note */}
          {(() => {
            const surplus = activeWater.available_m3.total.value - activeWater.need_m3.recommended_plan.value
            return (
              <div className="mt-3 flex items-start gap-2 bg-blue-50 rounded-xl px-3 py-2">
                <span className="text-blue-500 text-sm mt-0.5">ℹ️</span>
                <p className="text-xs text-blue-700">
                  {surplus >= 0
                    ? `${t('dashboard.water_sufficient', 'Available water is sufficient for the selected plan.')} ${t('dashboard.water_surplus', 'You have a surplus of')} ${((surplus * 1000) / 100000).toFixed(1)} lakh L.`
                    : t('dashboard.water_deficit', 'Available water may not be sufficient for the selected plan.')
                  }
                </p>
              </div>
            )
          })()}

          <div className="flex gap-2 mt-2 flex-wrap">
            <SourceBadge sourced={activeWater.basis.category_cap} compact />
            <SourceBadge sourced={activeWater.basis.effective_rain_factor} compact />
          </div>
        </div>

        {/* ── 4. Cost Breakdown — stacked bar ── */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-9 h-9 rounded-xl bg-amber-50 flex items-center justify-center text-lg">💰</div>
            <div>
              <h2 className="font-bold text-[15px] text-gray-800">
                {t('misc.cost_breakdown_label', { title: t('dashboard.cost_breakdown') })}
              </h2>
              <p className="text-xs text-gray-400">{t('dashboard.cost_subtitle', 'Estimated cost per crop for the selected plan')}</p>
            </div>
          </div>

          <div className="flex gap-2 mt-3">
            <div className="flex-1 h-52">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={costData} margin={{ top: 20, right: 4, left: 4, bottom: 0 }} barCategoryGap="30%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                  <YAxis tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(v: any, name: any) => [`₹${(v as number).toLocaleString('en-IN')}`, name]}
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                    cursor={{ fill: '#f9fafb' }}
                  />
                  {COST_KEYS.map((key, i) => (
                    <Bar
                      key={key}
                      dataKey={key}
                      stackId="a"
                      fill={COST_COLORS[i]}
                      radius={i === COST_KEYS.length - 1 ? [4, 4, 0, 0] : undefined}
                      label={i === COST_KEYS.length - 1
                        ? { position: 'top', fontSize: 11, fill: '#374151', formatter: (_value: number, _: any, index: number) => {
                            const row = costData[index]
                            if (!row) return ''
                            const total = COST_KEYS.reduce((s, k) => s + (row[k] ?? 0), 0)
                            return `₹${(total / 1000).toFixed(0)}k`
                          }}
                        : false
                      }
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Custom legend — right side */}
            <div className="flex flex-col justify-center gap-1.5 text-xs text-gray-600 w-28 flex-shrink-0">
              {COST_KEYS.map((key, i) => {
                const total = costData.reduce((s, row) => s + (row[key] ?? 0), 0)
                return (
                  <div key={key} className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: COST_COLORS[i] }} />
                    <span className="capitalize truncate">{key === 'other' ? 'Others' : key.charAt(0).toUpperCase() + key.slice(1)}</span>
                    <span className="ml-auto font-semibold text-gray-700">₹{(total / 1000).toFixed(0)}k</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Insight note */}
          {costData.length > 0 && (() => {
            const totals = costData.map(row => ({
              name: row.name,
              total: COST_KEYS.reduce((s, k) => s + (row[k] ?? 0), 0),
            }))
            const max = totals.sort((a, b) => b.total - a.total)[0]
            return (
              <div className="mt-3 flex items-start gap-2 bg-amber-50 rounded-xl px-3 py-2">
                <span className="text-amber-500 text-sm mt-0.5">💡</span>
                <p className="text-xs text-amber-800">
                  <span className="font-semibold">{max.name}</span> {t('dashboard.highest_cost_crop', 'has the highest cost due to higher labour and input requirements.')} {t('dashboard.cost_reference', 'Costs are based on 2022-23 (DES/CACP).')}
                </p>
              </div>
            )
          })()}
        </div>
      </div>

      {/* Crop cards */}
      <div>
        <h2 className="text-lg font-semibold text-ink mb-4">{t('dashboard.top_crops')}</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {plan.crops.map((crop) => {
            const alloc = activeStrategy?.allocations.find((a) => a.crop_id === crop.crop_id)
            return (
              <Card key={crop.crop_id}>
                <div className="p-5 space-y-3">
                  {/* Header */}
                  <div className="flex items-start gap-3">
                    <div className="w-14 h-14 rounded-xl bg-primary-soft flex items-center justify-center text-2xl flex-shrink-0">
                      {getCropEmoji(crop.crop_id)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-ink truncate">{crop.names[lang]}</p>
                      <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                        <Badge variant={crop.suitability.label === 'good' ? 'success' : crop.suitability.label === 'average' ? 'warning' : 'danger'}>
                          {t(`suitability.${crop.suitability.label}`)}
                        </Badge>
                        {alloc && (
                          <span className="text-xs text-muted">{alloc.acres} {t('units.acres')}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Yield + price */}
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <p className="text-xs text-muted">{t('misc.yield_label')}</p>
                      <QuintalText quintals={crop.yield_quintal_per_acre[selectedScenario]} />
                      <SourceBadge sourced={{ value: crop.yield_quintal_per_acre[selectedScenario], unit: 'quintal/acre', source: 'model', source_url: '', as_of: '', status: 'model' }} compact />
                    </div>
                    <div>
                      <p className="text-xs text-muted">{t('misc.today_price')}</p>
                      <MoneyText value={crop.price.value} className="font-semibold" />
                      <SourceBadge sourced={crop.price} compact />
                    </div>
                    <div>
                      <p className="text-xs text-muted">{t('misc.harvest_price')}</p>
                      <MoneyText value={crop.expected_harvest_price.value} className="font-semibold" />
                      <SourceBadge sourced={crop.expected_harvest_price} compact />
                    </div>
                    <div>
                      <p className="text-xs text-muted">{t('misc.profit_per_acre')}</p>
                      <MoneyText value={crop.profit_rs_per_acre[selectedScenario]} className="font-semibold text-primary" />
                      <SourceBadge sourced={{ value: crop.profit_rs_per_acre[selectedScenario], unit: 'rs/acre', source: 'computed', source_url: '', as_of: '', status: 'computed' }} compact />
                    </div>
                  </div>

                  {/* Duration */}
                  <p className="text-xs text-muted">
                    {t('misc.occupies_land', { months: Math.round(crop.duration_days / 30) })}
                  </p>

                  {/* Why this crop — SHAP factors */}
                  {crop.suitability.top_factors.length > 0 && (
                    <details className="text-xs">
                      <summary className="text-primary font-medium cursor-pointer">{t('dashboard.why_crop')}</summary>
                      <ul className="mt-2 space-y-1 pl-3 border-l-2 border-primary-soft">
                        {crop.suitability.top_factors.map((f, i) => (
                          <li key={i} className="text-muted">
                            {t(`shap_features.${f.feature}`, {
                              value: f.value,
                              direction: f.direction === 'up' ? '↑' : '↓',
                            })}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              </Card>
            )
          })}
        </div>
      </div>

      {/* Excluded crops */}
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

      <DistrictMap />

      {/* Sources chip */}
      <div className="flex items-center gap-2 text-sm text-muted">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-badge-live" aria-hidden="true" />
          {t('misc.live_count', { n: plan.data_status.live })}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-badge-cached" aria-hidden="true" />
          {t('misc.cached_count', { n: plan.data_status.cached })}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-badge-official" aria-hidden="true" />
          {t('misc.official_count', { n: plan.data_status.official_dataset })}
        </span>
      <Link to="/sources" className="ml-2 text-primary hover:underline">{t('dashboard.sources_chip')} →</Link>
      </div>

    </div>
    </div>
  )
}
