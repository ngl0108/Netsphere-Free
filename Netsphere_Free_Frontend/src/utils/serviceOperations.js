import { t } from '../i18n';

export const summarizeServiceReviewPosture = (groups = []) => {
  const rows = Array.isArray(groups) ? groups : [];
  return rows.reduce((summary, group) => {
    const health = group?.health || {};
    const status = String(health.health_status || 'healthy').trim().toLowerCase();
    const discoveredOnly = Number(health.discovered_only_device_count || 0);
    const managed = Number(health.managed_device_count || 0);
    const activeIssues = Number(health.active_issue_count || 0);
    const offlineDevices = Number(health.offline_device_count || 0);
    const reviewNeeded = ['critical', 'degraded', 'review'].includes(status) || activeIssues > 0 || offlineDevices > 0;
    if (status === 'critical') summary.criticalGroups += 1;
    if (reviewNeeded) summary.reviewGroups += 1;
    if (discoveredOnly > managed) summary.discoveredOnlyPressure += 1;
    summary.activeIssues += activeIssues;
    summary.totalGroups += 1;
    summary.totalHealthScore += Number.isFinite(Number(health?.health_score)) ? Number(health.health_score) : 0;
    return summary;
  }, {
    criticalGroups: 0,
    reviewGroups: 0,
    discoveredOnlyPressure: 0,
    activeIssues: 0,
    totalGroups: 0,
    totalHealthScore: 0,
  });
};

export const getServiceReviewAverageHealth = (posture) => {
  const totalGroups = Number(posture?.totalGroups || 0);
  if (totalGroups <= 0) return 0;
  return Math.round(Number(posture?.totalHealthScore || 0) / totalGroups);
};

export const getServicePressureIndex = (posture) => {
  const totalGroups = Math.max(1, Number(posture?.totalGroups || 0));
  const criticalGroups = Number(posture?.criticalGroups || 0);
  const reviewGroups = Number(posture?.reviewGroups || 0);
  const discoveredOnlyPressure = Number(posture?.discoveredOnlyPressure || 0);
  const activeIssues = Number(posture?.activeIssues || 0);
  const weightedPressure =
    (criticalGroups * 30)
    + (reviewGroups * 12)
    + (discoveredOnlyPressure * 8)
    + (Math.min(activeIssues, totalGroups * 3) * 4);
  const maxPressure = Math.max(18, totalGroups * 18);
  return Math.min(100, Math.round((weightedPressure / maxPressure) * 100));
};

export const summarizeServiceLaneBoard = (posture = {}) => {
  const critical = Number(posture?.criticalGroups || 0);
  const review = Math.max(0, Number(posture?.reviewGroups || 0) - critical);
  const discoveredOnly = Number(posture?.discoveredOnlyPressure || 0);
  const total = Number(posture?.totalGroups || 0);
  const stable = Math.max(0, total - Number(posture?.reviewGroups || 0));
  return {
    critical,
    review,
    discoveredOnly,
    stable,
  };
};

export const getOperationsPressureLevel = (pressureIndex) => {
  const value = Number(pressureIndex || 0);
  if (value >= 70) return 'critical';
  if (value >= 40) return 'elevated';
  return 'stable';
};

export const getOperationsPressureLabel = (pressureIndex, translate = t) => {
  const level = getOperationsPressureLevel(pressureIndex);
  if (level === 'critical') {
    return translate('service_operating_posture_pressure_label_critical', 'Critical pressure');
  }
  if (level === 'elevated') {
    return translate('service_operating_posture_pressure_label_elevated', 'Elevated pressure');
  }
  return translate('service_operating_posture_pressure_label_stable', 'Stable pressure');
};

export const getOperationsPressureGuidance = (pressureIndex, translate = t) => {
  const level = getOperationsPressureLevel(pressureIndex);
  if (level === 'critical') {
    return translate(
      'service_operating_posture_pressure_guidance_critical',
      'Start from service-aware alerts and topology before broader changes spread.',
    );
  }
  if (level === 'elevated') {
    return translate(
      'service_operating_posture_pressure_guidance_elevated',
      'Open the service review path first so alerts, reports, and ownership stay aligned.',
    );
  }
  return translate(
    'service_operating_posture_pressure_guidance_stable',
    'Keep the current baseline stable and use reports to confirm service posture over time.',
  );
};

