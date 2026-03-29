import { test, expect } from '@playwright/test';
import { mockCoreApis, seedAuth } from './helpers';

test('notifications page previews and runs issue automation from an active alert', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page);

  let automationRunCalls = 0;

  await page.route('**/api/v1/sdn/issues/unread-count**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ unread_count: 1 }),
    });
  });

  await page.route('**/api/v1/sdn/issues/active**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 501,
          title: 'BGP Neighbor Down: edge-1',
          device: 'edge-1',
          device_id: 77,
          message: 'peer 10.0.0.2 is down',
          severity: 'warning',
          category: 'system',
          is_read: false,
          created_at: '2026-03-08T01:00:00Z',
          status: 'active',
          automation: {
            engine_enabled: true,
            auto_execute_enabled: true,
            direct_change_actions_enabled: false,
            rules_total: 1,
            matched_rules: 1,
            ready_rules: 0,
            approval_rules: 1,
            blocked_rules: 0,
            disabled_rules: 0,
            can_run: true,
            primary_status: 'approval_required',
            next_action: 'Running this alert automation will open an approval request.',
            primary_action: {
              rule_id: 'issue-bgp-run-scan',
              rule_name: 'BGP Alert Scan',
              action_type: 'run_scan',
              action_title: 'Re-scan BGP Segment',
              status: 'approval_required',
            },
          },
        },
      ]),
    });
  });

  await page.route('**/api/v1/sdn/issues/501/automation', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        issue_id: 501,
        issue_title: 'BGP Neighbor Down: edge-1',
        automation: {
          engine_enabled: true,
          auto_execute_enabled: true,
          direct_change_actions_enabled: false,
          rules_total: 1,
          matched_rules: 1,
          ready_rules: 0,
          approval_rules: 1,
          blocked_rules: 0,
          disabled_rules: 0,
          can_run: true,
          primary_status: 'approval_required',
          next_action: 'Running this alert automation will open an approval request.',
          primary_action: {
            rule_id: 'issue-bgp-run-scan',
            rule_name: 'BGP Alert Scan',
            action_type: 'run_scan',
            action_title: 'Re-scan BGP Segment',
            status: 'approval_required',
          },
          decisions: [
            {
              rule_id: 'issue-bgp-run-scan',
              rule_name: 'BGP Alert Scan',
              status: 'approval_required',
              action_type: 'run_scan',
              action_title: 'Re-scan BGP Segment',
              next_action: 'Running this alert automation will open an approval request.',
            },
          ],
          snapshot: {
            issue: {
              match_paths: ['issue.signals.is_bgp', 'issue.severity', 'issue.category'],
            },
          },
        },
      }),
    });
  });

  await page.route('**/api/v1/sdn/issues/501/automation/run', async (route) => {
    automationRunCalls += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        issue_id: 501,
        issue_title: 'BGP Neighbor Down: edge-1',
        automation: {
          can_run: true,
          primary_status: 'approval_required',
        },
        result: {
          executed: 1,
          blocked: 0,
          decisions: [
            {
              status: 'executed',
              approval_id: 901,
              result: { mode: 'approval_opened' },
            },
          ],
        },
      }),
    });
  });

  await page.route('**/api/v1/settings/webhook-deliveries', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        total: 1,
        items: [
          {
            delivery_id: 'delivery-501',
            event_log_id: 12,
            timestamp: '2026-03-08T01:05:00Z',
            mode: 'jira',
            status: 'failed',
            status_code: 502,
            attempts: 3,
            title: 'BGP Neighbor Down: edge-1',
            event_type: 'issue_opened',
            replay_available: true,
            target_host: 'https://jira.local',
            target_path: '/rest/api/2/issue',
            error: 'Upstream timeout',
          },
        ],
      }),
    });
  });

  await page.goto('/notifications');

  await expect(page.getByTestId('northbound-delivery-watch')).toBeVisible();
  await expect(page.getByText('BGP Neighbor Down: edge-1')).toBeVisible();
  await expect(page.getByTestId('issue-automation-badge-501')).toContainText(/Approval Needed/i);

  await page.getByRole('button', { name: /Preview Automation/i }).click();
  await expect(page.getByTestId('issue-automation-panel-501')).toBeVisible();
  await expect(page.getByText('issue.signals.is_bgp')).toBeVisible();

  await page.getByRole('button', { name: /Run Automation/i }).click();
  await expect.poll(() => automationRunCalls).toBe(1);
  await expect(page.getByTestId('issue-automation-run-result-501')).toContainText(/executed 1/i);
});

