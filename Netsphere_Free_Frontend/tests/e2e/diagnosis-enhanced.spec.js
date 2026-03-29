import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('diagnosis page shows structured verdict, abnormal hops, and show plan', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  await page.route('**/api/v1/diagnosis/one-click', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        summary: {
          status: 'success',
          mode: 'topology_best_effort',
          path_health: 'degraded',
          abnormal_count: 1,
          show_collected: 1,
          severity: 'warning',
          confidence: 0.87,
          root_cause: 'bgp_session_degraded',
        },
        diagnosis: {
          verdict: 'bgp_session_degraded',
          severity: 'warning',
          confidence: 0.87,
          headline: 'BGP adjacency is degraded',
          summary: 'The traced path relies on a degraded BGP segment.',
          path_health: 'degraded',
          next_actions: [
            'Verify BGP neighbor state and last reset cause.',
            'Check route lookup and next-hop reachability.',
          ],
          warnings: ['Used best-effort topology path with degraded links.'],
        },
        path_trace: {
          summary: {
            health: 'degraded',
            protocols: ['BGP'],
            layers: ['l3'],
            warnings: ['Used best-effort topology path with degraded links.'],
          },
        },
        device_health: [
          {
            device_id: 77,
            name: 'edge-1',
            ip_address: '10.0.0.1',
            ping_ok: true,
            critical_issues: 0,
            warning_issues: 1,
            info_issues: 0,
            cpu_usage: 82.5,
            memory_usage: 63.1,
            health_score: 73,
            risk_level: 'warning',
            primary_signal: 'cpu_elevated',
            notes: ['CPU usage is elevated at 82.5%.'],
            recent_issues: [
              {
                id: 1,
                title: 'BGP Neighbor Down',
                severity: 'warning',
                category: 'system',
              },
            ],
          },
        ],
        abnormal: [
          {
            device_id: 77,
            device_name: 'edge-1',
            device_ip: '10.0.0.1',
            type: 'link',
            root_cause: 'bgp_session_degraded',
            severity: 'warning',
            confidence: 0.87,
            title: 'BGP adjacency is degraded',
            summary: 'The traced path relies on a degraded BGP segment.',
            next_actions: ['Verify BGP neighbor state and last reset cause.'],
            segment: {
              hop: 0,
              from_port: 'Eth1/1',
              to_port: 'Eth1/2',
              protocol: 'BGP',
              layer: 'l3',
              status: 'degraded',
              peer_name: 'edge-2',
            },
            evidence: [
              { kind: 'protocol', label: 'Protocol', value: 'BGP', status: 'info' },
              { kind: 'link_status', label: 'Link status', value: 'degraded', status: 'warning' },
            ],
          },
        ],
        show: [
          {
            device_id: 77,
            device_name: 'edge-1',
            device_ip: '10.0.0.1',
            reasons: ['bgp_session_degraded'],
            plan: [
              {
                command: 'show interfaces Eth1/1',
                area: 'interface',
                purpose: 'Inspect interface state.',
                priority: 'primary',
              },
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
                output: 'Neighbor 10.0.0.2 Idle',
              },
            ],
          },
        ],
        ts: '2026-03-08T01:23:45Z',
      }),
    });
  });

  await page.goto('/diagnosis');
  await page.getByPlaceholder('e.g. 10.0.0.10').fill('10.0.0.10');
  await page.getByPlaceholder('e.g. 10.0.1.20').fill('10.0.1.20');
  await page.getByRole('button', { name: /^Run$/ }).click();

  await expect(page.getByTestId('diagnosis-verdict')).toContainText(/BGP adjacency is degraded/i);
  await expect(page.getByTestId('diagnosis-verdict')).toContainText(/Root Cause: bgp_session_degraded/i);
  await expect(page.getByTestId('diagnosis-abnormal-card-77-0')).toContainText(/Eth1\/1/);
  await expect(page.getByTestId('diagnosis-device-card-77')).toContainText(/82\.5%/);
  await expect(page.getByTestId('diagnosis-show-device-77')).toContainText(/show ip bgp summary/i);
  await expect(page.getByTestId('diagnosis-path-warning-list')).toContainText('Used best-effort topology path with degraded links.');
});
