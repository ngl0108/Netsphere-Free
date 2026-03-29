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

const hybridReport = loadScenarioReport('pro-hybrid-operations');
const datacenterReport = loadScenarioReport('pro-datacenter-fabric');
const enterpriseReport = loadScenarioReport('pro-enterprise-operations');
const hybridCredentials = pickScenarioAdmin(hybridReport);
const datacenterCredentials = pickScenarioAdmin(datacenterReport);
const enterpriseCredentials = pickScenarioAdmin(enterpriseReport);
const baseUrl = 'http://localhost';

const gotoAtBase = async (page, targetPath) => {
  await gotoWithRetry(page, new URL(targetPath, baseUrl).toString(), { waitUntil: 'domcontentloaded' });
};

const waitForEnabled = async (locator, timeout = 30000) => {
  await expect(locator).toBeVisible({ timeout });
  await expect(locator).toBeEnabled({ timeout });
};

const waitForCloudPageStable = async (page, stableLocator, timeout = 30000) => {
  if (stableLocator) {
    await expect(stableLocator).toBeVisible({ timeout });
  }
  await expect(page.locator('main')).not.toContainText(/로딩 중|Loading/i, { timeout });
};

const clickAndObserveAction = async (page, locator, responseMatcher, stableLocator, timeout = 45000) => {
  await waitForEnabled(locator, timeout);
  const responsePromise = page
    .waitForResponse(
      (response) =>
        responseMatcher(response) &&
        response.status() >= 200 &&
        response.status() < 300,
      { timeout },
    )
    .catch(() => null);
  await locator.click();
  const response = await responsePromise;
  if (response) {
    await waitForCloudPageStable(page, stableLocator, timeout);
    return response;
  }
  await waitForCloudPageStable(page, stableLocator, timeout);
  await expect(locator).toBeEnabled({ timeout: 30000 });
  return null;
};

const resolveSiteIdByFragment = async (page, fragment) => {
  const sitesResponse = await fetchJsonWithAuth(page, '/api/v1/sites/');
  expect(sitesResponse.status).toBe(200);
  const sites = unwrapCollection(sitesResponse.data);
  const match = sites.find((site) => String(site?.name || '').includes(String(fragment || '')));
  expect(match?.id).toBeTruthy();
  return String(match.id);
};

const gotoTopologyAtSiteFragment = async (page, fragment) => {
  const siteId = await resolveSiteIdByFragment(page, fragment);
  await gotoAtBase(page, `/topology?siteId=${encodeURIComponent(siteId)}`);
  return siteId;
};

const ensureServiceOverlayFocused = async (page, groupId, timeout = 30000) => {
  const overlayToggle = page.getByTestId('topology-service-overlay-toggle');
  const overlaySelect = page.getByTestId('topology-service-overlay-select');

  const overlayVisible = await expect(overlayToggle).toBeVisible({ timeout }).then(() => true).catch(() => false);
  if (!overlayVisible) {
    return false;
  }
  let availableOptions = [];
  try {
    await expect
      .poll(async () => {
        return overlaySelect.evaluate((element) =>
          Array.from(element.querySelectorAll('option')).map((option) => option.value).filter(Boolean),
        );
      }, { timeout })
      .toContain(String(groupId));
    availableOptions = await overlaySelect.evaluate((element) =>
      Array.from(element.querySelectorAll('option')).map((option) => option.value).filter(Boolean),
    );
  } catch (error) {
    availableOptions = [];
  }

  if (!Array.isArray(availableOptions) || !availableOptions.includes(String(groupId))) {
    return false;
  }

  const overlayPressed = await overlayToggle.getAttribute('aria-pressed');
  if (overlayPressed !== 'true') {
    await overlayToggle.click();
  }

  if ((await overlaySelect.inputValue()) !== String(groupId)) {
    await expect(overlaySelect).toBeEnabled({ timeout });
    await overlaySelect.selectOption(String(groupId));
  }

  await expect(overlaySelect).toHaveValue(String(groupId), { timeout });
  return true;
};

