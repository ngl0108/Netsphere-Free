import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  CheckCircle, AlertTriangle, Trash2, X, Lock, Mail, UserPlus, Key,
  RefreshCw, Globe, Users, Shield, Bell, Database, Save, Plus, MoreHorizontal, Download, Upload
} from 'lucide-react';
import { AuthService, SettingsService, SDNService, DeviceService, LicenseService, SupportService, IntentService, PreviewService } from '../../api/services';
import { useAuth } from '../../context/AuthContext'; // [RBAC]
import { useToast } from '../../context/ToastContext';
import { useLocation, useNavigate } from 'react-router-dom';
import { getLocale, setLocale as setAppLocale, t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import {
  getOperationalStatusBadgeClass,
  getOperationalStatusHint,
  getOperationalStatusLabel,
} from '../../utils/deviceStatusTone';

const CAPABILITY_PROTOCOL_OPTIONS = ['snmp', 'ssh', 'gnmi'];
const DEFAULT_CAPABILITY_PROFILE = {
  default: {
    allowed_protocols: ['snmp', 'ssh', 'gnmi'],
    auto_reflection: { approval: true, topology: true, sync: true },
    read_only: false,
  },
  sites: {},
  device_types: {},
};
const DEFAULT_CAPABILITY_PROFILE_JSON = JSON.stringify(DEFAULT_CAPABILITY_PROFILE);

const getSettingsTabLabel = (tab) => {
  const key = String(tab || '').toLowerCase();
  if (key === 'general') return t('settings_tab_general', 'General Settings');
  if (key === 'users') return t('settings_tab_users', 'User Management');
  if (key === 'security') return t('settings_tab_security', 'Security & RBAC');
  if (key === 'license') return t('settings_tab_license', 'License Management');
  if (key === 'notifications') return t('settings_tab_notifications', 'Alert Channels');
  if (key === 'backup') return t('settings_tab_backup', 'System Backup');
  return key;
};

const normalizeLanguageSetting = (value) => {
  const raw = String(value || '').trim().toLowerCase();
  if (raw === 'ko' || raw === 'korean' || raw === 'korean (ko)' || raw === '한국어') return 'Korean';
  return 'English';
};

const mapSettingLanguageToLocale = (value) => (normalizeLanguageSetting(value) === 'Korean' ? 'ko' : 'en');
const mapLocaleToSettingLanguage = (value) => (String(value || '').trim().toLowerCase() === 'ko' ? 'Korean' : 'English');

const toBoolValue = (value, fallback = false) => {
  if (typeof value === 'boolean') return value;
  if (value == null) return fallback;
  const normalized = String(value).trim().toLowerCase();
  if (['true', '1', 'yes', 'y', 'on'].includes(normalized)) return true;
  if (['false', '0', 'no', 'n', 'off'].includes(normalized)) return false;
  return fallback;
};

const normalizeProtocols = (value, fallback = CAPABILITY_PROTOCOL_OPTIONS) => {
  const input = Array.isArray(value)
    ? value
    : (typeof value === 'string' ? value.split(',') : []);
  const normalized = [];
  input.forEach((item) => {
    const protocol = String(item || '').trim().toLowerCase();
    if (CAPABILITY_PROTOCOL_OPTIONS.includes(protocol) && !normalized.includes(protocol)) {
      normalized.push(protocol);
    }
  });
  return normalized.length > 0 ? normalized : [...fallback];
};

const createCapabilityLayer = (seed = {}, fallback = DEFAULT_CAPABILITY_PROFILE.default) => ({
  allowed_protocols: normalizeProtocols(seed?.allowed_protocols, fallback?.allowed_protocols || CAPABILITY_PROTOCOL_OPTIONS),
  auto_reflection: {
    approval: toBoolValue(seed?.auto_reflection?.approval, toBoolValue(fallback?.auto_reflection?.approval, true)),
    topology: toBoolValue(seed?.auto_reflection?.topology, toBoolValue(fallback?.auto_reflection?.topology, true)),
    sync: toBoolValue(seed?.auto_reflection?.sync, toBoolValue(fallback?.auto_reflection?.sync, true)),
  },
  read_only: toBoolValue(seed?.read_only, toBoolValue(fallback?.read_only, false)),
});

const createCapabilityOverrideRow = (key = '', layer = {}, fallback = DEFAULT_CAPABILITY_PROFILE.default) => ({
  id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  key: String(key ?? '').trim(),
  layer: createCapabilityLayer(layer, fallback),
});

const parseCapabilityProfileForForm = (rawValue) => {
  const fallbackProfile = {
    default: createCapabilityLayer(DEFAULT_CAPABILITY_PROFILE.default),
    sites: [],
    device_types: [],
  };

  let parsed = rawValue;
  let hadError = false;
  if (typeof rawValue === 'string') {
    const text = rawValue.trim();
    if (!text) return { profile: fallbackProfile, hadError: false };
    try {
      parsed = JSON.parse(text);
    } catch (_e) {
      return { profile: fallbackProfile, hadError: true };
    }
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { profile: fallbackProfile, hadError: true };
  }

  const defaultLayer = createCapabilityLayer(parsed.default, fallbackProfile.default);
  const sites = [];
  const siteObj = parsed.sites;
  if (siteObj && typeof siteObj === 'object' && !Array.isArray(siteObj)) {
    Object.entries(siteObj).forEach(([k, layer]) => {
      const key = String(k || '').trim();
      if (!key) return;
      sites.push(createCapabilityOverrideRow(key, layer, defaultLayer));
    });
  } else if (siteObj != null) {
    hadError = true;
  }

  const deviceTypes = [];
  const typeObj = parsed.device_types;
  if (typeObj && typeof typeObj === 'object' && !Array.isArray(typeObj)) {
    Object.entries(typeObj).forEach(([k, layer]) => {
      const key = String(k || '').trim().toLowerCase();
      if (!key) return;
      deviceTypes.push(createCapabilityOverrideRow(key, layer, defaultLayer));
    });
  } else if (typeObj != null) {
    hadError = true;
  }

  return {
    profile: {
      default: defaultLayer,
      sites,
      device_types: deviceTypes,
    },
    hadError,
  };
};

const serializeCapabilityProfileFromForm = (profile) => {
  const safeProfile = profile || {};
  const defaultLayer = createCapabilityLayer(safeProfile.default);
  const out = {
    default: defaultLayer,
    sites: {},
    device_types: {},
  };

  const sites = Array.isArray(safeProfile.sites) ? safeProfile.sites : [];
  sites.forEach((row) => {
    const key = String(row?.key || '').trim();
    if (!key) return;
    out.sites[key] = createCapabilityLayer(row?.layer, defaultLayer);
  });

  const deviceTypes = Array.isArray(safeProfile.device_types) ? safeProfile.device_types : [];
  deviceTypes.forEach((row) => {
    const key = String(row?.key || '').trim().toLowerCase();
    if (!key) return;
    out.device_types[key] = createCapabilityLayer(row?.layer, defaultLayer);
  });

  return JSON.stringify(out);
};

const SettingsPage = () => {
  const { user, isAdmin, refreshUser } = useAuth(); // [RBAC]
  const { toast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  useLocaleRerender();
  const [activeTab, setActiveTab] = useState('general');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [webhookDeliveries, setWebhookDeliveries] = useState([]);
  const [webhookHistoryLoading, setWebhookHistoryLoading] = useState(false);
  const [webhookHistoryRefreshing, setWebhookHistoryRefreshing] = useState(false);
  const [webhookRetryingId, setWebhookRetryingId] = useState(null);
  const [devices, setDevices] = useState([]);
  const [sites, setSites] = useState([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const currentRoleLabel = useMemo(() => {
    const roleKey = String(user?.role || '').trim().toLowerCase();
    if (roleKey === 'admin') return t('role_admin', 'Administrator');
    if (roleKey === 'operator') return t('role_operator', 'Operator');
    if (roleKey === 'viewer') return t('role_viewer', 'Viewer');
    return t('common_unknown', 'Unknown');
  }, [user?.role]);
  const settingsAccessCopy = useMemo(() => {
    const roleKey = String(user?.role || '').trim().toLowerCase();
    if (roleKey === 'admin') {
      return t(
        'settings_access_desc_admin',
        'Administrators own system settings, credential policy, backup controls, and alert channel configuration. Save actions remain restricted to this role.',
      );
    }
    if (roleKey === 'operator') {
      return t(
        'settings_access_desc_operator',
        'Operators can review system policy, audit posture, and notification setup, but settings stay read-only until an administrator applies changes.',
      );
    }
    return t(
      'settings_access_desc_viewer',
      'Viewers can inspect system policy and current configuration posture, but all settings remain read-only.',
    );
  }, [user?.role]);
  // const [currentUser, setCurrentUser] = useState(null); // Removed, use 'user' from context

  // Unified settings state
  const [settings, setSettings] = useState({
    hostname: '',
    contact_email: '',
    timezone: 'UTC',
    language: mapLocaleToSettingLanguage(getLocale()),
    session_timeout: 30,
    max_login_attempts: 5,
    lockout_minutes: 15,
    enable_2fa: false,
    password_min_length: 10,
    password_required_classes: 3,
    password_forbid_username: true,
    password_history_count: 5,
    password_expire_days: 0,
    audit_chain_enabled: true,
    audit_hmac_key: '',
    audit_forward_syslog_enabled: false,
    audit_forward_syslog_host: '',
    audit_forward_syslog_port: 514,
    pii_masking_enabled: false,
    pii_mask_ip: true,
    pii_mask_mac: true,
    pii_mask_phone: true,
    pii_mask_email: true,
    webhook_enabled: false,
    webhook_url: '',
    webhook_secret: '',
    webhook_timeout_seconds: 5,
    webhook_delivery_mode: 'generic',
    webhook_auth_type: 'none',
    webhook_auth_token: '',
    webhook_auth_header_name: 'Authorization',
    webhook_jira_project_key: '',
    webhook_jira_issue_type: 'Task',
    webhook_servicenow_table: 'incident',
    webhook_elastic_index: 'netsphere-events',
    webhook_retry_attempts: 3,
    webhook_retry_backoff_seconds: 1,
    webhook_retry_max_backoff_seconds: 8,
    webhook_retry_jitter_seconds: 0.2,
    webhook_retry_on_4xx: false,
    discovery_scope_include_cidrs: '',
    discovery_scope_exclude_cidrs: '',
    discovery_prefer_private: true,
    neighbor_crawl_scope_include_cidrs: '',
    neighbor_crawl_scope_exclude_cidrs: '',
    neighbor_crawl_prefer_private: true,
    auto_discovery_enabled: false,
    auto_discovery_interval_seconds: 1800,
    auto_discovery_mode: 'cidr',
    auto_discovery_cidr: '192.168.1.0/24',
    auto_discovery_seed_ip: '',
    auto_discovery_seed_device_id: '',
    auto_discovery_max_depth: 2,
    auto_discovery_site_id: '',
    auto_discovery_snmp_profile_id: '',
    auto_discovery_snmp_version: 'v2c',
    auto_discovery_snmp_port: 161,
    auto_discovery_refresh_topology: false,
    auto_topology_refresh_max_depth: 2,
    auto_topology_refresh_max_devices: 200,
    auto_topology_refresh_min_interval_seconds: 0.05,
    topology_candidate_low_confidence_threshold: 0.7,
    auto_discovery_last_run_at: '',
    auto_discovery_last_job_id: '',
    auto_discovery_last_job_cidr: '',
    auto_discovery_last_error: '',
    auto_topology_last_run_at: '',
    auto_topology_last_job_id: '',
    auto_topology_last_targets: '',
    auto_topology_last_enqueued_ok: '',
    auto_topology_last_enqueued_fail: '',
    auto_topology_last_error: '',
    auto_approve_enabled: false,
    auto_approve_min_vendor_confidence: 0.8,
    auto_approve_require_snmp_reachable: true,
    auto_approve_block_severities: 'error',
    auto_approve_trigger_topology: false,
    auto_approve_topology_depth: 2,
    auto_approve_trigger_sync: false,
    auto_approve_trigger_monitoring: false,
    ops_alerts_min_auto_reflection_pct: 70,
    ops_alerts_max_false_positive_pct: 20,
    ops_alerts_max_low_confidence_rate_pct: 30,
    ops_alerts_max_candidate_backlog: 100,
    ops_alerts_max_stale_backlog_24h: 20,
    ops_alerts_min_closed_loop_execute_per_trigger_pct: 30,
    ops_alerts_max_closed_loop_blocked_per_trigger_pct: 70,
    ops_alerts_max_closed_loop_approvals_per_execution_pct: 100,
    ops_alerts_min_closed_loop_cycles_30d: 1,
    ops_alerts_min_auto_action_rate_pct: 60,
    ops_alerts_max_operator_intervention_rate_pct: 40,
    ops_alerts_min_change_success_rate_pct: 98,
    ops_alerts_max_change_failure_rate_pct: 1,
    ops_alerts_max_change_rollback_p95_ms: 180000,
    ops_alerts_min_change_trace_coverage_pct: 100,
    release_evidence_refresh_enabled: true,
    release_evidence_refresh_profile: 'ci',
    release_evidence_refresh_include_synthetic: false,
    release_evidence_refresh_include_northbound_probe: false,
    change_policy_template_direct_max_devices: 3,
    change_policy_compliance_direct_max_devices: 3,
    change_policy_fabric_live_requires_approval: true,
    change_policy_cloud_bootstrap_live_requires_approval: true,
    intent_apply_execute_actions: false,
    intent_northbound_policy_enabled: false,
    intent_northbound_max_auto_publish_risk_score: 30,
    closed_loop_execute_change_actions: false,
    closed_loop_rules_json: '[]',
    capability_profile_json: DEFAULT_CAPABILITY_PROFILE_JSON,
    smtp_host: '',
    smtp_port: 587,
    smtp_user: '',
    smtp_password: '',
    smtp_from: ''
  });

  const [myEmail, setMyEmail] = useState('');
  const [myMfaEnabled, setMyMfaEnabled] = useState(false);
  const [myEmailVerified, setMyEmailVerified] = useState(false);
  const [mySaving, setMySaving] = useState(false);
  const [emailVerifyChallengeId, setEmailVerifyChallengeId] = useState(null);
  const [emailVerifyOtp, setEmailVerifyOtp] = useState('');
  const [emailVerifySending, setEmailVerifySending] = useState(false);
  const [emailVerifyVerifying, setEmailVerifyVerifying] = useState(false);
  const [emailVerifyCooldownSeconds, setEmailVerifyCooldownSeconds] = useState(0);
  const [emailVerifyFocusSignal, setEmailVerifyFocusSignal] = useState(0);

  const emailVerifyOtpLength = useMemo(() => {
    const v = Number(settings?.email_verify_otp_length);
    if (Number.isFinite(v) && v >= 4 && v <= 10) return v;
    return 6;
  }, [settings?.email_verify_otp_length]);

  useEffect(() => {
    if (emailVerifyCooldownSeconds <= 0) return;
    const t = window.setTimeout(() => {
      setEmailVerifyCooldownSeconds((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => window.clearTimeout(t);
  }, [emailVerifyCooldownSeconds]);

  useEffect(() => {
    setMyEmail(user?.email || '');
    setMyMfaEnabled(!!user?.mfa_enabled);
    setMyEmailVerified(!!user?.email_verified);
  }, [user?.email, user?.mfa_enabled, user?.email_verified]);

  // User management state
  const [users, setUsers] = useState([]);
  const [showUserModal, setShowUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [previewPolicy, setPreviewPolicy] = useState(null);
  const capabilitySyncRef = useRef(false);
  const generalTabDataCacheRef = useRef({ loaded: false, loadedAt: 0 });
  const [capabilityProfileForm, setCapabilityProfileForm] = useState(() => parseCapabilityProfileForForm(DEFAULT_CAPABILITY_PROFILE_JSON).profile);
  const [capabilityProfileParseError, setCapabilityProfileParseError] = useState(false);
  const [closedLoopRulesLint, setClosedLoopRulesLint] = useState(null);
  const [closedLoopRulesLintLoading, setClosedLoopRulesLintLoading] = useState(false);
  const [closedLoopRulesLintError, setClosedLoopRulesLintError] = useState('');
  const [blockSaveOnClosedLoopConflict, setBlockSaveOnClosedLoopConflict] = useState(true);

  const closedLoopLintConflictsCount = Number(closedLoopRulesLint?.conflicts_count || 0);
  const closedLoopLintWarningsCount = Number(closedLoopRulesLint?.warnings_count || 0);
  const saveBlockedByClosedLoopLint =
    activeTab === 'general' &&
    !!blockSaveOnClosedLoopConflict &&
    closedLoopLintConflictsCount > 0;

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const requestedTab = String(params.get('tab') || '').trim().toLowerCase();
    if (!requestedTab) return;
    const allowedTabs = new Set(['general', 'users', 'security', 'notifications', 'license', 'backup']);
    if (!allowedTabs.has(requestedTab)) return;
    if (requestedTab !== activeTab) {
      setActiveTab(requestedTab);
    }
  }, [activeTab, location.search]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await PreviewService.getPolicy();
        if (!cancelled) {
          setPreviewPolicy(res?.data || null);
        }
      } catch (_error) {
        if (!cancelled) {
          setPreviewPolicy(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (capabilitySyncRef.current) {
      capabilitySyncRef.current = false;
      return;
    }
    const parsed = parseCapabilityProfileForForm(settings.capability_profile_json);
    setCapabilityProfileForm(parsed.profile);
    setCapabilityProfileParseError(parsed.hadError);
  }, [settings.capability_profile_json]);

  useEffect(() => {
    const serialized = serializeCapabilityProfileFromForm(capabilityProfileForm);
    setSettings((prev) => {
      if (prev.capability_profile_json === serialized) return prev;
      capabilitySyncRef.current = true;
      return { ...prev, capability_profile_json: serialized };
    });
  }, [capabilityProfileForm]);

  // Initial data load (User is loaded by AuthContext)
  const toErrorText = (err, fallback) => {
    const detail = err?.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (detail && typeof detail === 'object') {
      if (typeof detail.message === 'string' && detail.message.trim()) return detail.message;
      try {
        return JSON.stringify(detail);
      } catch (_e) {
        return fallback;
      }
    }
    return String(err?.message || fallback || 'request failed');
  };

  const reloadClosedLoopRulesLint = useCallback(async () => {
    setClosedLoopRulesLintLoading(true);
    try {
      const res = await IntentService.getClosedLoopRulesLint();
      const body = res?.data || {};
      setClosedLoopRulesLint(body);
      setClosedLoopRulesLintError('');
      return body;
    } catch (err) {
      const msg = toErrorText(err, 'Failed to load closed-loop lint');
      setClosedLoopRulesLintError(msg);
      return null;
    } finally {
      setClosedLoopRulesLintLoading(false);
    }
  }, []);

  const lintClosedLoopRulesDraft = useCallback(async () => {
    const raw = String(settings?.closed_loop_rules_json ?? '').trim() || '[]';
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (_e) {
      const msg = t('settings_closed_loop_json_invalid', 'closed_loop_rules_json is not valid JSON.');
      setClosedLoopRulesLintError(msg);
      toast.error(msg);
      return null;
    }
    if (!Array.isArray(parsed)) {
      const msg = t('settings_closed_loop_json_array_required', 'closed_loop_rules_json must be a JSON array of rules.');
      setClosedLoopRulesLintError(msg);
      toast.error(msg);
      return null;
    }
    setClosedLoopRulesLintLoading(true);
    try {
      const res = await IntentService.lintClosedLoopRules(parsed);
      const body = res?.data || {};
      setClosedLoopRulesLint(body);
      setClosedLoopRulesLintError('');
      toast.success(
        t('settings_lint_complete_fmt', 'Lint complete: conflicts {conflicts}, warnings {warnings}')
          .replace('{conflicts}', String(Number(body?.conflicts_count || 0)))
          .replace('{warnings}', String(Number(body?.warnings_count || 0))),
      );
      return body;
    } catch (err) {
      const msg = toErrorText(err, t('settings_lint_failed', 'Failed to lint closed-loop rules'));
      setClosedLoopRulesLintError(msg);
      toast.error(msg);
      return null;
    } finally {
      setClosedLoopRulesLintLoading(false);
    }
  }, [settings?.closed_loop_rules_json, toast]);

  const loadWebhookDeliveries = useCallback(async ({ silent = false, refreshing = false } = {}) => {
    if (refreshing) setWebhookHistoryRefreshing(true);
    else setWebhookHistoryLoading(true);
    try {
      const res = await SettingsService.listWebhookDeliveries({ days: 7, limit: 20 });
      const body = res?.data || {};
      setWebhookDeliveries(Array.isArray(body?.items) ? body.items : []);
      return body;
    } catch (err) {
      if (!silent) {
        toast.error(toErrorText(err, t('settings_webhook_history_failed', 'Failed to load webhook delivery history')));
      }
      return null;
    } finally {
      if (refreshing) setWebhookHistoryRefreshing(false);
      else setWebhookHistoryLoading(false);
    }
  }, [toast]);

  const loadTabData = useCallback(async () => {
    setLoading(true);
    try {
      if (activeTab === 'users') {
        const res = await SDNService.getUsers();
        setUsers(Array.isArray(res.data) ? res.data : []);
      } else if (activeTab !== 'backup') {
        const res = await SettingsService.getGeneral();
        const incoming = { ...(res.data || {}) };
        const truthy = (v) => {
          const s = String(v ?? '').trim().toLowerCase();
          return ['true', '1', 'yes', 'y', 'on'].includes(s);
        };
        if (incoming.discovery_prefer_private !== undefined) incoming.discovery_prefer_private = truthy(incoming.discovery_prefer_private);
        if (incoming.neighbor_crawl_prefer_private !== undefined) incoming.neighbor_crawl_prefer_private = truthy(incoming.neighbor_crawl_prefer_private);
        if (incoming.auto_discovery_enabled !== undefined) incoming.auto_discovery_enabled = truthy(incoming.auto_discovery_enabled);
        if (incoming.auto_discovery_refresh_topology !== undefined) incoming.auto_discovery_refresh_topology = truthy(incoming.auto_discovery_refresh_topology);
        if (incoming.enable_2fa !== undefined) incoming.enable_2fa = truthy(incoming.enable_2fa);
        if (incoming.password_forbid_username !== undefined) incoming.password_forbid_username = truthy(incoming.password_forbid_username);
        if (incoming.audit_chain_enabled !== undefined) incoming.audit_chain_enabled = truthy(incoming.audit_chain_enabled);
        if (incoming.audit_forward_syslog_enabled !== undefined) incoming.audit_forward_syslog_enabled = truthy(incoming.audit_forward_syslog_enabled);
        if (incoming.pii_masking_enabled !== undefined) incoming.pii_masking_enabled = truthy(incoming.pii_masking_enabled);
        if (incoming.pii_mask_ip !== undefined) incoming.pii_mask_ip = truthy(incoming.pii_mask_ip);
        if (incoming.pii_mask_mac !== undefined) incoming.pii_mask_mac = truthy(incoming.pii_mask_mac);
        if (incoming.pii_mask_phone !== undefined) incoming.pii_mask_phone = truthy(incoming.pii_mask_phone);
        if (incoming.pii_mask_email !== undefined) incoming.pii_mask_email = truthy(incoming.pii_mask_email);
        if (incoming.webhook_enabled !== undefined) incoming.webhook_enabled = truthy(incoming.webhook_enabled);
        if (incoming.webhook_retry_on_4xx !== undefined) incoming.webhook_retry_on_4xx = truthy(incoming.webhook_retry_on_4xx);
        if (incoming.auto_discovery_interval_seconds !== undefined) incoming.auto_discovery_interval_seconds = Number(incoming.auto_discovery_interval_seconds) || 0;
        if (incoming.auto_discovery_max_depth !== undefined) incoming.auto_discovery_max_depth = Number(incoming.auto_discovery_max_depth) || 0;
        if (incoming.auto_discovery_snmp_port !== undefined) incoming.auto_discovery_snmp_port = Number(incoming.auto_discovery_snmp_port) || 161;
        if (incoming.auto_topology_refresh_max_depth !== undefined) incoming.auto_topology_refresh_max_depth = Number(incoming.auto_topology_refresh_max_depth) || 0;
        if (incoming.auto_topology_refresh_max_devices !== undefined) incoming.auto_topology_refresh_max_devices = Number(incoming.auto_topology_refresh_max_devices) || 0;
        if (incoming.auto_topology_refresh_min_interval_seconds !== undefined) incoming.auto_topology_refresh_min_interval_seconds = Number(incoming.auto_topology_refresh_min_interval_seconds) || 0;
        if (incoming.topology_candidate_low_confidence_threshold !== undefined) {
          const v = Number(incoming.topology_candidate_low_confidence_threshold);
          incoming.topology_candidate_low_confidence_threshold = Number.isFinite(v) ? v : 0.7;
        }
        if (incoming.auto_approve_enabled !== undefined) incoming.auto_approve_enabled = truthy(incoming.auto_approve_enabled);
        if (incoming.auto_approve_require_snmp_reachable !== undefined) incoming.auto_approve_require_snmp_reachable = truthy(incoming.auto_approve_require_snmp_reachable);
        if (incoming.auto_approve_trigger_topology !== undefined) incoming.auto_approve_trigger_topology = truthy(incoming.auto_approve_trigger_topology);
        if (incoming.auto_approve_trigger_sync !== undefined) incoming.auto_approve_trigger_sync = truthy(incoming.auto_approve_trigger_sync);
        if (incoming.auto_approve_trigger_monitoring !== undefined) incoming.auto_approve_trigger_monitoring = truthy(incoming.auto_approve_trigger_monitoring);
        if (incoming.change_policy_fabric_live_requires_approval !== undefined) incoming.change_policy_fabric_live_requires_approval = truthy(incoming.change_policy_fabric_live_requires_approval);
        if (incoming.change_policy_cloud_bootstrap_live_requires_approval !== undefined) incoming.change_policy_cloud_bootstrap_live_requires_approval = truthy(incoming.change_policy_cloud_bootstrap_live_requires_approval);
        if (incoming.intent_apply_execute_actions !== undefined) incoming.intent_apply_execute_actions = truthy(incoming.intent_apply_execute_actions);
        if (incoming.intent_northbound_policy_enabled !== undefined) incoming.intent_northbound_policy_enabled = truthy(incoming.intent_northbound_policy_enabled);
        if (incoming.closed_loop_execute_change_actions !== undefined) incoming.closed_loop_execute_change_actions = truthy(incoming.closed_loop_execute_change_actions);
        if (incoming.session_timeout !== undefined) incoming.session_timeout = Number(incoming.session_timeout) || 0;
        if (incoming.max_login_attempts !== undefined) incoming.max_login_attempts = Number(incoming.max_login_attempts) || 0;
        if (incoming.lockout_minutes !== undefined) incoming.lockout_minutes = Number(incoming.lockout_minutes) || 0;
        if (incoming.password_min_length !== undefined) incoming.password_min_length = Number(incoming.password_min_length) || 0;
        if (incoming.password_required_classes !== undefined) incoming.password_required_classes = Number(incoming.password_required_classes) || 0;
        if (incoming.password_history_count !== undefined) incoming.password_history_count = Number(incoming.password_history_count) || 0;
        if (incoming.password_expire_days !== undefined) incoming.password_expire_days = Number(incoming.password_expire_days) || 0;
        if (incoming.audit_forward_syslog_port !== undefined) incoming.audit_forward_syslog_port = Number(incoming.audit_forward_syslog_port) || 0;
        if (incoming.webhook_timeout_seconds !== undefined) incoming.webhook_timeout_seconds = Number(incoming.webhook_timeout_seconds) || 0;
        if (incoming.webhook_retry_attempts !== undefined) incoming.webhook_retry_attempts = Number(incoming.webhook_retry_attempts) || 0;
        if (incoming.webhook_retry_backoff_seconds !== undefined) incoming.webhook_retry_backoff_seconds = Number(incoming.webhook_retry_backoff_seconds) || 0;
        if (incoming.webhook_retry_max_backoff_seconds !== undefined) incoming.webhook_retry_max_backoff_seconds = Number(incoming.webhook_retry_max_backoff_seconds) || 0;
        if (incoming.webhook_retry_jitter_seconds !== undefined) incoming.webhook_retry_jitter_seconds = Number(incoming.webhook_retry_jitter_seconds) || 0;
        if (incoming.auto_approve_min_vendor_confidence !== undefined) {
          const v = Number(incoming.auto_approve_min_vendor_confidence);
          incoming.auto_approve_min_vendor_confidence = Number.isFinite(v) ? v : 0.8;
        }
        if (incoming.auto_approve_topology_depth !== undefined) incoming.auto_approve_topology_depth = Number(incoming.auto_approve_topology_depth) || 0;
        if (incoming.ops_alerts_min_auto_reflection_pct !== undefined) incoming.ops_alerts_min_auto_reflection_pct = Number(incoming.ops_alerts_min_auto_reflection_pct) || 0;
        if (incoming.ops_alerts_max_false_positive_pct !== undefined) incoming.ops_alerts_max_false_positive_pct = Number(incoming.ops_alerts_max_false_positive_pct) || 0;
        if (incoming.ops_alerts_max_low_confidence_rate_pct !== undefined) incoming.ops_alerts_max_low_confidence_rate_pct = Number(incoming.ops_alerts_max_low_confidence_rate_pct) || 0;
        if (incoming.ops_alerts_max_candidate_backlog !== undefined) incoming.ops_alerts_max_candidate_backlog = Number(incoming.ops_alerts_max_candidate_backlog) || 0;
        if (incoming.ops_alerts_max_stale_backlog_24h !== undefined) incoming.ops_alerts_max_stale_backlog_24h = Number(incoming.ops_alerts_max_stale_backlog_24h) || 0;
        if (incoming.ops_alerts_min_closed_loop_execute_per_trigger_pct !== undefined) incoming.ops_alerts_min_closed_loop_execute_per_trigger_pct = Number(incoming.ops_alerts_min_closed_loop_execute_per_trigger_pct) || 0;
        if (incoming.ops_alerts_max_closed_loop_blocked_per_trigger_pct !== undefined) incoming.ops_alerts_max_closed_loop_blocked_per_trigger_pct = Number(incoming.ops_alerts_max_closed_loop_blocked_per_trigger_pct) || 0;
        if (incoming.ops_alerts_max_closed_loop_approvals_per_execution_pct !== undefined) incoming.ops_alerts_max_closed_loop_approvals_per_execution_pct = Number(incoming.ops_alerts_max_closed_loop_approvals_per_execution_pct) || 0;
        if (incoming.ops_alerts_min_closed_loop_cycles_30d !== undefined) incoming.ops_alerts_min_closed_loop_cycles_30d = Number(incoming.ops_alerts_min_closed_loop_cycles_30d) || 0;
        if (incoming.ops_alerts_min_auto_action_rate_pct !== undefined) incoming.ops_alerts_min_auto_action_rate_pct = Number(incoming.ops_alerts_min_auto_action_rate_pct) || 0;
        if (incoming.ops_alerts_max_operator_intervention_rate_pct !== undefined) incoming.ops_alerts_max_operator_intervention_rate_pct = Number(incoming.ops_alerts_max_operator_intervention_rate_pct) || 0;
        if (incoming.ops_alerts_min_change_success_rate_pct !== undefined) incoming.ops_alerts_min_change_success_rate_pct = Number(incoming.ops_alerts_min_change_success_rate_pct) || 0;
        if (incoming.ops_alerts_max_change_failure_rate_pct !== undefined) incoming.ops_alerts_max_change_failure_rate_pct = Number(incoming.ops_alerts_max_change_failure_rate_pct) || 0;
        if (incoming.ops_alerts_max_change_rollback_p95_ms !== undefined) incoming.ops_alerts_max_change_rollback_p95_ms = Number(incoming.ops_alerts_max_change_rollback_p95_ms) || 0;
        if (incoming.ops_alerts_min_change_trace_coverage_pct !== undefined) incoming.ops_alerts_min_change_trace_coverage_pct = Number(incoming.ops_alerts_min_change_trace_coverage_pct) || 0;
        if (incoming.release_evidence_refresh_enabled !== undefined) incoming.release_evidence_refresh_enabled = truthy(incoming.release_evidence_refresh_enabled);
        if (incoming.release_evidence_refresh_include_synthetic !== undefined) incoming.release_evidence_refresh_include_synthetic = truthy(incoming.release_evidence_refresh_include_synthetic);
        if (incoming.release_evidence_refresh_include_northbound_probe !== undefined) incoming.release_evidence_refresh_include_northbound_probe = truthy(incoming.release_evidence_refresh_include_northbound_probe);
        if (incoming.intent_northbound_max_auto_publish_risk_score !== undefined) {
          const v = Number(incoming.intent_northbound_max_auto_publish_risk_score);
          incoming.intent_northbound_max_auto_publish_risk_score = Number.isFinite(v) ? Math.max(0, Math.min(100, Math.trunc(v))) : 30;
        }
        if (incoming.change_policy_template_direct_max_devices !== undefined) {
          const v = Number(incoming.change_policy_template_direct_max_devices);
          incoming.change_policy_template_direct_max_devices = Number.isFinite(v) ? Math.max(0, Math.trunc(v)) : 3;
        }
        if (incoming.change_policy_compliance_direct_max_devices !== undefined) {
          const v = Number(incoming.change_policy_compliance_direct_max_devices);
          incoming.change_policy_compliance_direct_max_devices = Number.isFinite(v) ? Math.max(0, Math.trunc(v)) : 3;
        }
        if (incoming.language !== undefined) {
          incoming.language = normalizeLanguageSetting(incoming.language);
        }
        setSettings(prev => ({ ...prev, ...incoming }));
        if (activeTab === 'general') {
          await reloadClosedLoopRulesLint();
        }
      }
    } catch (err) {
      console.error(`Failed to load ${activeTab} data:`, err);
    } finally {
      setLoading(false);
    }
  }, [activeTab, reloadClosedLoopRulesLint]);

  useEffect(() => {
    // fetchCurrentUser(); // Removed
    loadTabData();
  }, [loadTabData]);

  useEffect(() => {
    if (activeTab !== 'general') return;
    const cache = generalTabDataCacheRef.current;
    if (cache.loaded && Date.now() - cache.loadedAt < 30000) return;
    let cancelled = false;
    const run = async () => {
      try {
        setLoadingDevices(true);
        if (cancelled) return;
        const [devicesRes, sitesRes] = await Promise.all([
          DeviceService.getAll().catch(() => ({ data: [] })),
          DeviceService.getSites().catch(() => ({ data: [] })),
        ]);
        setDevices(Array.isArray(devicesRes?.data) ? devicesRes.data : []);
        setSites(Array.isArray(sitesRes?.data) ? sitesRes.data : []);
        generalTabDataCacheRef.current = { loaded: true, loadedAt: Date.now() };
      } catch (e) {
        if (!cancelled) {
          setDevices([]);
          setSites([]);
        }
      } finally {
        if (!cancelled) setLoadingDevices(false);
      }
    };
    run();
    return () => { cancelled = true; };
  }, [activeTab]);

  useEffect(() => {
    if (activeTab !== 'notifications') return;
    void loadWebhookDeliveries({ silent: true });
  }, [activeTab, loadWebhookDeliveries]);

  // Handlers
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    if (name === 'language') {
      const normalizedLanguage = normalizeLanguageSetting(value);
      setSettings(prev => ({ ...prev, language: normalizedLanguage }));
      setAppLocale(mapSettingLanguageToLocale(normalizedLanguage));
      return;
    }
    const clampRules = {
      topology_candidate_low_confidence_threshold: { min: 0, max: 1 },
      auto_approve_min_vendor_confidence: { min: 0, max: 1 },
      auto_approve_topology_depth: { min: 1, max: 10 },
      auto_discovery_max_depth: { min: 1, max: 10 },
      auto_discovery_interval_seconds: { min: 60, max: 604800 },
      auto_discovery_snmp_port: { min: 1, max: 65535 },
      auto_topology_refresh_max_depth: { min: 1, max: 10 },
      auto_topology_refresh_max_devices: { min: 1, max: 5000 },
      auto_topology_refresh_min_interval_seconds: { min: 0.01, max: 10 },
      ops_alerts_min_auto_reflection_pct: { min: 0, max: 100 },
      ops_alerts_max_false_positive_pct: { min: 0, max: 100 },
      ops_alerts_max_low_confidence_rate_pct: { min: 0, max: 100 },
      ops_alerts_max_candidate_backlog: { min: 0, max: 100000 },
      ops_alerts_max_stale_backlog_24h: { min: 0, max: 100000 },
      ops_alerts_min_closed_loop_execute_per_trigger_pct: { min: 0, max: 100 },
      ops_alerts_max_closed_loop_blocked_per_trigger_pct: { min: 0, max: 100 },
      ops_alerts_max_closed_loop_approvals_per_execution_pct: { min: 0, max: 1000 },
      ops_alerts_min_closed_loop_cycles_30d: { min: 0, max: 100000 },
      ops_alerts_min_auto_action_rate_pct: { min: 0, max: 100 },
      ops_alerts_max_operator_intervention_rate_pct: { min: 0, max: 100 },
      ops_alerts_min_change_success_rate_pct: { min: 0, max: 100 },
      ops_alerts_max_change_failure_rate_pct: { min: 0, max: 100 },
      ops_alerts_max_change_rollback_p95_ms: { min: 0, max: 600000 },
      ops_alerts_min_change_trace_coverage_pct: { min: 0, max: 100 },
      change_policy_template_direct_max_devices: { min: 0, max: 5000 },
      change_policy_compliance_direct_max_devices: { min: 0, max: 5000 },
      intent_northbound_max_auto_publish_risk_score: { min: 0, max: 100 },
      webhook_timeout_seconds: { min: 1, max: 30 },
      webhook_retry_attempts: { min: 1, max: 8 },
      webhook_retry_backoff_seconds: { min: 0, max: 60 },
      webhook_retry_max_backoff_seconds: { min: 0, max: 300 },
      webhook_retry_jitter_seconds: { min: 0, max: 10 },
    };
    if (type === 'number') {
      const n = Number(value);
      if (!Number.isFinite(n)) {
        setSettings(prev => ({ ...prev, [name]: value }));
        return;
      }
      const rule = clampRules[name];
      if (rule) {
        const clamped = Math.min(rule.max, Math.max(rule.min, n));
        setSettings(prev => ({ ...prev, [name]: clamped }));
        return;
      }
      setSettings(prev => ({ ...prev, [name]: n }));
      return;
    }
    setSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSaveSettings = async () => {
    if (saveBlockedByClosedLoopLint) {
      toast.error(t('settings_save_blocked_conflicts', 'Save blocked: Closed-loop rule conflicts detected. Resolve conflicts or disable the save guard.'));
      return;
    }
    setSaving(true);
    try {
      const payload = { ...settings };
      if (Object.prototype.hasOwnProperty.call(payload, 'capability_profile_json')) {
        const raw = String(payload.capability_profile_json ?? '').trim();
        if (!raw) {
          throw new Error(t('settings_capability_json_empty', 'Capability profile JSON cannot be empty.'));
        }
        try {
          const parsed = JSON.parse(raw);
          payload.capability_profile_json = JSON.stringify(parsed);
        } catch (_e) {
          throw new Error(t('settings_capability_json_invalid', 'Capability profile JSON is invalid. Please fix JSON syntax.'));
        }
      }
      await SettingsService.updateGeneral({ settings: payload });
      toast.success(t('settings_updated_success', 'Settings updated successfully!'));
      loadTabData();
    } catch (err) {
      toast.error(`${t('settings_update_failed', 'Failed to update settings')}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const applyAutoApprovePreset = (preset) => {
    const presets = {
      conservative: {
        auto_approve_enabled: true,
        auto_approve_min_vendor_confidence: 0.9,
        auto_approve_require_snmp_reachable: true,
        auto_approve_block_severities: 'error,warn',
        auto_approve_trigger_topology: false,
        auto_approve_topology_depth: 2,
        auto_approve_trigger_sync: false,
        auto_approve_trigger_monitoring: false,
      },
      balanced: {
        auto_approve_enabled: true,
        auto_approve_min_vendor_confidence: 0.85,
        auto_approve_require_snmp_reachable: true,
        auto_approve_block_severities: 'error',
        auto_approve_trigger_topology: true,
        auto_approve_topology_depth: 2,
        auto_approve_trigger_sync: true,
        auto_approve_trigger_monitoring: true,
      },
      aggressive: {
        auto_approve_enabled: true,
        auto_approve_min_vendor_confidence: 0.7,
        auto_approve_require_snmp_reachable: false,
        auto_approve_block_severities: 'error',
        auto_approve_trigger_topology: true,
        auto_approve_topology_depth: 3,
        auto_approve_trigger_sync: true,
        auto_approve_trigger_monitoring: true,
      },
    };
    const next = presets[String(preset || '').toLowerCase()];
    if (!next) return;
    setSettings(prev => ({ ...prev, ...next }));
    toast.success(t('settings_applied_preset_fmt', 'Applied preset: {preset}').replace('{preset}', String(preset).toUpperCase()));
  };

  const handleSaveMySecurity = async () => {
    setMySaving(true);
    try {
      await AuthService.updateMyProfile({ email: myEmail, mfa_enabled: !!myMfaEnabled });
      await refreshUser();
      toast.success(t('settings_my_account_saved', 'My account security settings were saved.'));
    } catch (err) {
      toast.error(`${t('settings_my_account_save_failed', 'Failed to save account security settings')}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setMySaving(false);
    }
  };

  const handleSendEmailVerification = async () => {
    if (emailVerifyCooldownSeconds > 0) return;
    setEmailVerifySending(true);
    try {
      const res = await AuthService.sendMyEmailVerification();
      const data = res?.data?.data || res?.data;
      setEmailVerifyChallengeId(data?.challenge_id ?? null);
      setEmailVerifyOtp('');
      setEmailVerifyCooldownSeconds(60);
      setEmailVerifyFocusSignal((x) => x + 1);
      toast.success(t('settings_verification_code_sent', 'Verification code sent to your email.'));
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail && typeof detail === 'object') {
        const retry = Number(detail.retry_after_seconds);
        if (Number.isFinite(retry) && retry > 0) {
          setEmailVerifyCooldownSeconds(Math.ceil(retry));
          setEmailVerifyFocusSignal((x) => x + 1);
          toast.info(t('settings_retry_in_seconds_fmt', 'Please retry in {seconds} seconds.').replace('{seconds}', String(Math.ceil(retry))));
        } else {
          toast.error(`${t('settings_verification_code_send_failed', 'Failed to send verification code')}: ${detail.message || err.message}`);
        }
      } else {
        toast.error(`${t('settings_verification_code_send_failed', 'Failed to send verification code')}: ${detail || err.message}`);
      }
    } finally {
      setEmailVerifySending(false);
    }
  };

  const handleVerifyEmail = async () => {
    if (!emailVerifyChallengeId) {
      toast.error(t('settings_send_verification_code_first', 'Send a verification code first.'));
      return;
    }
    setEmailVerifyVerifying(true);
    try {
      await AuthService.verifyMyEmail(emailVerifyChallengeId, emailVerifyOtp);
      await refreshUser();
      setEmailVerifyOtp('');
      toast.success(t('settings_email_verification_completed', 'Email verification completed.'));
    } catch (err) {
      toast.error(`${t('settings_email_verification_failed', 'Email verification failed')}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setEmailVerifyVerifying(false);
    }
  };

  const openLastDiscoveryJob = () => {
    const raw = String(settings.auto_discovery_last_job_id || '').trim();
    const id = Number(raw);
    if (!Number.isFinite(id) || id <= 0) return;
    navigate('/discovery', { state: { jobId: id } });
  };

  const clearAutoDiscoveryError = async () => {
    setSaving(true);
    try {
      await SettingsService.updateGeneral({ settings: { auto_discovery_last_error: '' } });
      toast.success(t('settings_last_error_cleared', 'Last error cleared.'));
      loadTabData();
    } catch (err) {
      toast.error(`${t('settings_clear_error_failed', 'Failed to clear error')}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const applyAutoDiscoveryPreset = (preset) => {
    const presets = {
      nightly: {
        auto_discovery_enabled: true,
        auto_discovery_interval_seconds: 86400,
        auto_discovery_mode: 'cidr',
        auto_discovery_cidr: '192.168.1.0/24',
        auto_discovery_seed_ip: '',
        auto_discovery_seed_device_id: '',
        auto_discovery_max_depth: 2,
        auto_discovery_snmp_version: 'v2c',
        auto_discovery_snmp_port: 161,
        auto_discovery_refresh_topology: true,
        auto_topology_refresh_max_depth: 2,
        auto_topology_refresh_max_devices: 200,
        auto_topology_refresh_min_interval_seconds: 0.05,
    topology_candidate_low_confidence_threshold: 0.7,
      },
      hourly: {
        auto_discovery_enabled: true,
        auto_discovery_interval_seconds: 3600,
        auto_discovery_mode: 'seed',
        auto_discovery_cidr: '192.168.1.0/24',
        auto_discovery_seed_ip: '',
        auto_discovery_seed_device_id: '',
        auto_discovery_max_depth: 2,
        auto_discovery_snmp_version: 'v2c',
        auto_discovery_snmp_port: 161,
        auto_discovery_refresh_topology: true,
        auto_topology_refresh_max_depth: 2,
        auto_topology_refresh_max_devices: 200,
        auto_topology_refresh_min_interval_seconds: 0.05,
    topology_candidate_low_confidence_threshold: 0.7,
      },
      lab: {
        auto_discovery_enabled: true,
        auto_discovery_interval_seconds: 300,
        auto_discovery_mode: 'seed',
        auto_discovery_cidr: '192.168.1.0/24',
        auto_discovery_seed_ip: '',
        auto_discovery_seed_device_id: '',
        auto_discovery_max_depth: 3,
        auto_discovery_snmp_version: 'v2c',
        auto_discovery_snmp_port: 161,
        auto_discovery_refresh_topology: true,
        auto_topology_refresh_max_depth: 3,
        auto_topology_refresh_max_devices: 500,
        auto_topology_refresh_min_interval_seconds: 0.02,
      },
      off: {
        auto_discovery_enabled: false,
      },
    };
    const next = presets[String(preset || '').toLowerCase()];
    if (!next) return;
    setSettings(prev => ({ ...prev, ...next }));
    toast.success(t('settings_applied_preset_fmt', 'Applied preset: {preset}').replace('{preset}', String(preset).toUpperCase()));
  };

  const handleCreateUser = async (userData) => {
    try {
      await SDNService.createUser(userData);
      toast.success(t('settings_user_created', 'User created!'));
      setShowUserModal(false);
      loadTabData();
    } catch (err) {
      toast.error(`${t('settings_user_create_failed', 'Failed to create user')}: ${err.response?.data?.detail || err.message}`);
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!window.confirm(t('settings_delete_user_confirm', 'Are you sure you want to delete this user?'))) return;
    try {
      await SDNService.deleteUser(userId);
      toast.success(t('settings_user_deleted', 'User deleted.'));
      loadTabData();
    } catch (err) {
      toast.error(`${t('settings_user_delete_failed', 'Failed to delete user')}: ${err.response?.data?.detail || err.message}`);
    }
  };

  const openAddUserModal = () => {
    setEditingUser(null);
    setShowUserModal(true);
  };

  const handleTestEmail = async () => {
    const email = window.prompt(
      t('settings_test_email_prompt', 'Enter recipient email address for testing:'),
      settings.smtp_from || '',
    );
    if (!email) return;

    setSaving(true);
    try {
      await SettingsService.sendTestEmail(email);
      toast.success(t('settings_test_email_sent_fmt', 'Test email sent to {email}.').replace('{email}', email));
    } catch (err) {
      toast.error(`${t('settings_test_email_failed', 'Failed to send email')}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleTestWebhook = async () => {
    setSaving(true);
    try {
      const res = await SettingsService.sendTestWebhookConnector({
        event_type: 'test',
        title: t('settings_test_webhook_title', '[NetSphere] Test Webhook'),
        message: t(
          'settings_test_webhook_message',
          'This is a test webhook from your SDN Controller. Notification system is working!',
        ),
      });
      const result = res?.data?.result || {};
      const mode = String(result.mode || settings.webhook_delivery_mode || 'generic');
      const attempts = Number(result.attempts || 1);
      const statusCode = result.status_code != null ? String(result.status_code) : '-';
      toast.success(
        t('settings_test_webhook_sent_fmt', 'Test webhook sent ({mode}, attempts {attempts}, HTTP {statusCode}).')
          .replace('{mode}', mode)
          .replace('{attempts}', String(attempts))
          .replace('{statusCode}', statusCode),
      );
      await loadWebhookDeliveries({ silent: true, refreshing: true });
    } catch (err) {
      toast.error(`${t('settings_test_webhook_failed', 'Failed to send webhook')}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRetryWebhookDelivery = async (deliveryId) => {
    const reason = window.prompt(
      t('settings_webhook_retry_reason_prompt', 'Optional retry reason:'),
      t('settings_webhook_retry_reason_default', 'Manual retry from Alert Channels'),
    );
    if (reason === null) return;

    setWebhookRetryingId(deliveryId);
    try {
      const res = await SettingsService.retryWebhookDelivery(deliveryId, { reason: reason || '' });
      const result = res?.data?.result || {};
      toast.success(
        t('settings_webhook_retry_success_fmt', 'Delivery retried (attempts {attempts}, HTTP {statusCode}).')
          .replace('{attempts}', String(Number(result?.attempts || 1)))
          .replace('{statusCode}', result?.status_code != null ? String(result.status_code) : '-'),
      );
      await loadWebhookDeliveries({ silent: true, refreshing: true });
    } catch (err) {
      toast.error(`${t('settings_webhook_retry_failed', 'Failed to retry delivery')}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setWebhookRetryingId(null);
    }
  };

  // const isAdmin = currentUser?.role === 'admin'; // Removed, use isAdmin() function

  return (
    <div className="flex flex-col lg:flex-row h-full min-h-0 bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white animate-fade-in overflow-hidden font-sans transition-colors duration-300">
      {/* Side Navigation */}
      <aside className="w-full lg:w-64 max-h-[42vh] lg:max-h-none bg-white dark:bg-[#1b1d1f] border-b lg:border-b-0 lg:border-r border-gray-200 dark:border-gray-800 flex flex-col flex-shrink-0">
        <div className="p-6 border-b border-gray-200 dark:border-gray-800">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <RefreshCw className={`text-blue-500 ${loading ? 'animate-spin' : ''}`} size={20} />
            {t('settings_system_control', 'System Control')}
          </h1>
          <p className="text-xs text-gray-500 mt-1">{t('settings_version_global', 'Version v2.5.0 Global')}</p>
        </div>
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto custom-scrollbar">
          <SidebarItem icon={Globe} label={t('settings_tab_general', 'General Settings')} active={activeTab === 'general'} onClick={() => setActiveTab('general')} />
          <SidebarItem icon={Users} label={t('settings_tab_users', 'User Management')} active={activeTab === 'users'} onClick={() => setActiveTab('users')} />
          <SidebarItem icon={Shield} label={t('settings_tab_security', 'Security & RBAC')} active={activeTab === 'security'} onClick={() => setActiveTab('security')} />
          <SidebarItem icon={Key} label={t('settings_tab_license', 'License Management')} active={activeTab === 'license'} onClick={() => setActiveTab('license')} />
          <SidebarItem icon={Bell} label={t('settings_tab_notifications', 'Alert Channels')} active={activeTab === 'notifications'} onClick={() => setActiveTab('notifications')} />
          <SidebarItem icon={Database} label={t('settings_tab_backup', 'System Backup')} active={activeTab === 'backup'} onClick={() => setActiveTab('backup')} />
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-h-0 flex flex-col overflow-hidden">
        <header className="h-16 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between px-3 sm:px-4 md:px-6 lg:px-8 bg-white dark:bg-[#1b1d1f] flex-shrink-0 z-10 transition-colors">
          <div>
            <h2 className="text-lg font-bold capitalize flex items-center gap-2">
              {getSettingsTabLabel(activeTab)}
              {!isAdmin() && user && (
                <span className="text-[10px] bg-red-500/10 text-red-500 px-2 py-0.5 rounded border border-red-500/20 uppercase font-black">
                  {t('settings_read_only', 'Read Only')}
                </span>
              )}
            </h2>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 sm:gap-3">
            {activeTab === 'general' && (
              <button
                type="button"
                onClick={() => reloadClosedLoopRulesLint()}
                disabled={closedLoopRulesLintLoading}
                className={`h-10 px-3 rounded-lg text-xs font-bold border transition-all ${
                  closedLoopRulesLintLoading
                    ? 'opacity-70 cursor-wait border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300'
                    : closedLoopRulesLintError
                      ? 'border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-500/20'
                      : closedLoopLintConflictsCount > 0
                        ? 'border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-500/20'
                        : closedLoopLintWarningsCount > 0
                          ? 'border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-500/20'
                          : 'border-emerald-200 dark:border-emerald-500/20 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-500/20'
                }`}
                title={t('settings_lint_refresh_title', 'Click to refresh closed-loop lint status')}
              >
                {closedLoopRulesLintLoading
                  ? t('settings_lint_checking', 'Lint: checking...')
                  : closedLoopRulesLintError
                    ? t('settings_lint_error', 'Lint: error')
                    : closedLoopLintConflictsCount > 0
                      ? t('settings_lint_conflicts_fmt', 'Lint: {count} conflicts').replace('{count}', String(closedLoopLintConflictsCount))
                      : closedLoopLintWarningsCount > 0
                        ? t('settings_lint_warnings_fmt', 'Lint: {count} warnings').replace('{count}', String(closedLoopLintWarningsCount))
                        : t('settings_lint_clean', 'Lint: clean')}
              </button>
            )}
            {activeTab !== 'users' && activeTab !== 'backup' && (
              <button
                onClick={handleSaveSettings}
                disabled={saving || !isAdmin() || saveBlockedByClosedLoopLint} // Call func
                className={`h-10 px-4 bg-blue-600 hover:bg-blue-500 text-white text-sm font-bold rounded-lg inline-flex items-center gap-2 transition-all shadow-lg shadow-blue-900/20
                  ${(saving || !isAdmin() || saveBlockedByClosedLoopLint) ? 'opacity-50 cursor-not-allowed' : ''}`}
                title={saveBlockedByClosedLoopLint ? t('settings_save_blocked_lint', 'Save is blocked by Closed-loop lint conflicts.') : undefined}
              >
                {saving ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
                {t('settings_save_changes', 'Save Changes')}
              </button>
            )}
            {activeTab === 'users' && isAdmin() && (
              <button
                onClick={openAddUserModal}
                className="h-10 px-4 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-bold rounded-lg inline-flex items-center gap-2 transition-all"
              >
                <UserPlus size={16} /> {t('settings_add_new_user', 'Add New User')}
              </button>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar bg-gray-50/50 dark:bg-[#202022]">
          <div className="max-w-4xl mx-auto space-y-12 pb-20">
            <div className="rounded-2xl border border-indigo-200 dark:border-indigo-900/40 bg-indigo-50/80 dark:bg-indigo-950/10 px-4 py-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="text-sm font-black text-indigo-900 dark:text-indigo-100">
                    {t('settings_access_title', 'Settings ownership boundary')}
                  </div>
                  <div className="mt-2 text-sm text-indigo-800 dark:text-indigo-200">
                    {settingsAccessCopy}
                  </div>
                </div>
                <div className="text-xs text-indigo-700 dark:text-indigo-300 shrink-0">
                  {t('settings_access_role_fmt', 'Current role: {role}').replace('{role}', currentRoleLabel)}
                </div>
              </div>
            </div>
            {activeTab === 'general' && previewPolicy?.preview_enabled && (
              <div className="rounded-2xl border border-amber-200 dark:border-amber-900/40 bg-amber-50/80 dark:bg-amber-950/10 px-4 py-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="text-sm font-black text-amber-900 dark:text-amber-100">
                      {t('settings_contribution_policy_title', 'Contribution policy')}
                    </div>
                    <div className="mt-2 text-sm text-amber-800 dark:text-amber-200">
                      {t(
                        'settings_contribution_policy_desc',
                        'This installation records the Free contribution policy during first-run setup. The decision stays locked unless the installation is reset or reinstalled.',
                      )}
                    </div>
                  </div>
                  <div className="text-xs text-amber-700 dark:text-amber-300 shrink-0">
                    {previewPolicy?.upload_enabled
                      ? t('settings_contribution_policy_enabled_locked', 'Enabled (locked)')
                      : previewPolicy?.upload_decision_recorded
                        ? t('settings_contribution_policy_disabled_locked', 'Disabled (locked)')
                        : t('settings_contribution_policy_pending', 'Awaiting first-run choice')}
                  </div>
                </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-3 text-xs text-amber-900 dark:text-amber-200">
                    <div className="rounded-xl border border-amber-200/70 dark:border-amber-900/50 bg-white/70 dark:bg-black/10 px-3 py-3">
                      {t('settings_contribution_policy_scope_fmt', 'Scope: {scope}').replace('{scope}', String(previewPolicy?.contribution_scope || 'allowlisted_read_only_commands_only'))}
                    </div>
                  <div className="rounded-xl border border-amber-200/70 dark:border-amber-900/50 bg-white/70 dark:bg-black/10 px-3 py-3">
                    {t('settings_contribution_policy_change_fmt', 'Change path: {value}').replace(
                      '{value}',
                      previewPolicy?.upload_change_requires_reset
                        ? t('settings_contribution_policy_reset_only', 'Reset or reinstall only')
                        : t('common_unknown', 'Unknown'),
                    )}
                  </div>
                  <div className="rounded-xl border border-amber-200/70 dark:border-amber-900/50 bg-white/70 dark:bg-black/10 px-3 py-3">
                    {t('settings_contribution_policy_actor_fmt', 'Recorded by: {value}').replace(
                      '{value}',
                      String(previewPolicy?.upload_opt_in_actor || t('common_unknown', 'Unknown')),
                      )}
                    </div>
                  </div>
                  {isAdmin() && (
                    <div className="mt-3">
                      <button
                        type="button"
                        onClick={() => navigate('/preview/contribute')}
                        className="rounded-xl border border-amber-300/80 dark:border-amber-800/70 px-3 py-2 text-xs font-semibold text-amber-900 dark:text-amber-200 hover:bg-amber-100/70 dark:hover:bg-amber-950/20"
                      >
                        {t('settings_contribution_policy_open_audit', 'Open data handling audit')}
                      </button>
                    </div>
                  )}
                </div>
              )}
            {activeTab === 'general' && (
              <GeneralSettings
                settings={settings}
                onChange={handleChange}
                disabled={!isAdmin()}
                onApplyAutoApprovePreset={applyAutoApprovePreset}
                onApplyAutoDiscoveryPreset={applyAutoDiscoveryPreset}
                devices={devices}
                sites={sites}
                loadingDevices={loadingDevices}
                onOpenLastDiscoveryJob={openLastDiscoveryJob}
                onClearAutoDiscoveryError={clearAutoDiscoveryError}
                onReloadSettings={loadTabData}
                capabilityProfileForm={capabilityProfileForm}
                onCapabilityProfileFormChange={setCapabilityProfileForm}
                capabilityProfileParseError={capabilityProfileParseError}
                closedLoopRulesLint={closedLoopRulesLint}
                closedLoopRulesLintLoading={closedLoopRulesLintLoading}
                closedLoopRulesLintError={closedLoopRulesLintError}
                onLintClosedLoopRulesDraft={lintClosedLoopRulesDraft}
                onReloadClosedLoopRulesLint={reloadClosedLoopRulesLint}
                blockSaveOnClosedLoopConflict={blockSaveOnClosedLoopConflict}
                onBlockSaveOnClosedLoopConflictChange={setBlockSaveOnClosedLoopConflict}
              />
            )}
            {activeTab === 'users' && (
              <UserManagement
                users={users}
                onDelete={handleDeleteUser}
                onAdd={openAddUserModal}
                isAdmin={isAdmin()} // Call func
              />
            )}
            {activeTab === 'security' && (
              <>
                <MyAccountSecurity
                  email={myEmail}
                  onEmailChange={setMyEmail}
                  mfaEnabled={myMfaEnabled}
                  onMfaChange={setMyMfaEnabled}
                  emailVerified={myEmailVerified}
                  onSendEmailVerification={handleSendEmailVerification}
                  emailVerifySending={emailVerifySending}
                  emailVerifyCooldownSeconds={emailVerifyCooldownSeconds}
                  emailVerifyOtpLength={emailVerifyOtpLength}
                  emailVerifyFocusSignal={emailVerifyFocusSignal}
                  emailVerifyOtp={emailVerifyOtp}
                  onEmailVerifyOtpChange={setEmailVerifyOtp}
                  onVerifyEmail={handleVerifyEmail}
                  emailVerifyVerifying={emailVerifyVerifying}
                  onRequireEmailVerification={() => toast.info(t('settings_email_verification_required', 'Email verification is required before enabling 2FA.'))}
                  mfaAvailable={!!settings.enable_2fa}
                  saving={mySaving}
                  onSave={handleSaveMySecurity}
                />
                <SecuritySettings settings={settings} onChange={handleChange} disabled={!isAdmin()} />
              </>
            )}
            {activeTab === 'notifications' && (
              <NotificationSettings
                settings={settings}
                onChange={handleChange}
                onTestEmail={handleTestEmail}
                onTestWebhook={handleTestWebhook}
                onRefreshWebhookHistory={() => loadWebhookDeliveries({ silent: false, refreshing: true })}
                onRetryWebhookDelivery={handleRetryWebhookDelivery}
                webhookDeliveries={webhookDeliveries}
                webhookHistoryLoading={webhookHistoryLoading}
                webhookHistoryRefreshing={webhookHistoryRefreshing}
                webhookRetryingId={webhookRetryingId}
                disabled={!isAdmin()}
              />
            )}
            {activeTab === 'license' && <LicenseSettings isAdmin={isAdmin()} />}
            {activeTab === 'backup' && <BackupSettings isAdmin={isAdmin()} />}
          </div>
        </div>
      </main>

      {showUserModal && (
        <UserModal
          onClose={() => setShowUserModal(false)}
          onSubmit={handleCreateUser}
          user={editingUser}
        />
      )}
    </div>
  );
};

// --- Sub-components ---

const GeneralSettings = ({
  settings,
  onChange,
  disabled,
  onApplyAutoApprovePreset,
  onApplyAutoDiscoveryPreset,
  devices,
  sites,
  loadingDevices,
  onOpenLastDiscoveryJob,
  onClearAutoDiscoveryError,
  onReloadSettings,
  capabilityProfileForm,
  onCapabilityProfileFormChange,
  capabilityProfileParseError,
  closedLoopRulesLint,
  closedLoopRulesLintLoading,
  closedLoopRulesLintError,
  onLintClosedLoopRulesDraft,
  onReloadClosedLoopRulesLint,
  blockSaveOnClosedLoopConflict,
  onBlockSaveOnClosedLoopConflictChange,
}) => (
  <>
    <Section
      title={t('settings_section_controller_identity', 'Controller Identity')}
      desc={t('settings_section_controller_identity_desc', 'Global identification and regional settings.')}
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Input label={t('settings_system_hostname', 'System Hostname')} name="hostname" value={settings.hostname} onChange={onChange} disabled={disabled} />
        <Input label={t('settings_contact_email', 'Contact Email')} name="contact_email" value={settings.contact_email} onChange={onChange} disabled={disabled} />
        <Select label={t('settings_timezone', 'Timezone')} name="timezone" value={settings.timezone} onChange={onChange} disabled={disabled} options={['UTC', 'Asia/Seoul', 'America/New_York']} />
        <Select
          label={t('settings_system_language', 'System Language')}
          name="language"
          value={settings.language}
          onChange={onChange}
          disabled={disabled}
          options={[
            { value: 'English', label: t('settings_language_english', 'English') },
            { value: 'Korean', label: t('settings_language_korean', 'Korean') },
          ]}
        />
      </div>
    </Section>

    <Section
      title={t('settings_section_auto_discovery_scope', 'Auto Discovery Scope')}
      desc={t('settings_section_auto_discovery_scope_desc', 'Control where discovery/crawl is allowed to run in production.')}
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <TextArea
          label={t('settings_discovery_include_cidrs', 'Discovery Include CIDRs')}
          name="discovery_scope_include_cidrs"
          value={settings.discovery_scope_include_cidrs}
          onChange={onChange}
          disabled={disabled}
          placeholder={t('settings_discovery_include_cidrs_placeholder', 'Example: 10.0.0.0/8, 192.168.0.0/16')}
        />
        <TextArea
          label={t('settings_discovery_exclude_cidrs', 'Discovery Exclude CIDRs')}
          name="discovery_scope_exclude_cidrs"
          value={settings.discovery_scope_exclude_cidrs}
          onChange={onChange}
          disabled={disabled}
          placeholder={t('settings_discovery_exclude_cidrs_placeholder', 'Example: 10.10.10.0/24, 10.10.20.5/32')}
        />
        <Toggle
          label={t('settings_discovery_prefer_private', 'Prefer Private IPs')}
          name="discovery_prefer_private"
          checked={!!settings.discovery_prefer_private}
          onChange={onChange}
          disabled={disabled}
          desc={t('settings_discovery_prefer_private_desc', 'Prioritize RFC1918 hosts first when scanning/crawling.')}
        />
      </div>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-8">
        <TextArea
          label={t('settings_neighbor_crawl_include_cidrs', 'Neighbor Crawl Include CIDRs')}
          name="neighbor_crawl_scope_include_cidrs"
          value={settings.neighbor_crawl_scope_include_cidrs}
          onChange={onChange}
          disabled={disabled}
          placeholder={t('settings_neighbor_crawl_include_cidrs_placeholder', 'Leave empty to use Discovery Include CIDRs')}
        />
        <TextArea
          label={t('settings_neighbor_crawl_exclude_cidrs', 'Neighbor Crawl Exclude CIDRs')}
          name="neighbor_crawl_scope_exclude_cidrs"
          value={settings.neighbor_crawl_scope_exclude_cidrs}
          onChange={onChange}
          disabled={disabled}
          placeholder={t('settings_neighbor_crawl_exclude_cidrs_placeholder', 'Leave empty to use Discovery Exclude CIDRs')}
        />
        <Toggle
          label={t('settings_neighbor_crawl_prefer_private', 'Prefer Private IPs (Crawl)')}
          name="neighbor_crawl_prefer_private"
          checked={!!settings.neighbor_crawl_prefer_private}
          onChange={onChange}
          disabled={disabled}
          desc={t('settings_neighbor_crawl_prefer_private_desc', 'Override crawl prioritization. Empty uses Discovery setting.')}
        />
      </div>
    </Section>

    <Section
      title={t('settings_auto_discovery_scheduler_title', 'Auto Discovery Scheduler')}
      desc={t('settings_auto_discovery_scheduler_desc', 'Run discovery/crawl periodically in production.')}
    >
      <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="font-black text-gray-900 dark:text-white">{t('settings_recommended_presets', 'Recommended Presets')}</div>
            <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">
              {t('settings_apply_baseline_then_save', 'Apply a baseline schedule, then Save Changes.')}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onApplyAutoDiscoveryPreset?.('nightly')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-50 dark:hover:bg-[#1b1d1f]'} bg-white dark:bg-[#15171a] border-gray-200 dark:border-gray-800`}
            >
              {t('settings_preset_nightly', 'Nightly')}
            </button>
            <button
              type="button"
              onClick={() => onApplyAutoDiscoveryPreset?.('hourly')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-blue-50 dark:hover:bg-blue-600/10'} bg-blue-600/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20`}
            >
              {t('settings_preset_hourly', 'Hourly')}
            </button>
            <button
              type="button"
              onClick={() => onApplyAutoDiscoveryPreset?.('lab')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-amber-50 dark:hover:bg-amber-500/10'} bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/20`}
            >
              {t('settings_preset_lab', 'Lab')}
            </button>
            <button
              type="button"
              onClick={() => onApplyAutoDiscoveryPreset?.('off')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-red-50 dark:hover:bg-red-500/10'} bg-red-500/10 text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/20`}
            >
              {t('settings_preset_off', 'Off')}
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Toggle
          label={t('settings_enable_auto_discovery', 'Enable Auto Discovery')}
          name="auto_discovery_enabled"
          checked={!!settings.auto_discovery_enabled}
          onChange={onChange}
          disabled={disabled}
          desc={t('settings_enable_auto_discovery_desc', 'When enabled, server will launch discovery jobs on a schedule.')}
        />
        <Input
          label={t('settings_interval_seconds', 'Interval Seconds')}
          name="auto_discovery_interval_seconds"
          type="number"
          value={settings.auto_discovery_interval_seconds}
          onChange={onChange}
          disabled={disabled}
          placeholder="1800"
        />
        <Select
          label={t('settings_mode', 'Mode')}
          name="auto_discovery_mode"
          value={settings.auto_discovery_mode}
          onChange={onChange}
          disabled={disabled}
          options={['cidr', 'seed']}
        />
        {String(settings.auto_discovery_mode || '').toLowerCase() === 'seed' && (
          <SelectRich
            label={t('settings_seed_device', 'Seed Device')}
            name="auto_discovery_seed_device_id"
            value={String(settings.auto_discovery_seed_device_id || '')}
            onChangeValue={(v) => onChange({ target: { name: 'auto_discovery_seed_device_id', value: v, type: 'text' } })}
            disabled={disabled || loadingDevices}
            options={[
              { value: '', label: loadingDevices ? t('common_loading', 'Loading...') : t('settings_none', '(none)') },
              ...(Array.isArray(devices) ? devices.map(d => ({ value: String(d.id), label: `${d.name || d.hostname || `Device ${d.id}`} (${d.ip_address})` })) : []),
            ]}
          />
        )}
        <Input
          label={t('settings_cidr_target', 'CIDR Target')}
          name="auto_discovery_cidr"
          value={settings.auto_discovery_cidr}
          onChange={onChange}
          disabled={disabled}
          placeholder="192.168.1.0/24"
        />
        <Input
          label={t('settings_seed_ip', 'Seed IP')}
          name="auto_discovery_seed_ip"
          value={settings.auto_discovery_seed_ip}
          onChange={onChange}
          disabled={disabled}
          placeholder="192.168.0.1"
        />
        {String(settings.auto_discovery_mode || '').toLowerCase() !== 'seed' && (
          <Input
            label={t('settings_seed_device_id', 'Seed Device ID')}
            name="auto_discovery_seed_device_id"
            value={settings.auto_discovery_seed_device_id}
            onChange={onChange}
            disabled={disabled}
            placeholder={t('settings_optional', '(optional)')}
          />
        )}
        <Input
          label={t('settings_max_depth_seed', 'Max Depth (Seed)')}
          name="auto_discovery_max_depth"
          type="number"
          value={settings.auto_discovery_max_depth}
          onChange={onChange}
          disabled={disabled}
          placeholder="2"
        />
        <Select
          label={t('settings_snmp_version', 'SNMP Version')}
          name="auto_discovery_snmp_version"
          value={settings.auto_discovery_snmp_version}
          onChange={onChange}
          disabled={disabled}
          options={['v2c', 'v3', 'v1']}
        />
        <Input
          label={t('settings_snmp_port', 'SNMP Port')}
          name="auto_discovery_snmp_port"
          type="number"
          value={settings.auto_discovery_snmp_port}
          onChange={onChange}
          disabled={disabled}
          placeholder="161"
        />
        <Input
          label={t('settings_site_id', 'Site ID')}
          name="auto_discovery_site_id"
          value={settings.auto_discovery_site_id}
          onChange={onChange}
          disabled={disabled}
          placeholder={t('settings_optional', '(optional)')}
        />
        <Input
          label={t('settings_snmp_profile_id', 'SNMP Profile ID')}
          name="auto_discovery_snmp_profile_id"
          value={settings.auto_discovery_snmp_profile_id}
          onChange={onChange}
          disabled={disabled}
          placeholder={t('settings_optional', '(optional)')}
        />
      </div>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-8">
        <Toggle
          label={t('settings_refresh_topology_after', 'Refresh Topology After')}
          name="auto_discovery_refresh_topology"
          checked={!!settings.auto_discovery_refresh_topology}
          onChange={onChange}
          disabled={disabled}
          desc={t('settings_refresh_topology_after_desc', 'After starting an auto discovery job, enqueue topology refresh tasks.')}
        />
        <Input
          label={t('settings_topology_max_depth', 'Topology Max Depth')}
          name="auto_topology_refresh_max_depth"
          type="number"
          value={settings.auto_topology_refresh_max_depth}
          onChange={onChange}
          disabled={disabled}
          placeholder="2"
        />
        <Input
          label={t('settings_topology_max_devices', 'Topology Max Devices')}
          name="auto_topology_refresh_max_devices"
          type="number"
          value={settings.auto_topology_refresh_max_devices}
          onChange={onChange}
          disabled={disabled}
          placeholder="200"
        />
        <Input
          label={t('settings_topology_min_interval', 'Topology Min Interval')}
          name="auto_topology_refresh_min_interval_seconds"
          type="number"
          value={settings.auto_topology_refresh_min_interval_seconds}
          onChange={onChange}
          disabled={disabled}
          placeholder="0.05"
        />
        <Input
          label={t('settings_low_confidence_threshold', 'Low-Confidence Threshold')}
          name="topology_candidate_low_confidence_threshold"
          type="number"
          value={settings.topology_candidate_low_confidence_threshold}
          onChange={onChange}
          disabled={disabled}
          placeholder="0.7"
          min={0}
          max={1}
          step={0.01}
          hint={t('settings_range_0_1', 'Range: 0.00 to 1.00')}
        />
      </div>

      <div className="mt-8 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="font-black text-gray-900 dark:text-white">{t('settings_automation_status', 'Automation Status')}</div>
            <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">{t('settings_automation_status_desc', 'Read-only runtime info.')}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onReloadSettings?.()}
              className="px-3 py-1.5 rounded-xl text-xs font-black border transition-all bg-white dark:bg-[#15171a] border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-[#1b1d1f]"
            >
              {t('common_refresh', 'Refresh')}
            </button>
            <button
              type="button"
              onClick={() => onOpenLastDiscoveryJob?.()}
              disabled={!settings.auto_discovery_last_job_id}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${!settings.auto_discovery_last_job_id ? 'opacity-60 cursor-not-allowed' : 'hover:bg-blue-50 dark:hover:bg-blue-600/10'} bg-blue-600/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20`}
            >
              {t('settings_open_job', 'Open Job')}
            </button>
            <button
              type="button"
              onClick={() => onClearAutoDiscoveryError?.()}
              disabled={!settings.auto_discovery_last_error || disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${(!settings.auto_discovery_last_error || disabled) ? 'opacity-60 cursor-not-allowed' : 'hover:bg-red-50 dark:hover:bg-red-500/10'} bg-red-500/10 text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/20`}
            >
              {t('settings_clear_error', 'Clear Error')}
            </button>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <StatusItem label={t('settings_status_last_run_at', 'Last Run At')} value={settings.auto_discovery_last_run_at || t('settings_never', '(never)')} />
          <StatusItem label={t('settings_status_last_job_id', 'Last Job ID')} value={settings.auto_discovery_last_job_id || t('settings_none', '(none)')} />
          <StatusItem label={t('settings_status_last_job_cidr', 'Last Job CIDR')} value={settings.auto_discovery_last_job_cidr || t('settings_none', '(none)')} />
          <StatusItem label={t('settings_status_last_error', 'Last Error')} value={settings.auto_discovery_last_error || t('settings_none', '(none)')} />
        </div>

        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <StatusItem label={t('settings_status_topo_last_run_at', 'Topo Last Run At')} value={settings.auto_topology_last_run_at || t('settings_never', '(never)')} />
          <StatusItem label={t('settings_status_topo_last_job_id', 'Topo Last Job ID')} value={settings.auto_topology_last_job_id || t('settings_none', '(none)')} />
          <StatusItem label={t('settings_status_topo_targets', 'Topo Targets')} value={settings.auto_topology_last_targets || t('settings_none', '(none)')} />
          <StatusItem label={t('settings_status_topo_enqueue_ok', 'Topo Enqueue OK')} value={settings.auto_topology_last_enqueued_ok || t('settings_none', '(none)')} />
          <StatusItem label={t('settings_status_topo_enqueue_fail', 'Topo Enqueue Fail')} value={settings.auto_topology_last_enqueued_fail || t('settings_none', '(none)')} />
          <StatusItem label={t('settings_status_topo_last_error', 'Topo Last Error')} value={settings.auto_topology_last_error || t('settings_none', '(none)')} />
        </div>
      </div>
    </Section>

    <Section
      title={t('settings_capability_profile_policy_title', 'Capability Profile Policy')}
      desc={t('settings_capability_profile_policy_desc', 'Policy by site/device group: allowed protocols, auto reflection scope, read-only mode.')}
    >
      <CapabilityProfilePolicyEditor
        profile={capabilityProfileForm}
        onChange={onCapabilityProfileFormChange}
        disabled={disabled}
        parseError={capabilityProfileParseError}
        devices={devices}
        sites={sites}
      />
    </Section>

    <Section
      title={t('settings_auto_approve_policy_title', 'Auto Approve Policy')}
      desc={t('settings_auto_approve_policy_desc', 'Safely auto-approve only high-confidence discoveries.')}
    >
      <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="font-black text-gray-900 dark:text-white">{t('settings_recommended_presets', 'Recommended Presets')}</div>
            <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">
              {t('settings_apply_safe_baseline_then_save', 'Apply a safe baseline, then Save Changes.')}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onApplyAutoApprovePreset?.('conservative')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-50 dark:hover:bg-[#1b1d1f]'} bg-white dark:bg-[#15171a] border-gray-200 dark:border-gray-800`}
            >
              {t('settings_preset_conservative', 'Conservative')}
            </button>
            <button
              type="button"
              onClick={() => onApplyAutoApprovePreset?.('balanced')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-blue-50 dark:hover:bg-blue-600/10'} bg-blue-600/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20`}
            >
              {t('settings_preset_balanced', 'Balanced')}
            </button>
            <button
              type="button"
              onClick={() => onApplyAutoApprovePreset?.('aggressive')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-amber-50 dark:hover:bg-amber-500/10'} bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/20`}
            >
              {t('settings_preset_aggressive', 'Aggressive')}
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Toggle
          label={t('settings_enable_auto_approve', 'Enable Auto Approve')}
          name="auto_approve_enabled"
          checked={!!settings.auto_approve_enabled}
          onChange={onChange}
          disabled={disabled}
          desc={t('settings_enable_auto_approve_desc', 'When enabled, newly discovered devices may be auto-approved after scan/crawl completes.')}
        />
        <Input
          label={t('settings_min_vendor_confidence', 'Min Vendor Confidence')}
          name="auto_approve_min_vendor_confidence"
          type="number"
          value={settings.auto_approve_min_vendor_confidence}
          onChange={onChange}
          disabled={disabled}
          placeholder="0.8"
          min={0}
          max={1}
          step={0.01}
          hint={t('settings_range_0_1', 'Range: 0.00 to 1.00')}
        />
        <Toggle
          label={t('settings_require_snmp_reachable', 'Require SNMP Reachable')}
          name="auto_approve_require_snmp_reachable"
          checked={!!settings.auto_approve_require_snmp_reachable}
          onChange={onChange}
          disabled={disabled}
          desc={t('settings_require_snmp_reachable_desc', 'Only auto-approve when SNMP is reachable.')}
        />
        <Input
          label={t('settings_block_severities', 'Block Severities')}
          name="auto_approve_block_severities"
          value={settings.auto_approve_block_severities}
          onChange={onChange}
          disabled={disabled}
          placeholder={t('settings_block_severities_placeholder', 'error')}
        />
      </div>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-8">
        <Toggle
          label={t('settings_trigger_topology_refresh', 'Trigger Topology Refresh')}
          name="auto_approve_trigger_topology"
          checked={!!settings.auto_approve_trigger_topology}
          onChange={onChange}
          disabled={disabled}
          desc={t('settings_trigger_topology_refresh_desc', 'After auto-approve, enqueue topology refresh for approved devices.')}
        />
        <Input
          label={t('settings_topology_depth', 'Topology Depth')}
          name="auto_approve_topology_depth"
          type="number"
          value={settings.auto_approve_topology_depth}
          onChange={onChange}
          disabled={disabled}
          placeholder="2"
        />
        <Toggle
          label={t('settings_trigger_ssh_sync', 'Trigger SSH Sync')}
          name="auto_approve_trigger_sync"
          checked={!!settings.auto_approve_trigger_sync}
          onChange={onChange}
          disabled={disabled}
          desc={t('settings_trigger_ssh_sync_desc', 'After auto-approve, enqueue SSH sync jobs (uses Auto Sync settings).')}
        />
        <Toggle
          label={t('settings_trigger_monitoring_burst', 'Trigger Monitoring Burst')}
          name="auto_approve_trigger_monitoring"
          checked={!!settings.auto_approve_trigger_monitoring}
          onChange={onChange}
          disabled={disabled}
          desc={t('settings_trigger_monitoring_burst_desc', 'After auto-approve, run a short monitoring burst to fill traffic state.')}
        />
      </div>

      <div className="mt-8 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
        <div className="font-black text-gray-900 dark:text-white">{t('settings_smart_deploy_policy_title', 'Smart Deploy Policy')}</div>
        <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">
          {t('settings_smart_deploy_policy_desc', 'Policy that decides whether deploy goes direct or approval-first.')}
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-8">
          <Input
            label="Template Direct Max Devices"
            name="change_policy_template_direct_max_devices"
            type="number"
            value={settings.change_policy_template_direct_max_devices}
            onChange={onChange}
            disabled={disabled}
            placeholder="3"
            min={0}
            step={1}
            hint="0 means all template deploys require approval."
          />
          <Input
            label="Compliance Direct Max Devices"
            name="change_policy_compliance_direct_max_devices"
            type="number"
            value={settings.change_policy_compliance_direct_max_devices}
            onChange={onChange}
            disabled={disabled}
            placeholder="3"
            min={0}
            step={1}
            hint="0 means all config drift remediation requests require approval."
          />
          <Toggle
            label="Fabric Live Requires Approval"
            name="change_policy_fabric_live_requires_approval"
            checked={!!settings.change_policy_fabric_live_requires_approval}
            onChange={onChange}
            disabled={disabled}
            desc="When enabled, non-dry-run Fabric deploy must go through approval."
          />
          <Toggle
            label={t('settings_cloud_bootstrap_live_requires_approval', 'Cloud Bootstrap Live Requires Approval')}
            name="change_policy_cloud_bootstrap_live_requires_approval"
            checked={!!settings.change_policy_cloud_bootstrap_live_requires_approval}
            onChange={onChange}
            disabled={disabled}
            desc={t('settings_cloud_bootstrap_live_requires_approval_desc', 'When enabled, non-dry-run Cloud Bootstrap must go through approval.')}
          />
          <Toggle
            label="Intent Apply Direct Actions"
            name="intent_apply_execute_actions"
            checked={!!settings.intent_apply_execute_actions}
            onChange={onChange}
            disabled={disabled}
            desc="Allow Intent apply to execute metadata.execution_actions directly (OFF keeps persist-only)."
          />
          <Toggle
            label="Intent Northbound Risk Gate"
            name="intent_northbound_policy_enabled"
            checked={!!settings.intent_northbound_policy_enabled}
            onChange={onChange}
            disabled={disabled}
            desc="When enabled, risky/conflicting intent simulation result gates webhook publish behind approval."
          />
          <Input
            label="Intent Northbound Auto Risk Max"
            name="intent_northbound_max_auto_publish_risk_score"
            type="number"
            value={settings.intent_northbound_max_auto_publish_risk_score}
            onChange={onChange}
            disabled={disabled}
            min={0}
            max={100}
            step={1}
            hint="0..100. Above this risk score, webhook publish switches to approval-gated mode."
          />
          <Toggle
            label="Closed-loop Direct Change Actions"
            name="closed_loop_execute_change_actions"
            checked={!!settings.closed_loop_execute_change_actions}
            onChange={onChange}
            disabled={disabled}
            desc="Allow closed-loop rules to execute run_scan/template_Netsphere_Free_Deploy/cloud_bootstrap/intent_apply directly (OFF keeps approval-first)."
          />
          <div className="md:col-span-2">
            <TextArea
              label="Closed-loop Rules JSON"
              name="closed_loop_rules_json"
              value={settings.closed_loop_rules_json}
              onChange={onChange}
              disabled={disabled}
              placeholder={'[{"id":"rule-cpu-high","enabled":true,"source":"any","condition":{"path":"summary.cpu_avg","operator":">=","value":80},"action":{"type":"notify","title":"CPU High","message":"CPU threshold reached","payload":{}}},{"id":"rule-cloud-bootstrap","enabled":false,"source":"any","condition":{"path":"summary.cpu_avg","operator":">=","value":90},"action":{"type":"cloud_bootstrap","title":"Cloud Bootstrap","message":"Bootstrap cloud VM targets","payload":{"account_ids":[101],"dry_run":true}}},{"id":"rule-intent-cloud-policy","enabled":false,"source":"any","condition":{"path":"summary.cpu_avg","operator":">=","value":92},"action":{"type":"intent_apply","title":"Cloud Policy Intent","message":"Apply cloud policy intent","payload":{"intent_type":"cloud_policy","name":"auto-cloud-policy","dry_run":true,"spec":{"targets":{"providers":["aws"]},"required_tags":[{"key":"owner"}]}}}}]'}
            />
            <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-500">
              Save persists this JSON. Use lint buttons below to validate conflict/warning before rollout.
            </div>
          </div>
        </div>

        <ClosedLoopRulesLintPanel
          lint={closedLoopRulesLint}
          loading={closedLoopRulesLintLoading}
          error={closedLoopRulesLintError}
          disabled={disabled}
          onLintDraft={onLintClosedLoopRulesDraft}
          onReloadSaved={onReloadClosedLoopRulesLint}
          blockSaveOnConflict={blockSaveOnClosedLoopConflict}
          onBlockSaveOnConflictChange={onBlockSaveOnClosedLoopConflictChange}
        />
      </div>

      <div className="mt-8 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
        <div className="font-black text-gray-900 dark:text-white">{t('settings_release_evidence_automation_title', 'Release Evidence Automation')}</div>
        <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">
          {t('settings_release_evidence_automation_desc', 'Schedule automatic release evidence refresh after the daily KPI snapshot run.')}
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-8">
          <Toggle
            label={t('settings_release_evidence_enable', 'Enable Scheduled Refresh')}
            name="release_evidence_refresh_enabled"
            checked={!!settings.release_evidence_refresh_enabled}
            onChange={onChange}
            disabled={disabled}
            desc={t('settings_release_evidence_enable_desc', 'Runs once a day through Celery Beat. Manual refresh remains available from the dashboard.')}
          />
          <Select
            label={t('settings_release_evidence_profile', 'Refresh Profile')}
            name="release_evidence_refresh_profile"
            value={settings.release_evidence_refresh_profile}
            onChange={onChange}
            disabled={disabled}
            options={['ci', 'local', 'release']}
          />
          <Toggle
            label={t('settings_release_evidence_include_synthetic', 'Include Synthetic Validation')}
            name="release_evidence_refresh_include_synthetic"
            checked={!!settings.release_evidence_refresh_include_synthetic}
            onChange={onChange}
            disabled={disabled}
            desc={t('settings_release_evidence_include_synthetic_desc', 'When disabled, the scheduler rebuilds the release evidence cache from the latest available reports only.')}
          />
          <Toggle
            label={t('settings_release_evidence_include_northbound_probe', 'Include Northbound Probe')}
            name="release_evidence_refresh_include_northbound_probe"
            checked={!!settings.release_evidence_refresh_include_northbound_probe}
            onChange={onChange}
            disabled={disabled}
            desc={t('settings_release_evidence_include_northbound_probe_desc', 'Runs a short self-contained northbound probe during scheduled refresh when automation auth is configured. This does not replace 72-hour soak acceptance evidence.')}
          />
          <div className="rounded-2xl border border-dashed border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#111315] px-4 py-3 text-xs text-gray-600 dark:text-gray-400">
            {t('settings_release_evidence_schedule_note', 'Fixed schedule: daily 04:30 Asia/Seoul, after the 04:15 KPI readiness snapshot.')}
          </div>
        </div>
      </div>

      <div className="mt-8 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
        <div className="font-black text-gray-900 dark:text-white">{t('settings_operational_alerts_title', 'Operational Alerts Thresholds')}</div>
        <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">
          {t('settings_operational_alerts_desc', 'Discovery KPI / Candidate Queue + Closed-loop KPI alert thresholds.')}
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-8">
          <Input
            label="Min Auto Reflection (%)"
            name="ops_alerts_min_auto_reflection_pct"
            type="number"
            value={settings.ops_alerts_min_auto_reflection_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="70"
            min={0}
            max={100}
            step={0.1}
            hint="Range: 0 to 100"
          />
          <Input
            label="Max False Positive (%)"
            name="ops_alerts_max_false_positive_pct"
            type="number"
            value={settings.ops_alerts_max_false_positive_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="20"
            min={0}
            max={100}
            step={0.1}
            hint="Range: 0 to 100"
          />
          <Input
            label="Max Low Confidence Rate (%)"
            name="ops_alerts_max_low_confidence_rate_pct"
            type="number"
            value={settings.ops_alerts_max_low_confidence_rate_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="30"
            min={0}
            max={100}
            step={0.1}
            hint="Range: 0 to 100"
          />
          <Input
            label="Max Candidate Backlog"
            name="ops_alerts_max_candidate_backlog"
            type="number"
            value={settings.ops_alerts_max_candidate_backlog}
            onChange={onChange}
            disabled={disabled}
            placeholder="100"
            min={0}
            step={1}
            hint="Range: 0 to 100000"
          />
          <Input
            label="Max Stale Backlog (24h)"
            name="ops_alerts_max_stale_backlog_24h"
            type="number"
            value={settings.ops_alerts_max_stale_backlog_24h}
            onChange={onChange}
            disabled={disabled}
            placeholder="20"
            min={0}
            step={1}
            hint="Range: 0 to 100000"
          />
          <Input
            label="Min Closed-loop Execute/Trigger (%)"
            name="ops_alerts_min_closed_loop_execute_per_trigger_pct"
            type="number"
            value={settings.ops_alerts_min_closed_loop_execute_per_trigger_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="30"
            min={0}
            max={100}
            step={0.1}
            hint="Range: 0 to 100"
          />
          <Input
            label="Max Closed-loop Blocked/Trigger (%)"
            name="ops_alerts_max_closed_loop_blocked_per_trigger_pct"
            type="number"
            value={settings.ops_alerts_max_closed_loop_blocked_per_trigger_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="70"
            min={0}
            max={100}
            step={0.1}
            hint="Range: 0 to 100"
          />
          <Input
            label="Max Closed-loop Approvals/Execution (%)"
            name="ops_alerts_max_closed_loop_approvals_per_execution_pct"
            type="number"
            value={settings.ops_alerts_max_closed_loop_approvals_per_execution_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="100"
            min={0}
            max={1000}
            step={0.1}
            hint="Range: 0 to 1000"
          />
          <Input
            label="Min Closed-loop Cycles (30d)"
            name="ops_alerts_min_closed_loop_cycles_30d"
            type="number"
            value={settings.ops_alerts_min_closed_loop_cycles_30d}
            onChange={onChange}
            disabled={disabled}
            placeholder="1"
            min={0}
            step={1}
            hint="Range: 0 to 100000"
          />
          <Input
            label="Min Auto Action Rate (%)"
            name="ops_alerts_min_auto_action_rate_pct"
            type="number"
            value={settings.ops_alerts_min_auto_action_rate_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="60"
            min={0}
            max={100}
            step={0.1}
            hint="Range: 0 to 100"
          />
          <Input
            label="Max Operator Intervention Rate (%)"
            name="ops_alerts_max_operator_intervention_rate_pct"
            type="number"
            value={settings.ops_alerts_max_operator_intervention_rate_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="40"
            min={0}
            max={100}
            step={0.1}
            hint="Range: 0 to 100"
          />
          <Input
            label="Min Change Success Rate (%)"
            name="ops_alerts_min_change_success_rate_pct"
            type="number"
            value={settings.ops_alerts_min_change_success_rate_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="98"
            min={0}
            max={100}
            step={0.1}
            hint="Range: 0 to 100"
          />
          <Input
            label="Max Change Failure Rate (%)"
            name="ops_alerts_max_change_failure_rate_pct"
            type="number"
            value={settings.ops_alerts_max_change_failure_rate_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="1"
            min={0}
            max={100}
            step={0.1}
            hint="Range: 0 to 100"
          />
          <Input
            label="Max Change Rollback P95 (ms)"
            name="ops_alerts_max_change_rollback_p95_ms"
            type="number"
            value={settings.ops_alerts_max_change_rollback_p95_ms}
            onChange={onChange}
            disabled={disabled}
            placeholder="180000"
            min={0}
            max={600000}
            step={100}
            hint="Range: 0 to 600000"
          />
          <Input
            label="Min Change Trace Coverage (%)"
            name="ops_alerts_min_change_trace_coverage_pct"
            type="number"
            value={settings.ops_alerts_min_change_trace_coverage_pct}
            onChange={onChange}
            disabled={disabled}
            placeholder="100"
            min={0}
            max={100}
            step={0.1}
            hint="Range: 0 to 100"
          />
        </div>
      </div>
    </Section>
  </>
);

const CapabilityProfilePolicyEditor = ({ profile, onChange, disabled, parseError, devices, sites }) => {
  const safeProfile = profile || {
    default: createCapabilityLayer(DEFAULT_CAPABILITY_PROFILE.default),
    sites: [],
    device_types: [],
  };
  const defaultLayer = createCapabilityLayer(safeProfile.default);
  const siteOverrides = Array.isArray(safeProfile.sites) ? safeProfile.sites : [];
  const deviceTypeOverrides = Array.isArray(safeProfile.device_types) ? safeProfile.device_types : [];
  const siteKeySuggestions = useMemo(() => {
    const map = new Map();
    (Array.isArray(sites) ? sites : []).forEach((site) => {
      const key = String(site?.id ?? '').trim();
      if (!key) return;
      const label = String(site?.name || site?.code || `Site ${key}`).trim();
      if (!map.has(key)) map.set(key, label);
    });
    (Array.isArray(devices) ? devices : []).forEach((device) => {
      const raw = device?.site_id;
      if (raw == null || raw === '') return;
      const key = String(raw).trim();
      if (!key) return;
      const label = String(device?.site_name || device?.site || `Site ${key}`).trim();
      if (!map.has(key)) map.set(key, label);
    });
    return Array.from(map.entries())
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => {
        const an = Number(a.value);
        const bn = Number(b.value);
        if (Number.isFinite(an) && Number.isFinite(bn)) return an - bn;
        return String(a.value).localeCompare(String(b.value));
      });
  }, [sites, devices]);
  const deviceTypeSuggestions = useMemo(() => {
    const set = new Set();
    (Array.isArray(devices) ? devices : []).forEach((device) => {
      const key = String(device?.device_type || '').trim().toLowerCase();
      if (key) set.add(key);
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [devices]);
  const siteListId = 'capability-site-key-suggestions';
  const deviceTypeListId = 'capability-device-type-suggestions';

  const mutateProfile = (updater) => {
    if (typeof onChange !== 'function') return;
    onChange((prev) => {
      const base = prev || safeProfile;
      return updater(base);
    });
  };

  const updateDefaultLayer = (nextLayer) => {
    mutateProfile((prev) => ({
      ...prev,
      default: createCapabilityLayer(nextLayer),
    }));
  };

  const addSiteOverride = () => {
    mutateProfile((prev) => ({
      ...prev,
      sites: [...(Array.isArray(prev.sites) ? prev.sites : []), createCapabilityOverrideRow('', {}, prev.default)],
    }));
  };

  const addDeviceTypeOverride = () => {
    mutateProfile((prev) => ({
      ...prev,
      device_types: [...(Array.isArray(prev.device_types) ? prev.device_types : []), createCapabilityOverrideRow('', {}, prev.default)],
    }));
  };

  const updateSiteRow = (rowId, patch) => {
    mutateProfile((prev) => ({
      ...prev,
      sites: (Array.isArray(prev.sites) ? prev.sites : []).map((row) => {
        if (row.id !== rowId) return row;
        const nextLayer = patch.layer ? createCapabilityLayer(patch.layer, prev.default) : createCapabilityLayer(row.layer, prev.default);
        return {
          ...row,
          ...patch,
          key: patch.key !== undefined ? String(patch.key || '').trim() : row.key,
          layer: nextLayer,
        };
      }),
    }));
  };

  const updateDeviceTypeRow = (rowId, patch) => {
    mutateProfile((prev) => ({
      ...prev,
      device_types: (Array.isArray(prev.device_types) ? prev.device_types : []).map((row) => {
        if (row.id !== rowId) return row;
        const nextLayer = patch.layer ? createCapabilityLayer(patch.layer, prev.default) : createCapabilityLayer(row.layer, prev.default);
        return {
          ...row,
          ...patch,
          key: patch.key !== undefined ? String(patch.key || '').trim().toLowerCase() : row.key,
          layer: nextLayer,
        };
      }),
    }));
  };

  const removeSiteRow = (rowId) => {
    mutateProfile((prev) => ({
      ...prev,
      sites: (Array.isArray(prev.sites) ? prev.sites : []).filter((row) => row.id !== rowId),
    }));
  };

  const removeDeviceTypeRow = (rowId) => {
    mutateProfile((prev) => ({
      ...prev,
      device_types: (Array.isArray(prev.device_types) ? prev.device_types : []).filter((row) => row.id !== rowId),
    }));
  };

  return (
    <div className="space-y-5">
      {parseError && (
        <div className="px-4 py-3 rounded-xl border border-amber-300 bg-amber-50 text-amber-800 text-xs font-semibold">
          {t('settings_capability_json_invalid_structure', 'Stored capability JSON had invalid structure. A safe default profile was loaded into this form.')}
        </div>
      )}
      <datalist id={siteListId}>
        {siteKeySuggestions.map((item) => (
          <option key={item.value} value={item.value} label={item.label} />
        ))}
      </datalist>
      <datalist id={deviceTypeListId}>
        {deviceTypeSuggestions.map((item) => (
          <option key={item} value={item} />
        ))}
      </datalist>

      <CapabilityLayerEditor
        title={t('settings_default_policy', 'Default Policy')}
        desc={t('settings_default_policy_desc', 'Baseline policy for all sites and device types.')}
        layer={defaultLayer}
        onLayerChange={updateDefaultLayer}
        disabled={disabled}
      />

      <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-4">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <div className="text-sm font-black text-gray-900 dark:text-white">{t('settings_site_overrides', 'Site Overrides')}</div>
            <div className="text-[11px] text-gray-600 dark:text-gray-500">{t('settings_site_overrides_desc', 'Override default policy for specific site IDs.')}</div>
          </div>
          <button
            type="button"
            onClick={addSiteOverride}
            disabled={disabled}
            className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-blue-50 dark:hover:bg-blue-600/10'} bg-blue-600/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20`}
          >
            + {t('settings_add_site_override', 'Add Site Override')}
          </button>
        </div>
        {siteOverrides.length === 0 ? (
          <div className="text-xs text-gray-500">{t('settings_no_site_overrides', 'No site overrides.')}</div>
        ) : (
          <div className="space-y-3">
            {siteOverrides.map((row) => (
              <div key={row.id} className="rounded-xl border border-gray-200 dark:border-gray-800 p-3 bg-gray-50/60 dark:bg-[#111214]">
                <div className="flex items-end gap-2 mb-3">
                  <div className="flex-1">
                    <Input
                      label={t('settings_site_id', 'Site ID')}
                      value={row.key}
                      onChange={(e) => updateSiteRow(row.id, { key: e.target.value })}
                      disabled={disabled}
                      placeholder={t('settings_site_id_placeholder', 'e.g. 10')}
                      list={siteListId}
                      hint={
                        siteKeySuggestions.length > 0
                          ? `${t('settings_suggestions', 'Suggestions')}: ${siteKeySuggestions.slice(0, 12).map((x) => x.value).join(', ')}${siteKeySuggestions.length > 12 ? ' ...' : ''}`
                          : t('settings_no_registered_sites_yet', 'No registered sites found yet.')
                      }
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => removeSiteRow(row.id)}
                    disabled={disabled}
                    className={`px-3 py-2 rounded-lg text-xs font-bold border ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-red-50 dark:hover:bg-red-500/10'} border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-400`}
                  >
                    {t('settings_remove', 'Remove')}
                  </button>
                </div>
                <CapabilityLayerEditor
                  title={null}
                  desc={null}
                  layer={createCapabilityLayer(row.layer, defaultLayer)}
                  onLayerChange={(layer) => updateSiteRow(row.id, { layer })}
                  disabled={disabled}
                  compact
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-4">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <div className="text-sm font-black text-gray-900 dark:text-white">{t('settings_device_type_overrides', 'Device Type Overrides')}</div>
            <div className="text-[11px] text-gray-600 dark:text-gray-500">{t('settings_device_type_overrides_desc', 'Override default policy by `device_type` (lower-case).')}</div>
          </div>
          <button
            type="button"
            onClick={addDeviceTypeOverride}
            disabled={disabled}
            className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-blue-50 dark:hover:bg-blue-600/10'} bg-blue-600/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20`}
          >
            + {t('settings_add_device_type_override', 'Add Device Type Override')}
          </button>
        </div>
        {deviceTypeOverrides.length === 0 ? (
          <div className="text-xs text-gray-500">{t('settings_no_device_type_overrides', 'No device type overrides.')}</div>
        ) : (
          <div className="space-y-3">
            {deviceTypeOverrides.map((row) => (
              <div key={row.id} className="rounded-xl border border-gray-200 dark:border-gray-800 p-3 bg-gray-50/60 dark:bg-[#111214]">
                <div className="flex items-end gap-2 mb-3">
                  <div className="flex-1">
                    <Input
                      label={t('settings_device_type', 'Device Type')}
                      value={row.key}
                      onChange={(e) => updateDeviceTypeRow(row.id, { key: e.target.value })}
                      disabled={disabled}
                      placeholder={t('settings_device_type_placeholder', 'e.g. cisco_ios')}
                      list={deviceTypeListId}
                      hint={
                        deviceTypeSuggestions.length > 0
                          ? `${t('settings_suggestions', 'Suggestions')}: ${deviceTypeSuggestions.slice(0, 12).join(', ')}${deviceTypeSuggestions.length > 12 ? ' ...' : ''}`
                          : t('settings_no_registered_device_types_yet', 'No registered device types found yet.')
                      }
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => removeDeviceTypeRow(row.id)}
                    disabled={disabled}
                    className={`px-3 py-2 rounded-lg text-xs font-bold border ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-red-50 dark:hover:bg-red-500/10'} border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-400`}
                  >
                    {t('settings_remove', 'Remove')}
                  </button>
                </div>
                <CapabilityLayerEditor
                  title={null}
                  desc={null}
                  layer={createCapabilityLayer(row.layer, defaultLayer)}
                  onLayerChange={(layer) => updateDeviceTypeRow(row.id, { layer })}
                  disabled={disabled}
                  compact
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const CapabilityLayerEditor = ({ title, desc, layer, onLayerChange, disabled, compact = false }) => {
  const safeLayer = createCapabilityLayer(layer);
  const setProtocol = (protocol, checked) => {
    const current = Array.isArray(safeLayer.allowed_protocols) ? safeLayer.allowed_protocols : [];
    const nextSet = new Set(current);
    if (checked) nextSet.add(protocol);
    else nextSet.delete(protocol);
    onLayerChange({
      ...safeLayer,
      allowed_protocols: normalizeProtocols(Array.from(nextSet), CAPABILITY_PROTOCOL_OPTIONS),
    });
  };

  const setAutoField = (field, checked) => {
    onLayerChange({
      ...safeLayer,
      auto_reflection: {
        ...safeLayer.auto_reflection,
        [field]: !!checked,
      },
    });
  };

  return (
    <div className={`rounded-xl border border-gray-200 dark:border-gray-800 ${compact ? 'p-3' : 'p-4'} bg-white dark:bg-[#15171a]`}>
      {title && <div className="text-sm font-black text-gray-900 dark:text-white">{title}</div>}
      {desc && <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">{desc}</div>}

      <div className={`${compact ? 'mt-2' : 'mt-3'}`}>
        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{t('settings_allowed_protocols', 'Allowed Protocols')}</div>
        <div className="mt-2 flex flex-wrap gap-2">
          {CAPABILITY_PROTOCOL_OPTIONS.map((protocol) => (
            <label
              key={protocol}
              className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-semibold ${disabled ? 'opacity-60' : ''} border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#111214] text-gray-700 dark:text-gray-300`}
            >
              <input
                type="checkbox"
                checked={safeLayer.allowed_protocols.includes(protocol)}
                onChange={(e) => setProtocol(protocol, e.target.checked)}
                disabled={disabled}
                className="accent-blue-600"
              />
              {protocol.toUpperCase()}
            </label>
          ))}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2">
        <label className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-semibold border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#111214] ${disabled ? 'opacity-60' : ''}`}>
          <input
            type="checkbox"
            checked={!!safeLayer.auto_reflection.approval}
            onChange={(e) => setAutoField('approval', e.target.checked)}
            disabled={disabled}
            className="accent-blue-600"
          />
          {t('settings_auto_approval', 'Auto Approval')}
        </label>
        <label className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-semibold border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#111214] ${disabled ? 'opacity-60' : ''}`}>
          <input
            type="checkbox"
            checked={!!safeLayer.auto_reflection.topology}
            onChange={(e) => setAutoField('topology', e.target.checked)}
            disabled={disabled}
            className="accent-blue-600"
          />
          {t('settings_auto_topology', 'Auto Topology')}
        </label>
        <label className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-semibold border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#111214] ${disabled ? 'opacity-60' : ''}`}>
          <input
            type="checkbox"
            checked={!!safeLayer.auto_reflection.sync}
            onChange={(e) => setAutoField('sync', e.target.checked)}
            disabled={disabled}
            className="accent-blue-600"
          />
          {t('settings_auto_sync', 'Auto Sync')}
        </label>
        <label className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-semibold border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#111214] ${disabled ? 'opacity-60' : ''}`}>
          <input
            type="checkbox"
            checked={!!safeLayer.read_only}
            onChange={(e) => onLayerChange({ ...safeLayer, read_only: e.target.checked })}
            disabled={disabled}
            className="accent-blue-600"
          />
          {t('settings_read_only', 'Read Only')}
        </label>
      </div>
    </div>
  );
};

const ClosedLoopRulesLintPanel = ({
  lint,
  loading,
  error,
  disabled,
  onLintDraft,
  onReloadSaved,
  blockSaveOnConflict,
  onBlockSaveOnConflictChange,
}) => {
  const safeLint = lint && typeof lint === 'object' ? lint : {};
  const rulesTotal = Number(safeLint.rules_total || 0);
  const rulesEnabled = Number(safeLint.rules_enabled || 0);
  const conflictsCount = Number(safeLint.conflicts_count || 0);
  const warningsCount = Number(safeLint.warnings_count || 0);
  const conflicts = Array.isArray(safeLint.conflicts) ? safeLint.conflicts : [];
  const warnings = Array.isArray(safeLint.warnings) ? safeLint.warnings : [];
  const topConflicts = conflicts.slice(0, 3);
  const topWarnings = warnings.slice(0, 3);

  return (
    <div className="mt-6 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111214] p-4">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <div className="text-sm font-black text-gray-900 dark:text-white">{t('settings_closed_loop_rules_lint', 'Closed-loop Rules Lint')}</div>
          <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">
            {t('settings_closed_loop_rules_lint_desc', 'Validate `closed_loop_rules_json` for conflicting actions before rollout.')}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onLintDraft?.()}
            disabled={disabled || loading}
            className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled || loading ? 'opacity-60 cursor-not-allowed' : 'hover:bg-blue-50 dark:hover:bg-blue-600/10'} bg-blue-600/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20`}
          >
            {t('settings_lint_draft_json', 'Lint Draft JSON')}
          </button>
          <button
            type="button"
            onClick={() => onReloadSaved?.()}
            disabled={disabled || loading}
            className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled || loading ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-50 dark:hover:bg-[#1b1d1f]'} bg-white dark:bg-[#15171a] border-gray-200 dark:border-gray-800`}
          >
            {t('settings_reload_saved_lint', 'Reload Saved Lint')}
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <LintStat label={t('settings_rules', 'Rules')} value={rulesTotal} tone="slate" />
        <LintStat label={t('settings_enabled', 'Enabled')} value={rulesEnabled} tone="slate" />
        <LintStat label={t('settings_conflicts', 'Conflicts')} value={conflictsCount} tone={conflictsCount > 0 ? 'red' : 'green'} />
        <LintStat label={t('settings_warnings', 'Warnings')} value={warningsCount} tone={warningsCount > 0 ? 'amber' : 'green'} />
      </div>

      <label className={`mt-3 inline-flex items-center gap-2 text-xs font-semibold px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#15171a] ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}>
        <input
          type="checkbox"
          checked={!!blockSaveOnConflict}
          onChange={(e) => onBlockSaveOnConflictChange?.(!!e.target.checked)}
          disabled={disabled}
          className="accent-blue-600"
        />
        {t('settings_block_save_on_conflicts', 'Block Save on Conflicts')}
      </label>

      {error ? (
        <div className="mt-3 px-3 py-2 rounded-lg border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/10 text-[11px] text-red-700 dark:text-red-300 font-semibold">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="mt-3 text-xs text-gray-500">{t('settings_running_lint', 'Running lint...')}</div>
      ) : (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          <LintList title={t('settings_top_conflicts', 'Top Conflicts')} rows={topConflicts} emptyText={t('settings_no_conflicts', 'No conflicts.')} tone="red" />
          <LintList title={t('settings_top_warnings', 'Top Warnings')} rows={topWarnings} emptyText={t('settings_no_warnings', 'No warnings.')} tone="amber" />
        </div>
      )}
    </div>
  );
};

const LintStat = ({ label, value, tone = 'slate' }) => {
  const toneClass =
    tone === 'red'
      ? 'border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-300'
      : tone === 'amber'
        ? 'border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300'
        : tone === 'green'
          ? 'border-emerald-200 dark:border-emerald-500/20 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
          : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-[#15171a] text-gray-700 dark:text-gray-300';
  return (
    <div className={`rounded-lg border px-3 py-2 ${toneClass}`}>
      <div className="text-[10px] uppercase tracking-wider font-black opacity-80">{label}</div>
      <div className="text-sm font-black mt-0.5">{value}</div>
    </div>
  );
};

const LintList = ({ title, rows, emptyText, tone = 'slate' }) => {
  const safeRows = Array.isArray(rows) ? rows : [];
  const itemTone =
    tone === 'red'
      ? 'border-red-200 dark:border-red-500/20 bg-red-50/70 dark:bg-red-500/10'
      : tone === 'amber'
        ? 'border-amber-200 dark:border-amber-500/20 bg-amber-50/70 dark:bg-amber-500/10'
        : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-[#15171a]';
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#15171a] p-3">
      <div className="text-[11px] font-black text-gray-700 dark:text-gray-300 uppercase tracking-wider">{title}</div>
      {safeRows.length === 0 ? (
        <div className="mt-2 text-xs text-gray-500">{emptyText}</div>
      ) : (
        <div className="mt-2 space-y-2">
          {safeRows.map((row, idx) => {
            const ruleIds = Array.isArray(row?.rule_ids) ? row.rule_ids.filter(Boolean) : [];
            return (
              <div key={`${title}-${idx}`} className={`rounded-lg border p-2 ${itemTone}`}>
                <div className="text-[11px] font-bold text-gray-800 dark:text-gray-200">
                  {String(row?.type || 'rule_lint')}
                </div>
                <div className="mt-0.5 text-[11px] text-gray-700 dark:text-gray-300">
                  {String(row?.message || 'Potential rule conflict detected.')}
                </div>
                {ruleIds.length > 0 && (
                  <div className="mt-1 text-[10px] text-gray-600 dark:text-gray-400">
                    Rule IDs: {ruleIds.join(', ')}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

const UserManagement = ({ users, onDelete, onAdd, isAdmin }) => (
  <Section title={t('settings_user_directory_title', 'User Directory')} desc={t('settings_user_directory_desc', 'View and manage system access. (RBAC Enabled)')}>
    <div className="flex justify-end mb-4">
      {isAdmin && (
        <button onClick={onAdd} className="bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-2 transition-all">
          <Plus size={14} /> {t('settings_add_user', 'Add User')}
        </button>
      )}
    </div>
    <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl overflow-x-auto shadow-sm dark:shadow-xl">
      <table className="min-w-[640px] w-full text-left text-sm">
        <thead className="bg-gray-50 dark:bg-[#1b1d1f] text-gray-500 dark:text-gray-400 font-bold border-b border-gray-200 dark:border-gray-800">
          <tr>
            <th className="px-6 py-4">{t('settings_identity', 'Identity')}</th>
            <th className="px-6 py-4">{t('settings_role', 'Role')}</th>
            <th className="px-6 py-4">{t('settings_status', 'Status')}</th>
            <th className="px-6 py-4 text-right">{t('settings_actions', 'Actions')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {users.length === 0 ? (
            <tr><td colSpan="4" className="px-6 py-10 text-center text-gray-500 italic">{t('settings_no_users_or_loading', 'No users found or loading...')}</td></tr>
          ) : users.map(u => (
            <tr key={u.id} className="hover:bg-gray-50 dark:hover:bg-[#1b1d1f] transition-colors group text-gray-700 dark:text-gray-300">
              <td className="px-6 py-4">
                <div className="font-bold text-gray-900 dark:text-gray-200">{u.username}</div>
                <div className="text-[11px] text-gray-600 dark:text-gray-500">{u.full_name || t('settings_not_available', 'N/A')} · {u.email}</div>
              </td>
              <td className="px-6 py-4">
                <span className={`px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider border 
                  ${u.role === 'admin' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                    u.role === 'operator' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                      'bg-gray-500/10 text-gray-600 dark:text-gray-400 border-gray-500/20'}`}>
                  {u.role === 'admin' ? t('role_admin', 'Administrator') : u.role === 'operator' ? t('role_operator', 'Operator') : t('role_viewer', 'Viewer')}
                </span>
              </td>
              <td className="px-6 py-4">
                <div className={`flex items-center gap-2 ${u.is_active ? 'text-emerald-500' : 'text-gray-500'}`}>
                  <div className={`w-1.5 h-1.5 rounded-full ${u.is_active ? 'bg-emerald-500 animate-pulse' : 'bg-gray-500'}`} />
                  {u.is_active ? t('settings_active', 'Active') : t('settings_disabled', 'Disabled')}
                </div>
              </td>
              <td className="px-6 py-4 text-right">
                <div className="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  {isAdmin && u.username !== 'admin' && (
                    <button onClick={() => onDelete(u.id)} className="p-2 hover:bg-red-100 dark:hover:bg-red-500/10 text-gray-500 hover:text-red-600 dark:hover:text-red-500 rounded-lg transition-all" title={t('settings_delete_user', 'Delete User')}>
                      <Trash2 size={16} />
                    </button>
                  )}
                  <button className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 hover:text-gray-900 dark:hover:text-white rounded-lg transition-all">
                    <MoreHorizontal size={16} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </Section>
);

const SecuritySettings = ({ settings, onChange, disabled }) => (
  <Section title={t('settings_auth_security_title', 'Auth Security')} desc={t('settings_auth_security_desc', 'Hardening session and authentication parameters.')}>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
      <Input label="Session Timeout (m)" name="session_timeout" type="number" value={settings.session_timeout} onChange={onChange} disabled={disabled} />
      <Input label="Max Retries" name="max_login_attempts" type="number" value={settings.max_login_attempts} onChange={onChange} disabled={disabled} />
      <Input label="Lockout Window (m)" name="lockout_minutes" type="number" value={settings.lockout_minutes} onChange={onChange} disabled={disabled} />

      <div className="md:col-span-2 flex items-center justify-between p-5 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-blue-500/10 rounded-xl text-blue-500">
            <Shield size={24} />
          </div>
          <div>
            <div className="font-bold text-gray-900 dark:text-white">{t('settings_mfa_title', 'Multi-Factor Authentication (MFA)')}</div>
            <div className="text-xs text-gray-500">{t('settings_mfa_desc', 'Enable optional 2FA feature. Each user can opt-in later.')}</div>
          </div>
        </div>
        <label className="relative inline-flex items-center cursor-pointer">
          <input type="checkbox" name="enable_2fa" checked={settings.enable_2fa} onChange={onChange} disabled={disabled} className="sr-only peer" />
          <div className="w-12 h-6 bg-gray-700 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
        </label>
      </div>

      <div className="md:col-span-2">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Input label="Password Min Length" name="password_min_length" type="number" value={settings.password_min_length} onChange={onChange} disabled={disabled} />
          <Input label="Required Classes (1-4)" name="password_required_classes" type="number" value={settings.password_required_classes} onChange={onChange} disabled={disabled} />
          <Input label="Password History Count" name="password_history_count" type="number" value={settings.password_history_count} onChange={onChange} disabled={disabled} />
          <Input label="Password Expire Days (0=off)" name="password_expire_days" type="number" value={settings.password_expire_days} onChange={onChange} disabled={disabled} />
          <Toggle
            label="Forbid Username in Password"
            name="password_forbid_username"
            checked={settings.password_forbid_username}
            onChange={onChange}
            disabled={disabled}
            desc="Reject passwords that contain the username."
          />
        </div>
      </div>

      <div className="md:col-span-2">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Toggle
            label="Audit Hash Chain"
            name="audit_chain_enabled"
            checked={settings.audit_chain_enabled}
            onChange={onChange}
            disabled={disabled}
            desc="Store tamper-evident HMAC chain fields in audit logs."
          />
          <Input
            label="Audit HMAC Key"
            name="audit_hmac_key"
            type="password"
            value={settings.audit_hmac_key}
            onChange={onChange}
            disabled={disabled}
            placeholder={t('settings_audit_hmac_key_placeholder', '(optional) override SECRET_KEY')}
          />
          <Toggle
            label="Audit Syslog Forwarding"
            name="audit_forward_syslog_enabled"
            checked={settings.audit_forward_syslog_enabled}
            onChange={onChange}
            disabled={disabled}
            desc="Forward audit events to a remote Syslog server (UDP)."
          />
          <Input
            label="Syslog Host"
            name="audit_forward_syslog_host"
            value={settings.audit_forward_syslog_host}
            onChange={onChange}
            disabled={disabled}
            placeholder={t('settings_syslog_host_placeholder', 'e.g. 10.0.0.10')}
          />
          <Input label="Syslog Port" name="audit_forward_syslog_port" type="number" value={settings.audit_forward_syslog_port} onChange={onChange} disabled={disabled} />
        </div>
      </div>

      <div className="md:col-span-2">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Toggle
            label="PII Masking"
            name="pii_masking_enabled"
            checked={!!settings.pii_masking_enabled}
            onChange={onChange}
            disabled={disabled}
            desc="Mask IP/MAC/Phone/Email in UI logs and API responses."
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Toggle label="Mask IP" name="pii_mask_ip" checked={!!settings.pii_mask_ip} onChange={onChange} disabled={disabled || !settings.pii_masking_enabled} />
            <Toggle label="Mask MAC" name="pii_mask_mac" checked={!!settings.pii_mask_mac} onChange={onChange} disabled={disabled || !settings.pii_masking_enabled} />
            <Toggle label="Mask Phone" name="pii_mask_phone" checked={!!settings.pii_mask_phone} onChange={onChange} disabled={disabled || !settings.pii_masking_enabled} />
            <Toggle label="Mask Email" name="pii_mask_email" checked={!!settings.pii_mask_email} onChange={onChange} disabled={disabled || !settings.pii_masking_enabled} />
          </div>
        </div>
      </div>
    </div>
  </Section>
);

const NotificationSettings = ({
  settings,
  onChange,
  onTestEmail,
  onTestWebhook,
  onRefreshWebhookHistory,
  onRetryWebhookDelivery,
  webhookDeliveries,
  webhookHistoryLoading,
  webhookHistoryRefreshing,
  webhookRetryingId,
  disabled,
}) => {
  const receiverGuides = {
    generic: {
      title: t('settings_webhook_mode_generic_title', 'Generic HTTP Receiver'),
      summary: t('settings_webhook_mode_generic_summary', 'Use this for custom receivers, Teams/Slack relays, or internal event gateways.'),
      checks: [
        t('settings_webhook_mode_generic_check_1', 'Provide a reachable HTTPS endpoint.'),
        t('settings_webhook_mode_generic_check_2', 'Expect signed JSON payloads and verify the optional webhook secret if enabled.'),
        t('settings_webhook_mode_generic_check_3', 'Use the recent delivery history below to confirm retries and failure causes.'),
      ],
    },
    jira: {
      title: t('settings_webhook_mode_jira_title', 'Jira Issue Creation'),
      summary: t('settings_webhook_mode_jira_summary', 'Publish operational issues into Jira with the selected project key and issue type.'),
      checks: [
        t('settings_webhook_mode_jira_check_1', 'Set the Jira REST endpoint and bearer token.'),
        t('settings_webhook_mode_jira_check_2', 'Confirm the project key and issue type are valid for the target workspace.'),
        t('settings_webhook_mode_jira_check_3', 'Run a test delivery and verify the created issue from recent deliveries.'),
      ],
    },
    servicenow: {
      title: t('settings_webhook_mode_servicenow_title', 'ServiceNow Record Delivery'),
      summary: t('settings_webhook_mode_servicenow_summary', 'Create or update records in ServiceNow tables such as incident or change_request.'),
      checks: [
        t('settings_webhook_mode_servicenow_check_1', 'Point the webhook URL to the ServiceNow Table API endpoint.'),
        t('settings_webhook_mode_servicenow_check_2', 'Set the target table and authentication token before testing.'),
        t('settings_webhook_mode_servicenow_check_3', 'Use delivery history to spot schema errors or permission failures.'),
      ],
    },
    splunk: {
      title: t('settings_webhook_mode_splunk_title', 'Splunk HEC Receiver'),
      summary: t('settings_webhook_mode_splunk_summary', 'Send operational events to Splunk via HEC with retry and jitter policy.'),
      checks: [
        t('settings_webhook_mode_splunk_check_1', 'Use the Splunk HEC URL and HEC token.'),
        t('settings_webhook_mode_splunk_check_2', 'Confirm the target index and source type in Splunk.'),
        t('settings_webhook_mode_splunk_check_3', 'Review recent deliveries for 4xx/5xx failures and replay when needed.'),
      ],
    },
    elastic: {
      title: t('settings_webhook_mode_elastic_title', 'Elastic / OpenSearch Ingest'),
      summary: t('settings_webhook_mode_elastic_summary', 'Push normalized operational events into an Elastic-compatible index for correlation and search.'),
      checks: [
        t('settings_webhook_mode_elastic_check_1', 'Set the ingest endpoint and index name.'),
        t('settings_webhook_mode_elastic_check_2', 'Use a token with index write permission.'),
        t('settings_webhook_mode_elastic_check_3', 'Replay failed deliveries after fixing mapping or permission errors.'),
      ],
    },
  };
  const activeGuide = receiverGuides[String(settings.webhook_delivery_mode || 'generic')] || receiverGuides.generic;

  return (
    <Section title={t('settings_alert_channels_title', 'Alert Channels')} desc={t('settings_alert_channels_desc', 'SMTP and Webhook notification delivery configuration.')}>
      <div className="space-y-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-2">
            <Input
              label="SMTP Server"
              name="smtp_host"
              value={settings.smtp_host}
              onChange={onChange}
              disabled={disabled}
              placeholder={t('settings_smtp_server_placeholder', 'e.g. smtp.gmail.com')}
            />
          </div>
          <Input label="Port" name="smtp_port" type="number" value={settings.smtp_port} onChange={onChange} disabled={disabled} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Input label="Username" name="smtp_user" value={settings.smtp_user} onChange={onChange} disabled={disabled} />
          <Input label="Password" name="smtp_password" type="password" value={settings.smtp_password} onChange={onChange} disabled={disabled} />
        </div>
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <Input
              label="Sender Address (From)"
              name="smtp_from"
              value={settings.smtp_from}
              onChange={onChange}
              disabled={disabled}
              placeholder={t('settings_sender_address_placeholder', 'netsphere@domain.com')}
            />
          </div>
          <button
            onClick={onTestEmail}
            disabled={disabled}
            className="px-4 py-3 bg-gray-800 hover:bg-gray-700 text-gray-200 rounded-xl transition-colors font-bold text-sm border border-gray-700 h-[50px] flex items-center gap-2"
          >
            <Mail size={16} /> {t('settings_test_email', 'Test Email')}
          </button>
        </div>

        <div className="border-t border-gray-200 dark:border-gray-800 pt-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Toggle
              label="Webhook Enabled"
              name="webhook_enabled"
              checked={settings.webhook_enabled}
              onChange={onChange}
              disabled={disabled}
              desc="Send JSON payloads to external receivers for ticketing, SIEM, and operational workflows."
            />
            <Input label="Webhook Timeout (s)" name="webhook_timeout_seconds" type="number" value={settings.webhook_timeout_seconds} onChange={onChange} disabled={disabled} />
            <Select
              label="Delivery Mode"
              name="webhook_delivery_mode"
              value={settings.webhook_delivery_mode || 'generic'}
              onChange={onChange}
              disabled={disabled}
              options={['generic', 'servicenow', 'jira', 'splunk', 'elastic']}
            />
            <Select
              label="Auth Type"
              name="webhook_auth_type"
              value={settings.webhook_auth_type || 'none'}
              onChange={onChange}
              disabled={disabled}
              options={['none', 'bearer', 'splunk_hec', 'custom']}
            />
            <div className="md:col-span-2">
              <Input
                label="Webhook URL"
                name="webhook_url"
                value={settings.webhook_url}
                onChange={onChange}
                disabled={disabled}
                placeholder={t('settings_webhook_url_placeholder', 'https://hooks.slack.com/services/...')}
              />
            </div>
            {settings.webhook_delivery_mode === 'jira' && (
              <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-6">
                <Input
                  label="Jira Project Key"
                  name="webhook_jira_project_key"
                  value={settings.webhook_jira_project_key || ''}
                  onChange={onChange}
                  disabled={disabled}
                  placeholder={t('settings_webhook_jira_project_key_placeholder', 'NET')}
                />
                <Input
                  label="Jira Issue Type"
                  name="webhook_jira_issue_type"
                  value={settings.webhook_jira_issue_type || 'Task'}
                  onChange={onChange}
                  disabled={disabled}
                  placeholder={t('settings_webhook_jira_issue_type_placeholder', 'Task')}
                />
              </div>
            )}
            {settings.webhook_delivery_mode === 'servicenow' && (
              <div className="md:col-span-2">
                <Input
                  label="ServiceNow Table"
                  name="webhook_servicenow_table"
                  value={settings.webhook_servicenow_table || 'incident'}
                  onChange={onChange}
                  disabled={disabled}
                  placeholder={t('settings_webhook_servicenow_table_placeholder', 'incident')}
                />
              </div>
            )}
            {settings.webhook_delivery_mode === 'elastic' && (
              <div className="md:col-span-2">
                <Input
                  label="Elastic Index"
                  name="webhook_elastic_index"
                  value={settings.webhook_elastic_index || 'netsphere-events'}
                  onChange={onChange}
                  disabled={disabled}
                  placeholder={t('settings_webhook_elastic_index_placeholder', 'netsphere-events')}
                />
              </div>
            )}
            {settings.webhook_auth_type !== 'none' && (
              <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-6">
                <Input
                  label="Auth Token"
                  name="webhook_auth_token"
                  type="password"
                  value={settings.webhook_auth_token}
                  onChange={onChange}
                  disabled={disabled}
                  placeholder={t('settings_webhook_auth_token_placeholder', 'API token / bearer token')}
                />
                {settings.webhook_auth_type === 'custom' ? (
                  <Input
                    label="Custom Header Name"
                    name="webhook_auth_header_name"
                    value={settings.webhook_auth_header_name}
                    onChange={onChange}
                    disabled={disabled}
                    placeholder={t('settings_webhook_auth_header_name_placeholder', 'Authorization')}
                  />
                ) : (
                  <div className="flex flex-col gap-2">
                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{t('settings_header_name_read_only', 'Header Name (read only)')}</label>
                    <div className="w-full bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      {settings.webhook_auth_type === 'splunk_hec'
                        ? t('settings_auth_header_splunk', 'Authorization (Splunk <token>)')
                        : t('settings_auth_header_bearer', 'Authorization (Bearer <token>)')}
                    </div>
                  </div>
                )}
              </div>
            )}
            <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-4 gap-6">
              <Input label="Retry Attempts" name="webhook_retry_attempts" type="number" value={settings.webhook_retry_attempts} onChange={onChange} disabled={disabled} />
              <Input label="Backoff Base (s)" name="webhook_retry_backoff_seconds" type="number" step="0.1" value={settings.webhook_retry_backoff_seconds} onChange={onChange} disabled={disabled} />
              <Input label="Backoff Max (s)" name="webhook_retry_max_backoff_seconds" type="number" step="0.1" value={settings.webhook_retry_max_backoff_seconds} onChange={onChange} disabled={disabled} />
              <Input label="Jitter (s)" name="webhook_retry_jitter_seconds" type="number" step="0.1" value={settings.webhook_retry_jitter_seconds} onChange={onChange} disabled={disabled} />
            </div>
            <div className="md:col-span-2">
              <Toggle
                label="Retry On 4xx"
                name="webhook_retry_on_4xx"
                checked={!!settings.webhook_retry_on_4xx}
                onChange={onChange}
                disabled={disabled}
                desc="By default only timeout/429/5xx responses are retried."
              />
            </div>
            <div className="md:col-span-2 flex gap-4 items-end">
              <div className="flex-1">
                <Input
                  label="Webhook Secret (optional)"
                  name="webhook_secret"
                  type="password"
                  value={settings.webhook_secret}
                  onChange={onChange}
                  disabled={disabled}
                  placeholder={t('settings_webhook_secret_placeholder', 'Used for X-NetManager-Signature and X-NetManager-Signature-V2')}
                />
              </div>
              <button
                onClick={onTestWebhook}
                disabled={disabled}
                className="px-4 py-3 bg-gray-800 hover:bg-gray-700 text-gray-200 rounded-xl transition-colors font-bold text-sm border border-gray-700 h-[50px] flex items-center gap-2"
              >
                <Bell size={16} /> {t('settings_test_webhook', 'Test Webhook')}
              </button>
            </div>
          </div>

          <div className="rounded-2xl border border-blue-200/70 dark:border-blue-500/20 bg-blue-50/70 dark:bg-blue-500/5 p-5">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <div className="text-[11px] font-black uppercase tracking-[0.25em] text-blue-600 dark:text-blue-300">
                  {t('settings_webhook_receiver_setup', 'Receiver Setup')}
                </div>
                <h3 className="mt-2 text-lg font-bold text-gray-900 dark:text-gray-100">{activeGuide.title}</h3>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300 max-w-3xl">{activeGuide.summary}</p>
              </div>
              <div className="text-xs text-blue-700 dark:text-blue-300 font-semibold">
                {t('settings_webhook_receiver_flow', 'Configure -> Test -> Verify -> Retry')}
              </div>
            </div>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
              {activeGuide.checks.map((item) => (
                <div
                  key={item}
                  className="rounded-xl border border-blue-200/80 dark:border-blue-500/20 bg-white/80 dark:bg-[#0f1113] px-4 py-3 text-sm text-gray-700 dark:text-gray-200"
                >
                  {item}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#17191c]">
            <div className="flex items-center justify-between gap-3 p-5 border-b border-gray-200 dark:border-gray-800">
              <div>
                <div className="text-[11px] font-black uppercase tracking-[0.25em] text-gray-500">
                  {t('settings_webhook_delivery_history', 'Delivery History')}
                </div>
                <h3 className="mt-2 text-lg font-bold text-gray-900 dark:text-gray-100">
                  {t('settings_webhook_delivery_history_title', 'Recent northbound deliveries')}
                </h3>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                  {t('settings_webhook_delivery_history_desc', 'Inspect recent northbound webhook results, identify failure causes, and replay supported deliveries.')}
                </p>
              </div>
              <button
                type="button"
                onClick={onRefreshWebhookHistory}
                disabled={webhookHistoryRefreshing}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 dark:bg-black/20 dark:hover:bg-black/30 border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-800 dark:text-gray-100 disabled:opacity-50"
              >
                <RefreshCw size={14} className={webhookHistoryRefreshing ? 'animate-spin' : ''} />
                {webhookHistoryRefreshing ? t('common_refreshing', 'Refreshing...') : t('common_refresh', 'Refresh')}
              </button>
            </div>

            <div className="p-5">
              {webhookHistoryLoading ? (
                <div className="text-sm text-gray-500 dark:text-gray-400">{t('common_loading', 'Loading...')}</div>
              ) : webhookDeliveries.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('settings_webhook_delivery_empty', 'No webhook deliveries recorded yet. Send a test webhook to populate recent history.')}
                </div>
              ) : (
                <div className="space-y-3">
                  {webhookDeliveries.map((delivery) => {
                    const target = [delivery.target_host, delivery.target_path].filter(Boolean).join('');
                    const timestamp = delivery.timestamp ? new Date(delivery.timestamp).toLocaleString() : '-';
                    return (
                      <div
                        key={`${delivery.delivery_id}-${delivery.event_log_id}`}
                        className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#0f1113] px-4 py-4"
                      >
                        <div className="flex items-start justify-between gap-4 flex-wrap">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-bold ${getOperationalStatusBadgeClass(delivery.status)}`}>
                                {getOperationalStatusLabel(delivery.status)}
                              </span>
                              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300">
                                {String(delivery.mode || 'generic')}
                              </span>
                              <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                                {String(delivery.event_type || 'event')}
                              </span>
                            </div>
                            <div className="mt-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
                              {delivery.title || t('settings_webhook_delivery_title_fallback', 'Webhook delivery')}
                            </div>
                            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              {getOperationalStatusHint(delivery.status)}
                            </div>
                            <div className="mt-2 text-xs text-gray-600 dark:text-gray-400 space-y-1">
                              <div>{t('settings_webhook_delivery_target_fmt', 'Target: {value}').replace('{value}', target || '-')}</div>
                              <div>{t('settings_webhook_delivery_attempts_fmt', 'Attempts: {value}').replace('{value}', String(Number(delivery.attempts || 0)))}</div>
                              <div>{t('settings_webhook_delivery_time_fmt', 'Timestamp: {value}').replace('{value}', timestamp)}</div>
                              {delivery.status_code != null && (
                                <div>{t('settings_webhook_delivery_status_code_fmt', 'HTTP: {value}').replace('{value}', String(delivery.status_code))}</div>
                              )}
                              {delivery.failure_cause && (
                                <div>{t('settings_webhook_delivery_failure_fmt', 'Failure cause: {value}').replace('{value}', delivery.failure_cause)}</div>
                              )}
                              {delivery.error && (
                                <div className="text-rose-600 dark:text-rose-300">
                                  {t('settings_webhook_delivery_error_fmt', 'Error: {value}').replace('{value}', delivery.error)}
                                </div>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {delivery.replay_available && (
                              <button
                                type="button"
                                onClick={() => onRetryWebhookDelivery(delivery.delivery_id)}
                                disabled={disabled || webhookRetryingId === delivery.delivery_id}
                                className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 border border-blue-500 text-sm font-medium text-white disabled:opacity-50"
                              >
                                <RefreshCw size={14} className={webhookRetryingId === delivery.delivery_id ? 'animate-spin' : ''} />
                                {webhookRetryingId === delivery.delivery_id
                                  ? t('settings_webhook_retrying', 'Retrying...')
                                  : t('settings_webhook_retry_delivery', 'Retry Delivery')}
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </Section>
  );
};

const BackupSettings = ({ isAdmin }) => {
  const { toast } = useToast();
  const [restoring, setRestoring] = useState(false);
  const restoreInputRef = useRef(null);

  const downloadSupportBundle = async () => {
    try {
      const res = await SupportService.bundle({ days: 7, limit_per_table: 5000, include_app_log: true });
      const blob = new Blob([res.data], { type: 'application/zip' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `support_bundle_${new Date().toISOString().replace(/[:.]/g, '-')}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success(t('settings_support_bundle_downloaded', 'Support bundle downloaded'));
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message || t('settings_support_bundle_download_failed', 'Failed to download bundle'));
    }
  };

  const handleRestorePick = () => {
    if (!isAdmin || restoring) return;
    if (restoreInputRef.current) {
      restoreInputRef.current.value = '';
      restoreInputRef.current.click();
    }
  };

  const handleRestoreSelected = async (evt) => {
    const file = evt?.target?.files?.[0];
    if (!file || !isAdmin || restoring) return;

    const name = String(file.name || '').toLowerCase();
    if (!name.endsWith('.zip')) {
      toast.warning(t('settings_restore_zip_required', 'Please select a .zip bundle file.'));
      return;
    }

    setRestoring(true);
    try {
      const res = await SupportService.restore(file, { apply: true, restoreSettings: true });
      const body = res?.data || {};
      const restored = Number(body?.restored?.settings || 0);
      const skipped = Number(body?.skipped?.settings || 0);
      toast.success(
        t('settings_restore_applied_fmt', 'Restore applied: settings {restored}, skipped {skipped}')
          .replace('{restored}', String(restored))
          .replace('{skipped}', String(skipped))
      );
      window.location.reload();
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message || t('settings_restore_failed', 'Restore failed'));
    } finally {
      setRestoring(false);
      if (restoreInputRef.current) restoreInputRef.current.value = '';
    }
  };

  return (
    <Section title={t('settings_maintenance_support_title', 'Maintenance & Support')} desc={t('settings_maintenance_support_desc', 'System diagnostics and disaster recovery.')}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <BackupCard title={t('settings_support_bundle_title', 'Tech Support Bundle')} icon={Download} color="blue" onClick={() => isAdmin && !restoring && downloadSupportBundle()} active={isAdmin && !restoring} />
        <BackupCard title={t('settings_restore_environment_title', 'Restore Environment')} icon={Upload} color="emerald" onClick={handleRestorePick} active={isAdmin && !restoring} />
        <input
          ref={restoreInputRef}
          type="file"
          accept=".zip,application/zip"
          className="hidden"
          onChange={handleRestoreSelected}
        />
      </div>
    </Section>
  );
};

const LicenseSettings = ({ isAdmin }) => {
  const { toast } = useToast();
  const [licenseData, setLicenseData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [newKey, setNewKey] = useState("");
  const [savingKey, setSavingKey] = useState(false);

  const fetchLicense = async () => {
    try {
      const res = await LicenseService.status();
      setLicenseData(res.data || null);
    } catch (e) {
      setLicenseData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchLicense(); }, []);

  const handleUpload = async () => {
    if (!newKey) return toast.warning(t('settings_license_key_required', 'Please enter a license key.'));
    setSavingKey(true);
    try {
      await LicenseService.install(newKey);
      setNewKey('');
      toast.success(t('settings_license_installed', 'License key installed'));
      fetchLicense();
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message || t('settings_license_install_failed', 'Failed to install license'));
    } finally {
      setSavingKey(false);
    }
  };

  const handleUninstall = async () => {
    setSavingKey(true);
    try {
      await LicenseService.uninstall();
      toast.success(t('settings_license_uninstalled', 'License uninstalled'));
      fetchLicense();
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message || t('settings_license_uninstall_failed', 'Failed to uninstall license'));
    } finally {
      setSavingKey(false);
    }
  };

  const isActive = String(licenseData?.status || '').toLowerCase().includes('active') || licenseData?.is_valid === true;
  const customer = licenseData?.license?.customer || t('settings_not_available', 'N/A');
  const expiration = licenseData?.expires_at ? new Date(licenseData.expires_at).toLocaleString() : t('settings_not_available', 'N/A');
  const maxDevices = Number(licenseData?.max_devices || 0);
  const deviceCount = Number(licenseData?.device_count || 0);

  return (
    <Section title={t('settings_subscription_license_title', 'Subscription & License')} desc={t('settings_subscription_license_desc', 'Manage product activation and limits.')}>
      <div className="grid grid-cols-1 gap-6">
        <div className={`p-6 border rounded-2xl flex items-center justify-between ${isActive ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-red-500/5 border-red-500/20'}`}>
          <div className="flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isActive ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
              <Key size={24} />
            </div>
            <div>
              <div className="text-lg font-bold text-gray-900 dark:text-white mb-1">
                {t('settings_license_product_name', 'NetSphere Pro')}
                <span className={`ml-2 text-xs px-2 py-0.5 rounded border uppercase ${isActive ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
                  {licenseData?.status || (loading ? t('common_loading', 'Loading...') : t('settings_not_available', 'N/A'))}
                </span>
              </div>
              <div className="text-sm text-gray-500">
                {t('settings_license_licensed_to', 'Licensed to')} <span className="text-gray-700 dark:text-gray-300 font-bold">{customer}</span> · {t('settings_license_expires', 'Expires')} {expiration}
              </div>
              <div className="mt-1 text-xs text-gray-500">
                {t('settings_license_devices', 'Devices')}: <span className="font-bold text-gray-700 dark:text-gray-300">{deviceCount}</span>
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-black text-gray-900 dark:text-white">{maxDevices}</div>
            <div className="text-xs text-gray-600 dark:text-gray-500 uppercase font-bold">{t('settings_license_max_devices', 'Max Devices')}</div>
          </div>
        </div>

        {isAdmin && (
          <div className="bg-[#15171a] p-6 rounded-2xl border border-gray-800 space-y-4">
            <h4 className="font-bold text-white flex items-center gap-2"><Upload size={16} /> {t('settings_license_update_key', 'Update License Key')}</h4>
            <textarea
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              className="w-full h-32 bg-gray-100 dark:bg-black/30 border border-gray-300 dark:border-gray-800 rounded-xl p-4 text-xs font-mono text-gray-700 dark:text-gray-400 focus:outline-none focus:border-blue-500"
              placeholder={t('settings_license_paste_placeholder', 'Paste your new license key string here...')}
            />
            <div className="flex justify-end gap-2">
              <button onClick={handleUninstall} disabled={savingKey} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white font-bold rounded-lg text-sm disabled:opacity-60">
                {t('settings_license_remove', 'Remove License')}
              </button>
              <button onClick={handleUpload} disabled={savingKey} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-lg text-sm disabled:opacity-60">
                {t('settings_license_activate', 'Activate New License')}
              </button>
            </div>
          </div>
        )}
      </div>
    </Section>
  );
};


const UserModal = ({ onClose, onSubmit }) => {
  const [formData, setFormData] = useState({
    username: '', email: '', password: '', full_name: '', role: 'viewer', is_active: true
  });

  return (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/80 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
      <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-md rounded-2xl border border-gray-200 dark:border-gray-800 shadow-2xl animate-scale-in">
        <div className="flex justify-between items-center p-6 border-b border-gray-800">
          <h3 className="text-xl font-bold flex items-center gap-2"><Plus size={20} className="text-blue-500" /> {t('settings_create_user', 'Create User')}</h3>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full text-gray-500 hover:text-gray-900 dark:hover:text-white transition-colors"><X size={20} /></button>
        </div>
        <div className="p-6 space-y-4">
          <Input label={t('user_mgmt_username_required', 'Username *')} value={formData.username} onChange={(e) => setFormData({ ...formData, username: e.target.value })} />
          <Input label={t('user_mgmt_email', 'Email')} value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} type="email" />
          <Input label={t('user_mgmt_full_name', 'Full Name')} value={formData.full_name} onChange={(e) => setFormData({ ...formData, full_name: e.target.value })} />
          <Input label={t('user_mgmt_password_required', 'Password *')} value={formData.password} onChange={(e) => setFormData({ ...formData, password: e.target.value })} type="password" />
          <Select label={t('user_mgmt_role_required', 'Role *')} value={formData.role} onChange={(e) => setFormData({ ...formData, role: e.target.value })} options={['viewer', 'editor', 'admin']} />
        </div>
        <div className="p-6 border-t border-gray-800 flex gap-3">
          <button onClick={onClose} className="flex-1 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-xl font-bold transition-all">{t('common_cancel', 'Cancel')}</button>
          <button onClick={() => onSubmit(formData)} className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold shadow-lg shadow-blue-900/40 transition-all">{t('settings_create_account', 'Create Account')}</button>
        </div>
      </div>
    </div>
  );
};

const SidebarItem = ({ icon: Icon, label, active, onClick }) => (
  <button onClick={onClick} className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all group ${active ? 'bg-blue-50/80 dark:bg-blue-600/10 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/20 shadow-sm' : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-200 border border-transparent'}`}>
    <Icon size={18} className={active ? 'text-blue-600 dark:text-blue-500' : 'text-gray-500 dark:text-gray-600 group-hover:text-gray-700 dark:group-hover:text-gray-400'} />
    {label}
  </button>
);

const Section = ({ title, desc, children }) => (
  <div className="animate-fade-in-up">
    <div className="mb-6 flex flex-col gap-1">
      <h3 className="text-xl font-black text-gray-900 dark:text-white tracking-tight">{title}</h3>
      <p className="text-xs text-gray-600 dark:text-gray-500 font-medium">{desc}</p>
    </div>
    {children}
  </div>
);

const translateSettingsStatic = (value) => {
  const raw = String(value || '').trim();
  if (!raw) return raw;

  const map = {
    'Password Min Length': t('settings_password_min_length', 'Password Min Length'),
    'Required Classes (1-4)': t('settings_required_classes', 'Required Classes (1-4)'),
    'Password History Count': t('settings_password_history_count', 'Password History Count'),
    'Password Expire Days (0=off)': t('settings_password_expire_days', 'Password Expire Days (0=off)'),
    'Forbid Username in Password': t('settings_forbid_username_in_password', 'Forbid Username in Password'),
    'Reject passwords that contain the username.': t('settings_forbid_username_in_password_desc', 'Reject passwords that contain the username.'),
    'Multi-Factor Authentication (MFA)': t('settings_mfa_title', 'Multi-Factor Authentication (MFA)'),
    'Enable optional 2FA feature. Each user can opt-in later.': t('settings_mfa_desc', 'Enable optional 2FA feature. Each user can opt-in later.'),
    'Audit Hash Chain': t('settings_audit_hash_chain', 'Audit Hash Chain'),
    'Store tamper-evident HMAC chain fields in audit logs.': t('settings_audit_hash_chain_desc', 'Store tamper-evident HMAC chain fields in audit logs.'),
    'Audit HMAC Key': t('settings_audit_hmac_key', 'Audit HMAC Key'),
    '(optional) override SECRET_KEY': t('settings_optional_override_secret', '(optional) override SECRET_KEY'),
    'Audit Syslog Forwarding': t('settings_audit_syslog_forwarding', 'Audit Syslog Forwarding'),
    'Forward audit events to a remote Syslog server (UDP).': t('settings_audit_syslog_forwarding_desc', 'Forward audit events to a remote Syslog server (UDP).'),
    'Syslog Host': t('settings_syslog_host', 'Syslog Host'),
    'e.g. 10.0.0.10': t('settings_example_10_0_0_10', 'e.g. 10.0.0.10'),
    'Syslog Port': t('settings_syslog_port', 'Syslog Port'),
    'PII Masking': t('settings_pii_masking', 'PII Masking'),
    'Mask IP/MAC/Phone/Email in UI logs and API responses.': t('settings_pii_masking_desc', 'Mask IP/MAC/Phone/Email in UI logs and API responses.'),
    'Mask IP': t('settings_mask_ip', 'Mask IP'),
    'Mask MAC': t('settings_mask_mac', 'Mask MAC'),
    'Mask Phone': t('settings_mask_phone', 'Mask Phone'),
    'Mask Email': t('settings_mask_email', 'Mask Email'),
    'SMTP Server': t('settings_smtp_server', 'SMTP Server'),
    'e.g. smtp.gmail.com': t('settings_example_smtp', 'e.g. smtp.gmail.com'),
    Port: t('settings_port', 'Port'),
    Username: t('settings_username', 'Username'),
    Password: t('settings_password', 'Password'),
    'Sender Address (From)': t('settings_sender_from', 'Sender Address (From)'),
    'netsphere@domain.com': t('settings_example_sender', 'netsphere@domain.com'),
    'Template Direct Max Devices': t('settings_template_direct_max_devices', 'Template Direct Max Devices'),
  };

  return map[raw] || raw;
};

const Input = ({ label, name, value, onChange, type = "text", placeholder, disabled, min, max, step, hint, list }) => (
  <div className="flex flex-col gap-2">
    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest flex items-center gap-1.5">
      {type === 'password' && <Lock size={10} />}
      {type === 'email' && <Mail size={10} />}
      {translateSettingsStatic(label)}
    </label>
    <input
      type={type} name={name} value={value || ''} onChange={onChange} placeholder={translateSettingsStatic(placeholder)} disabled={disabled}
      min={min}
      max={max}
      step={step}
      list={list}
      className={`w-full bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-900 dark:text-gray-200 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition-all placeholder-gray-400 dark:placeholder-gray-700
        ${disabled ? 'opacity-60 bg-gray-100 dark:bg-gray-900 cursor-not-allowed' : ''}`}
    />
    {!!hint && <div className="text-[11px] text-gray-500">{hint}</div>}
  </div>
);

const Select = ({ label, name, value, onChange, options, disabled }) => (
  <div className="flex flex-col gap-2">
    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{translateSettingsStatic(label)}</label>
    <select
      name={name} value={value} onChange={onChange} disabled={disabled}
      className={`w-full bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-900 dark:text-gray-200 focus:outline-none focus:border-blue-500 transition-all cursor-pointer appearance-none
        ${disabled ? 'opacity-60 bg-gray-100 dark:bg-gray-900 cursor-not-allowed' : ''}`}
    >
      {options.map((opt) => {
        if (opt && typeof opt === 'object') {
          const optionValue = String(opt.value ?? '');
          const optionLabel = String(opt.label ?? optionValue);
          return <option key={optionValue} value={optionValue}>{optionLabel}</option>;
        }
        const optionValue = String(opt);
        return <option key={optionValue} value={optionValue}>{optionValue}</option>;
      })}
    </select>
  </div>
);

const SelectRich = ({ label, name, value, onChangeValue, options, disabled }) => (
  <div className="flex flex-col gap-2">
    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{translateSettingsStatic(label)}</label>
    <select
      name={name}
      value={value}
      onChange={(e) => onChangeValue?.(e.target.value)}
      disabled={disabled}
      className={`w-full bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-900 dark:text-gray-200 focus:outline-none focus:border-blue-500 transition-all cursor-pointer appearance-none
        ${disabled ? 'opacity-60 bg-gray-100 dark:bg-gray-900 cursor-not-allowed' : ''}`}
    >
      {(options || []).map(opt => <option key={String(opt.value)} value={opt.value}>{opt.label}</option>)}
    </select>
  </div>
);

const MyAccountSecurity = ({ email, onEmailChange, mfaEnabled, onMfaChange, emailVerified, onSendEmailVerification, emailVerifySending, emailVerifyCooldownSeconds, emailVerifyOtpLength, emailVerifyFocusSignal, emailVerifyOtp, onEmailVerifyOtpChange, onVerifyEmail, emailVerifyVerifying, onRequireEmailVerification, mfaAvailable, saving, onSave }) => (
  <Section title={t('settings_my_account_title', 'My Account')} desc={t('settings_my_account_desc', 'Manage your own email and optional 2FA settings.')}>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <Input
        label={t('settings_my_email', 'My Email')}
        type="email"
        value={email}
        onChange={(e) => onEmailChange(e.target.value)}
        placeholder={t('settings_my_email_placeholder', 'you@company.com')}
      />
      <div className="flex items-center justify-between p-5 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm">
        <div>
          <div className="font-bold text-gray-900 dark:text-white">{t('settings_email_verification', 'Email Verification')}</div>
          <div className="text-xs text-gray-500">
            {email
              ? (emailVerified
                ? t('settings_email_verified', 'Verified')
                : t('settings_email_not_verified', 'Not verified'))
              : t('settings_email_set_first', 'Set your email first')}
          </div>
        </div>
        <button
          onClick={onSendEmailVerification}
          disabled={!email || emailVerifySending || (emailVerifyCooldownSeconds > 0)}
          className={`px-3 py-2 bg-gray-800 hover:bg-gray-700 text-gray-200 rounded-lg transition-colors font-bold text-xs border border-gray-700 ${(!email || emailVerifySending || (emailVerifyCooldownSeconds > 0)) ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {emailVerifySending
            ? t('settings_sending', 'Sending...')
            : (emailVerifyCooldownSeconds > 0
              ? t('settings_send_code_in_fmt', 'Send Code ({seconds}s)').replace('{seconds}', String(emailVerifyCooldownSeconds))
              : t('settings_send_code', 'Send Code'))}
        </button>
      </div>
      <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
        <div className="md:col-span-2">
          <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest flex items-center gap-1.5">
            {t('settings_verification_code', 'Verification Code')}
          </label>
          <OtpCodeInput
            length={emailVerifyOtpLength}
            value={emailVerifyOtp}
            onChange={onEmailVerifyOtpChange}
            focusSignal={emailVerifyFocusSignal}
          />
        </div>
        <button
          onClick={onVerifyEmail}
          disabled={!email || emailVerifyVerifying || String(emailVerifyOtp || '').length !== Number(emailVerifyOtpLength)}
          className={`px-4 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl transition-colors font-bold text-sm shadow-lg shadow-blue-900/20 ${(!email || emailVerifyVerifying) ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {emailVerifyVerifying ? <RefreshCw size={16} className="animate-spin" /> : t('common_verify', 'Verify')}
        </button>
        <div className="text-xs text-gray-500">
          {t('settings_email_verification_required', 'Email verification is required before enabling 2FA.')}
        </div>
      </div>
      <div className="flex items-center justify-between p-5 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm">
        <div>
          <div className="font-bold text-gray-900 dark:text-white">{t('settings_2fa_email_otp', '2FA (Email OTP)')}</div>
          <div className="text-xs text-gray-500">
            {mfaAvailable
              ? t('settings_2fa_optional_desc', 'Enable 2FA for this account (optional).')
              : t('settings_2fa_disabled_by_admin', 'System 2FA is disabled by admin.')}
          </div>
        </div>
        <label className="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            checked={!!mfaEnabled}
            onChange={(e) => {
              const checked = e.target.checked;
              if (checked && (!email || !emailVerified)) {
                onRequireEmailVerification?.();
                onMfaChange(false);
                return;
              }
              onMfaChange(checked);
            }}
            disabled={!mfaAvailable}
            className="sr-only peer"
          />
          <div className="w-12 h-6 bg-gray-700 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
        </label>
      </div>
      <div className="md:col-span-2 flex justify-end">
        <button
          onClick={onSave}
          disabled={saving}
          className={`px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-bold rounded-lg flex items-center gap-2 transition-all shadow-lg shadow-blue-900/20 ${saving ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {saving ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
          {t('settings_save_my_settings', 'Save My Settings')}
        </button>
      </div>
    </div>
  </Section>
);

const OtpCodeInput = ({ length = 6, value, onChange, focusSignal }) => {
  const inputsRef = useRef([]);
  const digits = useMemo(() => {
    const s = String(value || '').replace(/\D/g, '').slice(0, Number(length) || 6);
    return Array.from({ length: Number(length) || 6 }, (_, i) => s[i] || '');
  }, [value, length]);

  useEffect(() => {
    const idx = digits.findIndex((d) => !d);
    const target = idx >= 0 ? idx : Math.max(0, digits.length - 1);
    const el = inputsRef.current[target];
    if (el && typeof el.focus === 'function') el.focus();
  }, [focusSignal]);

  const setAt = (index, nextChar) => {
    const clean = String(nextChar || '').replace(/\D/g, '').slice(-1);
    const nextDigits = [...digits];
    nextDigits[index] = clean;
    const nextValue = nextDigits.join('');
    onChange(nextValue);
    if (clean && index < nextDigits.length - 1) {
      const el = inputsRef.current[index + 1];
      if (el && typeof el.focus === 'function') el.focus();
    }
  };

  const handlePaste = (e) => {
    const text = (e.clipboardData?.getData('text') || '').replace(/\D/g, '');
    if (!text) return;
    e.preventDefault();
    const nextDigits = Array.from({ length: Number(length) || 6 }, (_, i) => text[i] || '');
    const nextValue = nextDigits.join('');
    onChange(nextValue);
    const idx = nextDigits.findIndex((d) => !d);
    const target = idx >= 0 ? idx : Math.max(0, nextDigits.length - 1);
    const el = inputsRef.current[target];
    if (el && typeof el.focus === 'function') el.focus();
  };

  return (
    <div className="mt-2 flex gap-2" onPaste={handlePaste}>
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => { inputsRef.current[i] = el; }}
          value={d}
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          onChange={(e) => setAt(i, e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Backspace') {
              if (digits[i]) {
                setAt(i, '');
              } else if (i > 0) {
                const prev = inputsRef.current[i - 1];
                if (prev && typeof prev.focus === 'function') prev.focus();
              }
            }
          }}
          className="w-12 h-12 text-center bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl text-lg font-black text-gray-900 dark:text-gray-200 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition-all"
        />
      ))}
    </div>
  );
};

const TextArea = ({ label, name, value, onChange, placeholder, disabled }) => (
  <div className="flex flex-col gap-2">
    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{translateSettingsStatic(label)}</label>
    <textarea
      name={name}
      value={value || ''}
      onChange={onChange}
      placeholder={translateSettingsStatic(placeholder)}
      disabled={disabled}
      rows={5}
      className={`w-full bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-900 dark:text-gray-200 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition-all placeholder-gray-400 dark:placeholder-gray-700 resize-y
        ${disabled ? 'opacity-60 bg-gray-100 dark:bg-gray-900 cursor-not-allowed' : ''}`}
    />
  </div>
);

const Toggle = ({ label, name, checked, onChange, disabled, desc }) => (
  <div className="flex flex-col gap-2">
    <div className="flex items-center justify-between gap-4 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3">
      <div className="min-w-0">
        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{translateSettingsStatic(label)}</div>
        {desc && <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">{translateSettingsStatic(desc)}</div>}
      </div>
      <label className={`relative inline-flex items-center cursor-pointer ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}>
        <input type="checkbox" name={name} checked={!!checked} onChange={onChange} disabled={disabled} className="sr-only peer" />
        <div className="w-11 h-6 bg-gray-200 dark:bg-gray-800 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-500/10 rounded-full peer peer-checked:bg-blue-600 transition-colors"></div>
        <div className="absolute left-1 top-1 bg-white w-4 h-4 rounded-full transition-transform peer-checked:translate-x-5"></div>
      </label>
    </div>
  </div>
);

const StatusItem = ({ label, value }) => (
  <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3">
    <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{label}</div>
    <div className="mt-1 text-sm font-bold text-gray-900 dark:text-gray-200 break-all">{String(value ?? '')}</div>
  </div>
);

const BackupCard = ({ title, icon: Icon, color, onClick, active }) => (
  <div
    onClick={onClick}
    className={`p-6 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl transition-all flex items-center gap-5 group
      ${active ? `hover:border-${color}-500/50 cursor-pointer shadow-sm hover:shadow-md` : 'opacity-40 cursor-not-allowed'}`}
  >
    <div className={`p-4 bg-${color}-500/10 text-${color}-500 rounded-2xl group-hover:scale-110 transition-transform`}>
      <Icon size={28} />
    </div>
    <div>
      <div className="font-black text-gray-900 dark:text-white">{title}</div>
      <div className="text-[11px] text-gray-500 mt-1">{t('settings_backup_full_capture', 'Full system state capture')}</div>
    </div>
  </div>
);

export default SettingsPage;
