import { test, expect } from '@playwright/test'

// Farm Profile -> Save -> Optimize -> Dashboard, against the real app and backend.
// Optimize must be unavailable until the latest form data is saved, and the page
// must only redirect once the plan was generated and persisted.

test.setTimeout(180_000)

test('Optimize is gated on Save, then plans from the saved profile and redirects to the dashboard', async ({ page }) => {
  const optimizeRequests: string[] = []
  page.on('request', (req) => {
    if (req.method() === 'POST' && req.url().includes('/api/agent/chat')) {
      const body = req.postData() ?? ''
      if (body.includes('"intent":"optimize"')) optimizeRequests.push(body)
    }
  })

  await page.goto('/profile')
  await expect(page.getByRole('heading', { name: 'Farm Profile' })).toBeVisible()

  const save = page.getByRole('button', { name: 'Save Changes' })
  const optimize = page.getByRole('button', { name: /^Optimize Plan$/ })

  // Fill the Nashik farm.
  await page.getByLabel(/^Location/).fill('Nashik, Maharashtra')
  await page.getByLabel(/^Total land/).fill('2')
  await page.getByLabel(/^Budget/).fill('200000')
  await page.getByLabel(/^Water source/).selectOption('borewell')
  await page.getByLabel(/^Yield/).fill('8000')
  await page.getByLabel(/^Pump hours/).fill('6')
  await page.getByLabel(/^Irrigation method/).selectOption('drip')

  // Nothing saved yet: Optimize is disabled and says why.
  await expect(optimize).toBeVisible()
  await expect(optimize).toBeDisabled()
  await expect(page.getByText('Save your changes first')).toBeVisible()
  await expect(save).toBeEnabled()

  // Save -> confirmation -> Optimize becomes available.
  await save.click()
  await expect(page.getByText(/^Saved( at .+)?$/)).toBeVisible({ timeout: 30_000 })
  await expect(optimize).toBeEnabled()
  await expect(save).toBeDisabled()
  await expect(page.getByText('Save your changes first')).toHaveCount(0)

  // Editing again disables Optimize until the change is saved.
  await page.getByLabel(/^Total land/).fill('3')
  await expect(optimize).toBeDisabled()
  await expect(page.getByText('Save your changes first')).toBeVisible()
  await expect(save).toBeEnabled()

  // Reverting the edit makes the form clean again, so Optimize is available without a new save.
  await page.getByLabel(/^Total land/).fill('2')
  await expect(optimize).toBeEnabled()
  await expect(save).toBeDisabled()

  // Edit once more and save the new value.
  await page.getByLabel(/^Total land/).fill('2.5')
  await expect(optimize).toBeDisabled()
  await save.click()
  await expect(page.getByText(/^Saved( at .+)?$/)).toBeVisible({ timeout: 30_000 })
  await expect(optimize).toBeEnabled()
  expect(optimizeRequests).toHaveLength(0) // saving never plans

  // Optimize: a quick double click must start exactly one run.
  await optimize.dblclick()
  await expect(page.getByRole('button', { name: /Optimizing/ })).toBeVisible()
  await expect(page).toHaveURL(/\/profile$/) // not redirected before the run finishes

  // Redirect only after the plan is generated and saved.
  await page.waitForURL('**/dashboard', { timeout: 120_000 })
  expect(optimizeRequests).toHaveLength(1)
  expect(optimizeRequests[0]).toContain('"profile_version"')

  await expect(page.getByText('Investment').first()).toBeVisible()
  await expect(page.getByText('Net profit').first()).toBeVisible()
})
