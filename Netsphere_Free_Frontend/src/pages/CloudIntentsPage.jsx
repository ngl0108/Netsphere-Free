import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  CheckCircle2,
  Cloud,
  ExternalLink,
  GitBranch,
  Map as MapIcon,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';

import { ApprovalService, CloudService, IntentService } from '../api/services';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';
import { InlineEmpty, InlineLoading, SectionCard, SectionHeader } from '../components/common/PageState';
import { parseCloudIntentPrefill } from '../utils/cloudIntentLinks';
import { buildTopologyPath } from '../utils/observabilityLinks';

const DEFAULT_SPEC = {
  providers: ['aws'],
  accountIds: [],
  regions: 'ap-northeast-2',
  resourceTypes: 'vpc\nsubnet\nroute_table\nsecurity_group',
  requiredTags: 'owner\nenv=prod',
  blockedIngressCidrs: '0.0.0.0/0',
  protectedRouteDestinations: '0.0.0.0/0',
  allowedDefaultRouteTargets: '',
  enforcePrivateOnlyNextHop: true,
};

const PROVIDERS = [
  { value: 'aws', label: 'AWS' },
  { value: 'azure', label: 'Azure' },
  { value: 'gcp', label: 'GCP' },
  { value: 'ncp', label: 'NCP' },
];

const PANEL_CLASS = 'rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] shadow-sm';

const normalizeLines = (value) =>
  String(value || '')
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);

const slugify = (value) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

const parseRequiredTags = (value) =>
  normalizeLines(value)
    .map((row) => {
      const [key, ...rest] = row.split('=');
      const item = { key: String(key || '').trim() };
      const joined = rest.join('=').trim();
      if (joined) item.value = joined;
      return item;
    })
    .filter((row) => row.key);

const toSortedEntries = (value) =>
  Object.entries(value && typeof value === 'object' ? value : {})
    .map(([key, count]) => ({
      key: String(key || ''),
      count: Number(count || 0),
    }))
    .filter((row) => row.key)
    .sort((a, b) => (b.count - a.count) || a.key.localeCompare(b.key));

const buildIntentPayload = ({ name, draft }) => ({
  intent_type: 'cloud_policy',
  name: String(name || '').trim(),
  spec: {
    targets: {
      providers: draft.providers,
      account_ids: draft.accountIds.map((id) => Number(id)).filter((id) => Number.isFinite(id)),
      regions: normalizeLines(draft.regions),
      resource_types: normalizeLines(draft.resourceTypes),
    },
    required_tags: parseRequiredTags(draft.requiredTags),
    blocked_ingress_cidrs: normalizeLines(draft.blockedIngressCidrs),
    protected_route_destinations: normalizeLines(draft.protectedRouteDestinations),
    allowed_default_route_targets: normalizeLines(draft.allowedDefaultRouteTargets),
    enforce_private_only_next_hop: !!draft.enforcePrivateOnlyNextHop,
  },
  metadata: {
    source: 'cloud_intents_ui',
    engine: 'terraform',
    submission_channel: 'cloud_pro_mvp',
  },
  dry_run: true,
});

const buildResourceTypeDraft = (resourceTypes = []) =>
  resourceTypes.length > 0 ? resourceTypes.join('\n') : DEFAULT_SPEC.resourceTypes;

const buildPrefillName = (prefill) =>
  String(prefill?.intentName || '').trim() || 'cloud-guardrail-baseline';

const buildTemplateDraft = (template, accounts = []) => {
  const starter = template?.starter_payload && typeof template.starter_payload === 'object'
    ? template.starter_payload
    : {};
  const providers = Array.isArray(starter.providers) && starter.providers.length > 0
    ? starter.providers.map((row) => String(row || '').trim().toLowerCase()).filter(Boolean)
    : [...DEFAULT_SPEC.providers];
  const eligibleAccounts = accounts.filter((row) => providers.includes(String(row?.provider || '').trim().toLowerCase()));
  const firstEligible = eligibleAccounts[0] || null;
  return {
    name: String(starter.name || template?.key || 'cloud-guardrail-baseline').trim() || 'cloud-guardrail-baseline',
    draft: {
      providers,
      accountIds: firstEligible ? [Number(firstEligible.id)] : [],
      regions: Array.isArray(starter.regions) && starter.regions.length > 0 ? starter.regions.join('\n') : DEFAULT_SPEC.regions,
      resourceTypes: Array.isArray(starter.resource_types) && starter.resource_types.length > 0 ? starter.resource_types.join('\n') : DEFAULT_SPEC.resourceTypes,
      requiredTags: Array.isArray(starter.required_tags)
        ? starter.required_tags
            .map((row) => {
              const key = String(row?.key || '').trim();
              const value = String(row?.value || '').trim();
              if (!key) return '';
              return value ? `${key}=${value}` : key;
            })
            .filter(Boolean)
            .join('\n')
        : DEFAULT_SPEC.requiredTags,
      blockedIngressCidrs: Array.isArray(starter.blocked_ingress_cidrs) ? starter.blocked_ingress_cidrs.join('\n') : DEFAULT_SPEC.blockedIngressCidrs,
      protectedRouteDestinations: Array.isArray(starter.protected_route_destinations) ? starter.protected_route_destinations.join('\n') : DEFAULT_SPEC.protectedRouteDestinations,
      allowedDefaultRouteTargets: Array.isArray(starter.allowed_default_route_targets) ? starter.allowed_default_route_targets.join('\n') : DEFAULT_SPEC.allowedDefaultRouteTargets,
      enforcePrivateOnlyNextHop:
        typeof starter.enforce_private_only_next_hop === 'boolean'
          ? starter.enforce_private_only_next_hop
          : DEFAULT_SPEC.enforcePrivateOnlyNextHop,
    },
    prefillContext: {
      source: 'template',
      provider: providers.length === 1 ? providers[0] : '',
      accountName: firstEligible?.name || '',
      accountId: firstEligible?.id ? String(firstEligible.id) : '',
      region:
        Array.isArray(starter.regions) && starter.regions.length === 1
          ? String(starter.regions[0] || '').trim()
          : '',
      resourceTypes: Array.isArray(starter.resource_types) ? starter.resource_types : [],
      templateName: String(template?.name || template?.key || '').trim(),
    },
  };
};

const getPrefillCopy = (context) => {
  const source = String(context?.source || '').trim().toLowerCase();
  if (source === 'template') {
    return {
      title: t('cloud_intents_prefill_template_title', 'Prefilled from template'),
      desc: t(
        'cloud_intents_prefill_template_desc',
        'This draft started from an operating template. Providers, baseline resource scope, and guardrail defaults are already staged for validation and preview.',
      ),
    };
  }
  if (source === 'alert') {
    return {
      title: t('cloud_intents_prefill_alert_title', 'Prefilled from alert'),
      desc: t(
        'cloud_intents_prefill_alert_desc',
        'This intent draft inherited provider, account, region, and resource scope from the cloud alert you selected.',
      ),
    };
  }
  return {
    title: t('cloud_intents_prefill_title', 'Prefilled from topology'),
    desc: t(
      'cloud_intents_prefill_desc',
      'This intent draft inherited provider, account, region, and resource scope from the cloud node you selected in topology.',
    ),
  };
};

const badgeClass = (tone) => {
  if (tone === 'good') return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-800/60';
  if (tone === 'warn') return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-800/60';
  if (tone === 'bad') return 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:border-rose-800/60';
  return 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-800/60';
};

