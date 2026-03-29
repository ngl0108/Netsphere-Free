import { test, expect } from '@playwright/test';

import { mockCoreApis, seedAuth } from './helpers';

const FREE_BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:18080';

const gotoAtBase = async (page, path) => {
  await page.goto(new URL(path, FREE_BASE_URL).toString(), { waitUntil: 'domcontentloaded' });
};

test('free administrator audit page shows locked policy and sanitized contribution records', async ({ page }) => {
  const policy = {
    preview_enabled: true,
    capture_enabled: true,
    upload_feature_available: true,
    upload_enabled: true,
    upload_participation: 'enabled',
    upload_decision_recorded: true,
    upload_opt_in_enabled: true,
    upload_opt_in_required: true,
    upload_locked: true,
    upload_change_requires_reset: true,
    contribution_scope: 'allowlisted_read_only_commands_only',
    upload_opt_in_recorded_at: '2026-03-21T00:10:00+09:00',
    upload_opt_in_actor: 'bootstrap-admin',
    upload_target_mode: 'remote_only',
    deployment_role: 'collector_installed',
    local_embedded_execution: true,
    remote_upload_destination: 'https://netsphere.example/api/v1/preview/contributions',
    remote_upload_registration_state: 'registered',
    remote_upload_registration_error: '',
    allowed_commands: ['show version', 'show inventory', 'show lldp neighbors detail'],
    allowed_nav_exact_paths: ['/discovery', '/topology', '/diagnosis', '/preview/contribute', '/edition/compare'],
    experience_pillars: [
      { key: 'auto_discovery', title: 'Auto Discovery' },
      { key: 'auto_topology', title: 'Auto Topology' },
      { key: 'connected_nms', title: 'Connected NMS' },
    ],
    same_codebase_surfaces: ['discovery', 'topology', 'diagnosis', 'inventory'],
  };

  await seedAuth(page);
  await mockCoreApis(page, { previewPolicy: policy });

  await page.route('**/api/v1/preview/contributions/recent**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: 'preview-001',
            submitted_at: '2026-03-21T00:15:00+09:00',
            entry_count: 1,
            device_type: 'cisco_ios',
            model: 'C9300',
          },
        ],
      }),
    });
  });

  await page.route('**/api/v1/preview/contributions/preview-001', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'preview-001',
        submitted_at: '2026-03-21T00:15:00+09:00',
        redaction_summary: {
          hostname: 1,
          ip: 2,
          serial: 1,
          secret_line: 1,
        },
        entries: [
          {
            command: 'show version',
            sanitized_output: 'hostname HOST_001\nMgmt IP: IP_001\nSN: SERIAL_001\nsecret removed\n',
            redaction_summary: {
              hostname: 1,
              ip: 1,
              serial: 1,
              secret_line: 1,
            },
          },
        ],
      }),
    });
  });

  await gotoAtBase(page, '/preview/contribute');

  await expect(page.getByTestId('preview-audit-title')).toBeVisible();
  await expect(page.getByTestId('preview-audit-policy-card')).toBeVisible();
  await expect(page.getByTestId('preview-audit-local-card')).toBeVisible();
  await expect(page.getByTestId('preview-audit-outbound-card')).toBeVisible();
  await expect(page.getByText(/Enabled \(locked\)|Enabled/).first()).toBeVisible();
  await expect(page.getByText(/allowlisted_read_only_commands_only/).first()).toBeVisible();
  await expect(page.getByText(/show version/).first()).toBeVisible();
  await expect(page.getByTestId('preview-audit-record-preview-001')).toBeVisible();
  await expect(page.getByRole('button', { name: /Enable contribution upload/i })).toHaveCount(0);

  await page.getByTestId('preview-audit-record-preview-001').click();
  await expect(page.getByTestId('preview-audit-detail-title')).toBeVisible();
  await expect(page.getByText('HOST_001')).toBeVisible();
  await expect(page.getByText('IP_001')).toBeVisible();
  await expect(page.getByTestId('preview-audit-raw-hidden-note')).toBeVisible();
});
