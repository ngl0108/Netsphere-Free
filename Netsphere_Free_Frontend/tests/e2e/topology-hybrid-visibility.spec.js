import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('topology hybrid mode highlights cloud inventory and opens enriched cloud detail', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { mode: 'multicloud_full' });

  await page.route('**/api/v1/devices/topology/links**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        nodes: [
          {
            id: 301,
            label: 'edge-r1',
            ip: '10.30.0.1',
            role: 'core',
            status: 'online',
            site_id: 1,
            site_name: 'HQ',
            tier: 0,
            hybrid: {
              role: 'onprem',
              connected: true,
              hybrid_links: 1,
              peer_links: 1,
              inventory_links: 0,
              providers: ['aws'],
              account_names: ['prod'],
              accounts: ['101'],
              regions: ['ap-northeast-2'],
            },
          },
          {
            id: 302,
            label: 'aws-peer-1',
            ip: '203.0.113.10',
            role: 'cloud',
            status: 'online',
            site_id: null,
            site_name: 'Cloud',
            tier: 1,
            cloud: {
              kind: 'virtual_peer',
              provider: 'aws',
              account_id: 101,
              account_name: 'prod',
              region: 'ap-northeast-2',
              resource_type: 'instance',
              resource_type_label: 'Instance',
              resource_id: 'i-abc123',
              resource_name: 'prod-vm-1',
              refs: [
                { resource_type: 'instance', resource_type_label: 'Instance', resource_id: 'i-abc123', resource_name: 'prod-vm-1', region: 'ap-northeast-2' },
                { resource_type: 'subnet', resource_type_label: 'Subnet', resource_id: 'subnet-001', resource_name: 'app-subnet', region: 'ap-northeast-2' },
              ],
            },
            hybrid: {
              role: 'cloud',
              kind: 'virtual_peer',
              connected: true,
              hybrid_links: 2,
              peer_links: 1,
              inventory_links: 1,
              providers: ['aws'],
              account_names: ['prod'],
              accounts: ['101'],
              regions: ['ap-northeast-2'],
            },
          },
          {
            id: 'cr-vpc-001',
            label: 'prod-vpc',
            ip: '10.10.0.0/16',
            role: 'cloud',
            status: 'online',
            site_id: null,
            site_name: 'Cloud',
            tier: 0,
            cloud: {
              kind: 'inventory_resource',
              provider: 'aws',
              account_id: 101,
              account_name: 'prod',
              region: 'ap-northeast-2',
              resource_type: 'vpc',
              resource_type_label: 'VPC',
              resource_id: 'vpc-001',
              resource_name: 'prod-vpc',
              refs: [],
            },
            hybrid: {
              role: 'cloud',
              kind: 'inventory_resource',
              connected: true,
              hybrid_links: 1,
              peer_links: 0,
              inventory_links: 1,
              providers: ['aws'],
              account_names: ['prod'],
              accounts: ['101'],
              regions: ['ap-northeast-2'],
            },
          },
          {
            id: 'cr-subnet-001',
            label: 'app-subnet',
            ip: '10.10.1.0/24',
            role: 'cloud',
            status: 'online',
            site_id: null,
            site_name: 'Cloud',
            tier: 1,
            cloud: {
              kind: 'inventory_resource',
              provider: 'aws',
              account_id: 101,
              account_name: 'prod',
              region: 'ap-northeast-2',
              resource_type: 'subnet',
              resource_type_label: 'Subnet',
              resource_id: 'subnet-001',
              resource_name: 'app-subnet',
              refs: [],
            },
            hybrid: {
              role: 'cloud',
              kind: 'inventory_resource',
              connected: true,
              hybrid_links: 2,
              peer_links: 0,
              inventory_links: 2,
              providers: ['aws'],
              account_names: ['prod'],
              accounts: ['101'],
              regions: ['ap-northeast-2'],
            },
          },
          {
            id: 303,
            label: 'access-sw1',
            ip: '10.30.0.10',
            role: 'access',
            status: 'online',
            site_id: 1,
            site_name: 'HQ',
            tier: 2,
          },
        ],
        links: [
          {
            source: 301,
            target: 302,
            protocol: 'BGP',
            status: 'active',
            layer: 'l3',
            label: 'BGP edge-r1 <> aws-peer-1',
            confidence: 0.97,
            hybrid: {
              kind: 'cloud_peer',
              relationship: 'cloud_to_onprem',
              provider: 'aws',
              account_id: 101,
              account_name: 'prod',
              region: 'ap-northeast-2',
              resource_name: 'prod-vm-1',
              resource_id: 'i-abc123',
            },
            evidence: { confidence: 0.97, protocol: 'bgp', layer: 'l3' },
            l3: {
              relationship: 'ebgp',
              state: 'established',
              source: { local_as: 65001 },
              target: { local_as: 65010 },
            },
          },
          {
            source: 'cr-vpc-001',
            target: 'cr-subnet-001',
            protocol: 'CLOUD',
            status: 'active',
            layer: 'hybrid',
            label: 'contains',
            confidence: 1,
            hybrid: {
              kind: 'inventory',
              relationship: 'cloud_to_cloud',
              provider: 'aws',
              account_id: 101,
              account_name: 'prod',
              region: 'ap-northeast-2',
              resource_name: 'prod-vpc',
              resource_id: 'vpc-001',
            },
            evidence: { confidence: 1, protocol: 'cloud', layer: 'hybrid' },
          },
          {
            source: 'cr-subnet-001',
            target: 302,
            protocol: 'CLOUD',
            status: 'active',
            layer: 'hybrid',
            label: 'attached',
            confidence: 1,
            hybrid: {
              kind: 'inventory',
              relationship: 'cloud_attachment',
              provider: 'aws',
              account_id: 101,
              account_name: 'prod',
              region: 'ap-northeast-2',
              resource_name: 'app-subnet',
              resource_id: 'subnet-001',
            },
            evidence: { confidence: 1, protocol: 'cloud', layer: 'hybrid' },
          },
          {
            source: 301,
            target: 303,
            protocol: 'LLDP',
            status: 'active',
            layer: 'l2',
            label: 'Gi0/1 <> Gi0/24',
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
        body: JSON.stringify({
          id: 1,
          name: 'default',
          data: [
            { id: '301', position: { x: 80, y: 120 }, style: { width: 180, height: 130 } },
            { id: '302', position: { x: 380, y: 120 }, style: { width: 180, height: 150 } },
            { id: 'cr-vpc-001', position: { x: 700, y: 90 }, style: { width: 180, height: 140 } },
            { id: 'cr-subnet-001', position: { x: 700, y: 300 }, style: { width: 180, height: 140 } },
            { id: '303', position: { x: 80, y: 360 }, style: { width: 180, height: 120 } },
          ],
        }),
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

  await expect(page.getByTestId('topology-layer-filter-hybrid')).toBeVisible();
  await page.getByTestId('topology-layer-filter-hybrid').click();

  const summary = page.getByTestId('hybrid-topology-summary');
  await expect(summary).toBeVisible();
  await expect(page.getByTestId('hybrid-summary-total-links')).toContainText('3');
  await expect(page.getByTestId('hybrid-summary-peer-links')).toHaveText('1');
  await expect(page.getByTestId('hybrid-summary-inventory-links')).toHaveText('2');
  await expect(page.getByTestId('hybrid-summary-cloud-nodes')).toHaveText('3');
  await expect(page.getByTestId('hybrid-summary-onprem-nodes')).toHaveText('1');
  await expect(page.getByTestId('hybrid-summary-accounts')).toHaveText('1');
  await expect(summary.getByText('AWS')).toBeVisible();

  await expect(page.getByTestId('rf__node-301')).toBeVisible();
  await expect(page.getByTestId('rf__node-302')).toBeVisible();
  await expect(page.getByTestId('rf__node-cr-vpc-001')).toBeVisible();
  await expect(page.getByTestId('rf__node-cr-subnet-001')).toBeVisible();
  await expect(page.getByTestId('rf__node-303')).toHaveCount(0);

  await expect(page.getByTestId('rf__node-302')).toContainText('prod');
  await expect(page.getByTestId('rf__node-302')).toContainText('HY 2');
});
