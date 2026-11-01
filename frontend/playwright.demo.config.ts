import { defineConfig } from '@playwright/test'

// Separate config used ONLY to record the demo video (does not touch the smoke config).
// Run: npx playwright test -c playwright.demo.config.ts
// Needs the app already running: frontend 5173, backend 8000.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'demo-video.spec.ts',
  timeout: 6 * 60_000,
  workers: 1,
  retries: 0,
  reporter: 'list',
  outputDir: 'demo-video',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    channel: 'msedge',
    headless: true,
    viewport: { width: 1280, height: 720 },
    video: { mode: 'on', size: { width: 1280, height: 720 } },
  },
})
