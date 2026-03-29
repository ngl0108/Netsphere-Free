import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('seed crawl plug-and-scan auto-approves and jumps to topology', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  let approveAllCalled = false;
  let approveAllPolicy = null;

  await page.route('**/api/v1/devices**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 51, name: 'seed-sw', ip_address: '10.88.0.1', status: 'online', device_type: 'cisco_ios' },
      ]),
    });
  });
  await page.route('**/api/v1/discovery/kpi/summary**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ kpi: {}, totals: {}, jobs_count: 0, jobs: [] }) });
  });
  await page.route('**/api/v1/discovery/kpi/alerts**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'healthy', alerts: [] }) });
  });
  await page.route('**/api/v1/topology/candidates/summary**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ totals: {} }) });
  });
  await page.route('**/api/v1/topology/candidates/summary/trend**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ series: [], jobs: [] }) });
  });
  await page.route('**/api/v1/discovery/crawl', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 303 }) });
  });
  await page.route('**/api/v1/discovery/jobs/303', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'completed', logs: 'done', progress: 100 }),
    });
  });
  await page.route('**/api/v1/discovery/jobs/303/results', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });
  await page.route('**/api/v1/discovery/jobs/303/stream**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'event: done\ndata: {"status":"completed"}\n\n',
    });
  });
  await page.route('**/api/v1/discovery/jobs/303/kpi', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        kpi: { first_map_seconds: 8, auto_reflection_rate_pct: 100, false_positive_rate_pct: 0, low_confidence_rate_pct: 0 },
        totals: { low_confidence_candidates: 0 },
      }),
    });
  });
  await page.route('**/api/v1/discovery/jobs/303/approve-all**', async (route) => {
    approveAllCalled = true;
    const url = new URL(route.request().url());
    approveAllPolicy = url.searchParams.get('policy');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ approved_count: 1, skipped_count: 0, skip_breakdown: {}, policy: { mode: 'auto' } }),
    });
  });
  await page.route('**/api/v1/topology/snapshots', async (route) => {
    if (route.request().method().toUpperCase() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1 }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });
  await page.route('**/api/v1/topology**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ nodes: [], links: [] }) });
  });

  await page.goto('/discovery');
  await page.getByRole('button', { name: /seed crawl/i }).click();
  await page.getByRole('button', { name: /start crawl/i }).click();

  await expect(page).toHaveURL(/\/topology/, { timeout: 15000 });
  expect(approveAllCalled).toBeTruthy();
  expect(approveAllPolicy).toBe('true');
});
