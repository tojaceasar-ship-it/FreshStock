import { defineConfig, devices } from '@playwright/test'

const auditPort = Number(process.env.E2E_PORT || 4173)

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${auditPort}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${auditPort}`,
    url: `http://127.0.0.1:${auditPort}`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
