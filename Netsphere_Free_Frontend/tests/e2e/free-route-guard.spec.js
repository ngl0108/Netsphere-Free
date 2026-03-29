import { test, expect } from '@playwright/test';

import { gotoWithRetry, loginLiveUserAtBase } from './scenario-lab-live.helpers';

const FREE_BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:18080';

test('NetSphere Free hides blocked navigation and blocks direct access to pro-only routes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });

  await loginLiveUserAtBase(page, FREE_BASE_URL, {
    username: 'admin',
    password: 'Password1!!@',
    locale: 'ko',
  });

  const sidebar = page.getByTestId('app-sidebar');
  await expect(sidebar).toHaveCount(1);
  await expect(sidebar).toContainText(/Dashboard|대시보드/i);
  await expect(sidebar).toContainText(/Auto Discovery|오토 디스커버리/i);
  await expect(page.getByRole('button', { name: /Data Contribution|Data Handling Audit|데이터 처리 감사/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Settings|설정/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Users|사용자/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Approval Queue|Approval Center|변경 승인 센터/i })).toHaveCount(0);

  await gotoWithRetry(page, new URL('/settings', FREE_BASE_URL).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('policy-blocked-page')).toBeVisible();
  await expect(page.locator('body')).toContainText(/NetSphere Free|무료/i);

  await gotoWithRetry(page, new URL('/preview/contribute', FREE_BASE_URL).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('preview-audit-policy-card')).toBeVisible();
  await expect(page.getByTestId('preview-audit-policy-card')).toContainText(/Locked installation policy|잠긴 설치 정책/i);
});
