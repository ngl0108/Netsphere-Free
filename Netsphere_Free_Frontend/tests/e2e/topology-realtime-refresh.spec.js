import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('topology automatically refreshes after realtime topology events', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  let topologyFetches = 0;
  let snapshotFetches = 0;

  const initialTopology = {
    nodes: [
      {
        id: 301,
        label: 'edge-r1',
        ip: '10.30.0.1',
        role: 'core',
        status: 'online',
        site_id: 1,
        site_name: 'HQ',
        tier: 'core',
      },
      {
        id: 302,
        label: 'wan-r2',
        ip: '10.30.0.2',
        role: 'distribution',
        status: 'online',
        site_id: 1,
        site_name: 'HQ',
        tier: 'wan',
      },
    ],
    links: [
      {
        source: 301,
        target: 302,
        protocol: 'LLDP',
        status: 'active',
        layer: 'l2',
        label: 'Gi0/1 <> Gi0/2',
        confidence: 0.96,
        evidence: { confidence: 0.96, protocol: 'lldp', layer: 'l2' },
      },
    ],
  };

  const refreshedTopology = {
    nodes: [
      ...initialTopology.nodes,
      {
        id: 303,
        label: 'branch-r3',
        ip: '10.30.0.3',
        role: 'branch',
        status: 'online',
        site_id: 1,
        site_name: 'HQ',
        tier: 'branch',
      },
    ],
    links: [
      ...initialTopology.links,
      {
        source: 302,
        target: 303,
        protocol: 'BGP',
        status: 'active',
        layer: 'l3',
        label: 'BGP wan-r2 <> branch-r3',
        confidence: 0.98,
        evidence: { confidence: 0.98, protocol: 'bgp', layer: 'l3' },
        l3: {
          relationship: 'ebgp',
          state: 'established',
          source: { local_as: 65100, peer_ip: '192.0.2.2', interface: 'xe-0/0/0' },
          target: { local_as: 65200, peer_ip: '192.0.2.1', interface: 'xe-0/0/1' },
        },
      },
    ],
  };

  await page.route('**/api/v1/devices/topology/links**', async (route) => {
    topologyFetches += 1;
    const body = topologyFetches <= 2 ? initialTopology : refreshedTopology;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
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
    snapshotFetches += 1;
    const body = snapshotFetches === 1
      ? []
      : [
          {
            id: 41,
            site_id: 1,
            label: 'auto-refresh snapshot',
            node_count: 3,
            link_count: 2,
            created_at: '2026-03-07T10:00:00Z',
          },
        ];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });

  await page.route('**/api/v1/topology/stream**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'event: heartbeat',
        'data: {"ok":true}',
        '',
        'event: topology_refresh',
        'data: {"device_id":301,"site_id":1,"source":"topology_refresh_task","scope":"device_topology","topology_changed":true,"refresh_hint":"topology"}',
        '',
        'event: topology_snapshot_created',
        'data: {"site_id":1,"label":"auto-refresh snapshot","refresh_hint":"snapshots"}',
        '',
      ].join('\n'),
    });
  });

  await page.goto('/topology');

  await expect(page.getByText('edge-r1')).toBeVisible();
  await expect.poll(() => topologyFetches, { timeout: 10000 }).toBeGreaterThan(2);
  await expect.poll(() => snapshotFetches, { timeout: 10000 }).toBeGreaterThan(1);
  await expect(page.getByText('branch-r3')).toBeVisible();

  const snapshotSelect = page.getByTestId('topology-snapshot-select');
  await expect(snapshotSelect).toBeVisible();
  await expect(snapshotSelect.locator('option')).toHaveCount(2);
  await expect(snapshotSelect.locator('option').nth(1)).toContainText('auto-refresh snapshot');
});
