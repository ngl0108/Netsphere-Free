import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('settings saves autonomy threshold fields', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  let settingsPutCalls = 0;
  let lastPayload = null;

  await page.route('**/api/v1/settings/general', async (route) => {
    const method = route.request().method().toUpperCase();
    if (method === 'PUT') {
      settingsPutCalls += 1;
      try {
        lastPayload = route.request().postDataJSON();
      } catch (_e) {
        lastPayload = null;
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        product_setup_completed: 'true',
        product_operating_mode: 'wan_segment_only',
        session_timeout: '30',
        ops_alerts_min_auto_action_rate_pct: '60',
        ops_alerts_max_operator_intervention_rate_pct: '40',
        closed_loop_rules_json: '[]',
      }),
    });
  });

  await page.route('**/api/v1/intent/closed-loop/rules/lint', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        rules_total: 0,
        rules_enabled: 0,
        conflicts_count: 0,
        warnings_count: 0,
        conflicts: [],
        warnings: [],
      }),
    });
  });

  await page.route('**/api/v1/devices/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.goto('/settings');

  const minAutoInput = page.locator('input[name="ops_alerts_min_auto_action_rate_pct"]');
  const maxOperatorInput = page.locator('input[name="ops_alerts_max_operator_intervention_rate_pct"]');
  await expect(minAutoInput).toBeVisible();
  await expect(maxOperatorInput).toBeVisible();

  await minAutoInput.fill('75');
  await maxOperatorInput.fill('25');

  await page.getByRole('button', { name: /save changes/i }).click();

  await expect.poll(() => settingsPutCalls).toBe(1);
  await expect
    .poll(() => Number(lastPayload?.settings?.ops_alerts_min_auto_action_rate_pct ?? NaN))
    .toBe(75);
  await expect
    .poll(() => Number(lastPayload?.settings?.ops_alerts_max_operator_intervention_rate_pct ?? NaN))
    .toBe(25);
});
