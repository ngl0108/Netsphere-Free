import { chromium } from 'playwright';

import {
  attachPageGuards,
  loginLiveUserAtBase,
  pickScenarioAdmin,
  resolveScenarioReport,
} from './scenario-lab-live.helpers.js';

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!key.startsWith('--')) continue;
    const name = key.slice(2);
    const value = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[index + 1] : 'true';
    args[name] = value;
    if (value !== 'true') index += 1;
  }
  return args;
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const ROUTE_SETS = {
  pro: {
    baseUrl: process.env.PRO_AUDIT_BASE_URL || 'http://localhost',
    report: resolveScenarioReport('pro', process.env.PRO_AUDIT_SCENARIO || 'pro-hybrid-operations'),
    allowed: [
      '/',
      '/devices',
      '/sites',
      '/topology',
      '/config',
      '/images',
      '/visual-config',
      '/policy',
      '/ztp',
      '/fabric',
      '/compliance',
      '/discovery',
      '/logs',
      '/audit',
      '/wireless',
      '/notifications',
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
      '/observability',
      '/automation',
      '/diagnosis',
    ],
    blocked: ['/preview/contribute'],
  },
  free: {
    baseUrl: process.env.FREE_AUDIT_BASE_URL || 'http://127.0.0.1:18080',
    report: resolveScenarioReport('free', process.env.FREE_AUDIT_SCENARIO || 'free-enterprise-visibility'),
    allowed: [
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
      '/automation',
      '/diagnosis',
      '/edition/compare',
      '/preview/contribute',
    ],
    blocked: [
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
    ],
  },
};

async function openAtBase(page, baseUrl, path) {
  process.stdout.write(`[route-audit] visit ${baseUrl}${path}\n`);
  await page.goto(new URL(path, baseUrl).toString(), { waitUntil: 'commit', timeout: 60000 });
}

async function assertRouteRendered(page, scope, path) {
  await page.waitForFunction(
    () => {
      const text = String(document.body?.innerText || '').trim();
      return text && text !== 'Loading...' && text !== 'Loading...\nLoading...';
    },
    null,
    { timeout: 60000 },
  );
  const blockedVisible = await page.getByTestId('policy-blocked-page').isVisible().catch(() => false);
  assert(!blockedVisible, `${scope}:${path} rendered policy-blocked page unexpectedly`);
  const bodyText = await page.locator('body').innerText();
  assert(!/Internal Server Error|내부 서버 오류/i.test(bodyText), `${scope}:${path} rendered app error fallback`);
  assert(Boolean(String(bodyText || '').trim()), `${scope}:${path} rendered empty body`);
}

async function assertRouteBlocked(page, scope, path) {
  await page.getByTestId('policy-blocked-page').waitFor({ state: 'visible', timeout: 60000 });
  const bodyText = await page.locator('body').innerText();
  assert(/disabled|available only|비활성|Free|Preview/i.test(bodyText), `${scope}:${path} missing policy-blocked messaging`);
}

async function settleRoute(page) {
  await page.waitForLoadState('networkidle', { timeout: 3000 }).catch(() => {});
  await page.waitForTimeout(450);
}

async function runMatrix(scope) {
  const config = ROUTE_SETS[scope];
  if (!config) {
    throw new Error(`Unsupported scope '${scope}'.`);
  }

  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ acceptDownloads: true });
    const page = await context.newPage();
    const guards = attachPageGuards(page);
    const credentials = pickScenarioAdmin(config.report);
    try {
      await loginLiveUserAtBase(page, config.baseUrl, { ...credentials, locale: 'ko' });

      for (const path of config.allowed) {
        await openAtBase(page, config.baseUrl, path);
        assert(!/\/login(?:[/?#]|$)/.test(page.url()), `${scope}:${path} redirected back to login`);
        await assertRouteRendered(page, scope, path);
        await settleRoute(page);
        guards.assertClean();
        guards.reset();
      }

      for (const path of config.blocked) {
        await openAtBase(page, config.baseUrl, path);
        await assertRouteBlocked(page, scope, path);
        await settleRoute(page);
        guards.assertClean();
        guards.reset();
      }
      return {
        scope,
        status: 'passed',
        allowed_routes: config.allowed.length,
        blocked_routes: config.blocked.length,
      };
    } catch (error) {
      const bodyText = await page.locator('body').innerText().catch(() => '');
      const debugDetails = [
        `current_url=${page.url()}`,
        guards.pageErrors?.length ? `page_errors=${guards.pageErrors.join(' | ')}` : '',
        guards.consoleErrors?.length ? `console_errors=${guards.consoleErrors.join(' | ')}` : '',
        bodyText ? `body_excerpt=${String(bodyText).slice(0, 500)}` : '',
      ]
        .filter(Boolean)
        .join('\n');
      throw new Error(`${String(error?.message || error)}\n${debugDetails}`);
    } finally {
      await context.close();
    }
  } finally {
    await browser.close();
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const target = String(args.target || 'all').trim().toLowerCase();
  const scopes = target === 'all' ? ['pro', 'free'] : [target];
  const results = [];

  for (const scope of scopes) {
    results.push(await runMatrix(scope));
  }

  process.stdout.write(`${JSON.stringify({ generated_at: new Date().toISOString(), results }, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${String(error?.stack || error)}\n`);
  process.exit(1);
});
