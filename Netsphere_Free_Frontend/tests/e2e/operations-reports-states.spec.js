import { test, expect } from '@playwright/test';

import { mockCoreApis, seedAuth } from './helpers';
import { gotoWithRetry } from './scenario-lab-live.helpers';

async function mockOperationsReportsEmptyState(page) {
  await seedAuth(page);
  await mockCoreApis(page);

  await page.route('**/api/v1/ops/preventive-checks/summary', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        templates_total: 0,
        enabled_templates: 0,
        recent_runs_total: 0,
      }),
    });
  });

  await page.route('**/api/v1/ops/preventive-checks/runs**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/service-groups/', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/approval/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/ops/release-evidence**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        generated_at: '2026-03-22T10:00:00Z',
        summary: {
          overall_status: 'unavailable',
          accepted_gates: 0,
          available_gates: 0,
          total_gates: 0,
          warning_gates: [],
        },
        sections: {},
      }),
    });
  });

  await page.route('**/api/v1/sdn/issues/active**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/automation-hub/state-history/current', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) });
  });

  await page.route('**/api/v1/automation-hub/state-history/snapshots**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });
}

test('operations reports shows stable empty states when no review data exists', async ({ page }) => {
  await mockOperationsReportsEmptyState(page);

  await gotoWithRetry(page, '/operations-reports', { waitUntil: 'domcontentloaded' });

  await expect(page.getByTestId('operations-reports-page')).toBeVisible();
  await expect(page.getByTestId('operations-reports-empty-state-history')).toBeVisible();
  await expect(page.getByTestId('operations-reports-empty-runs')).toBeVisible();
  await expect(page.getByTestId('operations-reports-empty-approvals')).toBeVisible();
  await expect(page.getByTestId('operations-reports-empty-follow-up')).toBeVisible();
  await expect(page.getByTestId('operations-reports-empty-service-groups')).toBeVisible();
  await expect(page.getByTestId('operations-reports-empty-action-continuity')).toBeVisible();
  await expect(page.getByTestId('operations-reports-empty-release')).toBeVisible();
});

test('operations reports surfaces a handled load error when the summary API fails', async ({ page }) => {
  await mockOperationsReportsEmptyState(page);

  await page.route('**/api/v1/ops/preventive-checks/summary', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Synthetic operations report load failure' }),
    });
  });

  await gotoWithRetry(page, '/operations-reports', { waitUntil: 'domcontentloaded' });

  await expect(page.getByTestId('operations-reports-page')).toBeVisible();
  await expect(
    page.locator('[data-testid="toast-error"]').filter({
      hasText: /Synthetic operations report load failure|Failed to load operations reports/i,
    }).last(),
  ).toBeVisible();
});

test('operations reports shows a handled bundle download error', async ({ page }) => {
  await mockOperationsReportsEmptyState(page);

  await page.route('**/api/v1/ops/operations-review-bundle**', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Synthetic operations review bundle failure' }),
    });
  });

  await gotoWithRetry(page, '/operations-reports', { waitUntil: 'domcontentloaded' });

  await expect(page.getByTestId('operations-reports-page')).toBeVisible();
  const failedBundleResponse = page.waitForResponse(
    (response) => response.url().includes('/api/v1/ops/operations-review-bundle') && response.status() === 500,
  );
  await page.getByTestId('operations-reports-download-review-bundle').click();
  await failedBundleResponse;
  await expect(
    page.locator('[data-testid="toast-error"], [data-testid="toast-warning"]').last(),
  ).toBeVisible();
});
