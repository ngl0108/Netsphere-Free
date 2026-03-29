import {
  Activity,
  Bell,
  ClipboardCheck,
  Cloud,
  Database,
  FileCheck,
  FileText,
  GitBranch,
  HardDrive,
  Layers,
  LayoutDashboard,
  Radar,
  Scroll,
  Server,
  Settings,
  Shield,
  Stethoscope,
  TimerReset,
  Users,
  Wifi,
  Workflow,
  Blocks,
} from 'lucide-react';

export const OPERATIONS_SURFACES = {
  operations_home: {
    key: 'operations_home',
    path: '/automation',
    icon: Workflow,
    labelKey: 'sidebar_automation_hub',
    labelDefault: 'Operations Home',
    titleKey: 'ops_home_surface_title',
    titleDefault: 'Operations Home',
    descKey: 'ops_home_surface_desc',
    descDefault: 'Start from the four operator workspaces instead of hunting through individual pages.',
  },
  dashboard: {
    key: 'dashboard',
    path: '/',
    icon: LayoutDashboard,
    labelKey: 'sidebar_dashboard',
    labelDefault: 'Dashboard',
    descKey: 'ops_surface_dashboard_desc',
    descDefault: 'Review global posture, readiness, and the highest-priority operating signals.',
  },
  topology: {
    key: 'topology',
    path: '/topology',
    icon: Layers,
    labelKey: 'sidebar_network_map',
    labelDefault: 'Network Map',
    descKey: 'ops_surface_topology_desc',
    descDefault: 'See live topology, path trace, candidate links, and service overlays in one map.',
  },
  devices: {
    key: 'devices',
    path: '/devices',
    icon: Server,
    labelKey: 'sidebar_devices',
    labelDefault: 'Devices',
    descKey: 'ops_surface_devices_desc',
    descDefault: 'Move from discovered inventory into managed devices, health, and operating actions.',
  },
  diagnosis: {
    key: 'diagnosis',
    path: '/diagnosis',
    icon: Stethoscope,
    labelKey: 'sidebar_diagnosis',
    labelDefault: 'One-Click Diagnosis',
    descKey: 'ops_surface_diagnosis_desc',
    descDefault: 'Trace abnormal paths, root-cause hints, and next actions without leaving the flow.',
  },
  notifications: {
    key: 'notifications',
    path: '/notifications',
    icon: Bell,
    labelKey: 'sidebar_notifications',
    labelDefault: 'Active Alarms Center',
    descKey: 'ops_surface_notifications_desc',
    descDefault: 'Review active issues, service impact, actions, approvals, and state history context.',
  },
  observability: {
    key: 'observability',
    path: '/observability',
    icon: Activity,
    labelKey: 'sidebar_observability',
    labelDefault: 'Observability',
    descKey: 'ops_surface_observability_desc',
    descDefault: 'Open fleet health, device telemetry, and deeper timeseries analysis surfaces.',
  },
  wireless: {
    key: 'wireless',
    path: '/wireless',
    icon: Wifi,
    labelKey: 'sidebar_wireless',
    labelDefault: 'Wireless',
    descKey: 'ops_surface_wireless_desc',
    descDefault: 'Track wireless estates as part of the same operations posture.',
  },
  discovery: {
    key: 'discovery',
    path: '/discovery',
    icon: Radar,
    labelKey: 'sidebar_auto_discovery',
    labelDefault: 'Auto Discovery',
    descKey: 'hub_item_discovery_desc',
    descDefault: 'Run scans, seed crawl, and turn discovered assets into managed operating scope.',
  },
  sites: {
    key: 'sites',
    path: '/sites',
    icon: Blocks,
    labelKey: 'layout_page_sites',
    labelDefault: 'Sites',
    descKey: 'ops_surface_sites_desc',
    descDefault: 'Group assets by site so discovery, monitoring, and service ownership stay organized.',
  },
  monitoring_profiles: {
    key: 'monitoring_profiles',
    path: '/monitoring-profiles',
    icon: Shield,
    labelKey: 'sidebar_monitoring_profiles',
    labelDefault: 'Monitoring Profiles',
    descKey: 'hub_item_monitoring_profiles_desc',
    descDefault: 'Map discovered assets to role-aware monitoring policies automatically.',
  },
  source_of_truth: {
    key: 'source_of_truth',
    path: '/source-of-truth',
    icon: Database,
    labelKey: 'sidebar_source_of_truth',
    labelDefault: 'Source of Truth',
    descKey: 'hub_item_source_of_truth_desc',
    descDefault: 'Review the lightweight operating asset baseline for devices, services, and cloud resources.',
  },
  cloud_accounts: {
    key: 'cloud_accounts',
    path: '/cloud/accounts',
    icon: Cloud,
    labelKey: 'sidebar_cloud_accounts',
    labelDefault: 'Cloud Accounts',
    descKey: 'ops_surface_cloud_accounts_desc',
    descDefault: 'Validate, scan, and operate cloud accounts from an operator-focused control board.',
  },
  cloud_intents: {
    key: 'cloud_intents',
    path: '/cloud/intents',
    icon: GitBranch,
    labelKey: 'sidebar_cloud_intents',
    labelDefault: 'Cloud Intents',
    descKey: 'ops_surface_cloud_intents_desc',
    descDefault: 'Preview, pre-check, approve, and track infrastructure intent changes before execution.',
  },
  approval: {
    key: 'approval',
    path: '/approval',
    icon: ClipboardCheck,
    labelKey: 'layout_page_approval',
    labelDefault: 'Approval Center',
    descKey: 'hub_item_approval_desc',
    descDefault: 'Review pending approvals, service impact, evidence, and rollback readiness.',
  },
  config: {
    key: 'config',
    path: '/config',
    icon: FileText,
    labelKey: 'layout_page_config',
    labelDefault: 'Configuration Management',
    descKey: 'hub_item_config_desc',
    descDefault: 'Stage configuration changes, dry-run them, and prepare operational deployment.',
  },
  policy: {
    key: 'policy',
    path: '/policy',
    icon: Shield,
    labelKey: 'layout_page_policy',
    labelDefault: 'Security Policy',
    descKey: 'hub_item_policy_desc',
    descDefault: 'Maintain reusable policy intent and enforcement artifacts.',
  },
  images: {
    key: 'images',
    path: '/images',
    icon: HardDrive,
    labelKey: 'layout_page_images',
    labelDefault: 'Image Repository',
    descKey: 'hub_item_images_desc',
    descDefault: 'Prepare software image operations and rollout packs.',
  },
  intent_templates: {
    key: 'intent_templates',
    path: '/intent-templates',
    icon: Workflow,
    labelKey: 'sidebar_intent_templates',
    labelDefault: 'Intent Templates',
    descKey: 'hub_item_intent_templates_desc',
    descDefault: 'Start cloud intent workflows from reusable templates and prefilled change guidance.',
  },
  visual_config: {
    key: 'visual_config',
    path: '/visual-config',
    icon: Layers,
    labelKey: 'layout_page_visual_config',
    labelDefault: 'Visual Config',
    descKey: 'hub_item_visual_desc',
    descDefault: 'Review staged visual changes before execution.',
  },
  ztp: {
    key: 'ztp',
    path: '/ztp',
    icon: HardDrive,
    labelKey: 'layout_page_ztp',
    labelDefault: 'Zero Touch Provisioning',
    descKey: 'hub_item_ztp_desc',
    descDefault: 'Prepare staged onboarding and automated bring-up for eligible devices.',
  },
  fabric: {
    key: 'fabric',
    path: '/fabric',
    icon: Blocks,
    labelKey: 'layout_page_fabric',
    labelDefault: 'Fabric Automation',
    descKey: 'hub_item_fabric_desc',
    descDefault: 'Operate multi-device fabric workflows from a common orchestration surface.',
  },
  preventive_checks: {
    key: 'preventive_checks',
    path: '/preventive-checks',
    icon: Bell,
    labelKey: 'sidebar_preventive_checks',
    labelDefault: 'Preventive Checks',
    descKey: 'hub_item_preventive_checks_desc',
    descDefault: 'Run scheduled preventive reviews and export operating findings.',
  },
  service_groups: {
    key: 'service_groups',
    path: '/service-groups',
    icon: Cloud,
    labelKey: 'sidebar_service_groups',
    labelDefault: 'Service Groups',
    descKey: 'hub_item_service_groups_desc',
    descDefault: 'Map devices and cloud resources into services for impact and reporting.',
  },
  operations_reports: {
    key: 'operations_reports',
    path: '/operations-reports',
    icon: FileCheck,
    labelKey: 'sidebar_operations_reports',
    labelDefault: 'Operations Reports',
    descKey: 'hub_item_operations_reports_desc',
    descDefault: 'Review operations bundles, preventive outputs, and service continuity context.',
  },
  state_history: {
    key: 'state_history',
    path: '/state-history',
    icon: TimerReset,
    labelKey: 'sidebar_state_history',
    labelDefault: 'State History',
    descKey: 'hub_item_state_history_desc',
    descDefault: 'Capture snapshots and compare operating posture over time.',
  },
  compliance: {
    key: 'compliance',
    path: '/compliance',
    icon: FileCheck,
    labelKey: 'layout_page_compliance',
    labelDefault: 'Compliance',
    descKey: 'hub_item_compliance_desc',
    descDefault: 'Track policy conformance, drift, and remediation posture.',
  },
  logs: {
    key: 'logs',
    path: '/logs',
    icon: Scroll,
    labelKey: 'sidebar_system_logs',
    labelDefault: 'System Logs',
    descKey: 'ops_surface_logs_desc',
    descDefault: 'Review runtime events, task history, and support traces.',
  },
  audit: {
    key: 'audit',
    path: '/audit',
    icon: Shield,
    labelKey: 'sidebar_audit_trail',
    labelDefault: 'Audit Trail',
    descKey: 'ops_surface_audit_desc',
    descDefault: 'Inspect approvals, evidence, and administrator audit records.',
  },
  settings: {
    key: 'settings',
    path: '/settings',
    icon: Settings,
    labelKey: 'sidebar_settings',
    labelDefault: 'Settings',
    descKey: 'ops_surface_settings_desc',
    descDefault: 'Review operator defaults, channels, and locked product policy state.',
  },
  users: {
    key: 'users',
    path: '/users',
    icon: Users,
    labelKey: 'sidebar_users',
    labelDefault: 'Users',
    descKey: 'ops_surface_users_desc',
    descDefault: 'Manage platform operators, admins, and access boundaries.',
  },
  edition_compare: {
    key: 'edition_compare',
    path: '/edition/compare',
    icon: ClipboardCheck,
    labelKey: 'sidebar_edition_compare',
    labelDefault: 'Free vs Pro',
    descKey: 'edition_compare_desc',
    descDefault: 'Compare how Free discovery grows into Pro operating scope.',
  },
};

