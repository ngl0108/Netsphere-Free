import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';
import { gotoWithRetry } from './scenario-lab-live.helpers';

const templates = [
  {
    id: 11,
    name: 'Core Interface Template',
    category: 'Switching',
    content: 'hostname {{ device.name }}',
    tags: 'v1,vendor:cisco',
  },
];

const devices = [
  { id: 101, name: 'edge-1', ip_address: '10.10.10.1', status: 'online' },
  { id: 102, name: 'edge-2', ip_address: '10.10.10.2', status: 'online' },
];

async function mockConfigPageCore(page, settings = {}) {
  await seedAuth(page);
  await mockCoreApis(page, { settings: { change_policy_template_direct_max_devices: '3', ...settings } });

  await page.route('**/api/v1/templates/', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(templates) });
  });

  await page.route('**/api/v1/devices/', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(devices) });
  });
}

test('config page shows change plan, dry-run guards, and deploy rollback metadata', async ({ page }) => {
  await mockConfigPageCore(page);

  let deployPayload = null;

  await page.route('**/api/v1/templates/11/dry-run', async (route) => {
    const body = route.request().postDataJSON();
    expect(body.rollback_on_failure).toBe(true);
    expect(body.wave_size).toBe(2);

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        summary: [
          {
            device_id: 101,
            device_name: 'edge-1',
            ip_address: '10.10.10.1',
            status: 'ok',
            support_policy: {
              tier: 'full',
              readiness: 'ready',
              rollback_strategy: { label: 'checkpoint' },
            },
            pre_check_commands: ['show version'],
            post_check_commands: ['show clock'],
            change_guard: {
              deploy_allowed: true,
              rollback_supported: true,
              blocked_reasons: [],
            },
            diff_summary: {
              added_lines: 2,
              removed_lines: 1,
              changed_lines_estimate: 3,
              preview: ['+ hostname edge-1', '+ interface Loopback0', '- hostname old-edge-1'],
            },
            diff_lines: ['+ hostname edge-1'],
          },
          {
            device_id: 102,
            device_name: 'edge-2',
            ip_address: '10.10.10.2',
            status: 'ok',
            support_policy: {
              tier: 'full',
              readiness: 'ready',
              rollback_strategy: { label: 'checkpoint' },
            },
            pre_check_commands: ['show version'],
            post_check_commands: ['show clock'],
            change_guard: {
              deploy_allowed: true,
              rollback_supported: true,
              blocked_reasons: [],
            },
            diff_summary: {
              added_lines: 1,
              removed_lines: 0,
              changed_lines_estimate: 1,
              preview: ['+ hostname edge-2'],
            },
            diff_lines: ['+ hostname edge-2'],
          },
        ],
        totals: { total: 2, ok: 2, missing_variables: 0 },
        change_plan: {
          route: 'direct',
          reason: 'Target count (2) is within the direct deployment threshold (3).',
          target_count: 2,
          direct_max_devices: 3,
          rollback_on_failure: true,
          approval_bound: false,
          blocked_config_devices: [],
          blocked_rollback_devices: [],
          rollout: {
            canary_count: 0,
            wave_size: 2,
            waves_total: 1,
            stop_on_wave_failure: true,
            inter_wave_delay_seconds: 0,
          },
          summary: {
            config_supported: 2,
            rollback_supported: 2,
            blocked_config: 0,
            blocked_rollback: 0,
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/templates/11/deploy', async (route) => {
    deployPayload = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        summary: [
          {
            device_id: 101,
            device_name: 'edge-1',
            ip_address: '10.10.10.1',
            status: 'success',
            output: 'deploy ok',
            support_policy: { tier: 'full', readiness: 'ready' },
            pre_check: { ok: true, rows: [{ command: 'show version', ok: true }] },
            post_check: { ok: true, command: 'show clock', tried: [] },
            rollback: { attempted: false, success: false, prepared: true, ref: 'rb-edge-1' },
            backup: { id: 9001 },
          },
          {
            device_id: 102,
            device_name: 'edge-2',
            ip_address: '10.10.10.2',
            status: 'postcheck_failed',
            error: 'Post-check failed',
            failure_cause: 'post_check_failed',
            support_policy: { tier: 'full', readiness: 'ready' },
            pre_check: { ok: true, rows: [{ command: 'show version', ok: true }] },
            post_check: { ok: false, command: 'show clock', tried: [{ command: 'show clock', ok: false }] },
            rollback: {
              attempted: true,
              success: true,
              prepared: true,
              ref: 'rb-edge-2',
              output: 'rollback executed',
            },
            backup: { id: 9002 },
          },
        ],
        totals: {
          total: 2,
          success: 1,
          failed: 0,
          postcheck_failed: 1,
          rollback_attempted: 1,
        },
        execution: {
          waves_total: 1,
          waves_executed: 1,
          halted: false,
          execution_id: 'exec-config-11',
        },
        change_plan: {
          route: 'direct',
          reason: 'Target count (2) is within the direct deployment threshold (3).',
          target_count: 2,
          direct_max_devices: 3,
          rollback_on_failure: true,
          approval_bound: false,
          blocked_config_devices: [],
          blocked_rollback_devices: [],
          rollout: {
            canary_count: 0,
            wave_size: 2,
            waves_total: 1,
            stop_on_wave_failure: true,
            inter_wave_delay_seconds: 0,
          },
          summary: {
            config_supported: 2,
            rollback_supported: 2,
            blocked_config: 0,
            blocked_rollback: 0,
          },
        },
      }),
    });
  });

  await gotoWithRetry(page, '/config', { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('config-template-11')).toBeVisible();
  await page.getByTestId('config-template-11').click();
  await page.getByRole('button', { name: /^Deploy$/ }).click();
  await page.getByText('edge-1').click();
  await page.getByText('edge-2').click();
  await page.getByLabel('Wave size').fill('2');
  await page.getByRole('button', { name: /Dry-Run \(Diff\)/i }).click();

  await expect(page.getByTestId('config-change-plan')).toContainText(/direct/i);
  await expect(page.getByTestId('config-dry-run-results')).toContainText('show version');
  await expect(page.getByTestId('config-dry-run-results')).toContainText('show clock');
  await expect(page.getByTestId('config-dry-run-results')).toContainText('checkpoint');

  await page.getByRole('button', { name: /Execute Deploy/i }).click();

  await expect(page.getByTestId('config-deploy-results')).toContainText(/post_check_failed/i);
  await expect(page.getByTestId('config-deploy-results')).toContainText(/Rollback Output/i);
  await expect(page.getByTestId('config-deploy-results')).toContainText(/rollback executed/i);

  expect(deployPayload).not.toBeNull();
  expect(deployPayload.rollback_on_failure).toBe(true);
  expect(deployPayload.wave_size).toBe(2);
});