export const recommendServiceWorkspace = (group) => {
  if (!group) {
    return { workspace: 'observe', reason: 'default' };
  }
  if (Number(group.discoveredOnlyDeviceCount || 0) > Number(group.managedDeviceCount || 0)) {
    return { workspace: 'discover', reason: 'discovered_only' };
  }
  if (String(group.healthStatus || '').trim().toLowerCase() === 'critical' || Number(group.criticalIssueCount || 0) > 0) {
    return { workspace: 'observe', reason: 'critical' };
  }
  if (Number(group.activeIssueCount || 0) > 0 || Number(group.offlineDeviceCount || 0) > 0) {
    return { workspace: 'observe', reason: 'issues' };
  }
  return { workspace: 'govern', reason: 'review' };
};

export const getWorkspaceTitle = (workspace, translate = t) => {
  const value = String(workspace || '').trim().toLowerCase();
  if (value === 'discover') return translate('ops_workspace_discover_title', 'Discover');
  if (value === 'control') return translate('ops_workspace_control_title', 'Control');
  if (value === 'govern') return translate('ops_workspace_govern_title', 'Govern');
  return translate('ops_workspace_observe_title', 'Observe');
};

export const recommendCloudWorkspace = (account, ledger) => {
  const posture = String(ledger?.operations_posture || '').trim().toLowerCase();
  const failureCode = String(ledger?.last_failure_reason_code || '').trim().toLowerCase();
  const syncStatus = String(account?.sync_status || '').trim().toLowerCase();
  const pendingApprovals = Number(ledger?.pending_approvals || 0);
  const retryRecommended = Boolean(ledger?.retry_recommended);
  const changeEnabled = Boolean(account?.execution_readiness?.change_enabled);

  if (posture === 'approval_pending' || pendingApprovals > 0 || failureCode === 'policy_blocked') {
    return { workspace: 'govern', reason: 'approval' };
  }
  if (posture === 'syncing' || ['running', 'queued', 'syncing'].includes(syncStatus) || failureCode === 'scope_issue') {
    return { workspace: 'discover', reason: 'sync' };
  }
  if (retryRecommended || changeEnabled || ['credential_issue', 'permission_issue', 'connectivity_issue', 'operation_failed'].includes(failureCode)) {
    return { workspace: 'control', reason: 'recovery' };
  }
  return { workspace: 'observe', reason: 'stable' };
};

export const getCloudQueueNextAction = ({ workspaceReason, retryRecommended, pendingApprovals }, translate = t) => {
  if (Number(pendingApprovals || 0) > 0 || workspaceReason === 'approval') {
    return translate(
      'ops_home_cloud_review_next_action_approval',
      'Review the approval context first so cloud changes stay inside the governed path.',
    );
  }
  if (retryRecommended || workspaceReason === 'recovery') {
    return translate(
      'ops_home_cloud_review_next_action_recovery',
      'Open the account review and recover the safest validate, scan, or pipeline lane before retrying change work.',
    );
  }
  if (workspaceReason === 'sync') {
    return translate(
      'ops_home_cloud_review_next_action_sync',
      'Let the current sync cycle finish, then reopen the account review to confirm the inventory baseline has converged.',
    );
  }
  return translate(
    'ops_home_cloud_review_next_action_stable',
    'Keep the account on its current operating lane and return when service pressure or approval context changes.',
  );
};

export const summarizeCloudOperationsPressure = (ledgerRows = []) => {
  const rows = Array.isArray(ledgerRows) ? ledgerRows : [];
  return rows.reduce((summary, row) => {
    const posture = String(row?.operations_posture || '').trim().toLowerCase();
    if (posture === 'attention' || posture === 'approval_pending') summary.attention += 1;
    if (posture === 'syncing') summary.syncing += 1;
    summary.pendingApprovals += Number(row?.pending_approvals || 0);
    if (row?.retry_recommended) summary.retryRecommended += 1;
    summary.total += 1;
    return summary;
  }, {
    attention: 0,
    syncing: 0,
    pendingApprovals: 0,
    retryRecommended: 0,
    total: 0,
  });
};

