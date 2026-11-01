import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  retries: 0,
  use: {
    baseURL: process.env.DEMO_URL || 'http://127.0.0.1:8080',
    headless: true,
    // PW_CHANNEL=chrome runs the system Chrome where Playwright has no bundled build.
    channel: process.env.PW_CHANNEL || undefined,
  },
  reporter: [['list']],
})
