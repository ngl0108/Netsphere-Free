import { test, expect } from '@playwright/test';

import {
  attachPageGuards,
  fetchJsonWithAuth,
  gotoWithRetry,
  loginLiveUserAtBase,
  loadScenarioReport,
  pickScenarioAdmin,
  unwrapCollection,
} from './scenario-lab-live.helpers';

const hybridReport = loadScenarioReport('pro-hybrid-operations');
const branchReport = loadScenarioReport('pro-branch-operations');
const hybridCredentials = pickScenarioAdmin(hybridReport);
const branchCredentials = pickScenarioAdmin(branchReport);
const baseUrl = 'http://localhost';

const gotoAtBase = async (page, targetPath) => {
  await gotoWithRetry(page, new URL(targetPath, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page).not.toHaveURL(/\/login$/);
};

test.describe.configure({ mode: 'serial' });

test('scenario-lab pro buttons connect source-of-truth, services, reports, approvals, and state history', async ({ page }) => {
  test.slow();
  test.setTimeout(150000);
  const guards = attachPageGuards(page);

  await loginLiveUserAtBase(page, baseUrl, { ...hybridCredentials, locale: 'ko' });

  await gotoAtBase(page, '/source-of-truth');
  await expect(page.getByTestId('source-of-truth-page')).toBeVisible({ timeout: 45000 });

  await page.getByTestId('source-of-truth-open-monitoring-profiles').click();
  await expect(page).toHaveURL(/\/monitoring-profiles(?:[/?#]|$)/);

  await gotoAtBase(page, '/source-of-truth');
  await page.getByTestId('source-of-truth-open-service-groups').click();
  await expect(page).toHaveURL(/\/service-groups(?:[/?#]|$)/);

  await gotoAtBase(page, '/source-of-truth');
  await page.getByTestId('source-of-truth-open-state-history').click();
  await expect(page).toHaveURL(/\/state-history(?:[/?#]|$)/);

  await gotoAtBase(page, '/source-of-truth');
  await page.getByTestId('source-of-truth-open-inventory').click();
  await expect(page).toHaveURL(/\/devices(?:[/?#]|$)/);

  guards.assertClean();
  guards.reset();

  await gotoAtBase(page, '/service-groups');
  await page.getByRole('button', { name: new RegExp(`\\[LAB ${hybridReport.slug}\\]`) }).first().click();
  await page.getByRole('button', { name: /Open Topology|토폴로지 열기/i }).last().click();
  await expect(page).toHaveURL(/\/topology(?:[/?#]|$)/);

  guards.assertClean();
  guards.reset();

  await gotoAtBase(page, '/operations-reports');
  await expect(page.getByTestId('operations-reports-page')).toBeVisible({ timeout: 30000 });

  await expect(page.getByTestId('operations-reports-download-review-bundle')).toBeVisible();
  await expect(page.getByTestId('operations-reports-download-operator-package')).toBeVisible();
  await expect(page.getByRole('button', { name: /Download Release Evidence Bundle|릴리즈 증적 번들/i })).toBeVisible();
  await expect(page.getByRole('button', { name: /Download Compliance Export|컴플라이언스 내보내기/i })).toBeVisible();

  await page.getByRole('button', { name: /Open Dashboard|대시보드 열기/i }).click();
  await expect(page).toHaveURL(/\/(?:[?#].*)?$/);

  await gotoAtBase(page, '/operations-reports');
  if (await page.getByRole('button', { name: /Open Notifications|알림 열기/i }).count()) {
    await page.getByRole('button', { name: /Open Notifications|알림 열기/i }).first().click();
    await expect(page).toHaveURL(/\/notifications(?:[/?#]|$)/);
    await gotoAtBase(page, '/operations-reports');
  }

  await page.getByTestId('operations-reports-open-approval-center').click();
  await expect(page).toHaveURL(/\/approval(?:[/?#]|$)/);
  await expect(page.locator('main')).toContainText(/Approval|승인/, { timeout: 30000 });

  await gotoAtBase(page, '/state-history');
  await expect(page.getByTestId('state-history-page')).toBeVisible({ timeout: 30000 });

  guards.assertClean();
  guards.reset();

  await gotoAtBase(page, '/notifications');
  const openStateHistory = page.locator('[data-testid^="issue-open-state-history-"]').first();
  if (await openStateHistory.count()) {
    await openStateHistory.waitFor({ state: 'visible', timeout: 15000 });
    await openStateHistory.click();
    await expect(page).toHaveURL(/\/state-history(?:[/?#]|$)/);
  } else {
    await expect(
      page.locator(
        '[data-testid="notifications-service-impact-focus"], [data-testid="notifications-service-priority-focus"], [data-testid="notifications-filter-service-impact"]',
      ).first(),
    ).toBeVisible({ timeout: 30000 });
  }

  guards.assertClean();
});

test('scenario-lab pro no-cloud scenario renders empty cloud account state cleanly', async ({ page }) => {
  test.slow();
  const guards = attachPageGuards(page);

  await loginLiveUserAtBase(page, baseUrl, { ...branchCredentials, locale: 'ko' });

  const accountsResponse = await fetchJsonWithAuth(page, '/api/v1/cloud/accounts');
  expect(accountsResponse.status).toBe(200);
  expect(unwrapCollection(accountsResponse.data)).toHaveLength(0);

  await gotoAtBase(page, '/cloud/accounts');

  const pageRoot = page.getByTestId('cloud-accounts-page');
  await expect(pageRoot).toBeVisible({ timeout: 30000 });
  await expect(page.locator('[data-testid^="cloud-account-row-"]')).toHaveCount(0, { timeout: 30000 });
  await expect(pageRoot).toContainText(/No accounts registered|등록된 계정이 없습니다/i, { timeout: 30000 });

  guards.assertClean();
});
