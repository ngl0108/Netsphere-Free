import { expect, test } from '@playwright/test';

import { buildFreePolicy, buildProPolicy, mockCoreApis, seedAuth } from './helpers';

test('NetSphere Free blocks cloud intents route', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['all'] });
  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildFreePolicy()) });
  });

  await page.goto('/cloud/intents');
  await expect(page.getByTestId('policy-blocked-page')).toBeVisible();
});

test('NetSphere Pro can preview a cloud intent and submit approval', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['cloud'] });
  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildProPolicy()) });
  });

  await page.route('**/api/v1/cloud/accounts', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 101, name: 'aws-prod', provider: 'aws', region: 'ap-northeast-2', is_active: true },
        { id: 202, name: 'azure-core', provider: 'azure', region: 'koreacentral', is_active: true },
      ]),
    });
  });

  await page.route('**/api/v1/intent/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: true,
        apply_requires_approval: true,
        apply_execute_actions_enabled: false,
        max_auto_apply_risk_score: 30,
        northbound_policy_enabled: true,
        northbound_max_auto_publish_risk_score: 20,
        cloud_execution_live_apply_enabled: false,
        cloud_execution_mode: 'prepare_only',
        cloud_state_backend: 'local',
        cloud_state_prefix: 'netsphere/cloud-intents',
        cloud_execution_readiness: {
          mode: 'prepare_only',
          live_apply_enabled: false,
          state_backend: 'local',
          state_prefix: 'netsphere/cloud-intents',
          backend_validation: { backend: 'local', valid: true, errors: [], warnings: [] },
          terraform_runtime: { configured: 'terraform', primary: 'terraform', available: true, resolved: 'C:/terraform.exe' },
          ready_for_real_apply: false,
          errors: [],
          warnings: [
            'Current execution mode is safe-mode. Provider writes remain blocked until real_apply.',
            'Live apply policy is disabled. Approval can still generate preview and evidence bundles.',
          ],
        },
        supported_intents: ['cloud_policy'],
      }),
    });
  });

  await page.route('**/api/v1/intent/validate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        valid: true,
        errors: [],
        warnings: ['provider scope spans multiple accounts'],
        conflicts: [],
        normalized_intent: {
          intent_type: 'cloud_policy',
          name: 'cloud-guardrail-baseline',
        },
      }),
    });
  });

  await page.route('**/api/v1/intent/simulate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        validation: {
          valid: true,
          errors: [],
          warnings: ['missing owner tag on one scoped resource'],
          conflicts: [],
        },
        risk_score: 42,
        blast_radius: {
          estimated_devices: 3,
          estimated_networks: 2,
          estimated_rules: 5,
        },
        cloud_scope: {
          scoped_resources: 5,
          target_providers: ['aws'],
          target_accounts: [101],
        },
        change_summary: [
          'cloud_scope resources=5 providers=1 accounts=1',
          'required_tags missing=1',
        ],
        terraform_plan_preview: {
          engine: 'terraform',
          workspace_prefix: 'netsphere-aws-prod',
          summary: {
            accounts: 1,
            regions: 1,
            narrow_scope_ready: true,
          },
          change_blocks: [
            {
              provider: 'aws',
              module: 'aws_cloud_policy',
              resource_count: 3,
              targeted_resource_types: ['subnet', 'security_group'],
              changes: ['~ aws_security_group.sg-main', '+ aws_route_table.guardrail'],
              verification_checks: ['Re-run Pipeline or Scan for the affected cloud accounts immediately after apply.'],
              risk_hints: ['1 scoped resource is missing the owner tag.'],
            },
          ],
          plan_lines: ['Plan: 1 to add, 1 to change, 0 to destroy.'],
          post_check_plan: {
            required: true,
            steps: ['Re-run Pipeline or Scan for the affected cloud accounts immediately after apply.'],
          },
          evidence_plan: {
            operator_package_sections: ['change_preview', 'execution_logs'],
            artifacts: ['terraform-plan-preview.json', 'runner-result.json'],
          },
          rollback_plan: {
            strategy: 'terraform_state_reconcile',
            automatic_enabled: false,
            operator_steps: [
              'Review the post-check result before approving any rollback action.',
              'Use the rendered Terraform bundle and state backend to prepare rollback execution.',
            ],
          },
          operator_notes: ['Approval required because risk score exceeds auto-apply threshold.'],
        },
        operational_guardrails: {
          summary: {
            scoped_accounts: 1,
            change_enabled_accounts: 0,
            read_only_accounts: 1,
            critical_findings: 2,
            warning_findings: 1,
            approval_required: true,
            global_mode: 'prepare_only',
            state_backend: 'local',
            ready_for_real_apply: false,
            risk_score: 42,
          },
          findings: [
            {
              key: 'public_ingress',
              severity: 'critical',
              title: 'Public ingress rules are in scope',
              message: 'This plan will touch 1 public ingress CIDR guardrails across scoped security policies.',
              recommendation: 'Review blast radius and keep approval mandatory for public ingress changes.',
            },
            {
              key: 'read_only_accounts',
              severity: 'warning',
              title: 'Some scoped accounts are still read-only',
              message: '1 scoped account is not change-enabled yet.',
              recommendation: 'Fix credentials or global execution guardrails before planning real apply.',
            },
          ],
          account_modes: [
            {
              account_id: 101,
              name: 'aws-prod',
              provider: 'aws',
              change_mode: 'read_only',
              stage: 'real_apply_ready',
              change_enabled: false,
              change_mode_reason: 'Global execution guardrails keep this account in read-only mode until runtime, backend, and live apply policy are ready.',
              missing_fields: [],
            },
          ],
        },
        recommendations: ['Start with a single account, one or two regions, and a narrow resource type scope before widening rollout.'],
      }),
    });
  });

  await page.route('**/api/v1/approval/', async (route) => {
    if (route.request().method().toUpperCase() === 'POST') {
      const body = route.request().postDataJSON();
      expect(body.request_type).toBe('intent_apply');
      expect(body.payload.intent_type).toBe('cloud_policy');
      expect(body.payload.dry_run).toBe(false);
      expect(body.payload.terraform_plan_preview.engine).toBe('terraform');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 7001, status: 'pending' }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.goto('/cloud/intents');
  await expect(page.getByTestId('cloud-intents-page')).toBeVisible();
  await page.getByTestId('cloud-intents-simulate').click();
  await expect(page.getByTestId('cloud-intents-preview')).toContainText('Plan: 1 to add, 1 to change, 0 to destroy.');
  await expect(page.getByTestId('cloud-intents-preview')).toContainText('Narrow Scope Ready');
  await expect(page.getByTestId('cloud-intents-impact')).toContainText('Change Impact View');
  await expect(page.getByRole('link', { name: 'Open Topology Impact' })).toHaveAttribute('href', /cloudProvider=aws/);
  await expect(page.getByRole('link', { name: 'Open Topology Impact' })).toHaveAttribute('href', /cloudAccountId=101/);
  await expect(page.getByRole('link', { name: 'Open Topology Impact' })).toHaveAttribute('href', /cloudRegion=ap-northeast-2/);
  await expect(page.getByRole('link', { name: 'Open Topology Impact' })).toHaveAttribute('href', /cloudIntentImpact=1/);
  await expect(page.getByTestId('cloud-intents-preview')).toContainText('Execution Continuity');
  await expect(page.getByTestId('cloud-intents-preview')).toContainText('Post-check plan');
  await expect(page.getByTestId('cloud-intents-preview')).toContainText('Evidence package');
  await expect(page.getByTestId('cloud-intents-preview')).toContainText('Rollback plan');
  await expect(page.getByTestId('cloud-intents-guardrails')).toContainText('Operational guardrails');
  await expect(page.getByTestId('cloud-intents-guardrails')).toContainText('Public ingress rules are in scope');
  await expect(page.getByTestId('cloud-intents-guardrails')).toContainText('Read-only');
  await page.getByTestId('cloud-intents-submit-approval').click();
  await expect(page).toHaveURL(/\/approval/);
});

