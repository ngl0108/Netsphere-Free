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

const FREE_BASE_URL = process.env.FREE_AUDIT_BASE_URL || 'http://127.0.0.1:18080';
const REPORT = resolveScenarioReport('free', process.env.FREE_AUDIT_SCENARIO || 'free-enterprise-visibility');

const openAtBase = async (page, path) => {
  await gotoWithRetry(page, new URL(path, FREE_BASE_URL).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page).not.toHaveURL(/\/login$/);
  await waitForPath(page, new RegExp(`${path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:\\?.*)?$`));
};

const BLOCKED_ROUTES = [
  '/config',
  '/cloud/accounts',
  '/preventive-checks',
  '/users',
  '/approval',
];

test.describe.configure({ mode: 'serial' });

test('functional audit free surfaces, policy blocks, and admin audit states behave correctly', async ({ page }) => {
  test.slow();
  test.setTimeout(240000);
  const guards = attachPageGuards(page);
  const credentials = pickScenarioAdmin(REPORT);
  const expectReportsLanding = async () => {
    const reportsPage = page.getByTestId('operations-reports-page');
    const blockedPage = page.getByTestId('policy-blocked-page');
    if (await reportsPage.count()) {
      await expect(reportsPage).toBeVisible({ timeout: 30000 });
      const focusedGroup = page.getByTestId('operations-reports-focused-group');
      if (await focusedGroup.count()) {
        await expect(focusedGroup).toBeVisible({ timeout: 30000 });
      }
    } else if (await blockedPage.count()) {
      await expect(blockedPage).toBeVisible({ timeout: 30000 });
    }
  };

  await loginLiveUserAtBase(page, FREE_BASE_URL, { ...credentials, locale: 'ko' });

  await openAtBase(page, '/');
  await expect(page.getByTestId('app-sidebar')).toContainText('네트워크 맵');
  await expect(page.getByTestId('app-sidebar')).toContainText('알람 센터');
  await expect(page.getByTestId('dashboard-service-priority-board')).toBeVisible({ timeout: 30000 });
  if (await page.getByTestId('dashboard-service-priority-summary').count()) {
    await expect(page.getByTestId('dashboard-service-priority-summary')).toBeVisible({ timeout: 30000 });
  }
  if (await page.getByTestId('dashboard-service-posture').count()) {
    await expect(page.getByTestId('dashboard-service-posture')).toBeVisible({ timeout: 30000 });
  }
  if (await page.getByTestId('dashboard-service-health-next-action').count()) {
    await expect(page.getByTestId('dashboard-service-health-next-action')).toBeVisible({ timeout: 30000 });
  }
  await page.getByTestId('dashboard-service-priority-open-queue').click();
  await waitForPath(page, /\/notifications(?:[/?#]|$)/);
  await expect(page.getByTestId('notifications-service-priority-focus')).toBeVisible({ timeout: 30000 });
  await openAtBase(page, '/');
  await expect(page.getByTestId('dashboard-service-impact-panel')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('dashboard-service-review-queue')).toBeVisible({ timeout: 30000 });
  const freeDashboardIssueReviewButtons = page.locator('[data-testid^="dashboard-issue-open-review-"]');
  if (await freeDashboardIssueReviewButtons.count()) {
    await freeDashboardIssueReviewButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expectReportsLanding();
    await openAtBase(page, '/');
  }
  const freeDashboardPriorityButtons = page.locator('[data-testid^="dashboard-service-priority-open-review-"]');
  if (await freeDashboardPriorityButtons.count()) {
    await freeDashboardPriorityButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expectReportsLanding();
    await openAtBase(page, '/');
  }
  const freeDashboardServiceReviewButtons = page.locator('[data-testid^="dashboard-service-review-open-review-"]');
  if (await freeDashboardServiceReviewButtons.count()) {
    await freeDashboardServiceReviewButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    const reportsPage = page.getByTestId('operations-reports-page');
    const blockedPage = page.getByTestId('policy-blocked-page');
    if (await reportsPage.count()) {
      await expect(reportsPage).toBeVisible({ timeout: 30000 });
    } else if (await blockedPage.count()) {
      await expect(blockedPage).toBeVisible({ timeout: 30000 });
    }
    await openAtBase(page, '/');
  }
  const freeDashboardServiceWorkspaceButtons = page.locator('[data-testid^="dashboard-service-review-open-workspace-"]');
  if (await freeDashboardServiceWorkspaceButtons.count()) {
    await freeDashboardServiceWorkspaceButtons.first().click();
    await waitForPath(page, /\/automation(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/');
  }
  const freeDashboardServiceNotificationButtons = page.locator('[data-testid^="dashboard-service-review-open-notifications-"]');
  if (await freeDashboardServiceNotificationButtons.count()) {
    await freeDashboardServiceNotificationButtons.first().click();
    await waitForPath(page, /\/notifications(?:[/?#]|$)/);
    await expect(page.getByTestId('notifications-focused-service-context')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('notifications-focused-service-health-card')).toBeVisible({ timeout: 30000 });
    await page.getByTestId('notifications-focused-service-open-review').click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expectReportsLanding();
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
    await expectReportsLanding();
    await openAtBase(page, '/');
  }
  await page.getByTestId('dashboard-service-impact-open-notifications').click();
  await waitForPath(page, /\/notifications/);
  await expect(page.getByTestId('notifications-service-impact-focus')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('notifications-service-posture')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('notifications-service-priority-focus')).toBeVisible({ timeout: 30000 });
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
    await expectReportsLanding();
    await openAtBase(page, '/notifications');
  }
  if (await page.getByTestId('notifications-service-priority-open-review').count()) {
    await page.getByTestId('notifications-service-priority-open-review').click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expectReportsLanding();
    await openAtBase(page, '/notifications');
  }
  if (await page.getByTestId('notifications-service-priority-open-workspace').count()) {
    await page.getByTestId('notifications-service-priority-open-workspace').click();
    await waitForPath(page, /\/automation(?:[/?#]|$)/);
    await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/notifications');
  }

  await openAtBase(page, '/automation');
  await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
  if (await page.getByTestId('operations-home-pressure-board').count()) {
    await expect(page.getByTestId('operations-home-pressure-board')).toBeVisible({ timeout: 30000 });
  }
  if (await page.getByTestId('operations-home-pressure-card-service').count()) {
    await expect(page.getByTestId('operations-home-pressure-card-service')).toBeVisible({ timeout: 30000 });
  }
  if (await page.getByTestId('operations-home-primary-focus-open-workspace').count()) {
    await page.getByTestId('operations-home-primary-focus-open-workspace').click();
    await waitForPath(page, /\/automation\?workspace=/);
    await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/automation');
  }
  if (await page.getByTestId('operations-home-primary-focus-follow-ups').count()) {
    await expect(page.getByTestId('operations-home-primary-focus-follow-ups')).toBeVisible({ timeout: 30000 });
  }
  if (await page.getByTestId('operations-home-pressure-open-surface-observability').count()) {
    await page.getByTestId('operations-home-pressure-open-surface-observability').click();
    await waitForPath(page, /\/observability(?:[/?#]|$)/);
    await expect(page.getByTestId('obs-overview-guided-entry')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/automation');
  }
  await page.getByTestId('sidebar-workspace-discover').click();
  await expect(page).toHaveURL(/\/automation\?workspace=discover$/);
  await expect(page.getByTestId('operations-workspace-discover')).toBeVisible({ timeout: 30000 });
  await openAtBase(page, '/automation');
  await expect(page.getByTestId('automation-preview-compare')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
  const freeServiceReviewQueue = page.getByTestId('operations-home-service-review-queue');
  if (await freeServiceReviewQueue.count()) {
    await expect(freeServiceReviewQueue).toBeVisible({ timeout: 30000 });
    if (await page.getByTestId('operations-home-service-posture').count()) {
      await expect(page.getByTestId('operations-home-service-posture')).toBeVisible({ timeout: 30000 });
    }
    if (await page.getByTestId('operations-home-service-lane-board').count()) {
      await expect(page.getByTestId('operations-home-service-lane-board')).toBeVisible({ timeout: 30000 });
    }
  }
  const freeHomeReviewButtons = page.locator('[data-testid^="operations-home-service-review-reports-"]');
  if (await freeHomeReviewButtons.count()) {
    await freeHomeReviewButtons.first().click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    const reportsPage = page.getByTestId('operations-reports-page');
    const blockedPage = page.getByTestId('policy-blocked-page');
    if (await reportsPage.count()) {
      await expect(reportsPage).toBeVisible({ timeout: 30000 });
    } else if (await blockedPage.count()) {
      await expect(blockedPage).toBeVisible({ timeout: 30000 });
    }
    await openAtBase(page, '/automation');
  }
  if (await page.getByTestId('operations-home-service-review-open-priority-workspace').count()) {
    await page.getByTestId('operations-home-service-review-open-priority-workspace').click();
    await waitForPath(page, /\/automation\?workspace=/);
    await expect(page.getByTestId('operations-home-quick-flows')).toBeVisible({ timeout: 30000 });
    await openAtBase(page, '/automation');
  }
  const freeHomeNotificationButtons = page.locator('[data-testid^="operations-home-service-review-notifications-"]');
  if (await freeHomeNotificationButtons.count()) {
    await freeHomeNotificationButtons.first().click();
    await waitForPath(page, /\/notifications(?:[/?#]|$)/);
    await expect(page.getByTestId('notifications-focused-service-context')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('notifications-focused-service-health-card')).toBeVisible({ timeout: 30000 });
    await page.getByTestId('notifications-focused-service-open-review').click();
    await waitForPath(page, /\/operations-reports(?:[/?#]|$)/);
    await expectReportsLanding();
    await openAtBase(page, '/automation');
  }
  await page.getByTestId('operations-quick-flow-discover_review').click();
  await waitForPath(page, /\/discovery/);
  await openAtBase(page, '/automation');
  await expect(page.locator('button[aria-label*="Observability Collection"]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Data Handling Audit' })).toHaveCount(0);

  await openAtBase(page, '/devices');
  const devicesResponse = await fetchJsonWithAuth(page, '/api/v1/devices/?limit=1000');
  expect(devicesResponse.status).toBe(200);
  const devices = unwrapCollection(devicesResponse.data);
  expect(devices.length).toBeGreaterThan(0);

  const managedSummaryResponse = await fetchJsonWithAuth(page, '/api/v1/devices/managed-summary');
  expect(managedSummaryResponse.status).toBe(200);
  expect(Number(managedSummaryResponse?.data?.managed_limit || 0)).toBe(50);

  await openAtBase(page, '/logs');
  const searchInput = page.locator('main input[type="text"]').first();
  await expect(searchInput).toBeVisible({ timeout: 30000 });
  await searchInput.fill('functional-audit-empty-sentinel');
  await expect(searchInput).toHaveValue('functional-audit-empty-sentinel');

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

  await openAtBase(page, '/observability');
  if (await page.getByTestId('obs-overview-guided-entry').count()) {
    await expect(page.getByTestId('obs-overview-guided-entry')).toBeVisible({ timeout: 30000 });
    if (await page.getByTestId('obs-overview-open-workspace').count()) {
      await page.getByTestId('obs-overview-open-workspace').click();
      await waitForPath(page, /\/automation(?:[/?#]|$)/);
      await expect(page.locator('[data-testid="automation-preview-panel"], [data-testid="automation-pro-operations-panel"]').first()).toBeVisible({ timeout: 30000 });
      await openAtBase(page, '/observability');
    }
  }
  await expect(page.locator('button[aria-label*="Observability Collection"]')).toHaveCount(0);

  await openAtBase(page, '/preview/contribute');
  const previewPolicyResponse = await fetchJsonWithAuth(page, '/api/v1/preview/policy');
  expect(previewPolicyResponse.status).toBe(200);
  const previewRecentResponse = await fetchJsonWithAuth(page, '/api/v1/preview/contributions/recent?limit=5');
  expect(previewRecentResponse.status).toBe(200);
  expect(unwrapCollection(previewRecentResponse.data).length).toBeGreaterThan(0);
  await expect(page.getByTestId('preview-audit-title')).toBeVisible({ timeout: 30000 });

  await openAtBase(page, '/edition/compare');
  await expect(page.getByText('NetSphere Free').first()).toBeVisible({ timeout: 30000 });

  for (const route of BLOCKED_ROUTES) {
    await openAtBase(page, route);
    await page.waitForTimeout(2500);
    await expect(page.getByTestId('policy-blocked-page')).toBeVisible({ timeout: 10000 });
  }

  guards.assertClean();
});
