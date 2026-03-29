import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('topology path trace shows enhanced summary and segment health', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  await page.route('**/api/v1/devices/topology/links**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        nodes: [
          { id: 301, label: 'edge-r1', ip: '10.30.0.1', role: 'core', status: 'online', site_id: 1, site_name: 'WAN', tier: 'core' },
          { id: 302, label: 'wan-r2', ip: '10.30.0.2', role: 'distribution', status: 'online', site_id: 1, site_name: 'WAN', tier: 'distribution' },
          { id: 303, label: 'edge-r3', ip: '10.40.0.1', role: 'core', status: 'online', site_id: 1, site_name: 'WAN', tier: 'core' },
        ],
        links: [
          {
            id: 9001,
            source: 301,
            target: 302,
            src_port: 'Gi0/1',
            dst_port: 'Gi0/1',
            protocol: 'LLDP',
            status: 'active',
            layer: 'l2',
            label: 'Gi0/1 <> Gi0/1',
            confidence: 0.97,
            evidence: { confidence: 0.97, protocol: 'lldp', layer: 'l2' },
          },
          {
            id: 9002,
            source: 301,
            target: 302,
            src_port: '',
            dst_port: '',
            protocol: 'BGP',
            status: 'degraded',
            layer: 'l3',
            label: 'AS65001 <> AS65002',
            confidence: 0.72,
            evidence: { confidence: 0.72, protocol: 'bgp', layer: 'l3' },
            l3: {
              relationship: 'ebgp',
              state: 'idle',
              source: { local_as: 65001 },
              target: { local_as: 65002 },
            },
          },
          {
            id: 9003,
            source: 302,
            target: 303,
            src_port: 'Gi0/2',
            dst_port: 'Gi0/1',
            protocol: 'LLDP',
            status: 'active',
            layer: 'l2',
            label: 'Gi0/2 <> Gi0/1',
            confidence: 0.95,
            evidence: { confidence: 0.95, protocol: 'lldp', layer: 'l2' },
          },
        ],
      }),
    });
  });

  await page.route('**/api/v1/sites/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 1, name: 'WAN' }]),
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

  await page.route('**/api/v1/topology/path-trace', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'success',
        mode: 'topology_best_effort',
        message: 'Used best-effort topology path with degraded links.',
        path: [
          { id: 301, name: 'edge-r1', type: 'cisco_ios', ip: '10.30.0.1', ingress_intf: 'Vlan10', egress_intf: 'Gi0/0', role: 'core', evidence: { type: 'route_lookup', protocol: 'bgp', vrf: 'BLUE' } },
          { id: 302, name: 'wan-r2', type: 'cisco_ios', ip: '10.30.0.2', ingress_intf: 'Gi0/0', egress_intf: 'Gi0/2', role: 'distribution' },
          { id: 303, name: 'edge-r3', type: 'cisco_ios', ip: '10.40.0.1', ingress_intf: 'Gi0/1', egress_intf: 'Host', role: 'core' },
        ],
        path_node_ids: [301, 302, 303],
        segments: [
          {
            hop: 0,
            from_id: 301,
            to_id: 302,
            from_port: 'Gi0/0',
            to_port: 'Gi0/0',
            status: 'degraded',
            protocol: 'BGP',
            layer: 'l3',
            confidence: 0.72,
            link: { id: 9002, status: 'degraded', protocol: 'BGP', layer: 'l3', confidence: 0.72 },
          },
          {
            hop: 1,
            from_id: 302,
            to_id: 303,
            from_port: 'Gi0/2',
            to_port: 'Gi0/1',
            status: 'active',
            protocol: 'LLDP',
            layer: 'l2',
            confidence: 0.95,
            link: { id: 9003, status: 'active', protocol: 'LLDP', layer: 'l2', confidence: 0.95 },
          },
        ],
        summary: {
          hop_count: 3,
          device_count: 3,
          segment_count: 2,
          mode: 'topology_best_effort',
          status: 'success',
          health: 'degraded',
          confidence_avg: 0.835,
          confidence_min: 0.72,
          active_segments: 1,
          degraded_segments: 1,
          down_segments: 0,
          unresolved_segments: 0,
          protocols: ['BGP', 'LLDP'],
          layers: ['l2', 'l3'],
          route_lookup_hops: 1,
          l2_trace_hops: 0,
          warnings: ['Used best-effort topology path with degraded links.', '1 degraded segment(s) present.'],
          complete: true,
        },
      }),
    });
  });

  await page.goto('/topology');

  await page.getByRole('button', { name: /Path Trace/i }).click();
  await expect(page.getByPlaceholder('e.g. 192.168.10.100')).toBeVisible();

  await page.getByPlaceholder('e.g. 192.168.10.100').fill('10.30.0.10');
  await page.getByPlaceholder('e.g. 10.20.30.50').fill('10.40.0.20');
  const traceResponsePromise = page.waitForResponse((response) =>
    response.url().includes('/api/v1/topology/path-trace') && response.request().method().toUpperCase() === 'POST',
  );
  await page.getByRole('button', { name: /^Path Trace$/ }).last().click();

  const traceResponse = await traceResponsePromise;
  const tracePayload = await traceResponse.json();

  expect(tracePayload?.summary?.mode).toBe('topology_best_effort');
  expect(tracePayload?.summary?.health).toBe('degraded');
  expect(tracePayload?.segments?.[0]?.protocol).toBe('BGP');
  expect(tracePayload?.segments?.[0]?.status).toBe('degraded');

  await expect(page.getByText('Path Found (3 Hops, degraded)')).toBeVisible();
  await expect(page.getByTestId('path-trace-summary-mode')).toHaveText('topology_best_effort');
  await expect(page.getByTestId('path-trace-summary-health')).toContainText('degraded');
  await expect(page.getByTestId('path-trace-hop-0').getByText(/BGP.*VRF:BLUE/)).toBeVisible();
  await expect(page.getByText('Hop 1 - edge-r1')).toBeVisible();
  await expect(page.getByText('In: Vlan10')).toBeVisible();
});
