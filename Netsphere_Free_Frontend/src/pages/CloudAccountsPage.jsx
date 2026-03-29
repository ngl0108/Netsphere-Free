import React, { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Cloud, Pencil, Plus, RefreshCw, Save, ShieldCheck, Trash2, X } from 'lucide-react';
import { ApprovalService, CloudService } from '../api/services';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import { t } from '../i18n';
import { InlineEmpty, InlineLoading, SectionCard, SectionHeader } from '../components/common/PageState';
import { getWorkspaceTitle, recommendCloudWorkspace } from '../utils/serviceOperations';

const Field = ({ label, children }) => (
  <div>
    <div className="text-[10px] uppercase font-bold text-gray-500 mb-1.5">{label}</div>
    {children}
  </div>
);

const Input = ({ value, onChange, placeholder, type = 'text' }) => (
  <input
    value={value}
    onChange={(e) => onChange(e.target.value)}
    placeholder={placeholder}
    type={type}
    className="w-full bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-gray-900 dark:text-white text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
  />
);

const Select = ({ value, onChange, options, disabled = false }) => (
  <select
    value={value}
    onChange={(e) => onChange(e.target.value)}
    disabled={disabled}
    className="w-full bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-gray-900 dark:text-white text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all disabled:opacity-60"
  >
    {options.map((o) => (
      <option key={o.value} value={o.value}>{o.label}</option>
    ))}
  </select>
);

const ACTION_BUTTON_BASE =
  'h-9 px-3 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors';
const ACTION_BUTTON_NEUTRAL =
  `${ACTION_BUTTON_BASE} bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-[#1f2227]`;
const ACTION_BUTTON_PRIMARY =
  `${ACTION_BUTTON_BASE} text-white`;

const readinessToneClass = (stage) => {
  const value = String(stage || '').trim().toLowerCase();
  if (value === 'real_apply_ready') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300';
  if (value === 'scaffold_ready') return 'bg-sky-100 text-sky-700 dark:bg-sky-900/20 dark:text-sky-300';
  if (value === 'credentials_missing') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300';
  return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
};

const readinessLabel = (stage, translate) => {
  const value = String(stage || '').trim().toLowerCase();
  if (value === 'real_apply_ready') return translate('cloud_accounts_exec_ready', 'Ready for real apply');
  if (value === 'scaffold_ready') return translate('cloud_accounts_exec_scaffold', 'Scaffold only');
  if (value === 'credentials_missing') return translate('cloud_accounts_exec_missing', 'Credentials missing');
  return translate('cloud_accounts_exec_unknown', 'Execution unknown');
};

const resolveChangeMode = (readiness) => {
  if (readiness?.change_enabled === true) return 'change_enabled';
  if (readiness?.change_mode) return String(readiness.change_mode);
  const stage = String(readiness?.stage || '').trim().toLowerCase();
  if (stage === 'real_apply_ready') return 'change_enabled';
  return 'read_only';
};

const changeModeClass = (readiness) => {
  const value = String(resolveChangeMode(readiness) || '').trim().toLowerCase();
  if (value === 'change_enabled') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300';
  return 'bg-amber-100 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300';
};

const changeModeLabel = (readiness, translate) => {
  const value = String(resolveChangeMode(readiness) || '').trim().toLowerCase();
  if (value === 'change_enabled') return translate('cloud_accounts_change_enabled', 'Change enabled');
  return translate('cloud_accounts_read_only_mode', 'Read-only');
};

const operationsPostureClass = (value) => {
  const posture = String(value || '').trim().toLowerCase();
  if (posture === 'stable') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300';
  if (posture === 'syncing') return 'bg-sky-100 text-sky-700 dark:bg-sky-900/20 dark:text-sky-300';
  if (posture === 'approval_pending') return 'bg-violet-100 text-violet-700 dark:bg-violet-900/20 dark:text-violet-300';
  if (posture === 'attention') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300';
  return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
};

const operationsPostureLabel = (value, translate) => {
  const posture = String(value || '').trim().toLowerCase();
  if (posture === 'stable') return translate('cloud_accounts_ledger_posture_stable', 'Stable');
  if (posture === 'syncing') return translate('cloud_accounts_ledger_posture_syncing', 'Syncing');
  if (posture === 'approval_pending') return translate('cloud_accounts_ledger_posture_approval_pending', 'Approval pending');
  if (posture === 'attention') return translate('cloud_accounts_ledger_posture_attention', 'Needs review');
  return translate('cloud_accounts_ledger_posture_unknown', 'Unknown');
};

const ledgerOperationToneClass = (status) => {
  const value = String(status || '').trim().toLowerCase();
  if (value === 'ok' || value === 'success') return 'text-emerald-600 dark:text-emerald-300';
  if (value === 'queued' || value === 'running') return 'text-sky-600 dark:text-sky-300';
  return 'text-amber-600 dark:text-amber-300';
};

const ledgerFailureReasonLabel = (reasonCode, translate, fallbackLabel = '') => {
  const value = String(reasonCode || '').trim().toLowerCase();
  if (value === 'permission_issue') return translate('cloud_accounts_ledger_reason_permission_issue', 'Permission issue');
  if (value === 'credential_issue') return translate('cloud_accounts_ledger_reason_credential_issue', 'Credential issue');
  if (value === 'connectivity_issue') return translate('cloud_accounts_ledger_reason_connectivity_issue', 'Connectivity issue');
  if (value === 'policy_blocked') return translate('cloud_accounts_ledger_reason_policy_blocked', 'Policy blocked');
  if (value === 'scope_issue') return translate('cloud_accounts_ledger_reason_scope_issue', 'Scope issue');
  if (value === 'operation_failed') return translate('cloud_accounts_ledger_reason_operation_failed', 'Operation failed');
  return String(fallbackLabel || '').trim() || translate('cloud_accounts_ledger_reason_unknown', 'Unknown reason');
};

const ledgerFailureReasonClass = (reasonCode) => {
  const value = String(reasonCode || '').trim().toLowerCase();
  if (value === 'permission_issue' || value === 'credential_issue') {
    return 'bg-rose-100 text-rose-700 dark:bg-rose-900/20 dark:text-rose-300';
  }
  if (value === 'connectivity_issue' || value === 'scope_issue') {
    return 'bg-amber-100 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300';
  }
  if (value === 'policy_blocked') {
    return 'bg-violet-100 text-violet-700 dark:bg-violet-900/20 dark:text-violet-300';
  }
  return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
};

const buildLedgerRetryBlueprint = (ledger, translate) => {
  const retryableOp = Array.isArray(ledger?.recent_operations)
    ? ledger.recent_operations.find((op) => op?.retryable)
    : null;
  const eventType = String(retryableOp?.event_type || ledger?.last_operation_type || '').trim().toLowerCase();

  if (eventType === 'preflight') {
    return {
      key: 'validate',
      label: translate('cloud_accounts_ledger_retry_validate', 'Retry Validate'),
      desc: translate(
        'cloud_accounts_ledger_retry_validate_desc',
        'Run validation again to confirm access and refresh readiness before changing anything else.',
      ),
    };
  }
  if (eventType === 'scan') {
    return {
      key: 'scan',
      label: translate('cloud_accounts_ledger_retry_scan', 'Retry Scan'),
      desc: translate(
        'cloud_accounts_ledger_retry_scan_desc',
        'Refresh raw discovery again when the last account scan did not complete cleanly.',
      ),
    };
  }
  if (eventType === 'pipeline') {
    return {
      key: 'pipeline',
      label: translate('cloud_accounts_ledger_retry_pipeline', 'Retry Pipeline'),
      desc: translate(
        'cloud_accounts_ledger_retry_pipeline_desc',
        'Re-run the read-only pipeline so preflight, scan, and normalization can recover together.',
      ),
    };
  }
  if (eventType === 'bootstrap') {
    return {
      key: 'bootstrap_dry_run',
      label: translate('cloud_accounts_ledger_retry_bootstrap_dry_run', 'Retry Bootstrap Dry-Run'),
      desc: translate(
        'cloud_accounts_ledger_retry_bootstrap_dry_run_desc',
        'Use a dry-run first to verify bootstrap reachability and guardrails before any live execution.',
      ),
    };
  }
  return null;
};

const buildLedgerReviewGuide = (ledger, translate) => {
  const code = String(ledger?.last_failure_reason_code || '').trim().toLowerCase();

  if (code === 'credential_issue') {
    return {
      title: translate('cloud_accounts_ledger_review_credentials_title', 'Credential review'),
      bullets: [
        translate('cloud_accounts_ledger_review_credentials_1', 'Check the masked credential set for missing keys or expired secrets.'),
        translate('cloud_accounts_ledger_review_credentials_2', 'Run validation first, then continue to scan or pipeline only after it passes.'),
        translate('cloud_accounts_ledger_review_credentials_3', 'Keep this account in read-only mode until validation is stable again.'),
      ],
    };
  }
  if (code === 'permission_issue') {
    return {
      title: translate('cloud_accounts_ledger_review_permissions_title', 'Permission review'),
      bullets: [
        translate('cloud_accounts_ledger_review_permissions_1', 'Recheck IAM, service principal, or provider role scopes for this account.'),
        translate('cloud_accounts_ledger_review_permissions_2', 'Retry validation after the missing read permissions are restored.'),
        translate('cloud_accounts_ledger_review_permissions_3', 'Use approval-gated changes only after the account is back to a healthy validation path.'),
      ],
    };
  }
  if (code === 'connectivity_issue') {
    return {
      title: translate('cloud_accounts_ledger_review_connectivity_title', 'Connectivity review'),
      bullets: [
        translate('cloud_accounts_ledger_review_connectivity_1', 'Verify outbound connectivity, proxy settings, and provider API reachability from this runtime.'),
        translate('cloud_accounts_ledger_review_connectivity_2', 'Retry validate or scan after the network path is confirmed healthy.'),
        translate('cloud_accounts_ledger_review_connectivity_3', 'Keep using the last good inventory snapshot until the account reconnects cleanly.'),
      ],
    };
  }
  if (code === 'policy_blocked') {
    return {
      title: translate('cloud_accounts_ledger_review_policy_title', 'Policy review'),
      bullets: [
        translate('cloud_accounts_ledger_review_policy_1', 'Review blockers, pending approvals, and pre-check findings before retrying any live path.'),
        translate('cloud_accounts_ledger_review_policy_2', 'Resolve the guardrail condition on the safe path first, then return to the change workflow.'),
        translate('cloud_accounts_ledger_review_policy_3', 'Use the linked approval context when this account is waiting on a controlled action.'),
      ],
    };
  }
  if (code === 'scope_issue') {
    return {
      title: translate('cloud_accounts_ledger_review_scope_title', 'Scope review'),
      bullets: [
        translate('cloud_accounts_ledger_review_scope_1', 'Recheck account scope, region filters, target tags, and resource selectors.'),
        translate('cloud_accounts_ledger_review_scope_2', 'Narrow the target set first, then rerun validate or scan against the corrected scope.'),
        translate('cloud_accounts_ledger_review_scope_3', 'Use topology and service context to confirm the intended cloud resources are actually in scope.'),
      ],
    };
  }
  return {
    title: translate('cloud_accounts_ledger_review_generic_title', 'Operations review'),
    bullets: [
      translate('cloud_accounts_ledger_review_generic_1', 'Review the latest operation summary and any recorded blockers before retrying.'),
      translate('cloud_accounts_ledger_review_generic_2', 'Retry the safest available action first so the account can recover on the read-only path.'),
      translate('cloud_accounts_ledger_review_generic_3', 'Escalate to approval or a follow-up action when the same failure repeats.'),
    ],
  };
};

const buildLedgerDriftSummary = (account, ledger, translate) => {
  const posture = String(ledger?.operations_posture || '').trim().toLowerCase();
  const syncStatus = String(account?.sync_status || '').trim().toLowerCase();
  const failureCode = String(ledger?.last_failure_reason_code || '').trim().toLowerCase();

  if (posture === 'approval_pending') {
    return {
      tone: 'violet',
      title: translate('cloud_accounts_ledger_drift_pending_title', 'Change drift held behind approval'),
      description: translate(
        'cloud_accounts_ledger_drift_pending_desc',
        'This account is waiting on approval before the intended cloud state can converge. Review the approval context first.',
      ),
    };
  }
  if (posture === 'syncing') {
    return {
      tone: 'sky',
      title: translate('cloud_accounts_ledger_drift_syncing_title', 'Inventory refresh in progress'),
      description: translate(
        'cloud_accounts_ledger_drift_syncing_desc',
        'Discovery or normalization is still running, so the last known state may move again before the next review.',
      ),
    };
  }
  if (syncStatus === 'failed' || syncStatus === 'error' || failureCode) {
    return {
      tone: 'amber',
      title: translate('cloud_accounts_ledger_drift_attention_title', 'Inventory drift risk'),
      description: translate(
        'cloud_accounts_ledger_drift_attention_desc',
        'The latest account state could be stale or incomplete until validation, scan, or pipeline recovery succeeds again.',
      ),
    };
  }
  return {
    tone: 'emerald',
    title: translate('cloud_accounts_ledger_drift_stable_title', 'Inventory baseline looks stable'),
    description: translate(
      'cloud_accounts_ledger_drift_stable_desc',
      'Recent account operations are healthy enough to treat the current inventory as a trustworthy operating baseline.',
    ),
  };
};

const ledgerDriftToneClass = (tone) => {
  if (tone === 'violet') return 'border-violet-200 bg-violet-50/70 text-violet-800 dark:border-violet-900/40 dark:bg-violet-950/20 dark:text-violet-200';
  if (tone === 'sky') return 'border-sky-200 bg-sky-50/70 text-sky-800 dark:border-sky-900/40 dark:bg-sky-950/20 dark:text-sky-200';
  if (tone === 'amber') return 'border-amber-200 bg-amber-50/70 text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200';
  return 'border-emerald-200 bg-emerald-50/70 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200';
};

const buildProviderRunbook = (account, translate) => {
  const provider = String(account?.provider || '').trim().toLowerCase();
  if (provider === 'aws') {
    return {
      title: translate('cloud_accounts_runbook_aws_title', 'AWS operator runbook'),
      bullets: [
        translate('cloud_accounts_runbook_aws_1', 'Check IAM policy scope, STS identity, and regional API reachability before retrying the account path.'),
        translate('cloud_accounts_runbook_aws_2', 'Confirm whether UserData or SSM is the intended bootstrap path before opening a live change request.'),
      ],
    };
  }
  if (provider === 'azure') {
    return {
      title: translate('cloud_accounts_runbook_azure_title', 'Azure operator runbook'),
      bullets: [
        translate('cloud_accounts_runbook_azure_1', 'Verify the service principal, subscription scope, and Azure RunCommand prerequisites for this subscription.'),
        translate('cloud_accounts_runbook_azure_2', 'Treat validation as the safe gate before scans or approval-backed change paths resume.'),
      ],
    };
  }
  if (provider === 'gcp') {
    return {
      title: translate('cloud_accounts_runbook_gcp_title', 'GCP operator runbook'),
      bullets: [
        translate('cloud_accounts_runbook_gcp_1', 'Recheck service-account permissions, enabled APIs, and startup-script metadata expectations for the target project.'),
        translate('cloud_accounts_runbook_gcp_2', 'Use scan recovery first so inventory and topology converge again before opening change work.'),
      ],
    };
  }
  if (provider === 'ncp' || provider === 'naver' || provider === 'naver_cloud') {
    return {
      title: translate('cloud_accounts_runbook_naver_title', 'Naver Cloud operator runbook'),
      bullets: [
        translate('cloud_accounts_runbook_naver_1', 'Check NCP access keys, region scope, and any VPC-specific discovery boundaries before retrying.'),
        translate('cloud_accounts_runbook_naver_2', 'Use topology and service context to confirm the intended subnet, gateway, or tunnel resources are still in scope.'),
      ],
    };
  }
  return {
    title: translate('cloud_accounts_runbook_generic_title', 'Cloud operator runbook'),
    bullets: [
      translate('cloud_accounts_runbook_generic_1', 'Recheck credential health, provider reachability, and target scope before retrying the last failed operation.'),
      translate('cloud_accounts_runbook_generic_2', 'Prefer the read-only recovery path first, then move to approval-backed changes when the account is stable again.'),
    ],
  };
};

