/** Client-side validation for the farm profile form. Values are i18n keys. */

export interface ProfileFormValues {
  location_text: string
  land_acres: string
  budget_rs: string
}

export type ProfileErrors = Partial<Record<keyof ProfileFormValues, string>>

export function validateProfile(v: ProfileFormValues): ProfileErrors {
  const errors: ProfileErrors = {}
  if (!v.location_text.trim()) errors.location_text = 'profile_page.err_location'
  const land = v.land_acres.trim() === '' ? NaN : Number(v.land_acres)
  if (!Number.isFinite(land) || land <= 0) errors.land_acres = 'profile_page.err_land'
  const budget = v.budget_rs.trim() === '' ? NaN : Number(v.budget_rs)
  if (!Number.isFinite(budget) || budget <= 0) errors.budget_rs = 'profile_page.err_budget'
  return errors
}