export const summarizeCloudReviewQueue = (ledgerRows = [], translate = t, { limit = 4 } = {}) => {
  return (Array.isArray(ledgerRows) ? ledgerRows : [])
    .map((row) => {
      const accountId = Number(row?.account_id || 0);
      if (!Number.isFinite(accountId) || accountId <= 0) return null;
      const pendingApprovals = Number(row?.pending_approvals || 0);
      const retryRecommended = Boolean(row?.retry_recommended);
      const workspaceRecommendation = recommendCloudWorkspace(
        {
          id: accountId,
          name: row?.account_name,
          provider: row?.provider,
          sync_status: row?.sync_status,
          execution_readiness: row?.execution_readiness,
        },
        row,
      );
      const priority =
        (pendingApprovals > 0 ? 40 : 0) +
        (retryRecommended ? 28 : 0) +
        (String(row?.operations_posture || '').trim().toLowerCase() === 'attention' ? 18 : 0) +
        (String(row?.operations_posture || '').trim().toLowerCase() === 'approval_pending' ? 22 : 0) +
        (String(row?.operations_posture || '').trim().toLowerCase() === 'syncing' ? 8 : 0);
      if (priority <= 0) return null;
      return {
        accountId,
        name: String(row?.account_name || '').trim() || `Account ${accountId}`,
        provider: String(row?.provider || '').trim().toUpperCase() || 'CLOUD',
        operationsPosture: String(row?.operations_posture || '').trim().toLowerCase() || 'attention',
        pendingApprovals,
        retryRecommended,
        latestApprovalId: Number(row?.latest_approval_id || 0) || null,
        lastOperationAt: row?.last_operation_at || null,
        lastFailureReasonCode: String(row?.last_failure_reason_code || '').trim().toLowerCase(),
        lastFailureReasonLabel: String(row?.last_failure_reason_label || '').trim(),
        workspace: workspaceRecommendation.workspace,
        workspaceReason: workspaceRecommendation.reason,
        nextAction: getCloudQueueNextAction(
          {
            workspaceReason: workspaceRecommendation.reason,
            retryRecommended,
            pendingApprovals,
          },
          translate,
        ),
        priority,
      };
    })
    .filter(Boolean)
    .sort((left, right) => {
      if (right.priority !== left.priority) return right.priority - left.priority;
      const leftTs = Date.parse(String(left.lastOperationAt || '')) || 0;
      const rightTs = Date.parse(String(right.lastOperationAt || '')) || 0;
      if (rightTs !== leftTs) return rightTs - leftTs;
      return String(left.name || '').localeCompare(String(right.name || ''));
    })
    .slice(0, limit);
};

export const summarizeCloudLaneBoard = (ledgerRows = []) => {
  const summary = {
    approval: 0,
    recovery: 0,
    sync: 0,
    stable: 0,
  };
  (Array.isArray(ledgerRows) ? ledgerRows : []).forEach((row) => {
    const pendingApprovals = Number(row?.pending_approvals || 0);
    const retryRecommended = Boolean(row?.retry_recommended);
    const posture = String(row?.operations_posture || '').trim().toLowerCase();
    if (pendingApprovals > 0) {
      summary.approval += 1;
    } else if (retryRecommended) {
      summary.recovery += 1;
    } else if (posture === 'syncing') {
      summary.sync += 1;
    } else {
      summary.stable += 1;
    }
  });
  return summary;
};

