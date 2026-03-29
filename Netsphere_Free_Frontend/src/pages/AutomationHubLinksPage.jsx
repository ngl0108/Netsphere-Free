import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Bell,
  CheckCircle,
  ExternalLink,
  FileCheck,
  FileText,
  Globe,
  Package,
  RefreshCw,
  Shield,
  Workflow,
} from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import { CloudService, ComplianceService, IssueService, ObservabilityService, OpsService, ServiceGroupService, SupportService } from '../api/services';
import { useAuth } from '../context/AuthContext';
import { useProductPolicy } from '../context/ProductPolicyContext';
import {
  canSurfaceNavigate,
  canSurfaceRender,
  getSurfaceBlockSummary,
  getSurfacePolicyState,
} from '../context/productPolicySelectors';
import { useToast } from '../context/ToastContext';
import { buildWorkspaceManifest, OPERATIONS_SURFACES } from '../config/operationsManifest';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';
import ProductPolicyBlockCard from '../components/common/ProductPolicyBlockCard';
import {
  getCloudPressureIndex,
  getOperationsPressureGuidance,
  getOperationsPressureLabel,
  getOperationsPressureLevel,
  getOperationsPrimaryPressure,
  getObservabilityPressureIndex,
  getServicePressureIndex,
  getServiceReviewAverageHealth,
  getWorkspaceTitle,
  recommendCloudOperationsWorkspace,
  recommendObservabilityWorkspace,
  recommendServiceWorkspace,
  summarizeCloudExecutionHighlights,
  summarizeCloudRetryQueue,
  summarizeCloudScheduleQueue,
  summarizeCloudOperationsPressure,
  summarizeCloudLaneBoard,
  summarizeCloudReviewQueue,
  summarizeObservabilityPressure,
  summarizeServiceLaneBoard,
  summarizeServiceReviewPosture,
  summarizeServiceReviewQueue,
} from '../utils/serviceOperations';
import {
  buildGrafanaAlertingCenterUrl,
  buildGrafanaComplianceAutomationOpsUrl,
  buildGrafanaDiscoveryTopologyOpsUrl,
  buildGrafanaFleetHealthUrl,
  buildGrafanaOperationsControlPlaneUrl,
} from '../utils/observabilityLinks';

const parseFilename = (contentDisposition) => {
  const value = String(contentDisposition || '');
  const match = value.match(/filename="?([^"]+)"?/i);
  return match ? match[1] : null;
};

const downloadBlob = (data, filename, contentType) => {
  const blob = data instanceof Blob ? data : new Blob([data], { type: contentType || 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || 'download';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
};

const pressureBadgeClass = (pressureIndex) => {
  const level = getOperationsPressureLevel(pressureIndex);
  if (level === 'critical') {
    return 'border-rose-200/80 bg-rose-50/80 text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200';
  }
  if (level === 'elevated') {
    return 'border-amber-200/80 bg-amber-50/80 text-amber-700 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200';
  }
  return 'border-emerald-200/80 bg-emerald-50/80 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200';
};

const BLOCKED_FEATURE_LABELS = {
  config_deploy_and_rollback: {
    key: 'automation_preview_blocked_config_deploy_and_rollback',
    defaultLabel: 'Live config deploy and rollback',
  },
  live_policy_push: {
    key: 'automation_preview_blocked_live_policy_push',
    defaultLabel: 'Live policy push',
  },
  software_image_rollout: {
    key: 'automation_preview_blocked_software_image_rollout',
    defaultLabel: 'Software image rollout',
  },
  fabric_and_ztp_execution: {
    key: 'automation_preview_blocked_fabric_and_ztp_execution',
    defaultLabel: 'Fabric and ZTP execution',
  },
  compliance_remediation: {
    key: 'automation_preview_blocked_compliance_remediation',
    defaultLabel: 'Compliance remediation',
  },
  privileged_admin_and_secret_settings: {
    key: 'automation_preview_blocked_privileged_admin_and_secret_settings',
    defaultLabel: 'Privileged admin and secret settings',
  },
  cloud_bootstrap_and_external_webhooks: {
    key: 'automation_preview_blocked_cloud_bootstrap_and_external_webhooks',
    defaultLabel: 'Cloud bootstrap and external webhooks',
  },
};

const DEFAULT_PREVIEW_PILLARS = [
  { key: 'auto_discovery', route: '/discovery' },
  { key: 'auto_topology', route: '/topology' },
  { key: 'connected_nms', route: '/devices' },
];

const QUICK_FLOW_BLUEPRINTS = [
  {
    key: 'discover_review',
    route: '/discovery',
    titleKey: 'ops_quick_flow_discover_review_title',
    titleDefault: 'Discover and review assets',
    descKey: 'ops_quick_flow_discover_review_desc',
    descDefault: 'Run discovery, review the results, and move assets into managed operations from one starting point.',
  },
  {
    key: 'issue_to_action',
    route: '/notifications',
    titleKey: 'ops_quick_flow_issue_action_title',
    titleDefault: 'Investigate issue to action',
    descKey: 'ops_quick_flow_issue_action_desc',
    descDefault: 'Open active alarms, create actions, and follow service impact plus approval context without losing the thread.',
  },
  {
    key: 'change_with_precheck',
    route: '/cloud/intents',
    titleKey: 'ops_quick_flow_change_precheck_title',
    titleDefault: 'Preview and approve change',
    descKey: 'ops_quick_flow_change_precheck_desc',
    descDefault: 'Start from cloud intents, run pre-check, compare before and after, and move into approval from the same flow.',
  },
  {
    key: 'review_evidence',
    route: '/operations-reports',
    titleKey: 'ops_quick_flow_review_evidence_title',
    titleDefault: 'Review evidence and reports',
    descKey: 'ops_quick_flow_review_evidence_desc',
    descDefault: 'Use operations reports, state history, and evidence bundles to explain what changed and what needs follow-up.',
  },
];

const workspaceAccent = {
  observe: 'border-blue-200 dark:border-blue-900/40 bg-blue-50/60 dark:bg-blue-950/10',
  discover: 'border-emerald-200 dark:border-emerald-900/40 bg-emerald-50/60 dark:bg-emerald-950/10',
  control: 'border-violet-200 dark:border-violet-900/40 bg-violet-50/60 dark:bg-violet-950/10',
  govern: 'border-amber-200 dark:border-amber-900/40 bg-amber-50/60 dark:bg-amber-950/10',
};

const serviceHealthTone = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'critical') return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-300';
  if (normalized === 'degraded' || normalized === 'review') return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
  return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300';
};