export const OPERATIONS_WORKSPACES = [
  {
    key: 'observe',
    titleKey: 'ops_workspace_observe_title',
    titleDefault: 'Observe',
    descKey: 'ops_workspace_observe_desc',
    descDefault: 'See what is happening now across fleet health, issues, and service impact.',
    primarySurfaces: ['dashboard', 'notifications', 'observability'],
    surfaces: ['dashboard', 'topology', 'devices', 'diagnosis', 'notifications', 'observability', 'wireless'],
  },
  {
    key: 'discover',
    titleKey: 'ops_workspace_discover_title',
    titleDefault: 'Discover',
    descKey: 'ops_workspace_discover_desc',
    descDefault: 'Find assets, classify them, and connect discovery to managed operations.',
    primarySurfaces: ['discovery', 'devices', 'monitoring_profiles'],
    surfaces: ['discovery', 'devices', 'sites', 'monitoring_profiles', 'source_of_truth'],
  },
  {
    key: 'control',
    titleKey: 'ops_workspace_control_title',
    titleDefault: 'Control',
    descKey: 'ops_workspace_control_desc',
    descDefault: 'Stage, preview, approve, and execute controlled infrastructure changes.',
    primarySurfaces: ['cloud_intents', 'approval', 'config'],
    surfaces: ['cloud_accounts', 'cloud_intents', 'approval', 'config', 'policy', 'images', 'intent_templates', 'visual_config', 'ztp', 'fabric'],
  },
  {
    key: 'govern',
    titleKey: 'ops_workspace_govern_title',
    titleDefault: 'Govern',
    descKey: 'ops_workspace_govern_desc',
    descDefault: 'Keep reports, service context, history, compliance, and administration aligned.',
    primarySurfaces: ['operations_reports', 'service_groups', 'state_history'],
    surfaces: ['preventive_checks', 'service_groups', 'operations_reports', 'state_history', 'compliance', 'logs', 'audit', 'settings', 'users', 'edition_compare'],
  },
];