export const summarizeCloudRetryQueue = (ledgerRows = [], { limit = 3 } = {}) => {
  return (Array.isArray(ledgerRows) ? ledgerRows : [])
    .map((row) => {
      const accountId = Number(row?.account_id || 0);
      if (!Number.isFinite(accountId) || accountId <= 0 || !row?.retry_recommended) return null;
      const pendingApprovals = Number(row?.pending_approvals || 0);
      const posture = String(row?.operations_posture || '').trim().toLowerCase();
      const priority =
        (pendingApprovals > 0 ? 12 : 0)
        + (posture === 'attention' ? 22 : 0)
        + (posture === 'approval_pending' ? 18 : 0)
        + 24;
      return {
        accountId,
        name: String(row?.account_name || '').trim() || `Account ${accountId}`,
        provider: String(row?.provider || '').trim().toUpperCase() || 'CLOUD',
        retryLabel: String(row?.last_operation_label || row?.last_operation_type || 'Retry').trim() || 'Retry',
        lastFailureReasonCode: String(row?.last_failure_reason_code || '').trim().toLowerCase(),
        lastFailureReasonLabel: String(row?.last_failure_reason_label || '').trim(),
        lastOperationAt: row?.last_operation_at || null,
        latestApprovalId: Number(row?.latest_approval_id || 0) || null,
        priority,
      };
    })
    .filter(Boolean)
    .sort((left, right) => {
      if (right.priority !== left.priority) return right.priority - left.priority;
      const leftTs = Date.parse(String(left.lastOperationAt || '')) || 0;
      const rightTs = Date.parse(String(right.lastOperationAt || '')) || 0;
      return rightTs - leftTs;
    })
    .slice(0, limit);
};

export const summarizeCloudExecutionHighlights = (ledgerRows = [], { limit = 4 } = {}) => {
  return (Array.isArray(ledgerRows) ? ledgerRows : [])
    .flatMap((row) => {
      const accountId = Number(row?.account_id || 0);
      if (!Number.isFinite(accountId) || accountId <= 0) return [];
      const name = String(row?.account_name || '').trim() || `Account ${accountId}`;
      const provider = String(row?.provider || '').trim().toUpperCase() || 'CLOUD';
      const latestApprovalId = Number(row?.latest_approval_id || 0) || null;
      const recentOperations = Array.isArray(row?.recent_operations) ? row.recent_operations.slice(0, 2) : [];
      return recentOperations.map((operation, index) => ({
        key: `${accountId}:${String(operation?.event_type || operation?.label || 'operation')}:${String(operation?.timestamp || index)}`,
        accountId,
        name,
        provider,
        latestApprovalId,
        label: String(operation?.label || operation?.event_type || 'Operation'),
        summary: String(operation?.summary || '').trim(),
        status: String(operation?.status || '').trim().toLowerCase(),
        timestamp: operation?.timestamp || null,
        failureReasonCode: String(operation?.failure_reason_code || '').trim().toLowerCase(),
        failureReasonLabel: String(operation?.failure_reason_label || '').trim(),
      }));
    })
    .sort((left, right) => {
      const leftTs = Date.parse(String(left.timestamp || '')) || 0;
      const rightTs = Date.parse(String(right.timestamp || '')) || 0;
      return rightTs - leftTs;
    })
    .slice(0, limit);
};

