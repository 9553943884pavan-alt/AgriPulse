import { IndianRupee, ReceiptText, Scale, TrendingUp } from 'lucide-react'
import type { CropOption, ScenarioId, StrategyResult } from '@/api/types'
import { MoneyText } from '@/components/MoneyText'
import { SourceBadge } from '@/components/SourceBadge'
import { calculatePlanFinancials } from './financials'

interface FinancialSummaryProps {
  strategy: StrategyResult | undefined
  crops: CropOption[]
  scenario: ScenarioId
  createdAt: string
}

const SCENARIO_LABEL: Record<ScenarioId, string> = {
  drought: 'Drought year (dry, P10 rainfall)',
  normal: 'Normal year (median rainfall)',
  excess: 'Excess-rain year (wet, P90 rainfall)',
}

export function FinancialSummary({ strategy, crops, scenario, createdAt }: FinancialSummaryProps) {
  const financials = calculatePlanFinancials(strategy, crops, scenario)
  if (!financials) return null

  const moneySource = {
    value: financials.profitRs,
    unit: 'Rs',
    source: 'Optimizer allocation, yield forecast, and expected harvest-price inputs',
    source_url: '',
    as_of: createdAt,
    status: 'computed' as const,
  }
  const revenueMatches = financials.reconciliationDifferenceRs === 0

  return (
    <section aria-labelledby="financial-summary-heading" className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-700">
            <IndianRupee className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <h2 id="financial-summary-heading" className="font-bold text-[15px] text-gray-800">Plan finances</h2>
            <p className="text-xs text-gray-500">{SCENARIO_LABEL[scenario]} · total ₹ for the whole plan ({strategy?.totals.land_used_acres ?? 0} acres)</p>
          </div>
        </div>
        <SourceBadge sourced={moneySource} compact />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
        <Metric icon={<ReceiptText className="w-4 h-4" />} label="Investment" value={<MoneyText value={financials.investmentRs} />} detail="Total cultivation cost (₹)" />
        <Metric
          icon={<TrendingUp className="w-4 h-4" />}
          label="Gross revenue"
          value={financials.revenueRs === null ? 'Unavailable' : <MoneyText value={financials.revenueRs} />}
          detail={financials.revenueBasis === 'optimizer' ? 'Yield × expected harvest price (₹)' : 'Cost + net profit (₹)'}
        />
        <Metric icon={<IndianRupee className="w-4 h-4" />} label="Net profit" value={<MoneyText value={financials.profitRs} />} detail="Revenue − cultivation cost (₹)" />
        <Metric
          icon={<Scale className="w-4 h-4" />}
          label="ROI / break-even"
          value={financials.roiPct === null ? 'Unavailable' : `${financials.roiPct.toFixed(1)}%`}
          detail={financials.breakEvenPriceRsPerQuintal === null ? 'Net profit ÷ cost. Break-even price unavailable' : `Net profit ÷ cost. Break-even ₹${Math.round(financials.breakEvenPriceRsPerQuintal).toLocaleString('en-IN')}/quintal`}
        />
      </div>

      {financials.revenueRs !== null && !revenueMatches && (
        <p role="note" className="mt-3 text-xs text-amber-800 bg-amber-50 rounded-lg px-3 py-2">
          The optimizer’s scenario profit differs by ₹{Math.abs(financials.reconciliationDifferenceRs ?? 0).toLocaleString('en-IN')} from the displayed yield × price calculation. Optimizer profit is shown as the plan decision value.
        </p>
      )}
    </section>
  )
}

function Metric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: React.ReactNode; detail: string }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-slate-50 p-3">
      <div className="flex items-center gap-1.5 text-xs text-gray-500">{icon}{label}</div>
      <div className="mt-1 font-bold text-gray-900 tabular-nums">{value}</div>
      <p className="mt-1 text-[11px] leading-tight text-gray-500">{detail}</p>
    </div>
  )
}
