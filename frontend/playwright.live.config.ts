import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser',
  testMatch: '**/profile-live.spec.ts',
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 10_000 },
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    ...devices['Desktop Chrome'],
    channel: 'chrome',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: '../backend/.venv/bin/python ../scripts/browser-backend.py',
      url: 'http://127.0.0.1:8000/api/v1/health/live',
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
