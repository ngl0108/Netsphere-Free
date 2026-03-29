import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const SYNTHETIC_ROOT = path.join(REPO_ROOT, 'test-data', 'synthetic');

export const defaultUser = {
  id: 1,
  username: 'admin',
  role: 'admin',
  eula_accepted: true,
  must_change_password: false,
};

const policySurfaceDefinitions = [
  { key: 'operations_home', path: '/automation', requiredRole: 'operator' },
  { key: 'dashboard', path: '/', requiredRole: 'viewer' },
  { key: 'topology', path: '/topology', requiredRole: 'viewer' },
  { key: 'devices', path: '/devices', requiredRole: 'viewer' },
  { key: 'diagnosis', path: '/diagnosis', requiredRole: 'operator' },
  { key: 'notifications', path: '/notifications', requiredRole: 'viewer' },
  { key: 'observability', path: '/observability', requiredRole: 'operator' },
  { key: 'wireless', path: '/wireless', requiredRole: 'viewer' },
  { key: 'discovery', path: '/discovery', requiredRole: 'operator' },
  { key: 'sites', path: '/sites', requiredRole: 'viewer' },
  { key: 'cloud_accounts', path: '/cloud/accounts', requiredRole: 'operator', feature: 'cloud' },
  { key: 'cloud_intents', path: '/cloud/intents', requiredRole: 'operator', feature: 'cloud' },
  { key: 'approval', path: '/approval', requiredRole: 'operator' },
  { key: 'config', path: '/config', requiredRole: 'operator' },
  { key: 'policy', path: '/policy', requiredRole: 'operator', feature: 'policy' },
  { key: 'images', path: '/images', requiredRole: 'operator', feature: 'images' },
  { key: 'intent_templates', path: '/intent-templates', requiredRole: 'operator' },
  { key: 'visual_config', path: '/visual-config', requiredRole: 'operator', feature: 'visual_config' },
  { key: 'ztp', path: '/ztp', requiredRole: 'operator', feature: 'ztp' },
  { key: 'fabric', path: '/fabric', requiredRole: 'operator', feature: 'fabric' },
  { key: 'preventive_checks', path: '/preventive-checks', requiredRole: 'operator' },
  { key: 'monitoring_profiles', path: '/monitoring-profiles', requiredRole: 'operator' },
  { key: 'source_of_truth', path: '/source-of-truth', requiredRole: 'operator' },
  { key: 'state_history', path: '/state-history', requiredRole: 'operator' },
  { key: 'service_groups', path: '/service-groups', requiredRole: 'operator' },
  { key: 'operations_reports', path: '/operations-reports', requiredRole: 'operator' },
  { key: 'compliance', path: '/compliance', requiredRole: 'operator', feature: 'compliance' },
  { key: 'logs', path: '/logs', requiredRole: 'viewer' },
  { key: 'audit', path: '/audit', requiredRole: 'operator' },
  { key: 'settings', path: '/settings', requiredRole: 'admin' },
  { key: 'users', path: '/users', requiredRole: 'admin' },
  { key: 'edition_compare', path: '/edition/compare', requiredRole: 'viewer' },
  { key: 'preview_contribute', path: '/preview/contribute', requiredRole: 'admin', previewOnly: true },
];

const roleOrder = { admin: 0, operator: 1, viewer: 2 };

const normalizeFeature = (value) =>
  String(value || '').trim().toLowerCase().replace(/[-\s]+/g, '_');

const featureAliases = {
  policy: ['policies'],
  policies: ['policy'],
  visual: ['visual_config'],
  visual_config: ['visual'],
};

function getFeatureCandidates(feature) {
  const base = normalizeFeature(feature);
  if (!base) return [];
  const forward = featureAliases[base] || [];
  const reverse = Object.entries(featureAliases)
    .filter(([, aliases]) => aliases.includes(base))
    .map(([key]) => key);
  return [...new Set([base, ...forward, ...reverse])];
}

function normalizePath(path) {
  const raw = String(path || '').trim() || '/';
  if (raw === '/') return '/';
  return raw.startsWith('/') ? raw.replace(/\/+$/, '') : `/${raw.replace(/\/+$/, '')}`;
}