test('notifications page can open a cloud intent from a cloud-scoped alert', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['cloud'] });

  await page.route('**/api/v1/sdn/issues/unread-count**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ unread_count: 1 }),
    });
  });

  await page.route('**/api/v1/sdn/issues/active**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 601,
          title: 'Cloud route drift detected',
          device: 'aws-app-subnet-1',
          device_id: 88,
          message: 'Detected an unexpected route path for app-subnet-a.',
          severity: 'warning',
          category: 'config',
          is_read: false,
          created_at: '2026-03-08T01:00:00Z',
          status: 'active',
          automation: {
            engine_enabled: true,
            auto_execute_enabled: true,
            direct_change_actions_enabled: false,
            rules_total: 1,
            matched_rules: 1,
            ready_rules: 0,
            approval_rules: 1,
            blocked_rules: 0,
            disabled_rules: 0,
            can_run: true,
            primary_status: 'approval_required',
            next_action: 'Open a scoped Cloud Intent before applying changes.',
            primary_action: {
              rule_id: 'cloud-route-guardrail',
              rule_name: 'Cloud Route Guardrail',
              action_type: 'intent_apply',
              action_title: 'Create Cloud Guardrail Intent',
              status: 'approval_required',
            },
          },
          cloud_scope: {
            provider: 'aws',
            account_id: 101,
            account_name: 'aws-prod',
            region: 'ap-northeast-2',
            resource_type: 'subnet',
            resource_type_label: 'Subnet',
            resource_types: ['subnet', 'route_table', 'security_group'],
            resource_name: 'app-subnet-a',
            resource_id: 'subnet-001',
            can_create_intent: true,
          },
        },
      ]),
    });
  });

  await page.route('**/api/v1/cloud/accounts', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 101, name: 'aws-prod', provider: 'aws', region: 'ap-northeast-2', is_active: true },
      ]),
    });
  });

  await page.route('**/api/v1/intent/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        cloud_execution_mode: 'prepare_only',
        cloud_execution_live_apply_enabled: false,
        cloud_state_backend: 'local',
        cloud_execution_readiness: {
          terraform_runtime: { available: true, resolved: 'terraform' },
          backend_validation: { valid: true, state_prefix: 'netsphere/cloud-intents' },
          errors: [],
          warnings: [],
        },
        supported_intents: ['cloud_policy'],
      }),
    });
  });

  await page.goto('/notifications');

  await expect(page.getByTestId('issue-cloud-badge-601')).toContainText('AWS');
  await expect(page.getByTestId('issue-cloud-scope-601')).toContainText('aws-prod');
  await expect(page.getByTestId('issue-open-topology-impact-601')).toBeVisible();
  await page.getByTestId('issue-open-cloud-intent-601').click();

  await expect(page).toHaveURL(/\/cloud\/intents\?/);
  await expect(page.getByTestId('cloud-intents-name').locator('input')).toHaveValue('aws-app-subnet-a-ap-northeast-2-subnet-guardrail');
  await expect(page.getByTestId('cloud-intents-resource-types').locator('textarea')).toHaveValue('subnet\nroute_table\nsecurity_group');
});

