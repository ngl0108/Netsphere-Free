import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Download, ExternalLink, FileCheck, FileText, Globe, Package, RefreshCw, ShieldAlert, ShieldCheck, TimerReset, Wrench } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { ApprovalService, ComplianceService, IssueService, OpsService, PreventiveCheckService, ServiceGroupService, StateHistoryService } from '../api/services';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';
import {
  getOperationsPressureGuidance,
  getOperationsPressureLabel,
  getOperationsPressureLevel,
  compareServiceImpactAlerts,
  getServicePriorityNextAction,
  getServicePressureIndex,
  getServiceReviewAverageHealth,
  recommendServiceWorkspace,
  summarizeServiceReviewPosture,
  summarizeServiceReviewQueue,
} from '../utils/serviceOperations';

const PANEL_CLASS = 'rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] shadow-sm';

const parseFilename = (contentDisposition) => {
  const value = String(contentDisposition || '');
  const match = value.match(/filename="?([^"]+)"?/i);
  return match ? match[1] : null;
};

const downloadBlob = (blob, filename) => {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || 'download';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
};

const formatTs = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('ko-KR', { hour12: false });
};

const toneForCriticality = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'high') return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-300';
  if (normalized === 'elevated') return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
  return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300';
};

const statusTone = (run) => {
  const summary = run?.summary || {};
  if (Number(summary.critical_devices || 0) > 0) return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-300';
  if (Number(summary.warning_devices || 0) > 0) return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
  if (Number(summary.info_devices || 0) > 0) return 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/50 dark:bg-sky-500/10 dark:text-sky-300';
  return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300';
};

const approvalTone = (status, executionStatus) => {
  const normalized = String(executionStatus || status || '').trim().toLowerCase();
  if (normalized === 'rejected' || normalized === 'failed' || normalized === 'dispatch_failed') {
    return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-300';
  }
  if (normalized === 'pending' || normalized === 'dispatching' || normalized === 'queued') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
  }
  if (normalized === 'approved' || normalized === 'executed') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300';
  }
  return 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-500/10 dark:text-slate-300';
};

const releaseEvidenceTone = (status) => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'critical' || normalized === 'failed' || normalized === 'unhealthy') {
    return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-300';
  }
  if (normalized === 'warning' || normalized === 'stale') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
  }
  if (normalized === 'healthy' || normalized === 'accepted' || normalized === 'pass') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300';
  }
  return 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-500/10 dark:text-slate-300';
};

const severityTone = (severity) => {
  const normalized = String(severity || '').trim().toLowerCase();
  if (normalized === 'critical') {
    return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-300';
  }
  if (normalized === 'warning') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
  }
  return 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/50 dark:bg-sky-500/10 dark:text-sky-300';
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

const actionStatusTone = (status) => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'resolved') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300';
  }
  if (normalized === 'mitigated') {
    return 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/50 dark:bg-sky-500/10 dark:text-sky-300';
  }
  if (normalized === 'investigating') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
  }
  return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-300';
};

const sopTone = (status) => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'ready') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300';
  }
  return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
};

const summarizeApprovals = (rows = []) => {
  const summary = {
    total: 0,
    pending: 0,
    approved: 0,
    rejected: 0,
    evidenceReady: 0,
    rollbackTracked: 0,
  };
  for (const row of rows) {
    summary.total += 1;
    const status = String(row?.status || '').trim().toLowerCase();
    if (status === 'pending') summary.pending += 1;
    if (status === 'approved') summary.approved += 1;
    if (status === 'rejected') summary.rejected += 1;
    const payload = row?.payload && typeof row.payload === 'object' ? row.payload : {};
    if (payload.execution_result || payload.execution_trace) summary.evidenceReady += 1;
    if (payload.rollback_on_failure || payload.execution_result?.rollback_attempted) summary.rollbackTracked += 1;
  }
  return summary;
};

const MetricCard = ({ title, value, hint, icon: Icon }) => (
  <div className={`${PANEL_CLASS} p-4`}>
    <div className="flex items-center justify-between gap-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{title}</div>
      <Icon size={18} className="text-blue-500" />
    </div>
    <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{value}</div>
    {hint ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</div> : null}
  </div>
);