const SummaryBadge = ({ label, tone = 'info' }) => (
  <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-[11px] font-bold ${badgeClass(tone)}`}>
    {label}
  </span>
);

const FieldLabel = ({ children }) => (
  <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold mb-2">{children}</div>
);

const Input = ({ value, onChange, placeholder }) => (
  <input
    value={value}
    onChange={(e) => onChange(e.target.value)}
    placeholder={placeholder}
    className="w-full rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
  />
);

const TextArea = ({ value, onChange, placeholder, rows = 4 }) => (
  <textarea
    value={value}
    onChange={(e) => onChange(e.target.value)}
    placeholder={placeholder}
    rows={rows}
    className="w-full rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 resize-y"
  />
);

const MetricCard = ({ title, value, hint }) => (
  <div className={`${PANEL_CLASS} p-4`}>
    <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{title}</div>
    <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{value}</div>
    {hint ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</div> : null}
  </div>
);

const CloudIntentsPage = () => {
  useLocaleRerender();
  const location = useLocation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { isAtLeast } = useAuth();
  const appliedPrefillRef = useRef('');
  const appliedTemplatePrefillRef = useRef('');

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [intentStatus, setIntentStatus] = useState(null);
  const [name, setName] = useState('cloud-guardrail-baseline');
  const [draft, setDraft] = useState(DEFAULT_SPEC);
  const [validationResult, setValidationResult] = useState(null);
  const [simulationResult, setSimulationResult] = useState(null);
  const [prefillContext, setPrefillContext] = useState(null);

  const canSubmitApproval = isAtLeast('operator');

  const resetDraftToDefault = React.useCallback((rows = accounts) => {
    const nextDefaultAccountIds = Array.isArray(rows) && rows.length > 0 ? [Number(rows[0].id)] : [];
    setName('cloud-guardrail-baseline');
    setDraft({
      ...DEFAULT_SPEC,
      accountIds: nextDefaultAccountIds,
    });
    setValidationResult(null);
    setSimulationResult(null);
  }, [accounts]);

  const load = async () => {
    setLoading(true);
    try {
      const [accountsRes, statusRes] = await Promise.all([
        CloudService.listAccounts(),
        IntentService.getStatus(),
      ]);
      const rows = Array.isArray(accountsRes?.data) ? accountsRes.data : [];
      setAccounts(rows);
      setIntentStatus(statusRes?.data || null);
      setDraft((prev) => ({
        ...prev,
        accountIds: prev.accountIds.length > 0 ? prev.accountIds : rows.slice(0, 1).map((row) => Number(row.id)),
      }));
    } catch (error) {
      toast.error(`${t('cloud_intents_load_failed', 'Failed to load Cloud Intents baseline')}: ${error?.response?.data?.detail || error.message}`);
      setAccounts([]);
      setIntentStatus(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (loading) return;
    if (appliedPrefillRef.current === location.search) return;

    const prefill = parseCloudIntentPrefill(location.search);
    appliedPrefillRef.current = location.search;

    if (!prefill.hasPrefill) {
      setPrefillContext(null);
      return;
    }

    const availableProviders = new Set(PROVIDERS.map((provider) => provider.value));
    const nextProviders = prefill.provider && availableProviders.has(prefill.provider)
      ? [prefill.provider]
      : [...DEFAULT_SPEC.providers];
    const availableAccounts = new Map(accounts.map((row) => [String(row.id), row]));
    const nextAccountIds = prefill.accountId && availableAccounts.has(prefill.accountId)
      ? [Number(prefill.accountId)]
      : [];

    setName(buildPrefillName(prefill));
    setDraft((prev) => ({
      ...prev,
      providers: nextProviders,
      accountIds: nextAccountIds,
      regions: prefill.region || prev.regions || DEFAULT_SPEC.regions,
      resourceTypes: buildResourceTypeDraft(prefill.resourceTypes),
    }));
    setValidationResult(null);
    setSimulationResult(null);

    const matchedAccount = prefill.accountId ? availableAccounts.get(prefill.accountId) : null;
    setPrefillContext({
      source: prefill.source || 'topology',
      provider: prefill.provider || '',
      region: prefill.region || '',
      resourceName: prefill.resourceName || prefill.resourceId || '',
      resourceId: prefill.resourceId || '',
      resourceTypes: prefill.resourceTypes,
      accountName: matchedAccount?.name || '',
      accountId: prefill.accountId || '',
    });
  }, [accounts, loading, location.search]);

  useEffect(() => {
    if (loading) return;
    const template = location.state?.intentTemplatePrefill;
    if (!template || typeof template !== 'object') return;
    const templateKey = String(template?.key || '').trim();
    if (!templateKey) return;
    const applyKey = `${location.key}:${templateKey}`;
    if (appliedTemplatePrefillRef.current === applyKey) return;
    appliedTemplatePrefillRef.current = applyKey;

    const next = buildTemplateDraft(template, accounts);
    setName(next.name);
    setDraft(next.draft);
    setValidationResult(null);
    setSimulationResult(null);
    setPrefillContext(next.prefillContext);
  }, [accounts, loading, location.key, location.state]);

  const providerBuckets = useMemo(() => {
    const counts = {};
    for (const provider of PROVIDERS) counts[provider.value] = 0;
    for (const row of accounts) {
      const key = String(row?.provider || '').trim().toLowerCase();
      counts[key] = Number(counts[key] || 0) + 1;
    }
    return counts;
  }, [accounts]);

  const eligibleAccounts = useMemo(() => {
    const selectedProviders = new Set(draft.providers);
    return accounts.filter((row) => selectedProviders.has(String(row?.provider || '').trim().toLowerCase()));
  }, [accounts, draft.providers]);

  const previewSummary = useMemo(() => {
    if (!simulationResult || typeof simulationResult !== 'object') return null;
    return {
      riskScore: Number(simulationResult?.risk_score || 0),
      blastRadius: simulationResult?.blast_radius || {},
      cloudScope: simulationResult?.cloud_scope || {},
      plan: simulationResult?.terraform_plan_preview || {},
      changeSummary: Array.isArray(simulationResult?.change_summary) ? simulationResult.change_summary : [],
      recommendations: Array.isArray(simulationResult?.recommendations) ? simulationResult.recommendations : [],
      rollbackPlan: simulationResult?.terraform_plan_preview?.rollback_plan || null,
      operationalGuardrails: simulationResult?.operational_guardrails || null,
      preCheck: simulationResult?.pre_check || null,
      beforeAfterCompare: simulationResult?.before_after_compare || null,
    };
  }, [simulationResult]);

  const impactSummary = useMemo(() => {
    if (!previewSummary) return null;
    const cloudScope = previewSummary.cloudScope && typeof previewSummary.cloudScope === 'object'
      ? previewSummary.cloudScope
      : {};
    const providers = Array.isArray(cloudScope?.target_providers) ? cloudScope.target_providers.map((row) => String(row || '').trim()).filter(Boolean) : [];
    const accounts = Array.isArray(cloudScope?.target_accounts) ? cloudScope.target_accounts.map((row) => String(row || '').trim()).filter(Boolean) : [];
    const resourcesByType = toSortedEntries(cloudScope?.resources_by_type);
    const resourcesByProvider = toSortedEntries(cloudScope?.resources_by_provider);
    const regionsByProvider = cloudScope?.regions_by_provider && typeof cloudScope.regions_by_provider === 'object'
      ? cloudScope.regions_by_provider
      : {};
    const firstProvider = String(prefillContext?.provider || providers[0] || '').trim().toLowerCase();
    const providerRegions = firstProvider && Array.isArray(regionsByProvider[firstProvider]) ? regionsByProvider[firstProvider] : [];
    const region = String(prefillContext?.region || providerRegions[0] || '').trim();
    const accountId = String(prefillContext?.accountId || (providers.length === 1 && accounts.length === 1 ? accounts[0] : '')).trim();
    const resourceId = String(prefillContext?.resourceId || '').trim();
    const resourceName = String(prefillContext?.resourceName || '').trim();
    const routeTargets = Number(cloudScope?.route_like_targets || 0);
    const securityTargets = Number(cloudScope?.security_group_like_targets || 0);
    const instanceTargets = Number(cloudScope?.instance_like_targets || 0);
    const networkTargets = Number(cloudScope?.network_like_targets || 0);
    const topologyPath = buildTopologyPath({
      cloudProvider: firstProvider,
      cloudAccountId: accountId,
      cloudRegion: region,
      cloudResourceTypes: resourcesByType.map((row) => row.key),
      cloudIntentImpact: true,
      focusCloudResourceId: resourceId,
      focusCloudResourceName: resourceName,
    });

    return {
      providers,
      accounts,
      resourcesByType,
      resourcesByProvider,
      regionsByProvider,
      routeTargets,
      securityTargets,
      instanceTargets,
      networkTargets,
      topologyPath,
      focusedProvider: firstProvider,
      focusedRegion: region,
      focusedAccountId: accountId,
      focusedResourceId: resourceId,
      focusedResourceName: resourceName,
      cloudAccountsPath: accountId ? `/cloud/accounts?focusAccountId=${encodeURIComponent(accountId)}` : '/cloud/accounts',
    };
  }, [prefillContext, previewSummary]);
  const prefillCopy = useMemo(() => getPrefillCopy(prefillContext), [prefillContext]);

  const guardrailSignals = useMemo(() => {
    const findings = Array.isArray(previewSummary?.operationalGuardrails?.findings)
      ? previewSummary.operationalGuardrails.findings
      : [];
    const hasKey = (key) => findings.some((finding) => String(finding?.key || '').trim().toLowerCase() === key);
    return {
      publicIngress: hasKey('public_ingress'),
      defaultRoute: hasKey('default_route'),
      broadCidr: hasKey('broad_cidr'),
      highImpactEdges: hasKey('high_impact_edges'),
      readOnlyAccounts: hasKey('read_only_accounts'),
      broadScope: hasKey('broad_scope'),
      count: findings.length,
    };
  }, [previewSummary]);

  const executionReadiness = useMemo(() => {
    if (!intentStatus || typeof intentStatus !== 'object') return null;
    return intentStatus?.cloud_execution_readiness && typeof intentStatus.cloud_execution_readiness === 'object'
      ? intentStatus.cloud_execution_readiness
      : null;
  }, [intentStatus]);

  const readinessErrors = Array.isArray(executionReadiness?.errors) ? executionReadiness.errors : [];
  const readinessWarnings = Array.isArray(executionReadiness?.warnings) ? executionReadiness.warnings : [];
  const readinessRuntime = executionReadiness?.terraform_runtime && typeof executionReadiness.terraform_runtime === 'object'
    ? executionReadiness.terraform_runtime
    : null;
  const readinessBackend = executionReadiness?.backend_validation && typeof executionReadiness.backend_validation === 'object'
    ? executionReadiness.backend_validation
    : null;

  const toggleProvider = (provider) => {
    setDraft((prev) => {
      const has = prev.providers.includes(provider);
      const nextProviders = has ? prev.providers.filter((item) => item !== provider) : [...prev.providers, provider];
      const nextAccounts = prev.accountIds.filter((accountId) => {
        const match = accounts.find((row) => Number(row.id) === Number(accountId));
        return match ? nextProviders.includes(String(match.provider || '').trim().toLowerCase()) : false;
      });
      return {
        ...prev,
        providers: nextProviders.length > 0 ? nextProviders : [provider],
        accountIds: nextAccounts,
      };
    });
  };

  const toggleAccount = (accountId) => {
    setDraft((prev) => {
      const current = new Set(prev.accountIds.map((id) => Number(id)));
      const normalized = Number(accountId);
      if (current.has(normalized)) current.delete(normalized);
      else current.add(normalized);
      return {
        ...prev,
        accountIds: [...current],
      };
    });
  };

  const handleValidate = async () => {
    const payload = buildIntentPayload({ name, draft });
    setSubmitting(true);
    try {
      const res = await IntentService.validateIntent(payload);
      setValidationResult(res?.data || null);
      toast.success(t('cloud_intents_validate_success', 'Cloud intent validation completed.'));
    } catch (error) {
      setValidationResult(null);
      toast.error(`${t('cloud_intents_validate_failed', 'Cloud intent validation failed')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSimulate = async () => {
    const payload = buildIntentPayload({ name, draft });
    setSubmitting(true);
    try {
      const res = await IntentService.simulateIntent(payload);
      const data = res?.data || null;
      setSimulationResult(data);
      setValidationResult(data?.validation || null);
      toast.success(t('cloud_intents_preview_success', 'Terraform-style change preview is ready.'));
    } catch (error) {
      setSimulationResult(null);
      toast.error(`${t('cloud_intents_preview_failed', 'Failed to build change preview')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitApproval = async () => {
    if (!simulationResult) {
      toast.error(t('cloud_intents_approval_requires_preview', 'Create a change preview before submitting approval.'));
      return;
    }
    const slug = slugify(name) || 'cloud-intent';
    const payload = {
      ...buildIntentPayload({ name, draft }),
      dry_run: false,
      idempotency_key: `cloud-intent:${slug}:${Date.now()}`,
      metadata: {
        source: 'cloud_intents_ui',
        engine: 'terraform',
        submission_channel: 'cloud_pro_mvp',
        terraform_execution: {
          engine: 'terraform',
          plan_preview: simulationResult?.terraform_plan_preview || {},
        },
      },
      simulation_snapshot: simulationResult,
      terraform_plan_preview: simulationResult?.terraform_plan_preview || {},
      change_preview_summary: {
        risk_score: simulationResult?.risk_score,
        blast_radius: simulationResult?.blast_radius,
        change_summary: simulationResult?.change_summary,
        cloud_scope: simulationResult?.cloud_scope,
      },
    };

    setSubmitting(true);
    try {
      await ApprovalService.create({
        title: `Cloud Intent: ${name}`,
        description: 'Terraform-backed cloud policy change preview awaiting approval.',
        request_type: 'intent_apply',
        payload,
        requester_comment: 'Generated from Cloud Intents MVP plan/preview flow.',
      });
      toast.success(t('cloud_intents_approval_success', 'Approval request submitted.'));
      navigate('/approval');
    } catch (error) {
      toast.error(`${t('cloud_intents_approval_failed', 'Failed to submit approval request')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <InlineLoading label={t('common_loading', 'Loading...')} />;
  }

  return (
    <div data-testid="cloud-intents-page" className="p-6 space-y-6">
      <SectionHeader
        title={t('cloud_intents_title', 'Cloud Intents')}
        subtitle={t(
          'cloud_intents_desc',
          'Define a provider-agnostic cloud policy, validate it, build a Terraform-style change preview, and submit it to approval before execution.',
        )}
        right={(
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-[#202326]"
            >
              <RefreshCw size={14} /> {t('common_refresh', 'Refresh')}
            </button>
            <Link
              to="/cloud/accounts"
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-[#202326]"
            >
              <Cloud size={14} /> {t('sidebar_cloud_accounts', 'Cloud Accounts')}
            </Link>
            <Link
              to="/approval"
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold"
            >
              <ShieldCheck size={14} /> {t('layout_page_approval', 'Approval')}
            </Link>
          </div>
        )}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <MetricCard
          title={t('cloud_intents_engine_title', 'Intent Engine')}
          value={intentStatus?.enabled ? t('cloud_intents_engine_enabled', 'Enabled') : t('cloud_intents_engine_disabled', 'Disabled')}
          hint={t('cloud_intents_engine_hint', 'Cloud change planning uses the shared intent engine.')}
        />
        <MetricCard
          title={t('cloud_intents_approval_policy_title', 'Apply Policy')}
          value={intentStatus?.apply_requires_approval ? t('cloud_intents_approval_required', 'Approval Required') : t('cloud_intents_auto_allowed', 'Auto Apply Allowed')}
          hint={t('cloud_intents_approval_policy_hint', 'Live execution stays gated by Approval Center in Pro.')}
        />
        <MetricCard
          title={t('cloud_intents_threshold_title', 'Auto Apply Risk Ceiling')}
          value={Number(intentStatus?.max_auto_apply_risk_score ?? 0)}
          hint={t('cloud_intents_threshold_hint', 'Simulation above this score stays approval-gated.')}
        />
        <MetricCard
          title={t('cloud_intents_provider_footprint_title', 'Connected Providers')}
          value={draft.providers.length}
          hint={t('cloud_intents_provider_footprint_hint', '{count} cloud accounts currently available').replace('{count}', String(accounts.length))}
        />
        <MetricCard
          title={t('cloud_intents_execution_mode_title', 'Execution Mode')}
          value={String(intentStatus?.cloud_execution_mode || 'prepare_only')}
          hint={t('cloud_intents_execution_mode_hint', 'prepare_only and mock_apply are safest for baseline validation.')}
        />
        <MetricCard
          title={t('cloud_intents_state_backend_title', 'State Backend')}
          value={String(intentStatus?.cloud_state_backend || 'local')}
          hint={String(intentStatus?.cloud_state_prefix || 'netsphere/cloud-intents')}
        />
        <MetricCard
          title={t('cloud_intents_live_apply_title', 'Live Apply')}
          value={intentStatus?.cloud_execution_live_apply_enabled ? t('cloud_intents_live_apply_on', 'Enabled') : t('cloud_intents_live_apply_off', 'Disabled')}
          hint={t('cloud_intents_live_apply_hint', 'Keep disabled until state backend and provider credentials are ready.')}
        />
        <MetricCard
          title={t('cloud_intents_runtime_title', 'Terraform Runtime')}
          value={readinessRuntime?.available ? t('cloud_intents_runtime_available', 'Available') : t('cloud_intents_runtime_missing', 'Missing')}
          hint={String(readinessRuntime?.resolved || readinessRuntime?.configured || 'terraform')}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-6">
        <SectionCard className="p-5 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <FieldLabel>{t('cloud_intents_name', 'Intent Name')}</FieldLabel>
              <div data-testid="cloud-intents-name">
                <Input
                  value={name}
                  onChange={setName}
                  placeholder={t('cloud_intents_name_placeholder', 'cloud-guardrail-baseline')}
                />
              </div>
            </div>
            <div>
              <FieldLabel>{t('cloud_intents_providers', 'Target Providers')}</FieldLabel>
              <div className="flex flex-wrap gap-2">
                {PROVIDERS.map((provider) => {
                  const active = draft.providers.includes(provider.value);
                  return (
                    <button
                      key={provider.value}
                      type="button"
                      onClick={() => toggleProvider(provider.value)}
                      className={`px-3 py-2 rounded-xl border text-sm font-semibold transition-colors ${
                        active
                          ? 'bg-blue-600 text-white border-blue-500'
                          : 'bg-white dark:bg-[#111315] border-gray-200 dark:border-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-[#1f2226]'
                      }`}
                    >
                      {provider.label} <span className="ml-1 opacity-80">({providerBuckets[provider.value] || 0})</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <FieldLabel>{t('cloud_intents_regions', 'Regions')}</FieldLabel>
              <div data-testid="cloud-intents-regions">
                <TextArea
                  value={draft.regions}
                  onChange={(value) => setDraft((prev) => ({ ...prev, regions: value }))}
                  placeholder={'ap-northeast-2\nkoreacentral'}
                  rows={3}
                />
              </div>
            </div>
            <div>
              <FieldLabel>{t('cloud_intents_resource_types', 'Resource Types')}</FieldLabel>
              <div data-testid="cloud-intents-resource-types">
                <TextArea
                  value={draft.resourceTypes}
                  onChange={(value) => setDraft((prev) => ({ ...prev, resourceTypes: value }))}
                  placeholder={'vpc\nsubnet\nroute_table\nsecurity_group'}
                  rows={3}
                />
              </div>
            </div>
          </div>

          {prefillContext ? (
            <div data-testid="cloud-intents-prefill" className="rounded-2xl border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-bold text-sky-700 dark:text-sky-300">
                    {prefillCopy.title}
                  </div>
                  <div className="mt-1 text-xs text-sky-700/90 dark:text-sky-200/80">
                    {prefillCopy.desc}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    resetDraftToDefault();
                    setPrefillContext(null);
                    navigate('/cloud/intents');
                  }}
                  className="inline-flex items-center gap-2 rounded-xl border border-sky-300 dark:border-sky-800 bg-white/80 dark:bg-sky-950/30 px-3 py-2 text-xs font-semibold text-sky-700 dark:text-sky-200 hover:bg-white dark:hover:bg-sky-900/40"
                >
                  {t('cloud_intents_prefill_clear', 'Clear scoped prefill')}
                </button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
                {prefillContext.provider ? (
                  <SummaryBadge label={`${t('cloud_accounts_provider', 'Provider')}: ${String(prefillContext.provider).toUpperCase()}`} tone="info" />
                ) : null}
                {prefillContext.templateName ? (
                  <SummaryBadge
                    label={`${t('intent_templates_template_label', 'Template')}: ${prefillContext.templateName}`}
                    tone="good"
                  />
                ) : null}
                {prefillContext.accountName || prefillContext.accountId ? (
                  <SummaryBadge
                    label={`${t('cloud_detail_account', 'Account')}: ${prefillContext.accountName || `#${String(prefillContext.accountId)}`}`}
                    tone="info"
                  />
                ) : null}
                {prefillContext.region ? (
                  <SummaryBadge label={`${t('cloud_detail_region', 'Region')}: ${prefillContext.region}`} tone="info" />
                ) : null}
                {prefillContext.resourceName ? (
                  <SummaryBadge label={`${t('cloud_detail_resource_name', 'Resource')}: ${prefillContext.resourceName}`} tone="good" />
                ) : null}
                {Array.isArray(prefillContext.resourceTypes) && prefillContext.resourceTypes.length > 0 ? (
                  <SummaryBadge label={`${t('cloud_intents_resource_types', 'Resource Types')}: ${prefillContext.resourceTypes.join(', ')}`} tone="good" />
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div>
              <FieldLabel>{t('cloud_intents_required_tags', 'Required Tags')}</FieldLabel>
              <TextArea
                value={draft.requiredTags}
                onChange={(value) => setDraft((prev) => ({ ...prev, requiredTags: value }))}
                placeholder={'owner\nenv=prod'}
                rows={5}
              />
            </div>
            <div>
              <FieldLabel>{t('cloud_intents_blocked_ingress', 'Blocked Ingress CIDRs')}</FieldLabel>
              <TextArea
                value={draft.blockedIngressCidrs}
                onChange={(value) => setDraft((prev) => ({ ...prev, blockedIngressCidrs: value }))}
                placeholder={'0.0.0.0/0'}
                rows={5}
              />
            </div>
            <div>
              <FieldLabel>{t('cloud_intents_protected_routes', 'Protected Route Destinations')}</FieldLabel>
              <TextArea
                value={draft.protectedRouteDestinations}
                onChange={(value) => setDraft((prev) => ({ ...prev, protectedRouteDestinations: value }))}
                placeholder={'0.0.0.0/0'}
                rows={5}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-4 items-end">
            <div>
              <FieldLabel>{t('cloud_intents_allowed_defaults', 'Allowed Default Route Targets')}</FieldLabel>
              <Input
                value={draft.allowedDefaultRouteTargets}
                onChange={(value) => setDraft((prev) => ({ ...prev, allowedDefaultRouteTargets: value }))}
                placeholder={t('cloud_intents_allowed_defaults_placeholder', 'nat-gateway, transit-gateway')}
              />
            </div>
            <label className="inline-flex items-center gap-3 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3 text-sm font-semibold text-gray-700 dark:text-gray-200">
              <input
                type="checkbox"
                checked={draft.enforcePrivateOnlyNextHop}
                onChange={(e) => setDraft((prev) => ({ ...prev, enforcePrivateOnlyNextHop: e.target.checked }))}
                className="rounded border-gray-300"
              />
              {t('cloud_intents_private_next_hop', 'Enforce private-only next hop')}
            </label>
          </div>

          <div className={`${PANEL_CLASS} p-4`}>
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('cloud_intents_accounts_title', 'Scoped Cloud Accounts')}</div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {t('cloud_intents_accounts_desc', 'Choose the connected accounts that should participate in Terraform plan rendering and post-check.')}
                </div>
              </div>
              <SummaryBadge label={`${eligibleAccounts.length} ${t('cloud_intents_accounts_selected_pool', 'eligible')}`} tone="info" />
            </div>

            {eligibleAccounts.length === 0 ? (
              <InlineEmpty
                className="mt-4"
                label={t('cloud_intents_no_accounts', 'No cloud accounts match the selected providers. Add cloud accounts first.')}
              />
            ) : (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
                {eligibleAccounts.map((account) => {
                  const checked = draft.accountIds.some((id) => Number(id) === Number(account.id));
                  return (
                    <label
                      key={account.id}
                      className={`rounded-xl border px-4 py-3 flex items-start gap-3 cursor-pointer transition-colors ${
                        checked
                          ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10'
                          : 'border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315]'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleAccount(account.id)}
                        className="mt-1 rounded border-gray-300"
                      />
                      <div className="min-w-0">
                        <div className="font-semibold text-gray-900 dark:text-gray-100">{account.name}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          {String(account.provider || '').toUpperCase()} · {account.region || account.credentials?.region || t('cloud_intents_region_unspecified', 'Region not specified')}
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              data-testid="cloud-intents-validate"
              type="button"
              disabled={submitting}
              onClick={handleValidate}
              className="inline-flex items-center gap-2 px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-[#202326] disabled:opacity-60"
            >
              <CheckCircle2 size={16} /> {t('cloud_intents_validate', 'Validate')}
            </button>
            <button
              data-testid="cloud-intents-simulate"
              type="button"
              disabled={submitting}
              onClick={handleSimulate}
              className="inline-flex items-center gap-2 px-4 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold disabled:opacity-60"
            >
              <Sparkles size={16} /> {t('cloud_intents_preview', 'Change Preview')}
            </button>
            <button
              data-testid="cloud-intents-submit-approval"
              type="button"
              disabled={submitting || !canSubmitApproval || !simulationResult}
              onClick={handleSubmitApproval}
              className="inline-flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold disabled:opacity-60"
            >
              <ShieldCheck size={16} /> {t('cloud_intents_submit_approval', 'Submit Approval')}
            </button>
          </div>
        </SectionCard>

        <div className="space-y-6">
          <SectionCard className="p-5 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('cloud_intents_validation_title', 'Validation')}</div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">{t('cloud_intents_validation_desc', 'Schema, cloud scope, and policy checks show up here before you generate a plan.')}</div>
              </div>
              {validationResult?.valid === true ? (
                <SummaryBadge label={t('cloud_intents_valid', 'Valid')} tone="good" />
              ) : validationResult ? (
                <SummaryBadge label={t('cloud_intents_needs_attention', 'Needs Attention')} tone="warn" />
              ) : null}
            </div>

            {!validationResult ? (
              <InlineEmpty label={t('cloud_intents_validation_empty', 'Run validation to see errors, warnings, and normalized intent details.')} />
            ) : (
              <div className="space-y-3">
                {Array.isArray(validationResult?.errors) && validationResult.errors.length > 0 && (
                  <div className="rounded-xl border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/20 p-4">
                    <div className="flex items-center gap-2 text-sm font-bold text-rose-700 dark:text-rose-300"><TriangleAlert size={16} /> {t('cloud_intents_errors', 'Errors')}</div>
                    <ul className="mt-2 space-y-1 text-sm text-rose-700 dark:text-rose-300 list-disc ml-5">
                      {validationResult.errors.map((row) => <li key={row}>{row}</li>)}
                    </ul>
                  </div>
                )}
                {Array.isArray(validationResult?.warnings) && validationResult.warnings.length > 0 && (
                  <div className="rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 p-4">
                    <div className="flex items-center gap-2 text-sm font-bold text-amber-700 dark:text-amber-300"><TriangleAlert size={16} /> {t('cloud_intents_warnings', 'Warnings')}</div>
                    <ul className="mt-2 space-y-1 text-sm text-amber-700 dark:text-amber-300 list-disc ml-5">
                      {validationResult.warnings.map((row) => <li key={row}>{row}</li>)}
                    </ul>
                  </div>
                )}
                {Array.isArray(validationResult?.conflicts) && validationResult.conflicts.length > 0 && (
                  <div className="rounded-xl border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 p-4">
                    <div className="flex items-center gap-2 text-sm font-bold text-sky-700 dark:text-sky-300"><GitBranch size={16} /> {t('cloud_intents_conflicts', 'Conflicts')}</div>
                    <pre className="mt-2 text-xs text-sky-700 dark:text-sky-300 whitespace-pre-wrap">{JSON.stringify(validationResult.conflicts, null, 2)}</pre>
                  </div>
                )}
              </div>
            )}
          </SectionCard>

          <SectionCard data-testid="cloud-intents-preview" className="p-5 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('cloud_intents_preview_title', 'Terraform-style Change Preview')}</div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">{t('cloud_intents_preview_desc', 'Use this preview to review blast radius, affected providers, and generated module blocks before approval.')}</div>
              </div>
              {previewSummary ? (
                <SummaryBadge label={`${t('cloud_intents_risk', 'Risk')} ${previewSummary.riskScore}`} tone={previewSummary.riskScore >= 70 ? 'bad' : previewSummary.riskScore >= 40 ? 'warn' : 'good'} />
              ) : null}
            </div>

            {!previewSummary ? (
              <InlineEmpty label={t('cloud_intents_preview_empty', 'Run Change Preview to see Terraform plan lines, blast radius, and operator notes.')} />
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <SummaryBadge label={`${t('cloud_intents_estimated_devices', 'Devices')} ${previewSummary.blastRadius?.estimated_devices || 0}`} tone="info" />
                  <SummaryBadge label={`${t('cloud_intents_estimated_networks', 'Networks')} ${previewSummary.blastRadius?.estimated_networks || 0}`} tone="info" />
                  <SummaryBadge label={`${t('cloud_intents_estimated_rules', 'Rules')} ${previewSummary.blastRadius?.estimated_rules || 0}`} tone="info" />
                  <SummaryBadge label={`${t('cloud_intents_scoped_resources', 'Scoped Resources')} ${previewSummary.cloudScope?.scoped_resources || 0}`} tone="info" />
                  <SummaryBadge label={`${t('cloud_intents_accounts', 'Accounts')} ${(previewSummary.plan?.summary?.accounts || 0)}`} tone="info" />
                  <SummaryBadge label={`${t('cloud_intents_regions_short', 'Regions')} ${(previewSummary.plan?.summary?.regions || 0)}`} tone="info" />
                  {previewSummary.plan?.summary?.narrow_scope_ready ? (
                    <SummaryBadge label={t('cloud_intents_narrow_scope_ready', 'Narrow Scope Ready')} tone="good" />
                  ) : null}
                </div>

                {impactSummary && (
                  <div data-testid="cloud-intents-impact" className={`${PANEL_CLASS} p-4 space-y-4`}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{t('cloud_intents_impact_title', 'Change Impact View')}</div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {t('cloud_intents_impact_desc', 'Review the exact cloud scope, risk-heavy targets, and jump straight into a filtered topology view before approval.')}
                        </div>
                      </div>
                      <Link
                        to={impactSummary.topologyPath}
                        className="inline-flex items-center gap-2 rounded-xl border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/20 px-3 py-2 text-xs font-semibold text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-950/30"
                      >
                        <MapIcon size={14} />
                        {t('cloud_intents_open_topology_impact', 'Open Topology Impact')}
                      </Link>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {impactSummary.providers.map((provider) => (
                        <SummaryBadge key={`impact-provider-${provider}`} label={`${t('cloud_accounts_provider', 'Provider')}: ${String(provider).toUpperCase()}`} tone="info" />
                      ))}
                      {impactSummary.focusedAccountId ? (
                        <SummaryBadge label={`${t('cloud_detail_account', 'Account')}: #${impactSummary.focusedAccountId}`} tone="info" />
                      ) : null}
                      {impactSummary.focusedRegion ? (
                        <SummaryBadge label={`${t('cloud_detail_region', 'Region')}: ${impactSummary.focusedRegion}`} tone="good" />
                      ) : null}
                      {impactSummary.focusedResourceName ? (
                        <SummaryBadge label={`${t('cloud_detail_resource_name', 'Resource')}: ${impactSummary.focusedResourceName}`} tone="good" />
                      ) : null}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#111315] p-4">
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{t('cloud_intents_impact_scope_breakdown', 'Scoped resource breakdown')}</div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <SummaryBadge label={`${t('cloud_intents_routes_short', 'Routes')} ${impactSummary.routeTargets}`} tone={impactSummary.routeTargets > 0 ? 'warn' : 'info'} />
                          <SummaryBadge label={`${t('cloud_intents_security_short', 'Security')} ${impactSummary.securityTargets}`} tone={impactSummary.securityTargets > 0 ? 'warn' : 'info'} />
                          <SummaryBadge label={`${t('cloud_intents_instances_short', 'Instances')} ${impactSummary.instanceTargets}`} tone={impactSummary.instanceTargets > 0 ? 'good' : 'info'} />
                          <SummaryBadge label={`${t('cloud_intents_networks_short', 'Networks')} ${impactSummary.networkTargets}`} tone={impactSummary.networkTargets > 0 ? 'info' : 'good'} />
                        </div>
                        <div className="mt-3 space-y-2 text-sm text-gray-700 dark:text-gray-300">
                          {impactSummary.resourcesByType.slice(0, 6).map((row) => (
                            <div key={`impact-type-${row.key}`} className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-black/20 px-3 py-2">
                              <span className="font-medium">{row.key}</span>
                              <span className="text-xs font-bold text-gray-500 dark:text-gray-400">{row.count}</span>
                            </div>
                          ))}
                          {impactSummary.resourcesByType.length === 0 ? (
                            <div className="text-xs text-gray-500 dark:text-gray-400">{t('cloud_intents_impact_scope_empty', 'No discovered resource types are currently in the simulation scope.')}</div>
                          ) : null}
                        </div>
                      </div>

                      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#111315] p-4">
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{t('cloud_intents_impact_provider_breakdown', 'Provider footprint')}</div>
                        <div className="mt-3 space-y-2 text-sm text-gray-700 dark:text-gray-300">
                          {impactSummary.resourcesByProvider.slice(0, 6).map((row) => {
                            const regions = Array.isArray(impactSummary.regionsByProvider?.[row.key]) ? impactSummary.regionsByProvider[row.key] : [];
                            return (
                              <div key={`impact-provider-row-${row.key}`} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-black/20 px-3 py-2">
                                <div className="flex items-center justify-between gap-3">
                                  <span className="font-medium">{String(row.key).toUpperCase()}</span>
                                  <span className="text-xs font-bold text-gray-500 dark:text-gray-400">{row.count}</span>
                                </div>
                                {regions.length > 0 ? (
                                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                    {t('cloud_intents_regions_short', 'Regions')}: {regions.join(', ')}
                                  </div>
                                ) : null}
                              </div>
                            );
                          })}
                          {impactSummary.resourcesByProvider.length === 0 ? (
                            <div className="text-xs text-gray-500 dark:text-gray-400">{t('cloud_intents_impact_provider_empty', 'Provider-level scope summary is not available for this preview yet.')}</div>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {Array.isArray(previewSummary.changeSummary) && previewSummary.changeSummary.length > 0 && (
                  <div className={`${PANEL_CLASS} p-4`}>
                    <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{t('cloud_intents_change_summary', 'Change Summary')}</div>
                    <ul className="mt-3 space-y-2 text-sm text-gray-700 dark:text-gray-300 list-disc ml-5">
                      {previewSummary.changeSummary.map((row) => <li key={row}>{row}</li>)}
                    </ul>
                  </div>
                )}

                {Array.isArray(previewSummary.recommendations) && previewSummary.recommendations.length > 0 && (
                  <div className="rounded-xl border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 p-4">
                    <div className="flex items-center gap-2 text-sm font-bold text-sky-700 dark:text-sky-300">
                      <Sparkles size={16} /> {t('cloud_intents_recommendations', 'Execution Recommendations')}
                    </div>
                    <ul className="mt-2 space-y-1 text-sm text-sky-700 dark:text-sky-300 list-disc ml-5">
                      {previewSummary.recommendations.map((row) => <li key={row}>{row}</li>)}
                    </ul>
                  </div>
                )}

                {previewSummary.preCheck && (
                  <div data-testid="cloud-intents-precheck" className={`${PANEL_CLASS} p-4 space-y-3`}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">
                          {t('cloud_intents_precheck_title', 'Pre-Check Findings')}
                        </div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {t(
                            'cloud_intents_precheck_desc',
                            'Digital Twin Lite reviews scope, exposure, readiness, and verification coverage before this intent moves into approval.',
                          )}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <SummaryBadge
                          label={`${t('cloud_intents_precheck_result', 'Result')}: ${String(previewSummary.preCheck?.summary?.result || 'pass').toUpperCase()}`}
                          tone={
                            String(previewSummary.preCheck?.summary?.result || '').toLowerCase() === 'block'
                              ? 'bad'
                              : String(previewSummary.preCheck?.summary?.result || '').toLowerCase() === 'warn'
                                ? 'warn'
                                : 'good'
                          }
                        />
                        <SummaryBadge
                          label={`${t('cloud_intents_precheck_blockers', 'Blockers')} ${Number(previewSummary.preCheck?.summary?.blockers || 0)}`}
                          tone={Number(previewSummary.preCheck?.summary?.blockers || 0) > 0 ? 'bad' : 'good'}
                        />
                        <SummaryBadge
                          label={`${t('cloud_intents_precheck_warnings', 'Warnings')} ${Number(previewSummary.preCheck?.summary?.warnings || 0)}`}
                          tone={Number(previewSummary.preCheck?.summary?.warnings || 0) > 0 ? 'warn' : 'good'}
                        />
                        <SummaryBadge
                          label={`${t('cloud_intents_precheck_checks_run', 'Checks')} ${Number(previewSummary.preCheck?.summary?.checks_run || 0)}`}
                          tone="info"
                        />
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <SummaryBadge
                        label={`${t('cloud_intents_precheck_rule_pack', 'Rule Pack')}: ${String(previewSummary.preCheck?.rule_pack?.name || 'Digital Twin Lite')}`}
                        tone="info"
                      />
                      <SummaryBadge
                        label={`${t('cloud_intents_precheck_mode', 'Mode')}: ${String(previewSummary.preCheck?.rule_pack?.mode || 'explainable')}`}
                        tone="info"
                      />
                      <SummaryBadge
                        label={`${t('cloud_intents_precheck_version', 'Version')}: ${String(previewSummary.preCheck?.rule_pack?.version || '2026.03')}`}
                        tone="info"
                      />
                    </div>

                    {Array.isArray(previewSummary.preCheck?.findings) && previewSummary.preCheck.findings.length > 0 ? (
                      <div className="space-y-2">
                        {previewSummary.preCheck.findings.map((finding, idx) => {
                          const severity = String(finding?.severity || 'info').toLowerCase();
                          const tone =
                            severity === 'critical' ? 'rose'
                              : severity === 'warning' ? 'amber'
                                : 'sky';
                          const panelClass =
                            tone === 'rose'
                              ? 'border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300'
                              : tone === 'amber'
                                ? 'border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300'
                                : 'border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 text-sky-700 dark:text-sky-300';
                          return (
                            <div key={`${String(finding?.key || finding?.title || 'precheck')}-${idx}`} className={`rounded-xl border p-3 ${panelClass}`}>
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="text-sm font-bold">{String(finding?.title || '-')}</div>
                                <div className="flex flex-wrap gap-2">
                                  <SummaryBadge
                                    label={String(severity).toUpperCase()}
                                    tone={severity === 'critical' ? 'bad' : severity === 'warning' ? 'warn' : 'info'}
                                  />
                                  {finding?.category ? (
                                    <SummaryBadge label={String(finding.category)} tone="info" />
                                  ) : null}
                                  {finding?.blocking ? (
                                    <SummaryBadge label={t('cloud_intents_precheck_blocking', 'Review blocker')} tone="bad" />
                                  ) : null}
                                </div>
                              </div>
                              <div className="mt-2 text-xs">{String(finding?.message || '')}</div>
                              {finding?.recommendation ? (
                                <div className="mt-2 text-xs font-medium opacity-90">{String(finding.recommendation)}</div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 p-4 text-sm text-emerald-700 dark:text-emerald-300">
                        {t('cloud_intents_precheck_clear', 'No pre-check issues are currently blocking approval review for this preview.')}
                      </div>
                    )}
                  </div>
                )}

                {previewSummary.beforeAfterCompare && Array.isArray(previewSummary.beforeAfterCompare?.cards) && previewSummary.beforeAfterCompare.cards.length > 0 && (
                  <div data-testid="cloud-intents-before-after" className={`${PANEL_CLASS} p-4 space-y-3`}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">
                          {t('cloud_intents_before_after_title', 'Before / After Compare')}
                        </div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {t(
                            'cloud_intents_before_after_desc',
                            'Use this compare view to explain what changes in scope discipline, readiness, and operating posture before the intent moves into execution.',
                          )}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <SummaryBadge
                          label={`${t('cloud_intents_before_after_result', 'Compare Result')}: ${String(previewSummary.beforeAfterCompare?.summary?.result || 'review').toUpperCase()}`}
                          tone={
                            String(previewSummary.beforeAfterCompare?.summary?.result || '').toLowerCase() === 'blocked'
                              ? 'bad'
                              : String(previewSummary.beforeAfterCompare?.summary?.result || '').toLowerCase() === 'ready'
                                ? 'good'
                                : 'warn'
                          }
                        />
                        <SummaryBadge
                          label={`${t('cloud_intents_before_after_cards', 'Cards')} ${Number(previewSummary.beforeAfterCompare?.summary?.cards || 0)}`}
                          tone="info"
                        />
                        <SummaryBadge
                          label={`${t('cloud_intents_before_after_ready', 'Ready')} ${Number(previewSummary.beforeAfterCompare?.summary?.ready_cards || 0)}`}
                          tone="good"
                        />
                        <SummaryBadge
                          label={`${t('cloud_intents_before_after_review', 'Review')} ${Number(previewSummary.beforeAfterCompare?.summary?.review_cards || 0)}`}
                          tone="warn"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                      {previewSummary.beforeAfterCompare.cards.map((card, idx) => {
                        const tone = String(card?.tone || 'info').toLowerCase();
                        const panelClass =
                          tone === 'bad'
                            ? 'border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300'
                            : tone === 'warn'
                              ? 'border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300'
                              : tone === 'good'
                                ? 'border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300'
                                : 'border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 text-sky-700 dark:text-sky-300';
                        return (
                          <div key={`${String(card?.key || 'compare')}-${idx}`} className={`rounded-xl border p-4 ${panelClass}`}>
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="text-sm font-bold">{String(card?.title || '-')}</div>
                              <SummaryBadge
                                label={String(card?.status || 'review').toUpperCase()}
                                tone={tone === 'bad' ? 'bad' : tone === 'warn' ? 'warn' : tone === 'good' ? 'good' : 'info'}
                              />
                            </div>
                            <div className="mt-3 space-y-3 text-sm">
                              <div>
                                <div className="text-[11px] uppercase tracking-[0.18em] font-bold opacity-75">
                                  {t('cloud_intents_before_after_before', 'Current')}
                                </div>
                                <div className="mt-1">{String(card?.before || '')}</div>
                              </div>
                              <div>
                                <div className="text-[11px] uppercase tracking-[0.18em] font-bold opacity-75">
                                  {t('cloud_intents_before_after_after', 'With intent')}
                                </div>
                                <div className="mt-1">{String(card?.after || '')}</div>
                              </div>
                              {card?.recommendation ? (
                                <div className="text-xs font-medium opacity-90">{String(card.recommendation)}</div>
                              ) : null}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div className={`${PANEL_CLASS} p-4`}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{t('cloud_intents_execution_continuity_title', 'Execution Continuity')}</div>
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {t('cloud_intents_execution_continuity_desc', 'Confirm what will be verified after apply, how rollback is handled, and which evidence artifacts will be captured.')}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <SummaryBadge
                        label={`${t('cloud_intents_post_check_title', 'Post-check plan')} ${Array.isArray(previewSummary.plan?.post_check_plan?.steps) ? previewSummary.plan.post_check_plan.steps.length : 0}`}
                        tone={Array.isArray(previewSummary.plan?.post_check_plan?.steps) && previewSummary.plan.post_check_plan.steps.length > 0 ? 'good' : 'info'}
                      />
                      <SummaryBadge
                        label={
                          previewSummary.rollbackPlan?.automatic_enabled
                            ? t('cloud_intents_rollback_auto_enabled', 'Auto rollback enabled')
                            : t('cloud_intents_rollback_auto_disabled', 'Manual rollback review')
                        }
                        tone={previewSummary.rollbackPlan?.automatic_enabled ? 'warn' : 'info'}
                      />
                      <SummaryBadge
                        label={`${t('cloud_intents_evidence_title', 'Evidence package')} ${Array.isArray(previewSummary.plan?.evidence_plan?.artifacts) ? previewSummary.plan.evidence_plan.artifacts.length : 0}`}
                        tone="info"
                      />
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 p-4">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-300 font-bold">
                        {t('cloud_intents_post_check_title', 'Post-check plan')}
                      </div>
                      <ul className="mt-2 space-y-1 text-xs text-emerald-700 dark:text-emerald-300 list-disc ml-5">
                        {(previewSummary.plan?.post_check_plan?.steps || []).slice(0, 3).map((row) => <li key={row}>{row}</li>)}
                      </ul>
                    </div>
                    <div className="rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 p-4">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300 font-bold">
                        {t('cloud_intents_rollback_title', 'Rollback plan')}
                      </div>
                      <div className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                        {t('cloud_intents_rollback_strategy', 'Strategy')}: {String(previewSummary.rollbackPlan?.strategy || 'terraform_state_reconcile')}
                      </div>
                      <ul className="mt-2 space-y-1 text-xs text-amber-700 dark:text-amber-300 list-disc ml-5">
                        {(previewSummary.rollbackPlan?.operator_steps || []).slice(0, 3).map((row) => <li key={row}>{row}</li>)}
                      </ul>
                    </div>
                    <div className="rounded-xl border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 p-4">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-sky-700 dark:text-sky-300 font-bold">
                        {t('cloud_intents_evidence_title', 'Evidence package')}
                      </div>
                      <ul className="mt-2 space-y-1 text-xs text-sky-700 dark:text-sky-300 list-disc ml-5">
                        {(previewSummary.plan?.evidence_plan?.artifacts || []).slice(0, 4).map((row) => <li key={row}>{row}</li>)}
                      </ul>
                    </div>
                  </div>
                </div>

                {previewSummary.operationalGuardrails && (
                  <div data-testid="cloud-intents-guardrails" className={`${PANEL_CLASS} p-4 space-y-3`}>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{t('cloud_intents_guardrails_title', 'Operational guardrails')}</div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {t('cloud_intents_guardrails_desc', 'Product guardrails explain what keeps this intent in preview, approval-only, or change-enabled mode.')}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <SummaryBadge
                          label={`${t('cloud_intents_guardrails_change_enabled', 'Change-enabled')} ${Number(previewSummary.operationalGuardrails?.summary?.change_enabled_accounts || 0)}`}
                          tone="good"
                        />
                        <SummaryBadge
                          label={`${t('cloud_intents_guardrails_read_only', 'Read-only')} ${Number(previewSummary.operationalGuardrails?.summary?.read_only_accounts || 0)}`}
                          tone={Number(previewSummary.operationalGuardrails?.summary?.read_only_accounts || 0) > 0 ? 'warn' : 'info'}
                        />
                        <SummaryBadge
                          label={`${t('cloud_intents_guardrails_critical', 'Critical')} ${Number(previewSummary.operationalGuardrails?.summary?.critical_findings || 0)}`}
                          tone={Number(previewSummary.operationalGuardrails?.summary?.critical_findings || 0) > 0 ? 'bad' : 'good'}
                        />
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <SummaryBadge
                        label={
                          previewSummary.operationalGuardrails?.summary?.approval_required
                            ? t('cloud_intents_approval_required', 'Approval Required')
                            : t('cloud_intents_auto_allowed', 'Auto Apply Allowed')
                        }
                        tone={previewSummary.operationalGuardrails?.summary?.approval_required ? 'warn' : 'good'}
                      />
                      <SummaryBadge
                        label={`${t('cloud_intents_execution_mode_title', 'Execution Mode')}: ${String(previewSummary.operationalGuardrails?.summary?.global_mode || intentStatus?.cloud_execution_mode || 'prepare_only')}`}
                        tone="info"
                      />
                      <SummaryBadge
                        label={`${t('cloud_intents_state_backend_title', 'State Backend')}: ${String(previewSummary.operationalGuardrails?.summary?.state_backend || intentStatus?.cloud_state_backend || 'local')}`}
                        tone="info"
                      />
                    </div>

                    {Array.isArray(previewSummary.operationalGuardrails?.findings) && previewSummary.operationalGuardrails.findings.length > 0 && (
                      <div className="space-y-2">
                        {previewSummary.operationalGuardrails.findings.map((finding, idx) => {
                          const severity = String(finding?.severity || 'info').toLowerCase();
                          const tone =
                            severity === 'critical' ? 'rose'
                              : severity === 'warning' ? 'amber'
                                : 'sky';
                          const panelClass =
                            tone === 'rose'
                              ? 'border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300'
                              : tone === 'amber'
                                ? 'border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300'
                                : 'border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 text-sky-700 dark:text-sky-300';
                          return (
                            <div key={`${String(finding?.key || finding?.title || 'finding')}-${idx}`} className={`rounded-xl border p-3 ${panelClass}`}>
                              <div className="flex items-center justify-between gap-3">
                                <div className="text-sm font-bold">{String(finding?.title || '-')}</div>
                                <SummaryBadge label={String(severity).toUpperCase()} tone={severity === 'critical' ? 'bad' : severity === 'warning' ? 'warn' : 'info'} />
                              </div>
                              <div className="mt-2 text-xs">{String(finding?.message || '')}</div>
                              {finding?.recommendation ? (
                                <div className="mt-2 text-xs font-medium opacity-90">{String(finding.recommendation)}</div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {Array.isArray(previewSummary.operationalGuardrails?.account_modes) && previewSummary.operationalGuardrails.account_modes.length > 0 && (
                      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#111315] p-4">
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{t('cloud_intents_guardrails_accounts', 'Scoped account execution mode')}</div>
                        <div className="mt-3 space-y-2">
                          {previewSummary.operationalGuardrails.account_modes.map((row) => (
                            <div key={`${row.provider}-${row.account_id}`} className="rounded-lg border border-gray-200 dark:border-gray-800 px-3 py-2 bg-gray-50 dark:bg-black/20">
                              <div className="flex flex-wrap items-center gap-2">
                                <SummaryBadge label={String(row.provider || '').toUpperCase()} tone="info" />
                                <SummaryBadge
                                  label={row.change_enabled ? t('cloud_intents_guardrails_change_enabled_single', 'Change-enabled') : t('cloud_intents_guardrails_read_only_single', 'Read-only')}
                                  tone={row.change_enabled ? 'good' : 'warn'}
                                />
                                <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{String(row.name || row.account_id)}</span>
                              </div>
                              <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{String(row.change_mode_reason || '')}</div>
                              {Array.isArray(row.missing_fields) && row.missing_fields.length > 0 ? (
                                <div className="mt-1 text-xs text-amber-600 dark:text-amber-300">
                                  {t('cloud_accounts_exec_missing_fields', 'Missing')}: {row.missing_fields.join(', ')}
                                </div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {previewSummary && (
                  <div className={`${PANEL_CLASS} p-4 space-y-3`}>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">
                          {t('cloud_intents_risk_panel_title', 'High-risk change checks')}
                        </div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {t('cloud_intents_risk_panel_desc', 'Review cost-heavy, edge-routing, and public exposure signals before you move into approval.')}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <SummaryBadge
                          label={`${t('cloud_intents_risk', 'Risk')} ${previewSummary.riskScore}`}
                          tone={previewSummary.riskScore >= 70 ? 'bad' : previewSummary.riskScore >= 40 ? 'warn' : 'good'}
                        />
                        <SummaryBadge
                          label={
                            guardrailSignals.count > 0
                              ? t('cloud_intents_risk_panel_attention', 'Operator review recommended')
                              : t('cloud_intents_risk_panel_clear', 'No elevated cloud guardrails')
                          }
                          tone={guardrailSignals.count > 0 ? 'warn' : 'good'}
                        />
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {guardrailSignals.publicIngress && (
                        <SummaryBadge label={t('cloud_intents_risk_public_ingress', 'Public ingress')} tone="bad" />
                      )}
                      {guardrailSignals.defaultRoute && (
                        <SummaryBadge label={t('cloud_intents_risk_default_route', 'Default route')} tone="bad" />
                      )}
                      {guardrailSignals.highImpactEdges && (
                        <SummaryBadge label={t('cloud_intents_risk_edge_resources', 'NAT / LB / VPN / TGW')} tone="bad" />
                      )}
                      {guardrailSignals.broadCidr && (
                        <SummaryBadge label={t('cloud_intents_risk_broad_cidr', 'Broad CIDR')} tone="warn" />
                      )}
                      {guardrailSignals.broadScope && (
                        <SummaryBadge label={t('cloud_intents_risk_broad_scope', 'Wide rollout scope')} tone="warn" />
                      )}
                      {guardrailSignals.readOnlyAccounts && (
                        <SummaryBadge label={t('cloud_intents_risk_read_only_accounts', 'Read-only accounts in scope')} tone="warn" />
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Link
                        to={impactSummary?.cloudAccountsPath || '/cloud/accounts'}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 px-3 py-1.5 text-xs font-semibold text-sky-700 dark:text-sky-300 hover:border-sky-300 dark:hover:border-sky-700/80"
                      >
                        <Cloud size={14} /> {t('cloud_intents_open_cloud_accounts', 'Open Cloud Accounts')}
                      </Link>
                      <Link
                        to="/approval"
                        className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#111315] px-3 py-1.5 text-xs font-semibold text-gray-700 dark:text-gray-200 hover:border-blue-300 dark:hover:border-blue-700/80"
                      >
                        <ShieldCheck size={14} /> {t('cloud_intents_go_approval_hint', 'Approval Center')}
                      </Link>
                    </div>
                  </div>
                )}

                <div className={`${PANEL_CLASS} p-4`}>
                  <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{t('cloud_intents_execution_ready_title', 'Execution Readiness')}</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <SummaryBadge label={`${t('cloud_intents_execution_mode_title', 'Execution Mode')}: ${String(intentStatus?.cloud_execution_mode || 'prepare_only')}`} tone="info" />
                    <SummaryBadge label={`${t('cloud_intents_state_backend_title', 'State Backend')}: ${String(intentStatus?.cloud_state_backend || 'local')}`} tone="info" />
                    <SummaryBadge
                      label={readinessBackend?.valid ? t('cloud_intents_backend_ready', 'Backend Ready') : t('cloud_intents_backend_attention', 'Backend Needs Attention')}
                      tone={readinessBackend?.valid ? 'good' : 'warn'}
                    />
                    <SummaryBadge
                      label={readinessRuntime?.available ? t('cloud_intents_runtime_available', 'Available') : t('cloud_intents_runtime_missing', 'Missing')}
                      tone={readinessRuntime?.available ? 'good' : 'bad'}
                    />
                    <SummaryBadge
                      label={
                        executionReadiness?.ready_for_real_apply
                          ? t('cloud_intents_live_apply_ready', 'Live Apply Enabled')
                          : t('cloud_intents_live_apply_guarded', 'Live Apply Guarded')
                      }
                      tone={executionReadiness?.ready_for_real_apply ? 'warn' : 'good'}
                    />
                  </div>
                  <div className="mt-3 text-xs text-gray-500 dark:text-gray-400 space-y-1">
                    <div>{t('cloud_intents_execution_ready_line_1', '1. Register provider credentials in Cloud Accounts.')}</div>
                    <div>{t('cloud_intents_execution_ready_line_2', '2. Start with prepare_only, then mock_apply, then real_apply.')}</div>
                    <div>{t('cloud_intents_execution_ready_line_3', '3. Use a remote state backend for multi-user production runs.')}</div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Link
                      to={impactSummary?.cloudAccountsPath || '/cloud/accounts'}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 px-3 py-1.5 text-xs font-semibold text-sky-700 dark:text-sky-300 hover:border-sky-300 dark:hover:border-sky-700/80"
                    >
                      <Cloud size={14} /> {t('cloud_intents_open_cloud_accounts', 'Open Cloud Accounts')}
                    </Link>
                  </div>
                  {readinessErrors.length > 0 && (
                    <div className="mt-4 rounded-xl border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/20 p-4">
                      <div className="flex items-center gap-2 text-sm font-bold text-rose-700 dark:text-rose-300">
                        <TriangleAlert size={16} /> {t('cloud_intents_execution_ready_fix', 'Resolve before real apply')}
                      </div>
                      <ul className="mt-2 space-y-1 text-sm text-rose-700 dark:text-rose-300 list-disc ml-5">
                        {readinessErrors.map((row) => <li key={row}>{row}</li>)}
                      </ul>
                    </div>
                  )}
                  {readinessWarnings.length > 0 && (
                    <div className="mt-4 rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 p-4">
                      <div className="flex items-center gap-2 text-sm font-bold text-amber-700 dark:text-amber-300">
                        <TriangleAlert size={16} /> {t('cloud_intents_warnings', 'Warnings')}
                      </div>
                      <ul className="mt-2 space-y-1 text-sm text-amber-700 dark:text-amber-300 list-disc ml-5">
                        {readinessWarnings.map((row) => <li key={row}>{row}</li>)}
                      </ul>
                    </div>
                  )}
                  {readinessErrors.length === 0 && readinessWarnings.length === 0 && (
                    <div className="mt-4 rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 p-4">
                      <div className="flex items-center gap-2 text-sm font-bold text-emerald-700 dark:text-emerald-300">
                        <CheckCircle2 size={16} /> {t('cloud_intents_execution_ready_clear', 'Execution prerequisites look clear for the selected mode.')}
                      </div>
                    </div>
                  )}
                </div>

                <div className={`${PANEL_CLASS} p-4 space-y-3`}>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{t('cloud_intents_plan_title', 'Plan Blocks')}</div>
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {previewSummary.plan?.workspace_prefix || 'netsphere-workspace'} · {previewSummary.plan?.engine || 'terraform'}
                      </div>
                    </div>
                    <Link
                      to="/approval"
                      className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-600 dark:text-blue-300 hover:text-blue-500"
                    >
                      {t('cloud_intents_go_approval_hint', 'Approval Center')}
                    </Link>
                  </div>

                  {Array.isArray(previewSummary.plan?.change_blocks) && previewSummary.plan.change_blocks.length > 0 && (
                    <div className="grid grid-cols-1 gap-3">
                      {previewSummary.plan.change_blocks.map((block, idx) => (
                        <div key={`${block.provider}-${block.module}-${idx}`} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#111315] p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <SummaryBadge label={String(block.provider || '').toUpperCase()} tone="info" />
                            <SummaryBadge label={block.module || 'module'} tone="info" />
                            <SummaryBadge label={`${t('cloud_intents_resources', 'Resources')} ${block.resource_count || 0}`} tone="good" />
                            {Array.isArray(block.targeted_resource_types) && block.targeted_resource_types.length > 0 ? (
                              <SummaryBadge label={block.targeted_resource_types.join(', ')} tone="info" />
                            ) : null}
                          </div>
                          {Array.isArray(block.changes) && block.changes.length > 0 && (
                            <ul className="mt-3 space-y-1 text-xs text-gray-600 dark:text-gray-300 list-disc ml-5">
                              {block.changes.map((line) => <li key={line}>{line}</li>)}
                            </ul>
                          )}
                          {Array.isArray(block.verification_checks) && block.verification_checks.length > 0 && (
                            <div className="mt-3 rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 p-3">
                              <div className="text-[11px] uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-300 font-bold">
                                {t('cloud_intents_post_check_title', 'Post-check plan')}
                              </div>
                              <ul className="mt-2 space-y-1 text-xs text-emerald-700 dark:text-emerald-300 list-disc ml-5">
                                {block.verification_checks.map((line) => <li key={line}>{line}</li>)}
                              </ul>
                            </div>
                          )}
                          {Array.isArray(block.risk_hints) && block.risk_hints.length > 0 && (
                            <div className="mt-3 rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 p-3">
                              <div className="text-[11px] uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300 font-bold">
                                {t('cloud_intents_risk_hints', 'Risk hints')}
                              </div>
                              <ul className="mt-2 space-y-1 text-xs text-amber-700 dark:text-amber-300 list-disc ml-5">
                                {block.risk_hints.map((line) => <li key={line}>{line}</li>)}
                              </ul>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {Array.isArray(previewSummary.plan?.plan_lines) && previewSummary.plan.plan_lines.length > 0 && (
                    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-[#0b1020] text-slate-100 p-4 overflow-x-auto">
                      <pre className="text-xs whitespace-pre-wrap">{previewSummary.plan.plan_lines.join('\n')}</pre>
                    </div>
                  )}

                  {Array.isArray(previewSummary.plan?.operator_notes) && previewSummary.plan.operator_notes.length > 0 && (
                    <div className="rounded-xl border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 p-4">
                      <div className="flex items-center gap-2 text-sm font-bold text-sky-700 dark:text-sky-300">
                        <ExternalLink size={16} /> {t('cloud_intents_operator_notes', 'Operator Notes')}
                      </div>
                      <ul className="mt-2 space-y-1 text-sm text-sky-700 dark:text-sky-300 list-disc ml-5">
                        {previewSummary.plan.operator_notes.map((row) => <li key={row}>{row}</li>)}
                      </ul>
                    </div>
                  )}

                  {Array.isArray(previewSummary.plan?.post_check_plan?.steps) && previewSummary.plan.post_check_plan.steps.length > 0 && (
                    <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 p-4">
                      <div className="flex items-center gap-2 text-sm font-bold text-emerald-700 dark:text-emerald-300">
                        <CheckCircle2 size={16} /> {t('cloud_intents_post_check_title', 'Post-check plan')}
                      </div>
                      <ul className="mt-2 space-y-1 text-sm text-emerald-700 dark:text-emerald-300 list-disc ml-5">
                        {previewSummary.plan.post_check_plan.steps.map((row) => <li key={row}>{row}</li>)}
                      </ul>
                    </div>
                  )}

                  {Array.isArray(previewSummary.plan?.evidence_plan?.artifacts) && previewSummary.plan.evidence_plan.artifacts.length > 0 && (
                    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#111315] p-4">
                      <div className="text-sm font-bold text-gray-900 dark:text-gray-100">
                        {t('cloud_intents_evidence_title', 'Evidence package')}
                      </div>
                      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        {(previewSummary.plan?.evidence_plan?.operator_package_sections || []).join(' · ')}
                      </div>
                      <ul className="mt-3 space-y-1 text-xs text-gray-600 dark:text-gray-300 list-disc ml-5">
                        {previewSummary.plan.evidence_plan.artifacts.map((row) => <li key={row}>{row}</li>)}
                      </ul>
                    </div>
                  )}

                  {previewSummary.rollbackPlan && Array.isArray(previewSummary.rollbackPlan.operator_steps) && previewSummary.rollbackPlan.operator_steps.length > 0 && (
                    <div className="rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 p-4">
                      <div className="flex items-center gap-2 text-sm font-bold text-amber-700 dark:text-amber-300">
                        <GitBranch size={16} /> {t('cloud_intents_rollback_title', 'Rollback plan')}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <SummaryBadge
                          label={
                            previewSummary.rollbackPlan.automatic_enabled
                              ? t('cloud_intents_rollback_auto_enabled', 'Auto rollback enabled')
                              : t('cloud_intents_rollback_auto_disabled', 'Manual rollback review')
                          }
                          tone={previewSummary.rollbackPlan.automatic_enabled ? 'warn' : 'info'}
                        />
                        <SummaryBadge
                          label={`${t('cloud_intents_rollback_strategy', 'Strategy')}: ${String(previewSummary.rollbackPlan.strategy || 'terraform_state_reconcile')}`}
                          tone="info"
                        />
                      </div>
                      <ul className="mt-3 space-y-1 text-sm text-amber-700 dark:text-amber-300 list-disc ml-5">
                        {previewSummary.rollbackPlan.operator_steps.map((row) => <li key={row}>{row}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}
          </SectionCard>
        </div>
      </div>
    </div>
  );
};

export default CloudIntentsPage;