export const SIDEBAR_SECTIONS = [
  {
    key: 'operations',
    titleKey: 'ops_sidebar_section_operations',
    titleDefault: 'Operations',
    surfaces: ['operations_home'],
  },
  {
    key: 'observe',
    titleKey: 'ops_workspace_observe_title',
    titleDefault: 'Observe',
    surfaces: ['dashboard', 'topology', 'notifications', 'observability'],
  },
  {
    key: 'discover',
    titleKey: 'ops_workspace_discover_title',
    titleDefault: 'Discover',
    surfaces: ['discovery', 'devices', 'sites'],
  },
  {
    key: 'control',
    titleKey: 'ops_workspace_control_title',
    titleDefault: 'Control',
    surfaces: ['cloud_accounts', 'cloud_intents', 'approval', 'config'],
  },
  {
    key: 'govern',
    titleKey: 'ops_workspace_govern_title',
    titleDefault: 'Govern',
    surfaces: ['operations_reports', 'service_groups', 'state_history', 'settings'],
  },
  {
    key: 'edition',
    titleKey: 'sidebar_category_preview',
    titleDefault: 'Free Edition',
    surfaces: ['edition_compare'],
  },
];

export const WORKSPACE_META = Object.fromEntries(
  OPERATIONS_WORKSPACES.map((workspace) => [
    workspace.key,
    {
      key: workspace.key,
      titleKey: workspace.titleKey,
      titleDefault: workspace.titleDefault,
      descKey: workspace.descKey,
      descDefault: workspace.descDefault,
      surfaceKeys: Array.isArray(workspace.surfaces) ? [...workspace.surfaces] : [],
      primarySurfaceKeys: Array.isArray(workspace.primarySurfaces) ? [...workspace.primarySurfaces] : [],
    },
  ]),
);

