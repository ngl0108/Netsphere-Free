import { test, expect } from '@playwright/test';
import { buildFreePolicy, buildProPolicy, mockCoreApis, seedAuth } from './helpers';

test('NetSphere Free blocks cloud accounts route even when the user opens the URL directly', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['all'] });
  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildFreePolicy()) });
  });

  await page.goto('/cloud/accounts');
  await expect(page).toHaveURL(/\/cloud\/accounts/);
  await expect(page.getByTestId('policy-blocked-page')).toBeVisible();
  await expect(page.getByText('This page is disabled in NetSphere Free.')).toBeVisible();
});

test('NetSphere Pro allows cloud accounts when the cloud feature is licensed', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['cloud'] });
  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildProPolicy()) });
  });
  await page.route('**/api/v1/cloud/accounts', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      return;
    }
    await route.continue();
  });

  await page.goto('/cloud/accounts');
  await expect(page).toHaveURL(/\/cloud\/accounts/);
});

test('NetSphere Pro shows account execution readiness for AWS, Azure, and GCP/NCP-ready providers', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['cloud'] });
  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildProPolicy()) });
  });
  await page.route('**/api/v1/cloud/accounts', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 101,
          name: 'aws-prod',
          provider: 'aws',
          region: 'ap-northeast-2',
          is_active: true,
          sync_status: 'success',
          execution_readiness: {
            stage: 'real_apply_ready',
            change_mode: 'change_enabled',
            change_enabled: true,
            change_mode_reason: 'Credentials, runtime, backend, and live apply policy are ready for approval-gated changes.',
            missing_fields: [],
            warnings: [],
          },
        },
        {
          id: 202,
          name: 'azure-core',
          provider: 'azure',
          region: 'koreacentral',
          is_active: true,
          sync_status: 'success',
          execution_readiness: {
            stage: 'credentials_missing',
            change_mode: 'read_only',
            change_enabled: false,
            change_mode_reason: 'Required provider credentials are incomplete, so this account stays read-only.',
            missing_fields: ['client_secret'],
            warnings: [],
          },
        },
        {
          id: 303,
          name: 'ncp-lab',
          provider: 'ncp',
          region: 'KR',
          is_active: true,
          sync_status: 'success',
          execution_readiness: {
            stage: 'real_apply_ready',
            change_mode: 'change_enabled',
            change_enabled: true,
            change_mode_reason: 'Credentials, runtime, backend, and live apply policy are ready for approval-gated changes.',
            missing_fields: [],
            warnings: [],
          },
        },
      ]),
    });
  });

  await page.goto('/cloud/accounts');
  await expect(page.getByTestId('cloud-accounts-page')).toBeVisible();
  await expect(page.getByTestId('cloud-accounts-exec-ready')).toContainText('2');
  await expect(page.getByTestId('cloud-accounts-exec-scaffold')).toContainText('0');
  await expect(page.getByTestId('cloud-accounts-exec-missing')).toContainText('1');
  await expect(page.getByTestId('cloud-accounts-change-enabled')).toContainText('2');
  await expect(page.getByTestId('cloud-accounts-read-only')).toContainText('1');
  await expect(page.getByTestId('cloud-account-row-101')).toContainText('Ready for real apply');
  await expect(page.getByTestId('cloud-account-row-101')).toContainText('Change enabled');
  await expect(page.getByTestId('cloud-account-row-202')).toContainText('Missing: client_secret');
  await expect(page.getByTestId('cloud-account-row-202')).toContainText('Read-only');
  await expect(page.getByTestId('cloud-account-row-303')).toContainText('Ready for real apply');
});

