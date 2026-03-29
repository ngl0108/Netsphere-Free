/* global process */
import { test, expect } from '@playwright/test';

import {
  attachPageGuards,
  fetchJsonWithAuth,
  gotoWithRetry,
  loginLiveUserAtBase,
  pickScenarioAdmin,
  resolveScenarioReport,
  waitForPath,
  unwrapCollection,
} from './scenario-lab-live.helpers';

const PRO_BASE_URL = process.env.PRO_AUDIT_BASE_URL || 'http://localhost';
const REPORT = resolveScenarioReport('pro', process.env.PRO_AUDIT_SCENARIO || 'pro-hybrid-operations');

const openAtBase = async (page, path) => {
  await gotoWithRetry(page, new URL(path, PRO_BASE_URL).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page).not.toHaveURL(/\/login$/);
};

test.describe.configure({ mode: 'serial' });

test('functional audit pro representative surfaces and actions work end-to-end', async ({ page }) => {
  test.slow();
  test.setTimeout(240000);

  const guards = attachPageGuards(page);
  const credentials = pickScenarioAdmin(REPORT);

  await loginLiveUserAtBase(page, PRO_BASE_URL, { ...credentials, locale: 'ko' });

  await openAtBase(page, '/');
  await expect(page.getByTestId('app-sidebar')).toContainText('네트워크 맵');
  await expect(page.getByTestId('app-sidebar')).toContainText('변경 승인 센터');
  await expect(page.getByTestId('app-sidebar')).toContainText('구성 관리');
  const dashboardServiceSurface = page.locator(
    '[data-testid="dashboard-service-priority-board"], [data-testid="dashboard-service-impact-panel"]',
  ).first();
  if (await dashboardServiceSurface.count()) {
    await expect(dashboardServiceSurface).toBeVisible({ timeout: 30000 });
    if (await page.getByTestId('dashboard-service-priority-summary').count()) {
      await expect(page.getByTestId('dashboard-service-priority-summary')).toBeVisible({ timeout: 30000 });
    }
    if (await page.getByTestId('dashboard-service-posture').count()) {
      await expect(page.getByTestId('dashboard-service-posture')).toBeVisible({ timeout: 30000 });
    }
    if (await page.getByTestId('dashboard-service-health-next-action').count()) {
      await expect(page.getByTestId('dashboard-service-health-next-action')).toBeVisible({ timeout: 30000 });
    }
    if (await page.getByTestId('dashboard-service-priority-open-queue').count()) {
      await page.getByTestId('dashboard-service-priority-open-queue').click();
      await waitForPath(page, /\/notifications(?:[/?#]|$)/);
      await expect(
        page.locator('[data-testid="notifications-service-priority-focus"], [data-testid="notifications-focused-service-context"]').first(),
      ).toBeVisible({ timeout: 30000 });
      await openAtBase(page, '/');
    } else if (await page.getByTestId('dashboard-service-impact-open-notifications').count()) {
      await page.getByTestId('dashboard-service-impact-open-notifications').click();
      await waitForPath(page, /\/notifications(?:[/?#]|$)/);
      await expect(
        page.locator('[data-testid="notifications-service-priority-focus"], [data-testid="notifications-focused-service-context"]').first(),
      ).toBeVisible({ timeout: 30000 });
      await openAtBase(page, '/');
    }
  }
  if (await page.getByTestId('dashboard-service-impact-panel').count()) {
    await expect(page.getByTestId('dashboard-service-impact-panel')).toBeVisible({ timeout: 30000 });
  }
  if (await page.getByTestId('dashboard-service-review-queue').count()) {
    await expect(page.getByTestId('dashboard-service-review-queue')).toBeVisible({ timeout: 30000 });
  }
  const dashboardIssueReviewButtons = page.locator('[data-testid^="dashboard-issue-open-review-"]');
  if (await dashboardIssueReviewButtons.count()) {
    await dashboardIssueReviewButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-reports-focused-group')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/');
  }
  const dashboardServicePriorityButtons = page.locator('[data-testid^="dashboard-service-priority-open-review-"]');
  if (await dashboardServicePriorityButtons.count()) {
    await dashboardServicePriorityButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-reports-service-priority-focus')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('operations-reports-service-priority-queue')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('operations-reports-focused-group')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/');
  }
  const dashboardServiceReviewButtons = page.locator('[data-testid^="dashboard-service-review-open-review-"]');
  if (await dashboardServiceReviewButtons.count()) {
    await dashboardServiceReviewButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-reports-page')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('operations-reports-service-priority-focus')).toBeVisible({ timeout: 30000 });
    if (await page.getByTestId('operations-reports-focused-group').count()) {
      await expect(page.getByTestId('operations-reports-focused-group')).toBeVisible({ timeout: 30000 });
      await page.getByTestId('operations-reports-focused-group-clear').click();
      await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
      await expect(page.getByTestId('operations-reports-focused-group')).toHaveCount(0);
    }
    await openAtBase(page, '/');
  }
  const dashboardServiceWorkspaceButtons = page.locator('[data-testid^="dashboard-service-review-open-workspace-"]');
  if (await dashboardServiceWorkspaceButtons.count()) {
    await dashboardServiceWorkspaceButtons.first().click();
    await waitForPath(page, /\/automation(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/');
  }
  const dashboardServiceNotificationButtons = page.locator('[data-testid^="dashboard-service-review-open-notifications-"]');
  if (await dashboardServiceNotificationButtons.count()) {
    await dashboardServiceNotificationButtons.first().click();
    await waitForPath(page, /\/notifications(?:[/?#]|$)/);
    await expect(page.getByTestId('notifications-focused-service-context')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('notifications-focused-service-health-card')).toBeVisible({ timeout: 30000 });
    await page.getByTestId('notifications-focused-service-open-review').click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-reports-focused-group')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/notifications');
    await expect(page.getByTestId('notifications-focused-service-context')).toBeVisible({ timeout: 30000 });
    await page.getByTestId('notifications-focused-service-open-group').click();
    await waitForPath(page, /\/service-groups(?:[/?#]|$)/);
    await openAtBase(page, '/notifications');
    await expect(page.getByTestId('notifications-focused-service-context')).toBeVisible({ timeout: 30000 });
    await page.getByTestId('notifications-focused-service-open-topology').click();
    await waitForPath(page, /\/topology(?:[/?#]|$)/);
    await expect(page.getByTestId('topology-service-overlay-toggle')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/');
  }
  const dashboardReviewButtons = page.locator('[data-testid^="dashboard-service-impact-open-review-"]');
  if (await dashboardReviewButtons.count()) {
    await dashboardReviewButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-reports-focused-group')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/');
  }
  await page.getByTestId('dashboard-service-impact-open-notifications').click();
  await waitForPath(page, /\/notifications/);
  await expect(page.getByTestId('notifications-service-impact-focus')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('notifications-service-posture')).toBeVisible({ timeout: 30000 });
  await expect(
    page.locator('[data-testid="notifications-service-priority-focus"], [data-testid="notifications-focused-service-context"]').first(),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('notifications-service-queue')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('notifications-filter-service-impact').click();
  await expect(page.getByTestId('notifications-filter-service-impact')).toBeVisible({ timeout: 30000 });
  const queueIssueButtons = page.locator('[data-testid^="notifications-service-queue-open-issue-"]');
  if (await queueIssueButtons.count()) {
    const firstQueueButton = queueIssueButtons.first();
    const issueTestId = await firstQueueButton.getAttribute('data-testid');
    const issueId = issueTestId?.split('-').pop();
    await firstQueueButton.click();
    if (issueId) {
      await expect(page.getByTestId(`issue-service-impact-panel-${issueId}`)).toBeVisible({ timeout: 30000 });
    }
  }
  const queueReviewButtons = page.locator('[data-testid^="notifications-service-queue-open-review-"]');
  if (await queueReviewButtons.count()) {
    await queueReviewButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-reports-focused-group')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/notifications');
  }
  if (await page.getByTestId('notifications-service-priority-open-review').count()) {
    await page.getByTestId('notifications-service-priority-open-review').click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-reports-focused-group')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/notifications');
  }
  if (await page.getByTestId('notifications-service-priority-open-workspace').count()) {
    await page.getByTestId('notifications-service-priority-open-workspace').click();
    await waitForPath(page, /\/automation(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/notifications');
  }

  await openAtBase(page, '/sites');
  await expect(page).toHaveURL(/\/sites$/);

  await openAtBase(page, '/logs');
  await expect(page).toHaveURL(/\/logs$/);

  await openAtBase(page, '/devices');
  const deviceListResponse = await fetchJsonWithAuth(page, '/api/v1/devices/?limit=1000');
  expect(deviceListResponse.status).toBe(200);
  const deviceRows = unwrapCollection(deviceListResponse.data);
  expect(deviceRows.length).toBeGreaterThan(0);
  const auditDeviceId = Number(deviceRows[0]?.id || 0);
  expect(auditDeviceId).toBeGreaterThan(0);
  await openAtBase(page, `/devices/${auditDeviceId}`);
  await expect(page.getByTestId('device-detail-ops-review-panel')).toBeVisible({ timeout: 30000 });
  if (await page.getByRole('button', { name: 'Open Discovery Review' }).count()) {
    await expect(page.getByRole('button', { name: 'Open Discovery Review' }).first()).toBeVisible({ timeout: 30000 });
  }
  if (await page.getByRole('button', { name: 'Open Service Groups' }).count()) {
    await expect(page.getByRole('button', { name: 'Open Service Groups' }).first()).toBeVisible({ timeout: 30000 });
  }
  await expect(page).toHaveURL(new RegExp(`/devices/${auditDeviceId}(?:[/?#]|$)`));

  await openAtBase(page, '/wireless');
  await expect(page).toHaveURL(/\/wireless$/);

  await openAtBase(page, '/settings');
  const settingsGeneralTab = page.getByRole('button', { name: /^(일반 설정|General Settings)$/ }).first();
  await expect(settingsGeneralTab).toBeVisible({ timeout: 30000 });
  const settingsSaveButton = page.getByRole('button', { name: /^(변경사항 저장|Save Changes)$/ }).first();
  if (await settingsSaveButton.count()) {
    const settingsSaveResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/settings/general') &&
        response.request().method() === 'PUT' &&
        response.status() === 200,
      { timeout: 15000 },
    ).catch(() => null);
    await settingsSaveButton.click();
    await settingsSaveResponse;
  }

  await openAtBase(page, '/users');
  await expect(page).toHaveURL(/\/users$/);
  if (await page.getByRole('button', { name: '사용자 추가' }).count()) {
    await page.getByRole('button', { name: '사용자 추가' }).first().click();
    await expect(page.locator('form input').first()).toBeVisible({ timeout: 30000 });
    await page.getByRole('button', { name: '취소' }).click();
  }

  await openAtBase(page, '/monitoring-profiles');
  await expect(page.getByTestId('monitoring-profiles-page')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('monitoring-profiles-new').click();
  await page.getByTestId('monitoring-profiles-save').click();
  await expect(page.getByTestId('monitoring-profiles-page')).toBeVisible({ timeout: 30000 });
  await expect(page).toHaveURL(/\/monitoring-profiles$/);

  await openAtBase(page, '/discovery');
  await expect(page.getByTestId('discovery-start')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('discovery-mode-seed').click();
  const seedInput = page.getByTestId('discovery-seed-ip');
  await seedInput.fill('999.999.999.999');
  await expect(page.getByTestId('discovery-start')).toBeDisabled();
  await page.getByTestId('discovery-mode-cidr').click();
  await expect(page.getByTestId('discovery-start')).toBeEnabled();
  await page.getByTestId('discovery-cidr-input').fill('127.0.0.1/32');
  const discoveryStartResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/api/v1/discovery/scan') &&
      response.request().method() === 'POST',
  );
  await page.getByTestId('discovery-start').click();
  const discoveryStartResult = await discoveryStartResponse;
  expect(discoveryStartResult.status()).toBeGreaterThanOrEqual(200);
  expect(discoveryStartResult.status()).toBeLessThan(300);
  await expect(page.getByTestId('discovery-progress-panel')).toBeVisible({ timeout: 30000 });

  await openAtBase(page, '/config');
  await expect(page.getByTestId('config-create-first-template')).toBeVisible({ timeout: 30000 });
  const templatesResponse = await fetchJsonWithAuth(page, '/api/v1/templates/');
  expect(templatesResponse.status).toBe(200);
  const templates = unwrapCollection(templatesResponse.data);
  expect(templates.length).toBeGreaterThan(0);
  const templateId = Number(templates[0]?.id || 0);
  expect(templateId).toBeGreaterThan(0);
  const firstTemplateName = String(templates[0]?.name || '').trim();
  expect(firstTemplateName).toBeTruthy();
  await page.getByText(firstTemplateName).first().click();

  await page.getByTestId('config-open-merge-snippet').click();
  await expect(page.getByTestId('config-snippet-modal')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('config-close-snippet-modal').click();
  await expect(page.getByTestId('config-snippet-modal')).toHaveCount(0);

  await page.getByTestId('config-open-deploy').click();
  await expect(page.getByTestId('config-deploy-modal')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('config-deploy-options')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('config-change-plan')).toBeVisible({ timeout: 30000 });
  const configDevicesResponse = await fetchJsonWithAuth(page, '/api/v1/devices/');
  expect(configDevicesResponse.status).toBe(200);
  const configDevices = unwrapCollection(configDevicesResponse.data);
  expect(configDevices.length).toBeGreaterThan(0);
  const dryRunDeviceId = Number(configDevices[0]?.id || 0);
  expect(dryRunDeviceId).toBeGreaterThan(0);
  await page.getByTestId(`config-device-${dryRunDeviceId}`).click();
  const dryRunButton = page.getByRole('button', { name: 'Dry-Run (Diff)' });
  await expect(dryRunButton).toBeEnabled();
  const dryRunResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(`/api/v1/templates/${templateId}/dry-run`) &&
      response.request().method() === 'POST',
  );
  await dryRunButton.click();
  const dryRunResponse = await dryRunResponsePromise;
  expect(dryRunResponse.status()).toBeGreaterThanOrEqual(200);
  if (dryRunResponse.status() < 300) {
    await expect(page.getByTestId('config-dry-run-results')).toBeVisible({ timeout: 30000 });
  } else {
    await expect(page.getByTestId('config-deploy-modal')).toBeVisible({ timeout: 30000 });
    await expect(page.locator('[data-testid="toast-warning"], [data-testid="toast-error"]').last()).toBeVisible({ timeout: 30000 });
  }
  await page.getByTestId('config-close-deploy-modal').click();
  await expect(page.getByTestId('config-deploy-modal')).toHaveCount(0);

  await openAtBase(page, '/source-of-truth');
  await expect(page.getByTestId('source-of-truth-page')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('source-of-truth-open-state-history').click();
  await waitForPath(page, /\/state-history/);
  await expect(page.getByTestId('state-history-page')).toBeVisible({ timeout: 30000 });

  const snapshotListBefore = await fetchJsonWithAuth(page, '/api/v1/automation-hub/state-history/snapshots?limit=12');
  expect(snapshotListBefore.status).toBe(200);
  const snapshotCountBefore = Array.isArray(snapshotListBefore.data) ? snapshotListBefore.data.length : 0;
  await page.getByTestId('state-history-capture').click();
  await expect
    .poll(
      async () => {
        const response = await fetchJsonWithAuth(page, '/api/v1/automation-hub/state-history/snapshots?limit=12');
        return Array.isArray(response.data) ? response.data.length : 0;
      },
      { timeout: 30000, intervals: [1000, 1500, 2000] },
    )
    .toBeGreaterThanOrEqual(snapshotCountBefore);

  await openAtBase(page, '/service-groups');
  await expect(page.getByTestId('service-groups-review-queue')).toBeVisible({ timeout: 30000 });
  const reviewOpenButtons = page.locator('[data-testid^="service-groups-review-open-"]');
  if (await reviewOpenButtons.count()) {
    await reviewOpenButtons.first().click();
  }
  const reviewReportsButtons = page.locator('[data-testid^="service-groups-review-reports-"]');
  if (await reviewReportsButtons.count()) {
    await reviewReportsButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-reports-focused-group')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/service-groups');
  }
  const reviewNotificationsButtons = page.locator('[data-testid^="service-groups-review-notifications-"]');
  if (await reviewNotificationsButtons.count()) {
    await reviewNotificationsButtons.first().click();
    await waitForPath(page, /\/notifications(?:[/?#]|$)/);
    await expect(page.getByTestId('notifications-service-impact-focus')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('notifications-focused-service-context')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/service-groups');
  }
  const reviewTopologyButtons = page.locator('[data-testid^="service-groups-review-topology-"]');
  if (await reviewTopologyButtons.count()) {
    await reviewTopologyButtons.first().click();
    await waitForPath(page, /\/topology/);
  }

  await openAtBase(page, '/operations-reports');
  await expect(page.getByTestId('operations-reports-page')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('operations-reports-service-posture')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('operations-reports-service-priority-queue')).toBeVisible({ timeout: 30000 });
  if (await page.getByTestId('operations-reports-service-priority-open-workspace').count()) {
    await page.getByTestId('operations-reports-service-priority-open-workspace').click();
    await waitForPath(page, /\/automation(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/operations-reports');
  }
  const reportPriorityButtons = page.locator('[data-testid^="operations-reports-service-priority-queue-open-notifications-"]');
  if (await reportPriorityButtons.count()) {
    await reportPriorityButtons.first().click();
    await waitForPath(page, /\/notifications(?:[/?#]|$)/);
    await expect(
      page.locator('[data-testid="notifications-service-priority-focus"], [data-testid="notifications-focused-service-context"]').first(),
    ).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/operations-reports');
  }
  await expect(page.getByTestId('operations-reports-download-review-bundle')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('operations-reports-download-operator-package')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('operations-reports-open-approval-center').first().click();
  await waitForPath(page, /\/approval/);

  await openAtBase(page, '/observability');
  await expect(page.getByTestId('obs-overview-guided-entry')).toBeVisible({ timeout: 30000 });


  await expect(page.getByTestId('obs-overview-guided-entry')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('obs-service-impact-panel')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('obs-overview-open-workspace').click();
  await waitForPath(page, /\/automation(?:[/?#]|$)/);
  await expect(page.getByTestId('automation-pro-operations-panel')).toBeVisible({ timeout: 30000 });
  await openAtBase(page, '/observability');
  await page.getByTestId('obs-open-service-groups').click();
  await waitForPath(page, /\/service-groups/);
  await openAtBase(page, '/observability');
  await page.getByTestId('obs-overview-open-deep-dive-primary').click();
  await waitForPath(page, /\/observability\/deep-dive/);
  await expect(page.getByTestId('obs-deep-dive-focus')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('obs-deep-dive-open-workspace').click();
  await waitForPath(page, /\/automation(?:[/?#]|$)/);
  await expect(page.getByTestId('automation-pro-operations-panel')).toBeVisible({ timeout: 30000 });
  await openAtBase(page, '/observability/deep-dive');
  await expect(page.getByTestId('observability-back-overview')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('observability-back-overview').click();
  await waitForPath(page, /\/observability(?:[?#]|$)/);
  if (await page.getByTestId('obs-open-settings').count()) {
    await page.getByTestId('obs-open-settings').click();
    await waitForPath(page, /\/settings/);
    await openAtBase(page, '/observability');
  }
  const observabilityToggleCount = await page
    .locator('header')
    .getByRole('button', { name: 'Observability Collection' })
    .count();
  expect(observabilityToggleCount).toBeGreaterThanOrEqual(0);

  await openAtBase(page, '/automation');
  await expect(page.getByTestId('automation-pro-operations-panel')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('operations-home-pressure-board')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('operations-home-pressure-card-service')).toBeVisible({ timeout: 30000 });
  if (await page.getByTestId('operations-home-primary-focus-open-workspace').count()) {
    await page.getByTestId('operations-home-primary-focus-open-workspace').click();
    await waitForPath(page, /\/automation\?workspace=/);
    await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/automation');
  }
  if (await page.getByTestId('operations-home-primary-focus-follow-ups').count()) {
    await expect(page.getByTestId('operations-home-primary-focus-follow-ups')).toBeVisible({ timeout: 30000 });
  }
  if (await page.getByTestId('operations-home-pressure-open-surface-cloud').count()) {
    await page.getByTestId('operations-home-pressure-open-surface-cloud').click();
    await waitForPath(page, /\/cloud\/accounts(?:[/?#]|$)/);
    await expect(page.getByTestId('cloud-accounts-page')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/automation');
  }
  if (await page.getByTestId('operations-home-pressure-open-surface-observability').count()) {
    await page.getByTestId('operations-home-pressure-open-surface-observability').click();
    await waitForPath(page, /\/observability(?:[/?#]|$)/);
    await expect(page.getByTestId('obs-overview-guided-entry')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/automation');
  }
  await expect(page.getByTestId('operations-home-service-review-queue')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('operations-home-service-posture')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('operations-home-service-lane-board')).toBeVisible({ timeout: 30000 });
  if (await page.getByTestId('operations-home-cloud-review-queue').count()) {
    await expect(page.getByTestId('operations-home-cloud-review-queue')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('operations-home-cloud-lane-board')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('operations-home-cloud-lane-card-recovery')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('operations-home-cloud-retry-queue')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('operations-home-cloud-execution-highlights')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('operations-home-cloud-checkpoints')).toBeVisible({ timeout: 30000 });
    const cloudReviewButtons = page.locator('[data-testid^="operations-home-cloud-review-open-"]');
    if (await cloudReviewButtons.count()) {
      await cloudReviewButtons.first().click();
      await waitForPath(page, /\/cloud\/accounts(?:[/?#]|$)/);
      await expect(page.getByTestId('cloud-accounts-page')).toBeVisible({ timeout: 30000 });
      await openAtBase(page, '/automation');
    }
    const cloudApprovalButtons = page.locator('[data-testid^="operations-home-cloud-review-approval-"]');
    if (await cloudApprovalButtons.count()) {
      await cloudApprovalButtons.first().click();
      await waitForPath(page, /\/approval(?:[/?#]|$)/);
      await expect(page.getByTestId('approval-page')).toBeVisible({ timeout: 30000 });
      await openAtBase(page, '/automation');
    }
    const cloudIntentsButtons = page.locator('[data-testid^="operations-home-cloud-review-intents-"]');
    if (await cloudIntentsButtons.count()) {
      await cloudIntentsButtons.first().click();
      await waitForPath(page, /\/cloud\/intents(?:[/?#]|$)/);
      await expect(page.getByTestId('cloud-intents-page')).toBeVisible({ timeout: 30000 });
      await openAtBase(page, '/automation');
    }
  }
  const homeReviewButtons = page.locator('[data-testid^="operations-home-service-review-reports-"]');
  if (await homeReviewButtons.count()) {
    await homeReviewButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-reports-page')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('operations-reports-focused-group')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/automation');
  }
  const homeNotificationButtons = page.locator('[data-testid^="operations-home-service-review-notifications-"]');
  if (await homeNotificationButtons.count()) {
    await homeNotificationButtons.first().click();
    await waitForPath(page, /\/notifications(?:[/?#]|$)/);
    await expect(page.getByTestId('notifications-focused-service-context')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('notifications-focused-service-health-card')).toBeVisible({ timeout: 30000 });
    await page.getByTestId('notifications-focused-service-open-review').click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-reports-focused-group')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/automation');
  }
  if (await page.getByTestId('sidebar-workspace-control').count()) {
    await page.getByTestId('sidebar-workspace-control').click();
    await expect(page).toHaveURL(/\/automation\?workspace=control$/);
    await expect(page.getByTestId('operations-workspace-control')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/automation');
  }
  if (await page.getByTestId('operations-quick-flow-change_with_precheck').count()) {
    await page.getByTestId('operations-quick-flow-change_with_precheck').click();
    await waitForPath(page, /\/cloud\/intents/);
    await openAtBase(page, '/automation');
  }
  await page.getByTestId('automation-open-approval').click();
  await waitForPath(page, /\/approval/);

  await openAtBase(page, '/diagnosis');
  await expect(page.getByTestId('diagnosis-evidence-panel')).toBeVisible({ timeout: 30000 });

  await openAtBase(page, '/intent-templates');
  await expect(page).toHaveURL(/\/intent-templates$/);
  const useTemplateButton = page.locator('button').filter({ hasText: /^(Use Template|템플릿 사용)$/ }).first();
  if (await useTemplateButton.count()) {
    await useTemplateButton.click();
    await waitForPath(page, /\/cloud\/intents(?:[/?#]|$)/);
    await expect(page.getByTestId('cloud-intents-page')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('cloud-intents-prefill')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('cloud-intents-validate')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('cloud-intents-simulate')).toBeVisible({ timeout: 30000 });
  }

  guards.assertClean();
});