export const summarizeCloudScheduleQueue = (ledgerRows = [], translate = t, { limit = 3 } = {}) => {
  return (Array.isArray(ledgerRows) ? ledgerRows : [])
    .map((row) => {
      const accountId = Number(row?.account_id || 0);
      if (!Number.isFinite(accountId) || accountId <= 0) return null;
      const name = String(row?.account_name || '').trim() || `Account ${accountId}`;
      const provider = String(row?.provider || '').trim().toUpperCase() || 'CLOUD';
      const pendingApprovals = Number(row?.pending_approvals || 0);
      const retryRecommended = Boolean(row?.retry_recommended);
      const posture = String(row?.operations_posture || '').trim().toLowerCase();
      const latestApprovalId = Number(row?.latest_approval_id || 0) || null;
      const lastAttemptAt = row?.last_attempt_at || row?.last_operation_at || null;

      let title = translate('cloud_accounts_ledger_schedule_stable_title', 'Stable checkpoint');
      let description = translate(
        'cloud_accounts_ledger_schedule_stable_desc',
        'No immediate rerun is needed. Return here when service pressure, approval context, or drift signals change.',
      );
      let windowLabel = translate('cloud_accounts_ledger_schedule_daily', 'Daily review');
      let priority = 12;

      if (pendingApprovals > 0) {
        title = translate('cloud_accounts_ledger_schedule_pending_title', 'Approval checkpoint');
        description = translate(
          'cloud_accounts_ledger_schedule_pending_desc',
          'Review this account again as soon as the pending approval path changes so execution can continue on the right lane.',
        );
        windowLabel = translate('cloud_accounts_ledger_schedule_now', 'Review now');
        priority = 42 + pendingApprovals;
      } else if (retryRecommended) {
        title = translate('cloud_accounts_ledger_schedule_retry_title', 'Recovery checkpoint');
        description = translate(
          'cloud_accounts_ledger_schedule_retry_desc_fmt',
          'Run the recommended recovery action, then reopen this review after the next execution result lands.',
        );
        windowLabel = translate('cloud_accounts_ledger_schedule_after_result', 'After next result');
        priority = 34;
      } else if (posture === 'syncing') {
        title = translate('cloud_accounts_ledger_schedule_sync_title', 'Sync checkpoint');
        description = translate(
          'cloud_accounts_ledger_schedule_sync_desc',
          'Check this account again after the current discovery cycle finishes and the inventory baseline settles.',
        );
        windowLabel = translate('cloud_accounts_ledger_schedule_after_sync', 'After sync completes');
        priority = 24;
      }

      return {
        accountId,
        name,
        provider,
        title,
        description,
        windowLabel,
        latestApprovalId,
        lastAttemptAt,
        priority,
      };
    })
    .filter(Boolean)
    .sort((left, right) => {
      if (right.priority !== left.priority) return right.priority - left.priority;
      const leftTs = Date.parse(String(left.lastAttemptAt || '')) || 0;
      const rightTs = Date.parse(String(right.lastAttemptAt || '')) || 0;
      return rightTs - leftTs;
    })
    .slice(0, limit);
};

export const getCloudPressureIndex = (summary) => {
  const total = Math.max(1, Number(summary?.total || 0));
  const attention = Number(summary?.attention || 0);
  const syncing = Number(summary?.syncing || 0);
  const pendingApprovals = Number(summary?.pendingApprovals || 0);
  const retryRecommended = Number(summary?.retryRecommended || 0);
  const weighted =
    (attention * 24)
    + (syncing * 10)
    + (Math.min(pendingApprovals, total * 2) * 9)
    + (retryRecommended * 14);
  const max = Math.max(20, total * 24);
  return Math.min(100, Math.round((weighted / max) * 100));
};

export const recommendCloudOperationsWorkspace = (summary) => {
  const attention = Number(summary?.attention || 0);
  const syncing = Number(summary?.syncing || 0);
  const pendingApprovals = Number(summary?.pendingApprovals || 0);
  const retryRecommended = Number(summary?.retryRecommended || 0);

  if (pendingApprovals > 0) return { workspace: 'govern', reason: 'approval' };
  if (attention > 0 || retryRecommended > 0) return { workspace: 'control', reason: 'recovery' };
  if (syncing > 0) return { workspace: 'discover', reason: 'sync' };
  return { workspace: 'observe', reason: 'stable' };
};

export const summarizeObservabilityPressure = ({ summary, unreadCount = 0 } = {}) => {
  const counts = summary?.counts || {};
  const devices = Number(counts?.devices || 0);
  const online = Number(counts?.online || 0);
  const offline = Math.max(0, Number(counts?.offline || 0));
  return {
    devices,
    online,
    offline,
    unreadCount: Number(unreadCount || 0),
  };
};

export const getObservabilityPressureIndex = (summary) => {
  const devices = Math.max(1, Number(summary?.devices || 0));
  const offline = Number(summary?.offline || 0);
  const unread = Number(summary?.unreadCount || 0);
  const weighted =
    (Math.min(offline, devices) * 24)
    + (Math.min(unread, devices * 2) * 10);
  const max = Math.max(20, devices * 24);
  return Math.min(100, Math.round((weighted / max) * 100));
};

export const recommendObservabilityWorkspace = (summary) => {
  const offline = Number(summary?.offline || 0);
  const unread = Number(summary?.unreadCount || 0);
  const devices = Number(summary?.devices || 0);
  if (offline > 0 || unread > 0) return { workspace: 'observe', reason: 'signals' };
  if (devices <= 0) return { workspace: 'discover', reason: 'no_devices' };
  return { workspace: 'govern', reason: 'stable' };
};

