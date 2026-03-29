export const normalizeDeviceStatus = (status) => String(status || '').trim().toLowerCase();
export const normalizeManagementState = (state) => String(state || '').trim().toLowerCase() || 'managed';

export const isDeviceOnline = (status) => normalizeDeviceStatus(status) === 'online';
export const isDiscoveredOnlyDevice = (managementState) => normalizeManagementState(managementState) === 'discovered_only';

export const normalizeOperationalStatus = (status) => String(status || '').trim().toLowerCase().replace(/\s+/g, '_');

const OPERATIONAL_STATUS_TONES = {
  healthy: new Set(['healthy', 'ok', 'success', 'enabled', 'reachable', 'online', 'completed', 'passed', 'not_needed', 'mock_rollback_completed']),
  warning: new Set(['warning', 'degraded', 'approval_required', 'pending']),
  critical: new Set([
    'critical',
    'failed',
    'error',
    'dispatch_failed',
    'blocked',
    'down',
    'offline',
    'pre_check_failed',
    'precheck_failed',
    'post_check_failed',
    'postcheck_failed',
  ]),
  progress: new Set(['queued', 'running', 'dispatching', 'in_progress']),
  disabled: new Set(['disabled', 'unavailable', 'idle', 'skipped_prepare_only', 'skipped_no_accounts']),
};

const OPERATIONAL_STATUS_LABELS = {
  approval_required: 'approval required',
  pre_check_failed: 'pre-check failed',
  precheck_failed: 'pre-check failed',
  post_check_failed: 'post-check failed',
  postcheck_failed: 'post-check failed',
  dispatch_failed: 'dispatch failed',
  in_progress: 'in progress',
  skipped_prepare_only: 'skipped (prepare only)',
  skipped_no_accounts: 'skipped (no accounts)',
  mock_rollback_completed: 'mock rollback completed',
};

export const getOperationalStatusTone = (status) => {
  const key = normalizeOperationalStatus(status);
  if (!key) return 'neutral';
  for (const [tone, values] of Object.entries(OPERATIONAL_STATUS_TONES)) {
    if (values.has(key)) return tone;
  }
  return 'neutral';
};

export const getOperationalStatusLabel = (status) => {
  const key = normalizeOperationalStatus(status);
  if (!key) return 'n/a';
  return OPERATIONAL_STATUS_LABELS[key] || key.replace(/_/g, ' ');
};

export const getOperationalStatusBadgeClass = (status) => {
  const tone = getOperationalStatusTone(status);
  if (tone === 'healthy') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300';
  if (tone === 'warning') return 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300';
  if (tone === 'critical') return 'bg-rose-100 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300';
  if (tone === 'progress') return 'bg-cyan-100 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300';
  if (tone === 'disabled') return 'bg-slate-100 text-slate-700 dark:bg-slate-500/10 dark:text-slate-300';
  return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
};

export const getOperationalStatusHint = (status) => {
  const tone = getOperationalStatusTone(status);
  if (tone === 'healthy') return 'No blocking condition is currently detected.';
  if (tone === 'warning') return 'Attention is required, but the workflow can continue after review.';
  if (tone === 'critical') return 'A blocking condition was detected. Operator intervention is recommended.';
  if (tone === 'progress') return 'Background work is still running or waiting to be dispatched.';
  if (tone === 'disabled') return 'This workflow is disabled by policy or configuration.';
  return 'No additional operational context is available yet.';
};

export const getDeviceStatusChipClass = (status) => (
  isDeviceOnline(status)
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20'
    : 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:border-rose-500/20'
);

export const getDeviceStatusTextClass = (status) => (
  isDeviceOnline(status)
    ? 'text-emerald-700 dark:text-emerald-300'
    : 'text-rose-700 dark:text-rose-300'
);

export const getDeviceStatusDotClass = (status) => (
  isDeviceOnline(status) ? 'bg-emerald-500' : 'bg-rose-500'
);

export const getManagedDeviceStatusMeta = (status, managementState) => {
  if (isDiscoveredOnlyDevice(managementState)) {
    return {
      active: false,
      label: 'DISCOVERED',
      summary: 'Visible in topology only',
      chipClass: 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-500/10 dark:text-slate-300 dark:border-slate-500/20',
      dotClass: 'bg-slate-400',
      textClass: 'text-slate-700 dark:text-slate-300',
      isDiscoveredOnly: true,
    };
  }

  const online = isDeviceOnline(status);
  return {
    active: online,
    label: online ? 'ONLINE' : 'OFFLINE',
    summary: online ? 'Reachable' : 'Attention Needed',
    chipClass: getDeviceStatusChipClass(status),
    dotClass: getDeviceStatusDotClass(status),
    textClass: getDeviceStatusTextClass(status),
    isDiscoveredOnly: false,
  };
};

const CLOUD_COMPUTE_TYPES = new Set(['virtual_machine', 'instance', 'vm']);
const CLOUD_UNAVAILABLE_STATUSES = new Set(['offline', 'down', 'error', 'failed', 'deleted', 'unavailable']);

export const getCloudResourceStatusMeta = (status, resourceType) => {
  const normalizedStatus = normalizeDeviceStatus(status);
  const normalizedType = String(resourceType || '').trim().toLowerCase();
  const isCompute = CLOUD_COMPUTE_TYPES.has(normalizedType);

  if (isCompute) {
    const online = isDeviceOnline(status);
    return {
      active: online,
      label: online ? 'ONLINE' : 'OFFLINE',
      summary: online ? 'Reachable' : 'Powered off or unavailable',
      chipClass: getDeviceStatusChipClass(status),
      dotClass: getDeviceStatusDotClass(status),
      textClass: getDeviceStatusTextClass(status),
      isCompute: true,
    };
  }

  const available = normalizedStatus ? !CLOUD_UNAVAILABLE_STATUSES.has(normalizedStatus) : true;
  return {
    active: available,
    label: available ? 'AVAILABLE' : 'UNAVAILABLE',
    summary: available ? 'Provisioned' : 'Unavailable',
    chipClass: available
      ? 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/20'
      : 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-500/10 dark:text-slate-300 dark:border-slate-500/20',
    dotClass: available ? 'bg-sky-500' : 'bg-slate-400',
    textClass: available ? 'text-sky-700 dark:text-sky-300' : 'text-slate-700 dark:text-slate-300',
    isCompute: false,
  };
};