test('notifications page can open topology impact from a cloud-scoped alert', async ({ page }) => {
  await seedAuth(page);
  await mockCoreApis(page, { features: ['cloud'] });

  await page.route('**/api/v1/sdn/issues/unread-count**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ unread_count: 1 }),
    });
  });

  await page.route('**/api/v1/sdn/issues/active**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 602,
          title: 'Cloud ingress drift detected',
          device: 'aws-edge-sg',
          message: 'Security group drift was detected on the production edge subnet.',
          severity: 'warning',
          category: 'security',
          is_read: false,
          created_at: '2026-03-08T01:00:00Z',
          status: 'active',
          cloud_scope: {
            provider: 'aws',
            account_id: 101,
            account_name: 'aws-prod',
            region: 'ap-northeast-2',
            resource_type: 'security_group',
            resource_type_label: 'Security Group',
            resource_types: ['subnet', 'route_table', 'security_group'],
            resource_name: 'edge-sg',
            resource_id: 'sg-001',
            can_create_intent: true,
          },
        },
      ]),
    });
  });

  await page.route('**/api/v1/settings/webhook-deliveries**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total: 0, items: [] }),
    });
  });

  await page.route('**/api/v1/devices/topology/links**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        nodes: [
          {
            id: 'cr-vpc-001',
            label: 'aws-prod-vpc',
            ip: '10.20.0.0/16',
            role: 'cloud',
            status: 'available',
            tier: 0,
            cloud: {
              kind: 'inventory_resource',
              provider: 'aws',
              account_id: 101,
              account_name: 'aws-prod',
              region: 'ap-northeast-2',
              resource_type: 'vpc',
              resource_type_label: 'VPC',
              resource_id: 'vpc-001',
              resource_name: 'aws-prod-vpc',
            },
            hybrid: { role: 'cloud', kind: 'inventory_resource', connected: true, providers: ['aws'], accounts: ['101'], regions: ['ap-northeast-2'] },
          },
          {
            id: 'cr-subnet-001',
            label: 'edge-subnet',
            ip: '10.20.1.0/24',
            role: 'cloud',
            status: 'available',
            tier: 1,
            cloud: {
              kind: 'inventory_resource',
              provider: 'aws',
              account_id: 101,
              account_name: 'aws-prod',
              region: 'ap-northeast-2',
              resource_type: 'subnet',
              resource_type_label: 'Subnet',
              resource_id: 'subnet-001',
              resource_name: 'edge-subnet',
            },
            hybrid: { role: 'cloud', kind: 'inventory_resource', connected: true, providers: ['aws'], accounts: ['101'], regions: ['ap-northeast-2'] },
          },
          {
            id: 'cr-sg-001',
            label: 'edge-sg',
            ip: 'sg-001',
            role: 'cloud',
            status: 'available',
            tier: 2,
            cloud: {
              kind: 'inventory_resource',
              provider: 'aws',
              account_id: 101,
              account_name: 'aws-prod',
              region: 'ap-northeast-2',
              resource_type: 'security_group',
              resource_type_label: 'Security Group',
              resource_id: 'sg-001',
              resource_name: 'edge-sg',
            },
            hybrid: { role: 'cloud', kind: 'inventory_resource', connected: true, providers: ['aws'], accounts: ['101'], regions: ['ap-northeast-2'] },
          },
        ],
        links: [
          {
            source: 'cr-vpc-001',
            target: 'cr-subnet-001',
            protocol: 'CLOUD',
            status: 'active',
            layer: 'hybrid',
            label: 'contains',
            confidence: 1,
            hybrid: { kind: 'inventory', relationship: 'cloud_to_cloud', provider: 'aws', account_id: 101, account_name: 'aws-prod', region: 'ap-northeast-2' },
            evidence: { confidence: 1, protocol: 'cloud', layer: 'hybrid' },
          },
          {
            source: 'cr-subnet-001',
            target: 'cr-sg-001',
            protocol: 'CLOUD',
            status: 'active',
            layer: 'hybrid',
            label: 'protected-by',
            confidence: 1,
            hybrid: { kind: 'inventory', relationship: 'cloud_attachment', provider: 'aws', account_id: 101, account_name: 'aws-prod', region: 'ap-northeast-2' },
            evidence: { confidence: 1, protocol: 'cloud', layer: 'hybrid' },
          },
        ],
      }),
    });
  });

  await page.route('**/api/v1/sites/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/topology/layout**', async (route) => {
    const method = route.request().method().toUpperCase();
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          name: 'default',
          data: [
            { id: 'cr-vpc-001', position: { x: 80, y: 120 }, style: { width: 180, height: 120 } },
            { id: 'cr-subnet-001', position: { x: 340, y: 120 }, style: { width: 180, height: 120 } },
            { id: 'cr-sg-001', position: { x: 600, y: 120 }, style: { width: 180, height: 120 } },
          ],
        }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
  });

  await page.route('**/api/v1/topology/snapshots**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/topology/candidates/summary/trend**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ days: 7, buckets: [], totals: { backlog: 0, resolved: 0 } }),
    });
  });

  await page.route('**/api/v1/topology/candidates/summary**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ totals: { backlog: 0, resolved: 0, actionable: 0 } }),
    });
  });

  await page.route('**/api/v1/topology/candidates**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/topology/events**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/topology/stream**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'event: heartbeat\ndata: {"ok":true}\n\n',
    });
  });

  await page.goto('/notifications');
  await page.getByTestId('issue-open-topology-impact-602').click();

  await expect(page).toHaveURL(/\/topology\?/);
  await expect(page.getByTestId('topology-intent-impact-banner')).toBeVisible();
  await expect(page).toHaveURL(/cloudProvider=aws/);
  await expect(page).toHaveURL(/cloudAccountId=101/);
  await expect(page).toHaveURL(/cloudRegion=ap-northeast-2/);
  await expect(page).toHaveURL(/cloudIntentImpact=1/);
  await expect(page).toHaveURL(/focusCloudResourceId=sg-001/);
});
