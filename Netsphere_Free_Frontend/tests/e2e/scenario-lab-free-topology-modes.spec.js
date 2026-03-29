import { test, expect } from '@playwright/test';

import {
  attachPageGuards,
  gotoWithRetry,
  loadScenarioReport,
  loginLiveUserAtBase,
  pickScenarioAdmin,
} from './scenario-lab-live.helpers';

const report = loadScenarioReport('free-hybrid-visibility');
const credentials = pickScenarioAdmin(report);
const baseUrl = 'http://127.0.0.1:18080';

const gotoAtBase = async (page, targetPath) => {
  await gotoWithRetry(page, new URL(targetPath, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
};

test.describe.configure({ mode: 'serial' });

test('scenario-lab free topology mode buttons work without surfacing blocked admin controls', async ({ page }) => {
  test.slow();
  const guards = attachPageGuards(page);

  await loginLiveUserAtBase(page, baseUrl, { ...credentials, locale: 'ko' });

  await gotoAtBase(page, '/topology');
  await expect(page.getByTestId('topology-layer-filter-hybrid')).toBeVisible({ timeout: 30000 });

  const hybridToggle = page.getByTestId('topology-layer-filter-hybrid');
  await hybridToggle.click();
  await expect(hybridToggle).toHaveClass(/bg-sky-600/, { timeout: 30000 });

  await page.getByTestId('topology-layer-filter-all').click();
  await expect(page.getByTestId('topology-path-trace-toggle')).toBeVisible();

  await page.getByTestId('topology-path-trace-toggle').click();
  await expect(page.getByTestId('path-trace-panel')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('button[aria-label*="Observability Collection"]')).toHaveCount(0);

  guards.assertClean();
});

test('scenario-lab free layout editor opens without triggering app error fallback', async ({ page }) => {
  test.slow();
  const guards = attachPageGuards(page);

  await loginLiveUserAtBase(page, baseUrl, { ...credentials, locale: 'ko' });
  await gotoAtBase(page, '/topology');

  const manualEditButton = page.getByRole('button', { name: /Layout Editor|레이아웃 에디터/i }).first();
  await expect(manualEditButton).toBeVisible({ timeout: 30000 });
  await manualEditButton.click();

  await expect(page.getByText(/Layout Editor Workspace|레이아웃 에디터/i)).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/Internal Server Error|내부 서버 오류/i)).toHaveCount(0);

  guards.assertClean();
});
