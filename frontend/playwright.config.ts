import { defineConfig } from '@playwright/test'

// Uses the already-running dev server (5173) and backend (8000).
// Browser: system Microsoft Edge (channel 'msedge'), no browser download needed.
export default defineConfig({
  testDir: './e2e',
  // The long demo recording has its own config (playwright.demo.config.ts).
  testIgnore: 'demo-video.spec.ts',
  timeout: 60_000,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    channel: 'msedge',
    headless: true,
    viewport: { width: 1280, height: 900 },
  },
})
