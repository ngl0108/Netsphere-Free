import { test, expect } from '@playwright/test';

import {
  attachPageGuards,
  buildScenarioMatchers,
  fetchJsonWithAuth,
  loadScenarioReportsByPrefix,
  loginLiveUser,
  pickScenarioAdmin,
  waitForPath,
  unwrapCollection,
} from './scenario-lab-live.helpers';

const reports = loadScenarioReportsByPrefix('pro');
test.describe.configure({ mode: 'serial' });

for (const report of reports) {
  test(`scenario-lab pro ${report.slug} login and seeded operations surfaces work`, async ({ page }) => {
    test.slow();
    const credentials = pickScenarioAdmin(report);
    const matchers = buildScenarioMatchers(report);
    const guards = attachPageGuards(page);

    await loginLiveUser(page, credentials);

    await page.goto('/devices');
    await expect(page).not.toHaveURL(/\/login$/);
    const devicesResponse = await fetchJsonWithAuth(page, '/api/v1/devices/?limit=1000');
    expect(devicesResponse.status).toBe(200);
    const devices = unwrapCollection(devicesResponse.data);
    expect(Array.isArray(devices)).toBeTruthy();
    expect(devices.length).toBeGreaterThan(0);
    expect(
      devices.some(
        (row) => String(row?.name || '').includes(matchers.deviceName),
      ),
    ).toBeTruthy();

    await page.goto('/service-groups');
    await expect(page).not.toHaveURL(/\/login$/);
    const serviceGroupsResponse = await fetchJsonWithAuth(page, '/api/v1/service-groups/');
    expect(serviceGroupsResponse.status).toBe(200);
    const serviceGroups = unwrapCollection(serviceGroupsResponse.data);
    expect(Array.isArray(serviceGroups)).toBeTruthy();
    expect(serviceGroups.length).toBeGreaterThan(0);
    expect(
      serviceGroups.some(
        (row) => String(row?.name || '').includes(matchers.groupNameFragment),
      ),
    ).toBeTruthy();

    await page.goto('/source-of-truth');
    await expect(page).not.toHaveURL(/\/login$/);
    const sourceOfTruthResponse = await fetchJsonWithAuth(page, '/api/v1/automation-hub/source-of-truth/summary');
    expect(sourceOfTruthResponse.status).toBe(200);
    expect(Number(sourceOfTruthResponse?.data?.metrics?.devices_total || 0)).toBeGreaterThan(0);

    await page.goto('/intent-templates');
    await expect(page).not.toHaveURL(/\/login$/);
    const useTemplateButton = page.getByRole('button', { name: /Use Template|템플릿 사용/ }).first();
    await expect(useTemplateButton).toBeVisible();
    await useTemplateButton.click();
    await waitForPath(page, /\/cloud\/intents/);
    await expect(page.getByTestId('cloud-intents-prefill')).toBeVisible();
    await expect(page.getByRole('button', { name: /Validate|검증/ })).toBeVisible();

    await page.goto('/preventive-checks');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(page.getByRole('button', { name: /Run now|지금 실행/ }).first()).toBeVisible();

    await page.goto('/operations-reports');
    await expect(page).not.toHaveURL(/\/login$/);
    const openApprovalCenterButton = page.getByRole('button', { name: /Open Approval Center|승인 센터 열기/ }).first();
    await expect(openApprovalCenterButton).toBeVisible();
    await openApprovalCenterButton.click();
    await waitForPath(page, /\/approval/);

    await page.goto('/notifications');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect
      .poll(async () => {
        const bodyText = await page.locator('body').innerText().catch(() => '');
        return bodyText;
      }, { timeout: 20000 })
      .toMatch(/알림|Notifications|Active Alarms Center/);
    await expect(page.getByTestId('policy-blocked-page')).not.toBeVisible();

    if (Number(report?.counts?.cloud_accounts || 0) > 0) {
      await page.goto('/cloud/accounts');
      await expect(page).not.toHaveURL(/\/login$/);
      const cloudAccountsResponse = await fetchJsonWithAuth(page, '/api/v1/cloud/accounts');
      expect(cloudAccountsResponse.status).toBe(200);
      const cloudAccounts = unwrapCollection(cloudAccountsResponse.data);
      expect(Array.isArray(cloudAccounts)).toBeTruthy();
      expect(cloudAccounts.length).toBeGreaterThanOrEqual(Number(report.counts.cloud_accounts));
    }

    guards.assertClean();
  });
}
