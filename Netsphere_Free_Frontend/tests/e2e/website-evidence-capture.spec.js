import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const OUTPUT_DIR = path.resolve(__dirname, '..', '..', 'test-results', 'website-evidence');

const ensureKoreanLocale = async (page) => {
  await seedAuth(page);
  await page.addInitScript(() => {
    localStorage.setItem('nm_locale', 'ko');
  });
};

const mockInventoryEvidence = async (page) => {
  await page.route('**/api/v1/devices**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 501,
          name: 'demo-dist-01',
          model: 'QFX5120-48Y',
          device_type: 'JUNIPER_JUNOS',
          site_id: 1,
          ip_address: '127.0.10.12',
          status: 'online',
        },
        {
          id: 502,
          name: 'demo-core-01',
          model: 'Catalyst 9500',
          device_type: 'CISCO_IOSXE',
          site_id: 1,
          ip_address: '127.0.10.11',
          status: 'online',
        },
        {
          id: 503,
          name: 'demo-edge-b-01',
          model: 'FortiGate 200F',
          device_type: 'FORTINET',
          site_id: 1,
          ip_address: '127.0.10.14',
          status: 'online',
        },
        {
          id: 504,
          name: 'demo-edge-a-01',
          model: '7050SX3-48YC8',
          device_type: 'ARISTA_EOS',
          site_id: 1,
          ip_address: '127.0.10.13',
          status: 'online',
        },
      ]),
    });
  });

  await page.route('**/api/v1/sites/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 1, name: 'NetSphere Demo Campus' }]),
    });
  });
};

const mockTopologyEvidence = async (page) => {
  await page.route('**/api/v1/devices/topology/links**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        nodes: [
          {
            id: 201,
            label: 'demo-core-01',
            ip: '127.0.10.11',
            role: 'core',
            status: 'online',
            site_id: 1,
            site_name: 'NetSphere Demo Campus',
            tier: 'core',
            l3: { peer_counts: { total: 2, bgp: 1, ospf: 1 }, state_counts: { healthy: 2, degraded: 0 }, local_asns: [65100] },
          },
          {
            id: 202,
            label: 'demo-dist-01',
            ip: '127.0.10.12',
            role: 'distribution',
            status: 'online',
            site_id: 1,
            site_name: 'NetSphere Demo Campus',
            tier: 'distribution',
            l3: { peer_counts: { total: 3, bgp: 2, ospf: 1 }, state_counts: { healthy: 2, degraded: 1 }, local_asns: [65110] },
          },
          {
            id: 203,
            label: 'demo-edge-a-01',
            ip: '127.0.10.13',
            role: 'access',
            status: 'online',
            site_id: 1,
            site_name: 'NetSphere Demo Campus',
            tier: 'edge',
            l3: { peer_counts: { total: 1, bgp: 0, ospf: 1 }, state_counts: { healthy: 1, degraded: 0 }, local_asns: [] },
          },
          {
            id: 204,
            label: 'demo-edge-b-01',
            ip: '127.0.10.14',
            role: 'security',
            status: 'warning',
            site_id: 1,
            site_name: 'NetSphere Demo Campus',
            tier: 'edge',
            l3: { peer_counts: { total: 1, bgp: 1, ospf: 0 }, state_counts: { healthy: 0, degraded: 1 }, local_asns: [65120] },
          },
        ],
        links: [
          {
            source: 201,
            target: 202,
            protocol: 'OSPF',
            status: 'active',
            layer: 'l3',
            label: 'OSPF area 0.0.0.0',
            confidence: 0.99,
            evidence: { confidence: 0.99, protocol: 'ospf', layer: 'l3' },
          },
          {
            source: 202,
            target: 203,
            protocol: 'LLDP',
            status: 'active',
            layer: 'l2',
            label: 'xe-0/0/1 <> Ethernet1',
            confidence: 0.97,
            evidence: { confidence: 0.97, protocol: 'lldp', layer: 'l2' },
          },
          {
            source: 202,
            target: 204,
            protocol: 'BGP',
            status: 'degraded',
            layer: 'l3',
            label: 'AS65110 <> AS65120',
            confidence: 0.95,
            evidence: { confidence: 0.95, protocol: 'bgp', layer: 'l3' },
            l3: {
              relationship: 'ebgp',
              state: 'active',
              prefixes_received: 82,
              uptime: '00:12:31',
              source: { local_as: 65110, peer_ip: '192.0.2.20', interface: 'xe-0/0/2' },
              target: { local_as: 65120, peer_ip: '192.0.2.21', interface: 'port1' },
            },
          },
        ],
      }),
    });
  });

  await page.route('**/api/v1/sites/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 1, name: 'NetSphere Demo Campus' }]),
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
};

