import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('candidate queue prioritizes actionable backlog and can use top suggestion', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  let recommendationCalls = 0;
  let promotePayload = null;

  await page.route('**/api/v1/devices/topology/links**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        nodes: [
          { id: 1, label: 'core-sw1', ip: '10.10.0.1', role: 'core', status: 'online', site_id: 1, site_name: 'HQ' },
        ],
        links: [],
      }),
    });
  });

  await page.route('**/api/v1/sites/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 1, name: 'HQ' }]),
    });
  });

  await page.route('**/api/v1/topology/layout**', async (route) => {
    const method = route.request().method().toUpperCase();
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, name: 'default', data: [] }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
  });

  await page.route('**/api/v1/topology/snapshots**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/topology/stream**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'event: heartbeat\ndata: {"ok":true}\n\n',
    });
  });

  await page.route('**/api/v1/topology/candidates/summary**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        totals: {
          backlog_total: 2,
          backlog_low_confidence: 1,
          backlog_unmatched: 1,
          resolved_24h: 1,
          stale_backlog_24h: 1,
        },
      }),
    });
  });

  await page.route('**/api/v1/topology/candidates/summary/trend**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        series: [
          { date: '2026-03-05', backlog_total: 1, resolved_total: 0 },
          { date: '2026-03-06', backlog_total: 2, resolved_total: 1 },
        ],
        jobs: [
          { job_id: 7001, backlog_total: 2, resolved_total: 1 },
        ],
      }),
    });
  });

  await page.route(/\/api\/v1\/topology\/candidates(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get('order_by')).toBe('priority');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 101,
          discovery_job_id: null,
          source_device_id: 1,
          source_device_name: 'core-sw1',
          source_device_ip: '10.10.0.1',
          site_id: 1,
          site_name: 'HQ',
          neighbor_name: 'wan-edge-1',
          mgmt_ip: '10.10.0.2',
          local_interface: 'Gi1/0/1',
          remote_interface: 'Gi0/0',
          protocol: 'LLDP',
          confidence: 0.42,
          reason: 'ambiguous_name_exact:21,22',
          reason_code: 'ambiguous_name_exact',
          reason_meta: {
            raw: 'ambiguous_name_exact:21,22',
            code: 'ambiguous_name_exact',
            kind: 'ambiguous',
            label: 'Multiple exact hostname matches',
            candidate_ids: [21, 22],
          },
          status: 'low_confidence',
          age_seconds: 108000,
          stale: true,
          actionable: true,
          backlog: true,
          priority_score: 108,
          priority_band: 'critical',
          next_action: { code: 'review_matches', label: 'Review competing matches' },
          last_seen: '2026-03-06T00:00:00Z',
        },
        {
          id: 102,
          discovery_job_id: null,
          source_device_id: 1,
          source_device_name: 'core-sw1',
          source_device_ip: '10.10.0.1',
          site_id: 1,
          site_name: 'HQ',
          neighbor_name: 'access-sw9',
          mgmt_ip: '',
          local_interface: 'Gi1/0/24',
          remote_interface: 'UNKNOWN',
          protocol: 'FDB',
          confidence: 0.25,
          reason: 'missing_mgmt_ip',
          reason_code: 'missing_mgmt_ip',
          reason_meta: {
            raw: 'missing_mgmt_ip',
            code: 'missing_mgmt_ip',
            kind: 'missing_data',
            label: 'Management IP missing',
          },
          status: 'unmatched',
          age_seconds: 7200,
          stale: false,
          actionable: true,
          backlog: true,
          priority_score: 74,
          priority_band: 'medium',
          next_action: { code: 'fill_mgmt_ip_or_use_suggestion', label: 'Fill management IP or use top suggestion' },
          last_seen: '2026-03-07T00:00:00Z',
        },
      ]),
    });
  });

  await page.route('**/api/v1/topology/candidates/101/recommendations**', async (route) => {
    recommendationCalls += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          discovered_id: 501,
          ip_address: '10.10.0.2',
          hostname: 'wan-edge-1',
          vendor: 'Cisco',
          model: 'C9300',
          os_version: '17.12',
          snmp_status: 'reachable',
          status: 'new',
          score: 0.96,
          reason: 'ip_match',
          match_band: 'high',
          action_ready: true,
        },
      ]),
    });
  });

  await page.route('**/api/v1/topology/candidates/101/promote**', async (route) => {
    promotePayload = JSON.parse(route.request().postData() || '{}');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ discovered_id: 501 }),
    });
  });

  await page.route('**/api/v1/discovery/approve/501', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
  });

  await page.goto('/topology');

  await page.getByTestId('topology-candidates-toggle').click();

  const panel = page.getByTestId('candidate-panel');
  await expect(panel).toBeVisible();
  await expect(page.getByTestId('candidate-row-101')).toContainText('wan-edge-1');
  await expect(page.getByTestId('candidate-row-101')).toContainText('Review competing matches');
  await expect(page.getByTestId('candidate-row-101')).toContainText('critical');

  await page.getByTestId('candidate-filter-stale').click();
  await expect(page.getByTestId('candidate-row-101')).toBeVisible();
  await expect(page.getByTestId('candidate-row-102')).toHaveCount(0);

  await page.getByTestId('candidate-filter-stale').click();
  await page.getByTestId('candidate-use-top-101').click();

  await expect.poll(() => recommendationCalls).toBe(1);
  await expect.poll(() => promotePayload?.ip_address || '').toBe('10.10.0.2');
  await expect(page.getByTestId('candidate-row-101')).toContainText('approved');
});