export const SIDEBAR_SECTION_META = {
  operations: {
    key: 'operations',
    titleKey: 'ops_sidebar_section_operations',
    titleDefault: 'Operations',
    surfaceKeys: ['operations_home'],
  },
  observe: {
    key: 'observe',
    titleKey: 'ops_workspace_observe_title',
    titleDefault: 'Observe',
    surfaceKeys: ['dashboard', 'topology', 'notifications', 'observability'],
    workspaceKey: 'observe',
  },
  discover: {
    key: 'discover',
    titleKey: 'ops_workspace_discover_title',
    titleDefault: 'Discover',
    surfaceKeys: ['discovery', 'devices', 'monitoring_profiles'],
    workspaceKey: 'discover',
  },
  control: {
    key: 'control',
    titleKey: 'ops_workspace_control_title',
    titleDefault: 'Control',
    surfaceKeys: ['cloud_accounts', 'cloud_intents', 'approval', 'config'],
    workspaceKey: 'control',
  },
  govern: {
    key: 'govern',
    titleKey: 'ops_workspace_govern_title',
    titleDefault: 'Govern',
    surfaceKeys: ['operations_reports', 'service_groups', 'state_history'],
    workspaceKey: 'govern',
  },
  administration: {
    key: 'administration',
    titleKey: 'ops_sidebar_section_administration',
    titleDefault: 'Administration',
    surfaceKeys: ['settings', 'users'],
  },
  edition: {
    key: 'edition',
    titleKey: 'ops_sidebar_section_edition',
    titleDefault: 'Edition',
    surfaceKeys: ['edition_compare'],
  },
};

const normalizeSurfaceKeys = (value, fallback = []) =>
  Array.isArray(value) && value.length > 0 ? [...value] : [...fallback];

export const getWorkspaceDefinition = (workspaceKey) => WORKSPACE_META[workspaceKey] || null;

export const buildWorkspaceManifest = (manifestWorkspaces) => {
  if (Array.isArray(manifestWorkspaces) && manifestWorkspaces.length > 0) {
    return manifestWorkspaces
      .map((workspace) => {
        const meta = getWorkspaceDefinition(workspace?.key);
        if (!meta) return null;
        const surfaceKeys = normalizeSurfaceKeys(workspace?.surface_keys, meta.surfaceKeys);
        const primarySurfaceKeys = normalizeSurfaceKeys(workspace?.primary_surface_keys, meta.primarySurfaceKeys).filter((key) =>
          surfaceKeys.includes(key),
        );
        return {
          ...meta,
          surfaceKeys,
          primarySurfaceKeys,
        };
      })
      .filter(Boolean);
  }

  return Object.values(WORKSPACE_META);
};

export const getSidebarSectionDefinition = (sectionKey) => SIDEBAR_SECTION_META[sectionKey] || null;

export const buildSidebarSections = (manifestSections, { previewEnabled = false } = {}) => {
  if (Array.isArray(manifestSections) && manifestSections.length > 0) {
    return manifestSections
      .map((section) => {
        const meta = getSidebarSectionDefinition(section?.key);
        if (!meta) return null;
        return {
          ...meta,
          surfaceKeys: normalizeSurfaceKeys(section?.surface_keys, meta.surfaceKeys),
          workspaceKey: section?.workspace_key || meta.workspaceKey || null,
        };
      })
      .filter(Boolean);
  }

  return SIDEBAR_SECTIONS.map((section) => ({
    ...section,
    surfaceKeys: Array.isArray(section.surfaces) ? [...section.surfaces] : [],
  })).filter((section) => !(section.key === 'edition' && !previewEnabled));
};