const mockDiagnosisEvidence = async (page) => {
  await page.route('**/api/v1/diagnosis/one-click', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        summary: {
          status: 'success',
          mode: 'bfs',
          path_health: 'healthy',
          abnormal_count: 1,
          show_collected: 1,
          severity: 'critical',
          confidence: 0.82,
          root_cause: 'bgp_alarm',
        },
        diagnosis: {
          verdict: 'bgp_alarm',
          severity: 'critical',
          confidence: 0.82,
          headline: 'BGP control-plane alarm is active',
          summary: 'BGP session degraded on border uplink',
          path_health: 'healthy',
          next_actions: [
            'Verify BGP neighbor state and last reset cause.',
            'Check route lookup and next-hop reachability.',
            'Review recent routing-policy or peer configuration changes.',
          ],
          warnings: [],
        },
        path_trace: {
          summary: {
            health: 'healthy',
            protocols: ['BGP', 'LLDP'],
            layers: ['l2', 'l3'],
            warnings: [],
          },
        },
        device_health: [
          {
            device_id: 203,
            name: 'demo-edge-a-01',
            ip_address: '127.0.10.13',
            ping_ok: true,
            critical_issues: 0,
            warning_issues: 0,
            info_issues: 0,
            cpu_usage: 27,
            memory_usage: 39,
            health_score: 100,
            risk_level: 'healthy',
            primary_signal: 'healthy',
            notes: [],
            recent_issues: [],
          },
          {
            device_id: 202,
            name: 'demo-dist-01',
            ip_address: '127.0.10.12',
            ping_ok: true,
            critical_issues: 1,
            warning_issues: 0,
            info_issues: 0,
            cpu_usage: 0,
            memory_usage: 0,
            health_score: 82,
            risk_level: 'critical',
            primary_signal: 'active_critical_issue',
            notes: ['1 critical issue(s) active in the recent window.'],
            recent_issues: [
              {
                id: 1,
                title: 'BGP session degraded on border uplink',
                severity: 'critical',
                category: 'routing',
              },
            ],
          },
          {
            device_id: 204,
            name: 'demo-edge-b-01',
            ip_address: '127.0.10.14',
            ping_ok: true,
            critical_issues: 0,
            warning_issues: 1,
            info_issues: 0,
            cpu_usage: 0,
            memory_usage: 0,
            health_score: 92,
            risk_level: 'warning',
            primary_signal: 'active_warning_issue',
            notes: ['1 warning issue(s) active in the recent window.'],
            recent_issues: [
              {
                id: 2,
                title: 'High interface utilization detected',
                severity: 'warning',
                category: 'performance',
              },
            ],
          },
        ],
        abnormal: [
          {
            device_id: 202,
            device_name: 'demo-dist-01',
            device_ip: '127.0.10.12',
            type: 'link',
            root_cause: 'bgp_alarm',
            severity: 'critical',
            confidence: 0.82,
            title: 'BGP control-plane alarm is active',
            summary: 'BGP session degraded on border uplink',
            next_actions: [
              'Verify BGP neighbor state and last reset cause.',
              'Check route lookup and next-hop reachability.',
            ],
            segment: {
              hop: 1,
              from_port: 'xe-0/0/2',
              to_port: 'port1',
              protocol: 'BGP',
              layer: 'l3',
              status: 'active',
              peer_name: 'demo-edge-b-01',
            },
            evidence: [
              { kind: 'link_status', label: 'Link status', value: 'active', status: 'warning' },
              { kind: 'protocol', label: 'Protocol', value: 'BGP', status: 'info' },
              { kind: 'layer', label: 'Layer', value: 'l3', status: 'info' },
              { kind: 'path_status', label: 'Ping', value: 'reachable', status: 'healthy' },
              { kind: 'recent_issues', label: 'Recent issues', value: 'critical=1, warning=0', status: 'warning' },
            ],
          },
        ],
        show: [
          {
            device_id: 202,
            device_name: 'demo-dist-01',
            device_ip: '127.0.10.12',
            reasons: ['bgp_alarm'],
            plan: [
              {
                command: 'show ip bgp summary',
                area: 'control_plane',
                purpose: 'Inspect BGP session health on the device.',
                priority: 'primary',
              },
            ],
            results: [
              {
                command: 'show ip bgp summary',
                area: 'control_plane',
                purpose: 'Inspect BGP session health on the device.',
                priority: 'primary',
                output: 'Neighbor 192.0.2.21 Active',
              },
            ],
          },
        ],
        ts: '2026-03-17T11:22:45Z',
      }),
    });
  });
};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  await fs.rm(OUTPUT_DIR, { recursive: true, force: true });
  await fs.mkdir(OUTPUT_DIR, { recursive: true });
});

test.use({
  viewport: { width: 1600, height: 1200 },
  deviceScaleFactor: 1,
});

test('capture auto discovery evidence panel', async ({ page }) => {
  await ensureKoreanLocale(page);
  await mockCoreApis(page);
  await mockInventoryEvidence(page);

  await page.goto('/devices');

  const panel = page.getByTestId('device-inventory-panel');
  await expect(panel).toBeVisible();
  await expect(page.getByTestId('device-inventory-table')).toBeVisible();
  await panel.screenshot({
    path: path.join(OUTPUT_DIR, 'auto-discovery-panel.png'),
    animations: 'disabled',
  });
});

test('capture auto topology evidence panel', async ({ page }) => {
  await ensureKoreanLocale(page);
  await mockCoreApis(page);
  await mockTopologyEvidence(page);

  await page.goto('/topology');
  await page.getByTestId('topology-layer-filter-bgp').click();
  await expect(page.getByTestId('bgp-topology-summary')).toBeVisible();
  await page.waitForTimeout(500);

  const panel = page.getByTestId('topology-map-stage');
  await expect(panel).toBeVisible();
  await panel.screenshot({
    path: path.join(OUTPUT_DIR, 'auto-topology-panel.png'),
    animations: 'disabled',
  });
});

test('capture connected nms evidence panel', async ({ page }) => {
  await ensureKoreanLocale(page);
  await mockCoreApis(page);
  await mockDiagnosisEvidence(page);

  await page.goto('/diagnosis');
  const panel = page.getByTestId('diagnosis-evidence-panel');
  await panel.locator('input').nth(0).fill('10.10.10.50');
  await panel.locator('input').nth(1).fill('10.20.20.60');
  await page.getByRole('button').filter({ hasText: /^Run$|^실행$/i }).first().click();

  await expect(panel).toBeVisible();
  await expect(page.getByTestId('diagnosis-verdict')).toContainText(/BGP|bgp/i);
  await panel.screenshot({
    path: path.join(OUTPUT_DIR, 'connected-nms-panel.png'),
    animations: 'disabled',
  });
});
