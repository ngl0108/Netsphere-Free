import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';
import { gotoWithRetry } from './scenario-lab-live.helpers';

test('compliance report detail shows automation plan and opens drift view', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ preview_enabled: false }),
    });
  });

  const report = {
    device_id: 101,
    device_name: 'edge-sw1',
    status: 'violation',
    score: 50,
    last_checked: '2026-03-08T00:00:00Z',
    details: {
      summary: {
        status: 'violation',
        total_rules: 2,
        passed_rules: 1,
        violations_total: 1,
        score: 50,
      },
      standards: {
        Baseline: {
          total: 2,
          passed: 1,
          score: 50,
          violations: [
            {
              standard: 'Baseline',
              rule: 'NTP required',
              severity: 'warning',
              description: 'NTP must be configured',
              remediation: 'ntp server 10.0.0.10',
            },
          ],
        },
      },
      violations: [
        {
          standard: 'Baseline',
          rule: 'NTP required',
          severity: 'warning',
          description: 'NTP must be configured',
          remediation: 'ntp server 10.0.0.10',
        },
      ],
      automation: {
        status: 'auto_ready',
        requires_approval: false,
        primary_action: {
          code: 'drift_remediate',
          label: 'Force sync to golden',
        },
        support: {
          tier: 'official',
          config_supported: true,
          rollback_supported: true,
        },
        drift: {
          status: 'drift',
          has_golden: true,
          golden_id: 501,
          latest_id: 502,
        },
        fix_coverage: {
          total: 1,
          golden_fixable: 1,
          manual_guided: 1,
          manual_review: 0,
        },
        actions: [
          { code: 'open_drift', label: 'Open drift analysis', available: true, target: 'drift' },
          { code: 'drift_remediate', label: 'Force sync to golden', available: true, coverage: 'full' },
        ],
        next_steps: ['Open Drift and run force sync to golden.'],
        pre_check_commands: ['show version'],
      },
    },
  };

  await page.route('**/api/v1/compliance/standards', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/compliance/reports**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([report]) });
  });

  await page.route('**/api/v1/compliance/drift/kpi/summary**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        totals: { events: 1, success: 1, failed: 0, approval_context_events: 0, approval_traced: 0 },
        kpi: {
          status: 'healthy',
          change_success_rate_pct: 100,
          change_failure_rate_pct: 0,
          rollback_p95_ms: 1200,
          approval_execution_trace_coverage_pct: 100,
          targets: {
            min_success_rate_pct: 98,
            max_failure_rate_pct: 1,
            max_rollback_p95_ms: 180000,
            min_trace_coverage_pct: 100,
          },
          alerts: [],
        },
        failure_causes: [],
      }),
    });
  });

  await page.route('**/api/v1/devices**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 101, name: 'edge-sw1', ip_address: '10.10.10.1', device_type: 'cisco_ios', site_id: 7, site_name: 'Seoul Campus' },
        { id: 102, name: 'core-sw1', ip_address: '10.10.10.2', device_type: 'cisco_ios', site_id: 7, site_name: 'Seoul Campus' },
      ]),
    });
  });

  await page.route('**/api/v1/compliance/drift/backups/101', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 501, created_at: '2026-03-08T00:00:00Z', is_golden: true, size: 120 },
      ]),
    });
  });

  await page.route('**/api/v1/compliance/drift/check/101', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'drift',
        golden_id: 501,
        latest_id: 502,
        diff_lines: ['--- golden', '+++ running', '-hostname edge-sw1', '+hostname edge-sw1-old'],
        message: 'Configuration drift detected',
      }),
    });
  });

  await gotoWithRetry(page, '/compliance', { waitUntil: 'domcontentloaded' });

  await expect(page.getByRole('button', { name: /Compliance Reports/i })).toBeVisible();
  await page.getByRole('button', { name: /Compliance Reports/i }).click();
  await page.getByTestId('compliance-report-details-101').click();

  const modal = page.getByTestId('compliance-report-modal');
  await expect(modal).toBeVisible();
  await expect(modal).toContainText('Automation Ready');
  await expect(modal).toContainText('Force sync to golden');
  await expect(modal).toContainText('NTP required');
  await expect(page.getByTestId('compliance-report-open-device')).toHaveAttribute('href', '/devices/101');
  await expect(page.getByTestId('compliance-report-open-topology')).toHaveAttribute('href', '/topology?siteId=7');
  await expect(page.getByTestId('compliance-report-open-observability')).toHaveAttribute('href', '/observability?siteId=7&deviceId=101');
  await expect(page.getByTestId('compliance-report-open-grafana')).toHaveAttribute('href', /var-site_id=7/);
  await expect(page.getByText('Seoul Campus')).toBeVisible();

  await page.getByTestId('compliance-report-open-drift').click();

  await expect(page.getByTestId('drift-active-device-title')).toContainText('edge-sw1');
  await expect(page.getByText('Drift Detected')).toBeVisible();
});
