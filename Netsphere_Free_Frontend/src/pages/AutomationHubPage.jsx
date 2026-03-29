import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import ReactFlow, { Background, Controls, MiniMap, Panel, useEdgesState, useNodesState } from 'reactflow';
import 'reactflow/dist/style.css';
import { ExternalLink, Play, RefreshCw, Workflow, Scan, Activity, Zap, Shield, FileCheck, Blocks } from 'lucide-react';
import { DeviceService, DiscoveryHintService, DiscoveryService } from '../api/services';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { useNavigate } from 'react-router-dom';
import { getApiBaseUrl } from '../api/baseUrl';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';

const API_BASE_URL = getApiBaseUrl();

const hashToVariant = (key) => {
  const s = String(key || 'anonymous');
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) % 2 === 0 ? 'A' : 'B';
};

const makeNode = (type, position) => {
  const id = `${type}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  return {
    id,
    type: 'default',
    position,
    data: {
      label: type,
      stepType: type,
      configText: '{}',
    },
  };
};

const getWorkflowOrder = (nodes, edges) => {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const out = new Map();
  const inDeg = new Map();
  for (const n of nodes) {
    out.set(n.id, []);
    inDeg.set(n.id, 0);
  }
  for (const e of edges) {
    const s = String(e.source || '');
    const t = String(e.target || '');
    if (!byId.has(s) || !byId.has(t)) continue;
    out.get(s).push(t);
    inDeg.set(t, (inDeg.get(t) || 0) + 1);
  }
  const q = [];
  for (const [id, deg] of inDeg.entries()) {
    if (!deg) q.push(id);
  }
  const ordered = [];
  while (q.length) {
    q.sort((a, b) => {
      const ax = byId.get(a)?.position?.x ?? 0;
      const bx = byId.get(b)?.position?.x ?? 0;
      return ax - bx;
    });
    const id = q.shift();
    ordered.push(id);
    for (const nxt of out.get(id) || []) {
      inDeg.set(nxt, (inDeg.get(nxt) || 0) - 1);
      if (inDeg.get(nxt) === 0) q.push(nxt);
    }
  }
  if (ordered.length !== nodes.length) {
    return [...nodes].sort((a, b) => (a.position?.x ?? 0) - (b.position?.x ?? 0)).map((n) => n.id);
  }
  return ordered;
};

const safeJsonParse = (s, fallback = {}) => {
  try {
    const v = JSON.parse(String(s || ''));
    return v && typeof v === 'object' ? v : fallback;
  } catch (e) {
    return fallback;
  }
};

const endpointByStepType = (stepType) => {
  const t = String(stepType || '').toLowerCase();
  if (t === 'template') return 'template';
  if (t === 'fault-tolerance') return 'fault-tolerance';
  if (t === 'qos-autoscale') return 'qos-autoscale';
  if (t === 'acl-enforce') return 'acl-enforce';
  if (t === 'discovery') return 'discovery';
  return null;
};

const modulePalette = [
  { key: 'discovery', title: 'Auto Discovery', desc: 'Auto detect and register network devices.' },
  { key: 'template', title: 'Template Automation', desc: 'Apply templates to selected devices.' },
  { key: 'fault-tolerance', title: 'Fault-Tolerance', desc: 'Auto recovery workflow for failure events.' },
  { key: 'qos-autoscale', title: 'QoS Autoscaling', desc: 'Scale policy by traffic thresholds.' },
  { key: 'acl-enforce', title: 'Auto ACL', desc: 'Enforce ACL when policy violations occur.' },
];

const AutomationHubPage = () => {
  useLocaleRerender();
  const { user, isAtLeast } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const canView = isAtLeast('operator');
  const canTuneHints = isAtLeast('admin');
  const [variant] = useState(() => {
    const existing = localStorage.getItem('ab.automationHub.variant');
    if (existing === 'A' || existing === 'B') return existing;
    const v = hashToVariant(user?.username || user?.full_name || user?.id);
    localStorage.setItem('ab.automationHub.variant', v);
    return v;
  });

  const [deviceCount, setDeviceCount] = useState(0);
  const [templateCount, setTemplateCount] = useState(0);
  const [policyCount, setPolicyCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [runLoading, setRunLoading] = useState(false);
  const [runLog, setRunLog] = useState('');
  const [usage, setUsage] = useState(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [hintSummary, setHintSummary] = useState(null);
  const [hintAdjustmentsApplying, setHintAdjustmentsApplying] = useState(false);
  const [hintAliasesApplying, setHintAliasesApplying] = useState(false);
  const [hintSeedRulesApplying, setHintSeedRulesApplying] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState(5);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [viewMode, setViewMode] = useState('overview');

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const rfWrapperRef = useRef(null);

  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return nodes.find((n) => String(n.id) === String(selectedNodeId)) || null;
  }, [nodes, selectedNodeId]);

  const [discoveryStatus, setDiscoveryStatus] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [managedSummaryRes, tplRes, polRes, discRes, hintSummaryRes] = await Promise.allSettled([
        DeviceService.getManagedSummary(),
        DeviceService.getTemplates(),
        DeviceService.getPolicies?.() || Promise.resolve({ data: [] }),
        DiscoveryService.getKpiSummary({ days: 1, limit: 1 }),
        DiscoveryHintService.getSummary({ benchmark_limit: 250 }),
      ]);

      const managedSummary = managedSummaryRes.status === 'fulfilled' ? managedSummaryRes.value?.data || {} : {};
      const templatesPayload = tplRes.status === 'fulfilled' ? tplRes.value?.data : [];
      const policiesPayload = polRes.status === 'fulfilled' ? polRes.value?.data : [];
      const discoveryPayload = discRes.status === 'fulfilled' ? discRes.value?.data : null;
      const hintPayload = hintSummaryRes.status === 'fulfilled' ? hintSummaryRes.value?.data : null;

      setDeviceCount(Number(managedSummary?.total_discovered || 0));
      setTemplateCount(Array.isArray(templatesPayload) ? templatesPayload.length : 0);
      setPolicyCount(Array.isArray(policiesPayload) ? policiesPayload.length : 0);
      const latest =
        Array.isArray(discoveryPayload?.jobs) && discoveryPayload.jobs.length > 0
          ? discoveryPayload.jobs[0]
          : null;
      setDiscoveryStatus({
        status: String(latest?.status || 'idle').trim().toLowerCase() || 'idle',
        job_id: latest?.job_id ?? null,
        created_at: latest?.created_at ?? null,
      });
      setHintSummary(hintPayload || null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!canView) return;
    load();
  }, [canView, load]);

  useEffect(() => {
    if (!canView || loading) return undefined;
    try {
      const timeoutId = window.setTimeout(() => {
        const token = localStorage.getItem('authToken');
        fetch(`${API_BASE_URL}/automation-hub/track`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify({ event: 'view', variant }),
        }).catch(() => {});
      }, 800);
      return () => window.clearTimeout(timeoutId);
    } catch (e) {
      console.error(e);
      return undefined;
    }
  }, [canView, loading, variant]);

  useEffect(() => {
    if (!canView || loading || viewMode !== 'overview') return undefined;
    setUsageLoading(true);
    let cancelled = false;
    const timeoutId = window.setTimeout(() => {
      (async () => {
        try {
          const token = localStorage.getItem('authToken');
          const res = await fetch(`${API_BASE_URL}/automation-hub/usage?days=14`, {
            headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          });
          const json = await res.json().catch(() => ({}));
          if (!cancelled) {
            setUsage(res.ok ? json : null);
          }
        } finally {
          if (!cancelled) {
            setUsageLoading(false);
          }
        }
      })();
    }, 600);
    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [canView, loading, viewMode]);

  const submitFeedback = async () => {
    setFeedbackSending(true);
    try {
      const token = localStorage.getItem('authToken');
      await fetch(`${API_BASE_URL}/automation-hub/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ rating: Number(feedbackRating || 0), comment: feedbackComment, variant }),
      });
      setFeedbackComment('');
    } finally {
      setFeedbackSending(false);
    }
  };

  const applyHintScoreAdjustments = async () => {
    if (!allHintScoreAdjustments.length || hintAdjustmentsApplying) return;
    const confirmed = window.confirm(
      t(
        'automation_hub_hint_apply_score_adjustments_confirm',
        'Apply the suggested discovery hint score adjustments now?'
      ).replace('{count}', String(allHintScoreAdjustments.length))
    );
    if (!confirmed) return;
    setHintAdjustmentsApplying(true);
    try {
      const response = await DiscoveryHintService.applyScoreAdjustments({
        rule_keys: allHintScoreAdjustments.map((item) => String(item.rule_key || '').trim()).filter(Boolean),
      });
      const applied = Number(response?.data?.applied || 0);
      toast.success(
        t(
          'automation_hub_hint_apply_score_adjustments_success',
          'Applied {count} suggested score adjustments.'
        ).replace('{count}', String(applied))
      );
      await load();
    } catch (error) {
      toast.error(
        `${t('automation_hub_hint_apply_score_adjustments_failed', 'Failed to apply suggested score adjustments')}: ${
          error?.response?.data?.detail?.message ||
          error?.response?.data?.detail ||
          error?.message ||
          ''
        }`
      );
    } finally {
      setHintAdjustmentsApplying(false);
    }
  };

  const applyHintAliasCandidates = async () => {
    if (!allHintAliasCandidates.length || hintAliasesApplying) return;
    const confirmed = window.confirm(
      t(
        'automation_hub_hint_apply_alias_candidates_confirm',
        'Apply the suggested vendor alias candidates now?'
      ).replace('{count}', String(allHintAliasCandidates.length))
    );
    if (!confirmed) return;
    setHintAliasesApplying(true);
    try {
      const response = await DiscoveryHintService.applyAliasCandidates({
        raw_vendors: allHintAliasCandidates.map((item) => String(item.raw_vendor || '').trim()).filter(Boolean),
      });
      const applied = Number(response?.data?.applied || 0);
      toast.success(
        t(
          'automation_hub_hint_apply_alias_candidates_success',
          'Applied {count} suggested vendor aliases.'
        ).replace('{count}', String(applied))
      );
      await load();
    } catch (error) {
      toast.error(
        `${t('automation_hub_hint_apply_alias_candidates_failed', 'Failed to apply suggested vendor aliases')}: ${
          error?.response?.data?.detail?.message ||
          error?.response?.data?.detail ||
          error?.message ||
          ''
        }`
      );
    } finally {
      setHintAliasesApplying(false);
    }
  };

  const applyHintSeedRuleDrafts = async () => {
    if (!allHintSeedRuleDrafts.length || hintSeedRulesApplying) return;
    const confirmed = window.confirm(
      t(
        'automation_hub_hint_apply_seed_rule_drafts_confirm',
        'Apply the suggested seed rule drafts now?'
      ).replace('{count}', String(allHintSeedRuleDrafts.length))
    );
    if (!confirmed) return;
    setHintSeedRulesApplying(true);
    try {
      const response = await DiscoveryHintService.applySeedRuleDrafts({
        rule_keys: allHintSeedRuleDrafts.map((item) => String(item.rule_key || '').trim()).filter(Boolean),
      });
      const applied = Number(response?.data?.applied || 0);
      toast.success(
        t(
          'automation_hub_hint_apply_seed_rule_drafts_success',
          'Applied {count} suggested seed rule drafts.'
        ).replace('{count}', String(applied))
      );
      await load();
    } catch (error) {
      toast.error(
        `${t('automation_hub_hint_apply_seed_rule_drafts_failed', 'Failed to apply suggested seed rule drafts')}: ${
          error?.response?.data?.detail?.message ||
          error?.response?.data?.detail ||
          error?.message ||
          ''
        }`
      );
    } finally {
      setHintSeedRulesApplying(false);
    }
  };

  const onDragStart = (evt, stepKey) => {
    evt.dataTransfer.setData('application/automation-step', stepKey);
    evt.dataTransfer.effectAllowed = 'move';
  };

  const onDrop = (evt) => {
    evt.preventDefault();
    const type = evt.dataTransfer.getData('application/automation-step');
    if (!type) return;
    const bounds = rfWrapperRef.current?.getBoundingClientRect();
    const x = evt.clientX - (bounds?.left || 0);
    const y = evt.clientY - (bounds?.top || 0);
    setNodes((nds) => [...nds, makeNode(type, { x, y })]);
  };

  const onDragOver = (evt) => {
    evt.preventDefault();
    evt.dataTransfer.dropEffect = 'move';
  };

  const updateSelectedNodeConfig = (patch) => {
    if (!selectedNodeId) return;
    setNodes((nds) =>
      nds.map((n) => {
        if (String(n.id) !== String(selectedNodeId)) return n;
        return { ...n, data: { ...n.data, ...patch } };
      })
    );
  };

  const runWorkflow = async () => {
    setRunLoading(true);
    setRunLog('');
    try {
      const orderedIds = getWorkflowOrder(nodes, edges);
      if (orderedIds.length === 0) {
        setRunLog(t('automation_hub_no_steps', 'No steps.'));
        return;
      }
      const results = [];
      for (const id of orderedIds) {
        const n = nodes.find((x) => String(x.id) === String(id));
        const stepType = n?.data?.stepType;
        const ep = endpointByStepType(stepType);
        if (!ep) {
          results.push({ step: stepType, ok: false, error: t('automation_hub_unknown_step_type', 'Unknown stepType') });
          continue;
        }
        const payload = safeJsonParse(n?.data?.configText, {});
        const token = localStorage.getItem('authToken');
        const res = await fetch(`${API_BASE_URL}/automation-hub/${ep}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify({ ...payload, meta: { variant } }),
        });
        const json = await res.json().catch(() => ({}));
        results.push({ step: stepType, status: res.status, body: json });
        if (!res.ok) break;
      }
      setRunLog(JSON.stringify(results, null, 2));
    } finally {
      setRunLoading(false);
    }
  };

  const moduleCards = [
    {
      key: 'discovery',
      title: t('hub_item_discovery_title', 'Auto Discovery'),
      desc: t('automation_hub_card_discovery_desc', 'Automatically discover and register network devices.'),
      icon: Scan,
      actionLabel: t('open_action', 'Open'),
      onClick: () => navigate('/discovery'),
      meta: discoveryStatus?.status ? String(discoveryStatus.status).toUpperCase() : t('automation_hub_ready', 'READY'),
    },
    {
      key: 'visual-config',
      title: t('hub_item_visual_title', 'Visual Config'),
      desc: t('automation_hub_card_visual_desc', 'Design and deploy configurations with visual blocks.'),
      icon: Blocks,
      actionLabel: t('open_action', 'Open'),
      onClick: () => navigate('/visual-config'),
    },
    {
      key: 'templates',
      title: t('automation_hub_template_title', 'Template Automation'),
      desc: t('automation_hub_card_template_desc', 'Run template-based automation for selected devices.'),
      icon: FileCheck,
      actionLabel: t('open_action', 'Open'),
      onClick: () => navigate('/config'),
      meta: `${templateCount} ${t('automation_hub_templates', 'Templates')}`,
    },
    {
      key: 'policy',
      title: t('automation_hub_policy_title', 'Policy / ACL'),
      desc: t('automation_hub_card_policy_desc', 'Enforce and deploy security policy and ACL changes.'),
      icon: Shield,
      actionLabel: t('open_action', 'Open'),
      onClick: () => navigate('/policy'),
      meta: `${policyCount} ${t('automation_hub_policies', 'Policies')}`,
    },
    {
      key: 'qos',
      title: t('automation_hub_qos_title', 'QoS Autoscaling'),
      desc: t('automation_hub_card_qos_desc', 'Adjust QoS policy by traffic thresholds automatically.'),
      icon: Zap,
      actionLabel: t('automation_hub_open_builder', 'Open Builder'),
      onClick: () => setViewMode('workflow'),
    },
    {
      key: 'fault',
      title: t('automation_hub_fault_title', 'Fault-Tolerance'),
      desc: t('automation_hub_card_fault_desc', 'Build auto-recovery flow for fault events.'),
      icon: Activity,
      actionLabel: t('automation_hub_open_builder', 'Open Builder'),
      onClick: () => setViewMode('workflow'),
    },
  ];

  if (!canView) {
    return (
      <div className="p-6">
        <div className="max-w-3xl bg-white/90 dark:bg-[#1b1d1f]/90 border border-gray-200 dark:border-white/5 rounded-2xl p-6 shadow-sm">
          <div className="text-lg font-bold text-gray-900 dark:text-white">{t('access_denied_title', 'Access denied')}</div>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">{t('access_denied_desc', 'Operations Home requires Operator role or higher.')}</div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-transparent text-primary-glow font-mono">
        <RefreshCw className="animate-spin mr-2" /> {t('automation_hub_loading', 'Loading automation hub...')}
      </div>
    );
  }

  const hintSync = hintSummary?.sync || {};
  const hintRules = hintSummary?.rules || {};
  const hintBenchmarkDetail = hintSummary?.benchmark || {};
  const hintBenchmark = hintSummary?.benchmark?.summary || {};
  const topHintVendors = Array.isArray(hintBenchmarkDetail?.by_vendor) ? hintBenchmarkDetail.by_vendor.slice(0, 4) : [];
  const topHintDrivers = Array.isArray(hintBenchmarkDetail?.by_driver) ? hintBenchmarkDetail.by_driver.slice(0, 4) : [];
  const hintRecommendations = Array.isArray(hintSummary?.recommendations) ? hintSummary.recommendations.slice(0, 4) : [];
  const allHintScoreAdjustments = Array.isArray(hintSummary?.score_adjustments) ? hintSummary.score_adjustments : [];
  const hintScoreAdjustments = allHintScoreAdjustments.slice(0, 4);
  const allHintAliasCandidates = Array.isArray(hintSummary?.alias_candidates) ? hintSummary.alias_candidates : [];
  const hintAliasCandidates = allHintAliasCandidates.slice(0, 4);
  const allHintSeedRuleDrafts = Array.isArray(hintSummary?.seed_rule_drafts) ? hintSummary.seed_rule_drafts : [];
  const hintSeedRuleDrafts = allHintSeedRuleDrafts.slice(0, 4);
  const hintTrend = hintSummary?.benchmark_trend || {};
  const hintTrendCurrent = hintTrend.current || {};
  const hintTrendPrevious = hintTrend.previous || {};
  const hintTrendDelta = hintTrend.delta || {};
  const hintFalsePositiveHotspots = Array.isArray(hintSummary?.false_positive_hotspots)
    ? hintSummary.false_positive_hotspots.slice(0, 4)
    : [];
  const formatTimestamp = (value) => {
    if (!value) return '-';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleString();
  };

  const insightsPanel = (
    <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
      <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{t('automation_hub_insights', 'Insights')}</div>
      <div className="mt-4 rounded-xl border border-gray-200 dark:border-white/10 p-3">
        <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{t('automation_hub_assets', 'Assets')}</div>
        <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">{t('devices_col_device', 'Device')}: {deviceCount}</div>
        <div className="text-[11px] text-gray-600 dark:text-gray-300">{t('automation_hub_templates', 'Templates')}: {templateCount}</div>
        <div className="text-[11px] text-gray-600 dark:text-gray-300">{t('automation_hub_policies', 'Policies')}: {policyCount}</div>
      </div>

      <div className="mt-4 rounded-xl border border-gray-200 dark:border-white/10 p-3">
        <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{t('automation_hub_usage_14d', 'Usage (14d)')}</div>
        {usageLoading ? (
          <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">{t('common_loading', 'Loading...')}</div>
        ) : usage ? (
          <div className="mt-2 space-y-1 text-[11px] text-gray-600 dark:text-gray-300">
            <div>{t('automation_hub_views', 'Views')}: {Number(usage.counts_by_action?.AUTO_HUB_VIEW || 0)}</div>
            <div>{t('automation_hub_template', 'Template')}: {Number(usage.counts_by_action?.AUTO_HUB_TEMPLATE || 0)}</div>
            <div>{t('automation_hub_fault', 'Fault')}: {Number(usage.counts_by_action?.AUTO_HUB_FT || 0)}</div>
            <div>{t('automation_hub_qos', 'QoS')}: {Number(usage.counts_by_action?.AUTO_HUB_QOS || 0)}</div>
            <div>{t('automation_hub_acl', 'ACL')}: {Number(usage.counts_by_action?.AUTO_HUB_ACL || 0)}</div>
          </div>
        ) : (
          <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">{t('dashboard_no_data', 'No data')}</div>
        )}
      </div>

      <div className="mt-4 rounded-xl border border-gray-200 dark:border-white/10 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
            {t('automation_hub_hinting_title', 'Discovery Hinting')}
          </div>
          <span className={`px-2 py-1 rounded-full text-[10px] font-extrabold border ${
            hintSync.enabled
              ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-200 dark:border-emerald-500/30'
              : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-200 dark:border-amber-500/30'
          }`}>
            {hintSync.enabled ? t('common_enabled', 'Enabled') : t('common_disabled', 'Disabled')}
          </span>
        </div>
        <div className="mt-2 space-y-1 text-[11px] text-gray-600 dark:text-gray-300">
          <div>{t('automation_hub_hint_rule_version', 'Rule Version')}: <span className="font-mono">{hintRules.version || hintSync.rule_version || '-'}</span></div>
          <div>{t('automation_hub_hint_active_rules', 'Active Rules')}: {Number(hintRules.active || 0)} / {Number(hintRules.total || 0)}</div>
          <div>{t('automation_hub_hint_total_events', 'Telemetry Events')}: {Number(hintBenchmark.total || 0)}</div>
          <div>{t('automation_hub_hint_success_count', 'Hint Success Count')}: {Number(hintBenchmark.success || 0)}</div>
          <div>{t('automation_hub_hint_false_positive_count', 'False Positive Count')}: {Number(hintBenchmark.false_positive || 0)}</div>
          <div>{t('automation_hub_hint_success_rate', 'Hint Success')}: {Number(hintBenchmark.success_rate_pct || 0).toFixed(1)}%</div>
          <div>{t('automation_hub_hint_false_positive_rate', 'False Positive')}: {Number(hintBenchmark.false_positive_rate_pct || 0).toFixed(1)}%</div>
          <div>{t('automation_hub_hint_last_pull', 'Last Rule Pull')}: {formatTimestamp(hintSync.last_pull_at)}</div>
          <div>{t('automation_hub_hint_last_push', 'Last Telemetry Push')}: {formatTimestamp(hintSync.last_push_at)}</div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="px-2 py-1 rounded-full text-[10px] font-extrabold bg-slate-100 text-slate-700 dark:bg-white/5 dark:text-slate-200">
            {t('automation_hub_hint_pull_status', 'Pull')}: {hintSync.last_pull_status || '-'}
          </span>
          <span className="px-2 py-1 rounded-full text-[10px] font-extrabold bg-slate-100 text-slate-700 dark:bg-white/5 dark:text-slate-200">
            {t('automation_hub_hint_push_status', 'Push')}: {hintSync.last_push_status || '-'}
          </span>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
          <div className="rounded-xl border border-gray-200 dark:border-white/10 p-3">
            <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
              {t('automation_hub_hint_top_vendors', 'Top Vendors')}
            </div>
            {topHintVendors.length ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {topHintVendors.map((item) => (
                  <span
                    key={`hint-vendor-${item.vendor}`}
                    className="px-2 py-1 rounded-full text-[10px] font-extrabold bg-slate-100 text-slate-700 dark:bg-white/5 dark:text-slate-200"
                  >
                    {String(item.vendor || 'unknown')} · {Number(item.success || 0)}/{Number(item.total || 0)}
                  </span>
                ))}
              </div>
            ) : (
              <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
                {t('automation_hub_hint_no_recent_benchmark', 'No recent benchmark data')}
              </div>
            )}
          </div>
          <div className="rounded-xl border border-gray-200 dark:border-white/10 p-3">
            <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
              {t('automation_hub_hint_top_drivers', 'Top Drivers')}
            </div>
            {topHintDrivers.length ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {topHintDrivers.map((item) => (
                  <span
                    key={`hint-driver-${item.driver}`}
                    className="px-2 py-1 rounded-full text-[10px] font-extrabold bg-slate-100 text-slate-700 dark:bg-white/5 dark:text-slate-200"
                  >
                    {String(item.driver || 'unknown')} · {Number(item.success || 0)}/{Number(item.total || 0)}
                  </span>
                ))}
              </div>
            ) : (
              <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
                {t('automation_hub_hint_no_recent_benchmark', 'No recent benchmark data')}
              </div>
            )}
          </div>
        </div>
        <div className="mt-3 rounded-xl border border-gray-200 dark:border-white/10 p-3">
          <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
            {t('automation_hub_hint_trend', 'Trend Window')}
          </div>
          <div className="mt-2 grid grid-cols-1 gap-3 xl:grid-cols-3">
            <div className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2 bg-gray-50 dark:bg-white/5">
              <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                {t('automation_hub_hint_success_rate', 'Hint Success')}
              </div>
              <div className="mt-2 space-y-1 text-[11px] text-gray-600 dark:text-gray-300">
                <div>{t('automation_hub_hint_trend_current', 'Current')}: <span className="font-mono text-gray-800 dark:text-gray-100">{Number(hintTrendCurrent.success_rate_pct || 0).toFixed(1)}%</span></div>
                <div>{t('automation_hub_hint_trend_previous', 'Previous')}: <span className="font-mono text-gray-800 dark:text-gray-100">{Number(hintTrendPrevious.success_rate_pct || 0).toFixed(1)}%</span></div>
                <div>{t('automation_hub_hint_trend_delta', 'Delta')}: <span className={`font-mono ${Number(hintTrendDelta.success_rate_pct || 0) >= 0 ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300'}`}>{Number(hintTrendDelta.success_rate_pct || 0) > 0 ? '+' : ''}{Number(hintTrendDelta.success_rate_pct || 0).toFixed(1)}%</span></div>
              </div>
            </div>
            <div className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2 bg-gray-50 dark:bg-white/5">
              <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                {t('automation_hub_hint_false_positive_rate', 'False Positive')}
              </div>
              <div className="mt-2 space-y-1 text-[11px] text-gray-600 dark:text-gray-300">
                <div>{t('automation_hub_hint_trend_current', 'Current')}: <span className="font-mono text-gray-800 dark:text-gray-100">{Number(hintTrendCurrent.false_positive_rate_pct || 0).toFixed(1)}%</span></div>
                <div>{t('automation_hub_hint_trend_previous', 'Previous')}: <span className="font-mono text-gray-800 dark:text-gray-100">{Number(hintTrendPrevious.false_positive_rate_pct || 0).toFixed(1)}%</span></div>
                <div>{t('automation_hub_hint_trend_delta', 'Delta')}: <span className={`font-mono ${Number(hintTrendDelta.false_positive_rate_pct || 0) <= 0 ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300'}`}>{Number(hintTrendDelta.false_positive_rate_pct || 0) > 0 ? '+' : ''}{Number(hintTrendDelta.false_positive_rate_pct || 0).toFixed(1)}%</span></div>
              </div>
            </div>
            <div className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2 bg-gray-50 dark:bg-white/5">
              <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                {t('automation_hub_hint_unknown_after_hint', 'Unknown After Hint')}
              </div>
              <div className="mt-2 space-y-1 text-[11px] text-gray-600 dark:text-gray-300">
                <div>{t('automation_hub_hint_trend_current', 'Current')}: <span className="font-mono text-gray-800 dark:text-gray-100">{Number(hintTrendCurrent.unknown_after_hint || 0)}</span></div>
                <div>{t('automation_hub_hint_trend_previous', 'Previous')}: <span className="font-mono text-gray-800 dark:text-gray-100">{Number(hintTrendPrevious.unknown_after_hint || 0)}</span></div>
                <div>{t('automation_hub_hint_trend_delta', 'Delta')}: <span className={`font-mono ${Number(hintTrendDelta.unknown_after_hint || 0) <= 0 ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300'}`}>{Number(hintTrendDelta.unknown_after_hint || 0) > 0 ? '+' : ''}{Number(hintTrendDelta.unknown_after_hint || 0)}</span></div>
              </div>
            </div>
          </div>
        </div>
        <div className="mt-3 rounded-xl border border-gray-200 dark:border-white/10 p-3">
          <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
            {t('automation_hub_hint_false_positive_hotspots', 'False Positive Hotspots')}
          </div>
          {hintFalsePositiveHotspots.length ? (
            <div className="mt-2 space-y-2">
              {hintFalsePositiveHotspots.map((item, idx) => (
                <div
                  key={`hint-hotspot-${idx}`}
                  className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2 bg-gray-50 dark:bg-white/5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] font-extrabold text-gray-800 dark:text-gray-100">
                      {String(item.title || item.driver || 'Hotspot')}
                    </div>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold ${
                      String(item.severity || '').toLowerCase() === 'high'
                        ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-200'
                    }`}>
                      {String(item.severity || 'medium').toUpperCase()}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                    {String(item.description || '')}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-gray-500 dark:text-gray-400">
                    <span>{t('automation_hub_hint_driver', 'Driver')}: <span className="font-mono text-gray-700 dark:text-gray-200">{String(item.driver || '-')}</span></span>
                    <span>{t('automation_hub_hint_total_events', 'Telemetry Events')}: {Number(item.metrics?.total || 0)}</span>
                    <span>{t('automation_hub_hint_false_positive_count', 'False Positive Count')}: {Number(item.metrics?.false_positive || 0)}</span>
                    <span>{t('automation_hub_hint_false_positive_rate', 'False Positive')}: {Number(item.metrics?.false_positive_rate_pct || 0).toFixed(1)}%</span>
                    <span>{t('automation_hub_hint_unknown_after_hint', 'Unknown After Hint')}: {Number(item.metrics?.unknown_after_hint || 0)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
              {t('automation_hub_hint_no_false_positive_hotspots', 'No persistent false-positive hotspots were detected.')}
            </div>
          )}
        </div>
        <div className="mt-3 rounded-xl border border-gray-200 dark:border-white/10 p-3">
          <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
            {t('automation_hub_hint_recommendations', 'Tuning Recommendations')}
          </div>
          {hintRecommendations.length ? (
            <div className="mt-2 space-y-2">
              {hintRecommendations.map((item, idx) => (
                <div
                  key={`hint-recommendation-${idx}`}
                  className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2 bg-gray-50 dark:bg-white/5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] font-extrabold text-gray-800 dark:text-gray-100">
                      {String(item.title || item.kind || 'Recommendation')}
                    </div>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold ${
                      String(item.severity || '').toLowerCase() === 'high'
                        ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-200'
                    }`}>
                      {String(item.severity || 'medium').toUpperCase()}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                    {String(item.description || '')}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
              {t('automation_hub_hint_no_recommendations', 'No immediate tuning hotspots from recent telemetry.')}
            </div>
          )}
        </div>
        <div className="mt-3 rounded-xl border border-gray-200 dark:border-white/10 p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
              {t('automation_hub_hint_score_adjustments', 'Suggested Score Adjustments')}
            </div>
            {canTuneHints ? (
              <button
                type="button"
                onClick={applyHintScoreAdjustments}
                disabled={!hintScoreAdjustments.length || hintAdjustmentsApplying}
                className="px-2.5 py-1.5 rounded-lg text-[10px] font-extrabold bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {hintAdjustmentsApplying
                  ? t('common_loading', 'Loading...')
                  : t('automation_hub_hint_apply_score_adjustments', 'Apply Suggestions')}
              </button>
            ) : null}
          </div>
          {hintScoreAdjustments.length ? (
            <div className="mt-2 space-y-2">
              {hintScoreAdjustments.map((item, idx) => (
                <div
                  key={`hint-score-adjustment-${idx}`}
                  className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2 bg-gray-50 dark:bg-white/5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] font-extrabold text-gray-800 dark:text-gray-100">
                      {String(item.title || item.rule_key || 'Score adjustment')}
                    </div>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold ${
                      String(item.suggested_delta || '').startsWith('-')
                        ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200'
                        : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200'
                    }`}>
                      {Number(item.suggested_delta || 0) > 0 ? '+' : ''}{Number(item.suggested_delta || 0).toFixed(2)}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                    {String(item.description || '')}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-gray-500 dark:text-gray-400">
                    <span>{t('automation_hub_hint_rule', 'Rule')}: <span className="font-mono text-gray-700 dark:text-gray-200">{String(item.rule_key || '-')}</span></span>
                    <span>{t('automation_hub_hint_score_current', 'Current')}: {Number(item.current_score_bonus || 0).toFixed(2)}</span>
                    <span>{t('automation_hub_hint_score_suggested', 'Suggested')}: {Number(item.suggested_score_bonus || 0).toFixed(2)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
              {t('automation_hub_hint_no_score_adjustments', 'No score adjustments are suggested from recent telemetry.')}
            </div>
          )}
        </div>
        <div className="mt-3 rounded-xl border border-gray-200 dark:border-white/10 p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
              {t('automation_hub_hint_alias_candidates', 'Alias Candidates')}
            </div>
            {canTuneHints ? (
              <button
                type="button"
                onClick={applyHintAliasCandidates}
                disabled={!allHintAliasCandidates.length || hintAliasesApplying}
                className="px-2.5 py-1.5 rounded-lg text-[10px] font-extrabold bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {hintAliasesApplying
                  ? t('common_loading', 'Loading...')
                  : t('automation_hub_hint_apply_alias_candidates', 'Apply Aliases')}
              </button>
            ) : null}
          </div>
          {hintAliasCandidates.length ? (
            <div className="mt-2 space-y-2">
              {hintAliasCandidates.map((item, idx) => (
                <div
                  key={`hint-alias-candidate-${idx}`}
                  className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2 bg-gray-50 dark:bg-white/5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] font-extrabold text-gray-800 dark:text-gray-100">
                      {String(item.title || 'Alias candidate')}
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-200">
                      {Number(item.sample_count || 0)} {t('automation_hub_hint_samples', 'samples')}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                    {String(item.description || '')}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-gray-500 dark:text-gray-400">
                    <span>{t('automation_hub_hint_alias_raw', 'Raw')}: <span className="font-mono text-gray-700 dark:text-gray-200">{String(item.raw_vendor || '-')}</span></span>
                    <span>{t('automation_hub_hint_alias_suggested', 'Suggested')}: <span className="font-mono text-gray-700 dark:text-gray-200">{String(item.suggested_vendor_family || '-')}</span></span>
                    <span>{t('automation_hub_hint_driver', 'Driver')}: <span className="font-mono text-gray-700 dark:text-gray-200">{String(item.driver || '-')}</span></span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
              {t('automation_hub_hint_no_alias_candidates', 'No alias candidates are suggested from recent telemetry.')}
            </div>
          )}
        </div>
        <div className="mt-3 rounded-xl border border-gray-200 dark:border-white/10 p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
              {t('automation_hub_hint_seed_rule_drafts', 'Seed Rule Drafts')}
            </div>
            {canTuneHints ? (
              <button
                type="button"
                onClick={applyHintSeedRuleDrafts}
                disabled={!allHintSeedRuleDrafts.length || hintSeedRulesApplying}
                className="px-2.5 py-1.5 rounded-lg text-[10px] font-extrabold bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {hintSeedRulesApplying
                  ? t('common_loading', 'Loading...')
                  : t('automation_hub_hint_apply_seed_rule_drafts', 'Apply Seed Rules')}
              </button>
            ) : null}
          </div>
          {hintSeedRuleDrafts.length ? (
            <div className="mt-2 space-y-2">
              {hintSeedRuleDrafts.map((item, idx) => (
                <div
                  key={`hint-seed-rule-draft-${idx}`}
                  className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2 bg-gray-50 dark:bg-white/5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] font-extrabold text-gray-800 dark:text-gray-100">
                      {String(item.title || item.rule_key || 'Seed rule draft')}
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-200">
                      {Number(item.sample_count || 0)} {t('automation_hub_hint_samples', 'samples')}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                    {String(item.description || '')}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-gray-500 dark:text-gray-400">
                    <span>{t('automation_hub_hint_rule', 'Rule')}: <span className="font-mono text-gray-700 dark:text-gray-200">{String(item.rule_key || '-')}</span></span>
                    <span>{t('automation_hub_hint_alias_suggested', 'Suggested')}: <span className="font-mono text-gray-700 dark:text-gray-200">{String(item.vendor_family || '-')}</span></span>
                    <span>{t('automation_hub_hint_driver', 'Driver')}: <span className="font-mono text-gray-700 dark:text-gray-200">{String(Array.isArray(item.driver_overrides) ? item.driver_overrides.join(', ') : '-')}</span></span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
              {t('automation_hub_hint_no_seed_rule_drafts', 'No seed rule drafts are suggested from recent telemetry.')}
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-gray-200 dark:border-white/10 p-3">
        <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{t('automation_hub_feedback', 'Feedback')}</div>
        <div className="mt-2 flex items-center gap-2">
          <select
            value={feedbackRating}
            onChange={(e) => setFeedbackRating(e.target.value)}
            className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-2 py-2 focus:outline-none focus:border-primary/50 cursor-pointer transition-all"
          >
            {[5, 4, 3, 2, 1].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          <div className="text-[11px] text-gray-500 dark:text-gray-400">/ {t('automation_hub_five_scale', '5')}</div>
        </div>
        <textarea
          value={feedbackComment}
          onChange={(e) => setFeedbackComment(e.target.value)}
          className="mt-2 w-full h-20 bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 transition-all"
          placeholder={t('automation_hub_feedback_placeholder', 'Leave feedback (optional)')}
        />
        <button
          onClick={submitFeedback}
          disabled={feedbackSending}
          className="mt-2 w-full px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors disabled:opacity-60"
        >
          {t('automation_hub_submit', 'Submit')}
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full min-h-0 min-w-0 gap-6 animate-fade-in text-gray-900 dark:text-white font-sans pb-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-end pb-4 border-b border-gray-200 dark:border-white/5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white/90 flex items-center gap-2">
              <Workflow size={20} /> {t('automation_hub_title', 'Operations Home')}
            </h1>
          </div>
          <p className="text-xs text-gray-500 pl-4">{t('automation_hub_variant_label', 'NetSphere Pro operations modules - Variant')} {variant}</p>
        </div>
        <div className="flex gap-3 items-center flex-wrap justify-end">
          <div className="flex items-center gap-1 bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-lg p-1">
            <button
              type="button"
              onClick={() => setViewMode('overview')}
              className={`px-3 py-2 text-xs font-extrabold rounded-md transition-colors ${viewMode === 'overview' ? 'bg-gray-900 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10'}`}
            >
              {t('automation_hub_overview', 'Overview')}
            </button>
            <button
              type="button"
              onClick={() => setViewMode('workflow')}
              className={`px-3 py-2 text-xs font-extrabold rounded-md transition-colors ${viewMode === 'workflow' ? 'bg-gray-900 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10'}`}
            >
              {t('automation_hub_workflow', 'Workflow')}
            </button>
          </div>
          <button
            type="button"
            onClick={() => navigate('/discovery')}
            className="hidden md:flex items-center gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-100 dark:border-blue-500/30 hover:bg-blue-100/70 dark:hover:bg-blue-900/30 transition-colors"
          >
            <Scan size={14} className="text-blue-600 dark:text-blue-400" />
            <div className="flex flex-col">
              <span className="text-[10px] font-bold text-blue-500 dark:text-blue-400 uppercase tracking-wider leading-none">{t('hub_item_discovery_title', 'Auto Discovery')}</span>
              <span className="text-xs font-black text-blue-700 dark:text-blue-200 leading-none mt-1">{t('automation_hub_ready', 'READY')} ({deviceCount} {t('automation_hub_devices', 'Devices')})</span>
            </div>
          </button>
          <a
            href="/grafana/"
            target="_blank"
            rel="noreferrer"
            className="px-3 py-2 bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg text-xs font-bold text-gray-700 dark:text-gray-300 transition-colors border border-gray-200 dark:border-white/10 flex items-center gap-2"
          >
            Grafana <ExternalLink size={14} />
          </a>
          <button
            onClick={load}
            className="p-2 bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors border border-transparent hover:border-gray-300 dark:hover:border-white/10"
          >
            <RefreshCw size={16} title={t('common_refresh', 'Refresh')} />
          </button>
        </div>
      </div>

      {viewMode === 'overview' ? (
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
          <div className="xl:col-span-3 space-y-6">
            <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{t('automation_hub_modules', 'Automation Modules')}</div>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {moduleCards.map((m) => (
                  <div key={m.key} className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 p-4 flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <m.icon size={16} className="text-blue-600 dark:text-blue-400" />
                        <div className="text-sm font-black text-gray-900 dark:text-white">{m.title}</div>
                      </div>
                      {m.meta ? (
                        <div className="text-[10px] font-extrabold text-blue-600 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 border border-blue-100 dark:border-blue-700/40 px-2 py-1 rounded-full">
                          {m.meta}
                        </div>
                      ) : null}
                    </div>
                    <div className="text-xs text-gray-600 dark:text-gray-300">{m.desc}</div>
                    <button
                      type="button"
                      onClick={m.onClick}
                      className="mt-auto px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors"
                    >
                      {m.actionLabel}
                    </button>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{t('automation_hub_workflow_builder', 'Workflow Builder')}</div>
              <div className="mt-3 flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setViewMode('workflow')}
                  className="px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors flex items-center gap-2"
                >
                  <Workflow size={14} /> {t('automation_hub_open_builder', 'Open Builder')}
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/visual-config')}
                  className="px-3 py-2 rounded-xl text-xs font-extrabold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  {t('hub_item_visual_title', 'Visual Config')}
                </button>
              </div>
            </div>
          </div>
          {insightsPanel}
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
          <div className="xl:col-span-3 bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between gap-3 p-4 border-b border-gray-200 dark:border-white/10">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{t('automation_hub_workflow_builder', 'Workflow Builder')}</div>
              <div className="flex items-center gap-2">
                <button
                  onClick={runWorkflow}
                  disabled={runLoading}
                  className="px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors disabled:opacity-60 flex items-center gap-2"
                >
                  <Play size={14} /> {t('diagnosis_run', 'Run')}
                </button>
                <button
                  onClick={() => { setNodes([]); setEdges([]); setSelectedNodeId(null); setRunLog(''); }}
                  className="px-3 py-2 rounded-xl text-xs font-extrabold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  {t('common_reset', 'Reset')}
                </button>
              </div>
            </div>

            <div className="h-[min(60vh,520px)] min-h-[320px]" ref={rfWrapperRef}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={(c) => setEdges((eds) => [...eds, { ...c, id: `${c.source}-${c.target}-${Date.now()}` }])}
                onNodeClick={(_, n) => setSelectedNodeId(n.id)}
                onDrop={onDrop}
                onDragOver={onDragOver}
                fitView
                className="bg-gray-50 dark:bg-[#0e1012]"
              >
                <MiniMap nodeColor="#aaa" maskColor="rgba(0,0,0,0.1)" />
                <Controls />
                <Background color="#ccc" gap={20} size={1} />
                <Panel position="top-left" className="m-3 bg-white/90 dark:bg-[#1b1d1f]/90 border border-gray-200 dark:border-white/10 rounded-xl p-3 w-64">
                  <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">{t('automation_hub_palette', 'Palette')}</div>
                  <div className="space-y-2">
                    {modulePalette.map((m) => (
                      <div
                        key={m.key}
                        draggable
                        onDragStart={(e) => onDragStart(e, m.key)}
                        className="cursor-move select-none rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-black/20 p-3 hover:bg-gray-50 dark:hover:bg-white/5"
                      >
                        <div className="text-sm font-black text-gray-900 dark:text-white">{t(`automation_hub_palette_${m.key}_title`, m.title)}</div>
                        <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">{t(`automation_hub_palette_${m.key}_desc`, m.desc)}</div>
                      </div>
                    ))}
                  </div>
                </Panel>
              </ReactFlow>
            </div>

            {runLog ? (
              <div className="border-t border-gray-200 dark:border-white/10 p-4">
                <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-2">{t('automation_hub_run_log', 'Run Log')}</div>
                <pre className="text-xs bg-black/90 text-white rounded-xl p-3 overflow-auto max-h-56">{runLog}</pre>
              </div>
            ) : null}
          </div>

          <div className="space-y-4">
            <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{t('automation_hub_step_config', 'Step Config')}</div>
              {selectedNode ? (
                <>
                  <div className="mt-3 text-xs text-gray-600 dark:text-gray-300">{t('common_type', 'Type')}</div>
                  <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{selectedNode.data?.stepType}</div>
                  <div className="mt-4 text-xs text-gray-600 dark:text-gray-300">{t('automation_hub_config_json', 'Config JSON')}</div>
                  <textarea
                    value={selectedNode.data?.configText || ''}
                    onChange={(e) => updateSelectedNodeConfig({ configText: e.target.value })}
                    className="mt-2 w-full h-48 bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 transition-all"
                    placeholder='{"example":"value"}'
                  />
                  <div className="mt-3 text-[11px] text-gray-500 dark:text-gray-400">
                    {t('automation_hub_available_steps', 'Available')}: discovery | template | fault-tolerance | qos-autoscale | acl-enforce
                  </div>
                  <div className="mt-4 text-[11px] text-gray-500 dark:text-gray-400">
                    {t('automation_hub_hints', 'Hints')}: {t('automation_hub_hint_text', 'use device_ids (array), template_id/policy_id, variables (object), threshold_bps/current_bps.')}
                  </div>
                </>
              ) : (
                <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">{t('automation_hub_select_or_drag', 'Select a node or drag one from the palette.')}</div>
              )}
            </div>
            {insightsPanel}
          </div>
        </div>
      )}
    </div>
  );
};

export default AutomationHubPage;


