import { test, expect } from '@playwright/test';
import { buildFreePolicy, mockCoreApis, seedAuth } from './helpers';

async function mockDashboardApis(page) {
  await page.route('**/api/v1/sdn/dashboard/stats**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        counts: {
          sites: 1,
          devices: 4,
          online: 4,
          offline: 0,
          alert: 0,
          policies: 0,
          images: 0,
          wireless_aps: 0,
          wireless_clients: 0,
          compliant: 4,
        },
        health_score: 96,
        issues: [],
        trafficTrend: [],
        change_kpi: {
          status: 'healthy',
          change_success_rate_pct: 100,
          change_failure_rate_pct: 0,
          rollback_p95_ms: 0,
          approval_execution_trace_coverage_pct: 100,
          failure_causes: [],
          totals: { events: 0, success: 0, failed: 0, approval_context_events: 0, approval_traced: 0 },
          targets: {},
        },
        closed_loop_kpi: {
          status: 'healthy',
          execute_per_trigger_pct: 75,
          blocked_per_trigger_pct: 25,
          approvals_per_execution_pct: 0,
          avg_triggered_per_cycle: 1,
          avg_executed_per_cycle: 1,
          alerts: [],
          totals: { cycles: 2, triggered: 4, executed: 3, blocked: 1, approvals_opened: 0 },
        },
        northbound_kpi: {
          status: 'healthy',
          success_rate_pct: 100,
          avg_attempts: 1,
          p95_attempts: 1,
          failure_causes: [],
          modes: [],
          totals: { deliveries: 2, success: 2, failed: 0, failed_24h: 0 },
        },
        autonomy_kpi: {
          status: 'healthy',
          mttd_seconds: 0,
          mttd_p95_seconds: 0,
          mttr_seconds: 0,
          mttr_p95_seconds: 0,
          auto_action_rate_pct: 0,
          operator_intervention_rate_pct: 0,
          mttd_signal_coverage_pct: 0,
          mttr_coverage_pct: 0,
          trend_7d: [],
          totals: { issues_created: 0, issues_resolved: 0, mttd_samples: 0, mttr_samples: 0, actions_executed: 0, actions_auto: 0, actions_manual: 0 },
          targets: {},
        },
      }),
    });
  });

  await page.route('**/api/v1/devices/analytics**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ resourceTrend: [] }),
    });
  });

  await page.route('**/api/v1/ops/self-health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        cpu: { percent: 10 },
        memory: { used_percent: 20, used_bytes: 1, limit_bytes: 1 },
        disks: [{ path: '/', used_percent: 30, total_bytes: 1, used_bytes: 1, free_bytes: 1 }],
      }),
    });
  });

  await page.route('**/api/v1/ops/kpi/readiness/history**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        totals: { count: 0, by_status: {} },
        latest: null,
        coverage: {},
        comparison: {},
        current_streak: {},
        top_failing_checks: [],
        trend_by_day: [],
        items: [],
      }),
    });
  });

  await page.route('**/api/v1/ops/release-evidence**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        generated_at: '2026-03-08T14:00:00+00:00',
        source: 'cache',
        summary: {
          overall_status: 'unavailable',
          accepted_gates: 0,
          available_gates: 0,
          total_gates: 4,
          blocking_gates: [],
          warning_gates: [],
          in_progress_gates: [],
        },
        sections: {},
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

test('dashboard hides pro operational delivery panels in NetSphere Free', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);
  await mockDashboardApis(page);

  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildFreePolicy()),
    });
  });

  await page.goto('/');
  await page.waitForLoadState('networkidle');

  await expect(page.getByRole('heading', { name: 'Infrastructure Health' })).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('dashboard-pro-operations-panel')).toHaveCount(0);
  await expect(page.getByText('Change KPI')).toHaveCount(0);
  await expect(page.getByText('Northbound KPI')).toHaveCount(0);
  await expect(page.getByText('Autonomy KPI')).toHaveCount(0);
  await expect(page.getByText('Release Evidence')).toHaveCount(0);
});
