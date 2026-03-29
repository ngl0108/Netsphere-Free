import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const REPORTS_ROOT = path.join(REPO_ROOT, 'scenario-lab', 'reports');

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

function readJson(target) {
  return JSON.parse(fs.readFileSync(target, 'utf8').replace(/^\uFEFF/, ''));
}

function loadScenarioReportsByPrefix(prefix) {
  return fs
    .readdirSync(REPORTS_ROOT)
    .filter((name) => name.startsWith(`${prefix}-`) && name.endsWith('.latest.json'))
    .sort()
    .map((name) => readJson(path.join(REPORTS_ROOT, name)));
}

function pickScenarioAdmin(report) {
  const accounts = Array.isArray(report?.credentials?.accounts) ? report.credentials.accounts : [];
  const admin = accounts.find((row) => String(row?.role || '').trim().toLowerCase() === 'admin');
  if (!admin?.username) {
    throw new Error(`Scenario report '${report?.slug || 'unknown'}' does not contain an admin account.`);
  }
  return {
    username: admin.username,
    password: String(report?.credentials?.password || 'Password1!!@'),
  };
}

function buildScenarioMatchers(report) {
  const slug = String(report?.slug || '').trim();
  const slugToken = slug.replace(/-/g, '_').toUpperCase();
  return {
    slug,
    deviceName: `LAB-${slugToken}`,
    groupNameFragment: `[LAB ${slug}]`,
  };
}

function unwrapEnvelope(payload) {
  if (
    payload &&
    typeof payload === 'object' &&
    Object.prototype.hasOwnProperty.call(payload, 'success') &&
    Object.prototype.hasOwnProperty.call(payload, 'data') &&
    payload.success === true
  ) {
    return payload.data;
  }
  return payload;
}

function unwrapCollection(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === 'object') {
    if (Array.isArray(payload.items)) return payload.items;
    if (Array.isArray(payload.rows)) return payload.rows;
    if (Array.isArray(payload.results)) return payload.results;
    if (Array.isArray(payload.devices)) return payload.devices;
    if (Array.isArray(payload.service_groups)) return payload.service_groups;
  }
  return [];
}

function extractAccessToken(payload) {
  const normalized = unwrapEnvelope(payload);
  return (
    normalized?.access_token ||
    normalized?.token ||
    normalized?.data?.access_token ||
    normalized?.data?.token ||
    payload?.access_token ||
    payload?.token ||
    null
  );
}

async function fetchJsonWithAuth(page, targetPath, init = {}) {
  return page
    .evaluate(
      async ({ nextPath, requestInit }) => {
        const token = localStorage.getItem('authToken');
        const headers = new Headers(requestInit?.headers || {});
        if (token) {
          headers.set('Authorization', `Bearer ${token}`);
        }
        const response = await fetch(nextPath, {
          ...requestInit,
          headers,
        });
        const text = await response.text();
        let data = null;
        try {
          data = text ? JSON.parse(text) : null;
        } catch (error) {
          data = text;
        }
        return {
          status: response.status,
          ok: response.ok,
          data,
        };
      },
      { nextPath: targetPath, requestInit: init },
    )
    .then((result) => ({
      ...result,
      data: unwrapEnvelope(result.data),
    }));
}