test('Cloud Intents prefill provider scope from topology context', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['cloud'] });
  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildProPolicy()) });
  });

  await page.route('**/api/v1/cloud/accounts', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 101, name: 'aws-prod', provider: 'aws', region: 'ap-northeast-2', is_active: true },
        { id: 303, name: 'ncp-core', provider: 'ncp', region: 'KR', is_active: true },
      ]),
    });
  });

  await page.route('**/api/v1/intent/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: true,
        apply_requires_approval: true,
        max_auto_apply_risk_score: 30,
        cloud_execution_live_apply_enabled: false,
        cloud_execution_mode: 'prepare_only',
        cloud_state_backend: 'local',
        cloud_execution_readiness: {
          terraform_runtime: { available: true, resolved: 'C:/terraform.exe' },
          backend_validation: { valid: true },
          ready_for_real_apply: false,
          errors: [],
          warnings: [],
        },
        supported_intents: ['cloud_policy'],
      }),
    });
  });

  await page.goto('/cloud/intents?source=topology&provider=aws&accountId=101&region=ap-northeast-2&resourceTypes=subnet,route_table,security_group&resourceName=prod-edge-subnet&intentName=aws-prod-edge-subnet-guardrail');
  await expect(page.getByTestId('cloud-intents-prefill')).toContainText('Prefilled from topology');
  await expect(page.getByTestId('cloud-intents-prefill')).toContainText('AWS');
  await expect(page.getByTestId('cloud-intents-prefill')).toContainText('aws-prod');
  await expect(page.getByTestId('cloud-intents-name').locator('input')).toHaveValue('aws-prod-edge-subnet-guardrail');
  await expect(page.getByTestId('cloud-intents-regions').locator('textarea')).toHaveValue('ap-northeast-2');
  await expect(page.getByTestId('cloud-intents-resource-types').locator('textarea')).toHaveValue('subnet\nroute_table\nsecurity_group');
});