const AutomationHubLinksPage = () => {
  useLocaleRerender();
  const navigate = useNavigate();
  const location = useLocation();
  const { isAtLeast } = useAuth();
  const { toast } = useToast();
  const canView = isAtLeast('operator');
  const { manifest, loading } = useProductPolicy();
  const workspaceRefs = useRef({});
  const [downloadState, setDownloadState] = useState({
    operatorPackage: false,
    supportBundle: false,
    releaseBundle: false,
    complianceExport: false,
  });
  const [serviceReviewQueue, setServiceReviewQueue] = useState([]);
  const [serviceReviewLoading, setServiceReviewLoading] = useState(false);
  const [serviceReviewError, setServiceReviewError] = useState('');
  const [serviceReviewPosture, setServiceReviewPosture] = useState({
    critical: 0,
    review: 0,
    discoveredOnlyPressure: 0,
    activeIssues: 0,
    totalGroups: 0,
    totalHealthScore: 0,
  });
  const [cloudPressureSummary, setCloudPressureSummary] = useState({
    attention: 0,
    syncing: 0,
    pendingApprovals: 0,
    retryRecommended: 0,
    total: 0,
  });
  const [cloudReviewQueue, setCloudReviewQueue] = useState([]);
  const [cloudLaneBoard, setCloudLaneBoard] = useState({ approval: 0, recovery: 0, sync: 0, stable: 0 });
  const [cloudRetryQueue, setCloudRetryQueue] = useState([]);
  const [cloudExecutionHighlights, setCloudExecutionHighlights] = useState([]);
  const [cloudScheduleQueue, setCloudScheduleQueue] = useState([]);
  const [cloudPressureLoading, setCloudPressureLoading] = useState(false);
  const [cloudPressureError, setCloudPressureError] = useState('');
  const [observabilityPressureSummary, setObservabilityPressureSummary] = useState({
    devices: 0,
    online: 0,
    offline: 0,
    unreadCount: 0,
  });
  const [observabilityPressureLoading, setObservabilityPressureLoading] = useState(false);
  const [observabilityPressureError, setObservabilityPressureError] = useState('');

  const previewEnabled = manifest?.preview_enabled === true;
  const previewContext = manifest?.preview_policy || {};
  const blockedFeatures = Array.isArray(previewContext?.blocked_features)
    ? previewContext.blocked_features.map((item) => {
        const label = BLOCKED_FEATURE_LABELS[item];
        return t(label?.key, label?.defaultLabel || item);
      })
    : [];

  const experiencePillars = useMemo(() => {
    const source = Array.isArray(previewContext?.experience_pillars) && previewContext.experience_pillars.length > 0
      ? previewContext.experience_pillars
      : DEFAULT_PREVIEW_PILLARS;
    return source.map((item) => ({
      ...item,
      title:
        item.key === 'auto_discovery'
          ? t('automation_preview_pillar_auto_discovery_title', 'Auto Discovery')
          : item.key === 'auto_topology'
            ? t('automation_preview_pillar_auto_topology_title', 'Auto Topology')
            : t('automation_preview_pillar_connected_nms_title', 'Connected NMS'),
      desc:
        item.key === 'auto_discovery'
          ? t('automation_preview_pillar_auto_discovery_desc', 'Run scans and seed-based discovery, then move directly into inventory review.')
          : item.key === 'auto_topology'
            ? t('automation_preview_pillar_auto_topology_desc', 'Use L2/L3/BGP/VXLAN topology with path trace and candidate review.')
            : t('automation_preview_pillar_connected_nms_desc', 'Move from discovered assets into device detail, issues, and observability in one flow.'),
    }));
  }, [previewContext]);

  const workspaceSections = useMemo(() => {
    return buildWorkspaceManifest(manifest?.workspaces)
      .map((workspace) => {
        const items = workspace.surfaceKeys
          .map((key) => {
            const surface = OPERATIONS_SURFACES[key];
            const policyState = getSurfacePolicyState(manifest, key, t, t('locked_action', 'Locked'));
            const access = policyState.access;
            if (!surface || !access || !canSurfaceRender(manifest, key)) return null;
            return {
              ...surface,
              access,
              policyState,
              title: t(surface.labelKey, surface.labelDefault),
              desc: t(surface.descKey, surface.descDefault),
            };
          })
          .filter(Boolean);
        const primaryKeys = Array.isArray(workspace.primarySurfaceKeys) ? workspace.primarySurfaceKeys : [];
        const primaryItems = primaryKeys
          .map((key) => items.find((item) => item.key === key))
          .filter(Boolean);
        const secondaryItems = items.filter((item) => !primaryKeys.includes(item.key));
        return {
          ...workspace,
          title: t(workspace.titleKey, workspace.titleDefault),
          desc: t(workspace.descKey, workspace.descDefault),
          items,
          primaryItems,
          secondaryItems,
        };
      })
      .filter((workspace) => workspace.items.length > 0);
  }, [manifest]);

  const quickFlows = useMemo(() => {
    return QUICK_FLOW_BLUEPRINTS.filter((flow) => {
      const matchedSurface = Object.values(OPERATIONS_SURFACES).find((surface) => surface.path === flow.route);
      if (!matchedSurface) return true;
      return canSurfaceNavigate(manifest, matchedSurface.key);
    }).map((flow) => ({
      ...flow,
      title: t(flow.titleKey, flow.titleDefault),
      desc: t(flow.descKey, flow.descDefault),
    }));
  }, [manifest]);

  const showServiceReviewQueue =
    canSurfaceRender(manifest, 'service_groups')
    || canSurfaceRender(manifest, 'topology')
    || canSurfaceRender(manifest, 'operations_reports');
  const canReviewCloudOps = canSurfaceRender(manifest, 'cloud_accounts');
  const canReviewObservability = canSurfaceRender(manifest, 'observability');
  const priorityServiceGroup = serviceReviewQueue[0] || null;
  const priorityServiceWorkspace = useMemo(
    () => recommendServiceWorkspace(priorityServiceGroup),
    [priorityServiceGroup],
  );
  const priorityWorkspaceLabel = t(
    `ops_workspace_${priorityServiceWorkspace.workspace}_title`,
    priorityServiceWorkspace.workspace === 'discover'
      ? 'Discover'
      : priorityServiceWorkspace.workspace === 'govern'
        ? 'Govern'
        : 'Observe',
  );

  const focusedWorkspace = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return String(params.get('workspace') || '').trim().toLowerCase();
  }, [location.search]);

  useEffect(() => {
    if (!focusedWorkspace) return;
    const target = workspaceRefs.current?.[focusedWorkspace];
    if (!target) return;
    const timer = window.setTimeout(() => {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
    return () => window.clearTimeout(timer);
  }, [focusedWorkspace, workspaceSections.length]);

  useEffect(() => {
    if (!showServiceReviewQueue || !canView) {
      setServiceReviewQueue([]);
      setServiceReviewError('');
      return undefined;
    }

    let cancelled = false;
    setServiceReviewLoading(true);
    void ServiceGroupService.list()
      .then((response) => {
        if (cancelled) return;
        const rows = Array.isArray(response?.data) ? response.data : [];
        setServiceReviewQueue(summarizeServiceReviewQueue(rows, t));
        const posture = summarizeServiceReviewPosture(rows);
        setServiceReviewPosture({
          critical: posture.criticalGroups,
          review: posture.reviewGroups,
          discoveredOnlyPressure: posture.discoveredOnlyPressure,
          activeIssues: posture.activeIssues,
          totalGroups: posture.totalGroups,
          totalHealthScore: posture.totalHealthScore,
        });
        setServiceReviewError('');
      })
      .catch((error) => {
        if (cancelled) return;
        setServiceReviewQueue([]);
        setServiceReviewPosture({
          critical: 0,
          review: 0,
          discoveredOnlyPressure: 0,
          activeIssues: 0,
          totalGroups: 0,
          totalHealthScore: 0,
        });
        setServiceReviewError(error?.response?.data?.detail || error?.message || t('ops_home_service_review_unavailable', 'Service review queue is temporarily unavailable.'));
      })
      .finally(() => {
        if (!cancelled) setServiceReviewLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [showServiceReviewQueue, canView, manifest]);
  const serviceReviewAverageHealth = useMemo(() => {
    return getServiceReviewAverageHealth(serviceReviewPosture);
  }, [serviceReviewPosture]);
  const serviceLaneBoard = useMemo(() => summarizeServiceLaneBoard(serviceReviewPosture), [serviceReviewPosture]);
  const serviceReviewPressureIndex = useMemo(() => {
    return getServicePressureIndex(serviceReviewPosture);
  }, [serviceReviewPosture]);
  const cloudPressureIndex = useMemo(() => getCloudPressureIndex(cloudPressureSummary), [cloudPressureSummary]);
  const observabilityPressureIndex = useMemo(
    () => getObservabilityPressureIndex(observabilityPressureSummary),
    [observabilityPressureSummary],
  );
  const cloudWorkspaceRecommendation = useMemo(
    () => recommendCloudOperationsWorkspace(cloudPressureSummary),
    [cloudPressureSummary],
  );
  const observabilityWorkspaceRecommendation = useMemo(
    () => recommendObservabilityWorkspace(observabilityPressureSummary),
    [observabilityPressureSummary],
  );
  const cloudWorkspaceLabel = getWorkspaceTitle(cloudWorkspaceRecommendation.workspace, t);
  const observabilityWorkspaceLabel = getWorkspaceTitle(observabilityWorkspaceRecommendation.workspace, t);
  const operationsPressureCards = useMemo(() => {
    const cards = [];
    const serviceAction = (() => {
      if (priorityServiceWorkspace.workspace === 'discover') {
        return {
          action: () => navigate('/discovery'),
          actionLabel: t('ops_home_pressure_open_discovery', 'Open Discovery'),
        };
      }
      if (priorityServiceWorkspace.workspace === 'govern') {
        return {
          action: () => navigate('/service-groups'),
          actionLabel: t('ops_home_service_review_open_group', 'Open service review'),
        };
      }
      return {
        action: () => navigate('/notifications?serviceImpact=1&openServiceImpact=1'),
        actionLabel: t('ops_home_pressure_open_service_alerts', 'Open service-aware alerts'),
      };
    })();
    const cloudAction = (() => {
      if (cloudWorkspaceRecommendation.workspace === 'govern') {
        return {
          action: () => navigate('/approval'),
          actionLabel: t('ops_open_approval', 'Open Approval Center'),
        };
      }
      return {
        action: () => navigate('/cloud/accounts'),
        actionLabel: t('ops_home_pressure_open_cloud', 'Open Cloud Accounts'),
      };
    })();
    const observabilityAction = (() => {
      if (observabilityWorkspaceRecommendation.workspace === 'discover') {
        return {
          action: () => navigate('/discovery'),
          actionLabel: t('ops_home_pressure_open_discovery', 'Open Discovery'),
        };
      }
      return {
        action: () => navigate('/observability'),
        actionLabel: t('ops_home_pressure_open_observability', 'Open Observability'),
      };
    })();
    if (showServiceReviewQueue) {
      cards.push({
        key: 'service',
        title: t('ops_home_pressure_service_title', 'Service pressure'),
        value: serviceReviewPressureIndex,
        signalCount: serviceReviewPosture.review + serviceReviewPosture.critical,
        desc: t('ops_home_pressure_service_desc', 'Critical and review-needed service groups are driving operator attention.'),
        helper: t('ops_home_pressure_service_helper', '{count} groups need review').replace('{count}', String(serviceReviewPosture.review)),
        workspace: priorityServiceWorkspace.workspace,
        workspaceLabel: priorityWorkspaceLabel,
        action: serviceAction.action,
        actionLabel: serviceAction.actionLabel,
        reasons: [
          {
            label: t('ops_home_pressure_reason_critical', 'Critical'),
            value: serviceReviewPosture.critical,
          },
          {
            label: t('ops_home_pressure_reason_review', 'Needs review'),
            value: serviceReviewPosture.review,
          },
          {
            label: t('ops_home_pressure_reason_discovered_only', 'Discovered-only'),
            value: serviceReviewPosture.discoveredOnlyPressure,
          },
        ],
      });
    }
    if (canReviewCloudOps) {
      cards.push({
        key: 'cloud',
        title: t('ops_home_pressure_cloud_title', 'Cloud pressure'),
        value: cloudPressureIndex,
        signalCount: cloudPressureSummary.attention + cloudPressureSummary.pendingApprovals + cloudPressureSummary.retryRecommended,
        desc: t('ops_home_pressure_cloud_desc', 'Cloud accounts waiting on recovery, approval, or retry stay visible at the front door.'),
        helper: t('ops_home_pressure_cloud_helper', '{count} accounts need review').replace('{count}', String(cloudPressureSummary.attention)),
        workspace: cloudWorkspaceRecommendation.workspace,
        workspaceLabel: cloudWorkspaceLabel,
        action: cloudAction.action,
        actionLabel: cloudAction.actionLabel,
        loading: cloudPressureLoading,
        error: cloudPressureError,
        reasons: [
          {
            label: t('ops_home_pressure_reason_attention', 'Attention'),
            value: cloudPressureSummary.attention,
          },
          {
            label: t('ops_home_pressure_reason_pending_approvals', 'Pending approvals'),
            value: cloudPressureSummary.pendingApprovals,
          },
          {
            label: t('ops_home_pressure_reason_retry', 'Retry suggested'),
            value: cloudPressureSummary.retryRecommended,
          },
        ],
      });
    }
    if (canReviewObservability) {
      cards.push({
        key: 'observability',
        title: t('ops_home_pressure_observability_title', 'Observability pressure'),
        value: observabilityPressureIndex,
        signalCount: observabilityPressureSummary.offline + observabilityPressureSummary.unreadCount,
        desc: t('ops_home_pressure_observability_desc', 'Offline devices and unread signals should funnel operators into the right analysis path quickly.'),
        helper: t('ops_home_pressure_observability_helper', '{count} unread or offline signals').replace(
          '{count}',
          String(observabilityPressureSummary.offline + observabilityPressureSummary.unreadCount),
          ),
          workspace: observabilityWorkspaceRecommendation.workspace,
          workspaceLabel: observabilityWorkspaceLabel,
          action: observabilityAction.action,
          actionLabel: observabilityAction.actionLabel,
          loading: observabilityPressureLoading,
          error: observabilityPressureError,
        reasons: [
          {
            label: t('ops_home_pressure_reason_offline', 'Offline'),
            value: observabilityPressureSummary.offline,
          },
          {
            label: t('ops_home_pressure_reason_unread', 'Unread'),
            value: observabilityPressureSummary.unreadCount,
          },
          {
            label: t('ops_home_pressure_reason_devices', 'Devices'),
            value: observabilityPressureSummary.devices,
          },
        ],
      });
    }
    return cards;
  }, [
    canReviewCloudOps,
    canReviewObservability,
    cloudPressureError,
    cloudPressureIndex,
    cloudPressureLoading,
    cloudPressureSummary.attention,
      cloudPressureSummary.pendingApprovals,
      cloudPressureSummary.retryRecommended,
      cloudWorkspaceLabel,
      cloudWorkspaceRecommendation.workspace,
      navigate,
    observabilityPressureError,
    observabilityPressureIndex,
    observabilityPressureLoading,
      observabilityPressureSummary.offline,
      observabilityPressureSummary.unreadCount,
      observabilityWorkspaceLabel,
      observabilityWorkspaceRecommendation.workspace,
      priorityServiceWorkspace.workspace,
    priorityWorkspaceLabel,
    serviceReviewPosture.critical,
    serviceReviewPosture.review,
    serviceReviewPressureIndex,
    showServiceReviewQueue,
  ]);
  const primaryPressureCard = useMemo(() => getOperationsPrimaryPressure(operationsPressureCards), [operationsPressureCards]);
  const followUpPressureCards = useMemo(() => {
    if (!primaryPressureCard) return [];
    return operationsPressureCards
      .filter((card) => card.key !== primaryPressureCard.key)
      .sort((left, right) => Number(right?.value || 0) - Number(left?.value || 0))
      .slice(0, 2);
  }, [operationsPressureCards, primaryPressureCard]);

  useEffect(() => {
    if (!canReviewCloudOps || !canView) {
      setCloudPressureSummary({ attention: 0, syncing: 0, pendingApprovals: 0, retryRecommended: 0, total: 0 });
      setCloudReviewQueue([]);
      setCloudLaneBoard({ approval: 0, recovery: 0, sync: 0, stable: 0 });
      setCloudRetryQueue([]);
      setCloudExecutionHighlights([]);
      setCloudScheduleQueue([]);
      setCloudPressureError('');
      return undefined;
    }
    let cancelled = false;
    setCloudPressureLoading(true);
    void CloudService.getOperationsLedger()
      .then((response) => {
        if (cancelled) return;
        const rows = Array.isArray(response?.data) ? response.data : [];
        setCloudPressureSummary(summarizeCloudOperationsPressure(rows));
        setCloudReviewQueue(summarizeCloudReviewQueue(rows, t));
        setCloudLaneBoard(summarizeCloudLaneBoard(rows));
        setCloudRetryQueue(summarizeCloudRetryQueue(rows));
        setCloudExecutionHighlights(summarizeCloudExecutionHighlights(rows));
        setCloudScheduleQueue(summarizeCloudScheduleQueue(rows, t));
        setCloudPressureError('');
      })
      .catch((error) => {
        if (cancelled) return;
        setCloudPressureSummary({ attention: 0, syncing: 0, pendingApprovals: 0, retryRecommended: 0, total: 0 });
        setCloudReviewQueue([]);
        setCloudLaneBoard({ approval: 0, recovery: 0, sync: 0, stable: 0 });
        setCloudRetryQueue([]);
        setCloudExecutionHighlights([]);
        setCloudScheduleQueue([]);
        setCloudPressureError(error?.response?.data?.detail || error?.message || t('ops_home_pressure_cloud_unavailable', 'Cloud pressure is temporarily unavailable.'));
      })
      .finally(() => {
        if (!cancelled) setCloudPressureLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canReviewCloudOps, canView, manifest]);

  useEffect(() => {
    if (!canReviewObservability || !canView) {
      setObservabilityPressureSummary({ devices: 0, online: 0, offline: 0, unreadCount: 0 });
      setObservabilityPressureError('');
      return undefined;
    }
    let cancelled = false;
    setObservabilityPressureLoading(true);
    void Promise.all([ObservabilityService.summary(), IssueService.getUnreadCount()])
      .then(([summaryResponse, unreadResponse]) => {
        if (cancelled) return;
        setObservabilityPressureSummary(
          summarizeObservabilityPressure({
            summary: summaryResponse?.data || null,
            unreadCount: Number(unreadResponse?.data?.count || 0),
          }),
        );
        setObservabilityPressureError('');
      })
      .catch((error) => {
        if (cancelled) return;
        setObservabilityPressureSummary({ devices: 0, online: 0, offline: 0, unreadCount: 0 });
        setObservabilityPressureError(error?.response?.data?.detail || error?.message || t('ops_home_pressure_observability_unavailable', 'Observability pressure is temporarily unavailable.'));
      })
      .finally(() => {
        if (!cancelled) setObservabilityPressureLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canReviewObservability, canView, manifest]);

  const runBlobDownload = async ({ key, request, fallbackFilename, contentType, successMessage, errorMessage }) => {
    setDownloadState((current) => ({ ...current, [key]: true }));
    try {
      const response = await request();
      const filename = parseFilename(response?.headers?.['content-disposition']) || fallbackFilename;
      downloadBlob(response?.data, filename, contentType);
      toast.success(successMessage);
    } catch (error) {
      toast.error(error?.response?.data?.detail || error?.message || errorMessage);
    } finally {
      setDownloadState((current) => ({ ...current, [key]: false }));
    }
  };

  const openServiceReview = (group) => {
    const numericGroupId = Number(group?.id || 0);
    if (numericGroupId <= 0) {
      navigate('/service-groups');
      return;
    }
    const params = new URLSearchParams();
    params.set('focusGroupId', String(numericGroupId));
    if (String(group?.name || '').trim()) {
      params.set('focusGroupName', String(group.name).trim());
    }
    navigate(`/service-groups?${params.toString()}`);
  };

  const openServiceReports = (group) => {
    const numericGroupId = Number(group?.id || 0);
    if (numericGroupId <= 0) {
      navigate('/operations-reports');
      return;
    }
    const params = new URLSearchParams();
    params.set('focusGroupId', String(numericGroupId));
    if (String(group?.name || '').trim()) {
      params.set('focusGroupName', String(group.name).trim());
    }
    navigate(`/operations-reports?${params.toString()}`);
  };

  const openServiceTopology = (group) => {
    const numericGroupId = Number(group?.id || 0);
    if (numericGroupId <= 0) {
      navigate('/topology');
      return;
    }
    const params = new URLSearchParams();
    params.set('serviceGroupId', String(numericGroupId));
    params.set('serviceMap', '1');
    if (String(group?.name || '').trim()) {
      params.set('focusGroupName', String(group.name).trim());
    }
    navigate(`/topology?${params.toString()}`);
  };

  const openServiceNotifications = (group) => {
    const numericGroupId = Number(group?.id || 0);
    const params = new URLSearchParams();
    params.set('serviceImpact', '1');
    params.set('openServiceImpact', '1');
    if (numericGroupId > 0) {
      params.set('focusGroupId', String(numericGroupId));
    }
    if (String(group?.name || '').trim()) {
      params.set('focusGroupName', String(group.name).trim());
    }
    navigate(`/notifications?${params.toString()}`);
  };

  const openCloudReview = (entry) => {
    const numericAccountId = Number(entry?.accountId || 0);
    if (numericAccountId <= 0) {
      navigate('/cloud/accounts');
      return;
    }
    const params = new URLSearchParams();
    params.set('focusAccountId', String(numericAccountId));
    navigate(`/cloud/accounts?${params.toString()}`);
  };

  const openCloudApproval = (entry) => {
    const approvalId = Number(entry?.latestApprovalId || 0);
    if (approvalId > 0) {
      navigate(`/approval?focusRequestId=${approvalId}`);
      return;
    }
    navigate('/approval');
  };

  const openCloudIntents = () => {
    navigate('/cloud/intents');
  };

  if (!canView) {
    return (
      <div className="p-6">
        <div className="max-w-3xl bg-white/90 dark:bg-[#1b1d1f]/90 border border-gray-200 dark:border-white/5 rounded-2xl p-6 shadow-sm">
          <div className="text-lg font-bold text-gray-900 dark:text-white">{t('access_denied_title')}</div>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">{t('access_denied_desc')}</div>
        </div>
      </div>
    );
  }

  if (loading && !manifest) {
    return (
      <div className="p-6">
        <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 p-6 text-sm text-gray-600 dark:text-gray-300">
          {t('common_loading', 'Loading...')}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0 gap-6 animate-fade-in text-gray-900 dark:text-white font-sans pb-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-end pb-4 border-b border-gray-200 dark:border-white/5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white/90 flex items-center gap-2">
              <Workflow size={20} /> {t('ops_home_title', 'Operations Home')}
            </h1>
          </div>
          <p className="text-xs text-gray-500 pl-4">
            {t(
              'ops_home_desc',
              'Start from Observe, Discover, Control, and Govern so the same platform reads like one operating flow instead of a loose toolbox.',
            )}
          </p>
        </div>
      </div>

      {previewEnabled && (
        <div
          data-testid="automation-preview-panel"
          className="rounded-2xl border border-blue-200 dark:border-blue-900/40 bg-blue-50/70 dark:bg-blue-950/10 p-5 shadow-sm"
        >
          <div className="flex items-center gap-2">
            <Workflow size={16} className="text-blue-600 dark:text-blue-300" />
            <div data-testid="automation-preview-title" className="text-sm font-black text-blue-900 dark:text-blue-100">
              {t('automation_preview_title', 'NetSphere Free Experience')}
            </div>
          </div>
          <div data-testid="automation-preview-desc" className="mt-2 text-sm text-blue-800 dark:text-blue-200">
            {t(
              'automation_preview_desc',
              'NetSphere Free should first prove Auto Discovery, Auto Topology, and Connected NMS value. Active management stays limited while larger operating workflows remain Pro surfaces.',
            )}
          </div>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
            {experiencePillars.map((pillar) => (
              <button
                key={pillar.key}
                type="button"
                onClick={() => navigate(pillar.route)}
                data-testid={`automation-preview-pillar-${pillar.key}`}
                className="rounded-2xl border border-blue-200 dark:border-blue-900/40 bg-white/90 dark:bg-black/20 p-4 text-left hover:bg-blue-50 dark:hover:bg-blue-950/20 transition-colors"
              >
                <div className="text-sm font-black text-gray-900 dark:text-white">{pillar.title}</div>
                <div className="mt-2 text-xs text-gray-600 dark:text-gray-300">{pillar.desc}</div>
                <div className="mt-3 text-[11px] font-extrabold text-blue-600 dark:text-blue-300">
                  {t('automation_preview_open_cta', 'Open ->')}
                </div>
              </button>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => navigate('/edition/compare')}
              data-testid="automation-preview-compare"
              className="rounded-2xl border border-blue-200 dark:border-blue-900/40 bg-white/90 dark:bg-black/20 px-4 py-2 text-xs font-bold text-blue-700 dark:text-blue-200 hover:bg-blue-50 dark:hover:bg-blue-950/20 transition-colors"
            >
              {t('automation_preview_compare_cta', 'Compare Free and Pro operations')}
            </button>
            {previewContext?.managed_node_limit ? (
              <span className="text-xs text-blue-900 dark:text-blue-100">
                {t('edition_compare_value_managed_limit', 'Managed up to {count} nodes').replace('{count}', String(previewContext.managed_node_limit))}
              </span>
            ) : null}
          </div>
          {blockedFeatures.length > 0 && (
            <div data-testid="automation-preview-blocked-features" className="mt-4 flex flex-wrap gap-2">
              {blockedFeatures.map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-amber-300 dark:border-amber-900/50 bg-white/80 dark:bg-black/20 px-3 py-1 text-[11px] font-semibold text-amber-800 dark:text-amber-200"
                >
                  {t('automation_preview_blocked_prefix', 'Blocked:')} {item}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {!previewEnabled && (
        <div
          data-testid="automation-pro-operations-panel"
          className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 p-5 shadow-sm"
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                {t('ops_health_title', 'Operational Quick Actions')}
              </div>
              <div className="mt-2 text-sm font-black text-gray-900 dark:text-white">
                {t(
                  'ops_quick_actions_desc',
                  'Move directly into approval, observability, notifications, and downloadable operator evidence from one operating surface.',
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="automation-open-approval"
                onClick={() => navigate('/approval')}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center gap-2"
              >
                <CheckCircle size={14} />
                {t('ops_open_approval', 'Open Approval Center')}
              </button>
              <button
                type="button"
                data-testid="automation-open-compliance"
                onClick={() => navigate('/compliance')}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center gap-2"
              >
                <FileCheck size={14} />
                {t('ops_open_compliance', 'Open Compliance')}
              </button>
              <button
                type="button"
                data-testid="automation-open-notifications"
                onClick={() => navigate('/notifications')}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center gap-2"
              >
                <Bell size={14} />
                {t('ops_open_notifications', 'Open Notifications')}
              </button>
              <button
                type="button"
                data-testid="automation-open-settings"
                onClick={() => navigate('/settings')}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center gap-2"
              >
                <Shield size={14} />
                {t('ops_open_settings', 'Open Settings')}
              </button>
              <button
                type="button"
                data-testid="automation-open-observability"
                onClick={() => navigate('/observability')}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center gap-2"
              >
                <Activity size={14} />
                {t('ops_open_observability', 'Open Observability')}
              </button>
              <a
                data-testid="automation-open-alert-dashboard"
                href={buildGrafanaAlertingCenterUrl()}
                target="_blank"
                rel="noreferrer"
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center gap-2"
              >
                {t('obs_alert_dashboard', 'Alert Dashboard')} <ExternalLink size={14} />
              </a>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2">
            <button
              type="button"
              data-testid="automation-download-pro-operator-package"
              disabled={downloadState.operatorPackage}
              onClick={() =>
                runBlobDownload({
                  key: 'operatorPackage',
                  request: () => OpsService.downloadProOperatorPackage(),
                  fallbackFilename: 'pro_operator_package.zip',
                  contentType: 'application/zip',
                  successMessage: t('ops_download_operator_package_success', 'Operator package downloaded.'),
                  errorMessage: t('ops_download_operator_package_failed', 'Failed to download the operator package.'),
                })
              }
              className="px-3 py-2 rounded-lg text-xs font-bold bg-primary text-white hover:opacity-90 transition-opacity disabled:opacity-60 inline-flex items-center justify-center gap-2"
            >
              {downloadState.operatorPackage ? <RefreshCw size={14} className="animate-spin" /> : <Package size={14} />}
              {t('ops_download_operator_package', 'Download Operator Package')}
            </button>
            <button
              type="button"
              data-testid="automation-download-support-bundle"
              disabled={downloadState.supportBundle}
              onClick={() =>
                runBlobDownload({
                  key: 'supportBundle',
                  request: () => SupportService.bundle({ days: 7, limit_per_table: 5000, include_app_log: true }),
                  fallbackFilename: 'support_bundle.zip',
                  contentType: 'application/zip',
                  successMessage: t('settings_support_bundle_downloaded', 'Support bundle downloaded.'),
                  errorMessage: t('settings_support_bundle_download_failed', 'Support bundle download failed'),
                })
              }
              className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center justify-center gap-2"
            >
              {downloadState.supportBundle ? <RefreshCw size={14} className="animate-spin" /> : <Package size={14} />}
              {t('ops_download_support_bundle', 'Download Support Bundle')}
            </button>
            <button
              type="button"
              data-testid="automation-download-release-bundle"
              disabled={downloadState.releaseBundle}
              onClick={() =>
                runBlobDownload({
                  key: 'releaseBundle',
                  request: () => OpsService.downloadReleaseEvidenceBundle(),
                  fallbackFilename: 'release_evidence_bundle.zip',
                  contentType: 'application/zip',
                  successMessage: t('dashboard_release_bundle_downloaded', 'Release evidence bundle downloaded.'),
                  errorMessage: t('dashboard_release_bundle_download_failed', 'Failed to download release evidence bundle.'),
                })
              }
              className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center justify-center gap-2"
            >
              {downloadState.releaseBundle ? <RefreshCw size={14} className="animate-spin" /> : <FileText size={14} />}
              {t('ops_download_release_evidence', 'Download Release Evidence')}
            </button>
            <button
              type="button"
              data-testid="automation-download-compliance-export"
              disabled={downloadState.complianceExport}
              onClick={() =>
                runBlobDownload({
                  key: 'complianceExport',
                  request: () => ComplianceService.exportReports({ format: 'xlsx' }),
                  fallbackFilename: 'compliance_reports.xlsx',
                  contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                  successMessage: t('ops_download_compliance_export_success', 'Compliance export downloaded.'),
                  errorMessage: t('compliance_export_failed', 'Export failed'),
                })
              }
              className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center justify-center gap-2"
            >
              {downloadState.complianceExport ? <RefreshCw size={14} className="animate-spin" /> : <FileCheck size={14} />}
              {t('ops_download_compliance_export', 'Download Compliance Export')}
            </button>
            <a
              data-testid="automation-open-fleet-dashboard"
              href={buildGrafanaFleetHealthUrl()}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center justify-center gap-2"
            >
              {t('ops_open_fleet_dashboard', 'Open Fleet Dashboard')} <ExternalLink size={14} />
            </a>
            <a
              data-testid="automation-open-control-plane-dashboard"
              href={buildGrafanaOperationsControlPlaneUrl()}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center justify-center gap-2"
            >
              {t('ops_open_control_plane', 'Open Control Plane')} <ExternalLink size={14} />
            </a>
            <a
              data-testid="automation-open-discovery-topology-dashboard"
              href={buildGrafanaDiscoveryTopologyOpsUrl()}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center justify-center gap-2"
            >
              {t('ops_open_discovery_topology', 'Open Discovery and Topology')} <ExternalLink size={14} />
            </a>
            <a
              data-testid="automation-open-compliance-automation-dashboard"
              href={buildGrafanaComplianceAutomationOpsUrl()}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center justify-center gap-2"
            >
              {t('ops_open_compliance_automation', 'Open Compliance and Automation')} <ExternalLink size={14} />
            </a>
          </div>
        </div>
      )}

      <section
        data-testid="operations-home-quick-flows"
        className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 p-5 shadow-sm"
      >
        <div className="flex items-center gap-2">
          <Workflow size={16} className="text-primary" />
          <div className="text-base font-black text-gray-900 dark:text-white">
            {t('ops_quick_flow_title', 'Start from a live workflow')}
          </div>
        </div>
        <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
          {t(
            'ops_quick_flow_desc',
            'Use these guided entry points when you want the platform to feel like one operating sequence instead of a list of pages.',
          )}
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          {quickFlows.map((flow) => (
            <button
              key={flow.key}
              type="button"
              data-testid={`operations-quick-flow-${flow.key}`}
              onClick={() => navigate(flow.route)}
              className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 p-4 text-left hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
            >
              <div className="text-sm font-black text-gray-900 dark:text-white">{flow.title}</div>
              <div className="mt-2 text-xs text-gray-600 dark:text-gray-300">{flow.desc}</div>
              <div className="mt-3 text-[11px] font-extrabold text-blue-600 dark:text-blue-300">
                {t('common_open', 'Open')} -&gt;
              </div>
            </button>
          ))}
        </div>
      </section>

      {operationsPressureCards.length > 0 && (
        <section
          data-testid="operations-home-pressure-board"
          className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 p-5 shadow-sm"
        >
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-primary" />
            <div className="text-base font-black text-gray-900 dark:text-white">
              {t('ops_home_pressure_board_title', 'Operator pressure board')}
            </div>
          </div>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            {t(
              'ops_home_pressure_board_desc',
              'Compare service, cloud, and observability pressure in one place so the next workspace is obvious before you dive into details.',
            )}
          </div>

          {primaryPressureCard ? (
            <div
              data-testid="operations-home-primary-focus"
              className="mt-4 rounded-2xl border border-indigo-200/80 dark:border-indigo-900/40 bg-indigo-50/70 dark:bg-indigo-950/10 p-4"
            >
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="text-[11px] font-black uppercase tracking-[0.16em] text-indigo-700 dark:text-indigo-300">
                    {t('ops_home_primary_focus_title', 'Primary focus now')}
                  </div>
                  <div className="mt-2 text-sm font-black text-gray-900 dark:text-white">
                    {primaryPressureCard.title}
                  </div>
                  <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                    {primaryPressureCard.desc}
                  </div>
                  <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {t('ops_home_primary_focus_desc', 'Start with the recommended workspace to keep the busiest operational lane moving first.')}
                  </div>
                  <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {t('ops_home_pressure_recommended_surface', 'Recommended surface {value}').replace('{value}', primaryPressureCard.actionLabel)}
                  </div>
                  <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {t('ops_home_primary_focus_signal_count', '{value} active signals are driving this lane.')
                      .replace('{value}', String(primaryPressureCard.signalCount || 0))}
                  </div>
                  <div className="mt-3">
                    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-bold ${pressureBadgeClass(primaryPressureCard.value)}`}>
                      {getOperationsPressureLabel(primaryPressureCard.value, t)}
                    </span>
                  </div>
                  <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {getOperationsPressureGuidance(primaryPressureCard.value, t)}
                  </div>
                  {Array.isArray(primaryPressureCard.reasons) && primaryPressureCard.reasons.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2" data-testid="operations-home-primary-focus-reasons">
                      {primaryPressureCard.reasons.map((reason) => (
                        <span
                          key={`${primaryPressureCard.key}-${reason.label}`}
                          className="rounded-full border border-indigo-200/80 dark:border-indigo-900/40 bg-white/80 dark:bg-black/20 px-2.5 py-1 text-[11px] font-semibold text-indigo-700 dark:text-indigo-200"
                        >
                          {t('ops_home_pressure_reason_chip', '{label} {value}')
                            .replace('{label}', reason.label)
                            .replace('{value}', String(reason.value ?? 0))}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    data-testid="operations-home-primary-focus-open-workspace"
                    onClick={() => navigate(`/automation?workspace=${primaryPressureCard.workspace}`)}
                    className="rounded-lg border border-indigo-200 dark:border-indigo-900/40 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-indigo-800 dark:text-indigo-200 hover:bg-indigo-50 dark:hover:bg-indigo-950/20 transition-colors"
                  >
                    {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', primaryPressureCard.workspaceLabel)}
                  </button>
                  <button
                    type="button"
                    data-testid="operations-home-primary-focus-open-surface"
                    onClick={primaryPressureCard.action}
                    className="rounded-lg border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                  >
                    {primaryPressureCard.actionLabel}
                  </button>
                </div>
              </div>
              {followUpPressureCards.length > 0 ? (
                <div
                  className="mt-4 border-t border-indigo-200/70 dark:border-indigo-900/30 pt-4"
                  data-testid="operations-home-primary-focus-follow-ups"
                >
                  <div className="text-[10px] font-black uppercase tracking-[0.18em] text-indigo-700 dark:text-indigo-300">
                    {t('ops_home_primary_focus_follow_ups', 'Next lanes to watch')}
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                    {followUpPressureCards.map((card) => (
                      <div
                        key={`primary-follow-up-${card.key}`}
                        className="rounded-2xl border border-indigo-200/70 dark:border-indigo-900/30 bg-white/80 dark:bg-black/20 p-3"
                        data-testid={`operations-home-primary-follow-up-${card.key}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-black text-gray-900 dark:text-white">{card.title}</div>
                            <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">{card.desc}</div>
                          </div>
                          <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-bold ${pressureBadgeClass(card.value)}`}>
                            {getOperationsPressureLabel(card.value, t)}
                          </span>
                        </div>
                        <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
                          {t('ops_home_primary_focus_follow_up_surface', 'Then move into {value}')
                            .replace('{value}', card.actionLabel)}
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                          {getOperationsPressureGuidance(card.value, t)}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            data-testid={`operations-home-primary-follow-up-open-workspace-${card.key}`}
                            onClick={() => navigate(`/automation?workspace=${card.workspace}`)}
                            className="rounded-lg border border-indigo-200 dark:border-indigo-900/40 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-indigo-800 dark:text-indigo-200 hover:bg-indigo-50 dark:hover:bg-indigo-950/20 transition-colors"
                          >
                            {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', card.workspaceLabel)}
                          </button>
                          <button
                            type="button"
                            data-testid={`operations-home-primary-follow-up-open-surface-${card.key}`}
                            onClick={card.action}
                            className="rounded-lg border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                          >
                            {card.actionLabel}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-3">
            {operationsPressureCards.map((card) => (
              <div
                key={card.key}
                data-testid={`operations-home-pressure-card-${card.key}`}
                className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-black text-gray-900 dark:text-white">{card.title}</div>
                    <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">{card.desc}</div>
                  </div>
                  <span className="rounded-full border border-fuchsia-200 bg-fuchsia-50 px-2.5 py-1 text-[10px] font-extrabold tracking-[0.14em] text-fuchsia-700 dark:border-fuchsia-900/40 dark:bg-fuchsia-950/20 dark:text-fuchsia-200">
                    {card.value}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-600 dark:text-gray-300">
                  <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                    {t('ops_home_pressure_signals', 'Signals {value}').replace('{value}', String(card.signalCount || 0))}
                  </span>
                  <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                    {t('ops_home_pressure_recommended_workspace', 'Recommended {value}').replace('{value}', card.workspaceLabel)}
                  </span>
                  <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                    {t('ops_home_pressure_recommended_surface', 'Recommended surface {value}').replace('{value}', card.actionLabel)}
                  </span>
                  <span className={`rounded-full border px-2.5 py-1 font-semibold ${pressureBadgeClass(card.value)}`}>
                    {getOperationsPressureLabel(card.value, t)}
                  </span>
                </div>
                <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                  {getOperationsPressureGuidance(card.value, t)}
                </div>
                <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                  {card.error ? card.error : card.loading ? t('common_loading', 'Loading...') : card.helper}
                </div>
                {Array.isArray(card.reasons) && card.reasons.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {card.reasons.map((reason) => (
                      <span
                        key={`${card.key}-${reason.label}`}
                        className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1 text-[11px] font-semibold text-gray-600 dark:text-gray-300"
                      >
                        {t('ops_home_pressure_reason_chip', '{label} {value}')
                          .replace('{label}', reason.label)
                          .replace('{value}', String(reason.value ?? 0))}
                      </span>
                    ))}
                  </div>
                ) : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    data-testid={`operations-home-pressure-open-workspace-${card.key}`}
                    onClick={() => navigate(`/automation?workspace=${card.workspace}`)}
                    className="rounded-lg border border-blue-200 dark:border-blue-900/40 bg-blue-50 dark:bg-blue-950/20 px-3 py-2 text-xs font-bold text-blue-800 dark:text-blue-200 hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
                  >
                    {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', card.workspaceLabel)}
                  </button>
                  <button
                    type="button"
                    data-testid={`operations-home-pressure-open-surface-${card.key}`}
                    onClick={card.action}
                    className="rounded-lg border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                  >
                    {card.actionLabel}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {showServiceReviewQueue && (
        <section
          data-testid="operations-home-service-review-queue"
          className="rounded-2xl border border-cyan-200 dark:border-cyan-900/40 bg-cyan-50/70 dark:bg-cyan-950/10 p-5 shadow-sm"
        >
          <div className="flex items-center gap-2">
            <Bell size={16} className="text-cyan-600 dark:text-cyan-300" />
            <div className="text-base font-black text-gray-900 dark:text-white">
              {t('ops_home_service_review_title', 'Service review queue')}
            </div>
          </div>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            {t(
              'ops_home_service_review_desc',
              'Bring the highest-impact service groups to the front door so operators can move directly into review, topology, and operations reports.',
            )}
          </div>
          {!serviceReviewLoading && !serviceReviewError ? (
            <div
              data-testid="operations-home-service-posture"
              className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-6"
            >
              <div className="rounded-xl border border-rose-200/70 bg-rose-50/70 p-3 dark:border-rose-900/40 dark:bg-rose-950/10">
                <div className="text-[10px] font-black uppercase tracking-widest text-rose-700 dark:text-rose-300">
                  {t('ops_home_service_posture_critical', 'Critical services')}
                </div>
                <div className="mt-1 text-2xl font-black text-rose-700 dark:text-rose-200">
                  {serviceReviewPosture.critical}
                </div>
              </div>
              <div className="rounded-xl border border-amber-200/70 bg-amber-50/70 p-3 dark:border-amber-900/40 dark:bg-amber-950/10">
                <div className="text-[10px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
                  {t('ops_home_service_posture_review', 'Needs review')}
                </div>
                <div className="mt-1 text-2xl font-black text-amber-700 dark:text-amber-200">
                  {serviceReviewPosture.review}
                </div>
              </div>
              <div className="rounded-xl border border-cyan-200/70 bg-cyan-50/70 p-3 dark:border-cyan-900/40 dark:bg-cyan-950/10">
                <div className="text-[10px] font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-300">
                  {t('ops_home_service_posture_discovered_only', 'Discovered-only pressure')}
                </div>
                <div className="mt-1 text-2xl font-black text-cyan-700 dark:text-cyan-200">
                  {serviceReviewPosture.discoveredOnlyPressure}
                </div>
              </div>
              <div className="rounded-xl border border-indigo-200/70 bg-indigo-50/70 p-3 dark:border-indigo-900/40 dark:bg-indigo-950/10">
                <div className="text-[10px] font-black uppercase tracking-widest text-indigo-700 dark:text-indigo-300">
                  {t('operations_reports_metric_service_issues', 'Service-Scoped Issues')}
                </div>
                <div className="mt-1 text-2xl font-black text-indigo-700 dark:text-indigo-200">
                  {serviceReviewPosture.activeIssues}
                </div>
              </div>
              <div className="rounded-xl border border-sky-200/70 bg-sky-50/70 p-3 dark:border-sky-900/40 dark:bg-sky-950/10">
                <div className="text-[10px] font-black uppercase tracking-widest text-sky-700 dark:text-sky-300">
                  {t('service_operating_posture_average_health', 'Average health')}
                </div>
                <div className="mt-1 text-2xl font-black text-sky-700 dark:text-sky-200">
                  {serviceReviewAverageHealth}
                </div>
              </div>
              <div className="rounded-xl border border-fuchsia-200/70 bg-fuchsia-50/70 p-3 dark:border-fuchsia-900/40 dark:bg-fuchsia-950/10">
                <div className="text-[10px] font-black uppercase tracking-widest text-fuchsia-700 dark:text-fuchsia-300">
                  {t('service_operating_posture_pressure_index', 'Pressure index')}
                </div>
                <div className="mt-1 text-2xl font-black text-fuchsia-700 dark:text-fuchsia-200">
                  {serviceReviewPressureIndex}
                </div>
              </div>
            </div>
          ) : null}
          {!serviceReviewLoading && !serviceReviewError && serviceReviewPosture.totalGroups > 0 ? (
            <div data-testid="operations-home-service-lane-board" className="mt-4 rounded-xl border border-cyan-200/80 dark:border-cyan-900/40 bg-white/90 dark:bg-black/20 px-4 py-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-cyan-700 dark:text-cyan-300">
                {t('ops_home_service_lane_board_title', 'Service operating lanes')}
              </div>
              <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                {t(
                  'ops_home_service_lane_board_desc',
                  'Keep critical response, review alignment, discovered-only promotion, and stable baseline lanes visible before opening a single service review.',
                )}
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4 text-xs">
                <div data-testid="operations-home-service-lane-card-critical" className="rounded-lg border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/10 px-3 py-3">
                  <div className="text-[10px] font-bold text-rose-700 dark:text-rose-300">
                    {t('ops_home_service_lane_critical', 'Critical response')}
                  </div>
                  <div className="mt-1 text-lg font-black text-rose-700 dark:text-rose-300">{serviceLaneBoard.critical}</div>
                </div>
                <div data-testid="operations-home-service-lane-card-review" className="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/10 px-3 py-3">
                  <div className="text-[10px] font-bold text-amber-700 dark:text-amber-300">
                    {t('ops_home_service_lane_review', 'Review alignment')}
                  </div>
                  <div className="mt-1 text-lg font-black text-amber-700 dark:text-amber-300">{serviceLaneBoard.review}</div>
                </div>
                <div data-testid="operations-home-service-lane-card-discovered" className="rounded-lg border border-violet-200 dark:border-violet-900/40 bg-violet-50 dark:bg-violet-950/10 px-3 py-3">
                  <div className="text-[10px] font-bold text-violet-700 dark:text-violet-300">
                    {t('ops_home_service_lane_discovered', 'Promotion pressure')}
                  </div>
                  <div className="mt-1 text-lg font-black text-violet-700 dark:text-violet-300">{serviceLaneBoard.discoveredOnly}</div>
                </div>
                <div data-testid="operations-home-service-lane-card-stable" className="rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/10 px-3 py-3">
                  <div className="text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                    {t('ops_home_service_lane_stable', 'Stable baseline')}
                  </div>
                  <div className="mt-1 text-lg font-black text-emerald-700 dark:text-emerald-300">{serviceLaneBoard.stable}</div>
                </div>
              </div>
            </div>
          ) : null}
          {!serviceReviewLoading && !serviceReviewError && priorityServiceGroup ? (
            <div
              data-testid="operations-home-service-review-next-step"
              className="mt-4 rounded-2xl border border-sky-200/80 dark:border-sky-900/40 bg-white/90 dark:bg-black/20 p-4"
            >
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="text-[11px] font-black uppercase tracking-[0.16em] text-sky-700 dark:text-sky-300">
                    {t('ops_home_service_review_recommended_title', 'Recommended next move')}
                  </div>
                  <div className="mt-2 text-sm font-black text-gray-900 dark:text-white">
                    {priorityServiceGroup.name}
                  </div>
                  <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                    {priorityServiceGroup.nextAction}
                  </div>
                  <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {t(
                      'ops_home_service_review_recommended_desc',
                      'Start from the suggested workspace so alerts, topology, and reporting stay aligned for the highest-impact service.',
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    data-testid="operations-home-service-review-open-priority-workspace"
                    onClick={() => navigate(`/automation?workspace=${priorityServiceWorkspace.workspace}`)}
                    className="rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 px-3 py-2 text-xs font-bold text-sky-800 dark:text-sky-200 hover:bg-sky-100 dark:hover:bg-sky-900/30 transition-colors"
                  >
                    {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', priorityWorkspaceLabel)}
                  </button>
                  <button
                    type="button"
                    data-testid="operations-home-service-review-open-priority-group"
                    onClick={() => openServiceReview(priorityServiceGroup)}
                    className="rounded-lg border border-cyan-200 dark:border-cyan-900/40 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-cyan-800 dark:text-cyan-200 hover:bg-cyan-50 dark:hover:bg-cyan-950/20 transition-colors"
                  >
                    {t('ops_home_service_review_open_group', 'Open service review')}
                  </button>
                </div>
              </div>
            </div>
          ) : null}
          {serviceReviewLoading ? (
            <div className="mt-4 rounded-xl border border-cyan-200/80 dark:border-cyan-900/40 bg-white/80 dark:bg-black/20 px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
              {t('ops_home_service_review_loading', 'Loading the current service review queue...')}
            </div>
          ) : serviceReviewError ? (
            <div className="mt-4 rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50/80 dark:bg-amber-950/20 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
              {serviceReviewError}
            </div>
          ) : serviceReviewQueue.length === 0 ? (
            <div className="mt-4 rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-white/80 dark:bg-black/20 px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
              {t('ops_home_service_review_empty', 'No service groups need immediate review right now.')}
            </div>
          ) : (
            <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
              {serviceReviewQueue.map((group) => (
                <div
                  key={group.id}
                  data-testid={`operations-home-service-review-item-${group.id}`}
                  className="rounded-2xl border border-cyan-200/80 dark:border-cyan-900/40 bg-white/90 dark:bg-black/20 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-black text-gray-900 dark:text-white truncate">{group.name}</div>
                      <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                        {group.description || t('ops_home_service_review_no_description', 'No service summary has been added yet.')}
                      </div>
                    </div>
                    <span className={`rounded-full border px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${serviceHealthTone(group.healthStatus)}`}>
                      {String(group.healthStatus || 'healthy')}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-600 dark:text-gray-300">
                    <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                      {t('ops_home_service_review_health_score', 'Health {value}').replace('{value}', String(group.healthScore))}
                    </span>
                    <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                      {t('ops_home_service_review_active_issues', 'Issues {value}').replace('{value}', String(group.activeIssueCount))}
                    </span>
                    <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                      {t('ops_home_service_review_offline_devices', 'Offline {value}').replace('{value}', String(group.offlineDeviceCount))}
                    </span>
                  </div>
                  <div className="mt-3 text-xs text-gray-600 dark:text-gray-300">
                    {group.nextAction}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      data-testid={`operations-home-service-review-open-${group.id}`}
                      onClick={() => openServiceReview(group)}
                      className="rounded-lg border border-cyan-200 dark:border-cyan-900/40 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-cyan-800 dark:text-cyan-200 hover:bg-cyan-50 dark:hover:bg-cyan-950/20 transition-colors"
                    >
                      {t('ops_home_service_review_open_group', 'Open service review')}
                    </button>
                    <button
                      type="button"
                      data-testid={`operations-home-service-review-notifications-${group.id}`}
                      onClick={() => openServiceNotifications(group)}
                      className="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-amber-800 dark:text-amber-200 hover:bg-amber-50 dark:hover:bg-amber-950/20 transition-colors"
                    >
                      {t('ops_home_service_review_open_notifications', 'Open service-aware alerts')}
                    </button>
                    <button
                      type="button"
                      data-testid={`operations-home-service-review-reports-${group.id}`}
                      onClick={() => openServiceReports(group)}
                      className="rounded-lg border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                    >
                      {t('ops_home_service_review_open_reports', 'Open Operations Reports')}
                    </button>
                    <button
                      type="button"
                      data-testid={`operations-home-service-review-topology-${group.id}`}
                      onClick={() => openServiceTopology(group)}
                      className="rounded-lg border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                    >
                      {t('ops_home_service_review_open_topology', 'Open Topology')}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {canReviewCloudOps && (
        <section
          data-testid="operations-home-cloud-review-queue"
          className="rounded-2xl border border-violet-200 dark:border-violet-900/40 bg-violet-50/70 dark:bg-violet-950/10 p-5 shadow-sm"
        >
          <div className="flex items-center gap-2">
            <Globe size={16} className="text-violet-600 dark:text-violet-300" />
            <div className="text-base font-black text-gray-900 dark:text-white">
              {t('ops_home_cloud_review_title', 'Cloud review queue')}
            </div>
          </div>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            {t(
              'ops_home_cloud_review_desc',
              'Bring approval-backed, retry-prone, and syncing cloud accounts into one queue so operators can move straight into review, approval, or cloud intents.',
            )}
          </div>
          {cloudPressureLoading ? (
            <div className="mt-4 rounded-xl border border-violet-200/80 dark:border-violet-900/40 bg-white/80 dark:bg-black/20 px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
              {t('ops_home_cloud_review_loading', 'Loading the current cloud review queue...')}
            </div>
          ) : cloudPressureError ? (
            <div className="mt-4 rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50/80 dark:bg-amber-950/20 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
              {cloudPressureError}
            </div>
          ) : cloudReviewQueue.length === 0 ? (
            <div className="mt-4 rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-white/80 dark:bg-black/20 px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
              {t('ops_home_cloud_review_empty', 'No cloud accounts need immediate review right now.')}
            </div>
          ) : (
            <>
              <div data-testid="operations-home-cloud-lane-board" className="mt-4 rounded-xl border border-violet-200/80 dark:border-violet-900/40 bg-white/90 dark:bg-black/20 px-4 py-4">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-violet-700 dark:text-violet-300">
                  {t('ops_home_cloud_lane_board_title', 'Operating lanes')}
                </div>
                <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                  {t(
                    'ops_home_cloud_lane_board_desc',
                    'Keep recovery, approval, sync watch, and stable cloud lanes visible before opening an individual account review.',
                  )}
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4 text-xs">
                  <div data-testid="operations-home-cloud-lane-card-recovery" className="rounded-lg border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/10 px-3 py-3">
                    <div className="text-[10px] font-bold text-rose-700 dark:text-rose-300">
                      {t('cloud_accounts_ledger_lane_retry_title', 'Recovery lane')}
                    </div>
                    <div className="mt-1 text-lg font-black text-rose-700 dark:text-rose-300">{cloudLaneBoard.recovery}</div>
                  </div>
                  <div data-testid="operations-home-cloud-lane-card-approval" className="rounded-lg border border-violet-200 dark:border-violet-900/40 bg-violet-50 dark:bg-violet-950/10 px-3 py-3">
                    <div className="text-[10px] font-bold text-violet-700 dark:text-violet-300">
                      {t('cloud_accounts_ledger_lane_approval_title', 'Approval follow-up lane')}
                    </div>
                    <div className="mt-1 text-lg font-black text-violet-700 dark:text-violet-300">{cloudLaneBoard.approval}</div>
                  </div>
                  <div data-testid="operations-home-cloud-lane-card-sync" className="rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/10 px-3 py-3">
                    <div className="text-[10px] font-bold text-sky-700 dark:text-sky-300">
                      {t('cloud_accounts_ledger_lane_sync_title', 'Sync observation lane')}
                    </div>
                    <div className="mt-1 text-lg font-black text-sky-700 dark:text-sky-300">{cloudLaneBoard.sync}</div>
                  </div>
                  <div data-testid="operations-home-cloud-lane-card-stable" className="rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/10 px-3 py-3">
                    <div className="text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                      {t('cloud_accounts_ledger_lane_stable_title', 'Stable operating lane')}
                    </div>
                    <div className="mt-1 text-lg font-black text-emerald-700 dark:text-emerald-300">{cloudLaneBoard.stable}</div>
                  </div>
                </div>
              </div>
              <div className="mt-4 grid gap-3 xl:grid-cols-2">
                <div data-testid="operations-home-cloud-retry-queue" className="rounded-xl border border-rose-200/80 dark:border-rose-900/40 bg-white/90 dark:bg-black/20 px-4 py-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-rose-700 dark:text-rose-300">
                    {t('ops_home_cloud_retry_queue_title', 'Retry queue')}
                  </div>
                  <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                    {t(
                      'ops_home_cloud_retry_queue_desc',
                      'Keep the safest retry candidates visible on the home surface so operators can move into account review before a failed lane repeats.',
                    )}
                  </div>
                  {cloudRetryQueue.length === 0 ? (
                    <div className="mt-3 rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50/40 dark:bg-emerald-950/10 px-3 py-3 text-[11px] text-gray-600 dark:text-gray-300">
                      {t('ops_home_cloud_retry_queue_empty', 'No cloud retry actions are waiting right now.')}
                    </div>
                  ) : (
                    <div className="mt-3 grid gap-2">
                      {cloudRetryQueue.map((entry) => (
                        <div
                          key={`operations-home-cloud-retry-${entry.accountId}`}
                          data-testid={`operations-home-cloud-retry-item-${entry.accountId}`}
                          className="rounded-lg border border-rose-200/80 dark:border-rose-900/40 bg-rose-50/50 dark:bg-rose-950/10 px-3 py-3"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="text-sm font-bold text-gray-900 dark:text-white truncate">{entry.name}</div>
                              <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">{entry.provider}</div>
                            </div>
                            <span className="rounded-full border border-rose-200 dark:border-rose-900/40 bg-white/90 dark:bg-black/20 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-rose-700 dark:text-rose-300">
                              {entry.retryLabel}
                            </span>
                          </div>
                          <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
                            {entry.lastFailureReasonLabel || entry.lastFailureReasonCode || t('ops_home_cloud_retry_queue_reason_default', 'Review the account lane before retrying.')}
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            <button
                              type="button"
                              data-testid={`operations-home-cloud-retry-open-review-${entry.accountId}`}
                              onClick={() => openCloudReview(entry)}
                              className="rounded-lg border border-rose-200 dark:border-rose-900/40 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-rose-800 dark:text-rose-200 hover:bg-rose-50 dark:hover:bg-rose-950/20 transition-colors"
                            >
                              {t('cloud_accounts_ledger_open_review', 'Open review')}
                            </button>
                            {entry.latestApprovalId ? (
                              <button
                                type="button"
                                data-testid={`operations-home-cloud-retry-open-approval-${entry.accountId}`}
                                onClick={() => openCloudApproval(entry)}
                                className="rounded-lg border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                              >
                                {t('cloud_accounts_ledger_open_approval', 'Open Approval')}
                              </button>
                            ) : null}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div data-testid="operations-home-cloud-execution-highlights" className="rounded-xl border border-sky-200/80 dark:border-sky-900/40 bg-white/90 dark:bg-black/20 px-4 py-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-sky-700 dark:text-sky-300">
                    {t('ops_home_cloud_execution_highlights_title', 'Recent execution highlights')}
                  </div>
                  <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                    {t(
                      'ops_home_cloud_execution_highlights_desc',
                      'See which validate, scan, pipeline, or bootstrap lane moved most recently before you open a deeper account review.',
                    )}
                  </div>
                  {cloudExecutionHighlights.length === 0 ? (
                    <div className="mt-3 rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50/40 dark:bg-sky-950/10 px-3 py-3 text-[11px] text-gray-600 dark:text-gray-300">
                      {t('ops_home_cloud_execution_highlights_empty', 'No recent cloud execution highlights are available yet.')}
                    </div>
                  ) : (
                    <div className="mt-3 grid gap-2">
                      {cloudExecutionHighlights.map((entry) => (
                        <div
                          key={entry.key}
                          data-testid={`operations-home-cloud-highlight-${entry.accountId}`}
                          className="rounded-lg border border-sky-200/80 dark:border-sky-900/40 bg-sky-50/50 dark:bg-sky-950/10 px-3 py-3"
                        >
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <span className="font-bold text-gray-900 dark:text-white">{entry.name}</span>
                            <span className="font-bold text-sky-700 dark:text-sky-300">{entry.label}</span>
                            <span className="text-gray-500">
                              {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : t('cloud_discovery_never', 'Never')}
                            </span>
                          </div>
                          {!!entry.summary && (
                            <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">{entry.summary}</div>
                          )}
                          <div className="mt-3 flex flex-wrap gap-2">
                            <button
                              type="button"
                              data-testid={`operations-home-cloud-highlight-open-review-${entry.accountId}`}
                              onClick={() => openCloudReview(entry)}
                              className="rounded-lg border border-sky-200 dark:border-sky-900/40 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-sky-800 dark:text-sky-200 hover:bg-sky-50 dark:hover:bg-sky-950/20 transition-colors"
                            >
                              {t('cloud_accounts_ledger_open_review', 'Open review')}
                            </button>
                            {entry.latestApprovalId ? (
                              <button
                                type="button"
                                data-testid={`operations-home-cloud-highlight-open-approval-${entry.accountId}`}
                                onClick={() => openCloudApproval(entry)}
                                className="rounded-lg border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                              >
                                {t('cloud_accounts_ledger_open_approval', 'Open Approval')}
                              </button>
                            ) : null}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div data-testid="operations-home-cloud-checkpoints" className="mt-4 rounded-xl border border-amber-200/80 dark:border-amber-900/40 bg-white/90 dark:bg-black/20 px-4 py-4">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-amber-700 dark:text-amber-300">
                  {t('ops_home_cloud_checkpoints_title', 'Next checkpoints')}
                </div>
                <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                  {t(
                    'ops_home_cloud_checkpoints_desc',
                    'Keep the next approval, recovery, and sync checkpoints visible so operators know when to reopen a cloud review.',
                  )}
                </div>
                {cloudScheduleQueue.length === 0 ? (
                  <div className="mt-3 rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50/40 dark:bg-emerald-950/10 px-3 py-3 text-[11px] text-gray-600 dark:text-gray-300">
                    {t('ops_home_cloud_checkpoints_empty', 'No cloud checkpoints need follow-up right now.')}
                  </div>
                ) : (
                  <div className="mt-3 grid gap-2 xl:grid-cols-3">
                    {cloudScheduleQueue.map((entry) => (
                      <div
                        key={`operations-home-cloud-checkpoint-${entry.accountId}`}
                        data-testid={`operations-home-cloud-checkpoint-${entry.accountId}`}
                        className="rounded-lg border border-amber-200/80 dark:border-amber-900/40 bg-amber-50/50 dark:bg-amber-950/10 px-3 py-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-bold text-gray-900 dark:text-white truncate">{entry.name}</div>
                            <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">{entry.provider}</div>
                          </div>
                          <span className="rounded-full border border-amber-200 dark:border-amber-900/40 bg-white/90 dark:bg-black/20 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">
                            {entry.windowLabel}
                          </span>
                        </div>
                        <div className="mt-2 text-xs font-bold text-amber-800 dark:text-amber-200">{entry.title}</div>
                        <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">{entry.description}</div>
                        {!!entry.lastAttemptAt && (
                          <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
                            {t('cloud_accounts_ledger_schedule_last_attempt', 'Last attempt')}: {new Date(entry.lastAttemptAt).toLocaleString()}
                          </div>
                        )}
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            data-testid={`operations-home-cloud-checkpoint-open-review-${entry.accountId}`}
                            onClick={() => openCloudReview(entry)}
                            className="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-amber-800 dark:text-amber-200 hover:bg-amber-50 dark:hover:bg-amber-950/20 transition-colors"
                          >
                            {t('cloud_accounts_ledger_open_review', 'Open review')}
                          </button>
                          {entry.latestApprovalId ? (
                            <button
                              type="button"
                              data-testid={`operations-home-cloud-checkpoint-open-approval-${entry.accountId}`}
                              onClick={() => openCloudApproval(entry)}
                              className="rounded-lg border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                            >
                              {t('cloud_accounts_ledger_open_approval', 'Open Approval')}
                            </button>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
                {cloudReviewQueue.map((entry) => {
                  const workspaceLabel = getWorkspaceTitle(entry.workspace, t);
                  return (
                  <div
                    key={`operations-home-cloud-review-${entry.accountId}`}
                    data-testid={`operations-home-cloud-review-item-${entry.accountId}`}
                    className="rounded-2xl border border-violet-200/80 dark:border-violet-900/40 bg-white/90 dark:bg-black/20 p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-black text-gray-900 dark:text-white truncate">{entry.name}</div>
                        <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                          {entry.provider}
                          {' | '}
                          {t('ops_home_pressure_recommended_workspace', 'Recommended {value}').replace('{value}', workspaceLabel)}
                        </div>
                      </div>
                      <span className={`rounded-full border px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${pressureBadgeClass(entry.priority)}`}>
                        {t('ops_home_cloud_review_priority', 'Needs review')}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-600 dark:text-gray-300">
                      <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                        {t('ops_home_cloud_review_posture', 'Posture {value}').replace('{value}', entry.operationsPosture || 'attention')}
                      </span>
                      <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                        {t('ops_home_cloud_review_pending', 'Pending approvals {value}').replace('{value}', String(entry.pendingApprovals || 0))}
                      </span>
                    </div>
                    <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      {t('ops_home_cloud_review_last_operation', 'Last operation {value}').replace(
                        '{value}',
                        entry.lastOperationAt ? new Date(entry.lastOperationAt).toLocaleString() : t('cloud_discovery_never', 'Never'),
                      )}
                    </div>
                    <div className="mt-3 text-xs text-gray-600 dark:text-gray-300">
                      {entry.nextAction}
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        data-testid={`operations-home-cloud-review-open-${entry.accountId}`}
                        onClick={() => openCloudReview(entry)}
                        className="rounded-lg border border-violet-200 dark:border-violet-900/40 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-violet-800 dark:text-violet-200 hover:bg-violet-50 dark:hover:bg-violet-950/20 transition-colors"
                      >
                        {t('cloud_accounts_ledger_open_review', 'Open review')}
                      </button>
                      <button
                        type="button"
                        data-testid={`operations-home-cloud-review-workspace-${entry.accountId}`}
                        onClick={() => navigate(`/automation?workspace=${entry.workspace}`)}
                        className="rounded-lg border border-violet-200 dark:border-violet-900/40 bg-violet-50 dark:bg-violet-950/20 px-3 py-2 text-xs font-bold text-violet-800 dark:text-violet-200 hover:bg-violet-100 dark:hover:bg-violet-900/30 transition-colors"
                      >
                        {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', workspaceLabel)}
                      </button>
                      <button
                        type="button"
                        data-testid={`operations-home-cloud-review-intents-${entry.accountId}`}
                        onClick={openCloudIntents}
                        className="rounded-lg border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                      >
                        {t('cloud_accounts_ledger_open_intents', 'Open Cloud Intents')}
                      </button>
                      {entry.latestApprovalId ? (
                        <button
                          type="button"
                          data-testid={`operations-home-cloud-review-approval-${entry.accountId}`}
                          onClick={() => openCloudApproval(entry)}
                          className="rounded-lg border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                        >
                          {t('cloud_accounts_ledger_open_approval', 'Open Approval')}
                        </button>
                      ) : null}
                    </div>
                  </div>
                  );
                })}
              </div>
            </>
          )}
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {workspaceSections.map((workspace) => (
          <section
            key={workspace.key}
            ref={(node) => {
              workspaceRefs.current[workspace.key] = node;
            }}
            data-testid={`operations-workspace-${workspace.key}`}
            className={`rounded-2xl border p-5 shadow-sm ${
              focusedWorkspace === workspace.key
                ? 'ring-2 ring-blue-500/60 ring-offset-2 ring-offset-transparent'
                : ''
            } ${workspaceAccent[workspace.key] || 'border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20'}`}
          >
            <div className="flex items-center gap-2">
              <Globe size={16} className="text-primary" />
              <div className="text-lg font-black text-gray-900 dark:text-white">{workspace.title}</div>
            </div>
            <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">{workspace.desc}</div>
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {workspace.primaryItems.map((item) => {
                const Icon = item.icon;
                const locked = item.policyState?.navigable !== true;
                const blockState = locked ? item.policyState?.blockState : null;
                const blockSummary = locked ? getSurfaceBlockSummary(blockState, t) : null;
                return (
                  <button
                    key={item.key}
                    type="button"
                    data-testid={`operations-surface-${item.key}`}
                    onClick={() => {
                      navigate(locked ? (blockState?.actionPath || '/automation') : item.path);
                    }}
                    className={`text-left rounded-2xl border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 p-4 transition-colors ${
                      locked
                        ? 'border-amber-300 dark:border-amber-900/50 bg-amber-50/70 dark:bg-amber-950/20 hover:bg-amber-100/70 dark:hover:bg-amber-950/30'
                        : 'hover:bg-gray-50 dark:hover:bg-white/5'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Icon size={16} className={locked ? 'text-amber-700 dark:text-amber-300' : 'text-blue-600 dark:text-blue-400'} />
                      <div className="text-sm font-black text-gray-900 dark:text-white">{item.title}</div>
                    </div>
                    <div className="mt-2 text-xs text-gray-600 dark:text-gray-300">{item.desc}</div>
                    {locked ? (
                      <ProductPolicyBlockCard
                        blockState={blockState}
                        compact
                        className="mt-3"
                      />
                    ) : (
                      <div className="mt-3 text-[11px] font-extrabold text-blue-600 dark:text-blue-300">
                        {t('common_open', 'Open')} -&gt;
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
            {workspace.secondaryItems.length > 0 && (
              <div className="mt-4 border-t border-gray-200/80 dark:border-white/10 pt-4">
                <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                  {t('ops_home_secondary_surfaces', 'More surfaces in this workspace')}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {workspace.secondaryItems.map((item) => {
                    const locked = item.policyState?.navigable !== true;
                    const blockState = locked ? item.policyState?.blockState : null;
                    const blockSummary = locked ? getSurfaceBlockSummary(blockState, t) : null;
                    return (
                      <button
                        key={item.key}
                        type="button"
                        data-testid={`operations-secondary-surface-${item.key}`}
                        onClick={() => {
                          navigate(locked ? (blockState?.actionPath || '/automation') : item.path);
                        }}
                        className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
                          locked
                            ? 'border-amber-300 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-950/20 text-amber-800 dark:text-amber-200 hover:bg-amber-100/70 dark:hover:bg-amber-950/30'
                            : 'border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5'
                        }`}
                        title={locked
                          ? blockSummary?.tooltip || t('locked_action', 'Locked')
                          : item.desc}
                      >
                        {item.title}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
};

export default AutomationHubLinksPage;
