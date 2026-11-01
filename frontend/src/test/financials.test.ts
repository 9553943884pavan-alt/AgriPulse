import { describe, expect, it } from 'vitest'
import { calculatePlanFinancials } from '@/features/plan/financials'
import type { CropOption, StrategyResult } from '@/api/types'

const crop = {
  crop_id: 'wheat',
  yield_quintal_per_acre: { drought: 8, normal: 10, excess: 9 },
  expected_harvest_price: { value: 2000 },
} as CropOption

const strategy = {
  allocations: [{ crop_id: 'wheat', acres: 2, cost_rs: 20000, water_m3: 0, profit_rs: { drought: 10000, normal: 20000, excess: 16000 }, revenue_rs: null }],
  profit_by_scenario_rs: { drought: 10000, normal: 20000, excess: 16000 },
} as StrategyResult

describe('calculatePlanFinancials', () => {
  it('derives revenue as cost + profit when revenue_rs is null, plus ROI and break-even', () => {
    const result = calculatePlanFinancials(strategy, [crop], 'normal')
    expect(result).toMatchObject({
      investmentRs: 20000,
      revenueRs: 40000,
      revenueBasis: 'cost_plus_profit',
      profitRs: 20000,
      roiPct: 100,
      breakEvenPriceRsPerQuintal: 1000,
      productionQuintals: 20,
      reconciliationDifferenceRs: 0,
    })
  })

  it('uses optimizer revenue_rs when every allocation has it', () => {
    const s = {
      ...strategy,
      allocations: [{ ...strategy.allocations[0], revenue_rs: { drought: 31000, normal: 40000, excess: 36000 } }],
    } as StrategyResult
    const result = calculatePlanFinancials(s, [crop], 'drought')
    expect(result).toMatchObject({ revenueRs: 31000, revenueBasis: 'optimizer', profitRs: 10000 })
    expect(result?.reconciliationDifferenceRs).toBe(31000 - 20000 - 10000)
  })

  it('sums cost across multiple allocations and handles negative profit', () => {
    const s = {
      allocations: [
        { crop_id: 'wheat', acres: 1, cost_rs: 10000, water_m3: 0, profit_rs: { drought: -1, normal: -1, excess: -1 }, revenue_rs: null },
        { crop_id: 'onion', acres: 1, cost_rs: 30000, water_m3: 0, profit_rs: { drought: -9, normal: -9, excess: -9 }, revenue_rs: null },
      ],
      profit_by_scenario_rs: { drought: -10000, normal: -10000, excess: -10000 },
    } as StrategyResult
    const result = calculatePlanFinancials(s, [], 'normal')
    expect(result).toMatchObject({ investmentRs: 40000, revenueRs: 30000, profitRs: -10000, roiPct: -25, breakEvenPriceRsPerQuintal: null })
  })

  it('does not invent break-even price if the yield is absent', () => {
    const result = calculatePlanFinancials(strategy, [{ crop_id: 'wheat' } as CropOption], 'normal')
    expect(result?.breakEvenPriceRsPerQuintal).toBeNull()
    expect(result?.productionQuintals).toBeNull()
  })

  it('returns null (no plan) when there are no allocations', () => {
    const empty = { allocations: [], profit_by_scenario_rs: { drought: 0, normal: 0, excess: 0 } } as unknown as StrategyResult
    expect(calculatePlanFinancials(empty, [crop], 'normal')).toBeNull()
  })

  it('reconciles the live Nashik onion plan (revenue 68033 = cost 55558 + profit 12475, ROI 22.45%)', () => {
    const onion = { crop_id: 'onion', yield_quintal_per_acre: { drought: 53, normal: 53, excess: 53 } } as unknown as CropOption
    const lp = {
      allocations: [{
        crop_id: 'onion', acres: 1.3, cost_rs: 55558, water_m3: 3805,
        profit_rs: { drought: 12475.424, normal: 12475.424, excess: 12475.424 },
        revenue_rs: { drought: 68033.043, normal: 68033.043, excess: 68033.043 },
      }],
      profit_by_scenario_rs: { drought: 12475.424, normal: 12475.424, excess: 12475.424 },
    } as StrategyResult
    const r = calculatePlanFinancials(lp, [onion], 'normal')
    expect(r).toMatchObject({ investmentRs: 55558, revenueRs: 68033, revenueBasis: 'optimizer' })
    expect(r?.roiPct).toBeCloseTo(22.45, 1)
    expect(Math.abs(r?.reconciliationDifferenceRs ?? 9)).toBeLessThanOrEqual(1)
  })
})