function matchesAllowedPath(path, previewPolicy) {
  const normalized = normalizePath(path);
  const exact = new Set((previewPolicy?.allowed_nav_exact_paths || []).map(normalizePath));
  const prefixes = (previewPolicy?.allowed_nav_prefixes || []).map(normalizePath);
  if (exact.has(normalized)) return true;
  return prefixes.some((prefix) => normalized === prefix || normalized.startsWith(`${prefix}/`));
}

function buildPolicyManifest({ previewPolicy, license, user = defaultUser }) {
  const previewEnabled = previewPolicy?.preview_enabled === true;
  const role = String(user?.role || 'viewer').toLowerCase();
  const currentRoleOrder = roleOrder[role] ?? 99;
  const normalizedFeatures = new Set((license?.features || []).map(normalizeFeature));
  const hasAll = normalizedFeatures.has('all');

  const surfaces = Object.fromEntries(
    policySurfaceDefinitions.map((surface) => {
      const requiredRoleOrder = roleOrder[surface.requiredRole] ?? 99;
      const roleAllowed = currentRoleOrder <= requiredRoleOrder;

      if (surface.previewOnly) {
        const visible = roleAllowed && previewEnabled;
        return [
          surface.key,
          {
            path: surface.path,
            visible,
            navigable: visible,
            executable: visible,
            blocked_code: visible ? '' : 'preview_only',
            blocked_reason: visible ? '' : 'This surface is available only in NetSphere Free.',
            upgrade_copy: '',
          },
        ];
      }

      if (!roleAllowed) {
        return [
          surface.key,
          {
            path: surface.path,
            visible: false,
            navigable: false,
            executable: false,
            blocked_code: 'role_required',
            blocked_reason: `Requires ${surface.requiredRole} role.`,
            upgrade_copy: '',
          },
        ];
      }

      if (previewEnabled && !matchesAllowedPath(surface.path, previewPolicy)) {
        return [
          surface.key,
          {
            path: surface.path,
            visible: false,
            navigable: false,
            executable: false,
            blocked_code: 'preview_blocked',
            blocked_reason: 'This surface is disabled in NetSphere Free.',
            upgrade_copy: 'Upgrade to Pro to unlock this operating surface.',
          },
        ];
      }

      if (surface.feature && !hasAll) {
        const allowed = getFeatureCandidates(surface.feature).some((candidate) => normalizedFeatures.has(candidate));
        if (!allowed) {
          return [
            surface.key,
            {
              path: surface.path,
              visible: true,
              navigable: false,
              executable: false,
              blocked_code: 'license_feature_required',
              blocked_reason: `Valid license required for '${normalizeFeature(surface.feature)}'.`,
              upgrade_copy: 'Enable the matching Pro capability to open this workflow.',
            },
          ];
        }
      }

      return [
        surface.key,
        {
          path: surface.path,
          visible: true,
          navigable: true,
          executable: true,
          blocked_code: '',
          blocked_reason: '',
          upgrade_copy: '',
        },
      ];
    }),
  );

  return {
    preview_enabled: previewEnabled,
    edition: previewEnabled ? 'free' : 'pro',
    role,
    license: {
      is_valid: license?.is_valid !== false,
      features: Array.isArray(license?.features) ? license.features : ['all'],
      status: license?.status || 'Active',
    },
    preview_policy: {
      managed_node_limit: previewPolicy?.managed_node_limit ?? null,
      managed_nodes: previewPolicy?.managed_nodes || {},
      blocked_features: previewPolicy?.blocked_features || [],
      experience_pillars: previewPolicy?.experience_pillars || [],
      upload_locked: Boolean(previewPolicy?.upload_locked),
      contribution_scope: String(previewPolicy?.contribution_scope || ''),
    },
    surfaces,
  };
}