async function navigate(page, baseUrl, targetPath) {
  await page.goto(new URL(targetPath, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function waitForPath(page, matcher, timeout = 15000) {
  await page.waitForURL((url) => matcher.test(url.toString()), { timeout });
}

async function pollUntil(action, predicate, { timeoutMs = 15000, intervalMs = 500, description = 'condition' } = {}) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const value = await action();
    if (predicate(value)) return value;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Timed out waiting for ${description}.`);
}

function attachPageGuards(page) {
  const pageErrors = [];
  const consoleErrors = [];

  page.on('pageerror', (error) => {
    pageErrors.push(String(error?.message || error));
  });

  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = String(message.text() || '').trim();
    if (!text) return;
    consoleErrors.push(text);
  });

  return {
    assertClean(scopeLabel) {
      assert(pageErrors.length === 0, `${scopeLabel}: unexpected page errors\n${pageErrors.join('\n')}`);
      assert(consoleErrors.length === 0, `${scopeLabel}: unexpected console errors\n${consoleErrors.join('\n')}`);
    },
  };
}

async function loginLiveUser(page, baseUrl, credentials, locale = 'ko') {
  const formData = new FormData();
  formData.set('username', credentials.username);
  formData.set('password', credentials.password);

  const loginResponse = await fetch(new URL('/api/v1/auth/login', baseUrl).toString(), {
    method: 'POST',
    body: formData,
  });
  const loginText = await loginResponse.text();
  let loginPayload = null;
  try {
    loginPayload = loginText ? JSON.parse(loginText) : null;
  } catch (error) {
    loginPayload = { raw: loginText };
  }

  const token = extractAccessToken(loginPayload);
  assert(loginResponse.ok && token, `Live login failed (${loginResponse.status}) for '${credentials.username}'`);

  const meResponse = await fetch(new URL('/api/v1/auth/me', baseUrl).toString(), {
    headers: { Authorization: `Bearer ${token}` },
  });
  const meText = await meResponse.text();
  let mePayload = null;
  try {
    mePayload = meText ? JSON.parse(meText) : null;
  } catch (error) {
    mePayload = null;
  }
  const user = unwrapEnvelope(mePayload) || {
    username: credentials.username,
    role: 'viewer',
    eula_accepted: true,
    must_change_password: false,
  };

  await page.addInitScript(({ nextLocale, nextToken, nextUser, lastActiveAt }) => {
    localStorage.setItem('nm_locale', nextLocale);
    localStorage.setItem('authToken', nextToken);
    localStorage.setItem('authUser', JSON.stringify(nextUser));
    localStorage.setItem('authLastActiveAt', String(lastActiveAt));
  }, {
    nextLocale: locale,
    nextToken: token,
    nextUser: user,
    lastActiveAt: Date.now(),
  });

  await navigate(page, baseUrl, '/');
  await page.waitForFunction(
    () => {
      const text = String(document.body?.innerText || '').trim();
      return window.location.pathname !== '/login' && text && text !== 'Loading...' && text !== 'Loading...\nLoading...';
    },
    null,
    { timeout: 20000 },
  );
}

async function runProScenario(page, baseUrl, report) {
  const matchers = buildScenarioMatchers(report);

  const devicesResponse = await fetchJsonWithAuth(page, '/api/v1/devices/?limit=1000');
  assert(devicesResponse.status === 200, `${report.slug}: devices API returned ${devicesResponse.status}`);
  const devices = unwrapCollection(devicesResponse.data);
  assert(devices.length > 0, `${report.slug}: devices list is empty`);
  assert(
    devices.some((row) => String(row?.name || '').includes(matchers.deviceName)),
    `${report.slug}: scenario device prefix '${matchers.deviceName}' not found`,
  );

  await navigate(page, baseUrl, '/service-groups');
  const serviceGroupsResponse = await fetchJsonWithAuth(page, '/api/v1/service-groups/');
  assert(serviceGroupsResponse.status === 200, `${report.slug}: service groups API returned ${serviceGroupsResponse.status}`);
  const serviceGroups = unwrapCollection(serviceGroupsResponse.data);
  assert(
    serviceGroups.some((row) => String(row?.name || '').includes(matchers.groupNameFragment)),
    `${report.slug}: service group fragment '${matchers.groupNameFragment}' not found`,
  );

  await navigate(page, baseUrl, '/source-of-truth');
  const sourceOfTruthResponse = await fetchJsonWithAuth(page, '/api/v1/automation-hub/source-of-truth/summary');
  assert(sourceOfTruthResponse.status === 200, `${report.slug}: source of truth API returned ${sourceOfTruthResponse.status}`);
  assert(Number(sourceOfTruthResponse?.data?.metrics?.devices_total || 0) > 0, `${report.slug}: source of truth metrics are empty`);

  await navigate(page, baseUrl, '/intent-templates');
  const useTemplateButton = page.getByRole('button', { name: /Use Template/i }).first();
  await useTemplateButton.waitFor({ state: 'visible' });
  await useTemplateButton.click();
  await waitForPath(page, /\/cloud\/intents/);
  await page.getByTestId('cloud-intents-prefill').waitFor({ state: 'visible' });

  await navigate(page, baseUrl, '/preventive-checks');
  const runNowButton = page.getByRole('button', { name: /Run now/i }).first();
  const hasRunNowButton = await runNowButton.isVisible().catch(() => false);
  if (!hasRunNowButton) {
    await page.waitForFunction(
      () => {
        const text = String(document.body?.innerText || '');
        return text.includes('Preventive Checks') || text.includes('No preventive check templates yet.');
      },
      null,
      { timeout: 15000 },
    );
  }

  await navigate(page, baseUrl, '/operations-reports');
  const openApprovalCenterButton = page.getByRole('button', { name: /Open Approval Center/i }).first();
  await openApprovalCenterButton.waitFor({ state: 'visible' });
  await openApprovalCenterButton.click();
  await waitForPath(page, /\/approval/);

  await navigate(page, baseUrl, '/notifications');
  await page.waitForFunction(
    () => {
      const text = String(document.body?.innerText || '');
      return text.includes('Notifications') || text.includes('알림') || text.includes('Active Alarms Center');
    },
    null,
    { timeout: 15000 },
  );
  const activeIssuesResponse = await fetchJsonWithAuth(page, '/api/v1/sdn/issues/active');
  assert(activeIssuesResponse.status === 200, `${report.slug}: issues API returned ${activeIssuesResponse.status}`);
  const activeIssues = unwrapCollection(activeIssuesResponse.data);
  const issueStateHistoryButton = activeIssues.length > 0
    ? page.locator('[data-testid^="issue-open-state-history-"]').first()
    : null;
  const hasIssueStateHistory = issueStateHistoryButton
    ? await (async () => {
        try {
          await issueStateHistoryButton.waitFor({ state: 'visible', timeout: 15000 });
          return true;
        } catch (error) {
          return false;
        }
      })()
    : false;
  if (hasIssueStateHistory) {
    await issueStateHistoryButton.click();
    await waitForPath(page, /\/state-history/);
  } else {
    const blocked = await page.getByTestId('policy-blocked-page').isVisible().catch(() => false);
    assert(!blocked, `${report.slug}: notifications page was unexpectedly policy-blocked`);
  }

  if (Number(report?.counts?.cloud_accounts || 0) > 0) {
    await navigate(page, baseUrl, '/cloud/accounts');
    const cloudAccountsResponse = await fetchJsonWithAuth(page, '/api/v1/cloud/accounts');
    assert(cloudAccountsResponse.status === 200, `${report.slug}: cloud accounts API returned ${cloudAccountsResponse.status}`);
    const cloudAccounts = unwrapCollection(cloudAccountsResponse.data);
    assert(
      cloudAccounts.length >= Number(report.counts.cloud_accounts),
      `${report.slug}: cloud account count ${cloudAccounts.length} is below expected ${report.counts.cloud_accounts}`,
    );
  }
}

async function runFreeScenario(page, baseUrl, report) {
  const matchers = buildScenarioMatchers(report);
  const devicesResponse = await fetchJsonWithAuth(page, '/api/v1/devices/?limit=1000');
  assert(devicesResponse.status === 200, `${report.slug}: devices API returned ${devicesResponse.status}`);
  const devices = unwrapCollection(devicesResponse.data);
  assert(devices.length > 0, `${report.slug}: devices list is empty`);
  assert(
    devices.some((row) => String(row?.name || '').includes(matchers.deviceName)),
    `${report.slug}: scenario device prefix '${matchers.deviceName}' not found`,
  );

  const managedSummaryResponse = await fetchJsonWithAuth(page, '/api/v1/devices/managed-summary');
  assert(managedSummaryResponse.status === 200, `${report.slug}: managed summary returned ${managedSummaryResponse.status}`);
  assert(Number(managedSummaryResponse?.data?.managed_limit || 0) === 50, `${report.slug}: managed limit is not 50`);

  const previewPolicyResponse = await fetchJsonWithAuth(page, '/api/v1/preview/policy');
  assert(previewPolicyResponse.status === 200, `${report.slug}: preview policy returned ${previewPolicyResponse.status}`);
  assert(Boolean(previewPolicyResponse?.data?.upload_decision_recorded), `${report.slug}: upload decision not recorded`);
  assert(Boolean(previewPolicyResponse?.data?.upload_locked), `${report.slug}: upload policy is not locked`);

  await navigate(page, baseUrl, '/automation');
  await page.getByTestId('automation-preview-panel').waitFor({ state: 'visible' });
  await page.getByTestId('automation-preview-title').waitFor({ state: 'visible' });
  await page.getByTestId('automation-preview-blocked-features').waitFor({ state: 'visible' });

  const managedDevice = devices.find((row) => String(row?.management_state || '').trim().toLowerCase() === 'managed');
  const discoveredDevice = devices.find((row) => String(row?.management_state || '').trim().toLowerCase() !== 'managed');
  assert(Boolean(managedDevice?.name), `${report.slug}: managed device candidate missing`);
  assert(Boolean(discoveredDevice?.name), `${report.slug}: discovered-only device candidate missing`);

  await navigate(page, baseUrl, '/devices');
  const deviceSearchInput = page.getByPlaceholder(/Search by Hostname or IP/i);
  await deviceSearchInput.waitFor({ state: 'visible' });
  await deviceSearchInput.fill(managedDevice.name);
  const managedRow = page.locator('tr', { hasText: managedDevice.name }).first();
  await managedRow.waitFor({ state: 'visible' });
  await managedRow.hover();
  await managedRow.getByRole('button', { name: /Release Slot/i }).click({ force: true });
  await pollUntil(
    async () => {
      const response = await fetchJsonWithAuth(page, '/api/v1/devices/?limit=1000');
      const rows = unwrapCollection(response.data);
      return String(rows.find((row) => Number(row?.id) === Number(managedDevice.id))?.management_state || '');
    },
    (value) => value === 'discovered_only',
    { description: `${report.slug}: managed device state after release` },
  );

  await navigate(page, baseUrl, '/devices');
  await deviceSearchInput.waitFor({ state: 'visible' });
  await deviceSearchInput.fill(discoveredDevice.name);
  await pollUntil(
    async () => {
      const response = await fetchJsonWithAuth(page, '/api/v1/devices/managed-summary');
      return Number(response?.data?.remaining_slots || 0);
    },
    (value) => value > 0,
    { description: `${report.slug}: remaining managed slots after release` },
  );

  const discoveredRow = page.locator('tr', { hasText: discoveredDevice.name }).first();
  await discoveredRow.waitFor({ state: 'visible' });
  await discoveredRow.hover();
  await discoveredRow.getByRole('button', { name: /Make Managed/i }).click({ force: true });
  await pollUntil(
    async () => {
      const response = await fetchJsonWithAuth(page, '/api/v1/devices/?limit=1000');
      const rows = unwrapCollection(response.data);
      return String(rows.find((row) => Number(row?.id) === Number(discoveredDevice.id))?.management_state || '');
    },
    (value) => value === 'managed',
    { description: `${report.slug}: discovered-only device state after promote` },
  );

  await navigate(page, baseUrl, '/preview/contribute');
  await page.getByTestId('preview-audit-title').waitFor({ state: 'visible' });
  await page.getByTestId('preview-audit-policy-card').waitFor({ state: 'visible' });
  const recordButtons = page.locator('button').filter({ hasText: /^preview-/i });
  await recordButtons.first().waitFor({ state: 'visible' });

  await navigate(page, baseUrl, '/service-groups');
  await page.waitForLoadState('networkidle');
  const blocked = await page.getByTestId('policy-blocked-page').isVisible().catch(() => false);
  assert(blocked, `${report.slug}: service groups page was not policy-blocked in Free`);

  await navigate(page, baseUrl, '/edition/compare');
  const editionCompareText = await page.locator('body').innerText();
  assert(/Managed up to 50 nodes/i.test(editionCompareText), `${report.slug}: edition compare managed limit copy missing`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const target = String(args.target || 'all').trim().toLowerCase();
  const baseUrl = String(args['base-url'] || '').trim();
  if (!['all', 'pro', 'free'].includes(target)) {
    throw new Error(`Unsupported target '${target}'`);
  }
  if (!baseUrl) {
    throw new Error('--base-url is required');
  }

  const summary = {
    generated_at: new Date().toISOString(),
    target,
    base_url: baseUrl,
    runs: [],
  };

  const browser = await chromium.launch({ headless: true });
  try {
    const prefixes = target === 'all' ? ['pro', 'free'] : [target];
    for (const prefix of prefixes) {
      const reports = loadScenarioReportsByPrefix(prefix);
      for (const report of reports) {
        const context = await browser.newContext({ acceptDownloads: true });
        const page = await context.newPage();
        const guards = attachPageGuards(page);
        try {
          await loginLiveUser(page, baseUrl, pickScenarioAdmin(report), 'ko');
          if (prefix === 'pro') {
            await runProScenario(page, baseUrl, report);
          } else {
            await runFreeScenario(page, baseUrl, report);
          }
          guards.assertClean(`${prefix}:${report.slug}`);
          summary.runs.push({
            scope: prefix,
            slug: report.slug,
            status: 'passed',
          });
        } catch (error) {
          summary.runs.push({
            scope: prefix,
            slug: report.slug,
            status: 'failed',
            error: String(error?.message || error),
          });
          throw error;
        } finally {
          await context.close();
        }
      }
    }
  } finally {
    await browser.close();
  }

  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${String(error?.stack || error)}\n`);
  process.exit(1);
});
