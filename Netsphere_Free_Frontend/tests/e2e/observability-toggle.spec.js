import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

async function mockDashboardApis(page) {
  await page.route('**/api/v1/sdn/dashboard/stats**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        counts: {
          sites: 1,
          devices: 1,
          online: 1,
          offline: 0,
          alert: 0,
          policies: 0,
          images: 0,
          wireless_aps: 0,
          wireless_clients: 0,
          compliant: 1,
        },
        health_score: 100,
        issues: [],
        trafficTrend: [],
        change_kpi: { status: 'idle', totals: {}, alerts: [] },
        closed_loop_kpi: { status: 'idle', totals: {}, alerts: [] },
        northbound_kpi: { status: 'idle', totals: {}, alerts: [] },
        autonomy_kpi: { status: 'idle', totals: {}, alerts: [], trend_7d: [] },
      }),
    });
  });

  await page.route('**/api/v1/devices/analytics**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ resourceTrend: [], topDevices: [], trafficTrend: [] }),
    });
  });

  await page.route('**/api/v1/ops/self-health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        cpu: { percent: 10 },
        memory: { used_percent: 20, used_bytes: 1, limit_bytes: 2 },
        disks: [{ path: '/', used_percent: 30, used_bytes: 1, total_bytes: 3 }],
        services: [],
        uptime_seconds: 120,
      }),
    });
  });

  await page.route('**/api/v1/ops/kpi/readiness/history**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        totals: { count: 0, by_status: {} },
        trend_by_day: [],
        items: [],
        latest: null,
      }),
    });
  });

  await page.route('**/api/v1/sdn/dashboard/change-traces**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total: 0, summary: {}, items: [] }),
    });
  });
}

test('dashboard observability toggle switches ON/OFF from header button', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);
  await mockDashboardApis(page);

  let enabled = false;
  const postedStates = [];
  await page.route('**/api/v1/ops/observability**', async (route) => {
    const method = route.request().method().toUpperCase();
    if (method === 'POST') {
      const body = route.request().postDataJSON() || {};
      enabled = !!body.enabled;
      postedStates.push(enabled);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ enabled }),
    });
  });

  await page.goto('/');
  const obsToggle = page.locator('button[title*="Observability Collection:"]');
  await expect(obsToggle).toBeVisible();
  await expect(obsToggle).toHaveAttribute('title', /OFF/i);

  await obsToggle.click();
  await expect(obsToggle).toHaveAttribute('title', /ON/i);

  await obsToggle.click();
  await expect(obsToggle).toHaveAttribute('title', /OFF/i);

  expect(postedStates).toEqual([true, false]);
});