test('config page blocks smart deploy when change plan is blocked', async ({ page }) => {
  await mockConfigPageCore(page);

  await page.route('**/api/v1/templates/11/dry-run', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        summary: [
          {
            device_id: 101,
            device_name: 'edge-1',
            ip_address: '10.10.10.1',
            status: 'ok',
            support_policy: { tier: 'full', readiness: 'ready' },
            pre_check_commands: ['show version'],
            post_check_commands: ['show clock'],
            change_guard: {
              deploy_allowed: true,
              rollback_supported: true,
              blocked_reasons: [],
            },
            diff_summary: { added_lines: 1, removed_lines: 0, changed_lines_estimate: 1, preview: ['+ hostname edge-1'] },
            diff_lines: ['+ hostname edge-1'],
          },
        ],
        totals: { total: 1, ok: 1, missing_variables: 0 },
        change_plan: {
          route: 'blocked',
          reason: 'Rollback-on-failure is enabled, but some selected devices do not support rollback.',
          target_count: 2,
          direct_max_devices: 3,
          rollback_on_failure: true,
          approval_bound: false,
          blocked_config_devices: [],
          blocked_rollback_devices: [{ id: 102, name: 'edge-2' }],
          rollout: {
            canary_count: 0,
            wave_size: 0,
            waves_total: 1,
            stop_on_wave_failure: true,
            inter_wave_delay_seconds: 0,
          },
          summary: {
            config_supported: 2,
            rollback_supported: 1,
            blocked_config: 0,
            blocked_rollback: 1,
          },
        },
      }),
    });
  });

  await gotoWithRetry(page, '/config', { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('config-template-11')).toBeVisible();
  await page.getByTestId('config-template-11').click();
  await page.getByRole('button', { name: /^Deploy$/ }).click();
  await page.getByText('edge-1').click();
  await page.getByText('edge-2').click();
  await page.getByRole('button', { name: /Dry-Run \(Diff\)/i }).click();

  await expect(page.getByTestId('config-change-plan')).toContainText(/blocked/i);
  await expect(page.getByTestId('config-change-plan')).toContainText('edge-2');
  await expect(page.getByRole('button', { name: /Blocked by Policy/i })).toBeDisabled();
});
