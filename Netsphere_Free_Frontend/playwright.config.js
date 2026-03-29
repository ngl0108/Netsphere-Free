import { defineConfig, devices } from '@playwright/test';
import process from 'node:process';

const isWindows = process.platform === 'win32';
const e2eBaseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:5174';
const skipWebServer = String(process.env.PW_SKIP_WEBSERVER || '').trim() === '1';
const webServerCommand = isWindows
  ? 'npm.cmd run dev -- --host 127.0.0.1'
  : 'npm run dev -- --host 127.0.0.1';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL: e2eBaseUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: skipWebServer ? undefined : {
    command: webServerCommand,
    url: e2eBaseUrl,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