export const buildFreePolicy = (overrides = {}) => ({
  preview_enabled: true,
  capture_enabled: true,
  upload_feature_available: true,
  upload_enabled: false,
  upload_participation: 'unset',
  upload_decision_recorded: false,
  upload_opt_in_enabled: false,
  upload_opt_in_required: true,
  upload_target_mode: 'remote_only',
  deployment_role: 'collector_installed',
  local_embedded_execution: true,
  remote_upload_destination: 'https://netsphere.example/api/v1/preview/contributions',
  remote_upload_registration_state: 'pending_registration',
  remote_upload_registration_error: '',
  blocked_features: [
    'config_deploy_and_rollback',
    'live_policy_push',
  ],
  allowed_commands: [
    'show version',
    'show inventory',
    'show lldp neighbors detail',
  ],
  allowed_nav_exact_paths: [
    '/',
    '/devices',
    '/topology',
    '/sites',
    '/diagnosis',
    '/notifications',
    '/wireless',
    '/discovery',
    '/automation',
    '/observability',
    '/logs',
    '/audit',
    '/preview/contribute',
  ],
  allowed_nav_prefixes: [
    '/devices',
  ],
  experience_pillars: [
    { key: 'auto_discovery', title: 'Auto Discovery' },
    { key: 'auto_topology', title: 'Auto Topology' },
    { key: 'connected_nms', title: 'Connected NMS' },
  ],
  same_codebase_surfaces: ['discovery', 'topology', 'diagnosis', 'inventory'],
  ...overrides,
});

export const buildProPolicy = (overrides = {}) => ({
  preview_enabled: false,
  capture_enabled: false,
  upload_feature_available: false,
  upload_enabled: false,
  allowed_nav_exact_paths: [],
  allowed_nav_prefixes: [],
  blocked_features: [],
  ...overrides,
});

export async function seedAuth(page, user = defaultUser) {
  await page.addInitScript((u) => {
    localStorage.setItem('authToken', 'e2e-token');
    localStorage.setItem('authUser', JSON.stringify(u));
    localStorage.setItem('nm_locale', 'en');
  }, user);
}

export async function mockCoreApis(page, options = {}) {
  const mode = options.mode || 'multicloud_full';
  const features = Array.isArray(options.features) ? options.features : ['all'];
  const previewPolicy =
    options.previewPolicy ||
    buildProPolicy(options.previewPolicyOverrides || {});
  const license = {
    is_valid: options.licenseValid !== false,
    status: options.licenseValid === false ? 'Not installed' : 'Active',
    features,
    max_devices: 999,
    device_count: 1,
    ...options.license,
  };
  const settings = {
    product_setup_completed: 'true',
    product_operating_mode: mode,
    product_cloud_scope: mode === 'multicloud_full' ? 'inventory' : 'none',
    product_cloud_providers: mode === 'multicloud_full' ? 'aws,azure,gcp,naver' : '',
    session_timeout: '30',
    ...options.settings,
  };

  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(defaultUser) });
  });

  await page.route('**/api/v1/settings/general', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(settings) });
  });

  await page.route('**/api/v1/license/status', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(license) });
  });

  await page.route('**/api/v1/preview/policy', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(previewPolicy) });
  });

  await page.route('**/api/v1/ops/policy-manifest', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildPolicyManifest({ previewPolicy, license, user: defaultUser })),
    });
  });

  await page.route('**/api/v1/sdn/issues/unread-count**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ unread_count: 0 }) });
  });

  await page.route('**/api/v1/sdn/issues/active**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route('**/api/v1/ops/observability**', async (route) => {
    const method = route.request().method().toUpperCase();
    if (method === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ enabled: false }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ enabled: false }) });
  });

  await page.route('**/api/v1/ops/release-evidence**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        generated_at: '2026-03-08T14:00:00+00:00',
        source: 'cache',
        summary: {
          overall_status: 'unavailable',
          accepted_gates: 0,
          available_gates: 0,
          total_gates: 4,
          blocking_gates: [],
          warning_gates: [],
          in_progress_gates: [],
        },
        sections: {},
      }),
    });
  });

  await page.route('**/api/v1/settings/webhook-deliveries**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        days: 7,
        limit: 20,
        total: 0,
        items: [],
      }),
    });
  });

  await page.route('**/api/v1/settings/webhook-deliveries/*/retry', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        delivery_id: 'e2e-delivery-retry',
        result: {
          status: 'success',
          status_code: 200,
          attempts: 1,
        },
      }),
    });
  });

  await page.route('**/api/v1/sites/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });
}

