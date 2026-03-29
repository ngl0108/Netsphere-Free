import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Bell, CheckCircle, AlertTriangle, XCircle, Clock, Trash2, RefreshCw,
  Filter, Eye, EyeOff, Server, Shield, Settings, Cpu, Wrench, X, Activity, BarChart3, Map as MapIcon, GitBranch, Cloud, Camera, TimerReset, LayoutGrid, FileText,
} from 'lucide-react';
import { IssueService, ServiceGroupService, SettingsService, StateHistoryService } from '../../api/services';
import { useIssuePolling } from '../../context/IssuePollingContext';
import { useToast } from '../../context/ToastContext';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import { InlineEmpty, InlineLoading, SectionCard } from '../common/PageState';
import {
  buildGrafanaAlertingCenterUrl,
  buildGrafanaFleetHealthUrl,
  buildObservabilityPath,
  buildTopologyPath,
} from '../../utils/observabilityLinks';
import { buildCloudIntentPath } from '../../utils/cloudIntentLinks';
import {
  getOperationalStatusBadgeClass,
  getOperationalStatusHint,
  getOperationalStatusLabel,
} from '../../utils/deviceStatusTone';
import {
  compareServiceImpactAlerts,
  getOperationsPressureGuidance,
  getOperationsPressureLabel,
  getOperationsPressureLevel,
  getServicePressureIndex,
  getServiceReviewAverageHealth,
  recommendServiceWorkspace,
  summarizeServiceImpactAlertFocus,
  summarizeServiceReviewPosture,
} from '../../utils/serviceOperations';

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

