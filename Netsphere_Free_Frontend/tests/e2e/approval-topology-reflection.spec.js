import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('review queue action routes to topology after approval context', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  await page.route('**/api/v1/discovery/kpi/summary**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ kpi: {}, totals: {} }) });
  });
  await page.route('**/api/v1/discovery/kpi/alerts**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'healthy', alerts: [] }) });
  });
  await page.route('**/api/v1/topology/candidates/summary**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ totals: {} }) });
  });
  await page.route('**/api/v1/topology/candidates/summary-trend**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ series: [], jobs: [] }) });
  });
  await page.route('**/api/v1/discovery/scan', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 202 }) });
  });
  await page.route('**/api/v1/discovery/jobs/202', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'completed', logs: 'done', progress: 100 }),
    });
  });
  await page.route('**/api/v1/discovery/jobs/202/results', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });
  await page.route('**/api/v1/discovery/jobs/202/stream**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'event: done\ndata: {"status":"completed"}\n\n',
    });
  });
  await page.route('**/api/v1/discovery/jobs/202/kpi', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        kpi: {
          first_map_seconds: 6,
          auto_reflection_rate_pct: 80,
          false_positive_rate_pct: 2,
          low_confidence_rate_pct: 20,
          low_confidence_top_reasons: [{ reason: 'low_confidence_link', count: 3 }],
        },
        totals: { low_confidence_candidates: 3 },
      }),
    });
  });
  await page.route('**/api/v1/topology**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ nodes: [], links: [] }) });
  });
  await page.route('**/api/v1/sites**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.goto('/discovery');
  await page.getByRole('button', { name: /start scan/i }).click();
  await expect(page.getByText(/scan results/i)).toBeVisible();
  const reviewQueueBtn = page.getByTestId('discovery-review-queue-results');
  await expect(reviewQueueBtn).toBeVisible();
  await Promise.all([
    page.waitForURL(/\/topology/, { timeout: 10000 }),
    reviewQueueBtn.click(),
  ]);
});
