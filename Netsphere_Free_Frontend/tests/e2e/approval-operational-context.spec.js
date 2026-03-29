import { test, expect } from '@playwright/test';
import { buildProPolicy, mockCoreApis, seedAuth } from './helpers';

test('approval detail exposes operational context links for the linked device and site', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['all'] });

  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ preview_enabled: false }),
    });
  });

  await page.route('**/api/v1/approval/**', async (route) => {
    if (route.request().method().toUpperCase() !== 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 88,
          title: 'Fabric rollout approval',
          description: 'Approve the staged change window for site 7.',
          request_type: 'template_deploy',
          requester_id: 1,
          requester_name: 'admin',
          approver_id: null,
          approver_name: null,
          status: 'approved',
          requester_comment: 'Validated in lab.',
          approver_comment: 'Approved for the next wave.',
          created_at: '2026-03-17T08:00:00Z',
          decided_at: '2026-03-17T08:10:00Z',
          payload: {
            device_id: 101,
            device_ids: [101, 102],
            execution_status: 'executed',
            approval_id: 88,
            execution_id: 'exec-88',
            execution_result: {
              summary: [
                { status: 'success' },
              ],
            },
          },
        },
      ]),
    });
  });

  await page.route('**/api/v1/devices/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 101, name: 'edge-sw1', ip_address: '10.10.10.1', device_type: 'arista_eos', site_id: 7, site_name: 'Seoul Campus' },
        { id: 102, name: 'dist-sw1', ip_address: '10.10.10.2', device_type: 'cisco_ios_xe', site_id: 7, site_name: 'Seoul Campus' },
      ]),
    });
  });

  await page.goto('/approval');

  await expect(page.getByText('Fabric rollout approval')).toBeVisible();
  await page.getByText('Fabric rollout approval').click();

  await expect(page.getByTestId('approval-open-device')).toHaveAttribute('href', '/devices/101');
  await expect(page.getByTestId('approval-open-topology')).toHaveAttribute('href', '/topology?siteId=7');
  await expect(page.getByTestId('approval-open-observability')).toHaveAttribute('href', '/observability?siteId=7&deviceId=101');
  await expect(page.getByTestId('approval-open-grafana')).toHaveAttribute('href', /var-site_id=7/);
  await expect(page.getByTestId('approval-open-alert-dashboard')).toHaveAttribute('href', /var-device_id=101/);
  await expect(page.getByText('Seoul Campus')).toBeVisible();
});

test('approval detail shows cloud intent verification and rollback context', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['cloud'] });

  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildProPolicy()),
    });
  });

  await page.route('**/api/v1/approval/**', async (route) => {
    if (route.request().method().toUpperCase() !== 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 109,
          title: 'Cloud guardrail intent',
          request_type: 'intent_apply',
          requester_id: 1,
          requester_name: 'admin',
          approver_id: null,
          approver_name: null,
          status: 'approved',
          created_at: '2026-03-18T09:00:00Z',
          decided_at: '2026-03-18T09:05:00Z',
          payload: {
            execution_status: 'executed',
            approval_id: 109,
            execution_id: 'intent-109',
            change_preview_summary: {
              risk_score: 42,
              blast_radius: { estimated_devices: 2, estimated_networks: 1, estimated_rules: 3 },
              cloud_scope: {
                scoped_resources: 4,
                target_providers: ['aws'],
                target_accounts: [101],
                regions_by_provider: { aws: ['ap-northeast-2'] },
                resources_by_type: { subnet: 1, route_table: 1, security_group: 2 },
              },
              change_summary: ['cloud_scope resources=4 providers=1 accounts=1'],
            },
            spec: {
              targets: {
                providers: ['aws'],
                account_ids: [101],
                regions: ['ap-northeast-2'],
                resource_types: ['subnet', 'route_table', 'security_group'],
              },
            },
            terraform_plan_preview: {
              change_blocks: [
                { provider: 'aws', module: 'aws_cloud_policy', changes: ['~ aws_security_group.sg-main'] },
              ],
              post_check_plan: {
                steps: [
                  'Re-scan scoped accounts after apply.',
                  'Verify protected destinations remain policy-compliant.',
                ],
              },
              evidence_plan: {
                artifacts: [
                  'terraform-plan-preview.json',
                  'post-check-result.json',
                  'rollback-result.json',
                ],
                operator_package_sections: ['summary', 'verification', 'rollback'],
              },
              rollback_plan: {
                status: 'approval_required',
                strategy: 'terraform_state_reconcile',
                automatic_enabled: false,
                operator_steps: [
                  'Review the post-check result before approving any rollback action.',
                ],
              },
            },
            simulation_snapshot: {
              operational_guardrails: {
                summary: {
                  change_enabled_accounts: 0,
                  read_only_accounts: 1,
                  critical_findings: 1,
                },
                findings: [
                  {
                    key: 'read_only_accounts',
                    title: 'Some scoped accounts are still read-only',
                    severity: 'warning',
                    message: '1 scoped account is not change-enabled yet.',
                  },
                ],
                account_modes: [
                  {
                    provider: 'aws',
                    account_id: 101,
                    name: 'aws-prod',
                    change_enabled: false,
                    change_mode_reason: 'Live apply policy is disabled for this account.',
                  },
                ],
              },
            },
            execution_result: {
              execution_actions: {
                results: [
                  {
                    type: 'cloud_intent_apply',
                    status: 'post_check_failed',
                    post_check_failed: true,
                    failure_cause: 'post_check_failed',
                    rollback_attempted: false,
                    rollback_success: false,
                    post_check_result: {
                      status: 'failed',
                      scanned_resources: 2,
                      failed_accounts: 1,
                      blocking_failures: [
                        { account_id: 101, provider: 'aws', message: 'scan timed out' },
                      ],
                    },
                    rollback_plan: {
                      status: 'approval_required',
                      operator_steps: [
                        'Review the post-check result before approving any rollback action.',
                      ],
                    },
                    rollback_result: {
                      status: 'approval_required',
                      message: 'Rollback plan is prepared and awaits explicit approval.',
                    },
                  },
                ],
              },
            },
          },
        },
      ]),
    });
  });

  await page.route('**/api/v1/devices/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.goto('/approval');
  await page.getByText('Cloud guardrail intent').click();

  await expect(page.getByTestId('approval-open-topology-impact')).toHaveAttribute('href', /cloudProvider=aws/);
  await expect(page.getByTestId('approval-open-topology-impact')).toHaveAttribute('href', /cloudAccountId=101/);
  await expect(page.getByTestId('approval-open-topology-impact')).toHaveAttribute('href', /cloudRegion=ap-northeast-2/);
  await expect(page.getByText('Cloud Scope')).toBeVisible();
  await expect(page.getByTestId('approval-cloud-execution-continuity')).toBeVisible();
  await expect(page.getByText('Execution Continuity')).toBeVisible();
  await expect(page.getByText('terraform-plan-preview.json')).toBeVisible();
  await expect(page.getByTestId('approval-cloud-guardrails')).toBeVisible();
  await expect(page.getByText('Some scoped accounts are still read-only')).toBeVisible();
  await expect(page.getByText('AWS #101: scan timed out')).toBeVisible();
  await expect(page.locator('span.font-mono', { hasText: 'Rollback plan is prepared and awaits explicit approval.' })).toBeVisible();
  await expect(page.getByText('Failed Accounts')).toBeVisible();
});