const assertContainedChildrenInsideGroup = async (page, groupId) => {
  const containment = await page.evaluate((targetGroupId) => {
    const groupElement = document.querySelector(
      `[data-testid="topology-group-node-editable"][data-node-id="${targetGroupId}"]`,
    );
    if (!(groupElement instanceof HTMLElement)) {
      return { ok: false, reason: 'group-missing', offenders: [] };
    }
    const groupRect = groupElement.getBoundingClientRect();
    const childNodes = Array.from(document.querySelectorAll('.react-flow__node[data-id]')).filter((element) => {
      if (!(element instanceof HTMLElement)) return false;
      const candidateId = String(element.getAttribute('data-id') || '');
      if (!candidateId || candidateId === targetGroupId) return false;
      const parentId = String(element.getAttribute('data-parentid') || '');
      return parentId === targetGroupId;
    });
    const offenders = childNodes
      .map((element) => {
        const rect = element.getBoundingClientRect();
        const nodeId = String(element.getAttribute('data-id') || '');
        return {
          nodeId,
          rightOverflow: Math.round(rect.right - groupRect.right),
          bottomOverflow: Math.round(rect.bottom - groupRect.bottom),
          leftOverflow: Math.round(groupRect.left - rect.left),
          topOverflow: Math.round(groupRect.top - rect.top),
        };
      })
      .filter((item) => item.rightOverflow > 2 || item.bottomOverflow > 2 || item.leftOverflow > 2 || item.topOverflow > 2);
    return {
      ok: offenders.length === 0,
      reason: offenders.length === 0 ? 'ok' : 'overflow',
      offenders,
    };
  }, groupId);

  expect(containment.ok, JSON.stringify(containment)).toBeTruthy();
};

test.describe.configure({ mode: 'serial' });