export function loadSyntheticScenario(name = 'normal') {
  const target = path.join(SYNTHETIC_ROOT, 'scenarios', `${String(name || '').trim() || 'normal'}.json`);
  if (!fs.existsSync(target)) {
    throw new Error(`Synthetic scenario not found: ${target}`);
  }
  return JSON.parse(fs.readFileSync(target, 'utf8'));
}

export async function mockSyntheticDiscoveryScenario(page, scenarioName = 'normal', options = {}) {
  const scenario = loadSyntheticScenario(scenarioName);
  const scenarioDevices = Array.isArray(scenario?.devices) ? scenario.devices : [];
  const discoveryRows = scenarioDevices.slice(0, 12).map((d, idx) => ({
    id: Number(idx + 1),
    ip_address: String(d.ip_address || ''),
    hostname: String(d.name || d.ip_address || ''),
    vendor: String(d.vendor || ''),
    model: String(d.device_type || ''),
    device_type: String(d.device_type || 'unknown'),
    status: String(d.status || 'online'),
    confidence: Number(d.confidence || 0.8),
    snmp_status: 'reachable',
  }));

  const siteRows = [...new Set(scenarioDevices.map((d) => String(d.site || '').trim()).filter(Boolean))].map((name, idx) => ({
    id: idx + 1,
    name,
  }));

  const jobId = Number(options.jobId || 9101);
  const firstFailureStatus = Number(options.firstFailureStatus || 0);
  const firstFailureMessage = String(options.firstFailureMessage || 'synthetic failure');

  let scanAttempts = 0;

  await page.route('**/api/v1/devices**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(discoveryRows) });
  });

  await page.route('**/api/v1/sites/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(siteRows) });
  });

  await page.route('**/api/v1/discovery/kpi/summary**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        kpi: scenario?.kpi_snapshot || {},
        totals: { candidate_queue: Number(scenario?.counts?.events || 0) },
        jobs_count: 1,
        jobs: [{ id: jobId, status: 'completed' }],
      }),
    });
  });

  await page.route('**/api/v1/discovery/kpi/alerts**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'healthy', alerts: [] }) });
  });

  await page.route('**/api/v1/topology/candidates/summary**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ totals: { backlog: 0, resolved: Number(scenario?.counts?.events || 0) } }),
    });
  });

  await page.route('**/api/v1/topology/candidates/summary/trend**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ series: [], jobs: [] }) });
  });

  await page.route('**/api/v1/topology/candidates/summary-trend**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ series: [], jobs: [] }) });
  });

  await page.route('**/api/v1/discovery/scan', async (route) => {
    scanAttempts += 1;
    if (scanAttempts === 1 && firstFailureStatus > 0) {
      await route.fulfill({
        status: firstFailureStatus,
        contentType: 'application/json',
        body: JSON.stringify({ detail: firstFailureMessage }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: jobId }),
    });
  });

  await page.route(`**/api/v1/discovery/jobs/${jobId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: jobId, status: 'completed', progress: 100, logs: 'synthetic done' }),
    });
  });

  await page.route(`**/api/v1/discovery/jobs/${jobId}/results`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(discoveryRows),
    });
  });

  await page.route(`**/api/v1/discovery/jobs/${jobId}/stream**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'event: done\ndata: {"status":"completed","progress":100}\n\n',
    });
  });

  await page.route(`**/api/v1/discovery/jobs/${jobId}/kpi`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        kpi: scenario?.kpi_snapshot || {},
        totals: { low_confidence_candidates: 0 },
      }),
    });
  });

  await page.route('**/api/v1/topology**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ nodes: [], links: [] }) });
  });

  return {
    scenario,
    jobId,
    getScanAttempts: () => scanAttempts,
  };
}