const NotificationsPage = () => {
  useLocaleRerender();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { toast } = useToast();
  const {
    alerts,
    loading,
    loadAlerts: refreshIssues,
    markAsRead,
    markAllAsRead,
    resolveIssue,
    resolveAll,
  } = useIssuePolling();

  const [categoryFilter, setCategoryFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [showUnreadOnly, setShowUnreadOnly] = useState(false);
  const [showServiceImpactOnly, setShowServiceImpactOnly] = useState(false);
  const [expandedAutomationId, setExpandedAutomationId] = useState(null);
  const [automationPreviews, setAutomationPreviews] = useState({});
  const [automationRuns, setAutomationRuns] = useState({});
  const [automationLoadingId, setAutomationLoadingId] = useState(null);
  const [automationRunningId, setAutomationRunningId] = useState(null);
  const [expandedActionId, setExpandedActionId] = useState(null);
  const [issueActions, setIssueActions] = useState({});
  const [actionsLoadingId, setActionsLoadingId] = useState(null);
  const [actionSavingKey, setActionSavingKey] = useState('');
  const [issueApprovalContext, setIssueApprovalContext] = useState({});
  const [approvalContextLoadingId, setApprovalContextLoadingId] = useState(null);
  const [expandedKnowledgeId, setExpandedKnowledgeId] = useState(null);
  const [issueKnowledge, setIssueKnowledge] = useState({});
  const [knowledgeLoadingId, setKnowledgeLoadingId] = useState(null);
  const [knowledgeSavingKey, setKnowledgeSavingKey] = useState('');
  const [expandedSopId, setExpandedSopId] = useState(null);
  const [issueSops, setIssueSops] = useState({});
  const [sopLoadingId, setSopLoadingId] = useState(null);
  const [expandedServiceImpactId, setExpandedServiceImpactId] = useState(null);
  const [issueServiceImpact, setIssueServiceImpact] = useState({});
  const [serviceImpactLoadingId, setServiceImpactLoadingId] = useState(null);
  const [deliveryItems, setDeliveryItems] = useState([]);
  const [deliveryLoading, setDeliveryLoading] = useState(false);
  const [deliveryRefreshing, setDeliveryRefreshing] = useState(false);
  const [deliveryRetryingId, setDeliveryRetryingId] = useState(null);
  const [deliveryError, setDeliveryError] = useState('');
  const [stateHistoryActionKey, setStateHistoryActionKey] = useState('');
  const [focusedServiceGroup, setFocusedServiceGroup] = useState(null);

  const openGrafana = (url) => {
    if (!url) return;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const openDevice = (deviceId) => {
    if (!deviceId) return;
    navigate(`/devices/${deviceId}`);
  };

  const openObservability = (deviceId, siteId) => {
    if (!deviceId) return;
    navigate(buildObservabilityPath({ deviceId, siteId }));
  };

  const openTopology = (siteId) => {
    if (!siteId) return;
    navigate(`/topology?siteId=${encodeURIComponent(String(siteId))}`);
  };

  const openCloudTopologyImpact = (alert) => {
    const scope = alert?.cloud_scope;
    if (!scope || !scope.provider) return;
    navigate(buildTopologyPath({
      cloudProvider: scope.provider,
      cloudAccountId: scope.account_id,
      cloudRegion: scope.region,
      cloudResourceTypes: scope.resource_types || (scope.resource_type ? [scope.resource_type] : []),
      cloudIntentImpact: true,
      focusCloudResourceId: scope.resource_id,
      focusCloudResourceName: scope.resource_name || alert?.device,
    }));
  };

  const openAlertChannels = () => {
    navigate('/settings?tab=notifications');
  };

  const openCloudAccounts = (alert) => {
    const scope = alert?.cloud_scope;
    const accountId = scope?.account_id;
    navigate(accountId != null ? `/cloud/accounts?focusAccountId=${encodeURIComponent(String(accountId))}` : '/cloud/accounts');
  };

  const openCloudIntent = (alert) => {
    const scope = alert?.cloud_scope;
    if (!scope || !scope.provider) return;
    navigate(
      buildCloudIntentPath({
        provider: scope.provider,
        accountId: scope.account_id,
        region: scope.region,
        resourceType: scope.resource_type,
        resourceTypes: scope.resource_types,
        resourceName: scope.resource_name || alert?.device,
        resourceId: scope.resource_id,
        source: 'alert',
      }),
    );
  };

  const openServiceGroups = (groupId = null, groupName = '') => {
    const targetGroupId = Number(groupId || focusedServiceGroup?.id || 0);
    if (targetGroupId > 0) {
      const params = new URLSearchParams();
      params.set('focusGroupId', String(targetGroupId));
      const resolvedName = String(groupName || focusedServiceGroup?.name || focusedGroupName || '').trim();
      if (resolvedName) params.set('focusGroupName', resolvedName);
      navigate(`/service-groups?${params.toString()}`);
      return;
    }
    navigate('/service-groups');
  };
  const openFocusedServiceReview = (groupId, groupName = '') => {
    const numericGroupId = Number(groupId || 0);
    if (numericGroupId > 0) {
      const params = new URLSearchParams();
      params.set('focusGroupId', String(numericGroupId));
      const resolvedName = String(groupName || focusedServiceGroup?.name || focusedGroupName || '').trim();
      if (resolvedName) params.set('focusGroupName', resolvedName);
      navigate(`/operations-reports?${params.toString()}`);
      return;
    }
    navigate('/operations-reports');
  };
  const openFocusedServiceTopology = (groupId, groupName = '') => {
    const numericGroupId = Number(groupId || 0);
    if (numericGroupId > 0) {
      const params = new URLSearchParams();
      params.set('serviceOverlay', '1');
      params.set('serviceGroupId', String(numericGroupId));
      const resolvedName = String(groupName || focusedServiceGroup?.name || focusedGroupName || '').trim();
      if (resolvedName) params.set('focusGroupName', resolvedName);
      navigate(`/topology?${params.toString()}`);
      return;
    }
    navigate('/topology');
  };

  const focusServiceAwareAlert = useCallback((alert, { openActions = false, openServiceImpact = false } = {}) => {
    const issueId = Number(alert?.id || 0);
    if (issueId <= 0) return;
    const nextParams = new URLSearchParams(searchParams);
    const primaryGroupId = Number(alert?.service_impact_summary?.primary_group_id || 0);
    nextParams.set('serviceImpact', '1');
    nextParams.set('focusIssueId', String(issueId));
    if (primaryGroupId > 0) nextParams.set('focusGroupId', String(primaryGroupId));
    const primaryGroupName = String(alert?.service_impact_summary?.primary_name || '').trim();
    if (primaryGroupName) nextParams.set('focusGroupName', primaryGroupName);
    if (openActions) nextParams.set('openActions', '1');
    else nextParams.delete('openActions');
    if (openServiceImpact) nextParams.set('openServiceImpact', '1');
    else nextParams.delete('openServiceImpact');
    nextParams.delete('openKnowledge');
    nextParams.delete('openSop');
    nextParams.delete('openApproval');
    setSearchParams(nextParams);
  }, [searchParams, setSearchParams]);

  const openStateHistoryForIssue = async (alert, { capture = false } = {}) => {
    const issueId = Number(alert?.id || 0);
    if (issueId <= 0) return;

    const params = new URLSearchParams();
    params.set('focusIssueId', String(issueId));
    params.set('entry', 'notifications');

    if (capture) {
      const actionKey = `${issueId}:capture`;
      setStateHistoryActionKey(actionKey);
      try {
        const reviewLabelBase = String(
          alert?.device || alert?.title || alert?.message || alert?.category || t('notifications_state_history_default_label', 'issue review'),
        ).trim();
        const res = await StateHistoryService.createSnapshot({
          label: t('notifications_state_history_label_fmt', 'Issue #{value} review').replace('{value}', String(issueId)),
          note: `${String(alert?.severity || '').toUpperCase() || 'INFO'} · ${reviewLabelBase}`,
        });
        const createdId = Number(res?.data?.event_log_id || 0);
        if (createdId > 0) params.set('focusSnapshotId', String(createdId));
        toast.success(t('notifications_state_history_capture_success', 'State snapshot captured from this issue.'));
      } catch (err) {
        toast.error(`${t('notifications_state_history_capture_failed', 'Failed to capture state history snapshot')}: ${err?.response?.data?.detail || err?.message}`);
        return;
      } finally {
        setStateHistoryActionKey('');
      }
    }

    navigate(`/state-history?${params.toString()}`);
  };

  const openApprovalCenter = (approvalId) => {
    const numericApprovalId = Number(approvalId || 0);
    navigate(numericApprovalId > 0 ? `/approval?focusRequestId=${encodeURIComponent(String(numericApprovalId))}` : '/approval');
  };

  const loadWebhookDeliveries = useCallback(async ({ silent = false, refreshing = false } = {}) => {
    if (refreshing) setDeliveryRefreshing(true);
    else setDeliveryLoading(true);
    try {
      const res = await SettingsService.listWebhookDeliveries({ days: 7, limit: 6 });
      const body = res?.data || {};
      setDeliveryItems(Array.isArray(body?.items) ? body.items : []);
      setDeliveryError('');
      return body;
    } catch (err) {
      const message = err?.response?.data?.detail || err?.message || t('notifications_northbound_loading_failed', 'Failed to load northbound delivery history.');
      setDeliveryError(String(message));
      if (!silent) {
        toast.error(message);
      }
      return null;
    } finally {
      if (refreshing) setDeliveryRefreshing(false);
      else setDeliveryLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void loadWebhookDeliveries({ silent: true });
  }, [loadWebhookDeliveries]);

  useEffect(() => {
    void refreshIssues({ silent: false });
  }, [refreshIssues]);

  const handleRetryDelivery = async (deliveryId) => {
    const reason = window.prompt(
      t('notifications_northbound_retry_reason_prompt', 'Optional retry reason:'),
      t('notifications_northbound_retry_reason_default', 'Manual retry from Notifications'),
    );
    if (reason === null) return;
    setDeliveryRetryingId(deliveryId);
    try {
      const res = await SettingsService.retryWebhookDelivery(deliveryId, { reason: reason || '' });
      const result = res?.data?.result || {};
      toast.success(
        t('notifications_northbound_retry_success_fmt', 'Delivery retried (attempts {attempts}, HTTP {statusCode}).')
          .replace('{attempts}', String(Number(result?.attempts || 1)))
          .replace('{statusCode}', result?.status_code != null ? String(result.status_code) : '-'),
      );
      await loadWebhookDeliveries({ silent: true, refreshing: true });
    } catch (err) {
      toast.error(`${t('notifications_northbound_retry_failed', 'Failed to retry northbound delivery')}: ${err?.response?.data?.detail || err?.message}`);
    } finally {
      setDeliveryRetryingId(null);
    }
  };

  const categories = [
    { value: '', label: t('notifications_category_all', 'All Categories'), icon: Filter },
    { value: 'device', label: t('notifications_category_device', 'Device'), icon: Server },
    { value: 'security', label: t('notifications_category_security', 'Security'), icon: Shield },
    { value: 'system', label: t('notifications_category_system', 'System'), icon: Settings },
    { value: 'config', label: t('notifications_category_config', 'Configuration'), icon: Wrench },
    { value: 'performance', label: t('notifications_category_performance', 'Performance'), icon: Cpu },
  ];

  const severities = [
    { value: '', label: t('notifications_severity_all', 'All Severities') },
    { value: 'critical', label: t('notifications_severity_critical', 'Critical') },
    { value: 'warning', label: t('notifications_severity_warning', 'Warning') },
    { value: 'info', label: t('notifications_severity_info', 'Info') },
  ];

  const formatTimeAgo = (dateString) => {
    if (!dateString) return '';
    const now = new Date();
    const past = new Date(new Date(dateString).getTime() + 9 * 60 * 60 * 1000);
    const diffMins = Math.floor((now - past) / 60000);
    if (diffMins < 1) return t('layout_time_just_now', 'Just now');
    if (diffMins < 60) return t('layout_time_minutes_ago', '{value}m ago').replace('{value}', String(diffMins));
    if (diffMins < 1440) return t('layout_time_hours_ago', '{value}h ago').replace('{value}', String(Math.floor(diffMins / 60)));
    return t('layout_time_days_ago', '{value}d ago').replace('{value}', String(Math.floor(diffMins / 1440)));
  };

  const handleResolve = async (id) => {
    try {
      await resolveIssue(id);
    } catch (err) {
      console.error('Failed to resolve issue:', err);
      void refreshIssues({ silent: false });
    }
  };

  const handleMarkRead = async (id) => {
    try {
      await markAsRead(id);
    } catch (err) {
      console.error('Failed to mark as read:', err);
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm(t('notifications_confirm_ack_all', 'All active alarms will be marked as resolved. Continue?'))) return;
    try {
      await resolveAll();
    } catch (err) {
      console.error('Failed to resolve all:', err);
      void refreshIssues({ silent: false });
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllAsRead();
    } catch (err) {
      console.error('Failed to mark all as read:', err);
    }
  };

  const automationLabel = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'auto_ready') return t('notifications_automation_ready', 'Automation Ready');
    if (normalized === 'approval_required') return t('notifications_automation_approval', 'Approval Needed');
    if (normalized === 'blocked') return t('notifications_automation_blocked', 'Blocked');
    if (normalized === 'auto_execute_disabled') return t('notifications_automation_disabled', 'Auto Execute Off');
    if (normalized === 'engine_disabled') return t('notifications_automation_engine_off', 'Engine Off');
    return t('notifications_automation_no_rule', 'No Rule');
  };

  const automationBadgeClass = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'auto_ready') return 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30';
    if (normalized === 'approval_required') return 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30';
    if (normalized === 'blocked') return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30';
    if (normalized === 'auto_execute_disabled') return 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-500/15 dark:text-slate-300 dark:border-slate-500/30';
    if (normalized === 'engine_disabled') return 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-gray-500/15 dark:text-gray-300 dark:border-gray-500/30';
    return 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-500/30';
  };

  const decisionLabel = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'ready') return t('notifications_automation_decision_ready', 'Ready');
    if (normalized === 'approval_required') return t('notifications_automation_decision_approval', 'Approval');
    if (normalized === 'blocked_cooldown') return t('notifications_automation_decision_cooldown', 'Cooldown');
    if (normalized === 'blocked_rate_limit') return t('notifications_automation_decision_rate_limit', 'Rate Limit');
    if (normalized === 'notify_not_configured') return t('notifications_automation_decision_notify_config', 'Webhook Needed');
    if (normalized === 'auto_execute_disabled') return t('notifications_automation_decision_disabled', 'Disabled');
    return String(status || 'Unknown');
  };

  const getAutomationDetail = (id) => automationPreviews[id]?.automation || null;
  const getAutomationRun = (id) => automationRuns[id] || null;
  const getActionRows = (id) => (Array.isArray(issueActions[id]) ? issueActions[id] : []);
  const getApprovalPayload = (id) => (issueApprovalContext[id] && typeof issueApprovalContext[id] === 'object' ? issueApprovalContext[id] : null);
  const getKnowledgeRows = (id) => (Array.isArray(issueKnowledge[id]) ? issueKnowledge[id] : []);
  const getSopPayload = (id) => (issueSops[id] && typeof issueSops[id] === 'object' ? issueSops[id] : null);
  const getServiceImpactPayload = (id) => (issueServiceImpact[id] && typeof issueServiceImpact[id] === 'object' ? issueServiceImpact[id] : null);

  const actionStatusLabel = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'investigating') return t('notifications_action_status_investigating', 'Investigating');
    if (normalized === 'mitigated') return t('notifications_action_status_mitigated', 'Mitigated');
    if (normalized === 'resolved') return t('notifications_action_status_resolved', 'Resolved');
    return t('notifications_action_status_open', 'Open');
  };

  const actionStatusBadgeClass = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'resolved') return 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30';
    if (normalized === 'mitigated') return 'bg-teal-100 text-teal-700 border-teal-200 dark:bg-teal-500/15 dark:text-teal-300 dark:border-teal-500/30';
    if (normalized === 'investigating') return 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-500/30';
    return 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30';
  };

  const approvalStatusLabel = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'approved') return t('notifications_approval_status_approved', 'Approved');
    if (normalized === 'rejected') return t('notifications_approval_status_rejected', 'Rejected');
    return t('notifications_approval_status_pending', 'Pending');
  };

  const approvalStatusBadgeClass = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'approved') return 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30';
    if (normalized === 'rejected') return 'bg-rose-100 text-rose-700 border-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/30';
    return 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30';
  };

  const approvalExecutionStatusLabel = (status) => {
    const normalized = String(status || '').toLowerCase().replace(/_/g, ' ');
    if (!normalized) return t('common_unknown', 'Unknown');
    return normalized;
  };

  const sopReadinessLabel = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'ready') return t('notifications_sop_ready', 'SOP Ready');
    return t('notifications_sop_limited', 'Needs Operator Context');
  };

  const sopReadinessBadgeClass = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'ready') return 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30';
    return 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30';
  };

  const serviceHealthBadgeClass = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'critical') return 'bg-rose-100 text-rose-700 border-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/30';
    if (normalized === 'degraded' || normalized === 'review') return 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30';
    return 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30';
  };

  const loadIssueActions = useCallback(async (issueId, { silent = false } = {}) => {
    const numericIssueId = Number(issueId || 0);
    if (numericIssueId <= 0) return [];
    if (!silent) setActionsLoadingId(numericIssueId);
    try {
      const res = await IssueService.listActions(numericIssueId);
      const rows = Array.isArray(res?.data) ? res.data : [];
      setIssueActions((prev) => ({ ...prev, [numericIssueId]: rows }));
      return rows;
    } catch (err) {
      if (!silent) {
        toast.error(err?.response?.data?.detail || err?.message || t('notifications_action_load_failed', 'Failed to load actions'));
      }
      return [];
    } finally {
      if (!silent) setActionsLoadingId(null);
    }
  }, [toast]);

  const loadIssueApprovalContext = useCallback(async (issueId, { silent = false } = {}) => {
    const numericIssueId = Number(issueId || 0);
    if (numericIssueId <= 0) return null;
    if (!silent) setApprovalContextLoadingId(numericIssueId);
    try {
      const res = await IssueService.getApprovalContext(numericIssueId);
      const payload = res?.data && typeof res.data === 'object' ? res.data : null;
      setIssueApprovalContext((prev) => ({ ...prev, [numericIssueId]: payload }));
      return payload;
    } catch (err) {
      if (!silent) {
        toast.error(err?.response?.data?.detail || err?.message || t('notifications_approval_context_load_failed', 'Failed to load approval context'));
      }
      return null;
    } finally {
      if (!silent) setApprovalContextLoadingId(null);
    }
  }, [toast]);

  const loadIssueKnowledge = useCallback(async (issueId, { silent = false } = {}) => {
    const numericIssueId = Number(issueId || 0);
    if (numericIssueId <= 0) return [];
    if (!silent) setKnowledgeLoadingId(numericIssueId);
    try {
      const res = await IssueService.listKnowledge(numericIssueId);
      const rows = Array.isArray(res?.data) ? res.data : [];
      setIssueKnowledge((prev) => ({ ...prev, [numericIssueId]: rows }));
      return rows;
    } catch (err) {
      if (!silent) {
        toast.error(err?.response?.data?.detail || err?.message || t('notifications_knowledge_load_failed', 'Failed to load known errors'));
      }
      return [];
    } finally {
      if (!silent) setKnowledgeLoadingId(null);
    }
  }, [toast]);

  const loadIssueSop = useCallback(async (issueId, { silent = false } = {}) => {
    const numericIssueId = Number(issueId || 0);
    if (numericIssueId <= 0) return null;
    if (!silent) setSopLoadingId(numericIssueId);
    try {
      const res = await IssueService.getSop(numericIssueId);
      const payload = res?.data && typeof res.data === 'object' ? res.data : null;
      setIssueSops((prev) => ({ ...prev, [numericIssueId]: payload }));
      return payload;
    } catch (err) {
      if (!silent) {
        toast.error(err?.response?.data?.detail || err?.message || t('notifications_sop_load_failed', 'Failed to load SOP guidance'));
      }
      return null;
    } finally {
      if (!silent) setSopLoadingId(null);
    }
  }, [toast]);

  const loadIssueServiceImpact = useCallback(async (issueId, { silent = false } = {}) => {
    const numericIssueId = Number(issueId || 0);
    if (numericIssueId <= 0) return null;
    if (!silent) setServiceImpactLoadingId(numericIssueId);
    try {
      const res = await IssueService.getServiceImpact(numericIssueId);
      const payload = res?.data && typeof res.data === 'object' ? res.data : null;
      setIssueServiceImpact((prev) => ({ ...prev, [numericIssueId]: payload }));
      return payload;
    } catch (err) {
      if (!silent) {
        toast.error(err?.response?.data?.detail || err?.message || t('notifications_service_impact_load_failed', 'Failed to load service impact'));
      }
      return null;
    } finally {
      if (!silent) setServiceImpactLoadingId(null);
    }
  }, [toast]);

  const handlePreviewAutomation = async (alert) => {
    const issueId = Number(alert?.id || 0);
    if (issueId <= 0) return;
    if (expandedAutomationId === issueId) {
      setExpandedAutomationId(null);
      return;
    }
    setExpandedAutomationId(issueId);
    if (automationPreviews[issueId]) return;

    try {
      setAutomationLoadingId(issueId);
      const res = await IssueService.getAutomationPreview(issueId);
      setAutomationPreviews((prev) => ({ ...prev, [issueId]: res?.data || {} }));
    } catch (err) {
      console.error('Failed to load issue automation preview:', err);
      toast.error(err?.response?.data?.detail || err?.message || t('notifications_automation_preview_failed', 'Failed to load automation preview'));
    } finally {
      setAutomationLoadingId(null);
    }
  };

  const handleRunAutomation = async (alert) => {
    const issueId = Number(alert?.id || 0);
    if (issueId <= 0) return;
    if (!alert?.automation?.can_run) {
      toast.warning(alert?.automation?.next_action || t('notifications_automation_not_ready', 'Issue automation is not ready to run'));
      return;
    }

    try {
      setAutomationRunningId(issueId);
      const [runRes, previewRes] = await Promise.all([
        IssueService.runAutomation(issueId),
        IssueService.getAutomationPreview(issueId).catch(() => null),
      ]);
      const runBody = runRes?.data || {};
      const previewBody = previewRes?.data || null;
      setAutomationRuns((prev) => ({ ...prev, [issueId]: runBody?.result || {} }));
      if (previewBody) {
        setAutomationPreviews((prev) => ({ ...prev, [issueId]: previewBody }));
      }
      setExpandedAutomationId(issueId);
      const result = runBody?.result || {};
      const executed = Number(result?.executed || 0);
      const blocked = Number(result?.blocked || 0);
      if (executed > 0) {
        toast.success(
          t('notifications_automation_run_success', 'Automation executed')
            + ` (${t('notifications_automation_executed', 'executed')}: ${executed}, ${t('notifications_automation_blocked_short', 'blocked')}: ${blocked})`,
        );
      } else {
        toast.warning(alert?.automation?.next_action || t('notifications_automation_no_action', 'No automation action was executed'));
      }
      void refreshIssues({ silent: false });
    } catch (err) {
      console.error('Failed to run issue automation:', err);
      toast.error(err?.response?.data?.detail || err?.message || t('notifications_automation_run_failed', 'Failed to run automation'));
    } finally {
      setAutomationRunningId(null);
    }
  };

  const handleToggleActions = async (alert) => {
    const issueId = Number(alert?.id || 0);
    if (issueId <= 0) return;
    if (expandedActionId === issueId) {
      setExpandedActionId(null);
      return;
    }
    setExpandedActionId(issueId);
    const jobs = [];
    if (!issueActions[issueId]) jobs.push(loadIssueActions(issueId));
    if (!issueApprovalContext[issueId]) jobs.push(loadIssueApprovalContext(issueId));
    if (jobs.length > 0) {
      await Promise.all(jobs);
    }
  };

  const handleCreateAction = async (alert) => {
    const issueId = Number(alert?.id || 0);
    if (issueId <= 0) return;
    const assigneeName = window.prompt(
      t('notifications_action_assignee_prompt', 'Optional owner or team name:'),
      '',
    );
    if (assigneeName === null) return;
    const note = window.prompt(
      t('notifications_action_note_prompt', 'Initial action note:'),
      alert?.message || '',
    );
    if (note === null) return;

    const savingKey = `${issueId}:create`;
    setActionSavingKey(savingKey);
    try {
      await IssueService.createAction(issueId, {
        title: alert?.title,
        summary: alert?.message,
        assignee_name: assigneeName || '',
        note: note || '',
      });
      toast.success(t('notifications_action_created', 'Created an action from this alert'));
      setExpandedActionId(issueId);
      await loadIssueActions(issueId, { silent: true });
      await refreshIssues({ silent: false });
    } catch (err) {
      toast.error(err?.response?.data?.detail || err?.message || t('notifications_action_create_failed', 'Failed to create an action'));
    } finally {
      setActionSavingKey('');
    }
  };

  const handleUpdateAction = async (alert, action, nextStatus) => {
    const issueId = Number(alert?.id || 0);
    const actionId = Number(action?.id || 0);
    if (issueId <= 0 || actionId <= 0) return;
    const note = window.prompt(
      t('notifications_action_update_note_prompt', 'Optional update note:'),
      '',
    );
    if (note === null) return;
    const savingKey = `${actionId}:${nextStatus}`;
    setActionSavingKey(savingKey);
    try {
      await IssueService.updateAction(actionId, {
        status: nextStatus,
        note: note || '',
      });
      toast.success(
        t('notifications_action_updated_fmt', 'Updated action to {status}')
          .replace('{status}', actionStatusLabel(nextStatus)),
      );
      await loadIssueActions(issueId, { silent: true });
      await refreshIssues({ silent: false });
    } catch (err) {
      toast.error(err?.response?.data?.detail || err?.message || t('notifications_action_update_failed', 'Failed to update the action'));
    } finally {
      setActionSavingKey('');
    }
  };

  const handleToggleKnowledge = async (alert) => {
    const issueId = Number(alert?.id || 0);
    if (issueId <= 0) return;
    if (expandedKnowledgeId === issueId) {
      setExpandedKnowledgeId(null);
      return;
    }
    setExpandedKnowledgeId(issueId);
    if (issueKnowledge[issueId]) return;
    await loadIssueKnowledge(issueId);
  };

  const handleToggleSop = async (alert) => {
    const issueId = Number(alert?.id || 0);
    if (issueId <= 0) return;
    if (expandedSopId === issueId) {
      setExpandedSopId(null);
      return;
    }
    setExpandedSopId(issueId);
    if (issueSops[issueId]) return;
    await loadIssueSop(issueId);
  };

  const handleToggleServiceImpact = async (alert) => {
    const issueId = Number(alert?.id || 0);
    if (issueId <= 0) return;
    if (expandedServiceImpactId === issueId) {
      setExpandedServiceImpactId(null);
      return;
    }
    setExpandedServiceImpactId(issueId);
    if (issueServiceImpact[issueId]) return;
    await loadIssueServiceImpact(issueId);
  };

  const handleCreateKnowledge = async (alert) => {
    const issueId = Number(alert?.id || 0);
    if (issueId <= 0) return;
    const rootCause = window.prompt(
      t('notifications_knowledge_root_cause_prompt', 'Root cause summary:'),
      '',
    );
    if (rootCause === null) return;
    const workaround = window.prompt(
      t('notifications_knowledge_workaround_prompt', 'Workaround or recovery note:'),
      '',
    );
    if (workaround === null) return;
    const sopSummary = window.prompt(
      t('notifications_knowledge_sop_prompt', 'Optional SOP or runbook note:'),
      '',
    );
    if (sopSummary === null) return;

    const savingKey = `${issueId}:knowledge`;
    setKnowledgeSavingKey(savingKey);
    try {
      await IssueService.createKnowledge(issueId, {
        title: alert?.title,
        symptom_pattern: alert?.message,
        root_cause: rootCause || '',
        workaround: workaround || '',
        sop_summary: sopSummary || '',
      });
      toast.success(t('notifications_knowledge_created', 'Saved a known error entry from this alert'));
      setExpandedKnowledgeId(issueId);
      await loadIssueKnowledge(issueId, { silent: true });
      await refreshIssues({ silent: false });
    } catch (err) {
      toast.error(err?.response?.data?.detail || err?.message || t('notifications_knowledge_create_failed', 'Failed to save the known error'));
    } finally {
      setKnowledgeSavingKey('');
    }
  };

  const getCategoryIcon = (category) => {
    const cat = categories.find((c) => c.value === category);
    const Icon = cat?.icon || Settings;
    return <Icon size={14} />;
  };

  const getCategoryLabel = (category) => {
    const normalized = String(category || 'system').toLowerCase();
    const cat = categories.find((c) => c.value === normalized);
    return cat?.label || t('notifications_category_system', 'System');
  };

  const mapSeverityToOperationalStatus = (severity) => {
    const normalized = String(severity || '').toLowerCase();
    if (normalized === 'critical') return 'critical';
    if (normalized === 'warning') return 'warning';
    return 'healthy';
  };

  const focusedGroupId = useMemo(() => {
    const raw = Number(searchParams.get('focusGroupId') || 0);
    return raw > 0 ? raw : null;
  }, [searchParams]);
  const focusedGroupName = useMemo(() => {
    const raw = String(searchParams.get('focusGroupName') || '').trim();
    return raw || '';
  }, [searchParams]);

  useEffect(() => {
    let active = true;
    const numericGroupId = Number(focusedGroupId || 0);
    if (numericGroupId <= 0) {
      setFocusedServiceGroup(null);
      return () => {
        active = false;
      };
    }
    const loadFocusedGroup = async () => {
      try {
        const res = await ServiceGroupService.get(numericGroupId);
        if (!active) return;
        setFocusedServiceGroup(res?.data || null);
      } catch (err) {
        if (!active) return;
        setFocusedServiceGroup(null);
      }
    };
    void loadFocusedGroup();
    return () => {
      active = false;
    };
  }, [focusedGroupId]);

  const matchesFocusedServiceGroup = useCallback((alert) => {
    const numericGroupId = Number(focusedGroupId || 0);
    if (numericGroupId <= 0) return true;
    const summary = alert?.service_impact_summary || {};
    if (Number(summary?.primary_group_id || 0) === numericGroupId) return true;
    const focusedName = String(focusedServiceGroup?.name || focusedGroupName || '').trim().toLowerCase();
    const primaryName = String(summary?.primary_name || '').trim().toLowerCase();
    return !!focusedName && primaryName === focusedName;
  }, [focusedGroupId, focusedGroupName, focusedServiceGroup?.name]);

  const filteredAlerts = useMemo(() => {
    return alerts
      .filter((alert) => {
        const categoryMatch = !categoryFilter || String(alert?.category || '').toLowerCase() === String(categoryFilter).toLowerCase();
        const severityMatch = !severityFilter || String(alert?.severity || '').toLowerCase() === String(severityFilter).toLowerCase();
        const unreadMatch = !showUnreadOnly || !alert?.is_read;
        const serviceImpactMatch = !showServiceImpactOnly || Number(alert?.service_impact_summary?.count || 0) > 0;
        const focusedGroupMatch = matchesFocusedServiceGroup(alert);
        return categoryMatch && severityMatch && unreadMatch && serviceImpactMatch && focusedGroupMatch;
      })
      .sort(compareServiceImpactAlerts);
  }, [alerts, categoryFilter, severityFilter, showUnreadOnly, showServiceImpactOnly, matchesFocusedServiceGroup]);

  const serviceImpactAlerts = useMemo(
    () => alerts.filter((alert) => Number(alert?.service_impact_summary?.count || 0) > 0),
    [alerts],
  );
  const serviceImpactAlertCount = serviceImpactAlerts.length;
  const serviceImpactReviewCount = serviceImpactAlerts.filter(
    (alert) => Number(alert?.service_impact_summary?.review_group_count || 0) > 0,
  ).length;
  const serviceImpactCriticalCount = serviceImpactAlerts.filter((alert) => {
    const summary = alert?.service_impact_summary || {};
    return String(summary?.primary_health_status || '').toLowerCase() === 'critical' || Number(summary?.critical_group_count || 0) > 0;
  }).length;
  const serviceImpactGroupCount = useMemo(() => {
    const names = new Set(
      serviceImpactAlerts
        .map((alert) => String(alert?.service_impact_summary?.primary_name || '').trim())
        .filter(Boolean),
    );
    return names.size;
  }, [serviceImpactAlerts]);
  const serviceImpactQueue = useMemo(() => {
    return [...serviceImpactAlerts]
      .filter((alert) => matchesFocusedServiceGroup(alert))
      .sort(compareServiceImpactAlerts)
      .slice(0, 3);
  }, [serviceImpactAlerts, matchesFocusedServiceGroup]);
  const servicePriorityFocus = useMemo(() => {
    const topAlert = serviceImpactQueue[0];
    return summarizeServiceImpactAlertFocus(topAlert, t);
  }, [serviceImpactQueue]);
  const servicePriorityWorkspace = useMemo(() => recommendServiceWorkspace({
    healthStatus: servicePriorityFocus?.healthStatus,
    criticalIssueCount: servicePriorityFocus?.criticalGroups,
    activeIssueCount: servicePriorityFocus?.reviewGroups,
    discoveredOnlyDeviceCount: 0,
    managedDeviceCount: Math.max(1, Number(servicePriorityFocus?.matchedAssets || 0)),
    offlineDeviceCount: 0,
  }), [servicePriorityFocus]);
  const servicePriorityWorkspaceLabel = useMemo(() => t(
    `ops_workspace_${servicePriorityWorkspace.workspace}_title`,
    servicePriorityWorkspace.workspace === 'discover'
      ? 'Discover'
      : servicePriorityWorkspace.workspace === 'govern'
        ? 'Govern'
        : 'Observe',
  ), [servicePriorityWorkspace.workspace]);

  const focusedServiceSummary = useMemo(() => {
    if (!focusedServiceGroup) return null;
    const health = focusedServiceGroup?.health || {};
    return {
      criticality: String(focusedServiceGroup?.criticality || 'standard').trim().toLowerCase() || 'standard',
      ownerTeam: String(focusedServiceGroup?.owner_team || '').trim() || t('service_groups_owner_team_unassigned', 'Unassigned owner team'),
      healthScore: Number(health?.health_score || 0),
      activeIssueCount: Number(health?.active_issue_count || 0),
      offlineDeviceCount: Number(health?.offline_device_count || 0),
      managedDeviceCount: Number(health?.managed_device_count || 0),
      discoveredOnlyDeviceCount: Number(health?.discovered_only_device_count || 0),
    };
  }, [focusedServiceGroup]);
  const serviceReviewPosture = useMemo(
    () => summarizeServiceReviewPosture(focusedServiceGroup ? [focusedServiceGroup] : []),
    [focusedServiceGroup],
  );
  const serviceReviewAverageHealth = useMemo(() => {
    return getServiceReviewAverageHealth(serviceReviewPosture);
  }, [serviceReviewPosture]);
  const serviceReviewPressureIndex = useMemo(() => {
    return getServicePressureIndex(serviceReviewPosture);
  }, [serviceReviewPosture]);

  const focusedIssueId = useMemo(() => {
    const raw = Number(searchParams.get('focusIssueId') || 0);
    return raw > 0 ? raw : null;
  }, [searchParams]);

  useEffect(() => {
    if (!focusedIssueId) return;
    const alert = alerts.find((row) => Number(row?.id || 0) === focusedIssueId);
    if (!alert) return;

    setCategoryFilter('');
    setSeverityFilter('');
    setShowUnreadOnly(false);
    setShowServiceImpactOnly(false);

    const openActions = searchParams.get('openActions') === '1' || searchParams.get('openApproval') === '1';
    const openKnowledge = searchParams.get('openKnowledge') === '1';
    const openSop = searchParams.get('openSop') === '1';
    const openServiceImpact = searchParams.get('openServiceImpact') === '1';

    const run = async () => {
      const jobs = [];
      if (openActions) {
        setExpandedActionId(focusedIssueId);
        if (!issueActions[focusedIssueId]) jobs.push(loadIssueActions(focusedIssueId, { silent: true }));
        if (!issueApprovalContext[focusedIssueId]) jobs.push(loadIssueApprovalContext(focusedIssueId, { silent: true }));
      }
      if (openKnowledge) {
        setExpandedKnowledgeId(focusedIssueId);
        if (!issueKnowledge[focusedIssueId]) jobs.push(loadIssueKnowledge(focusedIssueId, { silent: true }));
      }
      if (openSop) {
        setExpandedSopId(focusedIssueId);
        if (!issueSops[focusedIssueId]) jobs.push(loadIssueSop(focusedIssueId, { silent: true }));
      }
      if (openServiceImpact) {
        setExpandedServiceImpactId(focusedIssueId);
        if (!issueServiceImpact[focusedIssueId]) jobs.push(loadIssueServiceImpact(focusedIssueId, { silent: true }));
      }
      if (jobs.length > 0) {
        await Promise.all(jobs);
      }
      window.requestAnimationFrame(() => {
        const node = document.getElementById(`issue-card-${focusedIssueId}`);
        node?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    };

    void run();
    const nextParams = new URLSearchParams(searchParams);
    ['focusIssueId', 'openActions', 'openApproval', 'openKnowledge', 'openSop', 'openServiceImpact'].forEach((key) => nextParams.delete(key));
    setSearchParams(nextParams, { replace: true });
  }, [
    alerts,
    focusedIssueId,
    issueActions,
    issueApprovalContext,
    issueKnowledge,
    issueServiceImpact,
    issueSops,
    loadIssueActions,
    loadIssueApprovalContext,
    loadIssueKnowledge,
    loadIssueServiceImpact,
    loadIssueSop,
    searchParams,
    setSearchParams,
  ]);

  const unreadCount = filteredAlerts.filter((a) => !a.is_read).length;

  useEffect(() => {
    if (searchParams.get('serviceImpact') !== '1') return;
    setShowServiceImpactOnly(true);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('serviceImpact');
    setSearchParams(nextParams, { replace: true });
  }, [searchParams, setSearchParams]);

  const clearFocusedServiceGroup = useCallback(() => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('focusGroupId');
    nextParams.delete('focusGroupName');
    setSearchParams(nextParams, { replace: true });
  }, [searchParams, setSearchParams]);
  const deliverySummary = useMemo(() => {
    const failed = deliveryItems.filter((item) => getOperationalStatusBadgeClass(item?.status).includes('rose') || String(item?.status || '').toLowerCase() === 'failed').length;
    const replayable = deliveryItems.filter((item) => !!item?.replay_available).length;
    return {
      total: deliveryItems.length,
      failed,
      replayable,
    };
  }, [deliveryItems]);

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012] h-full min-h-0 text-gray-900 dark:text-white animate-fade-in overflow-y-auto custom-scrollbar transition-colors">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <div className="relative">
              <Bell className="text-yellow-500" />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
                </span>
              )}
            </div>
            {t('layout_page_notifications')}
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-500 mt-1">
            {t('notifications_subtitle', 'Real-time infrastructure incidents.')}
            <span className="text-gray-500 dark:text-gray-400 ml-1">({t('notifications_auto_refresh', 'Auto-refreshing every 10s')})</span>
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => navigate('/observability')}
            className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:border-blue-300 dark:hover:border-blue-500/50 hover:text-blue-600 dark:hover:text-blue-400 rounded-lg transition-all text-sm font-medium text-gray-600 dark:text-gray-400"
          >
            <BarChart3 size={16} /> {t('common_open_observability', 'Open Observability')}
          </button>
          <button
            onClick={() => openGrafana(buildGrafanaAlertingCenterUrl())}
            className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 hover:bg-violet-50 dark:hover:bg-violet-900/20 hover:border-violet-300 dark:hover:border-violet-500/50 hover:text-violet-600 dark:hover:text-violet-400 rounded-lg transition-all text-sm font-medium text-gray-600 dark:text-gray-400"
          >
            <Activity size={16} /> {t('obs_alert_dashboard', 'Alert Dashboard')}
          </button>
          <button
            onClick={() => refreshIssues({ silent: false })}
            className="h-10 w-10 inline-flex items-center justify-center bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400 transition-colors"
            title={t('notifications_refresh_now', 'Refresh now')}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>

          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:border-blue-300 dark:hover:border-blue-500/50 hover:text-blue-600 dark:hover:text-blue-400 rounded-lg transition-all text-sm font-medium text-gray-600 dark:text-gray-400"
            >
              <Eye size={16} /> {t('notifications_mark_all_read', 'Mark All Read')}
            </button>
          )}

          {filteredAlerts.length > 0 && (
            <button
              onClick={handleClearAll}
              className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 hover:bg-red-50 dark:hover:bg-red-900/20 hover:border-red-300 dark:hover:border-red-500/50 hover:text-red-600 dark:hover:text-red-500 rounded-lg transition-all text-sm font-medium text-gray-600 dark:text-gray-400"
            >
              <Trash2 size={16} /> {t('notifications_ack_all', 'Acknowledge All')}
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-3 mb-6">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-4 py-2 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-700 dark:text-gray-300 outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
        >
          {categories.map((cat) => (
            <option key={cat.value} value={cat.value}>{cat.label}</option>
          ))}
        </select>

        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="px-4 py-2 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-700 dark:text-gray-300 outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
        >
          {severities.map((sev) => (
            <option key={sev.value} value={sev.value}>{sev.label}</option>
          ))}
        </select>

        <button
          onClick={() => setShowUnreadOnly(!showUnreadOnly)}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-all ${
            showUnreadOnly
              ? 'bg-blue-600 text-white border-blue-600 hover:bg-blue-500'
              : 'bg-white dark:bg-[#1b1d1f] text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700'
          }`}
        >
          {showUnreadOnly ? <EyeOff size={16} /> : <Eye size={16} />}
          {t('notifications_filter_unread', 'Unread Only')}
        </button>

        <button
          data-testid="notifications-filter-service-impact"
          onClick={() => setShowServiceImpactOnly(!showServiceImpactOnly)}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-all ${
            showServiceImpactOnly
              ? 'bg-cyan-600 text-white border-cyan-600 hover:bg-cyan-500'
              : 'bg-white dark:bg-[#1b1d1f] text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700'
          }`}
        >
          <LayoutGrid size={16} />
          {t('notifications_filter_service_impact', 'Service Impact Only')}
        </button>

        {(categoryFilter || severityFilter || showUnreadOnly || showServiceImpactOnly) && (
          <button
            onClick={() => {
              setCategoryFilter('');
              setSeverityFilter('');
              setShowUnreadOnly(false);
              setShowServiceImpactOnly(false);
            }}
            className="flex items-center gap-1 px-3 py-2 bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-lg text-sm hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            <X size={14} /> {t('notifications_filter_clear', 'Clear Filters')}
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 rounded-xl p-4">
          <div className="text-2xl font-bold text-gray-900 dark:text-white">{filteredAlerts.length}</div>
          <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_stat_total_active', 'Total Active')}</div>
        </div>
        <div className="bg-white dark:bg-[#1b1d1f] border border-red-200 dark:border-red-900/50 rounded-xl p-4">
          <div className="text-2xl font-bold text-red-600 dark:text-red-400">{filteredAlerts.filter((a) => a.severity === 'critical').length}</div>
          <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_severity_critical', 'Critical')}</div>
        </div>
        <div className="bg-white dark:bg-[#1b1d1f] border border-orange-200 dark:border-orange-900/50 rounded-xl p-4">
          <div className="text-2xl font-bold text-orange-600 dark:text-orange-400">{filteredAlerts.filter((a) => a.severity === 'warning').length}</div>
          <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_severity_warning', 'Warning')}</div>
        </div>
        <div className="bg-white dark:bg-[#1b1d1f] border border-blue-200 dark:border-blue-900/50 rounded-xl p-4">
          <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{unreadCount}</div>
          <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_stat_unread', 'Unread')}</div>
        </div>
      </div>

      <SectionCard className="mb-6 border border-cyan-200 dark:border-cyan-900/40 bg-cyan-50/70 dark:bg-cyan-950/10 shadow-sm" data-testid="notifications-service-impact-focus">
        {focusedGroupId || focusedGroupName ? (
          <div
            data-testid="notifications-focused-service-context"
            className="mb-4 rounded-2xl border border-violet-200/70 bg-white/80 p-4 shadow-sm dark:border-violet-900/40 dark:bg-violet-950/10"
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="text-[11px] font-black uppercase tracking-[0.25em] text-violet-700 dark:text-violet-300">
                  {t('notifications_service_context_badge', 'Focused service context')}
                </div>
                <h2 className="mt-2 text-lg font-bold text-gray-900 dark:text-gray-100">
                  {t('notifications_service_context_title_fmt', 'Review alerts for {value}').replace('{value}', focusedServiceGroup?.name || focusedGroupName || t('dashboard_service_impact_unknown_group', 'Mapped service group'))}
                </h2>
                <p className="mt-1 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
                  {t('notifications_service_context_desc', 'This alert view stays scoped to the selected service group so operators can follow impact, review reports, and open topology without losing context.')}
                </p>
                <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                  <span className="rounded-full border border-violet-200/70 bg-violet-50 px-2.5 py-1 dark:border-violet-900/40 dark:bg-violet-950/20">
                    {t('service_groups_health_score', 'Health Score')}: {Number(focusedServiceGroup?.health?.health_score || 0)}
                  </span>
                  <span className="rounded-full border border-gray-200 px-2.5 py-1 dark:border-white/10">
                    {t('service_groups_health_active_issues', 'Active issues')}: {Number(focusedServiceGroup?.health?.active_issue_count || 0)}
                  </span>
                  <span className="rounded-full border border-gray-200 px-2.5 py-1 dark:border-white/10">
                    {t('service_groups_health_offline_devices', 'Offline devices')}: {Number(focusedServiceGroup?.health?.offline_device_count || 0)}
                  </span>
                </div>
                {focusedServiceSummary ? (
                  <div
                    data-testid="notifications-focused-service-health-card"
                    className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
                  >
                    <div className="rounded-xl border border-violet-200/70 bg-white/90 p-3 dark:border-violet-900/40 dark:bg-[#121826]">
                      <div className="text-[11px] font-black uppercase tracking-[0.18em] text-violet-700 dark:text-violet-300">
                        {t('notifications_service_context_summary_title', 'Service review summary')}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <span className="inline-flex rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-violet-700 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200">
                          {t(`service_groups_criticality_${focusedServiceSummary.criticality}`, focusedServiceSummary.criticality)}
                        </span>
                        <span className="inline-flex rounded-full border border-cyan-200 bg-cyan-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-cyan-700 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200">
                          {t('service_groups_health_score', 'Health Score')}: {focusedServiceSummary.healthScore}
                        </span>
                      </div>
                      <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                        {t('service_groups_owner_team_label', 'Owner team')}: {focusedServiceSummary.ownerTeam}
                      </div>
                    </div>
                    <div className="rounded-xl border border-cyan-200/70 bg-white/90 p-3 dark:border-cyan-900/40 dark:bg-[#121826]">
                      <div className="text-[11px] font-black uppercase tracking-[0.18em] text-cyan-700 dark:text-cyan-300">
                        {t('notifications_service_context_health_title', 'Current impact')}
                      </div>
                      <div className="mt-2 space-y-1 text-xs text-gray-600 dark:text-gray-300">
                        <div>{t('service_groups_health_active_issues', 'Active issues')}: {focusedServiceSummary.activeIssueCount}</div>
                        <div>{t('service_groups_health_offline_devices', 'Offline devices')}: {focusedServiceSummary.offlineDeviceCount}</div>
                      </div>
                    </div>
                    <div className="rounded-xl border border-emerald-200/70 bg-white/90 p-3 dark:border-emerald-900/40 dark:bg-[#121826]">
                      <div className="text-[11px] font-black uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-300">
                        {t('notifications_service_context_monitoring_title', 'Monitoring coverage')}
                      </div>
                      <div className="mt-2 space-y-1 text-xs text-gray-600 dark:text-gray-300">
                        <div>{t('service_groups_health_managed_devices', 'Managed devices')}: {focusedServiceSummary.managedDeviceCount}</div>
                        <div>{t('service_groups_health_discovered_only', 'Discovered only')}: {focusedServiceSummary.discoveredOnlyDeviceCount}</div>
                      </div>
                    </div>
                    <div className="rounded-xl border border-amber-200/70 bg-white/90 p-3 dark:border-amber-900/40 dark:bg-[#121826]">
                      <div className="text-[11px] font-black uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300">
                        {t('notifications_service_context_next_title', 'Recommended next step')}
                      </div>
                      <div className="mt-2 text-xs text-gray-600 dark:text-gray-300">
                        {focusedServiceSummary.offlineDeviceCount > 0
                          ? t('service_groups_review_next_action_offline', 'Inspect offline devices and the attached path before pushing additional changes.')
                          : focusedServiceSummary.discoveredOnlyDeviceCount > focusedServiceSummary.managedDeviceCount
                            ? t('service_groups_review_next_action_discovered_only', 'Many assets are still discovered-only. Review which devices should be promoted into managed monitoring.')
                            : t('notifications_service_context_next_ready', 'Open the service review to continue from actions, reports, and topology with the same focus.')}
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  data-testid="notifications-focused-service-open-group"
                  onClick={() => openServiceGroups(focusedServiceGroup?.id || focusedGroupId, focusedServiceGroup?.name || focusedGroupName)}
                  className="inline-flex items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-700 transition-colors hover:bg-sky-100 dark:border-sky-900/50 dark:bg-sky-950/20 dark:text-sky-200 dark:hover:bg-sky-950/30"
                >
                  <LayoutGrid size={16} />
                  {t('notifications_service_context_open_group', 'Open service group')}
                </button>
                <button
                  type="button"
                  data-testid="notifications-focused-service-open-review"
                  onClick={() => openFocusedServiceReview(focusedServiceGroup?.id || focusedGroupId, focusedServiceGroup?.name || focusedGroupName)}
                  className="inline-flex items-center gap-2 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-sm font-medium text-violet-700 transition-colors hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200 dark:hover:bg-violet-950/30"
                >
                  <FileText size={16} />
                  {t('notifications_service_context_open_review', 'Open service review')}
                </button>
                <button
                  type="button"
                  data-testid="notifications-focused-service-open-topology"
                  onClick={() => openFocusedServiceTopology(focusedServiceGroup?.id || focusedGroupId, focusedServiceGroup?.name || focusedGroupName)}
                  className="inline-flex items-center gap-2 rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm font-medium text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
                >
                  <MapIcon size={16} />
                  {t('notifications_service_context_open_topology', 'Open topology')}
                </button>
                <button
                  type="button"
                  data-testid="notifications-focused-service-clear"
                  onClick={clearFocusedServiceGroup}
                  className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:border-gray-700 dark:bg-[#0e1012] dark:text-gray-200 dark:hover:bg-gray-800"
                >
                  <X size={16} />
                  {t('notifications_service_context_clear', 'Clear focus')}
                </button>
              </div>
            </div>
          </div>
        ) : null}
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-[11px] font-black uppercase tracking-[0.25em] text-cyan-700 dark:text-cyan-300">
              {t('notifications_service_focus_badge', 'Service impact focus')}
            </div>
            <h2 className="mt-2 text-lg font-bold text-gray-900 dark:text-gray-100">
              {t('notifications_service_focus_title', 'Keep business impact in view while you triage alerts.')}
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
              {t('notifications_service_focus_desc', 'Use the service-aware alert filter when you want the list to stay focused on mapped service groups, review hotspots, and the next operational action.')}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              data-testid="notifications-open-service-groups"
              onClick={openServiceGroups}
              className="inline-flex items-center gap-2 rounded-lg border border-cyan-200 bg-white px-3 py-2 text-sm font-medium text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-[#0e1012] dark:text-cyan-200 dark:hover:bg-cyan-950/30"
            >
              <LayoutGrid size={16} />
              {t('notifications_service_focus_open_groups', 'Open Service Groups')}
            </button>
            <button
              type="button"
              onClick={() => setShowServiceImpactOnly((prev) => !prev)}
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                showServiceImpactOnly
                  ? 'border-cyan-600 bg-cyan-600 text-white hover:bg-cyan-500'
                  : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:bg-[#0e1012] dark:text-gray-200 dark:hover:bg-gray-800'
              }`}
            >
              <Filter size={16} />
              {showServiceImpactOnly
                ? t('notifications_service_focus_show_all', 'Show all alerts')
                : t('notifications_service_focus_enable', 'Focus on service-aware alerts')}
            </button>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div className="rounded-xl border border-cyan-200/70 bg-white/90 p-4 dark:border-cyan-900/40 dark:bg-[#111827]">
            <div className="text-2xl font-bold text-cyan-700 dark:text-cyan-200">{serviceImpactAlertCount}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_service_focus_alerts', 'Service-aware alerts')}</div>
          </div>
          <div className="rounded-xl border border-indigo-200/70 bg-white/90 p-4 dark:border-indigo-900/40 dark:bg-[#111827]">
            <div className="text-2xl font-bold text-indigo-700 dark:text-indigo-200">{serviceImpactGroupCount}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_service_focus_groups', 'Mapped services')}</div>
          </div>
          <div className="rounded-xl border border-amber-200/70 bg-white/90 p-4 dark:border-amber-900/40 dark:bg-[#111827]">
            <div className="text-2xl font-bold text-amber-700 dark:text-amber-200">{serviceImpactReviewCount}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_service_focus_review', 'Needs review')}</div>
          </div>
          <div className="rounded-xl border border-rose-200/70 bg-white/90 p-4 dark:border-rose-900/40 dark:bg-[#111827]">
            <div className="text-2xl font-bold text-rose-700 dark:text-rose-200">{serviceImpactCriticalCount}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_service_focus_critical', 'Critical service impact')}</div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="notifications-service-posture">
          <div className="rounded-xl border border-rose-200/70 bg-white/90 p-4 dark:border-rose-900/40 dark:bg-[#111827]">
            <div className="text-2xl font-bold text-rose-700 dark:text-rose-200">{serviceReviewPosture.criticalGroups}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('ops_home_service_posture_critical', 'Critical groups')}</div>
          </div>
          <div className="rounded-xl border border-amber-200/70 bg-white/90 p-4 dark:border-amber-900/40 dark:bg-[#111827]">
            <div className="text-2xl font-bold text-amber-700 dark:text-amber-200">{serviceReviewPosture.reviewGroups}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('ops_home_service_posture_review', 'Review groups')}</div>
          </div>
          <div className="rounded-xl border border-violet-200/70 bg-white/90 p-4 dark:border-violet-900/40 dark:bg-[#111827]">
            <div className="text-2xl font-bold text-violet-700 dark:text-violet-200">{serviceReviewPosture.discoveredOnlyPressure}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('ops_home_service_posture_discovered_only', 'Discovered-only pressure')}</div>
          </div>
          <div className="rounded-xl border border-cyan-200/70 bg-white/90 p-4 dark:border-cyan-900/40 dark:bg-[#111827]">
            <div className="text-2xl font-bold text-cyan-700 dark:text-cyan-200">{serviceReviewPosture.activeIssues}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('operations_reports_metric_service_issues', 'Service-Scoped Issues')}</div>
          </div>
        </div>
        <div className="mt-3 rounded-2xl border border-sky-200/70 bg-white/85 p-4 shadow-sm dark:border-sky-900/40 dark:bg-sky-950/10">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-[11px] font-black uppercase tracking-[0.25em] text-sky-700 dark:text-sky-300">
                {t('service_operating_posture_title', 'Service Operating Posture')}
              </div>
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                {t('service_operating_posture_desc', 'Use the same service-health baseline across alerts, topology, and reports so operators do not lose business context while triaging.')}
              </p>
            </div>
            <div className="grid grid-cols-3 gap-3 lg:min-w-[480px]">
              <div className="rounded-xl border border-sky-200/70 bg-sky-50/70 p-3 dark:border-sky-900/40 dark:bg-sky-950/10">
                <div className="text-[10px] font-black uppercase tracking-widest text-sky-700 dark:text-sky-300">
                  {t('service_operating_posture_average_health', 'Average health')}
                </div>
                <div className="mt-1 text-2xl font-black text-sky-700 dark:text-sky-200">{serviceReviewAverageHealth}</div>
              </div>
              <div className="rounded-xl border border-indigo-200/70 bg-indigo-50/70 p-3 dark:border-indigo-900/40 dark:bg-indigo-950/10">
                <div className="text-[10px] font-black uppercase tracking-widest text-indigo-700 dark:text-indigo-300">
                  {t('service_operating_posture_groups_in_scope', 'Groups in scope')}
                </div>
                <div className="mt-1 text-2xl font-black text-indigo-700 dark:text-indigo-200">{serviceReviewPosture.totalGroups}</div>
              </div>
                <div className="rounded-xl border border-fuchsia-200/70 bg-fuchsia-50/70 p-3 dark:border-fuchsia-900/40 dark:bg-fuchsia-950/10">
                  <div className="text-[10px] font-black uppercase tracking-widest text-fuchsia-700 dark:text-fuchsia-300">
                    {t('service_operating_posture_pressure_index', 'Pressure index')}
                  </div>
                  <div className="mt-1 text-2xl font-black text-fuchsia-700 dark:text-fuchsia-200">{serviceReviewPressureIndex}</div>
                  <div className="mt-2">
                    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-bold ${pressureBadgeClass(serviceReviewPressureIndex)}`}>
                      {getOperationsPressureLabel(serviceReviewPressureIndex, t)}
                    </span>
                  </div>
                  <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
                    {getOperationsPressureGuidance(serviceReviewPressureIndex, t)}
                  </div>
                </div>
              </div>
            </div>
        </div>

        <div className="mt-4 rounded-2xl border border-violet-200/70 bg-white/85 p-4 shadow-sm dark:border-violet-900/40 dark:bg-violet-950/10" data-testid="notifications-service-priority-focus">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-[11px] font-black uppercase tracking-[0.25em] text-violet-700 dark:text-violet-300">
                {t('notifications_service_priority_focus_badge', 'Service priority focus')}
              </div>
              {servicePriorityFocus ? (
                <>
                  <h3 className="mt-2 text-lg font-bold text-gray-900 dark:text-gray-100">{servicePriorityFocus.groupName}</h3>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-semibold ${serviceHealthBadgeClass(servicePriorityFocus.healthStatus)}`}>
                      {t('service_groups_health_score', 'Health Score')}: {servicePriorityFocus.healthScore}
                    </span>
                    <span className="rounded-full border border-gray-200 px-2.5 py-1 dark:border-white/10">
                      {t('dashboard_service_impact_critical_groups_fmt', 'Critical groups {value}').replace('{value}', String(servicePriorityFocus.criticalGroups))}
                    </span>
                    <span className="rounded-full border border-gray-200 px-2.5 py-1 dark:border-white/10">
                      {t('dashboard_service_impact_review_groups_fmt', 'Needs review {value}').replace('{value}', String(servicePriorityFocus.reviewGroups))}
                    </span>
                  </div>
                  <p className="mt-3 max-w-3xl text-sm text-gray-600 dark:text-gray-300">{servicePriorityFocus.nextAction}</p>
                </>
              ) : (
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                  {t('notifications_service_priority_focus_empty', 'No mapped service is currently demanding immediate operator focus.')}
                </p>
              )}
            </div>
            {servicePriorityFocus ? (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  data-testid="notifications-service-priority-open-workspace"
                  onClick={() => navigate(`/automation?workspace=${servicePriorityWorkspace.workspace}`)}
                  className="inline-flex items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-700 transition-colors hover:bg-sky-100 dark:border-sky-900/50 dark:bg-sky-950/20 dark:text-sky-200 dark:hover:bg-sky-950/30"
                >
                  <Activity size={16} />
                  {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', servicePriorityWorkspaceLabel)}
                </button>
                <button
                  type="button"
                  data-testid="notifications-service-priority-open-review"
                  onClick={() => openFocusedServiceReview(servicePriorityFocus.groupId, servicePriorityFocus.groupName)}
                  className="inline-flex items-center gap-2 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-sm font-medium text-violet-700 transition-colors hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200 dark:hover:bg-violet-950/30"
                >
                  <FileText size={16} />
                  {t('notifications_service_priority_open_review', 'Open service review')}
                </button>
                <button
                  type="button"
                  data-testid="notifications-service-priority-open-topology"
                  onClick={() => openFocusedServiceTopology(servicePriorityFocus.groupId, servicePriorityFocus.groupName)}
                  className="inline-flex items-center gap-2 rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm font-medium text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
                >
                  <MapIcon size={16} />
                  {t('notifications_service_priority_open_topology', 'Open topology')}
                </button>
                <button
                  type="button"
                  data-testid="notifications-service-priority-open-issue"
                  onClick={() => {
                    const target = serviceImpactQueue.find((alert) => Number(alert?.id || 0) === servicePriorityFocus.issueId);
                    if (target) focusServiceAwareAlert(target, { openServiceImpact: true });
                  }}
                  className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:border-gray-700 dark:bg-[#0e1012] dark:text-gray-200 dark:hover:bg-gray-800"
                >
                  <Bell size={16} />
                  {t('notifications_service_priority_open_issue', 'Open issue flow')}
                </button>
              </div>
            ) : null}
          </div>
        </div>

        <div
          className="mt-4 rounded-2xl border border-cyan-200/70 bg-white/80 p-4 shadow-sm dark:border-cyan-900/40 dark:bg-[#0f1720]"
          data-testid="notifications-service-queue"
        >
          <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-[11px] font-black uppercase tracking-[0.25em] text-cyan-700 dark:text-cyan-300">
                {t('notifications_service_queue_title', 'Service operations queue')}
              </div>
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                {t('notifications_service_queue_desc', 'Pull the highest-impact mapped alerts to the top so operators can open the issue flow, actions, and state history without hunting through the full list.')}
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            {serviceImpactQueue.length > 0 ? serviceImpactQueue.map((alert) => {
              const summary = alert?.service_impact_summary || {};
              const issueId = Number(alert?.id || 0);
              return (
                <div
                  key={`service-queue-${issueId}`}
                  className="rounded-xl border border-cyan-200/70 bg-cyan-50/60 p-3 dark:border-cyan-900/40 dark:bg-cyan-950/10"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        {String(summary?.primary_name || '').trim() || t('dashboard_service_impact_unknown_group', 'Mapped service group')}
                      </div>
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {alert?.title || alert?.message || alert?.device || t('notifications_category_system', 'System')}
                      </div>
                    </div>
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-semibold ${serviceHealthBadgeClass(summary?.primary_health_status || 'review')}`}>
                      {t('service_groups_health_score', 'Health Score')}: {Number(summary?.primary_health_score || 0)}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                    <span>{t('notifications_service_impact_summary_fmt', 'Services {value}').replace('{value}', String(Number(summary?.count || 0)))}</span>
                    <span>{t('dashboard_service_impact_review_groups_fmt', 'Needs review {value}').replace('{value}', String(Number(summary?.review_group_count || 0)))}</span>
                    <span>{t('dashboard_service_impact_critical_groups_fmt', 'Critical groups {value}').replace('{value}', String(Number(summary?.critical_group_count || 0)))}</span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      data-testid={`notifications-service-queue-open-issue-${issueId}`}
                      onClick={() => focusServiceAwareAlert(alert, { openServiceImpact: true })}
                      className="rounded-full border border-cyan-200 bg-white px-3 py-1 text-[11px] font-semibold text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-[#0e1012] dark:text-cyan-200 dark:hover:bg-cyan-950/30"
                    >
                      {t('notifications_service_queue_open_issue_flow', 'Open issue flow')}
                    </button>
                    <button
                      type="button"
                      data-testid={`notifications-service-queue-open-actions-${issueId}`}
                      onClick={() => focusServiceAwareAlert(alert, { openActions: true })}
                      className="rounded-full border border-gray-200 px-3 py-1 text-[11px] font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/10"
                    >
                      {t('notifications_service_queue_open_actions', 'Open actions')}
                    </button>
                    <button
                      type="button"
                      data-testid={`notifications-service-queue-open-review-${issueId}`}
                      onClick={() => openFocusedServiceReview(summary?.primary_group_id, summary?.primary_name)}
                      className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-[11px] font-semibold text-violet-700 transition-colors hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200 dark:hover:bg-violet-950/30"
                    >
                      {t('notifications_service_queue_open_review', 'Open service review')}
                    </button>
                    <button
                      type="button"
                      data-testid={`notifications-service-queue-open-history-${issueId}`}
                      onClick={() => openStateHistoryForIssue(alert)}
                      className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-semibold text-slate-700 transition-colors hover:bg-slate-100 dark:border-slate-800/60 dark:bg-slate-950/20 dark:text-slate-200 dark:hover:bg-slate-900/40"
                    >
                      {t('notifications_service_queue_open_history', 'Open state history')}
                    </button>
                  </div>
                </div>
              );
            }) : (
              <div className="rounded-xl border border-dashed border-cyan-200 px-4 py-6 text-sm text-gray-500 dark:border-cyan-900/40 dark:text-gray-400">
                {t('notifications_service_queue_empty', 'No service-aware alerts are queued right now.')}
              </div>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard className="mb-6 border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#1b1d1f] shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-[11px] font-black uppercase tracking-[0.25em] text-blue-600 dark:text-blue-300">
              {t('notifications_northbound_watch', 'Northbound Delivery Watch')}
            </div>
            <h2 className="mt-2 text-lg font-bold text-gray-900 dark:text-gray-100">
              {t('notifications_northbound_watch_title', 'Keep receiver health visible while you investigate alerts.')}
            </h2>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400 max-w-3xl">
              {t('notifications_northbound_watch_desc', 'Recent webhook deliveries, failure causes, and replay actions stay close to the alert feed so operators can retry without losing context.')}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => loadWebhookDeliveries({ silent: false, refreshing: true })}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-[#0e1012] border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <RefreshCw size={14} className={deliveryRefreshing ? 'animate-spin' : ''} />
              {deliveryRefreshing ? t('common_refreshing', 'Refreshing...') : t('notifications_refresh_now', 'Refresh now')}
            </button>
            <button
              type="button"
              onClick={openAlertChannels}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium text-white"
            >
              <Settings size={14} />
              {t('notifications_open_alert_channels', 'Open Alert Channels')}
            </button>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#0f1113] p-4">
            <div className="text-2xl font-bold text-gray-900 dark:text-white">{deliverySummary.total}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_northbound_recent_total', 'Recent Deliveries')}</div>
          </div>
          <div className="rounded-xl border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/10 p-4">
            <div className="text-2xl font-bold text-rose-600 dark:text-rose-300">{deliverySummary.failed}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_northbound_failed_total', 'Failures')}</div>
          </div>
          <div className="rounded-xl border border-blue-200 dark:border-blue-900/40 bg-blue-50 dark:bg-blue-950/10 p-4">
            <div className="text-2xl font-bold text-blue-600 dark:text-blue-300">{deliverySummary.replayable}</div>
            <div className="text-xs text-gray-500 uppercase font-medium">{t('notifications_northbound_replayable_total', 'Replayable')}</div>
          </div>
        </div>

        <div className="mt-4 space-y-3" data-testid="northbound-delivery-watch">
          {deliveryLoading ? (
            <div className="text-sm text-gray-500 dark:text-gray-400">{t('common_loading', 'Loading...')}</div>
          ) : deliveryItems.length === 0 ? (
            <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
              {deliveryError || t('notifications_northbound_empty', 'No northbound delivery history is available yet.')}
            </div>
          ) : (
            deliveryItems.map((delivery) => {
              const target = [delivery.target_host, delivery.target_path].filter(Boolean).join('');
              const eventTitle = delivery.title || delivery.event_type || t('notifications_northbound_delivery', 'Delivery');
              const status = delivery.status || 'unknown';
              return (
                <div
                  key={`${delivery.delivery_id}-${delivery.event_log_id}`}
                  className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#0f1113] px-4 py-4"
                >
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-bold uppercase ${getOperationalStatusBadgeClass(status)}`}>
                          {getOperationalStatusLabel(status)}
                        </span>
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-semibold border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#14171a] text-gray-600 dark:text-gray-300">
                          {String(delivery.mode || 'generic')}
                        </span>
                        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{eventTitle}</span>
                      </div>
                      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        {getOperationalStatusHint(status)}
                      </p>
                    </div>
                    {delivery.replay_available && (
                      <button
                        type="button"
                        onClick={() => handleRetryDelivery(delivery.delivery_id)}
                        disabled={deliveryRetryingId === delivery.delivery_id}
                        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium text-white disabled:opacity-50"
                      >
                        <RefreshCw size={14} className={deliveryRetryingId === delivery.delivery_id ? 'animate-spin' : ''} />
                        {deliveryRetryingId === delivery.delivery_id
                          ? t('settings_webhook_retrying', 'Retrying...')
                          : t('notifications_northbound_retry', 'Retry Delivery')}
                      </button>
                    )}
                  </div>
                  <div className="mt-3 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 text-xs text-gray-600 dark:text-gray-300">
                    <div>
                      <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_northbound_target', 'Target')}</div>
                      <div className="font-mono break-all">{target || '-'}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_northbound_attempts', 'Attempts')}</div>
                      <div className="font-mono">{String(Number(delivery.attempts || 0))}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_northbound_http_status', 'HTTP Status')}</div>
                      <div className="font-mono">{delivery.status_code != null ? String(delivery.status_code) : '-'}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_northbound_last_event', 'Last Event')}</div>
                      <div>{delivery.timestamp ? new Date(delivery.timestamp).toLocaleString() : '-'}</div>
                    </div>
                  </div>
                  {delivery.error && (
                    <div className="mt-3 rounded-lg border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/10 px-3 py-2 text-xs text-rose-700 dark:text-rose-300">
                      {t('notifications_northbound_error', 'Failure cause')}: {delivery.error}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </SectionCard>

      <div className="space-y-4">
        {loading && filteredAlerts.length === 0 ? (
          <SectionCard className="py-20 border-dashed">
            <InlineLoading label={t('notifications_loading', 'Loading alerts...')} />
          </SectionCard>
        ) : filteredAlerts.length === 0 ? (
          <SectionCard className="py-20 border-dashed">
            <InlineEmpty label={t('notifications_no_active', 'No active alarms detected.')} />
          </SectionCard>
        ) : (
          filteredAlerts.map((alert) => {
            const automationSummary = alert?.automation || {};
            const automationDetail = getAutomationDetail(alert.id);
            const runResult = getAutomationRun(alert.id);
            const isAutomationExpanded = expandedAutomationId === alert.id;
            const isAutomationLoading = automationLoadingId === alert.id;
            const isAutomationRunning = automationRunningId === alert.id;
            const isActionExpanded = expandedActionId === alert.id;
            const isActionLoading = actionsLoadingId === alert.id;
            const actionRows = getActionRows(alert.id);
            const actionSummary = alert?.action_summary || {};
            const approvalSummary = alert?.approval_summary || {};
            const approvalPayload = getApprovalPayload(alert.id);
            const isApprovalContextLoading = approvalContextLoadingId === alert.id;
            const isKnowledgeExpanded = expandedKnowledgeId === alert.id;
            const isKnowledgeLoading = knowledgeLoadingId === alert.id;
            const knowledgeRows = getKnowledgeRows(alert.id);
            const knowledgeSummary = alert?.knowledge_summary || {};
            const isSopExpanded = expandedSopId === alert.id;
            const isSopLoading = sopLoadingId === alert.id;
            const sopPayload = getSopPayload(alert.id);
            const sopSummary = alert?.sop_summary || {};
            const isServiceImpactExpanded = expandedServiceImpactId === alert.id;
            const isServiceImpactLoading = serviceImpactLoadingId === alert.id;
            const serviceImpactPayload = getServiceImpactPayload(alert.id);
            const serviceImpactSummary = alert?.service_impact_summary || {};
            const cloudScope = alert?.cloud_scope && typeof alert.cloud_scope === 'object' ? alert.cloud_scope : null;
            const canCreateCloudIntent = Boolean(cloudScope?.can_create_intent && cloudScope?.provider);
            const cloudResourceSummary = [cloudScope?.resource_type_label || cloudScope?.resource_type, cloudScope?.region]
              .filter(Boolean)
              .join(' · ');
            const cloudAccountSummary = cloudScope?.account_name
              || (cloudScope?.account_id != null ? `#${String(cloudScope.account_id)}` : '');
            const scopedResourceCount = Number(cloudScope?.scoped_resources || 0);

            return (
              <div
                key={alert.id}
                id={`issue-card-${alert.id}`}
                className={`relative flex items-start gap-5 p-5 rounded-xl border transition-all hover:translate-x-1 ${
                  alert.severity === 'critical'
                    ? 'bg-red-50 dark:bg-red-950/10 border-red-200 dark:border-red-900/50 hover:bg-red-100 dark:hover:bg-red-900/20'
                    : alert.severity === 'warning'
                      ? 'bg-orange-50 dark:bg-orange-950/10 border-orange-200 dark:border-orange-900/50 hover:bg-orange-100 dark:hover:bg-orange-900/20'
                      : 'bg-blue-50 dark:bg-blue-950/10 border-blue-200 dark:border-blue-900/50 hover:bg-blue-100 dark:hover:bg-blue-900/20'
                } ${!alert.is_read ? 'ring-2 ring-blue-400/30' : ''}`}
              >
                <div className={`p-3 rounded-full shrink-0 ${
                  alert.severity === 'critical'
                    ? 'bg-red-100 dark:bg-red-500/20 text-red-500'
                    : alert.severity === 'warning'
                      ? 'bg-orange-100 dark:bg-orange-500/20 text-orange-500'
                      : 'bg-blue-100 dark:bg-blue-500/20 text-blue-500'
                }`}>
                  {alert.severity === 'critical'
                    ? <XCircle size={24} />
                    : alert.severity === 'warning'
                      ? <AlertTriangle size={24} />
                      : <Bell size={24} />}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-start gap-4">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className={`text-lg font-bold ${
                        alert.severity === 'critical'
                          ? 'text-red-600 dark:text-red-400'
                          : alert.severity === 'warning'
                            ? 'text-orange-600 dark:text-orange-400'
                            : 'text-blue-600 dark:text-blue-400'
                      }`}>
                        {alert.title}
                      </h3>
                      {!alert.is_read && (
                        <span className="px-2 py-0.5 text-[10px] font-bold bg-blue-600 text-white rounded-full uppercase">
                          {t('notifications_badge_new', 'New')}
                        </span>
                      )}
                      {alert.site_name && (
                        <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-gray-100 dark:bg-[#0e1012] border border-gray-200 dark:border-gray-800 text-gray-600 dark:text-gray-300">
                          {alert.site_name}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="flex items-center gap-1 px-2 py-1 text-[10px] text-gray-500 dark:text-gray-400 font-mono bg-gray-100 dark:bg-[#0e1012] rounded border border-gray-200 dark:border-gray-800">
                        {getCategoryIcon(alert.category)} {getCategoryLabel(alert.category)}
                      </span>
                      <span className={`inline-flex items-center gap-1 px-2 py-1 text-[10px] font-bold uppercase rounded border ${getOperationalStatusBadgeClass(mapSeverityToOperationalStatus(alert.severity))}`}>
                        {getOperationalStatusLabel(mapSeverityToOperationalStatus(alert.severity))}
                      </span>
                      <span className="flex items-center gap-1.5 text-xs text-gray-500 font-mono bg-gray-100 dark:bg-[#0e1012] px-2 py-1 rounded border border-gray-200 dark:border-gray-800">
                        <Clock size={12} /> {formatTimeAgo(alert.created_at)}
                      </span>
                    </div>
                  </div>

                  <p className="text-gray-700 dark:text-white mt-1 font-medium">{alert.device}</p>
                  <p className="text-gray-600 dark:text-gray-400 text-sm mt-0.5">{alert.message}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {getOperationalStatusHint(mapSeverityToOperationalStatus(alert.severity))}
                  </p>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span
                      data-testid={`issue-automation-badge-${alert.id}`}
                      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold ${automationBadgeClass(automationSummary?.primary_status)}`}
                    >
                      {automationLabel(automationSummary?.primary_status)}
                    </span>
                    {Number(automationSummary?.matched_rules || 0) > 0 && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-gray-200 dark:border-gray-700 bg-white/80 dark:bg-[#0e1012] text-[11px] text-gray-600 dark:text-gray-300">
                        {t('notifications_automation_rules_fmt', '{value} rule(s)').replace('{value}', String(automationSummary.matched_rules))}
                      </span>
                    )}
                    {Number(actionSummary?.total || 0) > 0 && (
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold ${actionStatusBadgeClass(actionSummary?.latest_status || 'open')}`}>
                        {t('notifications_action_summary_fmt', 'Actions {value}').replace('{value}', String(Number(actionSummary.total || 0)))}
                      </span>
                    )}
                    {Number(approvalSummary?.total || 0) > 0 && (
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold ${approvalStatusBadgeClass(approvalSummary?.latest_status || 'pending')}`}>
                        {t('notifications_approval_summary_fmt', 'Approvals {value}').replace('{value}', String(Number(approvalSummary.total || 0)))}
                      </span>
                    )}
                    {Number(knowledgeSummary?.recommendation_count || 0) > 0 && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-purple-200 dark:border-purple-800/50 bg-purple-50 dark:bg-purple-500/10 text-[11px] font-semibold text-purple-700 dark:text-purple-300">
                        {t('notifications_knowledge_summary_fmt', 'Known Errors {value}').replace('{value}', String(Number(knowledgeSummary.recommendation_count || 0)))}
                      </span>
                    )}
                    {Boolean(sopSummary?.available) && (
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold ${sopReadinessBadgeClass(sopSummary?.readiness_status)}`}>
                        {t('notifications_sop_summary_fmt', 'SOP {value}').replace('{value}', String(Number(sopSummary?.step_count || 0)))}
                      </span>
                    )}
                    {Number(serviceImpactSummary?.count || 0) > 0 && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-cyan-200 dark:border-cyan-800/50 bg-cyan-50 dark:bg-cyan-500/10 text-[11px] font-semibold text-cyan-700 dark:text-cyan-300">
                        {t('notifications_service_impact_summary_fmt', 'Services {value}').replace('{value}', String(Number(serviceImpactSummary?.count || 0)))}
                      </span>
                    )}
                    {serviceImpactSummary?.primary_health_status && (
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold ${serviceHealthBadgeClass(serviceImpactSummary?.primary_health_status)}`}>
                        {t('service_groups_health_score', 'Health Score')}: {Number(serviceImpactSummary?.primary_health_score || 0)}
                      </span>
                    )}
                    {automationSummary?.next_action && (
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {automationSummary.next_action}
                      </span>
                    )}
                    {cloudScope?.provider && (
                      <span
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-sky-200 dark:border-sky-800/60 bg-sky-50 dark:bg-sky-500/10 text-[11px] font-semibold text-sky-700 dark:text-sky-300"
                        data-testid={`issue-cloud-badge-${alert.id}`}
                      >
                        <GitBranch size={12} />
                        {String(cloudScope.provider || '').toUpperCase()}
                        {cloudResourceSummary ? ` · ${cloudResourceSummary}` : ''}
                      </span>
                    )}
                  </div>
                  {cloudScope?.provider && (
                    <div
                      className="mt-2 rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/10 px-3 py-2 text-xs text-sky-700 dark:text-sky-200"
                      data-testid={`issue-cloud-scope-${alert.id}`}
                    >
                      <span className="font-semibold">
                        {t('notifications_cloud_scope_title', 'Cloud scope')}:
                      </span>{' '}
                      {String(cloudScope.provider || '').toUpperCase()}
                      {cloudAccountSummary ? ` / ${cloudAccountSummary}` : ''}
                      {cloudResourceSummary ? ` / ${cloudResourceSummary}` : ''}
                      {scopedResourceCount > 0 ? ` / ${t('approval_scoped_resources', 'Scoped Resources')} ${scopedResourceCount}` : ''}
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap gap-3">
                    <button
                      onClick={() => handleResolve(alert.id)}
                      className="px-4 py-1.5 bg-green-600 hover:bg-green-500 text-white text-xs font-bold rounded shadow-lg shadow-green-900/20 transition-colors flex items-center gap-2"
                    >
                      <CheckCircle size={14} /> {t('notifications_resolve', 'Resolve')}
                    </button>
                    {!alert.is_read && (
                      <button
                        onClick={() => handleMarkRead(alert.id)}
                        className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded transition-colors flex items-center gap-2"
                      >
                        <Eye size={14} /> {t('notifications_mark_read', 'Mark Read')}
                      </button>
                    )}
                    {canCreateCloudIntent && (
                      <button
                        onClick={() => openCloudIntent(alert)}
                        className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-sky-50 dark:hover:bg-sky-900/20 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors flex items-center gap-2"
                        data-testid={`issue-open-cloud-intent-${alert.id}`}
                      >
                        <GitBranch size={14} /> {t('notifications_open_cloud_intent', 'Create Cloud Intent')}
                      </button>
                    )}
                    {cloudScope?.provider && (
                      <button
                        onClick={() => openCloudTopologyImpact(alert)}
                        className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-violet-50 dark:hover:bg-violet-900/20 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors flex items-center gap-2"
                        data-testid={`issue-open-topology-impact-${alert.id}`}
                      >
                        <MapIcon size={14} /> {t('notifications_open_topology_impact', 'Open Topology Impact')}
                      </button>
                    )}
                    {cloudScope?.provider && (
                      <button
                        onClick={() => openCloudAccounts(alert)}
                        className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-slate-50 dark:hover:bg-slate-800 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors flex items-center gap-2"
                      >
                        <Cloud size={14} /> {t('cloud_detail_open_accounts', 'Open Cloud Accounts')}
                      </button>
                    )}
                    <button
                      data-testid={`issue-open-state-history-${alert.id}`}
                      onClick={() => openStateHistoryForIssue(alert)}
                      className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-slate-50 dark:hover:bg-slate-800 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors flex items-center gap-2"
                    >
                      <TimerReset size={14} /> {t('notifications_open_state_history', 'Open State History')}
                    </button>
                    <button
                      data-testid={`issue-capture-state-history-${alert.id}`}
                      onClick={() => openStateHistoryForIssue(alert, { capture: true })}
                      disabled={stateHistoryActionKey === `${alert.id}:capture`}
                      className={`px-4 py-1.5 text-xs font-bold rounded transition-colors flex items-center gap-2 ${
                        stateHistoryActionKey === `${alert.id}:capture`
                          ? 'bg-gray-200 dark:bg-gray-800 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                          : 'bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-gray-100 text-white dark:text-slate-900'
                      }`}
                    >
                      <Camera size={14} />
                      {stateHistoryActionKey === `${alert.id}:capture`
                        ? t('notifications_state_history_capturing', 'Capturing...')
                        : t('notifications_capture_state_history', 'Capture Snapshot')}
                    </button>
                    {alert.device_id && (
                      <>
                        <button
                          onClick={() => openDevice(alert.device_id)}
                          className="px-4 py-1.5 bg-gray-100 dark:bg-[#0e1012] hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors"
                        >
                          {t('notifications_investigate_device', 'Investigate Device')}
                        </button>
                        <button
                          onClick={() => openObservability(alert.device_id, alert.site_id)}
                          className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-blue-50 dark:hover:bg-blue-900/20 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors"
                        >
                          {t('notifications_open_observability', 'Open Observability')}
                        </button>
                        <button
                          onClick={() => openGrafana(buildGrafanaFleetHealthUrl({ deviceId: alert.device_id, siteId: alert.site_id }))}
                          className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-violet-50 dark:hover:bg-violet-900/20 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors"
                        >
                          {t('notifications_open_grafana', 'Open Grafana')}
                        </button>
                        <button
                          onClick={() => openGrafana(buildGrafanaAlertingCenterUrl({ deviceId: alert.device_id, siteId: alert.site_id }))}
                          className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-amber-50 dark:hover:bg-amber-900/20 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors"
                        >
                          {t('notifications_alert_dashboard', 'Alert Dashboard')}
                        </button>
                        {alert.site_id && (
                          <button
                            onClick={() => openTopology(alert.site_id)}
                            className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-emerald-50 dark:hover:bg-emerald-900/20 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors flex items-center gap-2"
                          >
                            <MapIcon size={14} /> {t('notifications_open_topology', 'Open Topology')}
                          </button>
                        )}
                      </>
                    )}
                    <button
                      onClick={() => handleToggleServiceImpact(alert)}
                      className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors"
                    >
                      {isServiceImpactExpanded
                        ? t('notifications_service_impact_hide', 'Hide Service Impact')
                        : t('notifications_service_impact_open', 'Open Service Impact')}
                    </button>
                    <button
                      onClick={() => handleToggleSop(alert)}
                      className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors"
                    >
                      {isSopExpanded
                        ? t('notifications_sop_hide', 'Hide SOP')
                        : t('notifications_sop_open', 'Open SOP')}
                    </button>
                    <button
                      onClick={() => handleCreateKnowledge(alert)}
                      disabled={knowledgeSavingKey === `${alert.id}:knowledge`}
                      className={`px-4 py-1.5 text-xs font-bold rounded transition-colors ${
                        knowledgeSavingKey === `${alert.id}:knowledge`
                          ? 'bg-gray-200 dark:bg-gray-800 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                          : 'bg-purple-700 hover:bg-purple-600 text-white'
                      }`}
                    >
                      {knowledgeSavingKey === `${alert.id}:knowledge`
                        ? t('notifications_knowledge_creating', 'Saving...')
                        : t('notifications_knowledge_create', 'Save Known Error')}
                    </button>
                    <button
                      onClick={() => handleToggleKnowledge(alert)}
                      className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors"
                    >
                      {isKnowledgeExpanded
                        ? t('notifications_knowledge_hide', 'Hide Known Errors')
                        : t('notifications_knowledge_open', 'Open Known Errors')}
                    </button>
                    <button
                      onClick={() => handleCreateAction(alert)}
                      disabled={actionSavingKey === `${alert.id}:create`}
                      className={`px-4 py-1.5 text-xs font-bold rounded transition-colors ${
                        actionSavingKey === `${alert.id}:create`
                          ? 'bg-gray-200 dark:bg-gray-800 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                          : 'bg-slate-700 hover:bg-slate-600 text-white'
                      }`}
                    >
                      {actionSavingKey === `${alert.id}:create`
                        ? t('notifications_action_creating', 'Creating...')
                        : t('notifications_action_create', 'Create Action')}
                    </button>
                    <button
                      onClick={() => handleToggleActions(alert)}
                      className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors"
                    >
                      {isActionExpanded
                        ? t('notifications_action_hide', 'Hide Actions')
                        : t('notifications_action_open', 'Open Actions')}
                    </button>
                    <button
                      onClick={() => handlePreviewAutomation(alert)}
                      className="px-4 py-1.5 bg-white dark:bg-[#0e1012] hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors"
                    >
                      {isAutomationExpanded
                        ? t('notifications_hide_automation', 'Hide Automation')
                        : t('notifications_preview_automation', 'Preview Automation')}
                    </button>
                    <button
                      onClick={() => handleRunAutomation(alert)}
                      disabled={!automationSummary?.can_run || isAutomationRunning}
                      title={!automationSummary?.can_run ? (automationSummary?.next_action || '') : undefined}
                      className={`px-4 py-1.5 text-xs font-bold rounded transition-colors ${
                        automationSummary?.can_run && !isAutomationRunning
                          ? 'bg-violet-600 hover:bg-violet-500 text-white'
                          : 'bg-gray-200 dark:bg-gray-800 text-gray-500 dark:text-gray-500 cursor-not-allowed'
                      }`}
                    >
                      {isAutomationRunning
                        ? t('notifications_running_automation', 'Running...')
                        : t('notifications_run_automation', 'Run Automation')}
                    </button>
                  </div>

                  {isServiceImpactExpanded && (
                    <div
                      data-testid={`issue-service-impact-panel-${alert.id}`}
                      className="mt-4 rounded-xl border border-cyan-200 dark:border-cyan-900/40 bg-cyan-50/70 dark:bg-cyan-950/10 p-4"
                    >
                      {isServiceImpactLoading && !serviceImpactPayload ? (
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {t('notifications_service_impact_loading', 'Loading service impact...')}
                        </div>
                      ) : serviceImpactPayload && Array.isArray(serviceImpactPayload.groups) && serviceImpactPayload.groups.length > 0 ? (
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                              {t('notifications_service_impact_panel_title', 'Mapped service groups for this alert')}
                            </div>
                            <button
                              type="button"
                              onClick={openServiceGroups}
                              className="px-3 py-1.5 rounded-lg bg-white dark:bg-[#0e1012] hover:bg-gray-100 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-700 dark:text-gray-300"
                            >
                              {t('notifications_service_impact_open_groups', 'Open Service Groups')}
                            </button>
                          </div>
                          {serviceImpactPayload.groups.map((group) => (
                            <div
                              key={`${alert.id}-svc-${group.id}`}
                              className="rounded-lg border border-cyan-200 dark:border-cyan-900/40 bg-white dark:bg-[#14171a] p-3"
                            >
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-[#0e1012] text-[10px] text-gray-600 dark:text-gray-300">
                                      {t(`service_groups_criticality_${String(group.criticality || 'standard').toLowerCase()}`, group.criticality)}
                                    </span>
                                    <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                                      {group.name}
                                    </span>
                                  </div>
                                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                    {t('notifications_service_impact_owner_fmt', 'Owner team {value}').replace('{value}', group.owner_team || '-')}
                                  </div>
                                </div>
                                <div className="flex flex-col items-end gap-1 text-[11px] font-medium">
                                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 ${serviceHealthBadgeClass(group.health_status)}`}>
                                    {t('service_groups_health_score', 'Health Score')}: {Number(group.health_score || 0)}
                                  </span>
                                  <span className="text-cyan-700 dark:text-cyan-300">
                                    {t('notifications_service_impact_matched_members_fmt', 'Matched assets {value}')
                                      .replace('{value}', String(Number(group.matched_member_count || 0)))}
                                  </span>
                                </div>
                              </div>
                              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                                <span>{t('service_groups_health_active_issues', 'Active issues')}: {Number(group.active_issue_count || 0)}</span>
                                <span>{t('service_groups_health_offline_devices', 'Offline devices')}: {Number(group.offline_device_count || 0)}</span>
                                <span>{t('service_groups_health_discovered_only', 'Discovered only')}: {Number(group.discovered_only_device_count || 0)}</span>
                              </div>
                              <div className="mt-3 flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  data-testid={`issue-service-impact-open-review-${alert.id}-${group.id}`}
                                  onClick={() => openFocusedServiceReview(group.id, group.name)}
                                  className="px-3 py-1.5 rounded-lg bg-violet-50 dark:bg-violet-950/20 hover:bg-violet-100 dark:hover:bg-violet-950/30 border border-violet-200 dark:border-violet-900/50 text-xs font-medium text-violet-700 dark:text-violet-200"
                                >
                                  {t('notifications_service_impact_open_review', 'Open service review')}
                                </button>
                                {(Array.isArray(group.matched_members) ? group.matched_members : []).map((member) => (
                                  <span
                                    key={`${group.id}-${member.member_id}`}
                                    className="inline-flex items-center gap-1 px-2 py-1 rounded-full border border-cyan-200 dark:border-cyan-900/40 bg-cyan-50 dark:bg-cyan-950/20 text-[11px] text-cyan-700 dark:text-cyan-300"
                                  >
                                    {member.display_name}
                                    {member.role_label ? ` · ${member.role_label}` : ''}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {t('notifications_service_impact_empty', 'No service group is directly mapped to this alert yet.')}
                        </div>
                      )}
                    </div>
                  )}

                  {isAutomationExpanded && (
                    <div
                      data-testid={`issue-automation-panel-${alert.id}`}
                      className="mt-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white/80 dark:bg-[#0f1113] p-4"
                    >
                      {isAutomationLoading && !automationDetail ? (
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {t('notifications_loading_automation', 'Loading automation preview...')}
                        </div>
                      ) : automationDetail ? (
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold ${automationBadgeClass(automationDetail?.primary_status)}`}>
                              {automationLabel(automationDetail?.primary_status)}
                            </span>
                            {automationDetail?.primary_action?.action_title && (
                              <span className="text-xs text-gray-600 dark:text-gray-300">
                                {automationDetail.primary_action.action_title}
                              </span>
                            )}
                          </div>

                          <div className="text-xs text-gray-500 dark:text-gray-400">
                            {automationDetail?.next_action}
                          </div>

                          {!!automationDetail?.snapshot?.issue?.match_paths?.length && (
                            <div className="flex flex-wrap gap-2">
                              {automationDetail.snapshot.issue.match_paths.slice(0, 8).map((path) => (
                                <span
                                  key={path}
                                  className="inline-flex items-center px-2 py-1 rounded border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-[#14171a] text-[11px] text-gray-600 dark:text-gray-300 font-mono"
                                >
                                  {path}
                                </span>
                              ))}
                            </div>
                          )}

                          {!!automationDetail?.decisions?.length && (
                            <div className="space-y-2">
                              {automationDetail.decisions.slice(0, 4).map((decision) => (
                                <div
                                  key={`${decision.rule_id}-${decision.status}`}
                                  className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#14171a] p-3"
                                >
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold ${automationBadgeClass(decision?.status === 'ready' ? 'auto_ready' : decision?.status === 'approval_required' ? 'approval_required' : decision?.status === 'auto_execute_disabled' ? 'auto_execute_disabled' : 'blocked')}`}>
                                      {decisionLabel(decision?.status)}
                                    </span>
                                    <span className="text-xs font-semibold text-gray-700 dark:text-gray-200">
                                      {decision?.rule_name}
                                    </span>
                                    <span className="text-[11px] text-gray-500 dark:text-gray-400 font-mono">
                                      {decision?.action_type}
                                    </span>
                                  </div>
                                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                    {decision?.next_action}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}

                          {runResult && (
                            <div
                              data-testid={`issue-automation-run-result-${alert.id}`}
                              className="rounded-lg border border-violet-200 dark:border-violet-500/30 bg-violet-50 dark:bg-violet-500/10 p-3 text-xs text-violet-700 dark:text-violet-200"
                            >
                              {t('notifications_automation_last_run', 'Last run')}
                              {`: ${t('notifications_automation_executed', 'executed')} ${Number(runResult?.executed || 0)}, ${t('notifications_automation_blocked_short', 'blocked')} ${Number(runResult?.blocked || 0)}`}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {t('notifications_no_automation_preview', 'No automation preview available')}
                        </div>
                      )}
                    </div>
                  )}

                  {isActionExpanded && (
                    <div
                      data-testid={`issue-actions-panel-${alert.id}`}
                      className="mt-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white/80 dark:bg-[#0f1113] p-4"
                    >
                      <div className="space-y-4">
                        <div>
                          {isActionLoading ? (
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                              {t('notifications_action_loading', 'Loading actions...')}
                            </div>
                          ) : actionRows.length === 0 ? (
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                              {t('notifications_action_empty', 'No actions are linked to this alert yet.')}
                            </div>
                          ) : (
                            <div className="space-y-3">
                          {actionRows.map((action) => {
                            const canInvestigate = String(action?.status || '').toLowerCase() === 'open';
                            const canMitigate = ['open', 'investigating'].includes(String(action?.status || '').toLowerCase());
                            const canResolve = ['open', 'investigating', 'mitigated'].includes(String(action?.status || '').toLowerCase());
                            return (
                              <div
                                key={action.id}
                                className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#14171a] p-3"
                              >
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div>
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold ${actionStatusBadgeClass(action?.status)}`}>
                                        {actionStatusLabel(action?.status)}
                                      </span>
                                      <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                                        {action.title}
                                      </span>
                                    </div>
                                    {action.summary && (
                                      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                        {action.summary}
                                      </p>
                                    )}
                                  </div>
                                  <div className="text-[11px] text-gray-500 dark:text-gray-400">
                                    {formatTimeAgo(action.updated_at || action.created_at)}
                                  </div>
                                </div>
                                <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-gray-600 dark:text-gray-300">
                                  <div>
                                    <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_action_owner', 'Owner')}</div>
                                    <div>{action.assignee_name || '-'}</div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_action_created_by', 'Created By')}</div>
                                    <div>{action.created_by || '-'}</div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_action_latest_note', 'Latest Note')}</div>
                                    <div>{action.latest_note || '-'}</div>
                                  </div>
                                </div>
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {canInvestigate && (
                                    <button
                                      type="button"
                                      onClick={() => handleUpdateAction(alert, action, 'investigating')}
                                      disabled={actionSavingKey === `${action.id}:investigating`}
                                      className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium disabled:opacity-50"
                                    >
                                      {actionSavingKey === `${action.id}:investigating`
                                        ? t('common_saving', 'Saving...')
                                        : t('notifications_action_start_investigation', 'Start Investigation')}
                                    </button>
                                  )}
                                  {canMitigate && (
                                    <button
                                      type="button"
                                      onClick={() => handleUpdateAction(alert, action, 'mitigated')}
                                      disabled={actionSavingKey === `${action.id}:mitigated`}
                                      className="px-3 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-500 text-white text-xs font-medium disabled:opacity-50"
                                    >
                                      {actionSavingKey === `${action.id}:mitigated`
                                        ? t('common_saving', 'Saving...')
                                        : t('notifications_action_mark_mitigated', 'Mark Mitigated')}
                                    </button>
                                  )}
                                  {canResolve && (
                                    <button
                                      type="button"
                                      onClick={() => handleUpdateAction(alert, action, 'resolved')}
                                      disabled={actionSavingKey === `${action.id}:resolved`}
                                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium disabled:opacity-50"
                                    >
                                      {actionSavingKey === `${action.id}:resolved`
                                        ? t('common_saving', 'Saving...')
                                        : t('notifications_action_resolve', 'Resolve Action')}
                                    </button>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                            </div>
                          )}
                        </div>

                        <div className="rounded-xl border border-indigo-200 dark:border-indigo-900/40 bg-indigo-50/70 dark:bg-indigo-950/10 p-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <div className="text-[11px] font-black uppercase tracking-[0.22em] text-indigo-600 dark:text-indigo-300">
                                {t('notifications_approval_context_title', 'Approval Context')}
                              </div>
                              <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                                {t('notifications_approval_context_desc', 'Keep rollback readiness and evidence status close to the active action trail.')}
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={() => openApprovalCenter(approvalPayload?.summary?.latest_approval_id || approvalSummary?.latest_approval_id)}
                              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-medium text-white"
                            >
                              <ExternalLink size={14} />
                              {t('notifications_approval_context_open_center', 'Open Approval Center')}
                            </button>
                          </div>

                          <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
                            <div className="rounded-lg border border-indigo-200/70 dark:border-indigo-900/40 bg-white/80 dark:bg-[#111827] p-3">
                              <div className="text-lg font-bold text-gray-900 dark:text-gray-100">{Number(approvalSummary?.total || approvalPayload?.summary?.total || 0)}</div>
                              <div className="text-[10px] uppercase tracking-wide text-gray-500">{t('notifications_approval_context_total', 'Linked Approvals')}</div>
                            </div>
                            <div className="rounded-lg border border-amber-200/70 dark:border-amber-900/40 bg-white/80 dark:bg-[#111827] p-3">
                              <div className="text-lg font-bold text-amber-700 dark:text-amber-300">{Number(approvalSummary?.pending || approvalPayload?.summary?.pending || 0)}</div>
                              <div className="text-[10px] uppercase tracking-wide text-gray-500">{t('notifications_approval_context_pending', 'Pending')}</div>
                            </div>
                            <div className="rounded-lg border border-emerald-200/70 dark:border-emerald-900/40 bg-white/80 dark:bg-[#111827] p-3">
                              <div className="text-lg font-bold text-emerald-700 dark:text-emerald-300">{Number(approvalSummary?.evidence_ready_count || approvalPayload?.summary?.evidence_ready_count || 0)}</div>
                              <div className="text-[10px] uppercase tracking-wide text-gray-500">{t('notifications_approval_context_evidence', 'Evidence Ready')}</div>
                            </div>
                            <div className="rounded-lg border border-rose-200/70 dark:border-rose-900/40 bg-white/80 dark:bg-[#111827] p-3">
                              <div className="text-lg font-bold text-rose-700 dark:text-rose-300">{Number(approvalSummary?.rollback_tracked_count || approvalPayload?.summary?.rollback_tracked_count || 0)}</div>
                              <div className="text-[10px] uppercase tracking-wide text-gray-500">{t('notifications_approval_context_rollback', 'Rollback Tracked')}</div>
                            </div>
                          </div>

                          {isApprovalContextLoading && !approvalPayload ? (
                            <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
                              {t('notifications_approval_context_loading', 'Loading approval context...')}
                            </div>
                          ) : approvalPayload?.items?.length ? (
                            <div className="mt-4 space-y-3">
                              {approvalPayload.items.map((item) => (
                                <div
                                  key={item.id}
                                  className="rounded-lg border border-indigo-200/70 dark:border-indigo-900/40 bg-white/80 dark:bg-[#111827] p-3"
                                >
                                  <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div>
                                      <div className="flex flex-wrap items-center gap-2">
                                        <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold ${approvalStatusBadgeClass(item.status)}`}>
                                          {approvalStatusLabel(item.status)}
                                        </span>
                                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#14171a] text-[10px] font-semibold text-gray-600 dark:text-gray-300">
                                          {item.request_type_label}
                                        </span>
                                        <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">{item.title}</span>
                                      </div>
                                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                        {item.scope_summary || '-'}
                                      </div>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() => openApprovalCenter(item.id)}
                                      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-indigo-200 dark:border-indigo-800/60 bg-indigo-50 dark:bg-indigo-500/10 text-xs font-medium text-indigo-700 dark:text-indigo-200 hover:bg-indigo-100 dark:hover:bg-indigo-500/20"
                                    >
                                      <ExternalLink size={13} />
                                      {t('notifications_approval_context_open_request', 'Open Request')}
                                    </button>
                                  </div>

                                  <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-gray-600 dark:text-gray-300">
                                    <div>
                                      <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_approval_context_execution', 'Execution')}</div>
                                      <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold ${getOperationalStatusBadgeClass(item.execution_status || item.status)}`}>
                                        {approvalExecutionStatusLabel(item.execution_status || item.status)}
                                      </div>
                                    </div>
                                    <div>
                                      <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_approval_context_requester', 'Requester')}</div>
                                      <div>{item.requester_name || '-'}</div>
                                    </div>
                                    <div>
                                      <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_approval_context_approver', 'Approver')}</div>
                                      <div>{item.approver_name || '-'}</div>
                                    </div>
                                  </div>

                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {item.has_evidence && (
                                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800/60 bg-emerald-50 dark:bg-emerald-500/10 text-[10px] font-semibold text-emerald-700 dark:text-emerald-300">
                                        {t('notifications_approval_context_evidence_ready_badge', 'Evidence Ready')}
                                      </span>
                                    )}
                                    {item.rollback_on_failure && (
                                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-rose-200 dark:border-rose-800/60 bg-rose-50 dark:bg-rose-500/10 text-[10px] font-semibold text-rose-700 dark:text-rose-300">
                                        {t('notifications_approval_context_rollback_policy', 'Rollback on Failure')}
                                      </span>
                                    )}
                                    {item.post_check_failed && (
                                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-amber-200 dark:border-amber-800/60 bg-amber-50 dark:bg-amber-500/10 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
                                        {t('notifications_approval_context_postcheck_failed', 'Post-check Failed')}
                                      </span>
                                    )}
                                    {item.rollback_attempted && (
                                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold ${item.rollback_success ? 'border-emerald-200 dark:border-emerald-800/60 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border-rose-200 dark:border-rose-800/60 bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300'}`}>
                                        {item.rollback_success
                                          ? t('notifications_approval_context_rollback_success', 'Rollback Success')
                                          : t('notifications_approval_context_rollback_attempted', 'Rollback Attempted')}
                                      </span>
                                    )}
                                  </div>
                                  {item.top_cause && (
                                    <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                                      {t('notifications_approval_context_top_cause_fmt', 'Top cause: {value}').replace('{value}', String(item.top_cause || '').replace(/_/g, ' '))}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
                              {t('notifications_approval_context_empty', 'No approval requests are linked to this alert yet.')}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {isSopExpanded && (
                    <div className="mt-4 rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50/70 dark:bg-emerald-950/10 p-4">
                      {isSopLoading && !sopPayload ? (
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {t('notifications_sop_loading', 'Loading SOP guidance...')}
                        </div>
                      ) : sopPayload ? (
                        <div className="space-y-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="space-y-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold ${sopReadinessBadgeClass(sopPayload?.readiness_status)}`}>
                                  {sopReadinessLabel(sopPayload?.readiness_status)}
                                </span>
                                <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                                  {sopPayload?.top_known_error_title || sopSummary?.primary_title || alert.title}
                                </span>
                              </div>
                              <p className="text-xs text-gray-600 dark:text-gray-300">
                                {sopPayload?.summary}
                              </p>
                            </div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">
                              {t('notifications_sop_owner_fmt', 'Owner {value}')
                                .replace('{value}', sopPayload?.recommended_owner || '-')}
                            </div>
                          </div>

                          {!!sopPayload?.reasons?.length && (
                            <div className="flex flex-wrap gap-2">
                              {sopPayload.reasons.map((reason) => (
                                <span
                                  key={`${alert.id}-sop-${reason}`}
                                  className="inline-flex items-center px-2 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#0e1012] text-[10px] text-gray-600 dark:text-gray-300"
                                >
                                  {t(`notifications_sop_reason_${reason}`, reason)}
                                </span>
                              ))}
                            </div>
                          )}

                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                            <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-white dark:bg-[#14171a] p-3">
                              <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_sop_step_count', 'Steps')}</div>
                              <div className="mt-1 font-semibold text-gray-800 dark:text-gray-100">{Number(sopPayload?.steps?.length || 0)}</div>
                            </div>
                            <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-white dark:bg-[#14171a] p-3">
                              <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_sop_active_actions', 'Active Actions')}</div>
                              <div className="mt-1 font-semibold text-gray-800 dark:text-gray-100">{Number(sopPayload?.active_action_count || 0)}</div>
                            </div>
                            <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-white dark:bg-[#14171a] p-3">
                              <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_sop_known_errors', 'Matched Known Errors')}</div>
                              <div className="mt-1 font-semibold text-gray-800 dark:text-gray-100">{Number(sopPayload?.matched_known_error_count || 0)}</div>
                            </div>
                          </div>

                          <div className="space-y-3">
                            {(Array.isArray(sopPayload?.steps) ? sopPayload.steps : []).map((step, index) => (
                              <div
                                key={`${alert.id}-sop-step-${step.id}`}
                                className="rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-white dark:bg-[#14171a] p-3"
                              >
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div>
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-emerald-600 text-white text-[11px] font-bold">
                                        {index + 1}
                                      </span>
                                      <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                                        {step.title}
                                      </span>
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-[#0e1012] text-[10px] text-gray-600 dark:text-gray-300">
                                        {t(`notifications_sop_source_${step.source_type}`, step.source_type)}
                                      </span>
                                    </div>
                                    <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">
                                      {step.description}
                                    </p>
                                  </div>
                                  <div className="text-right text-[11px] text-gray-500 dark:text-gray-400">
                                    <div>{t(`notifications_sop_status_${step.status_hint}`, step.status_hint)}</div>
                                    {step.action_label && (
                                      <div className="mt-1 font-medium text-emerald-700 dark:text-emerald-300">
                                        {step.action_label}
                                      </div>
                                    )}
                                  </div>
                                </div>
                                {step.source_title && (
                                  <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
                                    {t('notifications_sop_source_title', 'Source')}: {step.source_title}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {t('notifications_sop_empty', 'No SOP guidance is available for this alert yet.')}
                        </div>
                      )}
                    </div>
                  )}

                  {isKnowledgeExpanded && (
                    <div className="mt-4 rounded-xl border border-purple-200 dark:border-purple-900/40 bg-purple-50/70 dark:bg-purple-950/10 p-4">
                      {isKnowledgeLoading ? (
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {t('notifications_knowledge_loading', 'Loading known errors...')}
                        </div>
                      ) : knowledgeRows.length === 0 ? (
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {t('notifications_knowledge_empty', 'No reusable known error entries were matched for this alert yet.')}
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {knowledgeRows.map((entry) => (
                            <div
                              key={entry.id}
                              className="rounded-lg border border-purple-200 dark:border-purple-900/40 bg-white dark:bg-[#14171a] p-3"
                            >
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-purple-200 dark:border-purple-800/50 bg-purple-50 dark:bg-purple-500/10 text-[11px] font-semibold text-purple-700 dark:text-purple-300">
                                      {t('notifications_knowledge_score_fmt', 'Match {value}')
                                        .replace('{value}', String(Number(entry.match_score || 0).toFixed(1)))}
                                    </span>
                                    <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                                      {entry.title}
                                    </span>
                                  </div>
                                  <div className="mt-1 flex flex-wrap gap-2">
                                    {(entry.match_reasons || []).map((reason) => (
                                      <span
                                        key={`${entry.id}-${reason}`}
                                        className="inline-flex items-center px-2 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-[#0e1012] text-[10px] text-gray-600 dark:text-gray-300"
                                      >
                                        {t(`notifications_knowledge_reason_${reason}`, reason)}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                                <div className="text-[11px] text-gray-500 dark:text-gray-400">
                                  {entry.category || '-'}
                                </div>
                              </div>
                              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-gray-600 dark:text-gray-300">
                                <div>
                                  <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_knowledge_root_cause', 'Root Cause')}</div>
                                  <div>{entry.root_cause || '-'}</div>
                                </div>
                                <div>
                                  <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_knowledge_workaround', 'Workaround')}</div>
                                  <div>{entry.workaround || '-'}</div>
                                </div>
                                <div>
                                  <div className="text-[10px] uppercase tracking-wide text-gray-400">{t('notifications_knowledge_sop', 'SOP')}</div>
                                  <div>{entry.sop_summary || '-'}</div>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l-xl ${
                  alert.severity === 'critical'
                    ? 'bg-red-500'
                    : alert.severity === 'warning'
                      ? 'bg-orange-500'
                      : 'bg-blue-500'
                }`}
                />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default NotificationsPage;
