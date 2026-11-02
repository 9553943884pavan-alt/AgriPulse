/** Detects when the saved farm profile no longer matches the profile a plan was made for. */

import type { FarmProfile } from '@/api/types'

const COMPARED_FIELDS = [
  'land_acres',
  'budget_rs',
  'location_text',
  'water_source',
  'borewell_count',
  'borewell_yield_lph',
  'pump_hours_per_day',
  'canal_access',
  'irrigation_method',
  'risk_appetite',
] as const

function norm(value: unknown): unknown {
  if (typeof value === 'string') return value.trim().toLowerCase()
  if (value === undefined) return null
  return value
}

export function isPlanStale(
  planProfile: FarmProfile | null | undefined,
  currentProfile: FarmProfile | null | undefined,
): boolean {
  if (!planProfile || !currentProfile) return false
  return COMPARED_FIELDS.some((field) => norm(planProfile[field]) !== norm(currentProfile[field]))
}
