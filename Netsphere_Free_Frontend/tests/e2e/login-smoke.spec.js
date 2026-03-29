import { test, expect } from '@playwright/test';

test('login page renders core controls', async ({ page }) => {
  await page.goto('/login');

  await expect(page.getByPlaceholder(/enter username/i)).toBeVisible();
  await expect(page.locator('input[type="password"]')).toBeVisible();
  await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();
});
