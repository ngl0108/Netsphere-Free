import { test, expect } from '@playwright/test';

import {
  attachPageGuards,
  gotoWithRetry,
  loginLiveUserAtBase,
  pickScenarioAdmin,
  resolveScenarioReport,
} from './scenario-lab-live.helpers';

const FREE_BASE_URL = process.env.FREE_AUDIT_BASE_URL || 'http://127.0.0.1:18080';
const REPORT = resolveScenarioReport('free', process.env.FREE_AUDIT_SCENARIO || 'free-enterprise-visibility');

const ALLOWED_ROUTES = [
  '/',
  '/devices',
  '/sites',
  '/topology',
  '/discovery',
  '/logs',
  '/audit',
  '/wireless',
  '/notifications',
  '/observability',
  '/observability/deep-dive',
  '/automation',
  '/diagnosis',
  '/edition/compare',
  '/preview/contribute',
];

const BLOCKED_ROUTES = [
  '/config',
  '/images',
  '/visual-config',
  '/policy',
  '/ztp',
  '/fabric',
  '/compliance',
  '/settings',
  '/cloud/accounts',
  '/cloud/intents',
  '/preventive-checks',
  '/monitoring-profiles',
  '/source-of-truth',
  '/state-history',
  '/intent-templates',
  '/service-groups',
  '/operations-reports',
  '/users',
  '/approval',
];

const openAtBase = async (page, path) => {
  await gotoWithRetry(page, new URL(path, FREE_BASE_URL).toString(), { waitUntil: 'domcontentloaded' });
};

const assertRouteRendered = async (page) => {
  await expect(page.getByTestId('app-sidebar')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('policy-blocked-page')).toHaveCount(0);
  await expect(page.getByText(/Internal Server Error|내부 서버 오류/i)).toHaveCount(0);
  await page.waitForFunction(
    () => {
      const text = String(document.body?.innerText || '').trim();
      return text && text !== 'Loading...' && text !== 'Loading...\nLoading...';
    },
    null,
    { timeout: 15000 },
  );
};

test.describe.configure({ mode: 'serial' });

test('functional route matrix free covers allowed and blocked surfaces', async ({ page }) => {
  test.slow();
  test.setTimeout(240000);

  const guards = attachPageGuards(page);
  const credentials = pickScenarioAdmin(REPORT);

  await loginLiveUserAtBase(page, FREE_BASE_URL, { ...credentials, locale: 'ko' });

  for (const path of ALLOWED_ROUTES) {
    await openAtBase(page, path);
    await expect(page).not.toHaveURL(/\/login(?:[/?#]|$)/);
    await assertRouteRendered(page);
  }

  for (const path of BLOCKED_ROUTES) {
    await openAtBase(page, path);
    await expect(page.getByTestId('policy-blocked-page')).toBeVisible({ timeout: 30000 });
  }

  guards.assertClean();
});
