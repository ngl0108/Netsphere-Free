import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('topology overlay mode highlights vxlan fabric and hides non-overlay nodes', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  await page.route('**/api/v1/devices/topology/links**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        nodes: [
          {
            id: 201,
            label: 'leaf1',
            ip: '10.20.0.1',
            role: 'core',
            status: 'online',
            site_id: 1,
            site_name: 'Fabric',
            tier: 1,
            overlay: {
              peer_counts: { total: 1, vxlan: 1, evpn: 1 },
              vni_counts: { total: 2, l2: 1, l3: 1 },
              state_counts: { healthy: 1, degraded: 0 },
              local_vtep_ips: ['172.16.1.1'],
              transports: ['EVPN'],
            },
          },
          {
            id: 202,
            label: 'leaf2',
            ip: '10.20.0.2',
            role: 'distribution',
            status: 'online',
            site_id: 1,
            site_name: 'Fabric',
            tier: 1,
            overlay: {
              peer_counts: { total: 1, vxlan: 1, evpn: 1 },
              vni_counts: { total: 2, l2: 1, l3: 1 },
              state_counts: { healthy: 1, degraded: 0 },
              local_vtep_ips: ['172.16.1.2'],
              transports: ['EVPN'],
            },
          },
          {
            id: 203,
            label: 'access-sw1',
            ip: '10.20.0.10',
            role: 'access',
            status: 'online',
            site_id: 1,
            site_name: 'Fabric',
            tier: 2,
          },
        ],
        links: [
          {
            source: 201,
            target: 202,
            protocol: 'VXLAN',
            status: 'active',
            layer: 'overlay',
            label: 'EVPN / 2 VNI / UP / nve1<->nve1',
            confidence: 0.96,
            evidence: { confidence: 0.96, protocol: 'vxlan', layer: 'overlay' },
            overlay: {
              protocol: 'VXLAN',
              state: 'up',
              transport: 'evpn',
              vni_count: 2,
              vnis: [
                { vni: 10010, type: 'l2', bridge_domain: 'Users' },
                { vni: 20010, type: 'l3', vrf: 'Tenant-A' },
              ],
              source: { local_vtep_ip: '172.16.1.1', nve_interface: 'nve1' },
              target: { local_vtep_ip: '172.16.1.2', nve_interface: 'nve1' },
              evpn: { relationship: 'ebgp', source_as: 65101, target_as: 65102 },
            },
          },
          {
            source: 201,
            target: 203,
            protocol: 'LLDP',
            status: 'active',
            layer: 'l2',
            label: 'Eth1/1 <> Eth1/48',
            confidence: 0.9,
            evidence: { confidence: 0.9, protocol: 'lldp', layer: 'l2' },
          },
        ],
      }),
    });
  });

  await page.route('**/api/v1/sites/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 1, name: 'Fabric' }]),
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

  await expect(page.getByTestId('topology-layer-filter-overlay')).toBeVisible();
  await page.getByTestId('topology-layer-filter-overlay').click();

  const summary = page.getByTestId('overlay-topology-summary');
  await expect(summary).toBeVisible();
  await expect(page.getByTestId('overlay-summary-total')).toContainText('1');
  await expect(page.getByTestId('overlay-summary-up')).toHaveText('1');
  await expect(page.getByTestId('overlay-summary-vnis')).toHaveText('2');
  await expect(page.getByTestId('overlay-summary-l2vni')).toHaveText('1');
  await expect(page.getByTestId('overlay-summary-l3vni')).toHaveText('1');
  await expect(page.getByTestId('overlay-summary-nodes')).toHaveText('2');

  await expect(summary.getByText('EVPN 1')).toBeVisible();
  await expect(page.getByText('leaf1')).toBeVisible();
  await expect(page.getByText('leaf2')).toBeVisible();
  await expect(page.getByText('access-sw1')).toHaveCount(0);
});