test('NetSphere Pro lets operators retry the recommended ledger action from the same cloud account row', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['cloud'] });

  let preflightHits = 0;

  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildProPolicy()) });
  });

  await page.route('**/api/v1/cloud/providers/presets', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/cloud/kpi/summary**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(null) });
  });

  await page.route('**/api/v1/cloud/accounts/operations-ledger**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          account_id: 101,
          account_name: 'aws-prod',
          provider: 'aws',
          operations_posture: 'attention',
          pending_approvals: 0,
          latest_approval_id: null,
          last_operation_type: 'preflight',
          last_operation_status: 'failed',
          last_operation_at: '2026-03-23T10:00:00Z',
          last_success_at: null,
          last_failure_at: '2026-03-23T10:00:00Z',
          last_failure_message: 'Access key is missing for this account.',
          last_failure_reason_code: 'credential_issue',
          last_failure_reason_label: 'Credential issue',
          blocker_events: 1,
          retry_recommended: true,
          recent_operations: [
            {
              event_type: 'preflight',
              label: 'Validate',
              status: 'failed',
              timestamp: '2026-03-23T10:00:00Z',
              summary: 'Access key is missing for this account.',
              failure_reason_code: 'credential_issue',
              failure_reason_label: 'Credential issue',
              blocker_count: 1,
              warning_count: 0,
              retryable: true,
              approval_id: null,
            },
          ],
        },
      ]),
    });
  });

  await page.route('**/api/v1/cloud/accounts/101/credentials', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        provider: 'aws',
        credentials: {
          bootstrap_path: 'auto',
        },
      }),
    });
  });

  await page.route('**/api/v1/cloud/accounts/101/preflight', async (route) => {
    preflightHits += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        provider: 'aws',
        status: 'ok',
        checks: [{ key: 'iam', ok: true, message: 'IAM path validated' }],
        summary: 'Validation passed',
      }),
    });
  });

  await page.route('**/api/v1/cloud/accounts', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 101,
          name: 'aws-prod',
          provider: 'aws',
          region: 'ap-northeast-2',
          is_active: true,
          sync_status: 'failed',
          sync_message: 'Latest validation failed.',
          execution_readiness: {
            stage: 'credentials_missing',
            change_mode: 'read_only',
            change_enabled: false,
            change_mode_reason: 'Credentials are incomplete.',
            missing_fields: ['access_key'],
            warnings: [],
          },
        },
      ]),
    });
  });

  await page.goto('/cloud/accounts');
  await expect(page.getByTestId('cloud-account-ledger-101')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-priority-focus')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-lane-board')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-lane-card-recovery')).toContainText('1');
  await expect(page.getByTestId('cloud-operations-lane-open-recovery')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-priority-open-review')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-priority-open-workspace')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-priority-open-intents')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-queue')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-retry-queue')).toBeVisible();
  await expect(page.getByTestId('cloud-retry-queue-item-101')).toBeVisible();
  await expect(page.getByTestId('cloud-operations-execution-highlights')).toBeVisible();
  await expect(page.getByTestId('cloud-execution-highlight-101')).toBeVisible();
  await page.getByTestId('cloud-operations-lane-open-recovery').click();
  await expect(page.getByTestId('cloud-account-ledger-review-101')).toBeVisible();
  await page.getByTestId('cloud-retry-queue-open-review-101').click();
  await expect(page.getByTestId('cloud-account-ledger-review-101')).toBeVisible();
  await page.getByTestId('cloud-operations-priority-open-review').click();
  await expect(page.getByTestId('cloud-account-ledger-review-101')).toBeVisible();
  await page.getByTestId('cloud-operations-queue-review-101').click();
  await expect(page.getByTestId('cloud-account-ledger-101')).toContainText('Credential issue');

  await expect(page.getByTestId('cloud-account-ledger-review-101')).toBeVisible();
  await expect(page.getByTestId('cloud-account-ledger-review-101')).toContainText('Credential review');
  await expect(page.getByTestId('cloud-account-ledger-drift-101')).toBeVisible();
  await expect(page.getByTestId('cloud-account-ledger-drift-101')).toContainText('Inventory drift risk');
  await expect(page.getByTestId('cloud-account-ledger-runbook-101')).toBeVisible();
  await expect(page.getByTestId('cloud-account-ledger-runbook-101')).toContainText('AWS operator runbook');
  await expect(page.getByTestId('cloud-account-ledger-history-101')).toBeVisible();
  await expect(page.getByTestId('cloud-account-ledger-history-101')).toContainText('Recent execution history');
  await expect(page.getByTestId('cloud-account-ledger-next-lane-101')).toBeVisible();
  await expect(page.getByTestId('cloud-account-ledger-next-lane-101')).toContainText('Recovery lane');
  await expect(page.getByTestId('cloud-account-ledger-cadence-101')).toBeVisible();
  await expect(page.getByTestId('cloud-account-ledger-cadence-101')).toContainText('Recovery cadence');
  await expect(page.getByTestId('cloud-account-ledger-schedule-101')).toBeVisible();
  await expect(page.getByTestId('cloud-account-ledger-schedule-101')).toContainText('Recovery checkpoint');
  await expect(page.getByTestId('cloud-account-ledger-review-retry-101')).toContainText('Retry Validate');

  await page.getByTestId('cloud-account-ledger-review-retry-101').click();

  await expect.poll(() => preflightHits).toBe(1);
});

test('NetSphere Pro submits an approval request when live bootstrap requires approval', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['cloud'] });

  let approvalPayload = null;

  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildProPolicy()) });
  });

  await page.route('**/api/v1/cloud/providers/presets', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/cloud/kpi/summary**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(null) });
  });

  await page.route('**/api/v1/cloud/accounts', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 101,
          name: 'aws-prod',
          provider: 'aws',
          region: 'ap-northeast-2',
          is_active: true,
          sync_status: 'success',
          execution_readiness: {
            stage: 'real_apply_ready',
            missing_fields: [],
            warnings: [],
          },
        },
      ]),
    });
  });

  await page.route('**/api/v1/cloud/accounts/101/bootstrap/run', async (route) => {
    await route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: 'Approval required for live cloud bootstrap. Use dry_run or submit an approval request first.',
      }),
    });
  });

  await page.route('**/api/v1/approval/**', async (route) => {
    const method = route.request().method().toUpperCase();
    if (method === 'POST') {
      approvalPayload = JSON.parse(route.request().postData() || '{}');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 77,
          title: approvalPayload?.title || 'Cloud Bootstrap',
          description: approvalPayload?.description || '',
          request_type: 'cloud_bootstrap',
          payload: approvalPayload?.payload || {},
          requester_id: 1,
          approver_id: null,
          status: 'pending',
          requester_comment: approvalPayload?.requester_comment || '',
          approver_comment: null,
          created_at: '2026-03-18T12:00:00Z',
          decided_at: null,
          requester_name: 'admin',
          approver_name: null,
        }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.goto('/cloud/accounts');
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByTestId('cloud-account-row-101').getByRole('button', { name: /Live Bootstrap|Bootstrap/ }).click();

  await expect(page).toHaveURL(/\/approval/);
  expect(approvalPayload?.request_type).toBe('cloud_bootstrap');
  expect(approvalPayload?.payload?.account_ids).toEqual([101]);
  expect(approvalPayload?.payload?.dry_run).toBe(false);
  expect(approvalPayload?.payload?.context?.aws_bootstrap_path).toBe('auto');
});

test('NetSphere Pro still blocks cloud accounts when the cloud feature is missing', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { licenseValid: false, features: [] });
  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildProPolicy()) });
  });

  await page.goto('/cloud/accounts');
  await expect(page).toHaveURL(/\/cloud\/accounts/);
  await expect(page.getByTestId('policy-blocked-page')).toBeVisible();
});
