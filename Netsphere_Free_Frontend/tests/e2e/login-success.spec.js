import { test, expect } from '@playwright/test';

test('login success redirects to dashboard', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('nm_locale', 'en');
  });

  await page.route('**/api/v1/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: 'e2e-token', token_type: 'bearer' }),
    });
  });
  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        username: 'admin',
        role: 'admin',
        eula_accepted: true,
        must_change_password: false,
      }),
    });
  });
  await page.route('**/api/v1/settings/general', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        product_setup_completed: 'true',
        product_operating_mode: 'wan_segment_only',
        session_timeout: '30',
      }),
    });
  });

  await page.goto('/login');
  await page.locator('input[type="text"]').first().fill('admin');
  await page.locator('input[type="password"]').first().fill('admin123');
  await page.locator('form button[type="submit"]').first().click();

  await expect(page).toHaveURL(/\/$/);
});
