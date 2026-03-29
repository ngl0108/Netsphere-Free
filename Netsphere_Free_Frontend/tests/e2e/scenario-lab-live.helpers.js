import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { expect } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const REPORTS_ROOT = path.join(REPO_ROOT, 'scenario-lab', 'reports');
const DEFAULT_E2E_BASE_URL = process.env.E2E_BASE_URL || 'http://localhost';

export function loadScenarioReport(slug) {
  const target = path.join(REPORTS_ROOT, `${slug}.latest.json`);
  if (!fs.existsSync(target)) {
    throw new Error(`Scenario report not found: ${target}`);
  }
  return JSON.parse(fs.readFileSync(target, 'utf8').replace(/^\uFEFF/, ''));
}

export function loadScenarioReportsByPrefix(prefix) {
  if (!fs.existsSync(REPORTS_ROOT)) {
    throw new Error(`Scenario reports directory not found: ${REPORTS_ROOT}`);
  }
  return fs
    .readdirSync(REPORTS_ROOT)
    .filter((name) => name.startsWith(`${prefix}-`) && name.endsWith('.latest.json'))
    .sort()
    .map((name) => JSON.parse(fs.readFileSync(path.join(REPORTS_ROOT, name), 'utf8').replace(/^\uFEFF/, '')));
}

export function resolveScenarioReport(prefix, preferredSlug = '') {
  const reports = loadScenarioReportsByPrefix(prefix);
  if (!reports.length) {
    throw new Error(`No scenario reports found for prefix '${prefix}'.`);
  }
  const normalizedPreferred = String(preferredSlug || '').trim().toLowerCase();
  if (!normalizedPreferred) {
    return reports[0];
  }
  return (
    reports.find((report) => String(report?.slug || '').trim().toLowerCase() === normalizedPreferred) ||
    reports[0]
  );
}

export function pickScenarioAdmin(report) {
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

export function buildScenarioMatchers(report) {
  const slug = String(report?.slug || '').trim();
  const slugToken = slug.replace(/-/g, '_').toUpperCase();
  return {
    slug,
    slugToken,
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

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetriableNavigationError(error) {
  const message = String(error?.message || error || '').toLowerCase();
  return (
    message.includes('err_connection_reset') ||
    message.includes('err_connection_refused') ||
    message.includes('err_failed') ||
    message.includes('net::err_')
  );
}

export async function gotoWithRetry(page, targetUrl, options = {}, retries = 4) {
  let lastError = null;
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      await page.goto(targetUrl, options);
      return;
    } catch (error) {
      lastError = error;
      if (!isRetriableNavigationError(error) || attempt === retries) {
        throw lastError;
      }
      await delay(900 * attempt);
    }
  }
  throw lastError;
}

async function postLiveLogin(baseUrl, { username, password }) {
  const loginUrl = new URL('/api/v1/auth/login', baseUrl).toString();
  let lastError = null;
  const maxAttempts = 8;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const formData = new FormData();
      formData.set('username', username);
      formData.set('password', password);

      const response = await fetch(loginUrl, {
        method: 'POST',
        body: formData,
      });

      const text = await response.text();
      let payload = null;
      try {
        payload = text ? JSON.parse(text) : null;
      } catch (error) {
        payload = { raw: text };
      }

      const token = extractAccessToken(payload);
      if (response.ok && token) {
        return token;
      }

      lastError = new Error(`Live login failed (${response.status}) for '${username}'.`);
      if (![502, 503, 504].includes(Number(response.status)) || attempt === maxAttempts) {
        throw lastError;
      }
    } catch (error) {
      lastError = error;
      if (attempt === maxAttempts) {
        throw lastError;
      }
    }
    await delay(1200 * attempt);
  }
  throw lastError || new Error(`Live login failed for '${username}'.`);
}

async function fetchLiveMe(baseUrl, token, username) {
  const response = await fetch(new URL('/api/v1/auth/me', baseUrl).toString(), {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    return {
      username,
      role: 'viewer',
      eula_accepted: true,
      must_change_password: false,
    };
  }

  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch (error) {
    payload = null;
  }
  return unwrapEnvelope(payload) || {
    username,
    role: 'viewer',
    eula_accepted: true,
    must_change_password: false,
  };
}

async function seedAuthenticatedSessionAtBase(page, baseUrl, { username, password, locale = 'ko', landingPath = '/' }) {
  const token = await postLiveLogin(baseUrl, { username, password });
  const user = await fetchLiveMe(baseUrl, token, username);

  await page.addInitScript(
    ({ nextLocale, nextToken, nextUser, lastActiveAt }) => {
      localStorage.setItem('nm_locale', nextLocale);
      localStorage.setItem('authToken', nextToken);
      localStorage.setItem('authUser', JSON.stringify(nextUser));
      localStorage.setItem('authLastActiveAt', String(lastActiveAt));
    },
    {
      nextLocale: locale,
      nextToken: token,
      nextUser: user,
      lastActiveAt: Date.now(),
    },
  );

  await gotoWithRetry(page, new URL(landingPath, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(
    () => {
      const text = String(document.body?.innerText || '').trim();
      return window.location.pathname !== '/login' && text && text !== 'Loading...' && text !== 'Loading...\nLoading...';
    },
    null,
    { timeout: 20000 },
  );
}

export async function loginLiveUser(page, { username, password, locale = 'ko' }) {
  await seedAuthenticatedSessionAtBase(page, DEFAULT_E2E_BASE_URL, {
    username,
    password,
    locale,
  });
}

export async function loginLiveUserAtBase(page, baseUrl, { username, password, locale = 'ko' }) {
  await seedAuthenticatedSessionAtBase(page, baseUrl, {
    username,
    password,
    locale,
  });
}

export function attachPageGuards(page, { ignoredConsolePatterns = [] } = {}) {
  const pageErrors = [];
  const consoleErrors = [];

  const shouldIgnoreConsole = (text) =>
    ignoredConsolePatterns.some((pattern) =>
      pattern instanceof RegExp ? pattern.test(text) : String(text).includes(String(pattern)),
    );

  page.on('pageerror', (error) => {
    pageErrors.push(String(error?.message || error));
  });

  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = String(message.text() || '').trim();
    if (!text || shouldIgnoreConsole(text)) return;
    consoleErrors.push(text);
  });

  return {
    pageErrors,
    consoleErrors,
    reset: () => {
      pageErrors.length = 0;
      consoleErrors.length = 0;
    },
    assertClean: () => {
      expect(pageErrors, `Unexpected page errors:\n${pageErrors.join('\n')}`).toEqual([]);
      expect(consoleErrors, `Unexpected console errors:\n${consoleErrors.join('\n')}`).toEqual([]);
    },
  };
}

export async function waitForPath(page, matcher) {
  await expect
    .poll(() => page.url())
    .toMatch(matcher);
}

export async function fetchJsonWithAuth(page, targetPath, init = {}) {
  return page.evaluate(async ({ nextPath, requestInit }) => {
    const unwrapEnvelope = (payload) => {
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
    };

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
      data = text ? unwrapEnvelope(JSON.parse(text)) : null;
    } catch (error) {
      data = text;
    }
    return {
      status: response.status,
      ok: response.ok,
      data,
    };
  }, { nextPath: targetPath, requestInit: init });
}

export function unwrapCollection(payload) {
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
