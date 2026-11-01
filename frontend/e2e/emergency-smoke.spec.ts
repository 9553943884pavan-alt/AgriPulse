import { test, expect, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'

const API = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000'
const SHOTS = process.env.E2E_SHOTS ?? join(process.cwd(), 'e2e', 'screenshots')

const PROFILE = {
  location_text: 'Nashik, Maharashtra', land_acres: 2, budget_rs: 200000,
  water_source: 'borewell', borewell_count: 1, borewell_yield_lph: 8000,
  pump_hours_per_day: 6, irrigation_method: 'drip', risk_appetite: 'balanced',
}

async function seed(page: Page, plan: unknown) {
  const state = { plan, profile: (plan as { profile: unknown }).profile, threadId: null, language: 'en', selectedScenario: 'normal', selectedStrategy: null, traceEvents: [], messages: [] }
  await page.addInitScript((s) => {
    localStorage.setItem('agripulse-session', JSON.stringify({ state: s, version: 0 }))
  }, state)
}

function watchConsole(page: Page) {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`) })
  return errors
}

test.beforeAll(() => { mkdirSync(SHOTS, { recursive: true }) })

test('positive plan renders allocation, cost, revenue, profit, ROI and provenance', async ({ page, request }) => {
  const res = await request.post(`${API}/api/plan`, { data: PROFILE })
  expect(res.ok()).toBeTruthy()
  const plan = await res.json()
  await seed(page, plan)
  const errors = watchConsole(page)

  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Plan finances' })).toBeVisible()
  const fin = page.locator('#financial-summary-heading').locator('xpath=ancestor::section')
  await expect(fin).toContainText('Investment')
  await expect(fin).toContainText('Gross revenue')
  await expect(fin).toContainText('Net profit')
  await expect(fin).toContainText('ROI')
  await expect(fin).toContainText('Normal year')
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.screenshot({ path: join(SHOTS, 'dashboard_positive.png'), fullPage: true })

  await page.goto('/sources')
  await expect(page.locator('body')).toContainText(/live|cached|official/i)
  await page.screenshot({ path: join(SHOTS, 'sources.png'), fullPage: true })
  expect(errors, errors.join('\n')).toEqual([])
})

test('no-profitable-plan view shows explanation, not a Rs 0 plan', async ({ page, request }) => {
  const res = await request.post(`${API}/api/plan`, { data: PROFILE })
  const plan = await res.json()
  // Synthetic empty case: every optimized strategy returns no allocation.
  for (const s of plan.strategies) if (s.id !== 'traditional') { s.allocations = []; s.feasible = false }
  plan.infeasibility = { binding: [], violated: [], detail: [], relaxations_tried: [], suggestion_code: 'NO_POSITIVE_ALLOCATION', suggestion_params: {} }
  await seed(page, plan)
  const errors = watchConsole(page)

  await page.goto('/dashboard')
  await expect(page.getByRole('alert').first()).toBeVisible()
  await expect(page.locator('#financial-summary-heading')).toHaveCount(0)
  await expect(page.locator('body')).toContainText('quintal/acre')
  await page.screenshot({ path: join(SHOTS, 'dashboard_no_plan.png'), fullPage: true })
  expect(errors, errors.join('\n')).toEqual([])
})
