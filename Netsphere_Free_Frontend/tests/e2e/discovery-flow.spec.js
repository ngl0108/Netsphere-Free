import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('discovery scan can start and render results step', async ({ page }) => {
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
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 101 }) });
  });
  await page.route('**/api/v1/discovery/jobs/101', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'completed', logs: 'done', progress: 100 }),
    });
  });
  await page.route('**/api/v1/discovery/jobs/101/results', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });
  await page.route('**/api/v1/discovery/jobs/101/stream**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'event: done\ndata: {"status":"completed"}\n\n',
    });
  });
  await page.route('**/api/v1/discovery/jobs/101/kpi', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ kpi: { first_map_seconds: 5, auto_reflection_rate_pct: 100, false_positive_rate_pct: 0, low_confidence_rate_pct: 0 }, totals: { low_confidence_candidates: 0 } }),
    });
  });

  await page.goto('/discovery');
  await page.getByRole('button', { name: /start scan/i }).click();
  await expect(page.getByText(/scanning network/i)).toBeVisible();
  await expect(page.getByText(/scan results/i)).toBeVisible();
});

test('discovery approval opens post-discovery review and can promote a node to managed', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  let managementState = 'discovered_only';
  let managementReason = 'edition_limit';

  await page.route('**/api/v1/settings/general', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) });
  });
  await page.route('**/api/v1/sites/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 11, name: 'Seoul HQ' },
        { id: 22, name: 'Busan Branch' },
      ]),
    });
  });
  await page.route('**/api/v1/devices/managed-summary', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        managed_limit: 50,
        total_discovered: 51,
        managed: managementState === 'managed' ? 50 : 49,
        discovered_only: managementState === 'managed' ? 1 : 2,
        remaining_slots: managementState === 'managed' ? 0 : 1,
      }),
    });
  });
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
        kpi: { first_map_seconds: 5, auto_reflection_rate_pct: 100, false_positive_rate_pct: 0, low_confidence_rate_pct: 0 },
        totals: { low_confidence_candidates: 0 },
      }),
    });
  });
  await page.route('**/api/v1/discovery/jobs/202/results', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 701,
          status: 'new',
          ip_address: '10.10.10.5',
          hostname: 'edge-sw-01',
          vendor: 'Dasan',
          vendor_confidence: 0.96,
          model: 'V6824',
          device_type: 'access',
          snmp_status: 'reachable',
          issues: [],
          evidence: {},
        },
      ]),
    });
  });
  await page.route('**/api/v1/discovery/approve/701', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Device approved', device_id: 501 }),
    });
  });
  await page.route('**/api/v1/devices/501', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 501,
        name: 'edge-sw-01',
        hostname: 'edge-sw-01',
        ip_address: '10.10.10.5',
        vendor: 'Dasan',
        model: 'V6824',
        role: 'access',
        site_id: null,
        management_state: managementState,
        management_reason: managementReason,
      }),
    });
  });
  await page.route('**/api/v1/monitoring-profiles/catalog', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        profiles: [
          { id: 301, name: 'Campus Access Managed', key: 'campus-access-managed' },
          { id: 302, name: 'Discovery Standby', key: 'discovery-standby' },
        ],
        coverage: {},
      }),
    });
  });
  await page.route('**/api/v1/monitoring-profiles/devices/501/recommendation', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        device_id: 501,
        recommendation: {
          profile_id: 301,
          key: 'campus-access-managed',
          name: 'Campus Access Managed',
          assignment_source: 'auto',
          confidence: 0.96,
          management_scope: 'managed',
          telemetry_mode: 'hybrid',
          recommendation_reasons: ['vendor match', 'access role'],
          activation_state: managementState === 'managed' ? 'active' : 'ready_when_managed',
          policy_summary: {
            managed_state: managementState,
            site_id: null,
            device_type: 'access',
            role: 'access',
          },
        },
      }),
    });
  });
  await page.route('**/api/v1/service-groups/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 401, name: 'Campus Access' }]),
    });
  });
  await page.route('**/api/v1/devices/501/manage', async (route) => {
    managementState = 'managed';
    managementReason = 'user_selected';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        summary: {
          managed_limit: 50,
          total_discovered: 51,
          managed: 50,
          discovered_only: 1,
          remaining_slots: 0,
        },
      }),
    });
  });

  await page.goto('/discovery');
  await page.getByRole('button', { name: /start scan/i }).click();
  await expect(page.getByText(/scan results/i)).toBeVisible();
  await page.getByRole('button', { name: /Add to Inventory/i }).click();

  const reviewPanel = page.getByTestId('discovery-post-review-panel');
  await expect(reviewPanel).toBeVisible();
  await expect(reviewPanel.getByText(/Post-Discovery Review/i)).toBeVisible();
  await expect(reviewPanel.getByText(/Campus Access Managed/i)).toBeVisible();

  await reviewPanel.getByRole('button', { name: /Promote to Managed/i }).click();
  await expect(reviewPanel.getByText(/Managed/i)).toBeVisible();
});
