import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('topology node panel keeps drilldown actions in the map context', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

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
            site_name: 'WAN',
            tier: 'core',
            vendor: 'cisco',
            model: 'Catalyst 9500',
            version: '17.9.4',
            metrics: { cpu: 27, memory: 39, traffic_in: 245000000, traffic_out: 198000000 },
          },
        ],
        links: [],
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

  await page.goto('/topology');

  await expect(page.getByTestId('topology-map-stage')).toBeVisible();
  await page.getByText('edge-r1').click();
  const panel = page.getByTestId('topology-node-panel');

  await expect(panel).toBeVisible();
  await expect(panel.getByText('Catalyst 9500')).toBeVisible();
  await expect(panel.getByText('WAN')).toBeVisible();
  await expect(panel.getByRole('button', { name: /Open Device|장비 열기/ })).toBeVisible();
  await expect(panel.getByRole('button', { name: /Open Observability|옵저버빌리티 열기/ })).toBeVisible();
  await expect(panel.getByRole('button', { name: /Grafana/ })).toBeVisible();
  await expect(panel.getByText(/Double-click opens Device Detail directly|더블클릭하면 장비 상세로 바로 이동합니다/)).toBeVisible();
});
