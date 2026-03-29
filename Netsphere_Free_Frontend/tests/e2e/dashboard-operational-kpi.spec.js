import { test, expect } from '@playwright/test';
import { buildProPolicy, mockCoreApis, seedAuth } from './helpers';

test('dashboard keeps internal ops panels hidden and exposes priority-issue investigation actions', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);
  let releaseBundleHits = 0;
  let releaseRefreshHits = 0;
  let releaseRefreshState = {
    status: 'idle',
    stage: 'idle',
    started_at: null,
    last_success_at: '2026-03-08T12:00:00+00:00',
    last_summary: {
      accepted_gates: 1,
      total_gates: 4,
    },
    error: null,
  };

  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildProPolicy()),
    });
  });

  await page.route('**/api/v1/sdn/dashboard/stats**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        counts: {
          sites: 2,
          devices: 10,
          online: 9,
          offline: 1,
          alert: 1,
          policies: 4,
          images: 2,
          wireless_aps: 3,
          wireless_clients: 40,
          compliant: 9,
        },
        health_score: 91,
        issues: [
          {
            id: 991,
            title: 'BGP control-plane alarm is active',
            device: 'demo-dist-01',
            device_id: 101,
            site_id: 7,
            site_name: 'Seoul Campus',
            severity: 'critical',
            category: 'routing',
            time: '2026-03-08T13:55:00+00:00',
          },
        ],
        trafficTrend: [],
        change_kpi: {
          status: 'healthy',
          change_success_rate_pct: 99.1,
          change_failure_rate_pct: 0.9,
          rollback_p95_ms: 900,
          approval_execution_trace_coverage_pct: 100,
          failure_causes: [{ cause: 'post_check_failed', count: 1 }],
          totals: {
            events: 120,
            success: 119,
            failed: 1,
            approval_context_events: 120,
            approval_traced: 120,
          },
          targets: {
            min_success_rate_pct: 98,
            max_failure_rate_pct: 1,
            max_rollback_p95_ms: 180000,
            min_trace_coverage_pct: 100,
          },
        },
        closed_loop_kpi: {
          status: 'healthy',
          execute_per_trigger_pct: 80,
          blocked_per_trigger_pct: 20,
          approvals_per_execution_pct: 25,
          avg_triggered_per_cycle: 3.2,
          avg_executed_per_cycle: 2.4,
          alerts: [],
          totals: {
            cycles: 10,
            triggered: 32,
            executed: 24,
            blocked: 8,
            approvals_opened: 6,
          },
          thresholds: {},
        },
        northbound_kpi: {
          status: 'healthy',
          success_rate_pct: 98.5,
          avg_attempts: 1.2,
          p95_attempts: 2,
          failure_causes: [{ cause: 'http_5xx', count: 2 }],
          modes: [{ mode: 'jira', count: 20 }],
          totals: {
            deliveries: 22,
            success: 20,
            failed: 2,
            failed_24h: 1,
          },
        },
        autonomy_kpi: {
          status: 'healthy',
          mttd_seconds: 45.3,
          mttd_p95_seconds: 70,
          mttr_seconds: 80.0,
          mttr_p95_seconds: 120,
          auto_action_rate_pct: 75.0,
          operator_intervention_rate_pct: 25.0,
          mttd_signal_coverage_pct: 90.0,
          mttr_coverage_pct: 100.0,
          trend_7d: [
            { date: '2026-02-11', actions_executed: 4, actions_auto: 3, actions_manual: 1, auto_action_rate_pct: 75, operator_intervention_rate_pct: 25 },
            { date: '2026-02-12', actions_executed: 5, actions_auto: 4, actions_manual: 1, auto_action_rate_pct: 80, operator_intervention_rate_pct: 20 },
            { date: '2026-02-13', actions_executed: 6, actions_auto: 5, actions_manual: 1, auto_action_rate_pct: 83.33, operator_intervention_rate_pct: 16.67 },
            { date: '2026-02-14', actions_executed: 5, actions_auto: 4, actions_manual: 1, auto_action_rate_pct: 80, operator_intervention_rate_pct: 20 },
            { date: '2026-02-15', actions_executed: 3, actions_auto: 2, actions_manual: 1, auto_action_rate_pct: 66.67, operator_intervention_rate_pct: 33.33 },
            { date: '2026-02-16', actions_executed: 4, actions_auto: 3, actions_manual: 1, auto_action_rate_pct: 75, operator_intervention_rate_pct: 25 },
            { date: '2026-02-17', actions_executed: 5, actions_auto: 4, actions_manual: 1, auto_action_rate_pct: 80, operator_intervention_rate_pct: 20 },
          ],
          totals: {
            issues_created: 10,
            issues_resolved: 9,
            mttd_samples: 9,
            mttr_samples: 9,
            actions_executed: 32,
            actions_auto: 24,
            actions_manual: 8,
          },
          targets: {
            min_auto_action_rate_pct: 60,
            max_operator_intervention_rate_pct: 40,
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/devices/analytics**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        resourceTrend: [
          { time: '10:00', cpu: 20, memory: 33 },
          { time: '10:05', cpu: 25, memory: 35 },
        ],
      }),
    });
  });

  await page.route('**/api/v1/ops/self-health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        cpu: { percent: 15.5 },
        memory: { used_percent: 40.2 },
        disks: [{ path: '/', used_percent: 50.1, total_bytes: 1, used_bytes: 1, free_bytes: 1 }],
      }),
    });
  });

  await page.route('**/api/v1/ops/kpi/readiness/history**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        totals: {
          count: 8,
          by_status: { healthy: 4, warning: 3, critical: 1 },
        },
        latest: {
          readiness: {
            status: 'warning',
            required_checks_total: 18,
            pass_count: 12,
            fail_count: 4,
            unknown_count: 2,
          },
          evidence: {
            sample_coverage: {
              discovery_jobs: { coverage_pct: 66.67 },
              change_events: { coverage_pct: 120.0 },
              northbound_deliveries: { coverage_pct: 40.0 },
              autonomy_actions_executed: { coverage_pct: 80.0 },
            },
          },
        },
        coverage: {
          coverage_pct: 66.67,
          days_with_snapshots: 20,
          expected_days: 30,
          latest_age_hours: 6.5,
        },
        comparison: {
          status_direction: 'improved',
          pass_delta: 2,
          fail_delta: -1,
          unknown_delta: -1,
        },
        current_streak: {
          status: 'warning',
          snapshots: 2,
        },
        top_failing_checks: [
          {
            id: 'plug_scan.auto_reflection_rate_pct',
            title: 'Plug & Scan auto reflection rate',
            fail_count: 3,
            latest_value: 61.2,
            latest_threshold: 75.0,
          },
        ],
        trend_by_day: [
          { date: '2026-03-01', healthy: 1, warning: 0, critical: 0, total: 1 },
          { date: '2026-03-02', healthy: 1, warning: 1, critical: 0, total: 2 },
          { date: '2026-03-03', healthy: 1, warning: 0, critical: 1, total: 2 },
          { date: '2026-03-04', healthy: 0, warning: 1, critical: 0, total: 1 },
          { date: '2026-03-05', healthy: 0, warning: 1, critical: 0, total: 1 },
          { date: '2026-03-06', healthy: 1, warning: 0, critical: 0, total: 1 },
          { date: '2026-03-07', healthy: 0, warning: 1, critical: 0, total: 1 },
        ],
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
          overall_status: 'warning',
          accepted_gates: 1,
          available_gates: 4,
          total_gates: 4,
          blocking_gates: [],
          warning_gates: ['kpi_readiness', 'vendor_support'],
          in_progress_gates: ['northbound_soak'],
        },
        sections: {
          kpi_readiness: {
            available: true,
            status: 'warning',
            pass_count: 12,
            required_checks_total: 18,
            sample_coverage: { met_count: 2, total: 4 },
            generated_at: '2026-03-08T08:00:00+00:00',
            source_name: 'kpi-readiness-30d-latest.json',
            details: {
              blocking_checks: [
                {
                  id: 'plug_scan.auto_reflection_rate_pct',
                  title: 'Plug & Scan auto reflection rate',
                  status: 'fail',
                  value: 61.2,
                  threshold: 75.0,
                  operator: '>=',
                },
              ],
              sample_gaps: [
                {
                  id: 'discovery_jobs',
                  title: 'Discovery jobs',
                  observed: 20,
                  threshold: 30,
                  coverage_pct: 66.67,
                  met: false,
                },
              ],
            },
          },
          vendor_support: {
            available: true,
            status: 'warning',
            covered_device_types: 49,
            total_supported_device_types: 49,
            readiness: { full: 15, partial: 5 },
            generated_at: '2026-03-08T09:00:00+00:00',
            source_name: 'vendor-support-matrix.latest.json',
            details: {
              weakest_device_types: [
                {
                  device_type: 'cisco_ios',
                  readiness: 'partial',
                  readiness_score: 40,
                  capabilities: ['neighbors'],
                },
              ],
            },
          },
          synthetic_validation: {
            available: true,
            status: 'healthy',
            scenario_count: 4,
            soak_runs: 3,
            total_processed_events: 1894,
            generated_at: '2026-03-08T10:00:00+00:00',
            source_name: 'synthetic-validation-matrix.latest.json',
            details: {
              scenarios: [
                {
                  name: 'security_incident',
                  devices: 72,
                  links: 100,
                  events: 21,
                  critical: 21,
                  warning: 0,
                },
              ],
              soak_summary: {
                max_duplicate_ratio: 0.08,
                max_queue_depth: 919,
                max_throughput_eps: 185.6,
              },
              first_wave_vendors: ['Juniper', 'Fortinet'],
              failed_assertions: [],
            },
          },
          northbound_soak: {
            available: true,
            status: 'in_progress',
            success_rate_pct: 100.0,
            total_attempts: 574,
            remaining_seconds: 190300,
            generated_at: '2026-03-08T11:00:00+00:00',
            source_name: 'northbound-soak-72h-latest.json',
            details: {
              last_record: {
                mode: 'servicenow',
                http_status: 200,
                latency_ms: 70.13,
                attempts: 1,
                timestamp: '2026-03-08T11:00:00+00:00',
              },
              window: {
                started_at: '2026-03-07T11:00:00+00:00',
                expected_finish_at: '2026-03-10T11:00:00+00:00',
                elapsed_seconds: 3600,
                remaining_seconds: 190300,
              },
            },
          },
        },
        automation: {
          enabled: true,
          profile: 'release',
          include_synthetic: true,
          schedule: {
            cadence: 'daily',
            timezone: 'Asia/Seoul',
            hour: 4,
            minute: 30,
            label: 'Daily 04:30 Asia/Seoul',
          },
          next_run_at: '2026-03-09T04:30:00+09:00',
        },
        refresh: releaseRefreshState,
      }),
    });
  });

  await page.route('**/api/v1/ops/release-evidence/refresh**', async (route) => {
    releaseRefreshHits += 1;
    releaseRefreshState = {
      status: 'running',
      stage: 'synthetic_validation',
      profile: 'release',
      include_synthetic: true,
      started_at: '2026-03-08T14:10:00+00:00',
      last_success_at: '2026-03-08T12:00:00+00:00',
      last_summary: {
        accepted_gates: 1,
        total_gates: 4,
      },
      error: null,
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        started: true,
        reason: 'started',
        refresh: releaseRefreshState,
      }),
    });
  });

  await page.route('**/api/v1/ops/release-evidence/bundle**', async (route) => {
    releaseBundleHits += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/zip',
      headers: {
        'content-disposition': 'attachment; filename="release_evidence_bundle_20260308_140000.zip"',
      },
      body: 'bundle',
    });
  });

  await page.route('**/api/v1/sdn/dashboard/change-traces**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        total: 1,
        summary: {},
        items: [],
      }),
    });
  });

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading', { name: 'Infrastructure Health' })).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('dashboard-pro-operations-panel')).toHaveCount(0);
  await expect(page.getByText('Change KPI')).toHaveCount(0);
  await expect(page.getByText('Release Evidence')).toHaveCount(0);
  await expect(page.getByText('Ops Readiness (30d)')).toHaveCount(0);
  expect(releaseRefreshHits).toBe(0);
  expect(releaseBundleHits).toBe(0);

  const issueCard = page.getByTestId('dashboard-issue-card-991');
  await expect(issueCard).toContainText('BGP control-plane alarm is active');
  await expect(issueCard.getByRole('button', { name: 'Open Device' })).toBeVisible();
  await expect(issueCard.getByRole('button', { name: 'Open Topology' })).toBeVisible();
  await expect(issueCard.getByRole('button', { name: 'Open Observability' })).toBeVisible();
  await expect(issueCard.getByRole('button', { name: 'Open Grafana' })).toBeVisible();
});
