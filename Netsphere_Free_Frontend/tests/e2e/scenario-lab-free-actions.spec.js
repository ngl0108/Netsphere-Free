import { test, expect } from '@playwright/test';

import {
  attachPageGuards,
  gotoWithRetry,
  loginLiveUserAtBase,
  loadScenarioReport,
  pickScenarioAdmin,
} from './scenario-lab-live.helpers';

const report = loadScenarioReport('free-enterprise-visibility');
const credentials = pickScenarioAdmin(report);
const baseUrl = 'http://127.0.0.1:18080';

const gotoAtBase = async (page, targetPath) => {
  await gotoWithRetry(page, new URL(targetPath, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
};

test.describe.configure({ mode: 'serial' });

test('scenario-lab free action flows navigate only through allowed surfaces', async ({ page }) => {
  test.slow();
  const guards = attachPageGuards(page);

  await loginLiveUserAtBase(page, baseUrl, { ...credentials, locale: 'ko' });

  await gotoAtBase(page, '/automation');
  await page.getByTestId('automation-preview-compare').click();
  await expect(page).toHaveURL(/\/edition\/compare(?:[/?#]|$)/);
  await expect(page.locator('body')).toContainText(/Managed up to 50 nodes|관리 노드 50대까지/i);

  guards.assertClean();
  guards.reset();

  const navigationCases = [
    { testId: 'operations-quick-flow-discover_review', path: /\/discovery(?:[/?#]|$)/ },
    { testId: 'operations-surface-devices', path: /\/devices(?:[/?#]|$)/ },
    { testId: 'operations-secondary-surface-diagnosis', path: /\/diagnosis(?:[/?#]|$)/ },
  ];

  for (const item of navigationCases) {
    await gotoAtBase(page, '/automation');
    await expect(page.getByTestId(item.testId)).toBeVisible({ timeout: 15000 });
    await page.getByTestId(item.testId).click();
    await expect(page).toHaveURL(item.path);
    guards.assertClean();
    guards.reset();
  }
});

test('scenario-lab free audit and blocked-page messaging stay trustworthy', async ({ page }) => {
  test.slow();
  const guards = attachPageGuards(page);

  await loginLiveUserAtBase(page, baseUrl, { ...credentials, locale: 'ko' });

  await gotoAtBase(page, '/preview/contribute');
  await expect(page.getByTestId('preview-audit-policy-card')).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('preview-audit-policy-card')).toContainText(/Locked installation policy|설치 정책/i);

  const firstRecord = page.locator('[data-testid^="preview-audit-record-"]').first();
  await expect(firstRecord).toBeVisible();
  await firstRecord.click();

  await expect(page.getByTestId('preview-audit-detail-title')).toContainText(/Sanitized audit detail|감사 상세/i);
  await expect(page.getByTestId('preview-audit-raw-hidden-note')).toBeVisible();

  guards.assertClean();
  guards.reset();

  await gotoAtBase(page, '/service-groups');
  await expect(page.getByTestId('policy-blocked-page')).toBeVisible();
  await expect(page.locator('body')).toContainText(/Free|Preview|무료/);

  guards.assertClean();
});