const OperationsReportsPage = () => {
  useLocaleRerender();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { isAtLeast } = useAuth();
  const { toast } = useToast();
  const canOperate = isAtLeast('operator');
  const canAdmin = isAtLeast('admin');
  const showInlineFocusedGroupCard = searchParams.get('inlineFocusCard') === '1';
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState({
    operatorPackage: false,
    operationsReviewBundle: false,
    releaseBundle: false,
    complianceExport: false,
    approvalEvidenceId: null,
  });
  const [summary, setSummary] = useState(null);
  const [runs, setRuns] = useState([]);
  const [groups, setGroups] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [releaseEvidence, setReleaseEvidence] = useState(null);
  const [activeIssues, setActiveIssues] = useState([]);
  const [stateHistoryReview, setStateHistoryReview] = useState(null);
  const [refreshingEvidence, setRefreshingEvidence] = useState(false);
  const [capturingStateHistory, setCapturingStateHistory] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [summaryRes, runsRes, groupsRes, approvalsRes, releaseEvidenceRes, issuesRes, stateCurrentRes, stateListRes] = await Promise.all([
        PreventiveCheckService.getSummary(),
        PreventiveCheckService.listRuns({ limit: 6 }),
        ServiceGroupService.list(),
        ApprovalService.getRequests({ limit: 6 }),
        OpsService.getReleaseEvidence(),
        IssueService.getActiveIssues(),
        StateHistoryService.getCurrent().catch(() => null),
        StateHistoryService.listSnapshots({ limit: 12 }).catch(() => null),
      ]);
      setSummary(summaryRes?.data || null);
      setRuns(Array.isArray(runsRes?.data) ? runsRes.data : []);
      setGroups(Array.isArray(groupsRes?.data) ? groupsRes.data : []);
      setApprovals(Array.isArray(approvalsRes?.data) ? approvalsRes.data : []);
      setReleaseEvidence(releaseEvidenceRes?.data || null);
      setActiveIssues(Array.isArray(issuesRes?.data) ? issuesRes.data : []);
      const currentSnapshot = stateCurrentRes?.data || null;
      const snapshotRows = Array.isArray(stateListRes?.data) ? stateListRes.data : [];
      const latestSnapshotId = Number(snapshotRows?.[0]?.event_log_id || 0);
      let latestCompare = null;
      if (latestSnapshotId > 0) {
        const compareRes = await StateHistoryService.compareSnapshot(latestSnapshotId).catch(() => null);
        latestCompare = compareRes?.data || null;
      }
      setStateHistoryReview({
        current: currentSnapshot,
        snapshots: snapshotRows,
        latestSnapshot: snapshotRows?.[0] || null,
        latestCompare,
      });
    } catch (error) {
      toast.error(`${t('operations_reports_load_failed', 'Failed to load operations reports')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, []);

  const stateHistorySummary = useMemo(() => {
    const rows = Array.isArray(stateHistoryReview?.snapshots) ? stateHistoryReview.snapshots : [];
    const latestSnapshot = stateHistoryReview?.latestSnapshot || rows?.[0] || null;
    const latestCompare = stateHistoryReview?.latestCompare || null;
    const latestAgeHours = latestSnapshot?.generated_at
      ? Math.max(0, (Date.now() - new Date(latestSnapshot.generated_at).getTime()) / 3600000)
      : null;
    const hotspotRows = Array.isArray(latestCompare?.cards)
      ? latestCompare.cards.filter((row) => ['review', 'changed'].includes(String(row?.status || '').toLowerCase())).slice(0, 3)
      : [];
    return {
      snapshotCount: rows.length,
      latestSnapshot,
      latestCompare,
      latestAgeHours,
      hotspotRows,
    };
  }, [stateHistoryReview]);

  const focusedGroupId = Number(searchParams.get('focusGroupId') || 0);
  const focusedGroupName = String(searchParams.get('focusGroupName') || '').trim();
  const focusedGroup = useMemo(
    () => (Array.isArray(groups) ? groups.find((group) => Number(group?.id || 0) === focusedGroupId) || null : null),
    [groups, focusedGroupId],
  );
  const serviceSnapshotGroups = useMemo(() => {
    const rows = Array.isArray(groups) ? [...groups] : [];
    if (!focusedGroupId) return rows;
    rows.sort((left, right) => {
      const leftFocused = Number(left?.id || 0) === focusedGroupId ? 1 : 0;
      const rightFocused = Number(right?.id || 0) === focusedGroupId ? 1 : 0;
      return rightFocused - leftFocused;
    });
    return rows;
  }, [groups, focusedGroupId]);

  const reportMetrics = useMemo(() => {
    const recentRuns = Array.isArray(runs) ? runs : [];
    const latestRun = recentRuns[0] || null;
    const groupRows = Array.isArray(groups) ? groups : [];
    const highCriticalityCount = groupRows.filter((item) => String(item.criticality || '').toLowerCase() === 'high').length;
    const approvalSummary = summarizeApprovals(approvals);
    const gateSummary = releaseEvidence?.summary || {};
    const serviceAwareIssues = (activeIssues || []).filter((issue) => Number(issue?.service_impact_summary?.count || 0) > 0);
    return [
      {
        title: t('operations_reports_metric_templates', 'Preventive Templates'),
        value: Number(summary?.templates_total || 0),
        hint: t('operations_reports_metric_templates_hint', '{value} enabled').replace('{value}', String(summary?.enabled_templates || 0)),
        icon: FileCheck,
      },
      {
        title: t('operations_reports_metric_recent_runs', 'Recent Runs'),
        value: Number(summary?.recent_runs_total || 0),
        hint: latestRun ? formatTs(latestRun.finished_at || latestRun.started_at) : t('operations_reports_no_runs', 'No runs yet'),
        icon: ShieldCheck,
      },
      {
        title: t('operations_reports_metric_pending_approvals', 'Pending Approvals'),
        value: approvalSummary.pending,
        hint: t('operations_reports_metric_pending_approvals_hint', '{value} evidence-ready')
          .replace('{value}', String(approvalSummary.evidenceReady)),
        icon: ShieldAlert,
      },
      {
        title: t('operations_reports_metric_release_gates', 'Release Gates'),
        value: `${Number(gateSummary.accepted_gates || 0)} / ${Number(gateSummary.available_gates || gateSummary.total_gates || 0)}`,
        hint: t('operations_reports_metric_release_gates_hint', '{value} warnings')
          .replace('{value}', String(Array.isArray(gateSummary.warning_gates) ? gateSummary.warning_gates.length : 0)),
        icon: CheckCircle2,
      },
      {
        title: t('operations_reports_metric_service_issues', 'Service-Scoped Issues'),
        value: serviceAwareIssues.length,
        hint: t('operations_reports_metric_service_issues_hint', '{value} SOP-ready')
          .replace('{value}', String(serviceAwareIssues.filter((issue) => String(issue?.sop_summary?.readiness_status || '').toLowerCase() === 'ready').length)),
        icon: AlertTriangle,
      },
      {
        title: t('operations_reports_metric_service_groups', 'Service Groups'),
        value: groupRows.length,
        hint: t('operations_reports_metric_service_groups_hint', '{value} high-critical groups').replace('{value}', String(highCriticalityCount)),
        icon: Globe,
      },
      {
        title: t('operations_reports_metric_state_history', 'State History'),
        value: stateHistorySummary.snapshotCount,
        hint: t('operations_reports_metric_state_history_hint', '{value} review cards')
          .replace('{value}', String(Number(stateHistorySummary.latestCompare?.summary?.review_cards || 0))),
        icon: TimerReset,
      },
    ];
  }, [activeIssues, approvals, groups, releaseEvidence, runs, stateHistorySummary, summary]);
  const servicePriorityQueue = useMemo(() => {
    return summarizeServiceReviewQueue(groups, t);
  }, [groups]);
  const servicePriorityFocus = useMemo(() => {
    const topGroup = servicePriorityQueue[0];
    if (!topGroup) return null;
    return {
      ...topGroup,
      nextAction: getServicePriorityNextAction(topGroup, t),
    };
  }, [servicePriorityQueue]);
  const servicePriorityWorkspace = useMemo(
    () => recommendServiceWorkspace(servicePriorityFocus),
    [servicePriorityFocus],
  );
  const servicePriorityWorkspaceLabel = useMemo(() => t(
    `ops_workspace_${servicePriorityWorkspace.workspace}_title`,
    servicePriorityWorkspace.workspace === 'discover'
      ? 'Discover'
      : servicePriorityWorkspace.workspace === 'govern'
        ? 'Govern'
        : 'Observe',
  ), [servicePriorityWorkspace.workspace]);
  const serviceReviewPosture = useMemo(() => summarizeServiceReviewPosture(groups), [groups]);
  const serviceReviewAverageHealth = useMemo(() => {
    return getServiceReviewAverageHealth(serviceReviewPosture);
  }, [serviceReviewPosture]);
  const serviceReviewPressureIndex = useMemo(() => {
    return getServicePressureIndex(serviceReviewPosture);
  }, [serviceReviewPosture]);

  const releaseSections = useMemo(() => {
    const sections = releaseEvidence?.sections;
    if (!sections || typeof sections !== 'object') return [];
    return Object.values(sections)
      .filter((section) => section && typeof section === 'object')
      .slice(0, 5);
  }, [releaseEvidence]);

  const actionContinuity = useMemo(() => {
    const matchesFocusedGroup = (issue) => {
      if (!focusedGroupId) return true;
      const primaryGroupId = Number(issue?.service_impact_summary?.primary_group_id || 0);
      if (primaryGroupId > 0) return primaryGroupId === focusedGroupId;
      return String(issue?.service_impact_summary?.primary_name || '').trim() === String(focusedGroup?.name || '').trim();
    };
    const rows = [...(Array.isArray(activeIssues) ? activeIssues : [])]
      .filter((issue) => Number(issue?.service_impact_summary?.count || 0) > 0)
      .filter(matchesFocusedGroup)
      .sort(compareServiceImpactAlerts);
    const summary = {
      issuesInScope: rows.length,
      withActiveActions: rows.filter((issue) => Boolean(issue?.action_summary?.has_active)).length,
      withAssignee: rows.filter((issue) => String(issue?.action_summary?.latest_assignee_name || '').trim().length > 0).length,
      withKnowledge: rows.filter((issue) => Number(issue?.knowledge_summary?.recommendation_count || 0) > 0).length,
      withEvidenceReady: rows.filter((issue) => Number(issue?.approval_summary?.evidence_ready_count || 0) > 0).length,
      limitedContext: rows.filter((issue) => !issue?.action_summary?.has_active && Number(issue?.knowledge_summary?.recommendation_count || 0) <= 0).length,
    };
    return {
      rows: rows.slice(0, 5),
      summary,
    };
  }, [activeIssues, focusedGroup?.name, focusedGroupId]);
  const serviceIssueRows = actionContinuity.rows;
  const followUpAgenda = useMemo(() => {
    const items = actionContinuity.rows.map((issue) => {
      const actionSummary = issue?.action_summary || {};
      const knowledgeSummary = issue?.knowledge_summary || {};
      const sopSummary = issue?.sop_summary || {};
      const approvalSummary = issue?.approval_summary || {};
      let recommendedStep = 'review_and_handoff';
      let stepLabel = t('operations_reports_follow_up_step_handoff', 'Review the latest note and complete the operator handoff.');
      let priority = 'normal';
      if (Number(actionSummary.total || 0) <= 0) {
        recommendedStep = 'create_action';
        stepLabel = t('operations_reports_follow_up_step_create_action', 'Create an action and assign an operator before remediation continues.');
        priority = 'critical';
      } else if (!String(actionSummary.latest_assignee_name || '').trim()) {
        recommendedStep = 'assign_owner';
        stepLabel = t('operations_reports_follow_up_step_assign_owner', 'Assign an owner so the active action has a clear control point.');
        priority = 'elevated';
      } else if (Number(knowledgeSummary.recommendation_count || 0) <= 0) {
        recommendedStep = 'capture_knowledge';
        stepLabel = t('operations_reports_follow_up_step_capture_knowledge', 'Capture or link reusable operating knowledge before the next recurrence.');
        priority = 'elevated';
      } else if (Number(approvalSummary.total || 0) > 0 && Number(approvalSummary.evidence_ready_count || 0) <= 0) {
        recommendedStep = 'capture_evidence';
        stepLabel = t('operations_reports_follow_up_step_capture_evidence', 'Linked approvals exist, but evidence is not ready yet. Record evidence before handoff.');
        priority = 'elevated';
      }
      return {
        ...issue,
        recommendedStep,
        stepLabel,
        priority,
      };
    });
    return {
      items,
      summary: {
        total: items.length,
        needsAction: items.filter((item) => item.recommendedStep === 'create_action').length,
        needsOwner: items.filter((item) => item.recommendedStep === 'assign_owner').length,
        needsKnowledge: items.filter((item) => item.recommendedStep === 'capture_knowledge').length,
        needsEvidence: items.filter((item) => item.recommendedStep === 'capture_evidence').length,
        readyForHandoff: items.filter((item) => item.recommendedStep === 'review_and_handoff').length,
      },
    };
  }, [actionContinuity.rows]);

  const handleExportRun = async (runId, format) => {
    try {
      const response = await PreventiveCheckService.exportRun(runId, { format });
      const fallbackExt = format === 'pdf' ? 'pdf' : format === 'md' ? 'md' : 'csv';
      const filename = parseFilename(response?.headers?.['content-disposition']) || `preventive_check_run_${runId}.${fallbackExt}`;
      downloadBlob(response.data, filename);
    } catch (error) {
      toast.error(`${t('operations_reports_export_failed', 'Failed to export report')}: ${error?.response?.data?.detail || error.message}`);
    }
  };

  const runDownload = async ({ key, request, fallbackFilename, successMessage, errorMessage }) => {
    setDownloading((current) => ({ ...current, [key]: true }));
    try {
      const response = await request();
      const filename = parseFilename(response?.headers?.['content-disposition']) || fallbackFilename;
      downloadBlob(response?.data, filename);
      toast.success(successMessage);
    } catch (error) {
      toast.error(error?.response?.data?.detail || error?.message || errorMessage);
    } finally {
      setDownloading((current) => ({ ...current, [key]: false }));
    }
  };

  const handleDownloadApprovalEvidence = async (approvalId) => {
    setDownloading((current) => ({ ...current, approvalEvidenceId: approvalId }));
    try {
      const response = await ApprovalService.downloadEvidencePackage(approvalId);
      const filename = parseFilename(response?.headers?.['content-disposition']) || `approval_evidence_${approvalId}.zip`;
      downloadBlob(response?.data, filename);
      toast.success(t('operations_reports_approval_evidence_downloaded', 'Approval evidence package downloaded.'));
    } catch (error) {
      toast.error(`${t('operations_reports_approval_evidence_failed', 'Failed to download approval evidence package')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setDownloading((current) => ({ ...current, approvalEvidenceId: null }));
    }
  };

  const handleRefreshEvidence = async () => {
    if (!canOperate) return;
    setRefreshingEvidence(true);
    try {
      await OpsService.refreshReleaseEvidence({ profile: 'ci', include_synthetic: true });
      toast.success(t('operations_reports_release_refresh_started', 'Release evidence refresh started.'));
      await loadAll();
    } catch (error) {
      toast.error(`${t('operations_reports_release_refresh_failed', 'Failed to refresh release evidence')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setRefreshingEvidence(false);
    }
  };

  const handleCaptureStateHistory = async () => {
    if (!canOperate) return;
    setCapturingStateHistory(true);
    try {
      const response = await StateHistoryService.createSnapshot({});
      const created = response?.data || null;
      toast.success(t('operations_reports_state_history_capture_success', 'State history snapshot captured.'));
      await loadAll();
      const createdId = Number(created?.event_log_id || 0);
      if (createdId > 0) {
        navigate(`/state-history?focusSnapshotId=${encodeURIComponent(String(createdId))}`);
      }
    } catch (error) {
      toast.error(`${t('operations_reports_state_history_capture_failed', 'Failed to capture state history snapshot')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setCapturingStateHistory(false);
    }
  };

  const openIssueFlow = (issueId, options = {}) => {
    const params = new URLSearchParams();
    params.set('focusIssueId', String(issueId));
    if (focusedGroupId > 0) params.set('focusGroupId', String(focusedGroupId));
    if (options.openActions !== false) params.set('openActions', '1');
    if (options.openApproval !== false) params.set('openApproval', '1');
    if (options.openKnowledge !== false) params.set('openKnowledge', '1');
    if (options.openSop !== false) params.set('openSop', '1');
    if (options.openServiceImpact) params.set('openServiceImpact', '1');
    navigate(`/notifications?${params.toString()}`);
  };

  return (
    <div data-testid="operations-reports-page" className="space-y-6">
      <div className={`${PANEL_CLASS} p-6`}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-blue-700 dark:border-blue-900/60 dark:bg-blue-500/10 dark:text-blue-300">
              <FileText size={14} />
              {t('operations_reports_header_badge', 'Operations Reporting')}
            </div>
            <h1 className="mt-3 text-2xl font-black text-gray-900 dark:text-gray-100">
              {t('operations_reports_title', 'Operations Reports')}
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
              {t(
                'operations_reports_desc',
                'Collect preventive check results, service-group context, and operational evidence from one reporting surface. This is the fastest path to an operator handoff package or a weekly operating review.',
              )}
            </p>
          </div>
          <button
            onClick={() => void loadAll()}
            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2 text-sm font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5"
          >
            <RefreshCw size={16} />
            {t('common_refresh', 'Refresh')}
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        {reportMetrics.map((card) => (
          <MetricCard key={card.title} {...card} />
        ))}
      </div>

      <section className={`${PANEL_CLASS} p-5`} data-testid="operations-reports-service-priority-focus">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
              {t('operations_reports_service_priority_title', 'Service Priority Review')}
            </div>
            <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
              {t('operations_reports_service_priority_desc', 'Bring the most urgent service group to the top of the reporting view so operators can continue from reports into alerts and topology without losing context.')}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => navigate('/service-groups')}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
            >
              {t('operations_reports_open_service_groups', 'Open Service Groups')}
              <ExternalLink size={14} />
            </button>
            <button
              onClick={() => navigate('/notifications?serviceImpact=1')}
              className="inline-flex items-center gap-2 rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs font-bold text-cyan-700 hover:bg-cyan-100 dark:border-cyan-900/60 dark:bg-cyan-500/10 dark:text-cyan-300 dark:hover:bg-cyan-500/20"
            >
              {t('operations_reports_service_priority_open_notifications', 'Open service-aware alerts')}
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="operations-reports-service-posture">
          <div className="rounded-2xl border border-rose-200/70 bg-rose-50/80 p-4 dark:border-rose-900/40 dark:bg-rose-950/10">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-rose-700 dark:text-rose-300">{t('ops_home_service_posture_critical', 'Critical groups')}</div>
            <div className="mt-2 text-2xl font-black text-rose-700 dark:text-rose-200">{serviceReviewPosture.criticalGroups}</div>
          </div>
          <div className="rounded-2xl border border-amber-200/70 bg-amber-50/80 p-4 dark:border-amber-900/40 dark:bg-amber-950/10">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">{t('ops_home_service_posture_review', 'Review groups')}</div>
            <div className="mt-2 text-2xl font-black text-amber-700 dark:text-amber-200">{serviceReviewPosture.reviewGroups}</div>
          </div>
          <div className="rounded-2xl border border-violet-200/70 bg-violet-50/80 p-4 dark:border-violet-900/40 dark:bg-violet-950/10">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-violet-700 dark:text-violet-300">{t('ops_home_service_posture_discovered_only', 'Discovered-only pressure')}</div>
            <div className="mt-2 text-2xl font-black text-violet-700 dark:text-violet-200">{serviceReviewPosture.discoveredOnlyPressure}</div>
          </div>
          <div className="rounded-2xl border border-cyan-200/70 bg-cyan-50/80 p-4 dark:border-cyan-900/40 dark:bg-cyan-950/10">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-cyan-700 dark:text-cyan-300">{t('operations_reports_metric_service_issues', 'Service-Scoped Issues')}</div>
            <div className="mt-2 text-2xl font-black text-cyan-700 dark:text-cyan-200">{serviceReviewPosture.activeIssues}</div>
          </div>
        </div>
        <div className="mt-4 rounded-2xl border border-sky-200/80 bg-sky-50/60 p-4 dark:border-sky-900/50 dark:bg-sky-950/15">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-[11px] font-black uppercase tracking-[0.25em] text-sky-700 dark:text-sky-300">
                {t('service_operating_posture_title', 'Service Operating Posture')}
              </div>
              <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                {t('service_operating_posture_desc', 'Use the same service-health baseline across alerts, topology, and reports so operators do not lose business context while triaging.')}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 lg:min-w-[480px]">
              <div className="rounded-xl border border-sky-200/70 bg-white/80 p-3 dark:border-sky-900/40 dark:bg-[#111315]">
                <div className="text-[10px] font-black uppercase tracking-widest text-sky-700 dark:text-sky-300">
                  {t('service_operating_posture_average_health', 'Average health')}
                </div>
                <div className="mt-1 text-2xl font-black text-sky-700 dark:text-sky-200">{serviceReviewAverageHealth}</div>
              </div>
              <div className="rounded-xl border border-indigo-200/70 bg-white/80 p-3 dark:border-indigo-900/40 dark:bg-[#111315]">
                <div className="text-[10px] font-black uppercase tracking-widest text-indigo-700 dark:text-indigo-300">
                  {t('service_operating_posture_groups_in_scope', 'Groups in scope')}
                </div>
                <div className="mt-1 text-2xl font-black text-indigo-700 dark:text-indigo-200">{serviceReviewPosture.totalGroups}</div>
              </div>
                <div className="rounded-xl border border-fuchsia-200/70 bg-white/80 p-3 dark:border-fuchsia-900/40 dark:bg-[#111315]">
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

        {servicePriorityFocus ? (
          <div className="mt-4 rounded-2xl border border-violet-200/80 bg-violet-50/60 p-4 dark:border-violet-900/50 dark:bg-violet-950/15">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${toneForCriticality(servicePriorityFocus.criticality)}`}>
                    {servicePriorityFocus.criticality || 'standard'}
                  </span>
                  <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${severityTone(servicePriorityFocus.healthStatus === 'critical' ? 'critical' : servicePriorityFocus.healthStatus === 'healthy' ? 'info' : 'warning')}`}>
                    {t('service_groups_health_score', 'Health Score')}: {servicePriorityFocus.healthScore}
                  </span>
                  <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{servicePriorityFocus.name}</div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                  <span>{t('service_groups_health_active_issues', 'Active issues')}: {servicePriorityFocus.activeIssueCount}</span>
                  <span>{t('service_groups_health_offline_devices', 'Offline devices')}: {servicePriorityFocus.offlineDeviceCount}</span>
                  <span>{t('service_groups_health_discovered_only', 'Discovered only')}: {servicePriorityFocus.discoveredOnlyDeviceCount}</span>
                </div>
                <div className="mt-3 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
                  {servicePriorityFocus.nextAction}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  data-testid="operations-reports-service-priority-open-workspace"
                  onClick={() => navigate(`/automation?workspace=${servicePriorityWorkspace.workspace}`)}
                  className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-bold text-sky-700 hover:bg-sky-100 dark:border-sky-900/60 dark:bg-sky-500/10 dark:text-sky-300 dark:hover:bg-sky-500/20"
                >
                  {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', servicePriorityWorkspaceLabel)}
                </button>
                <button
                  data-testid="operations-reports-service-priority-open-review"
                  onClick={() => navigate(`/operations-reports?focusGroupId=${servicePriorityFocus.id}&focusGroupName=${encodeURIComponent(servicePriorityFocus.name || '')}`)}
                  className="inline-flex items-center gap-2 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-xs font-bold text-violet-700 hover:bg-violet-100 dark:border-violet-900/60 dark:bg-violet-500/10 dark:text-violet-300 dark:hover:bg-violet-500/20"
                >
                  {t('operations_reports_service_priority_open_review', 'Open focused review')}
                </button>
                <button
                  data-testid="operations-reports-service-priority-open-topology"
                  onClick={() => navigate(`/topology?serviceOverlay=1&serviceGroupId=${servicePriorityFocus.id}`)}
                  className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700 hover:bg-emerald-100 dark:border-emerald-900/60 dark:bg-emerald-500/10 dark:text-emerald-300 dark:hover:bg-emerald-500/20"
                >
                  {t('operations_reports_open_service_map', 'Open Service Map')}
                </button>
                <button
                  data-testid="operations-reports-service-priority-open-notifications"
                  onClick={() => navigate(`/notifications?serviceImpact=1&openServiceImpact=1&focusGroupId=${servicePriorityFocus.id}&focusGroupName=${encodeURIComponent(servicePriorityFocus.name || '')}`)}
                  className="inline-flex items-center gap-2 rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs font-bold text-cyan-700 hover:bg-cyan-100 dark:border-cyan-900/60 dark:bg-cyan-500/10 dark:text-cyan-300 dark:hover:bg-cyan-500/20"
                >
                  {t('operations_reports_service_priority_open_notifications', 'Open service-aware alerts')}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
            {t('operations_reports_service_priority_empty', 'No service group currently needs immediate priority review.')}
          </div>
        )}

        <div className="mt-4 grid gap-3 lg:grid-cols-3" data-testid="operations-reports-service-priority-queue">
          {servicePriorityQueue.length > 0 ? servicePriorityQueue.map((group) => (
            <div
              key={`operations-reports-service-priority-${group.id}`}
              data-testid={`operations-reports-service-priority-card-${group.id}`}
              className="rounded-xl border border-violet-200/70 bg-white/90 p-3 shadow-sm dark:border-violet-900/40 dark:bg-black/20 dark:shadow-none"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{group.name}</div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {group.description || t('ops_home_service_review_no_description', 'Review this service group through topology, reports, and alerts.')}
                  </div>
                </div>
                <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${severityTone(group.healthStatus === 'critical' ? 'critical' : group.healthStatus === 'healthy' ? 'info' : 'warning')}`}>
                  {t('service_groups_health_score', 'Health Score')}: {group.healthScore}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                <span>{t('service_groups_health_active_issues', 'Active issues')}: {group.activeIssueCount}</span>
                <span>{t('service_groups_health_offline_devices', 'Offline devices')}: {group.offlineDeviceCount}</span>
                <span>{t('service_groups_health_discovered_only', 'Discovered only')}: {group.discoveredOnlyDeviceCount}</span>
              </div>
              <div className="mt-3 text-xs text-gray-600 dark:text-gray-300">
                {group.nextAction}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  data-testid={`operations-reports-service-priority-queue-open-review-${group.id}`}
                  onClick={() => navigate(`/operations-reports?focusGroupId=${group.id}&focusGroupName=${encodeURIComponent(group.name || '')}`)}
                  className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-[11px] font-semibold text-violet-700 transition-colors hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200 dark:hover:bg-violet-950/30"
                >
                  {t('operations_reports_service_priority_open_review', 'Open focused review')}
                </button>
                <button
                  type="button"
                  data-testid={`operations-reports-service-priority-queue-open-notifications-${group.id}`}
                  onClick={() => navigate(`/notifications?serviceImpact=1&openServiceImpact=1&focusGroupId=${group.id}&focusGroupName=${encodeURIComponent(group.name || '')}`)}
                  className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-semibold text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
                >
                  {t('operations_reports_service_priority_open_notifications', 'Open service-aware alerts')}
                </button>
                <button
                  type="button"
                  data-testid={`operations-reports-service-priority-queue-open-topology-${group.id}`}
                  onClick={() => navigate(`/topology?serviceOverlay=1&serviceGroupId=${group.id}&focusGroupName=${encodeURIComponent(group.name || '')}`)}
                  className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-200 dark:hover:bg-emerald-950/30"
                >
                  {t('operations_reports_open_service_map', 'Open Service Map')}
                </button>
              </div>
            </div>
          )) : (
            <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400 lg:col-span-3">
              {t('operations_reports_service_priority_empty', 'No service group currently needs immediate priority review.')}
            </div>
          )}
        </div>
      </section>

      <section className={`${PANEL_CLASS} p-5`}>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
              {t('operations_reports_state_history_title', 'State History Review')}
            </div>
            <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
              {t('operations_reports_state_history_desc', 'Use the latest captured baseline to explain whether today’s operating posture is stable, improved, or drifting before weekly review and handoff.')}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => navigate('/state-history')}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
            >
              {t('operations_reports_open_state_history', 'Open State History')}
              <ExternalLink size={14} />
            </button>
            <button
              onClick={() => void handleCaptureStateHistory()}
              disabled={capturingStateHistory || !canOperate}
              className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-bold text-blue-700 hover:bg-blue-100 disabled:opacity-60 dark:border-blue-900/60 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/20"
            >
              {capturingStateHistory ? <RefreshCw size={14} className="animate-spin" /> : <TimerReset size={14} />}
              {t('operations_reports_capture_state_history', 'Capture Snapshot')}
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
              {t('operations_reports_state_history_snapshots', 'Stored Snapshots')}
            </div>
            <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{stateHistorySummary.snapshotCount}</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {t('operations_reports_state_history_latest_age', '{value}h since latest')
                .replace('{value}', stateHistorySummary.latestAgeHours == null ? '-' : Number(stateHistorySummary.latestAgeHours).toFixed(1))}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
              {t('operations_reports_state_history_result', 'Latest Review Result')}
            </div>
            <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">
              {String(stateHistorySummary.latestCompare?.summary?.result || 'unavailable').toUpperCase()}
            </div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {t('operations_reports_state_history_result_hint', '{value} review cards')
                .replace('{value}', String(Number(stateHistorySummary.latestCompare?.summary?.review_cards || 0)))}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
              {t('operations_reports_state_history_baseline', 'Baseline')}
            </div>
            <div className="mt-2 text-sm font-bold text-gray-900 dark:text-gray-100 break-words">
              {stateHistorySummary.latestSnapshot?.label || t('operations_reports_state_history_none', 'No saved baseline')}
            </div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {formatTs(stateHistorySummary.latestSnapshot?.generated_at)}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
              {t('operations_reports_state_history_improved', 'Improved Signals')}
            </div>
            <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">
              {Number(stateHistorySummary.latestCompare?.summary?.improved_cards || 0)}
            </div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {t('operations_reports_state_history_changed_hint', '{value} changed cards')
                .replace('{value}', String(Number(stateHistorySummary.latestCompare?.summary?.changed_cards || 0)))}
            </div>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {loading ? (
            <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
              {t('common_loading', 'Loading...')}
            </div>
          ) : stateHistorySummary.hotspotRows.length === 0 ? (
            <div data-testid="operations-reports-empty-state-history" className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
              {t('operations_reports_state_history_empty', 'No state history hotspots yet. Capture a review snapshot after a weekly review or major change.')}
            </div>
          ) : (
            stateHistorySummary.hotspotRows.map((item) => (
              <div key={`state-hotspot-${item.key}`} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${String(item.status || '').toLowerCase() === 'review' ? 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300' : 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/50 dark:bg-sky-500/10 dark:text-sky-300'}`}>
                        {String(item.status || 'changed').toUpperCase()}
                      </span>
                      <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{item.title}</div>
                    </div>
                    <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      {t('operations_reports_state_history_delta_fmt', 'Delta: {value}').replace('{value}', String(item.delta || '-'))}
                    </div>
                    {item.recommendation ? (
                      <div className="mt-2 text-sm text-gray-700 dark:text-gray-200">{item.recommendation}</div>
                    ) : null}
                  </div>
                  <button
                    onClick={() => navigate('/state-history')}
                    className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                  >
                    {t('operations_reports_open_state_history_compare', 'Open State Compare')}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(340px,0.95fr)]">
        <section className={`${PANEL_CLASS} p-5`}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
                {t('operations_reports_recent_runs_title', 'Recent Preventive Runs')}
              </div>
              <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                {t('operations_reports_recent_runs_desc', 'Export PDF operator reports, raw CSV evidence, or markdown summaries from the latest preventive check runs.')}
              </div>
            </div>
            <button
              onClick={() => navigate('/preventive-checks')}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
            >
              {t('operations_reports_open_preventive_checks', 'Open Preventive Checks')}
              <ExternalLink size={14} />
            </button>
          </div>

          <div className="mt-4 space-y-3">
            {loading ? (
              <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                {t('common_loading', 'Loading...')}
              </div>
          ) : runs.length === 0 ? (
              <div data-testid="operations-reports-empty-runs" className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                {t('operations_reports_no_runs', 'No runs yet')}
              </div>
            ) : (
              runs.map((run) => (
                <div key={run.id} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{run.template_name || t('operations_reports_unknown_template', 'Unnamed template')}</div>
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${statusTone(run)}`}>
                          {String(run.status || 'completed')}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {t('operations_reports_run_meta', 'Triggered by {user} · {time}')
                          .replace('{user}', String(run.triggered_by || 'operator'))
                          .replace('{time}', formatTs(run.finished_at || run.started_at))}
                      </div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-3 text-xs text-gray-600 dark:text-gray-300">
                        <div>{t('preventive_checks_devices_total', 'Devices')}: {Number(run?.summary?.devices_total || 0)}</div>
                        <div>{t('preventive_checks_failed_checks_total', 'Failed checks')}: {Number(run?.summary?.failed_checks_total || 0)}</div>
                        <div>{t('preventive_checks_critical_devices', 'Critical Devices')}: {Number(run?.summary?.critical_devices || 0)}</div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => void handleExportRun(run.id, 'pdf')}
                        className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-bold text-blue-700 hover:bg-blue-100 dark:border-blue-900/60 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/20"
                      >
                        <Download size={14} />
                        {t('preventive_checks_export_pdf', 'Export PDF')}
                      </button>
                      <button
                        onClick={() => void handleExportRun(run.id, 'csv')}
                        className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                      >
                        <Download size={14} />
                        {t('preventive_checks_export_csv', 'Export CSV')}
                      </button>
                      <button
                        onClick={() => void handleExportRun(run.id, 'md')}
                        className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                      >
                        <Download size={14} />
                        {t('preventive_checks_export_markdown', 'Export Markdown')}
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="space-y-6">
          <div className={`${PANEL_CLASS} p-5`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_change_control_title', 'Change Control Review')}
                </div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {t('operations_reports_change_control_desc', 'Review the latest approval flow, evidence readiness, and rollback posture before you hand off the weekly operating review.')}
                </div>
              </div>
              <button
                data-testid="operations-reports-open-approval-center"
                onClick={() => navigate('/approval')}
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
              >
                {t('operations_reports_open_approval_center', 'Open Approval Center')}
                <ExternalLink size={14} />
              </button>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_approval_total', 'Recent Requests')}
                </div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{summarizeApprovals(approvals).total}</div>
              </div>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_approval_evidence_ready', 'Evidence Ready')}
                </div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{summarizeApprovals(approvals).evidenceReady}</div>
              </div>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_approval_rollback_tracked', 'Rollback Tracked')}
                </div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{summarizeApprovals(approvals).rollbackTracked}</div>
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {focusedGroupId > 0 || focusedGroupName ? (
                <div data-testid="operations-reports-focused-group" className="rounded-2xl border border-cyan-200/80 bg-cyan-50/70 p-4 dark:border-cyan-900/50 dark:bg-cyan-950/15">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-[11px] font-black uppercase tracking-[0.18em] text-cyan-700 dark:text-cyan-300">
                        {t('operations_reports_focused_group_label', 'Focused Service Review')}
                      </div>
                      {focusedGroup ? (
                        <>
                          <div className="mt-2 flex items-center gap-2">
                            <div
                              className="h-3 w-3 rounded-full border border-white/70"
                              style={{ backgroundColor: focusedGroup.color || '#0ea5e9' }}
                            />
                            <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{focusedGroup.name || focusedGroupName}</div>
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${toneForCriticality(focusedGroup.criticality)}`}>
                              {focusedGroup.criticality || 'standard'}
                            </span>
                          </div>
                          <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                            {(focusedGroup.owner_team || t('operations_reports_unassigned_owner', 'Unassigned owner'))}
                          </div>
                        </>
                      ) : (
                        <div className="mt-2 text-sm text-gray-700 dark:text-gray-200">
                          {loading
                            ? t('common_loading', 'Loading...')
                            : focusedGroupName
                              ? t(
                                  'operations_reports_focused_group_pending_named',
                                  'Opening service review context for {value}. Continue from Service Groups if the mapped details need a refresh.',
                                ).replace('{value}', focusedGroupName)
                              : t(
                                  'operations_reports_focused_group_pending',
                                  'Service review context is opening. Continue from Service Groups if the mapped details need a refresh.',
                                )}
                        </div>
                      )}
                    </div>
                    <div className="text-right text-[11px] text-gray-600 dark:text-gray-300">
                      <div>{t('operations_reports_service_group_members', '{total} members 夷?{devices} devices 夷?{cloud} cloud')
                        .replace('{total}', String(focusedGroup?.member_count || 0))
                        .replace('{devices}', String(focusedGroup?.device_count || 0))
                        .replace('{cloud}', String(focusedGroup?.cloud_resource_count || 0))}</div>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      data-testid="operations-reports-focused-group-open-group"
                      onClick={() => navigate(`/service-groups?focusGroupId=${focusedGroup?.id || focusedGroupId}&focusGroupName=${encodeURIComponent(focusedGroup?.name || focusedGroupName)}`)}
                      className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                    >
                      {t('operations_reports_open_group', 'Open Group')}
                    </button>
                    <button
                      data-testid="operations-reports-focused-group-open-topology"
                      onClick={() => navigate(`/topology?serviceOverlay=1&serviceGroupId=${focusedGroup?.id || focusedGroupId}`)}
                      className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                    >
                      {t('operations_reports_open_service_map', 'Open Service Map')}
                    </button>
                    <button
                      data-testid="operations-reports-focused-group-open-notifications"
                      onClick={() => navigate(`/notifications?serviceImpact=1&openServiceImpact=1&focusGroupId=${focusedGroup?.id || focusedGroupId}&focusGroupName=${encodeURIComponent(focusedGroup?.name || focusedGroupName)}`)}
                      className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                    >
                      {t('operations_reports_open_notifications', 'Open Notifications')}
                    </button>
                    <button
                      data-testid="operations-reports-focused-group-clear"
                      onClick={() => navigate('/operations-reports')}
                      className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                    >
                      {t('operations_reports_clear_focus', 'Clear focus')}
                    </button>
                  </div>
                </div>
              ) : null}
              {loading ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('common_loading', 'Loading...')}
                </div>
              ) : approvals.length === 0 ? (
                <div data-testid="operations-reports-empty-approvals" className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('operations_reports_no_approvals', 'No recent approval requests.')}
                </div>
              ) : (
                approvals.map((request) => {
                  const payload = request?.payload && typeof request.payload === 'object' ? request.payload : {};
                  const evidenceReady = Boolean(payload.execution_result || payload.execution_trace);
                  const rollbackTracked = Boolean(payload.rollback_on_failure || payload.execution_result?.rollback_attempted);
                  return (
                    <div key={request.id} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{request.title}</div>
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${approvalTone(request.status, request.payload?.execution_status)}`}>
                              {String(request.status || 'pending')}
                            </span>
                            {request?.payload?.execution_status ? (
                              <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${approvalTone(request.status, request.payload.execution_status)}`}>
                                {String(request.payload.execution_status)}
                              </span>
                            ) : null}
                          </div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                            {t('operations_reports_approval_meta', '{type} · requested by {user} · {time}')
                              .replace('{type}', String(request.request_type || 'approval'))
                              .replace('{user}', String(request.requester_name || 'operator'))
                              .replace('{time}', formatTs(request.created_at))}
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {evidenceReady ? (
                              <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300">
                                {t('operations_reports_evidence_ready_badge', 'Evidence Ready')}
                              </span>
                            ) : null}
                            {rollbackTracked ? (
                              <span className="inline-flex rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300">
                                {t('operations_reports_rollback_badge', 'Rollback Tracked')}
                              </span>
                            ) : null}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => navigate(`/approval?focusRequestId=${request.id}`)}
                            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                          >
                            {t('operations_reports_open_request', 'Open Request')}
                          </button>
                          {canAdmin && evidenceReady ? (
                            <button
                              onClick={() => void handleDownloadApprovalEvidence(request.id)}
                              disabled={downloading.approvalEvidenceId === request.id}
                              className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-bold text-blue-700 hover:bg-blue-100 disabled:opacity-60 dark:border-blue-900/60 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/20"
                            >
                              {downloading.approvalEvidenceId === request.id ? <RefreshCw size={14} className="animate-spin" /> : <Download size={14} />}
                              {t('operations_reports_download_approval_evidence', 'Download Evidence')}
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className={`${PANEL_CLASS} p-5`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_follow_up_title', 'Follow-up Agenda')}
                </div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {t('operations_reports_follow_up_desc', 'Turn the current service-scoped issue review into explicit next steps for the next operator shift, weekly review, or audit handoff.')}
                </div>
              </div>
              <button
                onClick={() => navigate('/approval')}
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
              >
                {t('operations_reports_open_approval_center', 'Open Approval Center')}
                <ExternalLink size={14} />
              </button>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">{t('operations_reports_follow_up_needs_action', 'Needs Action')}</div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{followUpAgenda.summary.needsAction}</div>
              </div>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">{t('operations_reports_follow_up_needs_owner', 'Needs Owner')}</div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{followUpAgenda.summary.needsOwner}</div>
              </div>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">{t('operations_reports_follow_up_needs_knowledge', 'Needs Knowledge')}</div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{followUpAgenda.summary.needsKnowledge}</div>
              </div>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">{t('operations_reports_follow_up_needs_evidence', 'Needs Evidence')}</div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{followUpAgenda.summary.needsEvidence}</div>
              </div>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">{t('operations_reports_follow_up_ready', 'Ready for Handoff')}</div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{followUpAgenda.summary.readyForHandoff}</div>
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {loading ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('common_loading', 'Loading...')}
                </div>
              ) : followUpAgenda.items.length === 0 ? (
                <div data-testid="operations-reports-empty-follow-up" className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('operations_reports_follow_up_empty', 'No follow-up agenda items are pending right now.')}
                </div>
              ) : (
                followUpAgenda.items.map((issue) => {
                  const actionSummary = issue?.action_summary || {};
                  const approvalSummary = issue?.approval_summary || {};
                  const latestApprovalId = approvalSummary?.latest_approval_id;
                  const serviceSummary = issue?.service_impact_summary || {};
                  return (
                    <div key={`follow-up-${issue.id}`} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${severityTone(issue.severity)}`}>
                              {String(issue.severity || 'info')}
                            </span>
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${toneForCriticality(issue.priority)}`}>
                              {String(issue.priority || 'normal')}
                            </span>
                            <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{issue.title}</div>
                          </div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                            {t('operations_reports_action_continuity_meta', '{device} · {service} · {time}')
                              .replace('{device}', String(issue.device_name || issue.device || 'System'))
                              .replace('{service}', String(serviceSummary.primary_name || '-'))
                              .replace('{time}', formatTs(actionSummary.latest_updated_at || issue.created_at))}
                          </div>
                          <div className="mt-3 rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#0f1113] p-3">
                            <div className="text-[10px] uppercase tracking-[0.14em] text-gray-400">{t('operations_reports_follow_up_next_step', 'Recommended Next Step')}</div>
                            <div className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{issue.stepLabel}</div>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => openIssueFlow(issue.id, { openServiceImpact: true })}
                            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                          >
                            {t('operations_reports_open_issue_flow', 'Open Issue Flow')}
                          </button>
                          <button
                            onClick={() => openIssueFlow(issue.id, { openServiceImpact: false })}
                            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                          >
                            {t('operations_reports_open_sop_flow', 'Open SOP Flow')}
                          </button>
                          {latestApprovalId ? (
                            <button
                              onClick={() => navigate(`/approval?focusRequestId=${encodeURIComponent(String(latestApprovalId))}`)}
                              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                            >
                              {t('operations_reports_open_approval', 'Open Approval')}
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className={`${PANEL_CLASS} p-5`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_service_groups_title', 'Service Group Snapshot')}
                </div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {t('operations_reports_service_groups_desc', 'Use service groups as reporting context so operators can explain which business services own the reviewed assets.')}
                </div>
              </div>
              <button
                onClick={() => navigate('/service-groups')}
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
              >
                {t('operations_reports_open_service_groups', 'Open Service Groups')}
                <ExternalLink size={14} />
              </button>
            </div>

            <div className="mt-4 space-y-3">
              {loading ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('common_loading', 'Loading...')}
                </div>
              ) : groups.length === 0 ? (
                <div data-testid="operations-reports-empty-service-groups" className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('operations_reports_no_service_groups', 'No service groups yet.')}
                </div>
              ) : (
                <>
                  {showInlineFocusedGroupCard && (focusedGroupId > 0 || focusedGroupName) ? (
                    <div data-testid="operations-reports-focused-group" className="rounded-2xl border border-cyan-200/80 bg-cyan-50/70 p-4 dark:border-cyan-900/50 dark:bg-cyan-950/15">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="text-[11px] font-black uppercase tracking-[0.18em] text-cyan-700 dark:text-cyan-300">
                            {t('operations_reports_focused_group_label', 'Focused Service Review')}
                          </div>
                          {focusedGroup ? (
                            <>
                              <div className="mt-2 flex items-center gap-2">
                                <div
                                  className="h-3 w-3 rounded-full border border-white/70"
                                  style={{ backgroundColor: focusedGroup.color || '#0ea5e9' }}
                                />
                                <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{focusedGroup.name || focusedGroupName}</div>
                                <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${toneForCriticality(focusedGroup.criticality)}`}>
                                  {focusedGroup.criticality || 'standard'}
                                </span>
                              </div>
                              <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                                {(focusedGroup.owner_team || t('operations_reports_unassigned_owner', 'Unassigned owner'))}
                              </div>
                            </>
                          ) : (
                            <div className="mt-2 text-sm text-gray-700 dark:text-gray-200">
                              {loading
                                ? t('common_loading', 'Loading...')
                                : focusedGroupName
                                  ? t(
                                      'operations_reports_focused_group_pending_named',
                                      'Opening service review context for {value}. Continue from Service Groups if the mapped details need a refresh.',
                                    ).replace('{value}', focusedGroupName)
                                  : t(
                                      'operations_reports_focused_group_pending',
                                      'Service review context is opening. Continue from Service Groups if the mapped details need a refresh.',
                                    )}
                            </div>
                          )}
                        </div>
                        <div className="text-right text-[11px] text-gray-600 dark:text-gray-300">
                          <div>{t('operations_reports_service_group_members', '{total} members 쨌 {devices} devices 쨌 {cloud} cloud')
                            .replace('{total}', String(focusedGroup.member_count || 0))
                            .replace('{devices}', String(focusedGroup.device_count || 0))
                            .replace('{cloud}', String(focusedGroup.cloud_resource_count || 0))}</div>
                        </div>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <button
                          data-testid="operations-reports-focused-group-open-group"
                          onClick={() => navigate(`/service-groups?focusGroupId=${focusedGroup?.id || focusedGroupId}&focusGroupName=${encodeURIComponent(focusedGroup?.name || focusedGroupName)}`)}
                          className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                        >
                          {t('operations_reports_open_group', 'Open Group')}
                        </button>
                        <button
                          data-testid="operations-reports-focused-group-open-topology"
                          onClick={() => navigate(`/topology?serviceOverlay=1&serviceGroupId=${focusedGroup?.id || focusedGroupId}`)}
                          className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                        >
                          {t('operations_reports_open_service_map', 'Open Service Map')}
                        </button>
                        <button
                          data-testid="operations-reports-focused-group-open-notifications"
                          onClick={() => navigate(`/notifications?serviceImpact=1&openServiceImpact=1&focusGroupId=${focusedGroup?.id || focusedGroupId}&focusGroupName=${encodeURIComponent(focusedGroup?.name || focusedGroupName)}`)}
                          className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                        >
                          {t('operations_reports_open_notifications', 'Open Notifications')}
                        </button>
                        <button
                          data-testid="operations-reports-focused-group-clear"
                          onClick={() => navigate('/operations-reports')}
                          className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                        >
                          {t('operations_reports_clear_focus', 'Clear focus')}
                        </button>
                      </div>
                    </div>
                  ) : null}
                  {serviceSnapshotGroups.slice(0, 5).map((group) => (
                  <div key={group.id} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <div
                            className="h-3 w-3 rounded-full border border-white/70"
                            style={{ backgroundColor: group.color || '#0ea5e9' }}
                          />
                          <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{group.name}</div>
                        </div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {(group.owner_team || t('operations_reports_unassigned_owner', 'Unassigned owner'))}
                        </div>
                      </div>
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${toneForCriticality(group.criticality)}`}>
                        {group.criticality || 'standard'}
                      </span>
                    </div>
                    <div className="mt-3 text-xs text-gray-600 dark:text-gray-300">
                      {t('operations_reports_service_group_members', '{total} members · {devices} devices · {cloud} cloud')
                        .replace('{total}', String(group.member_count || 0))
                        .replace('{devices}', String(group.device_count || 0))
                        .replace('{cloud}', String(group.cloud_resource_count || 0))}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={() => navigate(`/service-groups?focusGroupId=${group.id}&focusGroupName=${encodeURIComponent(String(group.name || '').trim())}`)}
                        className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                      >
                        {t('operations_reports_open_group', 'Open Group')}
                      </button>
                      <button
                        onClick={() => navigate(`/topology?serviceOverlay=1&serviceGroupId=${group.id}`)}
                        className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                      >
                        {t('operations_reports_open_service_map', 'Open Service Map')}
                      </button>
                    </div>
                  </div>
                  ))}
                </>
              )}
            </div>
          </div>

          <div className={`${PANEL_CLASS} p-5`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_service_impact_title', 'Service Impact and SOP Readiness')}
                </div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {focusedGroupId > 0
                    ? t(
                        'operations_reports_service_impact_desc_focused',
                        'This review stays scoped to the selected service group so operators can finish issue review, approvals, and handoff without losing service context.',
                      )
                    : t(
                        'operations_reports_service_impact_desc',
                        'Review active issues that already map to business services, then check whether SOP steps, knowledge hints, and action context are ready for the operator handoff.',
                      )}
                </div>
              </div>
              <button
                onClick={() => navigate('/notifications')}
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
              >
                {t('operations_reports_open_notifications', 'Open Notifications')}
                <ExternalLink size={14} />
              </button>
            </div>

            <div className="mt-4 space-y-3">
              {loading ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('common_loading', 'Loading...')}
                </div>
              ) : serviceIssueRows.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('operations_reports_no_service_issues', 'No active issues are currently mapped to service groups.')}
                </div>
              ) : (
                serviceIssueRows.map((issue) => {
                  const serviceSummary = issue?.service_impact_summary || {};
                  const sopSummary = issue?.sop_summary || {};
                  const knowledgeSummary = issue?.knowledge_summary || {};
                  const actionSummary = issue?.action_summary || {};
                  const approvalSummary = issue?.approval_summary || {};
                  const latestApprovalId = approvalSummary?.latest_approval_id;
                  return (
                    <div key={issue.id} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${severityTone(issue.severity)}`}>
                              {String(issue.severity || 'info')}
                            </span>
                            <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{issue.title}</div>
                          </div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                            {t('operations_reports_issue_meta', '{device} · {time}')
                              .replace('{device}', String(issue.device || 'System'))
                              .replace('{time}', formatTs(issue.created_at))}
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            <span className="inline-flex rounded-full border border-indigo-200 bg-indigo-50 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-indigo-700 dark:border-indigo-900/50 dark:bg-indigo-500/10 dark:text-indigo-300">
                              {t('operations_reports_issue_service_group_fmt', '{value} groups').replace('{value}', String(serviceSummary.count || 0))}
                            </span>
                            <span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] ${sopTone(sopSummary.readiness_status)}`}>
                              {String(sopSummary.readiness_status || 'limited_context').replace(/_/g, ' ')}
                            </span>
                            {(knowledgeSummary.recommendation_count || 0) > 0 ? (
                              <span className="inline-flex rounded-full border border-purple-200 bg-purple-50 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-purple-700 dark:border-purple-900/50 dark:bg-purple-500/10 dark:text-purple-300">
                                {t('operations_reports_issue_knowledge_fmt', '{value} knowledge matches').replace('{value}', String(knowledgeSummary.recommendation_count || 0))}
                              </span>
                            ) : null}
                            {(approvalSummary.total || 0) > 0 ? (
                              <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300">
                                {t('operations_reports_issue_approval_fmt', '{value} approvals').replace('{value}', String(approvalSummary.total || 0))}
                              </span>
                            ) : null}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => openIssueFlow(issue.id, { openServiceImpact: true })}
                            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                          >
                            {t('operations_reports_open_issue_flow', 'Open Issue Flow')}
                          </button>
                          <button
                            onClick={() => openIssueFlow(issue.id, { openServiceImpact: false })}
                            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                          >
                            {t('operations_reports_open_sop_flow', 'Open SOP Flow')}
                          </button>
                          {issue.site_id ? (
                            <button
                              onClick={() => navigate(`/topology?siteId=${encodeURIComponent(String(issue.site_id))}`)}
                              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                            >
                              {t('operations_reports_open_topology', 'Open Topology')}
                            </button>
                          ) : null}
                          {latestApprovalId ? (
                            <button
                              onClick={() => navigate(`/approval?focusRequestId=${encodeURIComponent(String(latestApprovalId))}`)}
                              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                            >
                              {t('operations_reports_open_approval', 'Open Approval')}
                            </button>
                          ) : null}
                          {canAdmin && latestApprovalId && Number(approvalSummary.evidence_ready_count || 0) > 0 ? (
                            <button
                              onClick={() => void handleDownloadApprovalEvidence(latestApprovalId)}
                              disabled={downloading.approvalEvidenceId === latestApprovalId}
                              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 disabled:opacity-60 dark:text-gray-200 dark:hover:bg-white/5"
                            >
                              {downloading.approvalEvidenceId === latestApprovalId ? <RefreshCw size={14} className="animate-spin" /> : <Download size={14} />}
                              {t('operations_reports_download_approval_evidence', 'Download Evidence')}
                            </button>
                          ) : null}
                        </div>
                      </div>

                      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5 text-xs text-gray-600 dark:text-gray-300">
                        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#0f1113] p-3">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-400">{t('operations_reports_service_primary', 'Primary Service')}</div>
                          <div className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{serviceSummary.primary_name || '-'}</div>
                          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {t('operations_reports_service_members_fmt', '{value} matched members').replace('{value}', String(serviceSummary.matched_member_count || 0))}
                          </div>
                        </div>
                        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#0f1113] p-3">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-400">{t('operations_reports_sop_status', 'SOP Readiness')}</div>
                          <div className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{String(sopSummary.readiness_status || 'limited_context').replace(/_/g, ' ')}</div>
                          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {t('operations_reports_sop_steps_fmt', '{value} steps').replace('{value}', String(sopSummary.step_count || 0))}
                          </div>
                        </div>
                        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#0f1113] p-3">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-400">{t('operations_reports_actions_status', 'Action Trail')}</div>
                          <div className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{String(actionSummary.latest_status || 'open')}</div>
                          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {t('operations_reports_actions_total_fmt', '{value} actions').replace('{value}', String(actionSummary.total || 0))}
                          </div>
                        </div>
                        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#0f1113] p-3">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-400">{t('operations_reports_knowledge_status', 'Knowledge')}</div>
                          <div className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{knowledgeSummary.top_title || '-'}</div>
                          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {t('operations_reports_knowledge_total_fmt', '{value} matched entries').replace('{value}', String(knowledgeSummary.recommendation_count || 0))}
                          </div>
                        </div>
                        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#0f1113] p-3">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-400">{t('operations_reports_approvals_status', 'Approval Context')}</div>
                          <div className="mt-1 flex items-center gap-2">
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] ${approvalTone(approvalSummary.latest_status, approvalSummary.latest_status)}`}>
                              {String(approvalSummary.latest_status || 'none')}
                            </span>
                            {approvalSummary.evidence_ready_count ? (
                              <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300">
                                {t('operations_reports_evidence_ready_badge', 'Evidence Ready')}
                              </span>
                            ) : null}
                          </div>
                          <div className="mt-2 space-y-1 text-[11px] text-gray-500 dark:text-gray-400">
                            <div>{t('operations_reports_approvals_total_fmt', '{value} approvals').replace('{value}', String(approvalSummary.total || 0))}</div>
                            <div>{t('operations_reports_approvals_pending_fmt', '{value} pending').replace('{value}', String(approvalSummary.pending || 0))}</div>
                            <div>{t('operations_reports_approvals_evidence_fmt', '{value} evidence ready').replace('{value}', String(approvalSummary.evidence_ready_count || 0))}</div>
                            <div>{t('operations_reports_approvals_rollback_fmt', '{value} rollback tracked').replace('{value}', String(approvalSummary.rollback_tracked_count || 0))}</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className={`${PANEL_CLASS} p-5`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_action_continuity_title', 'Action Continuity Review')}
                </div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {t('operations_reports_action_continuity_desc', 'Confirm that service-scoped issues already have an owner, the latest action note, reusable knowledge, and approval evidence before handoff.')}
                </div>
              </div>
              <button
                onClick={() => navigate('/notifications')}
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
              >
                {t('operations_reports_open_notifications', 'Open Notifications')}
                <ExternalLink size={14} />
              </button>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_action_continuity_scope', 'Issues In Scope')}
                </div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{actionContinuity.summary.issuesInScope}</div>
                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {t('operations_reports_action_continuity_scope_hint', '{value} with active actions').replace('{value}', String(actionContinuity.summary.withActiveActions))}
                </div>
              </div>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_action_continuity_owner', 'Owner Coverage')}
                </div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{actionContinuity.summary.withAssignee}</div>
                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {t('operations_reports_action_continuity_owner_hint', '{value} evidence-linked').replace('{value}', String(actionContinuity.summary.withEvidenceReady))}
                </div>
              </div>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_action_continuity_knowledge', 'Knowledge Coverage')}
                </div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{actionContinuity.summary.withKnowledge}</div>
                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {t('operations_reports_action_continuity_knowledge_hint', '{value} issues still limited').replace('{value}', String(actionContinuity.summary.limitedContext))}
                </div>
              </div>
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_action_continuity_evidence', 'Evidence Links')}
                </div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{actionContinuity.summary.withEvidenceReady}</div>
                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {t('operations_reports_action_continuity_evidence_hint', '{value} knowledge-backed').replace('{value}', String(actionContinuity.summary.withKnowledge))}
                </div>
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {loading ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('common_loading', 'Loading...')}
                </div>
              ) : actionContinuity.rows.length === 0 ? (
                <div data-testid="operations-reports-empty-action-continuity" className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('operations_reports_action_continuity_empty', 'No service-scoped issues are currently available for action continuity review.')}
                </div>
              ) : (
                actionContinuity.rows.map((issue) => {
                  const actionSummary = issue?.action_summary || {};
                  const knowledgeSummary = issue?.knowledge_summary || {};
                  const sopSummary = issue?.sop_summary || {};
                  const approvalSummary = issue?.approval_summary || {};
                  const serviceSummary = issue?.service_impact_summary || {};
                  const latestApprovalId = approvalSummary?.latest_approval_id;
                  const latestNote = actionSummary?.latest_note || t('operations_reports_action_no_note', 'No action note has been recorded yet.');
                  return (
                    <div key={`continuity-${issue.id}`} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${severityTone(issue.severity)}`}>
                              {String(issue.severity || 'info')}
                            </span>
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${actionStatusTone(actionSummary.latest_status || 'open')}`}>
                              {String(actionSummary.latest_status || 'open')}
                            </span>
                            <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{issue.title}</div>
                          </div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                            {t('operations_reports_action_continuity_meta', '{device} · {service} · {time}')
                              .replace('{device}', String(issue.device_name || issue.device || 'System'))
                              .replace('{service}', String(serviceSummary.primary_name || '-'))
                              .replace('{time}', formatTs(actionSummary.latest_updated_at || issue.created_at))}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => openIssueFlow(issue.id, { openServiceImpact: true })}
                            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                          >
                            {t('operations_reports_open_issue_flow', 'Open Issue Flow')}
                          </button>
                          {latestApprovalId ? (
                            <button
                              onClick={() => navigate(`/approval?focusRequestId=${encodeURIComponent(String(latestApprovalId))}`)}
                              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                            >
                              {t('operations_reports_open_approval', 'Open Approval')}
                            </button>
                          ) : null}
                          {canAdmin && latestApprovalId && Number(approvalSummary.evidence_ready_count || 0) > 0 ? (
                            <button
                              onClick={() => void handleDownloadApprovalEvidence(latestApprovalId)}
                              disabled={downloading.approvalEvidenceId === latestApprovalId}
                              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 disabled:opacity-60 dark:text-gray-200 dark:hover:bg-white/5"
                            >
                              {downloading.approvalEvidenceId === latestApprovalId ? <RefreshCw size={14} className="animate-spin" /> : <Download size={14} />}
                              {t('operations_reports_download_approval_evidence', 'Download Evidence')}
                            </button>
                          ) : null}
                        </div>
                      </div>

                      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4 text-xs text-gray-600 dark:text-gray-300">
                        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#0f1113] p-3">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-400">{t('operations_reports_action_owner_label', 'Assigned Owner')}</div>
                          <div className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{actionSummary.latest_assignee_name || '-'}</div>
                          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {t('operations_reports_actions_total_fmt', '{value} actions').replace('{value}', String(actionSummary.total || 0))}
                          </div>
                        </div>
                        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#0f1113] p-3">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-400">{t('operations_reports_action_note_label', 'Latest Action Note')}</div>
                          <div className="mt-1 font-semibold text-gray-900 dark:text-gray-100 break-words">{latestNote}</div>
                        </div>
                        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#0f1113] p-3">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-400">{t('operations_reports_knowledge_status', 'Knowledge')}</div>
                          <div className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{knowledgeSummary.top_title || '-'}</div>
                          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {t('operations_reports_action_continuity_sop_fmt', '{knowledge} knowledge · {steps} SOP steps')
                              .replace('{knowledge}', String(knowledgeSummary.recommendation_count || 0))
                              .replace('{steps}', String(sopSummary.step_count || 0))}
                          </div>
                        </div>
                        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#0f1113] p-3">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-400">{t('operations_reports_approvals_status', 'Approval Context')}</div>
                          <div className="mt-1 font-semibold text-gray-900 dark:text-gray-100">
                            {t('operations_reports_action_continuity_approval_fmt', '{approvals} approvals · {evidence} evidence')
                              .replace('{approvals}', String(approvalSummary.total || 0))
                              .replace('{evidence}', String(approvalSummary.evidence_ready_count || 0))}
                          </div>
                          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {t('operations_reports_action_continuity_rollback_fmt', '{value} rollback tracked').replace('{value}', String(approvalSummary.rollback_tracked_count || 0))}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className={`${PANEL_CLASS} p-5`}>
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
              {t('operations_reports_bundles_title', 'Operational Bundles')}
            </div>
            <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
              {t('operations_reports_bundles_desc', 'Download the full operator package or targeted artifacts for handoff, audit, and weekly operating review.')}
            </div>
            <div className="mt-4 grid gap-2">
              <button
                data-testid="operations-reports-download-review-bundle"
                type="button"
                disabled={downloading.operationsReviewBundle}
                onClick={() =>
                  runDownload({
                    key: 'operationsReviewBundle',
                    request: () => OpsService.downloadOperationsReviewBundle(),
                    fallbackFilename: 'operations_review_bundle.zip',
                    successMessage: t('operations_reports_review_bundle_downloaded', 'Operations review bundle downloaded.'),
                    errorMessage: t('operations_reports_review_bundle_failed', 'Failed to download operations review bundle.'),
                  })
                }
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-3 text-sm font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5 disabled:opacity-60"
              >
                {downloading.operationsReviewBundle ? <RefreshCw size={16} className="animate-spin" /> : <FileText size={16} />}
                {t('operations_reports_download_review_bundle', 'Download Operations Review Bundle')}
              </button>
              <button
                data-testid="operations-reports-download-operator-package"
                type="button"
                disabled={downloading.operatorPackage}
                onClick={() =>
                  runDownload({
                    key: 'operatorPackage',
                    request: () => OpsService.downloadProOperatorPackage(),
                    fallbackFilename: 'pro_operator_package.zip',
                    successMessage: t('operations_reports_operator_package_downloaded', 'Pro operator package downloaded.'),
                    errorMessage: t('operations_reports_operator_package_failed', 'Failed to download Pro operator package.'),
                  })
                }
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-3 text-sm font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5 disabled:opacity-60"
              >
                {downloading.operatorPackage ? <RefreshCw size={16} className="animate-spin" /> : <Package size={16} />}
                {t('operations_reports_download_operator_package', 'Download Pro Operator Package')}
              </button>
              <button
                type="button"
                disabled={downloading.releaseBundle}
                onClick={() =>
                  runDownload({
                    key: 'releaseBundle',
                    request: () => OpsService.downloadReleaseEvidenceBundle(),
                    fallbackFilename: 'release_evidence_bundle.zip',
                    successMessage: t('operations_reports_release_bundle_downloaded', 'Release evidence bundle downloaded.'),
                    errorMessage: t('operations_reports_release_bundle_failed', 'Failed to download release evidence bundle.'),
                  })
                }
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-3 text-sm font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5 disabled:opacity-60"
              >
                {downloading.releaseBundle ? <RefreshCw size={16} className="animate-spin" /> : <FileText size={16} />}
                {t('operations_reports_download_release_bundle', 'Download Release Evidence Bundle')}
              </button>
              <button
                type="button"
                disabled={downloading.complianceExport}
                onClick={() =>
                  runDownload({
                    key: 'complianceExport',
                    request: () => ComplianceService.exportReports({ format: 'xlsx' }),
                    fallbackFilename: 'compliance_reports.xlsx',
                    successMessage: t('operations_reports_compliance_export_downloaded', 'Compliance export downloaded.'),
                    errorMessage: t('operations_reports_compliance_export_failed', 'Failed to download compliance export.'),
                  })
                }
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-3 text-sm font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5 disabled:opacity-60"
              >
                {downloading.complianceExport ? <RefreshCw size={16} className="animate-spin" /> : <FileCheck size={16} />}
                {t('operations_reports_download_compliance_export', 'Download Compliance Export')}
              </button>
            </div>
          </div>

          <div className={`${PANEL_CLASS} p-5`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
                  {t('operations_reports_release_title', 'Release Readiness Snapshot')}
                </div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {t('operations_reports_release_desc', 'Bring release evidence gates into the same review so operations, change control, and audit readiness stay aligned.')}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => navigate('/')}
                  className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                >
                  {t('operations_reports_open_dashboard', 'Open Dashboard')}
                </button>
                <button
                  onClick={() => void handleRefreshEvidence()}
                  disabled={!canOperate || refreshingEvidence}
                  className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 disabled:opacity-60 dark:text-gray-200 dark:hover:bg-white/5"
                >
                  {refreshingEvidence ? <RefreshCw size={14} className="animate-spin" /> : <TimerReset size={14} />}
                  {t('operations_reports_refresh_release', 'Refresh Evidence')}
                </button>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <span className={`inline-flex rounded-full border px-3 py-1 text-[11px] font-bold uppercase tracking-[0.14em] ${releaseEvidenceTone(releaseEvidence?.summary?.overall_status)}`}>
                {String(releaseEvidence?.summary?.overall_status || 'unknown')}
              </span>
              <div className="text-sm text-gray-600 dark:text-gray-300">
                {t('operations_reports_release_gate_progress', '{accepted} accepted · {available} available · {warnings} warnings')
                  .replace('{accepted}', String(releaseEvidence?.summary?.accepted_gates || 0))
                  .replace('{available}', String(releaseEvidence?.summary?.available_gates || releaseEvidence?.summary?.total_gates || 0))
                  .replace('{warnings}', String(Array.isArray(releaseEvidence?.summary?.warning_gates) ? releaseEvidence.summary.warning_gates.length : 0))}
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {loading ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('common_loading', 'Loading...')}
                </div>
              ) : releaseSections.length === 0 ? (
                <div data-testid="operations-reports-empty-release" className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('operations_reports_no_release_sections', 'No release evidence sections are available yet.')}
                </div>
              ) : (
                releaseSections.map((section) => (
                  <div key={section.id || section.title} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{section.title}</div>
                          <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${releaseEvidenceTone(section.status)}`}>
                            {String(section.status || 'unknown')}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{section.summary || '-'}</div>
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">{formatTs(section.generated_at)}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default OperationsReportsPage;