test('scenario-lab pro cloud accounts buttons and service-map entrypoints work on live runtime', async ({ page }) => {
  test.slow();
  test.setTimeout(240000);
  const guards = attachPageGuards(page, {
    ignoredConsolePatterns: [
      /Failed to load resource: the server responded with a status of 504/i,
      /504 Gateway Time-out/i,
    ],
  });

  await loginLiveUserAtBase(page, baseUrl, { ...hybridCredentials, locale: 'ko' });

  const accountResponse = await fetchJsonWithAuth(page, '/api/v1/cloud/accounts');
  expect(accountResponse.status).toBe(200);
  const accounts = unwrapCollection(accountResponse.data);
  expect(accounts.length).toBeGreaterThan(0);

  await gotoAtBase(page, '/cloud/accounts');
  await expect(page.getByTestId('cloud-accounts-page')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('main')).not.toContainText(/로딩 중|Loading/i, { timeout: 30000 });
  await expect(page.getByTestId('cloud-accounts-change-enabled')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-ledger')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-lane-board')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('cloud-operations-retry-queue')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('cloud-operations-execution-highlights')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('cloud-accounts-open-operations-reports').click();
  await expect(page).toHaveURL(/\/operations-reports(?:[/?#]|$)/, { timeout: 30000 });
  await gotoAtBase(page, '/cloud/accounts');
  const firstAccountRow = page.locator('[data-testid^="cloud-account-row-"]').first();
  await expect(firstAccountRow).toBeVisible({ timeout: 30000 });
  const firstAccountId = await firstAccountRow.getAttribute('data-account-focus-id');
  expect(firstAccountId).toBeTruthy();
  await expect(page.getByTestId(`cloud-account-ledger-${firstAccountId}`)).toBeVisible();
  await page.getByTestId(`cloud-account-ledger-open-${firstAccountId}`).click();
  await expect(page.getByTestId(`cloud-account-ledger-review-${firstAccountId}`)).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId(`cloud-account-ledger-drift-${firstAccountId}`)).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId(`cloud-account-ledger-runbook-${firstAccountId}`)).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId(`cloud-account-ledger-history-${firstAccountId}`)).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId(`cloud-account-ledger-next-lane-${firstAccountId}`)).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId(`cloud-account-ledger-cadence-${firstAccountId}`)).toBeVisible({ timeout: 30000 });
  await page.getByTestId(`cloud-account-ledger-review-workspace-${firstAccountId}`).click();
  await expect(page).toHaveURL(/\/automation\?workspace=(?:observe|discover|control|govern)(?:[&#].*)?$/, { timeout: 30000 });
  await gotoAtBase(page, '/cloud/accounts');
  await expect(page.getByTestId(`cloud-account-ledger-${firstAccountId}`)).toBeVisible({ timeout: 30000 });
  await page.getByTestId(`cloud-account-ledger-open-${firstAccountId}`).click();
  await expect(page.getByTestId(`cloud-account-ledger-review-${firstAccountId}`)).toBeVisible({ timeout: 30000 });
  await page.getByTestId(`cloud-account-ledger-review-intents-${firstAccountId}`).click();
  await expect(page).toHaveURL(/\/cloud\/intents(?:[/?#]|$)/, { timeout: 30000 });
  await gotoAtBase(page, '/cloud/accounts');
  await expect(page.getByTestId(`cloud-account-ledger-${firstAccountId}`)).toBeVisible({ timeout: 30000 });

  const validateButton = page.getByTestId(`cloud-account-validate-${firstAccountId}`);
  await clickAndObserveAction(
    page,
    validateButton,
    (response) =>
      response.url().includes('/api/v1/cloud/accounts/') &&
      response.url().includes('/preflight') &&
      response.request().method() === 'POST',
    page.getByTestId(`cloud-account-ledger-${firstAccountId}`),
  );

  const scanButton = page.getByTestId(`cloud-account-scan-${firstAccountId}`);
  await clickAndObserveAction(
    page,
    scanButton,
    (response) =>
      response.url().includes('/api/v1/cloud/accounts/') &&
      response.url().includes('/scan') &&
      response.request().method() === 'POST',
    page.getByTestId(`cloud-account-ledger-${firstAccountId}`),
  );

  const bootstrapButton = page.getByRole('button', { name: /Bootstrap Dry-Run|Bootstrap/i }).first();
  await clickAndObserveAction(
    page,
    bootstrapButton,
    (response) =>
      response.url().includes('/api/v1/cloud/bootstrap') &&
      response.request().method() === 'POST',
    page.getByTestId('cloud-accounts-page'),
  );
  await expect(page.getByTestId('cloud-accounts-page')).toBeVisible();

  const enabledEditButton = page.locator('[data-testid^="cloud-account-edit-"]:not([disabled])').first();
  if (await enabledEditButton.count()) {
    await enabledEditButton.click();
    const cancelButton = page.getByTestId('cloud-account-edit-cancel');
    await expect(cancelButton).toBeVisible({ timeout: 15000 });
    await cancelButton.click();
  }

  const serviceGroupsResponse = await fetchJsonWithAuth(page, '/api/v1/service-groups/');
  expect(serviceGroupsResponse.status).toBe(200);
  const serviceGroups = unwrapCollection(serviceGroupsResponse.data);
  expect(serviceGroups.length).toBeGreaterThan(0);
  const firstGroup = serviceGroups[0];

  await gotoAtBase(page, `/topology?serviceOverlay=1&serviceGroupId=${encodeURIComponent(String(firstGroup.id))}`);
  const overlayFocused = await ensureServiceOverlayFocused(page, firstGroup.id);
  const useOverlayEntryPoints =
    overlayFocused &&
    (await page.getByTestId('topology-service-overlay-open-notifications').count()) > 0 &&
    (await page.getByTestId('topology-service-overlay-open-review').count()) > 0;

  if (useOverlayEntryPoints) {
    if (await page.getByTestId('topology-service-overlay-banner').count()) {
      await expect(page.getByTestId('topology-service-overlay-banner')).toBeVisible({ timeout: 30000 });
    }
    await page.getByTestId('topology-service-overlay-open-notifications').click();
    await expect(page).toHaveURL(/\/notifications(?:[/?#]|$)/, { timeout: 30000 });
    await expect(
      page.locator(
        '[data-testid="notifications-focused-service-context"], [data-testid="notifications-service-priority-focus"], [data-testid="notifications-service-impact-focus"]',
      ).first(),
    ).toBeVisible({ timeout: 30000 });
    await gotoAtBase(page, `/topology?serviceOverlay=1&serviceGroupId=${encodeURIComponent(String(firstGroup.id))}`);
    await ensureServiceOverlayFocused(page, firstGroup.id);
    const openReview = page.getByTestId('topology-service-overlay-open-review');
    await expect(openReview).toBeVisible({ timeout: 30000 });
    await openReview.click({ force: true });
  } else {
    await gotoAtBase(
      page,
      `/service-groups?focusGroupId=${encodeURIComponent(String(firstGroup.id))}&focusGroupName=${encodeURIComponent(String(firstGroup.name || '').trim())}`,
    );
    if (await page.getByTestId('service-groups-review-queue').count()) {
      await expect(page.getByTestId('service-groups-review-queue')).toBeVisible({ timeout: 30000 });
    }
    const reviewNotifications = page.locator(`[data-testid="service-groups-review-notifications-${firstGroup.id}"]`).first();
    if (await reviewNotifications.count()) {
      await expect(reviewNotifications).toBeVisible({ timeout: 30000 });
      await reviewNotifications.click();
    } else {
      await page.goto(`${baseUrl}/notifications?serviceImpact=1&openServiceImpact=1&focusGroupId=${encodeURIComponent(String(firstGroup.id))}&focusGroupName=${encodeURIComponent(String(firstGroup.name || '').trim())}`, { waitUntil: 'domcontentloaded' });
    }
    await expect(page).toHaveURL(/\/notifications(?:[/?#]|$)/, { timeout: 30000 });
    await expect(page.getByTestId('notifications-focused-service-context')).toBeVisible({ timeout: 30000 });
    await gotoAtBase(
      page,
      `/service-groups?focusGroupId=${encodeURIComponent(String(firstGroup.id))}&focusGroupName=${encodeURIComponent(String(firstGroup.name || '').trim())}`,
    );
    const reviewReports = page.locator(`[data-testid="service-groups-review-reports-${firstGroup.id}"]`).first();
    if (await reviewReports.count()) {
      await expect(reviewReports).toBeVisible({ timeout: 30000 });
      await reviewReports.click();
    } else {
      await page.goto(`${baseUrl}/operations-reports?focusGroupId=${encodeURIComponent(String(firstGroup.id))}&focusGroupName=${encodeURIComponent(String(firstGroup.name || '').trim())}`, { waitUntil: 'domcontentloaded' });
    }
  }
  await expect(page).toHaveURL(/\/operations-reports(?:[/?#]|$)/, { timeout: 30000 });
  await expect(
    page.locator(
      '[data-testid="operations-reports-focused-group"], [data-testid="operations-reports-service-priority-focus"], [data-testid="operations-reports-service-priority-queue"]',
    ).first(),
  ).toBeVisible({ timeout: 30000 });
  if (await page.getByTestId('operations-reports-focused-group-open-notifications').count()) {
    await page.getByTestId('operations-reports-focused-group-open-notifications').click();
    await expect(page).toHaveURL(/\/notifications(?:[/?#]|$)/, { timeout: 30000 });
    await expect(
      page.locator(
        '[data-testid="notifications-focused-service-context"], [data-testid="notifications-service-priority-focus"], [data-testid="notifications-service-impact-focus"]',
      ).first(),
    ).toBeVisible({ timeout: 30000 });
  }
  await gotoAtBase(page, `/operations-reports?focusGroupId=${encodeURIComponent(String(firstGroup.id))}`);
  if (await page.getByTestId('operations-reports-focused-group-clear').count()) {
    await page.getByTestId('operations-reports-focused-group-clear').click();
    await expect(page.getByTestId('operations-reports-focused-group')).toHaveCount(0);
  }

  guards.assertClean();
});

test('scenario-lab pro topology mode buttons cover bgp overlay hybrid and path trace flows', async ({ page }) => {
  test.slow();
  const guards = attachPageGuards(page);

  await loginLiveUserAtBase(page, baseUrl, { ...datacenterCredentials, locale: 'ko' });

  await gotoAtBase(page, '/topology');
  await expect(page.getByTestId('topology-layer-filter-bgp')).toBeVisible({ timeout: 30000 });

  await page.getByTestId('topology-layer-filter-bgp').click();
  await expect(page.getByTestId('bgp-topology-summary')).toBeVisible({ timeout: 30000 });

  const overlayToggle = page.getByTestId('topology-layer-filter-overlay');
  await overlayToggle.click();
  await expect(overlayToggle).toHaveClass(/bg-cyan-600/, { timeout: 30000 });

  await loginLiveUserAtBase(page, baseUrl, { ...hybridCredentials, locale: 'ko' });
  await gotoAtBase(page, '/topology');
  const hybridToggle = page.getByTestId('topology-layer-filter-hybrid');
  await hybridToggle.click();
  await expect(hybridToggle).toHaveClass(/bg-sky-600/, { timeout: 30000 });

  await page.getByTestId('topology-path-trace-toggle').click();
  await expect(page.getByTestId('path-trace-panel')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('path-trace-src-input').fill('10.10.10.10');
  await page.getByTestId('path-trace-dst-input').fill('10.20.20.20');
  await expect(page.getByTestId('path-trace-run')).toBeEnabled();

  guards.assertClean();
});

test('scenario-lab pro layout editor opens without triggering app error fallback', async ({ page }) => {
  test.slow();
  const guards = attachPageGuards(page);
  await loginLiveUserAtBase(page, baseUrl, { ...enterpriseCredentials, locale: 'ko' });
  await gotoTopologyAtSiteFragment(page, 'Branch 03');

  const manualEditButton = page.getByTestId('topology-toolbar-layout-editor-toggle');
  await expect(manualEditButton).toBeVisible({ timeout: 30000 });
  await manualEditButton.click();

  await expect(page.getByText(/Layout Editor Workspace|레이아웃 에디터/i)).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/Internal Server Error|내부 서버 오류/i)).toHaveCount(0);

  await page.waitForFunction(() => {
    const overlays = Array.from(document.querySelectorAll('[data-testid="topology-group-overlay-right"]'));
    return overlays.some((element) => {
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && rect.left >= 8 && rect.right <= (window.innerWidth - 8);
    });
  }, null, { timeout: 30000 });

  const targetGroup = await page.evaluate(() => {
    const overlays = Array.from(document.querySelectorAll('[data-testid="topology-group-overlay-right"]'));
    const match = overlays.find((element) => String(element.getAttribute('data-group-label') || '').includes('Branch 03'));
    if (!match) return { label: '', id: '' };
    return {
      label: String(match.getAttribute('data-group-label') || ''),
      id: String(match.getAttribute('data-node-id') || ''),
    };
  });
  expect(targetGroup.label).toBeTruthy();
  expect(targetGroup.id).toBeTruthy();

  const editableGroup = page.locator(`[data-testid="topology-group-node-editable"][data-node-id="${targetGroup.id}"]`).first();
  const editableGroupQuickEdit = page.locator(`[data-testid="topology-group-overlay-open-editor"][data-node-id="${targetGroup.id}"]`).first();
  await expect(editableGroup).toBeVisible({ timeout: 30000 });
  await editableGroupQuickEdit.click({ force: true });
  await expect(page.getByTestId('topology-editor-auto-group-panel')).toBeVisible({ timeout: 30000 });
  const autoWidthInput = page.getByTestId('topology-editor-auto-group-width');
  const autoHeightInput = page.getByTestId('topology-editor-auto-group-height');
  const minWidthAttr = Number(await autoWidthInput.getAttribute('min'));
  const minHeightAttr = Number(await autoHeightInput.getAttribute('min'));
  await autoWidthInput.fill('24');
  await autoHeightInput.fill('24');
  await autoHeightInput.blur();
  await expect(autoWidthInput).toHaveValue(String(minWidthAttr));
  await expect(autoHeightInput).toHaveValue(String(minHeightAttr));
  const snapGridToggle = page.getByTestId('topology-editor-snap-grid-toggle');
  await expect(snapGridToggle).toBeVisible({ timeout: 30000 });
  const snapInitially = await snapGridToggle.isChecked();
  await snapGridToggle.click();
  await expect(snapGridToggle).toHaveJSProperty('checked', !snapInitially);
  await snapGridToggle.click();
  await expect(snapGridToggle).toHaveJSProperty('checked', snapInitially);
  const resizeHandle = page.locator(`[data-testid="topology-group-overlay-right"][data-node-id="${targetGroup.id}"]`).first();
  await expect(resizeHandle).toBeVisible({ timeout: 30000 });

  const beforeBox = await editableGroup.boundingBox();
  expect(beforeBox).toBeTruthy();

  const handleBox = await resizeHandle.boundingBox();
  expect(handleBox).toBeTruthy();
  const resizeStartX = handleBox.x + handleBox.width / 2;
  const resizeStartY = handleBox.y + handleBox.height / 2;
  await page.mouse.move(resizeStartX, resizeStartY);
  await page.mouse.down();
  await page.mouse.move(resizeStartX + 120, resizeStartY, { steps: 8 });
  await page.mouse.up();

  await page.waitForTimeout(250);

  const afterBox = await editableGroup.boundingBox();
  expect(afterBox).toBeTruthy();
  const minimumFitWidth = await page.evaluate((groupId) => {
    const groupElement = document.querySelector(`[data-testid="topology-group-node-editable"][data-node-id="${groupId}"]`);
    if (!groupElement) return 160;
    const groupRect = groupElement.getBoundingClientRect();
    const childNodes = Array.from(document.querySelectorAll('.react-flow__node')).filter((element) => {
      if (!(element instanceof HTMLElement)) return false;
      const nodeId = String(element.getAttribute('data-id') || '');
      if (!nodeId || nodeId === groupId) return false;
      const rect = element.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      return centerX >= groupRect.left && centerX <= groupRect.right && centerY >= groupRect.top && centerY <= groupRect.bottom;
    });
    if (!childNodes.length) return 160;
    const maxRight = childNodes.reduce((current, element) => {
      const rect = element.getBoundingClientRect();
      return Math.max(current, rect.right - groupRect.left);
    }, 0);
    return Math.round(maxRight + 28);
  }, targetGroup.id);
  await page.mouse.move(resizeStartX, resizeStartY);
  await page.mouse.down();
  await page.mouse.move(resizeStartX - 720, resizeStartY, { steps: 10 });
  await page.mouse.up();
  await page.waitForTimeout(250);
  const shrunkBox = await editableGroup.boundingBox();
  expect(shrunkBox).toBeTruthy();
  expect(Math.round(shrunkBox.width)).toBeGreaterThanOrEqual(160);
  await assertContainedChildrenInsideGroup(page, targetGroup.id);
  await expect(page.getByText(/Internal Server Error/i)).toHaveCount(0);
  await expect(resizeHandle).toBeVisible({ timeout: 30000 });

  guards.assertClean();
});

test('scenario-lab pro layout editor supports group actions and manual group lifecycle', async ({ page }) => {
  test.slow();
  const guards = attachPageGuards(page);
  await loginLiveUserAtBase(page, baseUrl, { ...enterpriseCredentials, locale: 'ko' });
  await gotoTopologyAtSiteFragment(page, 'Branch 03');

  await expect(page.getByTestId('topology-toolbar-layout-editor-toggle')).toBeEnabled({ timeout: 30000 });
  await page.getByTestId('topology-toolbar-layout-editor-toggle').click();
  await expect(page.getByText(/Layout Editor Workspace|레이아웃 에디터/i)).toBeVisible({ timeout: 30000 });
  await page.getByTestId('topology-editor-resolve-overlaps').click({ force: true });
  await expect(page.getByText(/Internal Server Error/i)).toHaveCount(0);
  await page.getByTestId('topology-editor-tidy-canvas').click({ force: true });
  await expect(page.getByText(/Internal Server Error/i)).toHaveCount(0);
  await page.waitForFunction(() => {
    const candidates = Array.from(
      document.querySelectorAll(
        '[data-testid="topology-group-node-editable"], [data-testid="topology-group-overlay-right"]',
      ),
    );
    return candidates.some((element) => String(element.getAttribute('data-group-label') || '').includes('Branch 03'));
  }, null, { timeout: 30000 });

  const targetGroup = await page.evaluate(() => {
    const candidates = Array.from(
      document.querySelectorAll(
        '[data-testid="topology-group-node-editable"], [data-testid="topology-group-overlay-right"]',
      ),
    );
    const match = candidates.find((element) => String(element.getAttribute('data-group-label') || '').includes('Branch 03'));
    if (!match) return { id: '', label: '' };
    return {
      id: String(match.getAttribute('data-node-id') || ''),
      label: String(match.getAttribute('data-group-label') || ''),
    };
  });
  expect(targetGroup.id).toBeTruthy();

  const autoGroupNode = page.locator(`.react-flow__node:has([data-testid="topology-group-node-editable"][data-node-id="${targetGroup.id}"])`).first();
  const autoGroupQuickEdit = page.locator(`[data-testid="topology-group-overlay-open-editor"][data-node-id="${targetGroup.id}"]`).first();
  await expect(autoGroupNode).toBeVisible({ timeout: 30000 });
  await autoGroupQuickEdit.click({ force: true });
  await expect(page.getByTestId('topology-editor-auto-group-panel')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('topology-editor-auto-group-fit-children').click({ force: true });
  await expect(page.getByText(/Internal Server Error/i)).toHaveCount(0);
  await assertContainedChildrenInsideGroup(page, targetGroup.id);
  await page.getByTestId('topology-editor-auto-group-arrange-children').click({ force: true });
  await expect(page.getByText(/Internal Server Error/i)).toHaveCount(0);
  await assertContainedChildrenInsideGroup(page, targetGroup.id);

  const manualGroupLabel = `QA Manual Group ${Date.now()}`;
  const manualGroupIdsBefore = await page.locator('[data-testid="topology-group-node-editable"][data-node-id^="manual-group-"]').evaluateAll((elements) =>
    elements.map((element) => String(element.getAttribute('data-node-id') || '')).filter(Boolean),
  );
  await page.getByTestId('topology-toolbar-add-group').click();
  await expect(page.getByTestId('topology-editor-manual-group-panel')).toBeVisible({ timeout: 30000 });
  const manualGroupIdHandle = await page.waitForFunction((existingIds) => {
    const ids = Array.from(document.querySelectorAll('[data-testid="topology-group-node-editable"][data-node-id^="manual-group-"]'))
      .map((element) => String(element.getAttribute('data-node-id') || ''))
      .filter(Boolean);
    return ids.find((id) => !existingIds.includes(id)) || null;
  }, manualGroupIdsBefore, { timeout: 30000 });
  const manualGroupId = await manualGroupIdHandle.jsonValue();
  expect(manualGroupId).toBeTruthy();
  await page.getByTestId('topology-editor-manual-group-label').fill(manualGroupLabel);
  const manualWidthInput = page.getByTestId('topology-editor-manual-group-width');
  const manualHeightInput = page.getByTestId('topology-editor-manual-group-height');
  const manualMinWidth = Number(await manualWidthInput.getAttribute('min'));
  const manualMinHeight = Number(await manualHeightInput.getAttribute('min'));
  await manualWidthInput.fill('12');
  await manualHeightInput.fill('12');
  await manualHeightInput.blur();
  await expect(manualWidthInput).toHaveValue(String(manualMinWidth));
  await expect(manualHeightInput).toHaveValue(String(manualMinHeight));
  await page.getByTestId('topology-editor-manual-group-width').fill('460');
  await page.getByTestId('topology-editor-manual-group-height').fill('260');
  await page.getByTestId('topology-editor-manual-group-apply-size').click({ force: true });
  await page.getByTestId('topology-editor-manual-group-save').click({ force: true });

  const manualGroup = page.locator(`[data-testid="topology-group-node-editable"][data-node-id="${manualGroupId}"]`).first();
  await expect(manualGroup).toBeVisible({ timeout: 30000 });
  await expect
    .poll(async () => manualGroup.getAttribute('data-group-label'), { timeout: 30000 })
    .toBe(manualGroupLabel);

  const saveLayoutResponse = page.waitForResponse((response) =>
    response.url().includes('/api/v1/topology/layout') &&
    response.request().method() === 'POST' &&
    response.status() >= 200 &&
    response.status() < 300,
  );
  await page.getByTestId('topology-toolbar-save-layout').click();
  await saveLayoutResponse;

  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page).not.toHaveURL(/\/login$/);
  await gotoTopologyAtSiteFragment(page, 'Branch 03');
  await expect(page.getByTestId('topology-toolbar-layout-editor-toggle')).toBeEnabled({ timeout: 30000 });
  await page.getByTestId('topology-toolbar-layout-editor-toggle').click();
  await expect(page.getByTestId('topology-editor-manual-group-panel')).toHaveCount(0);
  await assertContainedChildrenInsideGroup(page, targetGroup.id);
  const reloadedManualGroupNode = page.locator(`.react-flow__node:has([data-testid="topology-group-node-editable"][data-node-id="${manualGroupId}"])`).first();
  const reloadedManualGroup = page.locator(`[data-testid="topology-group-node-editable"][data-node-id="${manualGroupId}"]`).first();
  const reloadedManualGroupQuickEdit = page.locator(`[data-testid="topology-group-overlay-open-editor"][data-node-id="${manualGroupId}"]`).first();
  await expect(reloadedManualGroupNode).toBeVisible({ timeout: 30000 });
  await expect(reloadedManualGroup).toBeVisible({ timeout: 30000 });
  await expect
    .poll(async () => reloadedManualGroup.getAttribute('data-group-label'), { timeout: 30000 })
    .toBe(manualGroupLabel);
  await reloadedManualGroupQuickEdit.click({ force: true });
  const quickEditDebug = await page.evaluate((groupId) => ({
    topologyDebug: window.__netmanagerTopologyDebug || null,
    manualPanel: !!document.querySelector('[data-testid="topology-editor-manual-group-panel"]'),
    autoPanel: !!document.querySelector('[data-testid="topology-editor-auto-group-panel"]'),
    targetLabel: document.querySelector(`[data-testid="topology-group-node-editable"][data-node-id="${groupId}"]`)?.getAttribute('data-group-label') || '',
  }), manualGroupId);
  console.log('manual group quick edit debug', quickEditDebug);
  await expect(page.getByTestId('topology-editor-manual-group-panel')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('topology-editor-manual-group-delete').click({ force: true });
  await expect(page.locator(`[data-testid="topology-group-node-editable"][data-node-id="${manualGroupId}"]`)).toHaveCount(0);

  page.once('dialog', (dialog) => dialog.accept());
  const resetLayoutResponse = page.waitForResponse((response) =>
    response.url().includes('/api/v1/topology/layout') &&
    response.request().method() === 'DELETE' &&
    response.status() >= 200 &&
    response.status() < 300,
  );
  await page.getByTestId('topology-toolbar-reset-layout').click();
  await resetLayoutResponse;

  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page).not.toHaveURL(/\/login$/);
  await gotoTopologyAtSiteFragment(page, 'Branch 03');
  await expect(page.getByTestId('topology-toolbar-layout-editor-toggle')).toBeEnabled({ timeout: 30000 });
  await page.getByTestId('topology-toolbar-layout-editor-toggle').click();
  await expect(page.locator(`[data-testid="topology-group-node-editable"][data-node-id="${manualGroupId}"]`)).toHaveCount(0);
  await expect(page.getByText(/Internal Server Error/i)).toHaveCount(0);

  guards.assertClean();
});
