import { test, expect } from '@playwright/test';
import { mockCoreApis, mockSyntheticDiscoveryScenario, seedAuth } from './helpers';

test('synthetic discovery retries after forbidden response and completes on second attempt', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);
  const scenario = await mockSyntheticDiscoveryScenario(page, 'failure', {
    jobId: 9401,
    firstFailureStatus: 403,
    firstFailureMessage: 'Forbidden synthetic case',
  });

  await page.goto('/discovery');

  const startBtn = page.getByRole('button', { name: /start scan/i });
  await expect(startBtn).toBeVisible();
  await startBtn.click();
  await page.waitForTimeout(250);

  await startBtn.click();
  await expect(page.getByText(/scan results/i)).toBeVisible({ timeout: 15000 });
  expect(scenario.getScanAttempts()).toBe(2);
});

test('synthetic rollback action is triggered from visual config history', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  let rollbackCalled = false;

  await page.route('**/api/v1/devices**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 77, name: 'syn-edge-77', ip_address: '10.77.0.1', status: 'online', device_type: 'cisco_ios' }]),
    });
  });

  await page.route('**/api/v1/visual/blueprints', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 1, name: 'SYN-BP', current_version: 3 }]),
    });
  });

  await page.route('**/api/v1/visual/blueprints/1', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        name: 'SYN-BP',
        description: 'synthetic blueprint',
        current_version: 3,
        graph: {
          nodes: [{ id: 'target-1', type: 'target', position: { x: 100, y: 120 }, data: { target_type: 'devices', device_ids: [77] } }],
          edges: [],
          viewport: null,
        },
      }),
    });
  });

  await page.route('**/api/v1/visual/blueprints/1/deploy-jobs**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 501,
          status: 'failed',
          created_at: '2026-02-19T01:00:00+00:00',
          finished_at: '2026-02-19T01:01:00+00:00',
          summary: { type: 'deploy', total: 1, success: 0, failed: 1 },
        },
      ]),
    });
  });

  await page.route('**/api/v1/visual/deploy-jobs/501/rollback', async (route) => {
    rollbackCalled = true;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ job_id: 601, status: 'success', results: [{ device_id: 77, success: true }] }),
    });
  });

  await page.route('**/api/v1/visual/deploy-jobs/601', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        job: { id: 601, status: 'success' },
        results: [{ device_id: 77, success: true }],
      }),
    });
  });

  page.on('dialog', async (dialog) => {
    await dialog.accept();
  });

  await page.goto('/visual-config');
  await page.getByRole('button', { name: 'SYN-BP' }).click();
  await page.getByRole('button', { name: /history/i }).click();
  await page.getByRole('button', { name: /rollback/i }).click();

  await expect.poll(() => rollbackCalled).toBeTruthy();
});
