import { test, expect } from '@playwright/test';

test('login shows a clear invalid-credentials message for 401 responses', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('nm_locale', 'ko');
  });

  await page.route('**/api/v1/auth/bootstrap/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: false,
        initial_admin_required: false,
        deployment_role: 'pro_server',
      }),
    });
  });

  await page.route('**/api/v1/auth/login', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: {
          code: 'AUTH_CREDENTIALS_INVALID',
          message: 'Incorrect username or password',
        },
      }),
    });
  });

  await page.goto('/login');
  await page.locator('input[type="text"]').first().fill('admin');
  await page.locator('input[type="password"]').first().fill('wrong-password');
  await page.locator('form button[type="submit"]').first().click();

  await expect(page.getByTestId('login-error-message')).toContainText('아이디 또는 비밀번호가 올바르지 않습니다.');
  await expect(page.getByTestId('login-error-message')).not.toContainText('401');
});
