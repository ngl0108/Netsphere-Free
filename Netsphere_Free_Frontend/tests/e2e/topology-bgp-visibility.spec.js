import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('topology bgp mode highlights routing sessions and hides non-bgp nodes', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  await page.route('**/api/v1/devices/topology/links**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        nodes: [
          {
            id: 101,
            label: 'edge-r1',
            ip: '10.10.10.1',
            role: 'core',
            status: 'online',
            site_id: 1,
            site_name: 'HQ',
            tier: 'core',
            l3: {
              peer_counts: { total: 1, bgp: 1, ospf: 0 },
              state_counts: { healthy: 1, degraded: 0 },
              local_asns: [65001],
            },
          },
          {
            id: 102,
            label: 'wan-r2',
            ip: '10.10.10.2',
            role: 'distribution',
            status: 'online',
            site_id: 1,
            site_name: 'HQ',
            tier: 'wan',
            l3: {
              peer_counts: { total: 1, bgp: 1, ospf: 0 },
              state_counts: { healthy: 1, degraded: 0 },
              local_asns: [65002],
            },
          },
          {
            id: 103,
            label: 'access-sw1',
            ip: '10.10.10.10',
            role: 'access',
            status: 'online',
            site_id: 1,
            site_name: 'HQ',
            tier: 'access',
            l3: {
              peer_counts: { total: 0, bgp: 0, ospf: 0 },
              state_counts: { healthy: 0, degraded: 0 },
              local_asns: [],
            },
          },
        ],
        links: [
          {
            source: 101,
            target: 102,
            protocol: 'BGP',
            status: 'active',
            layer: 'l3',
            label: 'BGP edge-r1 <> wan-r2',
            confidence: 0.99,
            evidence: { confidence: 0.99, protocol: 'bgp', layer: 'l3' },
            l3: {
              relationship: 'ebgp',
              state: 'established',
              prefixes_received: 128,
              uptime: '1d 02:00:00',
              source: { local_as: 65001, peer_ip: '192.0.2.2', interface: 'xe-0/0/0' },
              target: { local_as: 65002, peer_ip: '192.0.2.1', interface: 'xe-0/0/1' },
            },
          },
          {
            source: 101,
            target: 103,
            protocol: 'LLDP',
            status: 'active',
            layer: 'l2',
            label: 'xe-0/0/2 <> gi1/0/24',
            confidence: 0.93,
            evidence: { confidence: 0.93, protocol: 'lldp', layer: 'l2' },
          },
        ],
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

  await page.goto('/topology');

  await expect(page.getByTestId('topology-layer-filter-bgp')).toBeVisible();
  await page.getByTestId('topology-layer-filter-bgp').click();

  const summary = page.getByTestId('bgp-topology-summary');
  await expect(summary).toBeVisible();
  await expect(page.getByTestId('bgp-summary-total-sessions')).toContainText('1');
  await expect(page.getByTestId('bgp-summary-ebgp')).toHaveText('1');
  await expect(page.getByTestId('bgp-summary-ibgp')).toHaveText('0');
  await expect(page.getByTestId('bgp-summary-up')).toHaveText('1');
  await expect(page.getByTestId('bgp-summary-nodes')).toHaveText('2');

  await expect(summary.getByText('AS65001')).toBeVisible();
  await expect(summary.getByText('AS65002')).toBeVisible();
  await expect(page.getByText('edge-r1')).toBeVisible();
  await expect(page.getByText('wan-r2')).toBeVisible();
  await expect(page.getByText('access-sw1')).toHaveCount(0);
});
