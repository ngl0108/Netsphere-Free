import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

const mockProOpsApis = async (page) => {
  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ preview_enabled: false }),
    });
  });

  await page.route('**/api/v1/sdn/dashboard/stats**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        counts: {
          devices: 4,
          online: 3,
          offline: 1,
        },
        northbound_kpi: {
          status: 'warning',
          success_rate_pct: 94.4,
          avg_attempts: 1.7,
          p95_attempts: 3,
          failure_causes: [
            { cause: 'http_5xx', count: 3 },
            { cause: 'timeout', count: 2 },
          ],
          totals: {
            deliveries: 36,
            success: 34,
            failed: 2,
            failed_24h: 2,
          },
        },
        closed_loop_kpi: {
          status: 'healthy',
          totals: {
            cycles: 12,
            triggered: 18,
            executed: 14,
            blocked: 4,
            approvals_opened: 3,
          },
          alerts: [],
        },
      }),
    });
  });

  await page.route('**/api/v1/intent/closed-loop/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        engine_enabled: true,
        auto_execute_enabled: true,
        execute_change_actions_enabled: false,
        rules_total: 5,
        rules_enabled: 4,
        rules_lint: {
          conflicts_count: 1,
          warnings_count: 2,
          top_conflicts: [],
          top_warnings: [],
        },
      }),
    });
  });
};

test('observability shows pro operations delivery context', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);
  await mockProOpsApis(page);

  await page.route('**/api/v1/observability/summary', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        counts: { devices: 1, online: 1, offline: 0 },
      }),
    });
  });

  await page.route('**/api/v1/observability/devices/101/interfaces/timeseries**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ points: [] }) });
  });

  await page.route('**/api/v1/observability/devices/101/interfaces', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/observability/devices/101/timeseries**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ points: [] }) });
  });

  await page.route('**/api/v1/observability/devices', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 101,
          name: 'edge-r1',
          ip: '10.10.10.1',
          site_id: 7,
          status: 'online',
          cpu: 22,
          memory: 31,
          traffic_in_bps: 12000000,
          traffic_out_bps: 9000000,
          last_seen: '2026-03-17T01:00:00Z',
        },
      ]),
    });
  });

  await page.route('**/api/v1/sites/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 7, name: 'Seoul Campus' }]),
    });
  });

  await page.goto('/observability?siteId=7&deviceId=101');

  const panel = page.getByTestId('obs-pro-operations-panel');
  await expect(panel).toBeVisible();
  await expect(panel.getByText(/Northbound KPI|노스바운드 KPI/)).toBeVisible();
  await expect(panel.getByText(/Closed-Loop KPI|폐루프 KPI/)).toBeVisible();
  await expect(page.getByTestId('obs-open-settings')).toBeVisible();
  await expect(page.getByTestId('obs-open-automation-hub')).toBeVisible();
  await expect(page.getByTestId('obs-open-alert-dashboard')).toHaveAttribute('href', /var-site_id=7/);
});

test('automation hub shows pro operations delivery panel', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);
  await mockProOpsApis(page);

  await page.goto('/automation');

  const panel = page.getByTestId('automation-pro-operations-panel');
  await expect(panel).toBeVisible();
  await expect(panel.getByText(/Northbound KPI|노스바운드 KPI/)).toBeVisible();
  await expect(panel.getByText(/Closed-Loop KPI|폐루프 KPI/)).toBeVisible();
  await expect(page.getByTestId('automation-open-approval')).toBeVisible();
  await expect(page.getByTestId('automation-open-compliance')).toBeVisible();
  await expect(page.getByTestId('automation-open-notifications')).toBeVisible();
  await expect(page.getByTestId('automation-open-settings')).toBeVisible();
  await expect(page.getByTestId('automation-open-observability')).toBeVisible();
  await expect(page.getByTestId('automation-open-alert-dashboard')).toHaveAttribute('href', /grafana/);
  await expect(page.getByTestId('automation-download-pro-operator-package')).toBeVisible();
  await expect(page.getByTestId('automation-download-support-bundle')).toBeVisible();
  await expect(page.getByTestId('automation-download-release-bundle')).toBeVisible();
  await expect(page.getByTestId('automation-download-compliance-export')).toBeVisible();
  await expect(page.getByTestId('automation-open-fleet-dashboard')).toHaveAttribute('href', /grafana/);
  await expect(page.getByTestId('automation-open-control-plane-dashboard')).toHaveAttribute('href', /grafana/);
  await expect(page.getByTestId('automation-open-discovery-topology-dashboard')).toHaveAttribute('href', /grafana/);
  await expect(page.getByTestId('automation-open-compliance-automation-dashboard')).toHaveAttribute('href', /grafana/);
});
