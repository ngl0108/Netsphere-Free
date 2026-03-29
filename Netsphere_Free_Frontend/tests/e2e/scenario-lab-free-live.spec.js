import { test, expect } from '@playwright/test';

import {
  attachPageGuards,
  buildScenarioMatchers,
  fetchJsonWithAuth,
  loadScenarioReportsByPrefix,
  loginLiveUser,
  pickScenarioAdmin,
  unwrapCollection,
} from './scenario-lab-live.helpers';

const reports = loadScenarioReportsByPrefix('free');
test.describe.configure({ mode: 'serial' });

for (const report of reports) {
  test(`scenario-lab free ${report.slug} login and guarded surfaces work`, async ({ page }) => {
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
    expect(devices.some((row) => String(row?.name || '').includes(matchers.deviceName))).toBeTruthy();

    const managedSummaryResponse = await fetchJsonWithAuth(page, '/api/v1/devices/managed-summary');
    expect(managedSummaryResponse.status).toBe(200);
    expect(Number(managedSummaryResponse?.data?.managed_limit || 0)).toBe(50);

    const previewPolicyResponse = await fetchJsonWithAuth(page, '/api/v1/preview/policy');
    expect(previewPolicyResponse.status).toBe(200);
    expect(Boolean(previewPolicyResponse?.data?.upload_decision_recorded)).toBeTruthy();
    expect(Boolean(previewPolicyResponse?.data?.upload_locked)).toBeTruthy();

    await page.goto('/automation');
    await expect(page.getByTestId('automation-preview-panel')).toBeVisible();
    await expect(page.getByTestId('automation-preview-title')).toContainText(/NetSphere Free 경험|NetSphere Free Experience/);
    await expect(page.getByTestId('automation-preview-desc')).toContainText(/오토 디스커버리|Auto Discovery/);
    await expect(page.getByTestId('automation-preview-pillar-auto_discovery')).toContainText(/오토 디스커버리|Auto Discovery/);
    await expect(page.getByTestId('automation-preview-blocked-features')).toContainText(/차단됨|Blocked:/);

    const managedDevice = devices.find((row) => String(row?.management_state || '').trim().toLowerCase() === 'managed');
    const discoveredDevice = devices.find((row) => String(row?.management_state || '').trim().toLowerCase() !== 'managed');
    expect(managedDevice?.name).toBeTruthy();
    expect(discoveredDevice?.name).toBeTruthy();

    await page.goto('/devices');
    const managedRow = page.locator('tr', { hasText: managedDevice.name }).first();
    await expect(managedRow).toBeVisible();
    await managedRow.hover();
    await managedRow.getByRole('button', { name: /Release Slot|슬롯 해제/ }).click({ force: true });
    await expect
      .poll(async () => {
        const response = await fetchJsonWithAuth(page, '/api/v1/devices/managed-summary');
        return Number(response?.data?.remaining_slots || 0);
      })
      .toBeGreaterThan(0);

    const discoveredRow = page.locator('tr', { hasText: discoveredDevice.name }).first();
    await expect(discoveredRow).toBeVisible();
    await discoveredRow.hover();
    await discoveredRow.getByRole('button', { name: /Make Managed|관리 대상으로 지정/ }).click({ force: true });
    await expect
      .poll(async () => {
        const response = await fetchJsonWithAuth(page, '/api/v1/devices/?limit=1000');
        const rows = unwrapCollection(response.data);
        return String(rows.find((row) => Number(row?.id) === Number(discoveredDevice.id))?.management_state || '');
      })
      .toBe('managed');

    await page.goto('/preview/contribute');
    await expect(page.getByText(/Data Handling Audit|데이터 처리 감사/)).toBeVisible();
    await expect(page.getByText(/Locked installation policy|잠긴 설치 정책/)).toBeVisible();
    await expect(page.getByText(/Sanitized audit detail|마스킹 감사 상세|마스킹 적용 결과/)).toBeVisible();
    const recordButtons = page.locator('button').filter({ hasText: /^preview-/i });
    await expect(recordButtons.first()).toBeVisible();

    await page.goto('/service-groups');
    await expect(page.getByTestId('policy-blocked-page')).toBeVisible();

    await page.goto('/edition/compare');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(page.getByText(/관리 노드 50대까지|Managed up to 50 nodes/)).toBeVisible();

    guards.assertClean();
  });
}