export const getOperationsPrimaryPressure = (sections = []) => {
  const rows = (Array.isArray(sections) ? sections : []).filter(Boolean);
  if (rows.length === 0) return null;
  const sorted = [...rows].sort((left, right) => {
    const pressureDelta = Number(right?.pressureIndex || 0) - Number(left?.pressureIndex || 0);
    if (pressureDelta !== 0) return pressureDelta;
    return Number(right?.signalCount || 0) - Number(left?.signalCount || 0);
  });
  return sorted[0] || null;
};

export const getServiceImpactPriorityScore = (summary = {}) => {
  const criticalGroupCount = Number(summary?.critical_group_count || summary?.criticalGroupCount || 0);
  const reviewGroupCount = Number(summary?.review_group_count || summary?.reviewGroupCount || 0);
  const impactCount = Number(summary?.count || summary?.groupCount || 0);
  const matchedMemberCount = Number(summary?.matched_member_count || summary?.matchedMemberCount || 0);
  const primaryHealthStatus = String(summary?.primary_health_status || summary?.primaryHealthStatus || '').trim().toLowerCase();
  const primaryHealthScore = Number(summary?.primary_health_score || summary?.primaryHealthScore || 0);
  const statusWeight =
    primaryHealthStatus === 'critical'
      ? 28
      : ['degraded', 'review'].includes(primaryHealthStatus)
        ? 14
        : primaryHealthStatus === 'healthy'
          ? 4
          : 0;
  const score =
    (criticalGroupCount * 48)
    + (reviewGroupCount * 18)
    + (impactCount * 6)
    + (matchedMemberCount * 3)
    + statusWeight
    + Math.max(0, 100 - Math.min(100, primaryHealthScore));
  return score;
};

