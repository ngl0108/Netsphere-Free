import { test, expect } from '@playwright/test';
import {
  attachPageGuards,
  fetchJsonWithAuth,
  gotoWithRetry,
  loadScenarioReport,
  loginLiveUserAtBase,
  pickScenarioAdmin,
  unwrapCollection,
} from './scenario-lab-live.helpers';

const report = loadScenarioReport('pro-enterprise-operations');
const credentials = pickScenarioAdmin(report);
const baseUrl = 'http://localhost';

const resolveSiteIdByFragment = async (page, fragment) => {
  const sitesResponse = await fetchJsonWithAuth(page, '/api/v1/sites/');
  expect(sitesResponse.status).toBe(200);
  const sites = unwrapCollection(sitesResponse.data);
  const match = sites.find((site) => String(site?.name || '').includes(String(fragment || '')));
  expect(match?.id).toBeTruthy();
  return String(match.id);
};

test('debug topology editor actions around Branch 03', async ({ page }) => {
  test.slow();
  const guards = attachPageGuards(page);

  await loginLiveUserAtBase(page, baseUrl, { ...credentials, locale: 'ko' });
  const siteId = await resolveSiteIdByFragment(page, 'Branch 03');
  await gotoWithRetry(page, new URL(`/topology?siteId=${encodeURIComponent(siteId)}`, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);

  await page.waitForTimeout(2500);
  console.log('before layout editor click', {
    pageErrors: guards.pageErrors,
    consoleErrors: guards.consoleErrors,
    bodyText: await page.locator('body').innerText(),
  });
  await page.getByTestId('topology-toolbar-layout-editor-toggle').click({ force: true });
  await page.waitForTimeout(1500);
  console.log('after layout editor click', {
    pageErrors: guards.pageErrors,
    consoleErrors: guards.consoleErrors,
    bodyText: await page.locator('body').innerText(),
  });
  await expect(page.getByText(/Layout Editor Workspace|레이아웃 에디터/i)).toBeVisible({ timeout: 30000 });

  await page.getByTestId('topology-editor-resolve-overlaps').click({ force: true });
  await page.waitForTimeout(1000);
  console.log('after resolve', { pageErrors: guards.pageErrors, consoleErrors: guards.consoleErrors });

  await page.getByTestId('topology-editor-tidy-canvas').click({ force: true });
  await page.waitForTimeout(2000);
  console.log('after tidy', { pageErrors: guards.pageErrors, consoleErrors: guards.consoleErrors });

  await expect(page.getByText(/Internal Server Error|내부 서버 오류/i)).toHaveCount(0);
});

test('debug manual group reselection after reload', async ({ page }) => {
  test.slow();

  await loginLiveUserAtBase(page, baseUrl, { ...credentials, locale: 'ko' });
  const siteId = await resolveSiteIdByFragment(page, 'Branch 03');
  await gotoWithRetry(page, new URL(`/topology?siteId=${encodeURIComponent(siteId)}`, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);
  await expect(page.getByTestId('topology-toolbar-layout-editor-toggle')).toBeEnabled({ timeout: 30000 });
  await page.getByTestId('topology-toolbar-layout-editor-toggle').click({ force: true });

  const manualGroupLabel = `QA Manual Group ${Date.now()}`;
  await page.getByTestId('topology-toolbar-add-group').click();
  await expect(page.getByTestId('topology-editor-manual-group-panel')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('topology-editor-manual-group-label').fill(manualGroupLabel);
  await page.getByTestId('topology-editor-manual-group-save').click({ force: true });

  const manualGroup = page.locator('[data-testid="topology-group-node-editable"][data-node-id^="manual-group-"]').last();
  await expect(manualGroup).toBeVisible({ timeout: 30000 });
  const manualGroupId = await manualGroup.getAttribute('data-node-id');

  const saveLayoutResponse = page.waitForResponse((response) =>
    response.url().includes('/api/v1/topology/layout') &&
    response.request().method() === 'POST' &&
    response.status() >= 200 &&
    response.status() < 300,
  );
  await page.getByTestId('topology-toolbar-save-layout').click();
  await saveLayoutResponse;

  await page.reload({ waitUntil: 'domcontentloaded' });
  await gotoWithRetry(page, new URL(`/topology?siteId=${encodeURIComponent(siteId)}`, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);
  await expect(page.getByTestId('topology-toolbar-layout-editor-toggle')).toBeEnabled({ timeout: 30000 });
  await page.getByTestId('topology-toolbar-layout-editor-toggle').click({ force: true });

  const reloadedManualGroup = page.locator(`[data-testid="topology-group-node-editable"][data-node-id="${manualGroupId}"]`).first();
  await expect(reloadedManualGroup).toBeVisible({ timeout: 30000 });

  const before = await reloadedManualGroup.evaluate((node) => {
    const wrapper = node.closest('.react-flow__node');
    return {
      nodeId: node.getAttribute('data-node-id'),
      label: node.getAttribute('data-group-label'),
      wrapperClasses: wrapper?.className || '',
      wrapperPointerEvents: wrapper instanceof HTMLElement ? getComputedStyle(wrapper).pointerEvents : '',
      surfacePointerEvents: node instanceof HTMLElement ? getComputedStyle(node).pointerEvents : '',
      panelExists: !!document.querySelector('[data-testid="topology-editor-manual-group-panel"]'),
    };
  });
  console.log('manual group before click', before);

  await reloadedManualGroup.click({ force: true });
  await page.waitForTimeout(1000);

  const after = await reloadedManualGroup.evaluate((node) => {
    const wrapper = node.closest('.react-flow__node');
    return {
      wrapperClasses: wrapper?.className || '',
      ariaSelected: wrapper?.getAttribute('aria-selected') || '',
      panelExists: !!document.querySelector('[data-testid="topology-editor-manual-group-panel"]'),
      autoPanelExists: !!document.querySelector('[data-testid="topology-editor-auto-group-panel"]'),
    };
  });
  console.log('manual group after click', after);

  await page.evaluate((groupId) => {
    window.dispatchEvent(new CustomEvent('netmanager:topology-group-focus', {
      detail: { id: groupId },
    }));
  }, manualGroupId);
  await page.waitForTimeout(500);

  const afterManualDispatch = await reloadedManualGroup.evaluate((node) => {
    const wrapper = node.closest('.react-flow__node');
    return {
      wrapperClasses: wrapper?.className || '',
      ariaSelected: wrapper?.getAttribute('aria-selected') || '',
      panelExists: !!document.querySelector('[data-testid="topology-editor-manual-group-panel"]'),
      autoPanelExists: !!document.querySelector('[data-testid="topology-editor-auto-group-panel"]'),
    };
  });
  console.log('manual group after manual dispatch', afterManualDispatch);
});

test('debug manual group quick edit after reload', async ({ page }) => {
  test.slow();

  await loginLiveUserAtBase(page, baseUrl, { ...credentials, locale: 'ko' });
  const siteId = await resolveSiteIdByFragment(page, 'Branch 03');
  await gotoWithRetry(page, new URL(`/topology?siteId=${encodeURIComponent(siteId)}`, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);
  await page.getByTestId('topology-toolbar-layout-editor-toggle').click({ force: true });

  const manualGroupLabel = `QA Manual Group ${Date.now()}`;
  await page.getByTestId('topology-toolbar-add-group').click();
  await expect(page.getByTestId('topology-editor-manual-group-panel')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('topology-editor-manual-group-label').fill(manualGroupLabel);
  await page.getByTestId('topology-editor-manual-group-save').click({ force: true });

  const manualGroup = page.locator('[data-testid="topology-group-node-editable"][data-node-id^="manual-group-"]').last();
  await expect(manualGroup).toBeVisible({ timeout: 30000 });
  const manualGroupId = await manualGroup.getAttribute('data-node-id');

  const saveLayoutResponse = page.waitForResponse((response) =>
    response.url().includes('/api/v1/topology/layout') &&
    response.request().method() === 'POST' &&
    response.status() >= 200 &&
    response.status() < 300,
  );
  await page.getByTestId('topology-toolbar-save-layout').click();
  await saveLayoutResponse;

  await page.reload({ waitUntil: 'domcontentloaded' });
  await gotoWithRetry(page, new URL(`/topology?siteId=${encodeURIComponent(siteId)}`, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);
  await page.getByTestId('topology-toolbar-layout-editor-toggle').click({ force: true });

  const quickEdit = page.locator(`[data-testid="topology-group-open-editor"][data-node-id="${manualGroupId}"]`).first();
  await expect(quickEdit).toBeVisible({ timeout: 30000 });
  await quickEdit.click({ force: true });
  await page.waitForTimeout(1000);

  const snapshot = await page.evaluate((groupId) => {
    const button = document.querySelector(`[data-testid="topology-group-open-editor"][data-node-id="${groupId}"]`);
    const wrapper = document.querySelector(`.react-flow__node[data-id="${groupId}"]`);
    const panel = document.querySelector('[data-testid="topology-editor-manual-group-panel"]');
    const autoPanel = document.querySelector('[data-testid="topology-editor-auto-group-panel"]');
    const root = document.querySelector(`[data-testid="topology-group-node-editable"][data-node-id="${groupId}"]`);
    return {
      buttonExists: !!button,
      wrapperExists: !!wrapper,
      wrapperAriaSelected: wrapper?.getAttribute('aria-selected') || '',
      rootLabel: root?.getAttribute('data-group-label') || '',
      panelExists: !!panel,
      autoPanelExists: !!autoPanel,
      bodyText: document.body.innerText,
    };
  }, manualGroupId);
  console.log('manual group after quick edit', snapshot);
});
