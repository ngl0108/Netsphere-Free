import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('settings lint guard blocks save on conflicts and allows save after lint/options', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  let settingsPutCalls = 0;
  let lintPostCalls = 0;

  await page.route('**/api/v1/settings/general', async (route) => {
    const method = route.request().method().toUpperCase();
    if (method === 'PUT') {
      settingsPutCalls += 1;
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
        closed_loop_rules_json:
          '[{"id":"rule-1","enabled":true,"source":"any","condition":{"path":"summary.cpu_avg","operator":">=","value":80},"action":{"type":"notify","title":"CPU high","message":"high","payload":{}}}]',
      }),
    });
  });

  await page.route('**/api/v1/intent/closed-loop/rules/lint', async (route) => {
    const method = route.request().method().toUpperCase();
    if (method === 'POST') {
      lintPostCalls += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rules_total: 1,
          rules_enabled: 1,
          conflicts_count: 0,
          warnings_count: 1,
          conflicts: [],
          warnings: [
            {
              type: 'redundant_enabled_rules',
              message: 'Multiple enabled rules have identical condition and action.',
              rule_ids: ['rule-1', 'rule-2'],
            },
          ],
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        rules_total: 2,
        rules_enabled: 2,
        conflicts_count: 2,
        warnings_count: 0,
        conflicts: [
          {
            type: 'condition_action_conflict',
            message: 'Enabled rules share the same condition but define different actions.',
            rule_ids: ['rule-a', 'rule-b'],
          },
        ],
        warnings: [],
      }),
    });
  });

  await page.route('**/api/v1/devices/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.goto('/settings');

  const saveButton = page.getByRole('button', { name: /save changes/i });
  await expect(page.getByRole('button', { name: /lint: 2 conflicts/i })).toBeVisible();
  await expect(saveButton).toBeDisabled();

  const guardToggle = page.getByLabel('Block Save on Conflicts');
  await guardToggle.uncheck();
  await expect(saveButton).toBeEnabled();
  await guardToggle.check();
  await expect(saveButton).toBeDisabled();

  await page.getByRole('button', { name: /lint draft json/i }).click();
  await expect.poll(() => lintPostCalls).toBe(1);
  await expect(page.getByRole('button', { name: /lint: 1 warning/i })).toBeVisible();
  await expect(saveButton).toBeEnabled();

  await saveButton.click();
  await expect.poll(() => settingsPutCalls).toBe(1);
});
