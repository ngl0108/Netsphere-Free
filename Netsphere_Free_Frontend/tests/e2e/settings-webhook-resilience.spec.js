import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('alert channel retry values are clamped and persisted safely', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  let savedSettingsPayload = null;

  await page.route('**/api/v1/settings/general', async (route) => {
    const method = route.request().method().toUpperCase();
    if (method === 'PUT') {
      savedSettingsPayload = route.request().postDataJSON();
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'Settings updated', count: 1 }) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        product_setup_completed: 'true',
        product_operating_mode: 'wan_segment_only',
        session_timeout: '30',
        webhook_enabled: 'true',
        webhook_url: 'https://jira.local/rest/api/2/issue',
        webhook_delivery_mode: 'jira',
        webhook_auth_type: 'none',
        webhook_jira_project_key: 'NET',
        webhook_jira_issue_type: 'Task',
        webhook_timeout_seconds: '5',
        webhook_retry_attempts: '3',
        webhook_retry_backoff_seconds: '1',
        webhook_retry_max_backoff_seconds: '8',
        webhook_retry_jitter_seconds: '0.2',
      }),
    });
  });
  await page.route('**/api/v1/intent/closed-loop/rules/lint', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ rules_total: 0, rules_enabled: 0, conflicts_count: 0, warnings_count: 0, conflicts: [], warnings: [] }),
    });
  });
  await page.route('**/api/v1/devices**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });
  await page.route('**/api/v1/settings/test-webhook-connector', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: 'Webhook sent successfully',
        result: { mode: 'jira', status_code: 201, attempts: 1, delivery_id: 'e2e-delivery-2' },
      }),
    });
  });

  await page.goto('/settings');
  await page.getByText('Alert Channels').click();

  await page.locator('input[name="webhook_timeout_seconds"]').fill('100');
  await page.locator('input[name="webhook_retry_attempts"]').fill('99');
  await page.locator('input[name="webhook_retry_backoff_seconds"]').fill('-5');
  await page.locator('input[name="webhook_retry_max_backoff_seconds"]').fill('999');
  await page.locator('input[name="webhook_retry_jitter_seconds"]').fill('42');

  await page.getByRole('button', { name: /save changes/i }).click();

  expect(savedSettingsPayload).toBeTruthy();
  const settings = savedSettingsPayload?.settings || {};
  expect(settings.webhook_timeout_seconds).toBe(30);
  expect(settings.webhook_retry_attempts).toBe(8);
  expect(settings.webhook_retry_backoff_seconds).toBe(0);
  expect(settings.webhook_retry_max_backoff_seconds).toBe(300);
  expect(settings.webhook_retry_jitter_seconds).toBe(10);
});