export const compareServiceImpactAlerts = (left, right) => {
  const severityRank = { critical: 3, warning: 2, info: 1 };
  const toTimestamp = (value) => {
    const parsed = Date.parse(String(value || ''));
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const leftSummary = left?.service_impact_summary || {};
  const rightSummary = right?.service_impact_summary || {};
  const scoreDelta = getServiceImpactPriorityScore(rightSummary) - getServiceImpactPriorityScore(leftSummary);
  if (scoreDelta !== 0) return scoreDelta;
  const rightUnread = right?.is_read ? 0 : 1;
  const leftUnread = left?.is_read ? 0 : 1;
  if (rightUnread !== leftUnread) return rightUnread - leftUnread;
  const rightSeverity = severityRank[String(right?.severity || '').toLowerCase()] || 0;
  const leftSeverity = severityRank[String(left?.severity || '').toLowerCase()] || 0;
  if (rightSeverity !== leftSeverity) return rightSeverity - leftSeverity;
  return toTimestamp(right?.time || right?.created_at) - toTimestamp(left?.time || left?.created_at);
};

export const summarizeServiceImpactAlertFocus = (alert, translate = t) => {
  if (!alert) return null;
  const summary = alert?.service_impact_summary || {};
  const criticalGroups = Number(summary?.critical_group_count || 0);
  const reviewGroups = Number(summary?.review_group_count || 0);
  const matchedAssets = Number(summary?.matched_member_count || 0);
  return {
    issueId: Number(alert?.id || 0),
    groupId: Number(summary?.primary_group_id || 0),
    groupName: String(summary?.primary_name || '').trim() || translate('dashboard_service_impact_unknown_group', 'Mapped service group'),
    healthStatus: String(summary?.primary_health_status || 'review').trim().toLowerCase() || 'review',
    healthScore: Number(summary?.primary_health_score || 0),
    criticalGroups,
    reviewGroups,
    matchedAssets,
    nextAction: getServicePriorityNextAction({
      primaryHealthStatus: summary?.primary_health_status,
      criticalGroupCount: criticalGroups,
      reviewGroupCount: reviewGroups,
      matchedMemberCount: matchedAssets,
    }, translate),
  };
};

export const getServicePriorityNextAction = (summary, translate = t) => {
  const healthStatus = String(summary?.healthStatus || summary?.primaryHealthStatus || 'healthy').trim().toLowerCase();
  const criticalGroupCount = Number(summary?.criticalGroupCount || summary?.critical_issue_count || 0);
  const reviewGroupCount = Number(summary?.reviewGroupCount || 0);
  const activeIssueCount = Number(summary?.activeIssueCount || summary?.active_issue_count || 0);
  const offlineDeviceCount = Number(summary?.offlineDeviceCount || summary?.offline_device_count || 0);
  const discoveredOnlyDeviceCount = Number(summary?.discoveredOnlyDeviceCount || summary?.discovered_only_device_count || 0);
  const managedDeviceCount = Number(summary?.managedDeviceCount || summary?.managed_device_count || 0);
  const matchedMemberCount = Number(summary?.matchedMemberCount || summary?.matched_member_count || 0);

  if (healthStatus === 'critical' || criticalGroupCount > 0) {
    return translate('service_groups_review_next_action_critical', 'Open service-aware alerts and topology first to review the highest-impact path.');
  }
  if (offlineDeviceCount > 0) {
    return translate('service_groups_review_next_action_offline', 'Inspect offline devices and the attached path before pushing additional changes.');
  }
  if (discoveredOnlyDeviceCount > managedDeviceCount) {
    return translate('service_groups_review_next_action_discovered_only', 'Many assets are still discovered-only. Review which devices should be promoted into managed monitoring.');
  }
  if (activeIssueCount > 0) {
    return translate('service_groups_review_next_action_issues', 'Review the service-aware alerts and follow-up actions in operations reports.');
  }
  if (reviewGroupCount > 0 || matchedMemberCount > 0 || ['degraded', 'review'].includes(healthStatus)) {
    return translate('service_groups_review_next_action_review', 'Open the service review to align alerts, reports, and service context before more changes spread.');
  }
  return translate('service_groups_review_next_action_stable', 'Keep this service baseline stable and review the mapped topology when needed.');
};

export const summarizeServiceReviewQueue = (groups = [], translate = t, { limit = 4 } = {}) => {
  const statusRank = {
    critical: 0,
    degraded: 1,
    review: 1,
    healthy: 2,
  };
  const criticalityRank = {
    high: 0,
    elevated: 1,
    standard: 2,
  };

  return (Array.isArray(groups) ? groups : [])
    .map((group) => {
      const health = group?.health || {};
      const healthStatus = String(health.health_status || 'healthy').trim().toLowerCase() || 'healthy';
      const activeIssueCount = Number(health.active_issue_count || 0);
      const criticalIssueCount = Number(health.critical_issue_count || 0);
      const offlineDeviceCount = Number(health.offline_device_count || 0);
      const discoveredOnlyDeviceCount = Number(health.discovered_only_device_count || 0);
      const managedDeviceCount = Number(health.managed_device_count || 0);
      const healthScore = Number(health.health_score || 0);
      const criticality = String(group?.criticality || 'standard').trim().toLowerCase() || 'standard';
      const reviewNeeded = ['critical', 'degraded', 'review'].includes(healthStatus) || activeIssueCount > 0 || offlineDeviceCount > 0;
      return {
        ...group,
        reviewNeeded,
        healthStatus,
        healthScore,
        activeIssueCount,
        criticalIssueCount,
        offlineDeviceCount,
        managedDeviceCount,
        discoveredOnlyDeviceCount,
        nextAction: getServicePriorityNextAction({
          healthStatus,
          criticalGroupCount: criticalIssueCount,
          activeIssueCount,
          offlineDeviceCount,
          discoveredOnlyDeviceCount,
          managedDeviceCount,
        }, translate),
        sortKey: [
          statusRank[healthStatus] ?? 3,
          criticalityRank[criticality] ?? 3,
          -criticalIssueCount,
          -activeIssueCount,
          -offlineDeviceCount,
          healthScore,
        ],
      };
    })
    .filter((group) => group.reviewNeeded)
    .sort((a, b) => {
      for (let index = 0; index < Math.max(a.sortKey.length, b.sortKey.length); index += 1) {
        const left = a.sortKey[index] ?? 0;
        const right = b.sortKey[index] ?? 0;
        if (left !== right) return left - right;
      }
      return String(a.name || '').localeCompare(String(b.name || ''));
    })
    .slice(0, limit);
};
