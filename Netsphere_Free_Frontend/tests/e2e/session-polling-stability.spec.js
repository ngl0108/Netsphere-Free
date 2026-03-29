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

test('polling keeps session alive across transient 401 and token refresh recovery', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);
  await mockDashboardApis(page);

  let refreshCalls = 0;
  let unreadCalls = 0;
  let activeCalls = 0;

  await page.route('**/api/v1/auth/refresh', async (route) => {
    refreshCalls += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: `e2e-token-refreshed-${refreshCalls}` }),
    });
  });

  await page.route('**/api/v1/sdn/issues/unread-count**', async (route) => {
    unreadCalls += 1;
    if (unreadCalls === 1) {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: {
            code: 'AUTH_SESSION_MISSING',
            message: 'Session record is missing. Please retry.',
            details: { retryable: true, force_logout: false },
          },
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ unread_count: 0 }),
    });
  });

  await page.route('**/api/v1/sdn/issues/active**', async (route) => {
    activeCalls += 1;
    if (activeCalls === 1) {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: {
            code: 'AUTH_SESSION_MISSING',
            message: 'Session record is missing. Please retry.',
            details: { retryable: true, force_logout: false },
          },
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.goto('/');
  await expect(page).toHaveURL(/\/$/);

  // Wait long enough for at least one polling round after the initial recovery.
  await page.waitForTimeout(14000);

  await expect(page).not.toHaveURL(/\/login/);
  expect(refreshCalls).toBeGreaterThanOrEqual(1);
  expect(unreadCalls).toBeGreaterThanOrEqual(2);
  expect(activeCalls).toBeGreaterThanOrEqual(2);

  const token = await page.evaluate(() => localStorage.getItem('authToken') || '');
  expect(token).toContain('e2e-token-refreshed');
});
