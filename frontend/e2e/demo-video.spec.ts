import { test, expect, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'

// Records the AgriPulse demo walk-through (see docs/DEMO_VIDEO_SCRIPT.md).
// Needs the app running (frontend 5173, backend 8000). The AI replies are real
// Sarvam calls, so each chat turn can take 10-20 s; waits are generous.
const OUT = join(process.cwd(), 'demo-video')
const REPLY_TIMEOUT = 120_000

const MSG_NASHIK =
  'I am from Nashik, Maharashtra. I have 2 acres, budget 2 lakh rupees, one borewell 8000 litres per hour for 6 hours daily, drip irrigation.'
const MSG_WHY = 'Why onion and not wheat?'
const MSG_PUNE = 'I am from Pune, Maharashtra'
const MSG_CANAL = 'Now I have canal water instead'

const pause = (page: Page, ms = 2000) => page.waitForTimeout(ms)
const shot = (page: Page, name: string) => page.screenshot({ path: join(OUT, `${name}.png`) })

/** Type like a person, send, and wait for the AI reply (input re-enabled + 2 new bubbles). */
async function ask(page: Page, text: string): Promise<string> {
  const bubbles = page.locator('p.whitespace-pre-wrap')
  const before = await bubbles.count()
  const input = page.getByRole('textbox', { name: 'Chat message' })
  await expect(input).toBeEnabled({ timeout: REPLY_TIMEOUT })
  await input.click()
  await pause(page, 600)
  await input.pressSequentially(text, { delay: 35 })
  await pause(page, 1200)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(bubbles).toHaveCount(before + 2, { timeout: REPLY_TIMEOUT })
  await expect(input).toBeEnabled({ timeout: REPLY_TIMEOUT })
  await pause(page, 1000)
  const reply = (await bubbles.last().innerText()).trim()
  console.log(`\n[AGENT REPLY to "${text.slice(0, 40)}..."]\n${reply}\n`)
  return reply
}

async function goTo(page: Page, name: 'Home' | 'Dashboard' | 'Comparison' | 'Sources') {
  await page.getByRole('navigation', { name: 'Sidebar navigation' }).getByRole('link', { name }).click()
  // Park the mouse over the main content so mouse.wheel scrolls the page, not the sidebar.
  await page.mouse.move(760, 400)
}

test('AgriPulse demo walk-through', async ({ page }) => {
  mkdirSync(OUT, { recursive: true })

  // 0. Fresh start: clear app storage so it is a new conversation.
  await page.goto('/')
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear() })
  await page.reload()
  await expect(page.getByRole('textbox', { name: 'Chat message' })).toBeVisible()
  await pause(page, 3000)
  await shot(page, '01_home_fresh')

  // 1. Live plan for Nashik.
  const r1 = await ask(page, MSG_NASHIK)
  await pause(page, 3000)
  await shot(page, '02_chat_plan_nashik')

  // 2. Dashboard: finances, allocation, scenarios.
  await goTo(page, 'Dashboard')
  await expect(page.getByRole('heading', { name: 'Plan finances' })).toBeVisible({ timeout: 30_000 })
  await pause(page, 3000)
  await shot(page, '03_dashboard_top')
  const fin = page.locator('#financial-summary-heading').locator('xpath=ancestor::section')
  await fin.scrollIntoViewIfNeeded()
  await pause(page, 1500)
  await fin.hover()
  await pause(page, 4000)
  await shot(page, '04_dashboard_finances')
  for (const name of ['Drought', 'Excess rain', 'Normal']) {
    const chip = page.getByRole('group', { name: 'Weather scenario' }).getByRole('button', { name: new RegExp(name, 'i') }).first()
    if (await chip.count()) {
      await chip.click()
      await pause(page, 2500)
      if (name === 'Drought') await shot(page, '05_dashboard_drought')
    }
  }
  await page.mouse.wheel(0, 700)
  await pause(page, 3000)
  await shot(page, '06_dashboard_lower')
  await page.mouse.wheel(0, 700)
  await pause(page, 2500)

  // 3. Back to chat: why onion?
  await goTo(page, 'Home')
  await pause(page, 1500)
  const r2 = await ask(page, MSG_WHY)
  await pause(page, 3000)
  await shot(page, '07_chat_why_onion')

  // 4. Change location to Pune.
  const r3 = await ask(page, MSG_PUNE)
  await pause(page, 3000)
  await shot(page, '08_chat_pune_replan')

  // 5. Comparison of strategies.
  await goTo(page, 'Comparison')
  await expect(page.getByRole('heading', { name: 'Strategy Comparison' })).toBeVisible({ timeout: 30_000 })
  await pause(page, 4000)
  await shot(page, '09_comparison_top')
  await page.mouse.wheel(0, 600)
  await pause(page, 4000)
  await shot(page, '10_comparison_lower')
  await page.mouse.wheel(0, 600)
  await pause(page, 2500)

  // 6. Sources / provenance.
  await goTo(page, 'Sources')
  await expect(page.getByRole('heading', { name: 'Data Sources' })).toBeVisible({ timeout: 30_000 })
  await pause(page, 4000)
  await shot(page, '11_sources_top')
  await page.mouse.wheel(0, 600)
  await pause(page, 4000)
  await shot(page, '12_sources_lower')
  await page.mouse.wheel(0, 600)
  await pause(page, 2500)

  // 7. Honest no-plan case (canal water).
  await goTo(page, 'Home')
  await pause(page, 1500)
  const r4 = await ask(page, MSG_CANAL)
  await pause(page, 4000)
  await shot(page, '13_chat_canal_no_plan')
  await goTo(page, 'Dashboard')
  await pause(page, 4000)
  await shot(page, '14_dashboard_no_plan')
  await page.mouse.wheel(0, 700)
  await pause(page, 3500)
  await shot(page, '14b_dashboard_no_plan_reasons')
  const body = await page.locator('body').innerText()
  const canalLines = body.split(/\r?\n/).filter((l) => /canal/i.test(l))
  console.log('[NO-PLAN PAGE lines mentioning canal] ' + (canalLines.join(' | ') || '(none)'))
  await page.mouse.wheel(0, 700)
  await pause(page, 2500)

  // 8. Closing: back to the home screen.
  await goTo(page, 'Home')
  await pause(page, 3000)
  await shot(page, '15_closing_home')

  // Light sanity checks on what was said (real AI text, so keep these loose).
  expect(r1.length).toBeGreaterThan(20)
  expect(r2.length).toBeGreaterThan(20)
  expect(r3.length).toBeGreaterThan(20)
  expect(r4.length).toBeGreaterThan(20)
})
