import type { CropOption, ScenarioId, StrategyResult } from '@/api/types'

export interface PlanFinancials {
  investmentRs: number
  revenueRs: number | null
  /** 'optimizer' when every allocation carried revenue_rs; otherwise derived as cost + profit. */
  revenueBasis: 'optimizer' | 'cost_plus_profit'
  profitRs: number
  roiPct: number | null
  breakEvenPriceRsPerQuintal: number | null
  productionQuintals: number | null
  reconciliationDifferenceRs: number | null
}

/**
 * Calculate farmer-facing finances from the selected allocation.
 *
 * Revenue uses the optimizer's allocation-level revenue_rs when every
 * allocation carries it. When any is null/missing, revenue is derived as
 * total cultivation cost + scenario profit, so the three displayed numbers
 * always reconcile (revenue - cost = profit). Break-even price still needs
 * the model yield; if absent it stays unknown and is never defaulted.
 */
export function calculatePlanFinancials(
  strategy: StrategyResult | undefined,
  crops: CropOption[],
  scenario: ScenarioId,
): PlanFinancials | null {
  if (!strategy || strategy.allocations.length === 0) return null

  let investmentRs = 0
  let reportedRevenue = 0
  let allReported = true
  let productionQuintals = 0
  let productionKnown = true

  for (const allocation of strategy.allocations) {
    investmentRs += allocation.cost_rs
    const crop = crops.find((item) => item.crop_id === allocation.crop_id)
    const reported = allocation.revenue_rs?.[scenario]
    // Older cached responses and incomplete fixtures can contain a crop shell
    // without a model yield. Treat that as unknown rather than throwing.
    const yieldPerAcre = crop?.yield_quintal_per_acre?.[scenario]

    if (typeof yieldPerAcre === 'number' && Number.isFinite(yieldPerAcre)) {
      productionQuintals += yieldPerAcre * allocation.acres
    } else {
      productionKnown = false
    }

    if (typeof reported === 'number' && Number.isFinite(reported)) {
      reportedRevenue += reported
    } else {
      allReported = false
    }
  }

  const profitRs = strategy.profit_by_scenario_rs[scenario]
  if (typeof profitRs !== 'number' || !Number.isFinite(profitRs)) return null
  const roundedInvestment = Math.round(investmentRs)
  const revenueRs = allReported ? Math.round(reportedRevenue) : Math.round(roundedInvestment + profitRs)

  return {
    investmentRs: roundedInvestment,
    revenueRs,
    revenueBasis: allReported ? 'optimizer' : 'cost_plus_profit',
    profitRs,
    roiPct: roundedInvestment > 0 ? (profitRs / roundedInvestment) * 100 : null,
    breakEvenPriceRsPerQuintal: productionKnown && productionQuintals > 0
      ? roundedInvestment / productionQuintals
      : null,
    productionQuintals: productionKnown ? productionQuintals : null,
    reconciliationDifferenceRs: Math.round(revenueRs - roundedInvestment - profitRs),
  }
}
