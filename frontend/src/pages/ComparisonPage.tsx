/**
 * ComparisonPage — side-by-side strategy comparison.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Star } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { useStore } from '@/state/store'
import { ScenarioToggle } from '@/components/ScenarioToggle'
import { Card, CardHeader } from '@/components/Card'
import { Badge } from '@/components/Badge'
import { MoneyText } from '@/components/MoneyText'
import { WaterText } from '@/components/WaterText'
import { ApiClientError, apiPost } from '@/api/client'
import { EmptyPlanNotice, isEmptyPlan } from '@/components/EmptyPlanNotice'
import { ErrorState } from '@/components/ErrorState'
import type { ApiError, Language, PlanResult, RiskAppetite, StrategyId } from '@/api/types'

const STRATEGY_COLORS: Record<string, string> = {
  traditional:     '#78909C',
  lp_max_profit:   '#1565C0',
  qp_balanced:     '#2E7D32',
  qp_drought_safe: '#00897B',
}

const STRATEGY_ICONS: Record<string, string> = {
  traditional:     '🌾',
  lp_max_profit:   '📈',
  qp_balanced:     '⚖️',
  qp_drought_safe: '🛡️',
}

export function ComparisonPage() {
  const { t } = useTranslation()
  const { language, plan, selectedScenario, setStrategy, selectedStrategy, setPlan, setProfile } = useStore()
  const [reoptimizing, setReoptimizing] = useState(false)
  const [reoptimizeError, setReoptimizeError] = useState<ApiError | null>(null)
  const [requestedRisk, setRequestedRisk] = useState<RiskAppetite | null>(null)

  if (!plan) {
    return (
      <div className="max-w-5xl mx-auto px-4 lg:px-6 py-6 flex flex-col items-center justify-center gap-4 min-h-64">
        <span className="text-5xl" aria-hidden="true">📊</span>
        <p className="text-muted text-center">{t('misc.no_plan_home')}</p>
        <Link to="/" className="text-primary font-medium hover:underline">{t('misc.go_home')}</Link>
      </div>
    )
  }

  if (isEmptyPlan(plan)) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="max-w-5xl mx-auto px-4 lg:px-6 py-6 space-y-4">
          <h1 className="text-2xl font-bold text-ink">{t('comparison.title')}</h1>
          <EmptyPlanNotice plan={plan} scenario={selectedScenario} lang={language as Language} />
        </div>
      </div>
    )
  }

  // Bar chart data for each metric
  const profitData = plan.strategies.map((s) => ({
    name: t(`strategies.${s.id}`),
    value: s.profit_by_scenario_rs[selectedScenario],
    color: STRATEGY_COLORS[s.id],
  }))

  const worstData = plan.strategies.map((s) => ({
    name: t(`strategies.${s.id}`),
    value: s.worst_case_profit_rs,
    color: STRATEGY_COLORS[s.id],
  }))

  const waterData = plan.strategies.map((s) => ({
    name: t(`strategies.${s.id}`),
    value: Math.round(s.totals.water_m3 / 1000), // m³ → thousands
    color: STRATEGY_COLORS[s.id],
  }))

  const fertData = plan.strategies.map((s) => ({
    name: t(`strategies.${s.id}`),
    value: s.totals.fertilizer_kg.n + s.totals.fertilizer_kg.p2o5 + s.totals.fertilizer_kg.k2o,
    color: STRATEGY_COLORS[s.id],
  }))

  // Scenario summary for selected strategy
  const summaryStrategy = plan.strategies.find((s) => s.id === (selectedStrategy ?? plan.recommended_strategy))
  const riskValue = plan.profile.risk_appetite === 'safe'
    ? 0
    : plan.profile.risk_appetite === 'balanced' ? 50 : 100

  const updateRisk = async (value: number) => {
    const risk_appetite: RiskAppetite = value === 0 ? 'safe' : value === 50 ? 'balanced' : 'max_profit'
    if (risk_appetite === plan.profile.risk_appetite || reoptimizing) return
    setReoptimizing(true)
    setRequestedRisk(risk_appetite)
    setReoptimizeError(null)
    try {
      const updated = await apiPost<PlanResult>(
        `/api/plans/${encodeURIComponent(plan.plan_id)}/reoptimize`,
        { risk_appetite },
      )
      setPlan(updated)
      setProfile(updated.profile)
    } catch (error) {
      setReoptimizeError(error instanceof ApiClientError ? error.apiError : {
        code: 'UPSTREAM_UNAVAILABLE',
        message: 'Reoptimization request failed.',
        user_message: {
          en: 'The plan could not be recalculated. Please try again.',
          mr: 'योजना पुन्हा मोजता आली नाही. कृपया पुन्हा प्रयत्न करा.',
          hi: 'योजना दोबारा नहीं बन सकी। कृपया फिर से प्रयास करें।',
        },
        retryable: true,
        details: {},
      })
    } finally {
      setReoptimizing(false)
    }
  }

  // Auto-generate insights from data comparisons (not free text)
  const insights: string[] = []
  const qpB = plan.strategies.find((s) => s.id === 'qp_balanced')
  const qpD = plan.strategies.find((s) => s.id === 'qp_drought_safe')
  const lp = plan.strategies.find((s) => s.id === 'lp_max_profit')
  const trad = plan.strategies.find((s) => s.id === 'traditional')

  if (qpB && trad && qpB.expected_profit_rs > trad.expected_profit_rs) {
    insights.push(`QP Balanced gives ${Math.round(((qpB.expected_profit_rs - trad.expected_profit_rs) / trad.expected_profit_rs) * 100)}% more expected profit than Traditional.`)
  }
  if (qpD && lp && qpD.worst_case_profit_rs > lp.worst_case_profit_rs) {
    insights.push('QP Drought-Safe performs best in low rainfall conditions (highest worst-year profit).')
  }
  if (lp && qpB && lp.totals.water_m3 > qpB.totals.water_m3) {
    insights.push('LP Max-Profit gives highest expected profit but uses more water.')
  }
  if (trad && qpB && trad.totals.water_m3 > qpB.totals.water_m3) {
    insights.push('Traditional plan has highest water usage.')
  }

  return (
    <div className="h-full overflow-y-auto" style={{ scrollbarWidth: 'thin', scrollbarColor: '#86efac transparent' }}>
    <div className="max-w-6xl mx-auto px-4 lg:px-6 py-6 space-y-6">

      {/* Page header */}
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-xl bg-primary-soft flex items-center justify-center">
          <span className="text-xl" aria-hidden="true">📊</span>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-ink">{t('comparison.title')}</h1>
          <p className="text-sm text-muted">{t('comparison.subtitle')}</p>
        </div>
      </div>

      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-6">
        <div>
          <p className="text-sm font-semibold text-ink mb-2">{t('comparison.weather_scenario')}</p>
          <ScenarioToggle scenarios={['normal', 'drought', 'excess']} />
        </div>
        <div className="flex-1 max-w-xs">
          <p className="text-sm font-semibold text-ink mb-2">{t('comparison.risk_preference')}</p>
          <div className="flex items-center gap-2 text-xs text-muted">
            <span>{t('misc.risk_safe_short')}</span>
            <input
              type="range"
              min={0}
              max={100}
              step={50}
              value={riskValue}
              disabled={reoptimizing}
              onChange={(event) => void updateRisk(Number(event.target.value))}
              className="flex-1 accent-primary"
              aria-label="Risk preference"
            />
            <span>{t('misc.risk_max_short')}</span>
          </div>
        </div>
      </div>

      {reoptimizing && (
        <p role="status" className="text-sm text-muted">
          {t('comparison.reoptimizing', 'Recalculating your plan…')}
        </p>
      )}
      {reoptimizeError && (
        <ErrorState
          error={reoptimizeError}
          retryable={reoptimizeError.retryable}
          onRetry={() => void updateRisk(requestedRisk === 'safe' ? 0 : requestedRisk === 'balanced' ? 50 : 100)}
        />
      )}

      {/* Strategy cards */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {plan.strategies.map((strategy) => {
          const isRecommended = strategy.id === plan.recommended_strategy
          const isSelected = strategy.id === (selectedStrategy ?? plan.recommended_strategy)
          const color = STRATEGY_COLORS[strategy.id] ?? '#78909C'
          return (
            <button
              key={strategy.id}
              type="button"
              onClick={() => setStrategy(strategy.id as StrategyId)}
              className={`text-left rounded-2xl p-5 border-2 transition-all shadow-sm ${
                isSelected
                  ? 'border-green-500 bg-green-50 shadow-md'
                  : 'border-gray-100 bg-white hover:border-green-200 hover:shadow-md'
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shadow-sm"
                  style={{ background: `${color}20` }}>
                  {STRATEGY_ICONS[strategy.id]}
                </div>
                {isRecommended && (
                  <Badge variant="success">
                    <Star className="w-3 h-3" aria-hidden="true" />
                    {t('comparison.recommended')}
                  </Badge>
                )}
              </div>
              <p className="font-bold text-gray-800">{t(`strategies.${strategy.id}`)}</p>
              <p className="text-xs text-gray-400 mb-4">{t(`strategies.${strategy.id}_desc`)}</p>
              <dl className="space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <dt className="text-gray-400">{t('comparison.expected_profit')}</dt>
                  <dd className="font-semibold text-gray-800"><MoneyText value={strategy.profit_by_scenario_rs[selectedScenario]} /></dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-400">{t('comparison.worst_year')}</dt>
                  <dd className="font-semibold text-gray-800"><MoneyText value={strategy.worst_case_profit_rs} /></dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-400">{t('comparison.water_usage')}</dt>
                  <dd className="font-semibold text-gray-800"><WaterText m3={strategy.totals.water_m3} showTankers={false} /></dd>
                </div>
              </dl>
              {isSelected && (
                <div className="mt-3 h-1 rounded-full" style={{ background: color }} />
              )}
            </button>
          )
        })}
      </div>

      {/* 4 bar charts — 2×2 grid for readability */}
      <div className="grid sm:grid-cols-2 gap-6">
        {[
          { title: t('comparison.expected_profit'), data: profitData, fmt: (v: number) => `₹${(v/1000).toFixed(0)}k` },
          { title: t('comparison.worst_year'),      data: worstData,  fmt: (v: number) => `₹${(v/1000).toFixed(0)}k` },
          { title: `${t('comparison.water_usage')} (k L)`, data: waterData, fmt: (v: number) => `${v}k L` },
          { title: `${t('comparison.fertilizer_usage')} (kg)`, data: fertData, fmt: (v: number) => `${v} kg` },
        ].map(({ title, data, fmt }) => (
          <div key={title} className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
            <p className="text-sm font-bold text-gray-700 mb-3">{title}</p>
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} margin={{ top: 20, right: 8, left: 0, bottom: 0 }} barCategoryGap="30%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                  <YAxis tickFormatter={fmt} tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} width={52} />
                  <Tooltip
                    formatter={(v: any) => [fmt(v as number)]}
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                    cursor={{ fill: '#f9fafb' }}
                  />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]}
                    label={{ position: 'top', fontSize: 10, fill: '#6B7280', formatter: fmt }}
                  >
                    {data.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        ))}
      </div>

      {/* Insights + Scenario summary */}
      <div className="grid lg:grid-cols-2 gap-6">

        {/* Strategy Insights — derived from data */}
        {insights.length > 0 && (
          <Card>
            <div className="p-5">
              <CardHeader icon={<span aria-hidden="true">💡</span>} title={t('comparison.insights_title')} />
              <ul className="mt-4 space-y-2">
                {insights.map((insight, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-ink">
                    <span className="text-primary mt-0.5" aria-hidden="true">✓</span>
                    {insight}
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        )}

        {/* Scenario summary table */}
        {summaryStrategy && (
          <Card>
            <div className="p-5">
              <CardHeader icon={<span aria-hidden="true">📋</span>} title={`${t('comparison.scenario_summary')} (${t(`strategies.${summaryStrategy.id}`)})`} />
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="text-left py-2 text-muted font-medium">{t('comparison.metric')}</th>
                      <th className="text-right py-2 text-primary font-medium">{t('scenarios.normal')}</th>
                      <th className="text-right py-2 text-drought font-medium">{t('scenarios.drought')}</th>
                      <th className="text-right py-2 text-rain font-medium">{t('scenarios.excess')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    <tr>
                      <td className="py-2 text-muted">{t('comparison.expected_profit')} (₹)</td>
                      <td className="py-2 text-right font-medium"><MoneyText value={summaryStrategy.profit_by_scenario_rs.normal} /></td>
                      <td className="py-2 text-right font-medium"><MoneyText value={summaryStrategy.profit_by_scenario_rs.drought} /></td>
                      <td className="py-2 text-right font-medium"><MoneyText value={summaryStrategy.profit_by_scenario_rs.excess} /></td>
                    </tr>
                    <tr>
                      <td className="py-2 text-muted">{t('misc.worst_year_profit')}</td>
                      <td colSpan={3} className="py-2 text-right font-medium"><MoneyText value={summaryStrategy.worst_case_profit_rs} /></td>
                    </tr>
                    <tr>
                      <td className="py-2 text-muted">{t('comparison.water_usage')}</td>
                      <td colSpan={3} className="py-2 text-right font-medium">
                        <WaterText m3={summaryStrategy.totals.water_m3} showTankers={false} />
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 text-muted">{t('comparison.fertilizer_usage')}</td>
                      <td colSpan={3} className="py-2 text-right font-medium">
                        {summaryStrategy.totals.fertilizer_kg.n + summaryStrategy.totals.fertilizer_kg.p2o5 + summaryStrategy.totals.fertilizer_kg.k2o} kg
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
    </div>
  )
}