const buildLedgerExecutionTimeline = (ledger, translate) => {
  const operations = Array.isArray(ledger?.recent_operations) ? ledger.recent_operations.slice(0, 4) : [];
  if (!operations.length) {
    return {
      title: translate('cloud_accounts_ledger_timeline_empty_title', 'No recent execution history'),
      description: translate(
        'cloud_accounts_ledger_timeline_empty_desc',
        'This account has not recorded validate, scan, pipeline, or bootstrap activity yet.',
      ),
      items: [],
    };
  }

  const lastOk = operations.find((op) => ['ok', 'success'].includes(String(op?.status || '').trim().toLowerCase()));
  const lastFailure = operations.find((op) => !['ok', 'success', 'queued', 'running', 'syncing'].includes(String(op?.status || '').trim().toLowerCase()));
  const retryableCount = operations.filter((op) => op?.retryable).length;

  return {
    title: translate('cloud_accounts_ledger_timeline_title', 'Recent execution history'),
    description: translate(
      'cloud_accounts_ledger_timeline_desc_fmt',
      'Last success: {lastSuccess} | Last failure: {lastFailure} | Retryable lanes: {retryable}',
    )
      .replace('{lastSuccess}', String(lastOk?.label || translate('cloud_accounts_ledger_timeline_none', 'None')))
      .replace('{lastFailure}', String(lastFailure?.label || translate('cloud_accounts_ledger_timeline_none', 'None')))
      .replace('{retryable}', String(retryableCount)),
    items: operations,
  };
};

const buildLedgerNextLane = (ledger, retryBlueprint, translate) => {
  const pendingApprovals = Number(ledger?.pending_approvals || 0);
  const posture = String(ledger?.operations_posture || '').trim().toLowerCase();

  if (pendingApprovals > 0) {
    return {
      tone: 'violet',
      title: translate('cloud_accounts_ledger_lane_approval_title', 'Approval follow-up lane'),
      description: translate(
        'cloud_accounts_ledger_lane_approval_desc',
        'An approval is still pending, so the safest next move is to review the approval context before retrying account execution.',
      ),
    };
  }
  if (retryBlueprint) {
    return {
      tone: 'rose',
      title: translate('cloud_accounts_ledger_lane_retry_title', 'Recovery lane'),
      description: translate(
        'cloud_accounts_ledger_lane_retry_desc_fmt',
        'Use {action} first so the account can recover on the safest available path.',
      ).replace('{action}', String(retryBlueprint.label || translate('cloud_accounts_ledger_next_step', 'Recommended next step'))),
    };
  }
  if (posture === 'syncing') {
    return {
      tone: 'sky',
      title: translate('cloud_accounts_ledger_lane_sync_title', 'Sync observation lane'),
      description: translate(
        'cloud_accounts_ledger_lane_sync_desc',
        'Discovery is still converging. Watch the latest scan and normalization results before pushing another action.',
      ),
    };
  }
  return {
    tone: 'emerald',
    title: translate('cloud_accounts_ledger_lane_stable_title', 'Stable operating lane'),
    description: translate(
      'cloud_accounts_ledger_lane_stable_desc',
      'This account is on a stable operating path. Continue from review, observability, or approval only when a new signal appears.',
    ),
  };
};

const ledgerNextLaneToneClass = (tone) => {
  if (tone === 'violet') return 'border-violet-200 bg-violet-50/70 text-violet-800 dark:border-violet-900/40 dark:bg-violet-950/20 dark:text-violet-200';
  if (tone === 'rose') return 'border-rose-200 bg-rose-50/70 text-rose-800 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200';
  if (tone === 'sky') return 'border-sky-200 bg-sky-50/70 text-sky-800 dark:border-sky-900/40 dark:bg-sky-950/20 dark:text-sky-200';
  return 'border-emerald-200 bg-emerald-50/70 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200';
};

const buildLedgerCadenceSummary = (ledger, retryBlueprint, translate) => {
  const pendingApprovals = Number(ledger?.pending_approvals || 0);
  const posture = String(ledger?.operations_posture || '').trim().toLowerCase();
  const latestType = String(ledger?.last_operation_type || '').trim().toLowerCase();

  const latestTypeLabel =
    latestType === 'preflight'
      ? translate('cloud_accounts_ledger_cadence_validate', 'Validate lane')
      : latestType === 'scan'
        ? translate('cloud_accounts_ledger_cadence_scan', 'Scan lane')
        : latestType === 'pipeline'
          ? translate('cloud_accounts_ledger_cadence_pipeline', 'Pipeline lane')
          : latestType === 'bootstrap'
            ? translate('cloud_accounts_ledger_cadence_bootstrap', 'Bootstrap lane')
            : translate('cloud_accounts_ledger_cadence_general', 'Operations lane');

  if (pendingApprovals > 0) {
    return {
      tone: 'violet',
      title: translate('cloud_accounts_ledger_cadence_pending_title', 'Approval queue cadence'),
      description: translate(
        'cloud_accounts_ledger_cadence_pending_desc',
        'Stay on the approval queue first. Recheck the ledger after the pending request is approved or rejected.',
      ),
      laneLabel: latestTypeLabel,
    };
  }
  if (retryBlueprint) {
    return {
      tone: 'rose',
      title: translate('cloud_accounts_ledger_cadence_retry_title', 'Recovery cadence'),
      description: translate(
        'cloud_accounts_ledger_cadence_retry_desc_fmt',
        'Run {action} now, then check this ledger again after the next execution result lands.',
      ).replace('{action}', String(retryBlueprint.label || translate('cloud_accounts_ledger_next_step', 'Recommended next step'))),
      laneLabel: latestTypeLabel,
    };
  }
  if (posture === 'syncing') {
    return {
      tone: 'sky',
      title: translate('cloud_accounts_ledger_cadence_sync_title', 'Sync watch cadence'),
      description: translate(
        'cloud_accounts_ledger_cadence_sync_desc',
        'Let the current discovery cycle finish, then reopen the ledger to confirm scan and normalization have converged.',
      ),
      laneLabel: latestTypeLabel,
    };
  }
  return {
    tone: 'emerald',
    title: translate('cloud_accounts_ledger_cadence_stable_title', 'Stable review cadence'),
    description: translate(
      'cloud_accounts_ledger_cadence_stable_desc',
      'No immediate rerun is needed. Return here when service pressure, approval context, or drift signals change.',
    ),
    laneLabel: latestTypeLabel,
  };
};

const buildLedgerScheduleSummary = (ledger, retryBlueprint, translate) => {
  const pendingApprovals = Number(ledger?.pending_approvals || 0);
  const posture = String(ledger?.operations_posture || '').trim().toLowerCase();
  const lastAttemptAt = ledger?.last_attempt_at || ledger?.last_operation_at || null;

  if (pendingApprovals > 0) {
    return {
      tone: 'violet',
      title: translate('cloud_accounts_ledger_schedule_pending_title', 'Approval checkpoint'),
      description: translate(
        'cloud_accounts_ledger_schedule_pending_desc',
        'Review this account again as soon as the pending approval path changes so execution can continue on the right lane.',
      ),
      windowLabel: translate('cloud_accounts_ledger_schedule_now', 'Review now'),
      lastAttemptAt,
    };
  }
  if (retryBlueprint) {
    return {
      tone: 'rose',
      title: translate('cloud_accounts_ledger_schedule_retry_title', 'Recovery checkpoint'),
      description: translate(
        'cloud_accounts_ledger_schedule_retry_desc_fmt',
        'Run {action}, then reopen this review after the next execution result lands so you can confirm recovery.',
      ).replace('{action}', String(retryBlueprint.label || translate('cloud_accounts_ledger_next_step', 'Recommended next step'))),
      windowLabel: translate('cloud_accounts_ledger_schedule_after_result', 'After next result'),
      lastAttemptAt,
    };
  }
  if (posture === 'syncing') {
    return {
      tone: 'sky',
      title: translate('cloud_accounts_ledger_schedule_sync_title', 'Sync checkpoint'),
      description: translate(
        'cloud_accounts_ledger_schedule_sync_desc',
        'Let the active sync cycle finish, then reopen this review to confirm inventory, topology, and policy signals have converged.',
      ),
      windowLabel: translate('cloud_accounts_ledger_schedule_after_sync', 'After sync completes'),
      lastAttemptAt,
    };
  }
  return {
    tone: 'emerald',
    title: translate('cloud_accounts_ledger_schedule_stable_title', 'Stable checkpoint'),
    description: translate(
      'cloud_accounts_ledger_schedule_stable_desc',
      'This account can stay on a lighter review rhythm until approval, drift, or service pressure changes.',
    ),
    windowLabel: translate('cloud_accounts_ledger_schedule_daily', 'Daily review'),
    lastAttemptAt,
  };
};

const getLedgerLaneKey = (ledger, retryBlueprint) => {
  const pendingApprovals = Number(ledger?.pending_approvals || 0);
  const posture = String(ledger?.operations_posture || '').trim().toLowerCase();
  if (pendingApprovals > 0) return 'approval';
  if (retryBlueprint) return 'recovery';
  if (posture === 'syncing') return 'sync';
  return 'stable';
};

const guardrailBadgeClass = (tone = 'info') => {
  if (tone === 'good') return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-800/60';
  if (tone === 'warn') return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-800/60';
  if (tone === 'bad') return 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:border-rose-800/60';
  return 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-800/60';
};

const buildGuardrailBadges = (account, translate) => {
  const readiness = account?.execution_readiness || {};
  const badges = [];
  const readOnly = resolveChangeMode(readiness) !== 'change_enabled';
  const readyForPreview = !!readiness?.ready_for_intent_preview;
  const readyForRealApply = !!readiness?.ready_for_real_apply;
  const liveApplyGuarded = readyForRealApply && readOnly;
  const missingFields = Array.isArray(readiness?.missing_fields) ? readiness.missing_fields : [];

  if (missingFields.length > 0) {
    badges.push({
      label: translate('cloud_accounts_credentials_incomplete', 'Credentials incomplete'),
      tone: 'bad',
    });
  } else if (readyForPreview) {
    badges.push({
      label: translate('cloud_accounts_preview_ready', 'Preview ready'),
      tone: 'info',
    });
  }

  if (readOnly) {
    badges.push({
      label: translate('cloud_accounts_safe_discovery', 'Validate / Pipeline / Scan only'),
      tone: 'info',
    });
  } else {
    badges.push({
      label: translate('cloud_accounts_change_path_ready', 'Approval-gated changes enabled'),
      tone: 'good',
    });
  }

  if (liveApplyGuarded) {
    badges.push({
      label: translate('cloud_accounts_live_apply_guarded', 'Live apply guarded'),
      tone: 'warn',
    });
  }

  return badges;
};

const CloudAccountsPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const { user, isAtLeast } = useAuth();
  const [loading, setLoading] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [provider, setProvider] = useState('aws');
  const [name, setName] = useState('');
  const [creds, setCreds] = useState({});
  const [editingAccountId, setEditingAccountId] = useState(null);
  const [presets, setPresets] = useState([]);
  const [preflightResult, setPreflightResult] = useState(null);
  const [pipelineResult, setPipelineResult] = useState(null);
  const [bootstrapResult, setBootstrapResult] = useState(null);
  const [cloudKpi, setCloudKpi] = useState(null);
  const [kpiLoading, setKpiLoading] = useState(false);
  const [operationsLedger, setOperationsLedger] = useState([]);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [ledgerRetryKey, setLedgerRetryKey] = useState('');
  const [expandedLedgerAccountId, setExpandedLedgerAccountId] = useState('');
  const [accountBootstrapPaths, setAccountBootstrapPaths] = useState({});
  const [savingBootstrapPaths, setSavingBootstrapPaths] = useState({});
  const [bootstrapPaths, setBootstrapPaths] = useState({
    aws: 'auto',
    azure: 'auto',
    gcp: 'startup_metadata',
  });
  const [focusedAccountId, setFocusedAccountId] = useState('');

  const canEdit = useMemo(() => isAtLeast('operator'), [isAtLeast]);
  const roleLabel = useMemo(() => {
    const roleKey = String(user?.role || '').trim().toLowerCase();
    if (roleKey === 'admin') return t('role_admin', 'Administrator');
    if (roleKey === 'operator') return t('role_operator', 'Operator');
    if (roleKey === 'viewer') return t('role_viewer', 'Viewer');
    return t('common_unknown', 'Unknown');
  }, [user?.role]);
  const roleAccessCopy = useMemo(() => {
    const roleKey = String(user?.role || '').trim().toLowerCase();
    if (roleKey === 'admin') {
      return t(
        'cloud_accounts_access_desc_admin',
        'Administrators can register credentials, review execution readiness, and keep cloud changes behind approval and runtime guardrails.',
      );
    }
    if (roleKey === 'operator') {
      return t(
        'cloud_accounts_access_desc_operator',
        'Operators can validate discovery paths and work with approval-gated cloud changes, but account policy and credential ownership should stay controlled.',
      );
    }
    return t(
      'cloud_accounts_access_desc_viewer',
      'Viewers can inspect readiness, discovery status, and account scope, but credential changes and live paths stay locked.',
    );
  }, [user?.role]);
  const activePreset = useMemo(
    () => presets.find((p) => String(p?.provider || '').toLowerCase() === String(provider || '').toLowerCase()) || null,
    [presets, provider],
  );
  const isEditMode = editingAccountId !== null && editingAccountId !== undefined && Number.isFinite(Number(editingAccountId));
  const actionGuide = [
      {
        key: 'validate',
        title: t('cloud_accounts_guide_validate_title', 'Validate'),
        desc: t('cloud_accounts_guide_validate_desc', 'Checks the credential and minimum read permission set. No resources are created or changed.'),
      },
      {
        key: 'pipeline',
        title: t('cloud_accounts_guide_pipeline_title', 'Pipeline'),
        desc: t('cloud_accounts_guide_pipeline_desc', 'Runs preflight, scans the account, normalizes cloud resources, and updates inventory/topology. Read-only flow.'),
      },
      {
        key: 'scan',
        title: t('cloud_accounts_guide_scan_title', 'Scan'),
        desc: t('cloud_accounts_guide_scan_desc', 'Refreshes raw discovery for one account only. Use this when you just want the latest resource snapshot.'),
      },
      {
        key: 'bootstrap',
        title: t('cloud_accounts_guide_bootstrap_title', 'Live Bootstrap'),
        desc: t('cloud_accounts_guide_bootstrap_desc', 'This is not a scan. It executes bootstrap actions on target VMs with UserData, RunCommand, or startup script paths, so approval is required by default.'),
      },
    ];

  const formatSyncStatus = (value) => {
    const v = String(value || '').trim().toLowerCase();
    if (v === 'success' || v === 'ok') return t('cloud_discovery_sync_success', 'success');
    if (v === 'failed' || v === 'error') return t('cloud_discovery_sync_failed', 'failed');
    if (v === 'running' || v === 'queued' || v === 'syncing') return t('cloud_discovery_sync_running', 'running');
    return t('cloud_discovery_sync_unknown', 'unknown');
  };

  const syncStatusClass = (value) => {
    const v = String(value || '').trim().toLowerCase();
    if (v === 'success' || v === 'ok') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300';
    if (v === 'failed' || v === 'error') return 'bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-300';
    if (v === 'running' || v === 'queued' || v === 'syncing') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300';
    return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
  };

  const formatDateTime = (value, fallback = null) => {
    if (!value) return fallback || t('cloud_discovery_never', 'Never');
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return String(value);
    return dt.toLocaleString();
  };

  const discoverySummary = useMemo(() => {
    const summary = {
      success: 0,
      failed: 0,
      running: 0,
      unknown: 0,
      lastSyncedAt: null,
    };

    for (const account of Array.isArray(accounts) ? accounts : []) {
      const s = String(account?.sync_status || '').trim().toLowerCase();
      if (s === 'success' || s === 'ok') summary.success += 1;
      else if (s === 'failed' || s === 'error') summary.failed += 1;
      else if (s === 'running' || s === 'queued' || s === 'syncing') summary.running += 1;
      else summary.unknown += 1;

      const ts = account?.last_synced_at ? new Date(account.last_synced_at).getTime() : NaN;
      if (!Number.isNaN(ts) && (summary.lastSyncedAt === null || ts > summary.lastSyncedAt)) {
        summary.lastSyncedAt = ts;
      }
    }

    return summary;
  }, [accounts]);

  const executionSummary = useMemo(() => {
    const summary = { ready: 0, scaffold: 0, missing: 0, unknown: 0, changeEnabled: 0, readOnly: 0 };
    for (const account of Array.isArray(accounts) ? accounts : []) {
      const stage = String(account?.execution_readiness?.stage || '').trim().toLowerCase();
      if (stage === 'real_apply_ready') summary.ready += 1;
      else if (stage === 'scaffold_ready') summary.scaffold += 1;
      else if (stage === 'credentials_missing') summary.missing += 1;
      else summary.unknown += 1;

      if (resolveChangeMode(account?.execution_readiness) === 'change_enabled') summary.changeEnabled += 1;
      else summary.readOnly += 1;
    }
    return summary;
  }, [accounts]);

  const ledgerByAccountId = useMemo(() => {
    const rows = Array.isArray(operationsLedger) ? operationsLedger : [];
    return rows.reduce((acc, item) => {
      const id = Number(item?.account_id || 0);
      if (Number.isFinite(id) && id > 0) acc[id] = item;
      return acc;
    }, {});
  }, [operationsLedger]);

  const ledgerSummary = useMemo(() => {
    const rows = Array.isArray(operationsLedger) ? operationsLedger : [];
    let attention = 0;
    let syncing = 0;
    let pendingApprovals = 0;
    let retryRecommended = 0;
    let latestOperationAt = null;

    for (const row of rows) {
      const posture = String(row?.operations_posture || '').trim().toLowerCase();
      if (posture === 'attention') attention += 1;
      else if (posture === 'syncing') syncing += 1;
      else if (posture === 'approval_pending') attention += 1;
      pendingApprovals += Number(row?.pending_approvals || 0);
      if (row?.retry_recommended) retryRecommended += 1;
      const ts = row?.last_operation_at ? new Date(row.last_operation_at).getTime() : NaN;
      if (!Number.isNaN(ts) && (latestOperationAt === null || ts > latestOperationAt)) latestOperationAt = ts;
    }

    return {
      attention,
      syncing,
      pendingApprovals,
      retryRecommended,
      latestOperationAt,
      total: rows.length,
    };
  }, [operationsLedger]);

  const ledgerReviewQueue = useMemo(() => {
    const rows = Array.isArray(accounts) ? accounts : [];
    return rows
      .map((account) => {
        const ledger = ledgerByAccountId[Number(account?.id || 0)] || null;
        if (!ledger) return null;
        const pendingApprovals = Number(ledger.pending_approvals || 0);
        const needsReview =
          String(ledger.operations_posture || '').trim().toLowerCase() === 'attention' ||
          String(ledger.operations_posture || '').trim().toLowerCase() === 'approval_pending' ||
          ledger.retry_recommended ||
          pendingApprovals > 0;
        if (!needsReview) return null;
        return {
          account,
          ledger,
          pendingApprovals,
          priority:
            (pendingApprovals > 0 ? 30 : 0) +
            (ledger.retry_recommended ? 20 : 0) +
            (String(ledger.operations_posture || '').trim().toLowerCase() === 'attention' ? 10 : 0),
        };
      })
      .filter(Boolean)
      .sort((left, right) => {
        if (right.priority !== left.priority) return right.priority - left.priority;
        return String(left.account?.name || '').localeCompare(String(right.account?.name || ''));
      })
      .slice(0, 4);
  }, [accounts, ledgerByAccountId]);
  const priorityLedgerReview = ledgerReviewQueue[0] || null;
  const ledgerLaneBoard = useMemo(() => {
    const rows = Array.isArray(accounts) ? accounts : [];
    const summary = {
      approval: { count: 0, entry: null },
      recovery: { count: 0, entry: null },
      sync: { count: 0, entry: null },
      stable: { count: 0, entry: null },
    };
    rows.forEach((account) => {
      const ledger = ledgerByAccountId[Number(account?.id || 0)];
      if (!ledger) return;
      const retryBlueprint = buildLedgerRetryBlueprint(ledger, t);
      const laneKey = getLedgerLaneKey(ledger, retryBlueprint);
      summary[laneKey].count += 1;
      if (!summary[laneKey].entry) {
        summary[laneKey].entry = { account, ledger };
      }
    });
    return summary;
  }, [accounts, ledgerByAccountId, t]);
  const ledgerRetryQueue = useMemo(() => {
    return (Array.isArray(accounts) ? accounts : [])
      .map((account) => {
        const ledger = ledgerByAccountId[Number(account?.id || 0)];
        if (!ledger) return null;
        const retryBlueprint = buildLedgerRetryBlueprint(ledger, t);
        if (!ledger?.retry_recommended || !retryBlueprint) return null;
        const failureCode = String(ledger?.last_failure_reason_code || '').trim().toLowerCase();
        const priority =
          30 +
          (failureCode === 'credential_issue' ? 10 : 0) +
          (failureCode === 'permission_issue' ? 8 : 0) +
          (failureCode === 'policy_blocked' ? 6 : 0) +
          (Number(ledger?.pending_approvals || 0) > 0 ? 4 : 0);
        return { account, ledger, retryBlueprint, priority };
      })
      .filter(Boolean)
      .sort((left, right) => {
        if (right.priority !== left.priority) return right.priority - left.priority;
        const leftTs = Date.parse(String(left.ledger?.last_operation_at || '')) || 0;
        const rightTs = Date.parse(String(right.ledger?.last_operation_at || '')) || 0;
        return rightTs - leftTs;
      })
      .slice(0, 3);
  }, [accounts, ledgerByAccountId, t]);
  const ledgerExecutionHighlights = useMemo(() => {
    return (Array.isArray(accounts) ? accounts : [])
      .flatMap((account) => {
        const ledger = ledgerByAccountId[Number(account?.id || 0)];
        const operations = Array.isArray(ledger?.recent_operations) ? ledger.recent_operations : [];
        return operations.map((op, index) => ({
          account,
          ledger,
          operation: op,
          ts: Date.parse(String(op?.timestamp || ledger?.last_operation_at || '')) || 0,
          key: `${account?.id || 'account'}-${op?.event_type || 'operation'}-${op?.timestamp || index}`,
        }));
      })
      .filter((entry) => entry.ts > 0)
      .sort((left, right) => right.ts - left.ts)
      .slice(0, 4);
  }, [accounts, ledgerByAccountId]);

  const openLedgerReview = (accountId) => {
    setFocusedAccountId(String(accountId));
    setExpandedLedgerAccountId(String(accountId));
  };

  const openLedgerApproval = (approvalId) => {
    navigate(approvalId ? `/approval?focusRequestId=${approvalId}` : '/approval');
  };

  const load = async () => {
    setLoading(true);
    try {
      const res = await CloudService.listAccounts();
      const rows = Array.isArray(res.data) ? res.data : [];
      setAccounts(rows);
      await loadAccountBootstrapPaths(rows);
      await loadLedger();
    } catch (e) {
      setAccounts([]);
      setAccountBootstrapPaths({});
      setOperationsLedger([]);
    } finally {
      setLoading(false);
    }
  };

  const loadPresets = async () => {
    try {
      const res = await CloudService.listProviderPresets();
      setPresets(Array.isArray(res?.data) ? res.data : []);
    } catch (e) {
      setPresets([]);
    }
  };

  const loadKpi = async () => {
    setKpiLoading(true);
    try {
      const res = await CloudService.getKpiSummary({ days: 30 });
      setCloudKpi(res?.data || null);
    } catch (e) {
      setCloudKpi(null);
    } finally {
      setKpiLoading(false);
    }
  };

  const loadLedger = async () => {
    setLedgerLoading(true);
    try {
      const res = await CloudService.getOperationsLedger({ limit: 5 });
      setOperationsLedger(Array.isArray(res?.data) ? res.data : []);
    } catch (e) {
      setOperationsLedger([]);
    } finally {
      setLedgerLoading(false);
    }
  };

  useEffect(() => {
    load();
    loadPresets();
    loadKpi();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(location.search || '');
    const nextFocusedAccountId = String(params.get('focusAccountId') || '').trim();
    setFocusedAccountId(nextFocusedAccountId);
  }, [location.search]);

  useEffect(() => {
    if (!focusedAccountId) return;
    const timer = window.setTimeout(() => {
      const target = document.querySelector(`[data-account-focus-id="${focusedAccountId}"]`);
      if (target && typeof target.scrollIntoView === 'function') {
        target.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    }, 120);
    return () => window.clearTimeout(timer);
  }, [focusedAccountId, accounts]);

  const formatSeconds = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return '-';
    if (num < 60) return `${num.toFixed(1)}s`;
    if (num < 3600) return `${(num / 60).toFixed(1)}m`;
    return `${(num / 3600).toFixed(2)}h`;
  };

  const formatPct = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return '-';
    return `${num.toFixed(2)}%`;
  };

  const bootstrapPathOptions = {
    aws: [
      { value: 'auto', label: t('cloud_bootstrap_path_auto', 'Auto (Recommended)') },
      { value: 'userdata', label: t('cloud_bootstrap_path_aws_userdata', 'AWS UserData') },
      { value: 'ssm', label: t('cloud_bootstrap_path_aws_ssm', 'AWS SSM RunCommand') },
    ],
    azure: [
      { value: 'auto', label: t('cloud_bootstrap_path_auto', 'Auto (Recommended)') },
      { value: 'run_command', label: t('cloud_bootstrap_path_azure_run_command', 'Azure RunCommand') },
      { value: 'custom_script', label: t('cloud_bootstrap_path_azure_custom_script', 'Azure Custom Script') },
    ],
    gcp: [
      { value: 'startup_metadata', label: t('cloud_bootstrap_path_gcp_startup_metadata', 'GCP startup-script metadata') },
    ],
  };

  const normalizeProvider = (providerName) => String(providerName || '').trim().toLowerCase();
  const toFormProvider = (providerName) => {
    const p = normalizeProvider(providerName);
    if (p === 'ncp' || p === 'naver_cloud') return 'naver';
    return p || 'aws';
  };
  const resetAccountDraft = () => {
    setEditingAccountId(null);
    setProvider('aws');
    setName('');
    setCreds({});
    setPreflightResult(null);
  };

  const normalizeBootstrapPath = (providerName, rawPath) => {
    const p = normalizeProvider(providerName);
    const value = String(rawPath || '').trim().toLowerCase();
    if (p === 'aws') {
      if (value === 'run_command') return 'ssm';
      if (['auto', 'userdata', 'ssm'].includes(value)) return value;
      return 'auto';
    }
    if (p === 'azure') {
      if (['auto', 'run_command', 'custom_script'].includes(value)) return value;
      return 'auto';
    }
    if (p === 'gcp') {
      if (['startup_metadata', 'startup_script'].includes(value)) return value;
      return 'startup_metadata';
    }
    return 'auto';
  };

  const getBootstrapOptionsByProvider = (providerName) => {
    const p = normalizeProvider(providerName);
    return bootstrapPathOptions[p] || [{ value: 'auto', label: t('cloud_bootstrap_path_auto', 'Auto (Recommended)') }];
  };

  const loadAccountBootstrapPaths = async (rows) => {
    const targets = Array.isArray(rows) ? rows : [];
    if (targets.length === 0) {
      setAccountBootstrapPaths({});
      return;
    }

    const pairs = await Promise.all(
      targets.map(async (a) => {
        try {
          const res = await CloudService.getMaskedCredentials(a.id);
          const raw = res?.data?.credentials?.bootstrap_path;
          return [Number(a.id), normalizeBootstrapPath(a.provider, raw)];
        } catch (e) {
          return [Number(a.id), normalizeBootstrapPath(a.provider, '')];
        }
      }),
    );

    const map = {};
    for (const [id, path] of pairs) {
      if (Number.isFinite(Number(id))) {
        map[Number(id)] = path;
      }
    }
    setAccountBootstrapPaths(map);
  };

  const saveAccountBootstrapPath = async (account, selectedPath) => {
    const accountId = Number(account?.id);
    if (!Number.isFinite(accountId)) return;
    const normalizedPath = normalizeBootstrapPath(account?.provider, selectedPath);
    const currentPath = normalizeBootstrapPath(account?.provider, accountBootstrapPaths[accountId]);
    if (normalizedPath === currentPath) return;

    setSavingBootstrapPaths((prev) => ({ ...prev, [accountId]: true }));
    try {
      await CloudService.updateAccount(accountId, { credentials: { bootstrap_path: normalizedPath } });
      setAccountBootstrapPaths((prev) => ({ ...prev, [accountId]: normalizedPath }));
      toast.success(t('cloud_bootstrap_account_path_saved', 'Bootstrap path saved.'));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e?.message || t('cloud_bootstrap_account_path_failed', 'Failed to save bootstrap path.'));
    } finally {
      setSavingBootstrapPaths((prev) => ({ ...prev, [accountId]: false }));
    }
  };

  const buildBootstrapContext = (targetAccounts) => {
    const targets = Array.isArray(targetAccounts) ? targetAccounts : [];
    const providerSet = new Set(targets.map((a) => normalizeProvider(a?.provider)).filter((p) => !!p));
    const ctx = {};

    if (targets.length === 1) {
      const one = targets[0];
      const p = normalizeProvider(one?.provider);
      const saved = normalizeBootstrapPath(p, accountBootstrapPaths[Number(one?.id)]);
      if (p === 'aws') ctx.aws_bootstrap_path = saved;
      if (p === 'azure') ctx.azure_bootstrap_path = saved;
      if (p === 'gcp') ctx.gcp_bootstrap_path = saved;
    }

    if (providerSet.has('aws') && !ctx.aws_bootstrap_path) {
      ctx.aws_bootstrap_path = normalizeBootstrapPath('aws', bootstrapPaths.aws);
    }
    if (providerSet.has('azure') && !ctx.azure_bootstrap_path) {
      ctx.azure_bootstrap_path = normalizeBootstrapPath('azure', bootstrapPaths.azure);
    }
    if (providerSet.has('gcp') && !ctx.gcp_bootstrap_path) {
      ctx.gcp_bootstrap_path = normalizeBootstrapPath('gcp', bootstrapPaths.gcp);
    }
    return ctx;
  };

  const submitBootstrapApproval = async ({ targetAccounts, targetIds, payload }) => {
    const names = (Array.isArray(targetAccounts) ? targetAccounts : [])
      .map((account) => String(account?.name || '').trim())
      .filter(Boolean);
    const providers = [...new Set(
      (Array.isArray(targetAccounts) ? targetAccounts : [])
        .map((account) => String(account?.provider || '').trim().toUpperCase())
        .filter(Boolean),
    )];
    const scopeLabel = names.length === 1
      ? names[0]
      : `${Number(targetIds?.length || 0)} account(s)`;

    const approvalPayload = {
      ...payload,
      dry_run: false,
      metadata: {
        source: 'cloud_accounts_ui',
        submission_channel: 'cloud_bootstrap_live',
        providers,
        account_names: names,
      },
      change_preview_summary: {
        target_accounts: names,
        providers,
        total_accounts: Number(targetIds?.length || 0),
        bootstrap_context: payload?.context || {},
      },
    };

    const res = await ApprovalService.create({
      title: `Cloud Bootstrap: ${scopeLabel}`,
      description: 'Live cloud bootstrap requires approval before execution. Review the target accounts, adapter path, and rollout settings in Approval Center.',
      request_type: 'cloud_bootstrap',
      payload: approvalPayload,
      requester_comment: 'Generated automatically from Cloud Accounts after live bootstrap hit approval-required policy.',
    });

    const approvalId = Number(res?.data?.id || 0) || null;
    setBootstrapResult({
      status: 'approval_required',
      total_targets: Number(targetIds?.length || 0),
      success_targets: 0,
      failed_targets: 0,
      dry_run_targets: 0,
      approval_id: approvalId,
      execution_id: null,
      idempotency_key: payload?.idempotency_key || null,
      results: [],
    });
    toast.success(t('cloud_bootstrap_approval_submitted', 'Live bootstrap requires approval. Approval request submitted.'));
    navigate('/approval');
  };

  const normalizeCreds = () => {
    const p = String(provider).toLowerCase();
    if (p === 'aws') {
      const auth_type = String(creds.auth_type || (creds.role_arn ? 'assume_role' : 'access_key')).trim().toLowerCase();
      if (auth_type === 'assume_role') {
        return {
          auth_type,
          region: String(creds.region || 'ap-northeast-2').trim(),
          role_arn: String(creds.role_arn || '').trim(),
          external_id: String(creds.external_id || '').trim(),
          role_session_name: String(creds.role_session_name || 'netsphere-cloud-scan').trim(),
          source_access_key: String(creds.source_access_key || '').trim(),
          source_secret_key: String(creds.source_secret_key || '').trim(),
          source_session_token: String(creds.source_session_token || '').trim(),
        };
      }
      return {
        auth_type: 'access_key',
        region: String(creds.region || 'ap-northeast-2').trim(),
        access_key: String(creds.access_key || '').trim(),
        secret_key: String(creds.secret_key || '').trim(),
        session_token: String(creds.session_token || '').trim(),
      };
    }
    if (p === 'azure') return { tenant_id: String(creds.tenant_id || '').trim(), subscription_id: String(creds.subscription_id || '').trim(), client_id: String(creds.client_id || '').trim(), client_secret: String(creds.client_secret || '').trim() };
    if (p === 'gcp') return { project_id: String(creds.project_id || '').trim(), service_account_json: creds.service_account_json || '', regions: String(creds.regions || '').trim() };
    if (p === 'naver') return { access_key: String(creds.access_key || '').trim(), secret_key: String(creds.secret_key || '').trim(), region_code: String(creds.region_code || '').trim() };
    return creds;
  };

  const submitAccount = async () => {
    if (!name.trim()) {
      toast.warning(t('cloud_accounts_name_required'));
      return;
    }
    const c = normalizeCreds();
    if (String(provider) === 'aws') {
      if (c.auth_type === 'assume_role') {
        if (!c.role_arn) {
          toast.warning(t('aws_role_arn_required'));
          return;
        }
        const hasSourceAk = !!c.source_access_key;
        const hasSourceSk = !!c.source_secret_key;
        if (hasSourceAk !== hasSourceSk) {
          toast.warning(t('aws_source_key_pair_required'));
          return;
        }
      } else if (!c.access_key || !c.secret_key) {
        toast.warning(t('aws_access_key_required'));
        return;
      }
    }
    setLoading(true);
    try {
      if (isEditMode) {
        await CloudService.updateAccount(Number(editingAccountId), {
          name: name.trim(),
          credentials: c,
        });
        toast.success(t('cloud_accounts_update_success', 'Cloud account updated.'));
      } else {
        await CloudService.createAccount({ name: name.trim(), provider, credentials: c, is_active: true });
        toast.success(t('cloud_accounts_register_success'));
      }
      resetAccountDraft();
      await load();
    } catch (e) {
      toast.error(
        e?.response?.data?.detail ||
        e?.message ||
        (isEditMode
          ? t('cloud_accounts_update_failed', 'Failed to update cloud account.')
          : t('cloud_accounts_create_failed')),
      );
    } finally {
      setLoading(false);
    }
  };

  const beginEdit = async (account) => {
    const id = Number(account?.id);
    if (!Number.isFinite(id)) return;
    setLoading(true);
    try {
      const res = await CloudService.getMaskedCredentials(id);
      setEditingAccountId(id);
      setProvider(toFormProvider(account?.provider));
      setName(String(account?.name || ''));
      setCreds(res?.data?.credentials || {});
      setPreflightResult(null);
      toast.success(t('cloud_accounts_edit_mode', 'Edit mode enabled.'));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e?.message || t('cloud_accounts_load_credentials_failed', 'Failed to load account credentials.'));
    } finally {
      setLoading(false);
    }
  };

  const scan = async (id) => {
    setLoading(true);
    try {
      await CloudService.scanAccount(id);
      toast.success(t('cloud_scan_queued'));
      window.setTimeout(() => {
        load();
      }, 1200);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e?.message || t('cloud_scan_failed'));
    } finally {
      setLoading(false);
    }
  };

  const del = async (id) => {
    if (!window.confirm(t('cloud_accounts_delete_confirm'))) return;
    setLoading(true);
    try {
      await CloudService.deleteAccount(id);
      if (Number(editingAccountId) === Number(id)) {
        resetAccountDraft();
      }
      toast.success(t('cloud_accounts_delete_success'));
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e?.message || t('cloud_accounts_deleted_failed'));
    } finally {
      setLoading(false);
    }
  };

  const buildHybrid = async () => {
    setLoading(true);
    try {
      await CloudService.buildHybrid();
      toast.success(t('hybrid_topology_created'));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e?.message || t('hybrid_topology_failed'));
    } finally {
      setLoading(false);
    }
  };

  const runDraftPreflight = async () => {
    const c = normalizeCreds();
    setLoading(true);
    try {
      const res = await CloudService.preflight({ provider, credentials: c });
      const data = res?.data || null;
      setPreflightResult(data);
      if (String(data?.status || '').toLowerCase() === 'ok') {
        toast.success(t('cloud_preflight_passed', 'Cloud preflight passed'));
      } else {
        toast.warning(t('cloud_preflight_failed', 'Cloud preflight failed'));
      }
    } catch (e) {
      setPreflightResult(null);
      toast.error(e?.response?.data?.detail || e?.message || t('cloud_preflight_failed', 'Cloud preflight failed'));
    } finally {
      setLoading(false);
    }
  };

  const runAccountPreflight = async (id) => {
    setLoading(true);
    try {
      const res = await CloudService.preflightAccount(id);
      const data = res?.data || null;
      if (String(data?.status || '').toLowerCase() === 'ok') {
        toast.success(t('cloud_account_preflight_passed', 'Account validation passed'));
      } else {
        const firstError = Array.isArray(data?.checks)
          ? data.checks.find((c) => !c?.ok)?.message
          : '';
        toast.warning(firstError || t('cloud_account_preflight_failed', 'Account validation failed'));
      }
      await loadLedger();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e?.message || t('cloud_account_preflight_failed', 'Account validation failed'));
    } finally {
      setLoading(false);
    }
  };

  const runPipeline = async (accountId = null) => {
    const activeAccountIds = Array.isArray(accounts)
      ? accounts.filter((a) => !!a?.is_active).map((a) => Number(a.id)).filter((v) => Number.isFinite(v))
      : [];
    if (!accountId && activeAccountIds.length === 0) {
      toast.warning(t('cloud_accounts_pipeline_no_active', 'No active cloud accounts to run pipeline.'));
      return;
    }

    const targetIds = accountId ? [Number(accountId)] : activeAccountIds;
    const payload = {
      account_ids: targetIds,
      preflight: true,
      include_hybrid_build: true,
      include_hybrid_infer: true,
      enrich_inferred: true,
      continue_on_error: true,
      idempotency_key: `ui-cloud-pipeline:${accountId ? String(accountId) : 'all'}:${Math.floor(Date.now() / 30000)}`,
    };

    setLoading(true);
    try {
      const res = accountId
        ? await CloudService.runAccountPipeline(Number(accountId), payload)
        : await CloudService.runPipeline(payload);
      const data = res?.data || null;
      setPipelineResult(data);
      const status = String(data?.status || '').toLowerCase();
      if (status === 'ok') {
        toast.success(t('cloud_accounts_pipeline_ok', 'Cloud pipeline completed.'));
      } else if (status === 'partial') {
        toast.warning(t('cloud_accounts_pipeline_partial', 'Cloud pipeline completed with partial failures.'));
      } else if (status === 'skipped_duplicate') {
        toast.warning(t('cloud_accounts_pipeline_duplicate', 'Duplicate pipeline request was skipped.'));
      } else {
        toast.warning(t('cloud_accounts_pipeline_failed', 'Cloud pipeline failed.'));
      }
      await load();
      await loadKpi();
      await loadLedger();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e?.message || t('cloud_accounts_pipeline_failed', 'Cloud pipeline failed.'));
    } finally {
      setLoading(false);
    }
  };

  const runBootstrap = async (accountId = null, dryRun = true) => {
    const activeAccountIds = Array.isArray(accounts)
      ? accounts.filter((a) => !!a?.is_active).map((a) => Number(a.id)).filter((v) => Number.isFinite(v))
      : [];
    const targetAccounts = accountId
      ? (Array.isArray(accounts) ? accounts.filter((a) => Number(a?.id) === Number(accountId)) : [])
      : (Array.isArray(accounts) ? accounts.filter((a) => !!a?.is_active) : []);
    if (!accountId && activeAccountIds.length === 0) {
      toast.warning(t('cloud_bootstrap_no_active', 'No active cloud accounts to run bootstrap.'));
      return;
    }
    if (!dryRun) {
      const ok = window.confirm(t('cloud_bootstrap_confirm', 'Apply bootstrap to selected cloud VMs?'));
      if (!ok) return;
    }

    const targetIds = accountId ? [Number(accountId)] : activeAccountIds;
    const context = buildBootstrapContext(targetAccounts);
    const contextKey = `aws=${String(context.aws_bootstrap_path || '-')},azure=${String(context.azure_bootstrap_path || '-')},gcp=${String(context.gcp_bootstrap_path || '-')}`;
    const payload = {
      account_ids: targetIds,
      dry_run: !!dryRun,
      pre_check_enabled: true,
      post_check_enabled: true,
      rollback_on_failure: true,
      canary_count: 0,
      wave_size: 2,
      stop_on_wave_failure: true,
      inter_wave_delay_seconds: 0.0,
      context,
      idempotency_key: `ui-cloud-bootstrap:${accountId ? String(accountId) : 'all'}:${dryRun ? 'dry' : 'run'}:${contextKey}:${Math.floor(Date.now() / 30000)}`,
    };

    setLoading(true);
    try {
      const res = accountId
        ? await CloudService.runAccountBootstrap(Number(accountId), payload)
        : await CloudService.runBootstrap(payload);
      const data = res?.data || null;
      setBootstrapResult(data);
      const status = String(data?.status || '').toLowerCase();
      if (status === 'ok') {
        toast.success(dryRun ? t('cloud_bootstrap_dry_run_done', 'Bootstrap dry-run completed.') : t('cloud_bootstrap_run_done', 'Bootstrap completed.'));
      } else if (status === 'partial') {
        toast.warning(t('cloud_bootstrap_partial', 'Bootstrap completed with partial failures.'));
      } else if (status === 'skipped_duplicate') {
        toast.warning(t('cloud_bootstrap_duplicate', 'Duplicate bootstrap request was skipped.'));
      } else {
        toast.warning(t('cloud_bootstrap_failed', 'Bootstrap failed.'));
      }
      await loadLedger();
    } catch (e) {
      const status = Number(e?.response?.status || 0);
      const detail = String(e?.response?.data?.detail || e?.message || '').trim();
      const approvalRequired = !dryRun && status === 409 && detail.toLowerCase().includes('approval required for live cloud bootstrap');
      if (approvalRequired) {
        try {
          await submitBootstrapApproval({ targetAccounts, targetIds, payload });
          return;
        } catch (approvalError) {
          toast.error(
            approvalError?.response?.data?.detail ||
            approvalError?.message ||
            t('cloud_bootstrap_approval_failed', 'Approval request could not be created.'),
          );
          return;
        }
      }
      toast.error(detail || t('cloud_bootstrap_failed', 'Bootstrap failed.'));
    } finally {
      setLoading(false);
    }
  };

  const runLedgerRetry = async (account, ledger) => {
    const blueprint = buildLedgerRetryBlueprint(ledger, t);
    const accountId = Number(account?.id || 0);
    if (!blueprint || !Number.isFinite(accountId) || accountId <= 0) return;

    const retryKey = `${accountId}:${blueprint.key}`;
    setLedgerRetryKey(retryKey);
    try {
      if (blueprint.key === 'validate') {
        await runAccountPreflight(accountId);
        return;
      }
      if (blueprint.key === 'scan') {
        await scan(accountId);
        return;
      }
      if (blueprint.key === 'pipeline') {
        await runPipeline(accountId);
        return;
      }
      if (blueprint.key === 'bootstrap_dry_run') {
        await runBootstrap(accountId, true);
      }
    } finally {
      setLedgerRetryKey('');
    }
  };

  return (
    <div className="h-full min-h-0 w-full bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white p-3 sm:p-4 md:p-6 overflow-y-auto custom-scrollbar">
      <div data-testid="cloud-accounts-page" className="max-w-5xl mx-auto space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-center gap-2 flex-wrap">
            <Cloud className="text-sky-500" />
            <h1 className="text-xl font-bold">{t('cloud_accounts_title')}</h1>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-2">
            <Link
              to="/cloud/intents"
              className={`${ACTION_BUTTON_NEUTRAL} no-underline`}
            >
              <ShieldCheck size={16} /> {t('cloud_intents_open_short', 'Cloud Intents')}
            </Link>
            <button
              onClick={load}
              disabled={loading}
              className={ACTION_BUTTON_NEUTRAL}
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> {t('cloud_accounts_refresh')}
            </button>
            <button
              onClick={loadKpi}
              disabled={loading || kpiLoading}
              className={ACTION_BUTTON_NEUTRAL}
            >
              <RefreshCw size={16} className={kpiLoading ? 'animate-spin' : ''} /> {t('cloud_accounts_kpi_refresh', 'KPI Refresh')}
            </button>
            <button
              onClick={() => runPipeline(null)}
              disabled={loading || !canEdit}
              className={`${ACTION_BUTTON_PRIMARY} bg-indigo-600 hover:bg-indigo-500`}
            >
              {t('cloud_accounts_pipeline_run', 'Run Pipeline')}
            </button>
            <button
              onClick={() => runBootstrap(null, true)}
              disabled={loading || !canEdit}
              className={`${ACTION_BUTTON_PRIMARY} bg-violet-600 hover:bg-violet-500`}
            >
              {t('cloud_bootstrap_dry_run', 'Bootstrap Dry-Run')}
            </button>
            <button
              onClick={buildHybrid}
              disabled={loading || !canEdit}
              className={`${ACTION_BUTTON_PRIMARY} bg-sky-600 hover:bg-sky-500`}
            >
              {t('cloud_accounts_hybrid_build')}
            </button>
          </div>
        </div>

        <SectionCard className="px-4 py-3">
          <div className="grid gap-3 md:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-xl border border-sky-200 dark:border-sky-900/40 bg-sky-50/80 dark:bg-sky-950/10 px-4 py-4">
              <div className="text-sm font-black text-sky-900 dark:text-sky-100">
                {t('cloud_accounts_access_title', 'Role and execution boundary')}
              </div>
              <div className="mt-2 text-sm text-sky-800 dark:text-sky-200">
                {roleAccessCopy}
              </div>
              <div className="mt-3 text-xs text-sky-700 dark:text-sky-300">
                {t('cloud_accounts_access_role_fmt', 'Current role: {role}').replace('{role}', roleLabel)}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-900/10 px-4 py-3">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
                  {t('cloud_accounts_guardrail_read_path', 'Read path')}
                </div>
                <div className="mt-2 text-sm font-semibold text-emerald-800 dark:text-emerald-200">
                  {t('cloud_accounts_guardrail_read_path_desc', 'Validate, Pipeline, and Scan stay read-only.')}
                </div>
              </div>
              <div className="rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/10 px-4 py-3">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">
                  {t('cloud_accounts_guardrail_change_path', 'Change path')}
                </div>
                <div className="mt-2 text-sm font-semibold text-amber-800 dark:text-amber-200">
                  {t('cloud_accounts_guardrail_change_path_desc', 'Cloud Intents stay approval-gated until runtime readiness is clear.')}
                </div>
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard className="px-4 py-3">
          <div className="mb-4 rounded-xl border border-sky-200 dark:border-sky-900/40 bg-sky-50/70 dark:bg-sky-950/10 p-4">
            <div className="text-sm font-black text-sky-900 dark:text-sky-100">
              {t('cloud_accounts_flow_title', 'Cloud account flow')}
            </div>
            <div className="mt-1 text-xs text-sky-800 dark:text-sky-200">
              {t('cloud_accounts_flow_desc', 'Add the account first, validate access, run pipeline for read-only discovery, and only use Live Bootstrap when you intentionally want guest bootstrap execution on cloud VMs.')}
            </div>
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              {actionGuide.map((item) => (
                <div key={item.key} className="rounded-xl border border-sky-200/80 dark:border-sky-900/30 bg-white/80 dark:bg-black/20 p-3">
                  <div className="text-xs font-extrabold uppercase tracking-[0.18em] text-sky-700 dark:text-sky-300">{item.title}</div>
                  <div className="mt-2 text-xs text-gray-700 dark:text-gray-300">{item.desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="text-[11px] font-bold text-gray-500 mb-2">{t('cloud_bootstrap_adapter_paths', 'Bootstrap Adapter Paths')}</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="AWS">
              <Select
                value={bootstrapPaths.aws}
                onChange={(v) => setBootstrapPaths((p) => ({ ...p, aws: v }))}
                options={bootstrapPathOptions.aws}
              />
            </Field>
            <Field label="Azure">
              <Select
                value={bootstrapPaths.azure}
                onChange={(v) => setBootstrapPaths((p) => ({ ...p, azure: v }))}
                options={bootstrapPathOptions.azure}
              />
            </Field>
            <Field label="GCP">
              <Select
                value={bootstrapPaths.gcp}
                onChange={(v) => setBootstrapPaths((p) => ({ ...p, gcp: v }))}
                options={bootstrapPathOptions.gcp}
              />
            </Field>
          </div>
          <div className="text-[11px] text-gray-500 mt-2">
            {t('cloud_bootstrap_adapter_paths_desc', 'Selected paths are applied to bootstrap context by provider.')}
          </div>
        </SectionCard>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <SectionCard className="px-4 py-3">
            <div className="text-[11px] font-bold text-gray-500 mb-1">{t('cloud_kpi_first_map_p50', 'First Map P50')}</div>
            <div className="text-xl font-black text-gray-900 dark:text-white">{formatSeconds(cloudKpi?.first_map_seconds_p50)}</div>
            <div className="text-[11px] text-gray-500 mt-1">P95: {formatSeconds(cloudKpi?.first_map_seconds_p95)}</div>
          </SectionCard>
          <SectionCard className="px-4 py-3">
            <div className="text-[11px] font-bold text-gray-500 mb-1">{t('cloud_kpi_auto_reflection', 'Auto Reflection')}</div>
            <div className="text-xl font-black text-emerald-600">{formatPct(cloudKpi?.auto_reflection_rate_pct)}</div>
            <div className="text-[11px] text-gray-500 mt-1">Reflected links: {Number(cloudKpi?.reflected_links || 0)}</div>
          </SectionCard>
          <SectionCard className="px-4 py-3">
            <div className="text-[11px] font-bold text-gray-500 mb-1">{t('cloud_kpi_false_positive', 'False Positive')}</div>
            <div className="text-xl font-black text-amber-600">{formatPct(cloudKpi?.false_positive_rate_pct)}</div>
            <div className="text-[11px] text-gray-500 mt-1">Low-confidence queued: {Number(cloudKpi?.low_confidence_queued || 0)}</div>
          </SectionCard>
          <SectionCard className="px-4 py-3">
            <div className="text-[11px] font-bold text-gray-500 mb-1">{t('cloud_kpi_runs_30d', 'Runs (30d)')}</div>
            <div className="text-xl font-black text-sky-600">{Number(cloudKpi?.runs || 0)}</div>
            <div className="text-[11px] text-gray-500 mt-1">
              ok {Number(cloudKpi?.ok_runs || 0)} / partial {Number(cloudKpi?.partial_runs || 0)} / failed {Number(cloudKpi?.failed_runs || 0)}
            </div>
          </SectionCard>
        </div>

        <SectionCard data-testid="cloud-operations-ledger" className="px-4 py-3">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-[11px] font-bold text-gray-500 mb-1">
                {t('cloud_accounts_ledger_title', 'Cloud Operations Ledger')}
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-300">
                {t(
                  'cloud_accounts_ledger_desc',
                  'Track recent validate, scan, pipeline, and bootstrap outcomes with approval context and retry posture per account.',
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="cloud-accounts-open-operations-reports"
                onClick={() => navigate('/operations-reports')}
                className={ACTION_BUTTON_NEUTRAL}
              >
                {t('cloud_accounts_open_operations_reports', 'Open Operations Reports')}
              </button>
              {Number(ledgerSummary.pendingApprovals || 0) > 0 ? (
                <button
                  type="button"
                  data-testid="cloud-accounts-open-approval-center"
                  onClick={() => navigate('/approval')}
                  className={ACTION_BUTTON_NEUTRAL}
                >
                  {t('cloud_accounts_open_approval_center', 'Open Approval Center')}
                </button>
              ) : null}
              <button
                onClick={loadLedger}
                disabled={loading || ledgerLoading}
                className={ACTION_BUTTON_NEUTRAL}
              >
                <RefreshCw size={16} className={ledgerLoading ? 'animate-spin' : ''} />
                {t('cloud_accounts_ledger_refresh', 'Ledger Refresh')}
              </button>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
            <div className="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/10 px-3 py-2">
              <div className="text-[10px] text-amber-700 dark:text-amber-300">
                {t('cloud_accounts_ledger_attention', 'Needs review')}
              </div>
              <div className="font-black text-amber-700 dark:text-amber-300">{Number(ledgerSummary.attention || 0)}</div>
            </div>
            <div className="rounded-lg border border-violet-200 dark:border-violet-900/40 bg-violet-50 dark:bg-violet-900/10 px-3 py-2">
              <div className="text-[10px] text-violet-700 dark:text-violet-300">
                {t('cloud_accounts_ledger_pending_approvals', 'Pending approvals')}
              </div>
              <div className="font-black text-violet-700 dark:text-violet-300">{Number(ledgerSummary.pendingApprovals || 0)}</div>
            </div>
            <div className="rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-900/10 px-3 py-2">
              <div className="text-[10px] text-sky-700 dark:text-sky-300">
                {t('cloud_accounts_ledger_syncing', 'Syncing')}
              </div>
              <div className="font-black text-sky-700 dark:text-sky-300">{Number(ledgerSummary.syncing || 0)}</div>
            </div>
            <div className="rounded-lg border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-900/10 px-3 py-2">
              <div className="text-[10px] text-rose-700 dark:text-rose-300">
                {t('cloud_accounts_ledger_retry_recommended', 'Retry recommended')}
              </div>
              <div className="font-black text-rose-700 dark:text-rose-300">{Number(ledgerSummary.retryRecommended || 0)}</div>
            </div>
          </div>
          <div className="mt-3 text-[11px] text-gray-500">
            {t('cloud_accounts_ledger_last_operation', 'Latest operation')}:{' '}
            {formatDateTime(
              ledgerSummary.latestOperationAt ? new Date(ledgerSummary.latestOperationAt).toISOString() : null,
              t('cloud_discovery_never', 'Never'),
            )}
          </div>
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            <div data-testid="cloud-operations-retry-queue" className="rounded-xl border border-rose-200 dark:border-rose-900/40 bg-rose-50/60 dark:bg-rose-950/10 px-4 py-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-rose-700 dark:text-rose-300">
                {t('cloud_accounts_retry_queue_title', 'Retry queue')}
              </div>
              <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                {t(
                  'cloud_accounts_retry_queue_desc',
                  'Accounts with a safe retry lane stay grouped here so operators can recover validate, scan, or pipeline work without digging through every row.',
                )}
              </div>
              {ledgerRetryQueue.length === 0 ? (
                <div className="mt-3 rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-white/80 dark:bg-black/20 px-3 py-3 text-[11px] text-gray-600 dark:text-gray-300">
                  {t('cloud_accounts_retry_queue_empty', 'No retry actions are waiting right now.')}
                </div>
              ) : (
                <div className="mt-3 grid gap-2">
                  {ledgerRetryQueue.map(({ account, ledger, retryBlueprint }) => (
                    <div
                      key={`cloud-retry-queue-${account.id}`}
                      data-testid={`cloud-retry-queue-item-${account.id}`}
                      className="rounded-lg border border-rose-200/80 dark:border-rose-900/40 bg-white/80 dark:bg-black/20 px-3 py-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-gray-900 dark:text-white truncate">{String(account?.name || '-')}</div>
                          <div className="mt-1 text-[11px] text-gray-500">
                            {ledgerFailureReasonLabel(ledger?.last_failure_reason_code, t, ledger?.last_failure_reason_label)}
                          </div>
                        </div>
                        <span className="rounded-full border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/10 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-rose-700 dark:text-rose-300">
                          {retryBlueprint.label}
                        </span>
                      </div>
                      <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
                        {retryBlueprint.desc}
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          data-testid={`cloud-retry-queue-open-review-${account.id}`}
                          onClick={() => openLedgerReview(account.id)}
                          className={ACTION_BUTTON_NEUTRAL}
                        >
                          {t('cloud_accounts_ledger_open_review', 'Open review')}
                        </button>
                        <button
                          type="button"
                          data-testid={`cloud-retry-queue-run-${account.id}`}
                          onClick={() => runLedgerRetry(account, ledger)}
                          disabled={loading || !canEdit || ledgerRetryKey === `${Number(account.id)}:${retryBlueprint.key}`}
                          className={`${ACTION_BUTTON_PRIMARY} bg-rose-600 hover:bg-rose-500`}
                        >
                          {ledgerRetryKey === `${Number(account.id)}:${retryBlueprint.key}`
                            ? t('cloud_accounts_ledger_retry_running', 'Retrying...')
                            : retryBlueprint.label}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div data-testid="cloud-operations-execution-highlights" className="rounded-xl border border-sky-200 dark:border-sky-900/40 bg-sky-50/60 dark:bg-sky-950/10 px-4 py-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-sky-700 dark:text-sky-300">
                {t('cloud_accounts_execution_highlights_title', 'Recent execution highlights')}
              </div>
              <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                {t(
                  'cloud_accounts_execution_highlights_desc',
                  'Keep the latest validate, scan, pipeline, and bootstrap outcomes visible so operators can see which lane moved most recently.',
                )}
              </div>
              {ledgerExecutionHighlights.length === 0 ? (
                <div className="mt-3 rounded-lg border border-sky-200 dark:border-sky-900/40 bg-white/80 dark:bg-black/20 px-3 py-3 text-[11px] text-gray-600 dark:text-gray-300">
                  {t('cloud_accounts_execution_highlights_empty', 'No recent cloud execution history is available yet.')}
                </div>
              ) : (
                <div className="mt-3 grid gap-2">
                  {ledgerExecutionHighlights.map(({ account, ledger, operation, key }) => (
                    <div
                      key={key}
                      data-testid={`cloud-execution-highlight-${account.id}`}
                      className="rounded-lg border border-sky-200/80 dark:border-sky-900/40 bg-white/80 dark:bg-black/20 px-3 py-3"
                    >
                      <div className="flex flex-wrap items-center gap-2 text-[11px]">
                        <span className="font-bold text-gray-900 dark:text-white">{String(account?.name || '-')}</span>
                        <span className={`font-bold ${ledgerOperationToneClass(operation?.status)}`}>
                          {String(operation?.label || operation?.event_type || 'Operation')}
                        </span>
                        <span className="text-gray-500">
                          {formatDateTime(operation?.timestamp, t('cloud_discovery_never', 'Never'))}
                        </span>
                      </div>
                      {!!String(operation?.summary || '').trim() && (
                        <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                          {String(operation.summary)}
                        </div>
                      )}
                      <div className="mt-2 flex flex-wrap gap-2">
                        {!!String(operation?.failure_reason_code || '').trim() ? (
                          <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${ledgerFailureReasonClass(operation.failure_reason_code)}`}>
                            {ledgerFailureReasonLabel(operation.failure_reason_code, t, operation.failure_reason_label)}
                          </span>
                        ) : null}
                        {operation?.retryable ? (
                          <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
                            {t('cloud_accounts_ledger_retry_recommended', 'Retry recommended')}
                          </span>
                        ) : null}
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          data-testid={`cloud-execution-highlight-open-review-${account.id}`}
                          onClick={() => openLedgerReview(account.id)}
                          className={ACTION_BUTTON_NEUTRAL}
                        >
                          {t('cloud_accounts_ledger_open_review', 'Open review')}
                        </button>
                        {ledger?.latest_approval_id ? (
                          <button
                            type="button"
                            data-testid={`cloud-execution-highlight-open-approval-${account.id}`}
                            onClick={() => openLedgerApproval(ledger.latest_approval_id)}
                            className={ACTION_BUTTON_NEUTRAL}
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
          {priorityLedgerReview ? (() => {
            const { account, ledger, pendingApprovals } = priorityLedgerReview;
            const workspaceRecommendation = recommendCloudWorkspace(account, ledger);
            const workspaceLabel = getWorkspaceTitle(workspaceRecommendation.workspace, t);
            const ledgerRetryBlueprint = buildLedgerRetryBlueprint(ledger, t);
            const ledgerNextLane = buildLedgerNextLane(ledger, ledgerRetryBlueprint, t);
            const ledgerSchedule = buildLedgerScheduleSummary(ledger, ledgerRetryBlueprint, t);
            return (
              <div data-testid="cloud-operations-priority-focus" className="mt-4 rounded-xl border border-violet-200 dark:border-violet-900/40 bg-violet-50/60 dark:bg-violet-950/10 px-4 py-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-violet-700 dark:text-violet-300">
                      {t('cloud_accounts_ledger_priority_title', 'Recommended next move')}
                    </div>
                    <div className="mt-2 text-sm font-black text-gray-900 dark:text-white truncate">
                      {String(account?.name || '-')}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-600 dark:text-gray-300">
                      <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                        {String(account?.provider || '').toUpperCase()}
                      </span>
                      <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                        {t('cloud_accounts_ledger_workspace_hint', 'Recommended workspace')}: {workspaceLabel}
                      </span>
                      <span className="rounded-full border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-black/20 px-2.5 py-1">
                        {t('cloud_accounts_ledger_pending_short', 'Pending approvals')}: {pendingApprovals}
                      </span>
                    </div>
                    <div className={`mt-3 inline-flex rounded-lg border px-3 py-2 text-[11px] font-semibold ${ledgerNextLaneToneClass(ledgerNextLane.tone)}`}>
                      {ledgerNextLane.title}
                    </div>
                    <div className="mt-3 text-sm text-gray-600 dark:text-gray-300">
                      {ledgerNextLane.description}
                    </div>
                    <div className={`mt-3 inline-flex rounded-lg border px-3 py-2 text-[11px] font-semibold ${ledgerNextLaneToneClass(ledgerSchedule.tone)}`}>
                      {ledgerSchedule.title}: {ledgerSchedule.windowLabel}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      data-testid="cloud-operations-priority-open-review"
                      onClick={() => openLedgerReview(account.id)}
                      className={ACTION_BUTTON_NEUTRAL}
                    >
                      {t('cloud_accounts_ledger_open_review', 'Open review')}
                    </button>
                    <button
                      type="button"
                      data-testid="cloud-operations-priority-open-workspace"
                      onClick={() => navigate(`/automation?workspace=${workspaceRecommendation.workspace}`)}
                      className={ACTION_BUTTON_NEUTRAL}
                    >
                      {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', workspaceLabel)}
                    </button>
                    <button
                      type="button"
                      data-testid="cloud-operations-priority-open-intents"
                      onClick={() => navigate('/cloud/intents')}
                      className={ACTION_BUTTON_NEUTRAL}
                    >
                      {t('cloud_accounts_ledger_open_intents', 'Open Cloud Intents')}
                    </button>
                    {ledger.latest_approval_id ? (
                      <button
                        type="button"
                        data-testid="cloud-operations-priority-open-approval"
                        onClick={() => navigate(`/approval?focusRequestId=${ledger.latest_approval_id}`)}
                        className={ACTION_BUTTON_NEUTRAL}
                      >
                        {t('cloud_accounts_ledger_open_approval', 'Open Approval')}
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })() : null}
          <div data-testid="cloud-operations-lane-board" className="mt-4 rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50/50 dark:bg-emerald-950/10 px-4 py-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-emerald-700 dark:text-emerald-300">
                  {t('cloud_accounts_ledger_lane_board_title', 'Operating lane board')}
                </div>
                <div className="mt-1 text-sm text-emerald-900/80 dark:text-emerald-100/80">
                  {t(
                    'cloud_accounts_ledger_lane_board_desc',
                    'See how many cloud accounts are sitting in recovery, approval, sync watch, or stable review lanes before diving into individual rows.',
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {ledgerLaneBoard.recovery.entry ? (
                  <button
                    type="button"
                    data-testid="cloud-operations-lane-open-recovery"
                    onClick={() => openLedgerReview(ledgerLaneBoard.recovery.entry.account.id)}
                    className={ACTION_BUTTON_NEUTRAL}
                  >
                    {t('cloud_accounts_ledger_lane_board_open_recovery', 'Open recovery review')}
                  </button>
                ) : null}
                {ledgerLaneBoard.approval.entry ? (
                  <button
                    type="button"
                    data-testid="cloud-operations-lane-open-approval"
                    onClick={() => openLedgerApproval(ledgerLaneBoard.approval.entry.ledger.latest_approval_id)}
                    className={ACTION_BUTTON_NEUTRAL}
                  >
                    {t('cloud_accounts_ledger_lane_board_open_approval', 'Open approval lane')}
                  </button>
                ) : null}
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4 text-xs">
              <div data-testid="cloud-operations-lane-card-recovery" className="rounded-lg border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/10 px-3 py-3">
                <div className="text-[10px] font-bold text-rose-700 dark:text-rose-300">
                  {t('cloud_accounts_ledger_lane_retry_title', 'Recovery lane')}
                </div>
                <div className="mt-1 text-xl font-black text-rose-700 dark:text-rose-300">
                  {ledgerLaneBoard.recovery.count}
                </div>
              </div>
              <div data-testid="cloud-operations-lane-card-approval" className="rounded-lg border border-violet-200 dark:border-violet-900/40 bg-violet-50 dark:bg-violet-950/10 px-3 py-3">
                <div className="text-[10px] font-bold text-violet-700 dark:text-violet-300">
                  {t('cloud_accounts_ledger_lane_approval_title', 'Approval follow-up lane')}
                </div>
                <div className="mt-1 text-xl font-black text-violet-700 dark:text-violet-300">
                  {ledgerLaneBoard.approval.count}
                </div>
              </div>
              <div data-testid="cloud-operations-lane-card-sync" className="rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/10 px-3 py-3">
                <div className="text-[10px] font-bold text-sky-700 dark:text-sky-300">
                  {t('cloud_accounts_ledger_lane_sync_title', 'Sync observation lane')}
                </div>
                <div className="mt-1 text-xl font-black text-sky-700 dark:text-sky-300">
                  {ledgerLaneBoard.sync.count}
                </div>
              </div>
              <div data-testid="cloud-operations-lane-card-stable" className="rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/10 px-3 py-3">
                <div className="text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                  {t('cloud_accounts_ledger_lane_stable_title', 'Stable operating lane')}
                </div>
                <div className="mt-1 text-xl font-black text-emerald-700 dark:text-emerald-300">
                  {ledgerLaneBoard.stable.count}
                </div>
              </div>
            </div>
          </div>
          {ledgerReviewQueue.length > 0 ? (
            <div data-testid="cloud-operations-queue" className="mt-4 rounded-xl border border-sky-200 dark:border-sky-900/40 bg-sky-50/60 dark:bg-sky-950/10 px-3 py-3">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-sky-700 dark:text-sky-300">
                {t('cloud_accounts_ledger_queue_title', 'Review queue')}
              </div>
              <div className="mt-1 text-[11px] text-sky-700 dark:text-sky-200">
                {t(
                  'cloud_accounts_ledger_queue_desc',
                  'These accounts currently need operator review because approvals, retry posture, or blocker findings are still active.',
                )}
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {ledgerReviewQueue.map(({ account, ledger, pendingApprovals }) => {
                  const workspaceRecommendation = recommendCloudWorkspace(account, ledger);
                  const workspaceLabel = getWorkspaceTitle(workspaceRecommendation.workspace, t);
                  const ledgerRetryBlueprint = buildLedgerRetryBlueprint(ledger, t);
                  const ledgerExecutionTimeline = buildLedgerExecutionTimeline(ledger, t);
                  const ledgerNextLane = buildLedgerNextLane(ledger, ledgerRetryBlueprint, t);
                  const ledgerCadence = buildLedgerCadenceSummary(ledger, ledgerRetryBlueprint, t);
                  return (
                  <div
                    key={`cloud-ledger-queue-${account.id}`}
                    className="rounded-lg border border-sky-200/80 dark:border-sky-900/40 bg-white/80 dark:bg-slate-950/40 px-3 py-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-bold text-gray-900 dark:text-white">{String(account.name || '-')}</div>
                      <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${operationsPostureClass(ledger.operations_posture)}`}>
                        {operationsPostureLabel(ledger.operations_posture, t)}
                      </span>
                      {!!String(ledger.last_failure_reason_code || '').trim() && (
                        <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${ledgerFailureReasonClass(ledger.last_failure_reason_code)}`}>
                          {ledgerFailureReasonLabel(ledger.last_failure_reason_code, t, ledger.last_failure_reason_label)}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-[11px] text-gray-500">
                      {String(account.provider || '').toUpperCase()} | {t('cloud_accounts_ledger_pending_short', 'Pending approvals')}: {pendingApprovals}
                    </div>
                    <div className="mt-2 text-[11px] text-sky-700 dark:text-sky-200">
                      {t('cloud_accounts_ledger_workspace_hint', 'Recommended workspace')}: {workspaceLabel}
                    </div>
                    <div className={`mt-2 rounded-lg border px-3 py-2 ${ledgerNextLaneToneClass(ledgerNextLane.tone)}`}>
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.16em]">
                        {ledgerNextLane.title}
                      </div>
                      <div className="mt-1 text-[11px] opacity-90">
                        {ledgerNextLane.description}
                      </div>
                    </div>
                    <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
                      {ledgerExecutionTimeline.description}
                    </div>
                    <div className={`mt-2 rounded-lg border px-3 py-2 ${ledgerNextLaneToneClass(ledgerCadence.tone)}`}>
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.16em]">
                        {ledgerCadence.title}
                      </div>
                      <div className="mt-1 text-[11px] opacity-90">
                        {ledgerCadence.description}
                      </div>
                      <div className="mt-2 text-[11px] opacity-80">
                        {ledgerCadence.laneLabel}
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        data-testid={`cloud-operations-queue-review-${account.id}`}
                        onClick={() => openLedgerReview(account.id)}
                        className={ACTION_BUTTON_NEUTRAL}
                      >
                        {t('cloud_accounts_ledger_open_review', 'Open review')}
                      </button>
                      <button
                        type="button"
                        data-testid={`cloud-operations-queue-workspace-${account.id}`}
                        onClick={() => navigate(`/automation?workspace=${workspaceRecommendation.workspace}`)}
                        className={ACTION_BUTTON_NEUTRAL}
                      >
                        {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', workspaceLabel)}
                      </button>
                      {ledger.latest_approval_id ? (
                        <button
                          type="button"
                          data-testid={`cloud-operations-queue-approval-${account.id}`}
                          onClick={() => openLedgerApproval(ledger.latest_approval_id)}
                          className={ACTION_BUTTON_NEUTRAL}
                        >
                          {t('cloud_accounts_ledger_open_approval', 'Open Approval')}
                        </button>
                      ) : null}
                    </div>
                  </div>
                  );
                })}
              </div>
            </div>
          ) : null}
        </SectionCard>

        <SectionCard className="px-4 py-3">
          <div className="text-[11px] font-bold text-gray-500 mb-2">{t('cloud_discovery_status_title', 'Discovery Status')}</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <div className="rounded-lg border border-emerald-200 dark:border-emerald-800/40 bg-emerald-50 dark:bg-emerald-900/10 px-3 py-2">
              <div className="text-[10px] text-emerald-700 dark:text-emerald-300">{t('cloud_discovery_sync_success', 'success')}</div>
              <div className="font-black text-emerald-700 dark:text-emerald-300">{Number(discoverySummary.success || 0)}</div>
            </div>
            <div className="rounded-lg border border-red-200 dark:border-red-800/40 bg-red-50 dark:bg-red-900/10 px-3 py-2">
              <div className="text-[10px] text-red-700 dark:text-red-300">{t('cloud_discovery_sync_failed', 'failed')}</div>
              <div className="font-black text-red-700 dark:text-red-300">{Number(discoverySummary.failed || 0)}</div>
            </div>
            <div className="rounded-lg border border-amber-200 dark:border-amber-800/40 bg-amber-50 dark:bg-amber-900/10 px-3 py-2">
              <div className="text-[10px] text-amber-700 dark:text-amber-300">{t('cloud_discovery_sync_running', 'running')}</div>
              <div className="font-black text-amber-700 dark:text-amber-300">{Number(discoverySummary.running || 0)}</div>
            </div>
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/30 px-3 py-2">
              <div className="text-[10px] text-gray-600 dark:text-gray-300">{t('cloud_discovery_sync_unknown', 'unknown')}</div>
              <div className="font-black text-gray-700 dark:text-gray-200">{Number(discoverySummary.unknown || 0)}</div>
            </div>
          </div>
          <div className="text-[11px] text-gray-500 mt-2">
            {t('cloud_discovery_last_synced', 'Last synced')}: {formatDateTime(discoverySummary.lastSyncedAt, t('cloud_discovery_never', 'Never'))}
          </div>
        </SectionCard>

        <SectionCard className="px-4 py-3">
          <div className="text-[11px] font-bold text-gray-500 mb-2">{t('cloud_accounts_execution_status_title', 'Intent Execution Readiness')}</div>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs">
            <div data-testid="cloud-accounts-exec-ready" className="rounded-lg border border-emerald-200 dark:border-emerald-800/40 bg-emerald-50 dark:bg-emerald-900/10 px-3 py-2">
              <div className="text-[10px] text-emerald-700 dark:text-emerald-300">{t('cloud_accounts_exec_ready', 'Ready for real apply')}</div>
              <div className="font-black text-emerald-700 dark:text-emerald-300">{Number(executionSummary.ready || 0)}</div>
            </div>
            <div data-testid="cloud-accounts-exec-scaffold" className="rounded-lg border border-sky-200 dark:border-sky-800/40 bg-sky-50 dark:bg-sky-900/10 px-3 py-2">
              <div className="text-[10px] text-sky-700 dark:text-sky-300">{t('cloud_accounts_exec_scaffold', 'Scaffold only')}</div>
              <div className="font-black text-sky-700 dark:text-sky-300">{Number(executionSummary.scaffold || 0)}</div>
            </div>
            <div data-testid="cloud-accounts-exec-missing" className="rounded-lg border border-amber-200 dark:border-amber-800/40 bg-amber-50 dark:bg-amber-900/10 px-3 py-2">
              <div className="text-[10px] text-amber-700 dark:text-amber-300">{t('cloud_accounts_exec_missing', 'Credentials missing')}</div>
              <div className="font-black text-amber-700 dark:text-amber-300">{Number(executionSummary.missing || 0)}</div>
            </div>
            <div data-testid="cloud-accounts-exec-unknown" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/30 px-3 py-2">
              <div className="text-[10px] text-gray-600 dark:text-gray-300">{t('cloud_accounts_exec_unknown', 'Execution unknown')}</div>
              <div className="font-black text-gray-700 dark:text-gray-200">{Number(executionSummary.unknown || 0)}</div>
            </div>
            <div data-testid="cloud-accounts-change-enabled" className="rounded-lg border border-emerald-200 dark:border-emerald-800/40 bg-emerald-50 dark:bg-emerald-900/10 px-3 py-2">
              <div className="text-[10px] text-emerald-700 dark:text-emerald-300">{t('cloud_accounts_change_enabled', 'Change enabled')}</div>
              <div className="font-black text-emerald-700 dark:text-emerald-300">{Number(executionSummary.changeEnabled || 0)}</div>
            </div>
            <div data-testid="cloud-accounts-read-only" className="rounded-lg border border-amber-200 dark:border-amber-800/40 bg-amber-50 dark:bg-amber-900/10 px-3 py-2">
              <div className="text-[10px] text-amber-700 dark:text-amber-300">{t('cloud_accounts_read_only_mode', 'Read-only')}</div>
              <div className="font-black text-amber-700 dark:text-amber-300">{Number(executionSummary.readOnly || 0)}</div>
            </div>
          </div>
          <div className="text-[11px] text-gray-500 mt-2">
            {t('cloud_accounts_execution_status_desc', 'This shows whether each account has enough credentials for Cloud Intents preview or real apply.')}
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-3 text-xs">
            <div className="rounded-xl border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-900/10 px-3 py-3">
              <div className="font-semibold text-sky-800 dark:text-sky-200">
                {t('cloud_accounts_stage_preview_title', 'Preview-ready accounts')}
              </div>
              <div className="mt-1 text-sky-700 dark:text-sky-300">
                {t('cloud_accounts_stage_preview_desc', 'Validate, Pipeline, and Scan stay in the read-only discovery path. Use this state for onboarding and verification.')}
              </div>
            </div>
            <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-900/10 px-3 py-3">
              <div className="font-semibold text-emerald-800 dark:text-emerald-200">
                {t('cloud_accounts_stage_change_title', 'Approval-gated change path')}
              </div>
              <div className="mt-1 text-emerald-700 dark:text-emerald-300">
                {t('cloud_accounts_stage_change_desc', 'These accounts have enough credential coverage for controlled Cloud Intent submission. Changes still stay behind approval and runtime guardrails.')}
              </div>
            </div>
            <div className="rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/10 px-3 py-3">
              <div className="font-semibold text-amber-800 dark:text-amber-200">
                {t('cloud_accounts_stage_guarded_title', 'Live apply guarded')}
              </div>
              <div className="mt-1 text-amber-700 dark:text-amber-300">
                {t('cloud_accounts_stage_guarded_desc', 'If execution is still guarded, keep the account in review-first mode until runtime readiness, approval policy, and live apply controls are clear.')}
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard className="p-5">
          <SectionHeader
            title={isEditMode ? t('cloud_accounts_edit', 'Edit Cloud Account') : t('cloud_accounts_add')}
            className="mb-4"
            right={(
              <div className="flex items-center gap-2 flex-wrap justify-end">
                <button
                  onClick={runDraftPreflight}
                  disabled={loading || !canEdit}
                  className={`${ACTION_BUTTON_PRIMARY} bg-emerald-600 hover:bg-emerald-500`}
                >
                  <ShieldCheck size={16} /> {t('cloud_accounts_preflight', 'Validate')}
                </button>
                <button
                  onClick={submitAccount}
                  disabled={loading || !canEdit}
                  className={`${ACTION_BUTTON_PRIMARY} bg-blue-600 hover:bg-blue-500`}
                >
                  {isEditMode ? <Save size={16} /> : <Plus size={16} />}
                  {isEditMode ? t('common_save', 'Save') : t('cloud_accounts_add_button')}
                </button>
                {isEditMode && (
                  <button
                    data-testid="cloud-account-edit-cancel"
                    onClick={resetAccountDraft}
                    disabled={loading || !canEdit}
                    className={ACTION_BUTTON_NEUTRAL}
                  >
                    <X size={16} /> {t('common_cancel', 'Cancel')}
                  </button>
                )}
              </div>
            )}
          />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Field label="Provider">
              <Select
                value={provider}
                onChange={(v) => {
                  if (isEditMode) return;
                  setProvider(v);
                  setCreds({});
                  setPreflightResult(null);
                }}
                disabled={isEditMode}
                options={[
                  { value: 'aws', label: 'AWS' },
                  { value: 'azure', label: 'Azure' },
                  { value: 'gcp', label: 'GCP' },
                  { value: 'naver', label: 'Naver Cloud' },
                ]}
              />
            </Field>
            <Field label="Name">
              <Input value={name} onChange={setName} placeholder={t('cloud_accounts_name_placeholder', 'customer-prod')} />
            </Field>
            {provider === 'aws' && (
              <Field label="Region">
                <Input value={creds.region || ''} onChange={(v) => setCreds((p) => ({ ...p, region: v }))} placeholder={t('cloud_accounts_region_placeholder', 'ap-northeast-2')} />
              </Field>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
            {provider === 'aws' && (
              <>
                <Field label="AWS Auth">
                  <Select
                    value={String(creds.auth_type || 'access_key')}
                    onChange={(v) => setCreds((p) => ({ ...p, auth_type: v }))}
                    options={[
                      { value: 'access_key', label: 'Access Key' },
                      { value: 'assume_role', label: 'AssumeRole + ExternalId' },
                    ]}
                  />
                </Field>
                {String(creds.auth_type || 'access_key') === 'assume_role' ? (
                  <>
                    <Field label="Role ARN">
                      <Input
                        value={creds.role_arn || ''}
                        onChange={(v) => setCreds((p) => ({ ...p, role_arn: v }))}
                        placeholder={t('cloud_accounts_role_arn_placeholder', 'arn:aws:iam::123456789012:role/NetSphereReadOnlyRole')}
                      />
                    </Field>
                    <Field label="External ID (Optional)">
                      <Input
                        value={creds.external_id || ''}
                        onChange={(v) => setCreds((p) => ({ ...p, external_id: v }))}
                        placeholder={t('cloud_accounts_external_id_placeholder', 'netsphere-prod-extid')}
                      />
                    </Field>
                    <Field label="Role Session Name (Optional)">
                      <Input
                        value={creds.role_session_name || ''}
                        onChange={(v) => setCreds((p) => ({ ...p, role_session_name: v }))}
                        placeholder={t('cloud_accounts_role_session_name_placeholder', 'netsphere-cloud-scan')}
                      />
                    </Field>
                    <Field label="Source Access Key (Optional)">
                      <Input
                        value={creds.source_access_key || ''}
                        onChange={(v) => setCreds((p) => ({ ...p, source_access_key: v }))}
                        placeholder={t('cloud_accounts_source_access_key_placeholder', 'AKIA...')}
                      />
                    </Field>
                    <Field label="Source Secret Key (Optional)">
                      <Input value={creds.source_secret_key || ''} onChange={(v) => setCreds((p) => ({ ...p, source_secret_key: v }))} placeholder="********" type="password" />
                    </Field>
                    <Field label="Source Session Token (Optional)">
                      <Input value={creds.source_session_token || ''} onChange={(v) => setCreds((p) => ({ ...p, source_session_token: v }))} placeholder="..." />
                    </Field>
                  </>
                ) : (
                  <>
                    <Field label="Access Key">
                      <Input
                        value={creds.access_key || ''}
                        onChange={(v) => setCreds((p) => ({ ...p, access_key: v }))}
                        placeholder={t('cloud_accounts_access_key_placeholder', 'AKIA...')}
                      />
                    </Field>
                    <Field label="Secret Key">
                      <Input value={creds.secret_key || ''} onChange={(v) => setCreds((p) => ({ ...p, secret_key: v }))} placeholder="********" type="password" />
                    </Field>
                    <Field label="Session Token (Optional)">
                      <Input value={creds.session_token || ''} onChange={(v) => setCreds((p) => ({ ...p, session_token: v }))} placeholder="..." />
                    </Field>
                  </>
                )}
              </>
            )}

            {provider === 'azure' && (
              <>
                <Field label="Tenant ID"><Input value={creds.tenant_id || ''} onChange={(v) => setCreds((p) => ({ ...p, tenant_id: v }))} placeholder="..." /></Field>
                <Field label="Subscription ID"><Input value={creds.subscription_id || ''} onChange={(v) => setCreds((p) => ({ ...p, subscription_id: v }))} placeholder="..." /></Field>
                <Field label="Client ID"><Input value={creds.client_id || ''} onChange={(v) => setCreds((p) => ({ ...p, client_id: v }))} placeholder="..." /></Field>
                <Field label="Client Secret"><Input value={creds.client_secret || ''} onChange={(v) => setCreds((p) => ({ ...p, client_secret: v }))} placeholder="********" type="password" /></Field>
              </>
            )}

            {provider === 'gcp' && (
              <>
                <Field label="Project ID"><Input value={creds.project_id || ''} onChange={(v) => setCreds((p) => ({ ...p, project_id: v }))} placeholder="..." /></Field>
                <Field label="Regions (Optional)">
                  <Input
                    value={creds.regions || ''}
                    onChange={(v) => setCreds((p) => ({ ...p, regions: v }))}
                    placeholder={t('cloud_accounts_regions_placeholder', 'asia-northeast3,us-east1')}
                  />
                </Field>
                <Field label="Service Account JSON">
                  <textarea
                    value={creds.service_account_json || ''}
                    onChange={(e) => setCreds((p) => ({ ...p, service_account_json: e.target.value }))}
                    placeholder="{ ... }"
                    className="w-full min-h-[120px] bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-gray-900 dark:text-white text-sm"
                  />
                </Field>
              </>
            )}

            {provider === 'naver' && (
              <>
                <Field label="Access Key"><Input value={creds.access_key || ''} onChange={(v) => setCreds((p) => ({ ...p, access_key: v }))} placeholder="..." /></Field>
                <Field label="Secret Key"><Input value={creds.secret_key || ''} onChange={(v) => setCreds((p) => ({ ...p, secret_key: v }))} placeholder="********" type="password" /></Field>
                <Field label="Region Code (Optional)">
                  <Input
                    value={creds.region_code || ''}
                    onChange={(v) => setCreds((p) => ({ ...p, region_code: v }))}
                    placeholder={t('cloud_accounts_region_code_placeholder', 'KR')}
                  />
                </Field>
              </>
            )}
          </div>

          {activePreset?.preflight_checks?.length > 0 && (
            <div className="mt-4 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-black/20 px-4 py-3 text-xs text-gray-600 dark:text-gray-300">
              <div className="font-bold mb-1">{t('cloud_accounts_preflight_checks', 'Preflight checks')}</div>
              <div>{activePreset.preflight_checks.join(' | ')}</div>
            </div>
          )}
          {activePreset?.read_only_policy && (
            <div className="mt-3 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#15171a] px-4 py-3 text-xs text-gray-600 dark:text-gray-300">
              <div className="font-bold mb-1">{t('cloud_accounts_policy_preset', 'Read-only policy preset')}</div>
              <pre className="whitespace-pre-wrap text-[11px] leading-5">{String(activePreset.read_only_policy)}</pre>
            </div>
          )}

          {preflightResult && (
            <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${
              String(preflightResult?.status || '').toLowerCase() === 'ok'
                ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700/50 dark:bg-emerald-900/10 dark:text-emerald-300'
                : 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700/50 dark:bg-amber-900/10 dark:text-amber-300'
            }`}>
              <div className="font-bold mb-1">{t('cloud_accounts_preflight_result', 'Validation result')}</div>
              <div className="text-xs mb-2">{preflightResult.summary || '-'}</div>
              <div className="space-y-1">
                {(Array.isArray(preflightResult.checks) ? preflightResult.checks : []).map((c) => (
                  <div key={`${c.key}-${c.message}`} className="text-xs">
                    [{c.ok ? 'OK' : 'FAIL'}] {c.key}: {c.message}
                  </div>
                ))}
              </div>
            </div>
          )}

          {pipelineResult && (
            <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${
              String(pipelineResult?.status || '').toLowerCase() === 'ok'
                ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700/50 dark:bg-emerald-900/10 dark:text-emerald-300'
                : 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700/50 dark:bg-amber-900/10 dark:text-amber-300'
            }`}>
              <div className="font-bold mb-1">{t('cloud_accounts_pipeline_result', 'Pipeline result')}</div>
              <div className="text-xs mb-2">
                status={String(pipelineResult?.status || '-')} | accounts={Number(pipelineResult?.total_accounts || 0)} | resources={Number(pipelineResult?.scanned_resources || 0)} | failed={Number(pipelineResult?.failed_accounts || 0)}
              </div>
              <div className="text-xs mb-2">
                idempotency_key={String(pipelineResult?.idempotency_key || '-')}
              </div>
              {pipelineResult?.normalized_by_provider && (
                <div className="text-xs mb-2">
                  {Object.entries(pipelineResult.normalized_by_provider).map(([k, v]) => `${k}:${v}`).join(' | ') || '-'}
                </div>
              )}
              {Array.isArray(pipelineResult?.accounts) && pipelineResult.accounts.length > 0 && (
                <div className="space-y-1">
                  {pipelineResult.accounts.slice(0, 8).map((r) => (
                    <div key={`${r.account_id}-${r.provider}-${r.scan_status}`} className="text-xs">
                      [{String(r.provider || '').toUpperCase()} #{r.account_id}] preflight={r.preflight_status} scan={r.scan_status} count={Number(r.scan_count || 0)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {bootstrapResult && (
            <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${
              String(bootstrapResult?.status || '').toLowerCase() === 'ok'
                ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700/50 dark:bg-emerald-900/10 dark:text-emerald-300'
                : String(bootstrapResult?.status || '').toLowerCase() === 'approval_required'
                  ? 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-700/50 dark:bg-sky-900/10 dark:text-sky-300'
                : 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700/50 dark:bg-amber-900/10 dark:text-amber-300'
            }`}>
              <div className="font-bold mb-1">{t('cloud_bootstrap_result', 'Bootstrap result')}</div>
              {String(bootstrapResult?.status || '').toLowerCase() === 'approval_required' && (
                <div className="text-xs mb-2">
                  {t('cloud_bootstrap_approval_pending_hint', 'Live bootstrap was converted into an approval request. Review and approve it in Approval Center before execution.')}
                </div>
              )}
              <div className="text-xs mb-2">
                status={String(bootstrapResult?.status || '-')} | targets={Number(bootstrapResult?.total_targets || 0)} | success={Number(bootstrapResult?.success_targets || 0)} | failed={Number(bootstrapResult?.failed_targets || 0)} | dry_run={Number(bootstrapResult?.dry_run_targets || 0)}
              </div>
              <div className="text-xs mb-2">
                approval_id={String(bootstrapResult?.approval_id ?? '-')} | execution_id={String(bootstrapResult?.execution_id || '-')} | idempotency_key={String(bootstrapResult?.idempotency_key || '-')}
              </div>
              {Array.isArray(bootstrapResult?.results) && bootstrapResult.results.length > 0 && (
                <div className="space-y-1">
                  {bootstrapResult.results.slice(0, 8).map((r, idx) => (
                    <div key={`${r.account_id}-${r.resource_id}-${r.status}-${idx}`} className="text-xs">
                      [{String(r.provider || '').toUpperCase()} #{r.account_id}] {r.resource_name || r.resource_id} status={r.status} wave={r.wave ?? '-'} exec={String(r.execution_id || bootstrapResult?.execution_id || '-')}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </SectionCard>

        <SectionCard className="p-5">
          <SectionHeader title={t('cloud_accounts_title')} className="mb-3" />
          {loading && accounts.length === 0 ? (
            <InlineLoading className="py-8" />
          ) : accounts.length === 0 ? (
            <InlineEmpty label={t('cloud_accounts_empty')} className="py-8" />
          ) : (
            <div className="space-y-2">
              {accounts.map((a) => {
                const isFocusedAccount = focusedAccountId && String(a.id) === String(focusedAccountId);
                const ledger = ledgerByAccountId[Number(a.id)] || null;
                const ledgerRetryBlueprint = buildLedgerRetryBlueprint(ledger, t);
                  const ledgerReviewGuide = buildLedgerReviewGuide(ledger, t);
                  const ledgerDriftSummary = buildLedgerDriftSummary(a, ledger, t);
                  const providerRunbook = buildProviderRunbook(a, t);
                  const ledgerExecutionTimeline = buildLedgerExecutionTimeline(ledger, t);
                  const ledgerNextLane = buildLedgerNextLane(ledger, ledgerRetryBlueprint, t);
                  const ledgerCadence = buildLedgerCadenceSummary(ledger, ledgerRetryBlueprint, t);
                  const ledgerSchedule = buildLedgerScheduleSummary(ledger, ledgerRetryBlueprint, t);
                  const workspaceRecommendation = recommendCloudWorkspace(a, ledger);
                const workspaceLabel = getWorkspaceTitle(workspaceRecommendation.workspace, t);
                const reviewExpanded = expandedLedgerAccountId && String(expandedLedgerAccountId) === String(a.id);
                const retryButtonBusy = ledgerRetryKey === `${Number(a.id)}:${ledgerRetryBlueprint?.key || ''}`;
                return (
                <div
                  key={a.id}
                  data-testid={`cloud-account-row-${a.id}`}
                  data-testid-ledger={ledger ? 'available' : 'empty'}
                  data-account-focus-id={String(a.id)}
                  className={`rounded-xl border px-4 py-3 transition-all ${
                    isFocusedAccount
                      ? 'border-sky-400 dark:border-sky-500 bg-sky-50 dark:bg-sky-950/20 shadow-[0_0_0_1px_rgba(14,165,233,0.35)]'
                      : 'border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-black/20'
                  }`}
                >
                  <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-3">
                    <div className="min-w-0 flex-1">
                    <div className="font-bold truncate">{a.name}</div>
                    <div className="text-xs text-gray-500 flex items-center gap-2 flex-wrap">
                      {String(a.provider || '').toUpperCase()} | {a.is_active ? t('common_active', 'active') : t('common_inactive', 'inactive')}
                      <span className={`px-2 py-0.5 rounded-full font-bold ${syncStatusClass(a.sync_status)}`}>
                        {formatSyncStatus(a.sync_status)}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full font-bold ${readinessToneClass(a?.execution_readiness?.stage)}`}>
                        {readinessLabel(a?.execution_readiness?.stage, t)}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full font-bold ${changeModeClass(a?.execution_readiness)}`}>
                        {changeModeLabel(a?.execution_readiness, t)}
                      </span>
                    </div>
                    <div className="text-[11px] text-gray-500 mt-0.5 truncate">
                      {t('cloud_discovery_last_synced', 'Last synced')}: {formatDateTime(a.last_synced_at, t('cloud_discovery_never', 'Never'))}
                    </div>
                    {!!String(a.sync_message || '').trim() && (
                      <div className="text-[11px] text-gray-500 mt-0.5 truncate" title={String(a.sync_message)}>
                        {t('cloud_discovery_sync_message', 'Message')}: {String(a.sync_message)}
                      </div>
                    )}
                    {Array.isArray(a?.execution_readiness?.missing_fields) && a.execution_readiness.missing_fields.length > 0 && (
                      <div className="text-[11px] text-amber-600 dark:text-amber-300 mt-0.5 truncate">
                        {t('cloud_accounts_exec_missing_fields', 'Missing')}: {a.execution_readiness.missing_fields.join(', ')}
                      </div>
                    )}
                    {Array.isArray(a?.execution_readiness?.warnings) && a.execution_readiness.warnings.length > 0 && (
                      <div className="text-[11px] text-sky-600 dark:text-sky-300 mt-0.5">
                        {String(a.execution_readiness.warnings[0] || '')}
                      </div>
                    )}
                    {!!String(a?.execution_readiness?.change_mode_reason || '').trim() && (
                      <div className="text-[11px] text-gray-500 mt-0.5">
                        {String(a.execution_readiness.change_mode_reason)}
                      </div>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {buildGuardrailBadges(a, t).map((badge) => (
                        <span
                          key={`${a.id}-${badge.label}`}
                          className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-bold ${guardrailBadgeClass(badge.tone)}`}
                        >
                          {badge.label}
                        </span>
                      ))}
                    </div>
                    {isFocusedAccount && (
                      <div className="mt-2 inline-flex items-center rounded-full border border-sky-300 dark:border-sky-700 bg-white/80 dark:bg-sky-950/30 px-2.5 py-1 text-[11px] font-bold text-sky-700 dark:text-sky-200">
                        {t('cloud_accounts_focus_badge', 'Focused from topology')}
                      </div>
                    )}
                    <div
                      data-testid={`cloud-account-ledger-${a.id}`}
                      className="mt-3 rounded-xl border border-gray-200 dark:border-gray-800 bg-white/70 dark:bg-[#121417] px-3 py-3"
                    >
                      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="text-[10px] font-bold uppercase tracking-wide text-gray-500">
                            {t('cloud_accounts_ledger_inline_title', 'Operations ledger')}
                          </div>
                          {ledger ? (
                            <>
                              <div className="mt-2 flex flex-wrap items-center gap-2">
                                <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${operationsPostureClass(ledger.operations_posture)}`}>
                                  {operationsPostureLabel(ledger.operations_posture, t)}
                                </span>
                                <span className="text-[11px] text-gray-500">
                                  {t('cloud_accounts_ledger_pending_short', 'Pending approvals')}: {Number(ledger.pending_approvals || 0)}
                                </span>
                                <span className="text-[11px] text-gray-500">
                                  {t('cloud_accounts_ledger_blockers_short', 'Blockers')}: {Number(ledger.blocker_events || 0)}
                                </span>
                                {ledger.retry_recommended && (
                                  <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
                                    {t('cloud_accounts_ledger_retry_now', 'Retry recommended')}
                                  </span>
                                )}
                              </div>
                              <div className="mt-2 text-[11px] text-gray-500">
                                {t('cloud_accounts_ledger_last_run_fmt', 'Latest: {type} | {status} | {time}')
                                  .replace('{type}', String(ledger.last_operation_type || '-'))
                                  .replace('{status}', String(ledger.last_operation_status || '-'))
                                  .replace('{time}', formatDateTime(ledger.last_operation_at, t('cloud_discovery_never', 'Never')))}
                              </div>
                              {!!String(ledger.last_failure_reason_code || '').trim() && (
                                <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
                                  <span className="text-gray-500">
                                    {t('cloud_accounts_ledger_failure_reason', 'Failure reason')}:
                                  </span>
                                  <span className={`px-2 py-0.5 rounded-full font-bold ${ledgerFailureReasonClass(ledger.last_failure_reason_code)}`}>
                                    {ledgerFailureReasonLabel(ledger.last_failure_reason_code, t, ledger.last_failure_reason_label)}
                                  </span>
                                </div>
                              )}
                              {!!String(ledger.last_failure_message || '').trim() && (
                                <div className="mt-1 text-[11px] text-amber-600 dark:text-amber-300">
                                  {t('cloud_accounts_ledger_failure_hint', 'Latest failure')}: {String(ledger.last_failure_message)}
                                </div>
                              )}
                              {ledger.retry_recommended && ledgerRetryBlueprint ? (
                                <div className="mt-3 rounded-lg border border-rose-200 dark:border-rose-900/40 bg-rose-50/70 dark:bg-rose-950/20 px-3 py-3">
                                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-rose-700 dark:text-rose-300">
                                    {t('cloud_accounts_ledger_next_step', 'Recommended next step')}
                                  </div>
                                  <div className="mt-1 text-[11px] text-rose-700 dark:text-rose-200">
                                    {ledgerRetryBlueprint.desc}
                                  </div>
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    <button
                                      type="button"
                                      data-testid={`cloud-account-ledger-retry-${a.id}`}
                                      onClick={() => runLedgerRetry(a, ledger)}
                                      disabled={loading || !canEdit || retryButtonBusy}
                                      className={`${ACTION_BUTTON_PRIMARY} bg-rose-600 hover:bg-rose-500`}
                                    >
                                      {retryButtonBusy ? t('cloud_accounts_ledger_retry_running', 'Retrying...') : ledgerRetryBlueprint.label}
                                    </button>
                                  </div>
                                </div>
                              ) : null}
                            </>
                          ) : (
                            <div className="mt-2 text-[11px] text-gray-500">
                              {t('cloud_accounts_ledger_empty', 'No recent cloud operations recorded for this account yet.')}
                            </div>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {ledger ? (
                            <button
                              type="button"
                              data-testid={`cloud-account-ledger-open-${a.id}`}
                              onClick={() => setExpandedLedgerAccountId((current) => (String(current) === String(a.id) ? '' : String(a.id)))}
                              className={ACTION_BUTTON_NEUTRAL}
                            >
                              {reviewExpanded
                                ? t('cloud_accounts_ledger_hide_review', 'Hide review')
                                : t('cloud_accounts_ledger_open_review', 'Open review')}
                            </button>
                          ) : null}
                          {ledger?.latest_approval_id ? (
                            <button
                              type="button"
                              data-testid={`cloud-account-open-approval-${a.id}`}
                              onClick={() => navigate(`/approval?focusRequestId=${ledger.latest_approval_id}`)}
                              className={ACTION_BUTTON_NEUTRAL}
                            >
                              {t('cloud_accounts_ledger_open_approval', 'Open Approval')}
                            </button>
                          ) : null}
                        </div>
                      </div>
                      {Array.isArray(ledger?.recent_operations) && ledger.recent_operations.length > 0 && (
                        <div className="mt-3 grid gap-2">
                          {ledger.recent_operations.slice(0, 3).map((op, idx) => (
                            <div
                              key={`${a.id}-${op.event_type}-${op.timestamp || idx}`}
                              className="rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-black/20 px-3 py-2"
                            >
                              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                                <span className={`font-bold ${ledgerOperationToneClass(op.status)}`}>{String(op.label || op.event_type || 'Operation')}</span>
                                <span className="text-gray-500">{formatDateTime(op.timestamp, t('cloud_discovery_never', 'Never'))}</span>
                                <span className="text-gray-500">status={String(op.status || '-')}</span>
                                {Number(op.blocker_count || 0) > 0 && (
                                  <span className="text-amber-600 dark:text-amber-300">
                                    blockers={Number(op.blocker_count || 0)}
                                  </span>
                                )}
                                {!!String(op.failure_reason_code || '').trim() && (
                                  <span className={`px-2 py-0.5 rounded-full font-bold ${ledgerFailureReasonClass(op.failure_reason_code)}`}>
                                    {ledgerFailureReasonLabel(op.failure_reason_code, t, op.failure_reason_label)}
                                  </span>
                                )}
                              </div>
                              {!!String(op.summary || '').trim() && (
                                <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">{String(op.summary)}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      {ledger && reviewExpanded ? (
                        <div
                          data-testid={`cloud-account-ledger-review-${a.id}`}
                          className="mt-3 rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50/70 dark:bg-sky-950/20 px-3 py-3"
                        >
                          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                            <div className="min-w-0 flex-1">
                              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-sky-700 dark:text-sky-300">
                                {t('cloud_accounts_ledger_review_title', 'Operator review')}
                              </div>
                              <div className="mt-1 text-[11px] text-sky-700 dark:text-sky-200">
                                {t(
                                  'cloud_accounts_ledger_review_desc',
                                  'Use this review to decide whether the next safe step is validate, scan, pipeline recovery, or approval follow-up.',
                                )}
                              </div>
                              <div className="mt-3 grid gap-2 md:grid-cols-2">
                                <div className="rounded-lg border border-sky-200/70 dark:border-sky-900/40 bg-white/80 dark:bg-slate-950/40 px-3 py-2">
                                  <div className="text-[10px] font-bold uppercase tracking-wide text-gray-500">
                                    {t('cloud_accounts_ledger_review_last_success', 'Last success')}
                                  </div>
                                  <div className="mt-1 text-[11px] text-gray-700 dark:text-gray-200">
                                    {formatDateTime(ledger.last_success_at, t('cloud_discovery_never', 'Never'))}
                                  </div>
                                </div>
                                <div className="rounded-lg border border-sky-200/70 dark:border-sky-900/40 bg-white/80 dark:bg-slate-950/40 px-3 py-2">
                                  <div className="text-[10px] font-bold uppercase tracking-wide text-gray-500">
                                    {t('cloud_accounts_ledger_review_last_failure', 'Last failure')}
                                  </div>
                                  <div className="mt-1 text-[11px] text-gray-700 dark:text-gray-200">
                                    {formatDateTime(ledger.last_failure_at, t('cloud_discovery_never', 'Never'))}
                                  </div>
                                </div>
                              </div>
                              <div className="mt-3 rounded-lg border border-sky-200/70 dark:border-sky-900/40 bg-white/80 dark:bg-slate-950/40 px-3 py-3">
                                <div className="text-[11px] font-bold text-sky-800 dark:text-sky-100">
                                  {ledgerReviewGuide.title}
                                </div>
                                <ul className="mt-2 space-y-1.5 text-[11px] text-gray-700 dark:text-gray-200">
                                  {ledgerReviewGuide.bullets.map((bullet, index) => (
                                    <li key={`${a.id}-ledger-guide-${index}`} className="flex items-start gap-2">
                                      <span className="mt-[3px] inline-block h-1.5 w-1.5 rounded-full bg-sky-500" />
                                      <span>{bullet}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                              <div
                                data-testid={`cloud-account-ledger-drift-${a.id}`}
                                className={`mt-3 rounded-lg border px-3 py-3 ${ledgerDriftToneClass(ledgerDriftSummary.tone)}`}
                              >
                                <div className="text-[11px] font-bold">
                                  {ledgerDriftSummary.title}
                                </div>
                                <div className="mt-1 text-[11px] opacity-90">
                                  {ledgerDriftSummary.description}
                                </div>
                              </div>
                              <div
                                data-testid={`cloud-account-ledger-runbook-${a.id}`}
                                className="mt-3 rounded-lg border border-sky-200/70 dark:border-sky-900/40 bg-white/80 dark:bg-slate-950/40 px-3 py-3"
                              >
                                <div className="text-[11px] font-bold text-sky-800 dark:text-sky-100">
                                  {providerRunbook.title}
                                </div>
                                <ul className="mt-2 space-y-1.5 text-[11px] text-gray-700 dark:text-gray-200">
                                  {providerRunbook.bullets.map((bullet, index) => (
                                    <li key={`${a.id}-runbook-${index}`} className="flex items-start gap-2">
                                      <span className="mt-[3px] inline-block h-1.5 w-1.5 rounded-full bg-sky-500" />
                                      <span>{bullet}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                              <div
                                data-testid={`cloud-account-ledger-history-${a.id}`}
                                className="mt-3 rounded-lg border border-sky-200/70 dark:border-sky-900/40 bg-white/80 dark:bg-slate-950/40 px-3 py-3"
                              >
                                <div className="text-[11px] font-bold text-sky-800 dark:text-sky-100">
                                  {ledgerExecutionTimeline.title}
                                </div>
                                <div className="mt-1 text-[11px] text-gray-700 dark:text-gray-200">
                                  {ledgerExecutionTimeline.description}
                                </div>
                                {ledgerExecutionTimeline.items.length ? (
                                  <div className="mt-3 grid gap-2">
                                    {ledgerExecutionTimeline.items.map((op, index) => (
                                      <div
                                        key={`${a.id}-review-history-${op.event_type || 'op'}-${op.timestamp || index}`}
                                        className="rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-black/20 px-3 py-2"
                                      >
                                        <div className="flex flex-wrap items-center gap-2 text-[11px]">
                                          <span className={`font-bold ${ledgerOperationToneClass(op.status)}`}>
                                            {String(op.label || op.event_type || 'Operation')}
                                          </span>
                                          <span className="text-gray-500">
                                            {formatDateTime(op.timestamp, t('cloud_discovery_never', 'Never'))}
                                          </span>
                                          <span className="text-gray-500">status={String(op.status || '-')}</span>
                                          {Number(op.blocker_count || 0) > 0 ? (
                                            <span className="text-amber-600 dark:text-amber-300">
                                              blockers={Number(op.blocker_count || 0)}
                                            </span>
                                          ) : null}
                                          {!!String(op.failure_reason_code || '').trim() ? (
                                            <span className={`px-2 py-0.5 rounded-full font-bold ${ledgerFailureReasonClass(op.failure_reason_code)}`}>
                                              {ledgerFailureReasonLabel(op.failure_reason_code, t, op.failure_reason_label)}
                                            </span>
                                          ) : null}
                                        </div>
                                        {!!String(op.summary || '').trim() ? (
                                          <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">{String(op.summary)}</div>
                                        ) : null}
                                      </div>
                                    ))}
                                  </div>
                                ) : null}
                              </div>
                            </div>
                            <div className="w-full max-w-xs rounded-lg border border-sky-200/70 dark:border-sky-900/40 bg-white/80 dark:bg-slate-950/40 px-3 py-3">
                              <div className="text-[10px] font-bold uppercase tracking-wide text-gray-500">
                                {t('cloud_accounts_ledger_review_next_action', 'Next action')}
                              </div>
                              <div className="mt-2 rounded-lg border border-sky-200/70 dark:border-sky-900/40 bg-sky-50/70 dark:bg-sky-950/10 px-3 py-2">
                                <div className="text-[10px] font-bold uppercase tracking-wide text-sky-700 dark:text-sky-200">
                                  {t('cloud_accounts_ledger_workspace_hint', 'Recommended workspace')}
                                </div>
                                <div className="mt-1 text-[11px] text-sky-700 dark:text-sky-100">
                                  {workspaceLabel}
                                </div>
                              </div>
                              <div
                                data-testid={`cloud-account-ledger-next-lane-${a.id}`}
                                className={`mt-2 rounded-lg border px-3 py-3 ${ledgerNextLaneToneClass(ledgerNextLane.tone)}`}
                              >
                                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em]">
                                  {ledgerNextLane.title}
                                </div>
                                <div className="mt-1 text-[11px] opacity-90">
                                  {ledgerNextLane.description}
                                </div>
                              </div>
                              <div
                                data-testid={`cloud-account-ledger-cadence-${a.id}`}
                                className={`mt-2 rounded-lg border px-3 py-3 ${ledgerNextLaneToneClass(ledgerCadence.tone)}`}
                              >
                                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em]">
                                  {ledgerCadence.title}
                                </div>
                                <div className="mt-1 text-[11px] opacity-90">
                                  {ledgerCadence.description}
                                </div>
                                <div className="mt-2 text-[11px] opacity-80">
                                  {ledgerCadence.laneLabel}
                                </div>
                              </div>
                              <div
                                data-testid={`cloud-account-ledger-schedule-${a.id}`}
                                className={`mt-2 rounded-lg border px-3 py-3 ${ledgerNextLaneToneClass(ledgerSchedule.tone)}`}
                              >
                                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em]">
                                  {ledgerSchedule.title}
                                </div>
                                <div className="mt-1 text-[11px] opacity-90">
                                  {ledgerSchedule.description}
                                </div>
                                <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] opacity-80">
                                  <span>{ledgerSchedule.windowLabel}</span>
                                  <span>|</span>
                                  <span>
                                    {t('cloud_accounts_ledger_schedule_last_attempt', 'Last attempt')}: {formatDateTime(ledgerSchedule.lastAttemptAt, t('cloud_discovery_never', 'Never'))}
                                  </span>
                                </div>
                              </div>
                              <div className="mt-2 flex flex-col gap-2">
                                {ledger.retry_recommended && ledgerRetryBlueprint ? (
                                  <button
                                    type="button"
                                    data-testid={`cloud-account-ledger-review-retry-${a.id}`}
                                    onClick={() => runLedgerRetry(a, ledger)}
                                    disabled={loading || !canEdit || retryButtonBusy}
                                    className={`${ACTION_BUTTON_PRIMARY} w-full bg-sky-600 hover:bg-sky-500`}
                                  >
                                    {retryButtonBusy ? t('cloud_accounts_ledger_retry_running', 'Retrying...') : ledgerRetryBlueprint.label}
                                  </button>
                                ) : null}
                                <button
                                  type="button"
                                  data-testid={`cloud-account-ledger-review-workspace-${a.id}`}
                                  onClick={() => navigate(`/automation?workspace=${workspaceRecommendation.workspace}`)}
                                  className={ACTION_BUTTON_NEUTRAL}
                                >
                                  {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', workspaceLabel)}
                                </button>
                                {ledger.latest_approval_id ? (
                                  <button
                                    type="button"
                                    data-testid={`cloud-account-ledger-review-approval-${a.id}`}
                                    onClick={() => navigate(`/approval?focusRequestId=${ledger.latest_approval_id}`)}
                                    className={ACTION_BUTTON_NEUTRAL}
                                  >
                                    {t('cloud_accounts_ledger_open_approval', 'Open Approval')}
                                  </button>
                                ) : null}
                                <button
                                  type="button"
                                  data-testid={`cloud-account-ledger-review-intents-${a.id}`}
                                  onClick={() => navigate('/cloud/intents')}
                                  className={ACTION_BUTTON_NEUTRAL}
                                >
                                  {t('cloud_accounts_ledger_open_intents', 'Open Cloud Intents')}
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                    <div className="flex flex-col sm:flex-row gap-2 xl:justify-end xl:items-center">
                      <div className="flex items-center gap-1 min-w-[220px]">
                      <span className="text-[11px] text-gray-500">{t('cloud_bootstrap_account_path', 'Account Path')}</span>
                      <select
                        value={normalizeBootstrapPath(a.provider, accountBootstrapPaths[Number(a.id)])}
                        onChange={(e) => saveAccountBootstrapPath(a, e.target.value)}
                        disabled={loading || !canEdit || !!savingBootstrapPaths[Number(a.id)]}
                        className="flex-1 min-w-[150px] bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-lg px-2 py-1.5 text-xs text-gray-900 dark:text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                      >
                        {getBootstrapOptionsByProvider(a.provider).map((opt) => (
                          <option key={`${a.id}-${opt.value}`} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        <button
                          data-testid={`cloud-account-edit-${a.id}`}
                          onClick={() => beginEdit(a)}
                          disabled={loading || !canEdit}
                          className={`${ACTION_BUTTON_PRIMARY} bg-gray-700 hover:bg-gray-600`}
                        >
                          <Pencil size={14} /> {t('common_edit', 'Edit')}
                        </button>
                        <button
                          data-testid={`cloud-account-validate-${a.id}`}
                          onClick={() => runAccountPreflight(a.id)}
                          disabled={loading || !canEdit}
                          className={`${ACTION_BUTTON_PRIMARY} bg-indigo-600 hover:bg-indigo-500`}
                        >
                          {t('cloud_accounts_validate', 'Validate')}
                        </button>
                        <button
                          data-testid={`cloud-account-pipeline-${a.id}`}
                          onClick={() => runPipeline(a.id)}
                          disabled={loading || !canEdit || !a.is_active}
                          className={`${ACTION_BUTTON_PRIMARY} bg-sky-600 hover:bg-sky-500`}
                        >
                          {t('cloud_accounts_pipeline', 'Pipeline')}
                        </button>
                        <button
                          data-testid={`cloud-account-bootstrap-${a.id}`}
                          onClick={() => runBootstrap(a.id, false)}
                          disabled={loading || !canEdit || !a.is_active}
                          className={`${ACTION_BUTTON_PRIMARY} bg-violet-600 hover:bg-violet-500`}
                        >
                          {t('cloud_bootstrap_run_live', 'Live Bootstrap')}
                        </button>
                        <button
                          data-testid={`cloud-account-scan-${a.id}`}
                          onClick={() => scan(a.id)}
                          disabled={loading || !canEdit || !a.is_active}
                          className={`${ACTION_BUTTON_PRIMARY} bg-emerald-600 hover:bg-emerald-500`}
                        >
                          {t('cloud_accounts_scan')}
                        </button>
                        <button
                          data-testid={`cloud-account-delete-${a.id}`}
                          onClick={() => del(a.id)}
                          disabled={loading || !canEdit}
                          className={`${ACTION_BUTTON_PRIMARY} bg-red-600 hover:bg-red-500`}
                        >
                          <Trash2 size={14} /> {t('cloud_accounts_delete')}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                );
              })}
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
};

export default CloudAccountsPage;

