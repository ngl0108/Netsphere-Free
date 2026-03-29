import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DeviceService, OpsService, PreviewService, ServiceGroupService } from '../../api/services';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import {
  Activity, Server, MapPin, ShieldCheck, AlertOctagon,
  CheckCircle, RefreshCw, LayoutGrid, Wifi, Users, Radio, Globe, Bot, Download, X, ExternalLink
} from 'lucide-react';
import {
  PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import TrafficChart from './TrafficChart'; // [수정] TrafficChart 컴포넌트 Import
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import useVisiblePolling from '../../hooks/useVisiblePolling';
import { InlineLoading } from '../common/PageState';
import {
  compareServiceImpactAlerts,
  getOperationsPressureGuidance,
  getOperationsPressureLabel,
  getOperationsPressureLevel,
  getWorkspaceTitle,
  getServicePressureIndex,
  getServiceReviewAverageHealth,
  recommendServiceWorkspace,
  summarizeServiceImpactAlertFocus,
  summarizeServiceReviewPosture,
  summarizeServiceReviewQueue,
} from '../../utils/serviceOperations';
import {
  buildDevicePath,
  buildGrafanaFleetHealthUrl,
  buildObservabilityPath,
  buildTopologyPath,
} from '../../utils/observabilityLinks';
import { getOperationalStatusBadgeClass, getOperationalStatusLabel } from '../../utils/deviceStatusTone';

// [추가] 상대 시간 포맷팅 함수
const formatRelativeTime = (isoString) => {
  if (!isoString) return '';
  const date = new Date(isoString);
  const now = new Date();
  const diffInSeconds = Math.floor((now - date) / 1000);

  if (diffInSeconds < 60) {
    return t('dashboard_time_seconds_ago', '{value}s ago').replace('{value}', String(diffInSeconds));
  }
  if (diffInSeconds < 3600) {
    return t('dashboard_time_minutes_ago', '{value}m ago').replace(
      '{value}',
      String(Math.floor(diffInSeconds / 60)),
    );
  }
  if (diffInSeconds < 86400) {
    return t('dashboard_time_hours_ago', '{value}h ago').replace(
      '{value}',
      String(Math.floor(diffInSeconds / 3600)),
    );
  }
  return t('dashboard_time_days_ago', '{value}d ago').replace(
    '{value}',
    String(Math.floor(diffInSeconds / 86400)),
  );
};
const normalizeStatusToken = (value) => String(value || '').trim().toLowerCase().replace(/\s+/g, '_');
const formatFailureCauseLabel = (value) => {
  const key = normalizeStatusToken(value);
  if (!key) return '-';
  const labels = {
    precheck_failed: 'pre-check failed',
    pre_check_failed: 'pre-check failed',
    postcheck_failed: 'post-check failed',
    post_check_failed: 'post-check failed',
    auth_failed: 'auth failed',
    auth_denied: 'auth denied',
    http_4xx: 'http 4xx',
    http_5xx: 'http 5xx',
    timeout: 'timeout',
    unknown: 'unknown',
  };
  return labels[key] || key.replace(/_/g, ' ');
};
const formatExecutionStatusLabel = (value) => {
  const key = normalizeStatusToken(value);
  if (!key) return 'n/a';
  if (key === 'ok') return 'ok';
  if (key === 'success') return 'success';
  if (key === 'failed') return 'failed';
  return formatFailureCauseLabel(key);
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
const formatSignedDelta = (value) => {
  if (value === null || value === undefined) return '-';
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  if (n > 0) return `+${n}`;
  return `${n}`;
};
const formatReadinessDirectionLabel = (value) => {
  const key = normalizeStatusToken(value);
  if (key === 'improved') return t('dashboard_readiness_improved', 'improved');
  if (key === 'regressed') return t('dashboard_readiness_regressed', 'regressed');
  if (key === 'stable') return t('dashboard_readiness_stable', 'stable');
  return t('dashboard_readiness_unknown', 'unknown');
};
const formatReadinessCheckLabel = (row) => {
  const title = String(row?.title || '').trim();
  if (title) return title;
  const id = String(row?.id || '').trim();
  if (!id) return '-';
  return id.replace(/\./g, ' ');
};
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
const serviceHealthTone = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'critical') return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-300';
  if (normalized === 'degraded' || normalized === 'review') return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
  return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300';
};
const formatServiceHealthLabel = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'critical') return t('service_groups_health_status_critical', 'Critical');
  if (normalized === 'degraded') return t('service_groups_health_status_degraded', 'Degraded');
  if (normalized === 'review') return t('service_groups_health_status_review', 'Needs review');
  return t('service_groups_health_status_healthy', 'Healthy');
};
const getServiceIssueNextActionLabel = (summary) => {
  const criticalGroups = Number(summary?.critical_group_count || 0);
  const reviewGroups = Number(summary?.review_group_count || 0);
  const matchedMembers = Number(summary?.matched_member_count || 0);
  const healthStatus = String(summary?.primary_health_status || '').trim().toLowerCase();
  if (healthStatus === 'critical' || criticalGroups > 0) {
    return t(
      'dashboard_priority_service_next_action_critical',
      'Open service review first and confirm the impacted topology path before taking action.',
    );
  }
  if (reviewGroups > 0) {
    return t(
      'dashboard_priority_service_next_action_review',
      'Review the mapped service group and open the service-aware alerts before changing scope.',
    );
  }
  if (matchedMembers > 0) {
    return t(
      'dashboard_priority_service_next_action_scope',
      'Use topology and observability to confirm the assets in scope before moving into actions.',
    );
  }
  return t(
    'dashboard_priority_service_next_action_stable',
    'Service impact is mapped. Keep this alert tied to the service review flow as you investigate.',
  );
};
const statusBadgeClass = (value) => getOperationalStatusBadgeClass(value);
const formatReleaseValue = (value) => {
  if (value === null || value === undefined || value === '') return '-';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (Number.isInteger(n)) return String(n);
  if (Math.abs(n) >= 100) return n.toFixed(0);
  return n.toFixed(2);
};
const formatReleasePercent = (value) => {
  if (value === null || value === undefined) return '-';
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return `${n.toFixed(2)}%`;
};
const formatReleaseDateTime = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString();
};
const formatReleaseRefreshStatusLabel = (value) => {
  const key = normalizeStatusToken(value);
  if (key === 'queued') return t('dashboard_release_refresh_status_queued', 'queued');
  if (key === 'running') return t('dashboard_release_refresh_status_running', 'running');
  if (key === 'completed') return t('dashboard_release_refresh_status_completed', 'completed');
  if (key === 'failed') return t('dashboard_release_refresh_status_failed', 'failed');
  return t('dashboard_release_refresh_status_idle', 'idle');
};
const formatReleaseRefreshStageLabel = (value) => {
  const key = normalizeStatusToken(value);
  if (key === 'synthetic_validation') return t('dashboard_release_refresh_stage_synthetic_validation', 'synthetic validation');
  if (key === 'release_evidence_cache') return t('dashboard_release_refresh_stage_release_evidence_cache', 'release evidence cache');
  if (key === 'completed') return t('dashboard_release_refresh_stage_completed', 'completed');
  return t('dashboard_release_refresh_stage_idle', 'idle');
};
const formatReleaseProfileLabel = (value) => {
  const key = normalizeStatusToken(value);
  if (!key) return 'CI';
  return key.toUpperCase();
};
const formatReleaseAutomationLabel = (enabled) => (
  enabled
    ? t('dashboard_release_automation_enabled', 'enabled')
    : t('dashboard_release_automation_disabled', 'disabled')
);
const formatReleaseSampleLabel = (value) => {
  const labels = {
    discovery_jobs: 'Discovery jobs',
    change_events: 'Change events',
    northbound_deliveries: 'Northbound deliveries',
    autonomy_issues_created: 'Autonomy issues created',
    autonomy_actions_executed: 'Autonomy actions executed',
  };
  return labels[String(value || '').trim()] || String(value || '').replace(/_/g, ' ') || '-';
};

const unwrapApiData = (res) => res?.data?.data || res?.data || null;

const ReleaseEvidenceModal = ({
  isOpen,
  onClose,
  releaseData,
  releaseSummary,
  releaseGateRows,
}) => {
  if (!isOpen) return null;

  const overallStatus = String(releaseSummary?.overall_status || 'unavailable').toLowerCase();
  const acceptedGates = Number(releaseSummary?.accepted_gates || 0);
  const availableGates = Number(releaseSummary?.available_gates || 0);
  const totalGates = Number(releaseSummary?.total_gates || 0);
  const blockingGates = Array.isArray(releaseSummary?.blocking_gates) ? releaseSummary.blocking_gates : [];
  const warningGates = Array.isArray(releaseSummary?.warning_gates) ? releaseSummary.warning_gates : [];
  const inProgressGates = Array.isArray(releaseSummary?.in_progress_gates) ? releaseSummary.in_progress_gates : [];

  const formatStatusLabel = (value) => String(value || 'unavailable').replace(/_/g, ' ');
  const blockingLabels = releaseGateRows.filter((row) => blockingGates.includes(row.key)).map((row) => row.label);
  const warningLabels = releaseGateRows.filter((row) => warningGates.includes(row.key)).map((row) => row.label);

  const renderSectionDetails = (row) => {
    const details = row.section?.details || {};
    if (row.key === 'kpi_readiness') {
      const blockingChecks = Array.isArray(details.blocking_checks) ? details.blocking_checks : [];
      const sampleGaps = Array.isArray(details.sample_gaps) ? details.sample_gaps : [];
      return (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
            <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
              {t('dashboard_release_detail_blocking_checks', 'Blocking checks')}
            </div>
            {blockingChecks.length > 0 ? (
              <div className="mt-2 space-y-2">
                {blockingChecks.map((check) => (
                  <div key={check.id} className="rounded-lg border border-gray-200 dark:border-white/5 bg-white/80 dark:bg-black/20 p-2">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="truncate font-semibold text-gray-800 dark:text-gray-100">{check.title || check.id}</span>
                      <span className={`rounded px-1.5 py-0.5 font-bold uppercase ${statusBadgeClass(check.status)}`}>
                        {formatStatusLabel(check.status)}
                      </span>
                    </div>
                    <div className="mt-1 text-[11px] font-mono text-gray-500">
                      {t('dashboard_release_detail_observed', 'observed')} {formatReleaseValue(check.value)} {check.operator || ''} {formatReleaseValue(check.threshold)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-2 text-xs text-gray-500">{t('dashboard_release_detail_no_items', 'No detail items')}</div>
            )}
          </div>
          <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
            <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
              {t('dashboard_release_detail_sample_gaps', 'Sample gaps')}
            </div>
            {sampleGaps.length > 0 ? (
              <div className="mt-2 space-y-2">
                {sampleGaps.map((sample) => (
                  <div key={sample.id} className="rounded-lg border border-gray-200 dark:border-white/5 bg-white/80 dark:bg-black/20 p-2">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="truncate font-semibold text-gray-800 dark:text-gray-100">
                        {sample.title || formatReleaseSampleLabel(sample.id)}
                      </span>
                      <span className={`rounded px-1.5 py-0.5 font-bold uppercase ${sample.met === false ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'}`}>
                        {sample.met === false ? 'gap' : 'n/a'}
                      </span>
                    </div>
                    <div className="mt-1 text-[11px] font-mono text-gray-500">
                      {t('dashboard_release_detail_observed', 'observed')} {formatReleaseValue(sample.observed)} / {t('dashboard_release_detail_threshold', 'threshold')} {formatReleaseValue(sample.threshold)}
                    </div>
                    <div className="mt-1 text-[11px] font-mono text-gray-500">
                      coverage {formatReleasePercent(sample.coverage_pct)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-2 text-xs text-gray-500">{t('dashboard_release_detail_no_items', 'No detail items')}</div>
            )}
          </div>
        </div>
      );
    }
    if (row.key === 'vendor_support') {
      const weakestDeviceTypes = Array.isArray(details.weakest_device_types) ? details.weakest_device_types : [];
      return (
        <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
          <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
            {t('dashboard_release_detail_weakest_device_types', 'Weakest device types')}
          </div>
          {weakestDeviceTypes.length > 0 ? (
            <div className="mt-2 space-y-2">
              {weakestDeviceTypes.map((item) => (
                <div key={`${item.device_type}-${item.readiness}`} className="rounded-lg border border-gray-200 dark:border-white/5 bg-white/80 dark:bg-black/20 p-2">
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="font-semibold text-gray-800 dark:text-gray-100">{item.device_type}</span>
                    <span className={`rounded px-1.5 py-0.5 font-bold uppercase ${statusBadgeClass(item.readiness === 'partial' || item.readiness === 'none' ? 'warning' : item.readiness === 'full' ? 'healthy' : 'in_progress')}`}>
                      {formatStatusLabel(item.readiness)}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] font-mono text-gray-500">
                    score {formatReleaseValue(item.readiness_score)}
                  </div>
                  <div className="mt-1 text-[11px] text-gray-500">
                    {t('dashboard_release_detail_capabilities', 'Capabilities')}: {(Array.isArray(item.capabilities) && item.capabilities.length > 0) ? item.capabilities.join(', ') : '-'}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-2 text-xs text-gray-500">{t('dashboard_release_detail_no_items', 'No detail items')}</div>
          )}
        </div>
      );
    }
    if (row.key === 'discovery_hinting') {
      const sync = details.sync || {};
      const benchmark = details.benchmark || {};
      const topVendors = Array.isArray(details.top_vendors) ? details.top_vendors : [];
      const topDrivers = Array.isArray(details.top_drivers) ? details.top_drivers : [];
      return (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
            <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
              {t('dashboard_release_detail_hint_sync', 'Hint sync')}
            </div>
            <div className="mt-2 space-y-2 text-xs text-gray-600 dark:text-gray-300">
              <div className="flex items-center justify-between">
                <span>{t('dashboard_release_detail_hint_rules', 'active rules')}</span>
                <span className="font-mono">{formatReleaseValue(row.section?.active_rules)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>{t('dashboard_release_detail_hint_rule_version', 'rule version')}</span>
                <span className="text-right font-mono">{sync.rule_version || '-'}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>{t('dashboard_release_detail_hint_last_pull', 'last pull')}</span>
                <span className="text-right font-mono">{formatReleaseDateTime(sync.last_pull_at)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>{t('dashboard_release_detail_hint_pull_status', 'pull status')}</span>
                <span className={`rounded px-1.5 py-0.5 font-bold uppercase ${statusBadgeClass(String(sync.last_pull_status || '').toLowerCase().startsWith('ok') ? 'healthy' : String(sync.last_pull_status || '').toLowerCase().startsWith('failed') ? 'critical' : 'warning')}`}>
                  {sync.last_pull_status || 'idle'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>{t('dashboard_release_detail_hint_last_push', 'last push')}</span>
                <span className="text-right font-mono">{formatReleaseDateTime(sync.last_push_at)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>{t('dashboard_release_detail_hint_push_status', 'push status')}</span>
                <span className={`rounded px-1.5 py-0.5 font-bold uppercase ${statusBadgeClass(String(sync.last_push_status || '').toLowerCase().startsWith('ok') ? 'healthy' : String(sync.last_push_status || '').toLowerCase().startsWith('failed') ? 'critical' : 'warning')}`}>
                  {sync.last_push_status || 'idle'}
                </span>
              </div>
            </div>
          </div>
          <div className="space-y-3">
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                {t('dashboard_release_detail_hint_benchmark', 'Hint benchmark')}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-300">
                <div className="flex items-center justify-between gap-4">
                  <span>{t('dashboard_release_detail_hint_total', 'total')}</span>
                  <span className="font-mono">{formatReleaseValue(benchmark.total)}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>{t('dashboard_release_detail_hint_success', 'success')}</span>
                  <span className="font-mono">{formatReleaseValue(benchmark.success)}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>{t('dashboard_release_detail_hint_success_rate', 'success rate')}</span>
                  <span className="font-mono">{formatReleasePercent(benchmark.success_rate_pct)}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>{t('dashboard_release_detail_hint_false_positive_rate', 'false positive')}</span>
                  <span className="font-mono">{formatReleasePercent(benchmark.false_positive_rate_pct)}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>{t('dashboard_release_detail_hint_false_positive_count', 'false positives')}</span>
                  <span className="font-mono">{formatReleaseValue(benchmark.false_positive)}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>{t('dashboard_release_detail_hint_unknown_after_hint', 'unknown after hint')}</span>
                  <span className="font-mono">{formatReleaseValue(benchmark.unknown_after_hint)}</span>
                </div>
              </div>
            </div>
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                {t('dashboard_release_detail_hint_top_vendors', 'Top vendors')}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {topVendors.length > 0 ? topVendors.map((item) => (
                  <span key={item.vendor} className="rounded-full border border-cyan-200 bg-cyan-50 px-2 py-0.5 text-[11px] font-semibold text-cyan-700 dark:border-cyan-500/30 dark:bg-cyan-900/20 dark:text-cyan-300">
                    {item.vendor} {formatReleasePercent(item.success_rate_pct)}
                  </span>
                )) : (
                  <div className="text-xs text-gray-500">{t('dashboard_release_detail_no_items', 'No detail items')}</div>
                )}
              </div>
              <div className="mt-3 text-[10px] font-black uppercase tracking-widest text-gray-500">
                {t('dashboard_release_detail_hint_top_drivers', 'Top drivers')}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {topDrivers.length > 0 ? topDrivers.map((item) => (
                  <span key={item.driver} className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[11px] font-semibold text-violet-700 dark:border-violet-500/30 dark:bg-violet-900/20 dark:text-violet-300">
                    {item.driver} {formatReleasePercent(item.success_rate_pct)}
                  </span>
                )) : (
                  <div className="text-xs text-gray-500">{t('dashboard_release_detail_no_items', 'No detail items')}</div>
                )}
              </div>
            </div>
          </div>
        </div>
      );
    }
    if (row.key === 'synthetic_validation') {
      const scenarios = Array.isArray(details.scenarios) ? details.scenarios : [];
      const firstWaveVendors = Array.isArray(details.first_wave_vendors) ? details.first_wave_vendors : [];
      const failedAssertions = Array.isArray(details.failed_assertions) ? details.failed_assertions : [];
      return (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
            <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
              {t('dashboard_release_detail_scenarios', 'Scenario catalog')}
            </div>
            {scenarios.length > 0 ? (
              <div className="mt-2 space-y-2">
                {scenarios.map((scenario) => (
                  <div key={scenario.name} className="rounded-lg border border-gray-200 dark:border-white/5 bg-white/80 dark:bg-black/20 p-2">
                    <div className="text-xs font-semibold text-gray-800 dark:text-gray-100">{scenario.name}</div>
                    <div className="mt-1 text-[11px] font-mono text-gray-500">
                      {formatReleaseValue(scenario.devices)} dev / {formatReleaseValue(scenario.links)} links / {formatReleaseValue(scenario.events)} events
                    </div>
                    <div className="mt-1 text-[11px] font-mono text-gray-500">
                      critical {formatReleaseValue(scenario.critical)} / warning {formatReleaseValue(scenario.warning)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-2 text-xs text-gray-500">{t('dashboard_release_detail_no_items', 'No detail items')}</div>
            )}
          </div>
          <div className="space-y-3">
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                {t('dashboard_release_detail_soak_summary', 'Soak summary')}
              </div>
              <div className="mt-2 grid grid-cols-1 gap-2 text-xs text-gray-600 dark:text-gray-300">
                <div className="flex items-center justify-between">
                  <span>duplicate ratio</span>
                  <span className="font-mono">{formatReleasePercent(Number(details.soak_summary?.max_duplicate_ratio || 0) * 100)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>max queue</span>
                  <span className="font-mono">{formatReleaseValue(details.soak_summary?.max_queue_depth)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>max eps</span>
                  <span className="font-mono">{formatReleaseValue(details.soak_summary?.max_throughput_eps)}</span>
                </div>
              </div>
            </div>
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                {t('dashboard_release_detail_first_wave_vendors', 'First wave vendors')}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {firstWaveVendors.length > 0 ? firstWaveVendors.map((vendor) => (
                  <span key={vendor} className="rounded-full border border-cyan-200 bg-cyan-50 px-2 py-0.5 text-[11px] font-semibold text-cyan-700 dark:border-cyan-500/30 dark:bg-cyan-900/20 dark:text-cyan-300">
                    {vendor}
                  </span>
                )) : (
                  <div className="text-xs text-gray-500">{t('dashboard_release_detail_no_items', 'No detail items')}</div>
                )}
              </div>
              {failedAssertions.length > 0 && (
                <>
                  <div className="mt-3 text-[10px] font-black uppercase tracking-widest text-gray-500">
                    {t('dashboard_release_detail_failed_assertions', 'Failed assertions')}
                  </div>
                  <div className="mt-2 space-y-1">
                    {failedAssertions.map((item) => (
                      <div key={item} className="text-[11px] font-mono text-red-500">{item}</div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      );
    }
    if (row.key === 'northbound_soak') {
      const lastRecord = details.last_record || {};
      const window = details.window || {};
      return (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
            <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
              {t('dashboard_release_detail_last_delivery', 'Last delivery')}
            </div>
            <div className="mt-2 space-y-2 text-xs text-gray-600 dark:text-gray-300">
              <div className="flex items-center justify-between">
                <span>mode</span>
                <span className="font-mono">{lastRecord.mode || '-'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>http</span>
                <span className="font-mono">{formatReleaseValue(lastRecord.http_status)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>latency</span>
                <span className="font-mono">{lastRecord.latency_ms === null || lastRecord.latency_ms === undefined ? '-' : `${formatReleaseValue(lastRecord.latency_ms)}ms`}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>attempts</span>
                <span className="font-mono">{formatReleaseValue(lastRecord.attempts)}</span>
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
            <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
              {t('dashboard_release_detail_run_window', 'Run window')}
            </div>
            <div className="mt-2 space-y-2 text-xs text-gray-600 dark:text-gray-300">
              <div className="flex items-center justify-between gap-4">
                <span>start</span>
                <span className="text-right font-mono">{formatReleaseDateTime(window.started_at)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>finish</span>
                <span className="text-right font-mono">{formatReleaseDateTime(window.expected_finish_at)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>elapsed</span>
                <span className="font-mono">{formatReleaseValue(window.elapsed_seconds)}s</span>
              </div>
              <div className="flex items-center justify-between">
                <span>remaining</span>
                <span className="font-mono">{formatReleaseValue(window.remaining_seconds)}s</span>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="text-xs text-gray-500">{t('dashboard_release_detail_no_items', 'No detail items')}</div>
    );
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm p-4 sm:p-6" onClick={onClose}>
      <div
        className="mx-auto flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-2xl dark:border-white/10 dark:bg-[#101317]"
        onClick={(event) => event.stopPropagation()}
        data-testid="dashboard-release-evidence-modal"
      >
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-6 py-5 dark:border-white/10">
          <div>
            <div className="flex items-center gap-2">
              <Activity size={18} className="text-cyan-500" />
              <h2 className="text-lg font-black tracking-tight text-gray-900 dark:text-white">
                {t('dashboard_release_details_title', 'Release Evidence Details')}
              </h2>
            </div>
            <div className="mt-1 text-sm text-gray-500">
              {t('dashboard_release_updated', 'updated')} {formatRelativeTime(releaseData?.generated_at) || '-'}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className={`rounded px-2.5 py-1 text-[11px] font-black uppercase tracking-wider ${statusBadgeClass(overallStatus)}`}>
              {formatStatusLabel(overallStatus)}
            </span>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-200 p-2 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:border-white/10 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
              aria-label={t('common_close', 'Close')}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto px-6 py-5">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-white/10 dark:bg-black/20">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">{t('dashboard_release_gates', 'Accepted Gates')}</div>
              <div className="mt-1 text-2xl font-black text-gray-900 dark:text-white">{acceptedGates} / {totalGates}</div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-white/10 dark:bg-black/20">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">{t('dashboard_release_available', 'Available Evidence')}</div>
              <div className="mt-1 text-2xl font-black text-gray-900 dark:text-white">{availableGates} / {totalGates}</div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-white/10 dark:bg-black/20">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">{t('dashboard_release_blocking_gates', 'Blocking Gates')}</div>
              <div className={`mt-1 text-2xl font-black ${blockingGates.length > 0 ? 'text-red-500' : 'text-gray-900 dark:text-white'}`}>{blockingGates.length}</div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-white/10 dark:bg-black/20">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">{t('dashboard_release_in_progress_gates', 'In Progress')}</div>
              <div className={`mt-1 text-2xl font-black ${inProgressGates.length > 0 ? 'text-cyan-500' : 'text-gray-900 dark:text-white'}`}>{inProgressGates.length}</div>
            </div>
          </div>

          {(blockingLabels.length > 0 || warningLabels.length > 0) && (
            <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-white/10 dark:bg-black/20">
                <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">{t('dashboard_release_blocking_gates', 'Blocking Gates')}</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {blockingLabels.length > 0 ? blockingLabels.map((item) => (
                    <span key={item} className="rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-red-700 dark:bg-red-900/30 dark:text-red-300">{item}</span>
                  )) : (
                    <span className="text-xs text-gray-500">none</span>
                  )}
                </div>
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-white/10 dark:bg-black/20">
                <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">{t('dashboard_release_warning_gates', 'Warning Gates')}</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {warningLabels.length > 0 ? warningLabels.map((item) => (
                    <span key={item} className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">{item}</span>
                  )) : (
                    <span className="text-xs text-gray-500">none</span>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="mt-5 space-y-4">
            {releaseGateRows.map((row) => {
              const section = row.section || {};
              const available = !!section.available;
              const sectionStatus = String(section.status || 'unavailable').toLowerCase();
              return (
                <div
                  key={row.key}
                  className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/[0.03]"
                  data-testid={`dashboard-release-evidence-section-${row.key}`}
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <div className="text-sm font-black tracking-tight text-gray-900 dark:text-white">{row.label}</div>
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-black uppercase tracking-wider ${statusBadgeClass(sectionStatus)}`}>
                          {formatStatusLabel(sectionStatus)}
                        </span>
                      </div>
                      <div className="mt-1 text-sm font-semibold text-gray-700 dark:text-gray-100">
                        {available ? row.detail : t('dashboard_release_no_evidence', 'No evidence')}
                      </div>
                      <div className="mt-1 text-[11px] text-gray-500">
                        {available ? (row.subdetail || `${t('dashboard_release_updated', 'updated')} ${formatRelativeTime(section.generated_at || releaseData?.generated_at) || '-'}`) : t('dashboard_release_no_evidence', 'No evidence')}
                      </div>
                      {section.source_name && (
                        <div className="mt-1 text-[11px] font-mono text-gray-500">
                          {t('dashboard_release_detail_source', 'Evidence file')}: {section.source_name}
                        </div>
                      )}
                    </div>
                    <div className="text-[11px] font-mono text-gray-500">
                      {t('dashboard_release_updated', 'updated')} {formatReleaseDateTime(section.generated_at || releaseData?.generated_at)}
                    </div>
                  </div>
                  <div className="mt-4">
                    {renderSectionDetails(row)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

const DashboardPage = () => {
  useLocaleRerender();
  const navigate = useNavigate();
  const { user, isOperator } = useAuth();
  const { toast } = useToast();
  const [stats, setStats] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [selfHealth, setSelfHealth] = useState(null);
  const [readinessHistory, setReadinessHistory] = useState(null);
  const [releaseEvidence, setReleaseEvidence] = useState(null);
  const [changeTraces, setChangeTraces] = useState([]);
  const [releaseBundleDownloading, setReleaseBundleDownloading] = useState(false);
  const [releaseRefreshStarting, setReleaseRefreshStarting] = useState(false);
  const [releaseEvidenceModalOpen, setReleaseEvidenceModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sites, setSites] = useState([]); // [NEW] Sites List
  const [selectedSite, setSelectedSite] = useState(""); // [NEW] Selected Site ID
  const [previewPolicy, setPreviewPolicy] = useState(null);
  const [serviceReviewQueue, setServiceReviewQueue] = useState([]);
  const [serviceReviewLoading, setServiceReviewLoading] = useState(false);
  const [serviceReviewError, setServiceReviewError] = useState('');
  const loadInFlightRef = useRef(null);

  // 데이터 자동 갱신을 위한 Ref

  // 1. 데이터 로드 (백그라운드 갱신 지원)
  const loadData = async (isInitial = false) => {
    if (loadInFlightRef.current) return loadInFlightRef.current;
    if (isInitial) setLoading(true);
    const request = (async () => {
      try {
        const readinessParams = { days: 30, limit: 30 };
        if (selectedSite) {
          readinessParams.site_id = Number(selectedSite);
        }
        const readinessPromise = OpsService.getKpiReadinessHistory(readinessParams).catch(() => null);
        const releaseEvidencePromise = OpsService.getReleaseEvidence().catch(() => null);
        const traceParams = { days: 30, limit: 6 };
        if (selectedSite) {
          traceParams.site_id = Number(selectedSite);
        }
        const tracesPromise = DeviceService.getDashboardChangeTraces(traceParams).catch(() => null);
        const [statsRes, analyticsRes, readinessRes, releaseEvidenceRes, traceRes] = await Promise.all([
          DeviceService.getDashboardStats(selectedSite || null), // [FIX] Pass site filter
          DeviceService.getAnalytics('24h'),
          readinessPromise,
          releaseEvidencePromise,
          tracesPromise,
        ]);

        setStats(unwrapApiData(statsRes));
        setAnalytics(unwrapApiData(analyticsRes));
        setReadinessHistory(unwrapApiData(readinessRes));
        setReleaseEvidence(unwrapApiData(releaseEvidenceRes));
        const tracePayload = unwrapApiData(traceRes);
        setChangeTraces(Array.isArray(tracePayload?.items) ? tracePayload.items : []);
      } catch (err) {
        console.error("Dashboard Load Error:", err);
      } finally {
        if (isInitial) setLoading(false);
      }
    })().finally(() => {
      loadInFlightRef.current = null;
    });
    loadInFlightRef.current = request;
    return request;
  };

  // 0. 사이트 목록 로드
  useEffect(() => {
    DeviceService.getSites()
      .then(res => setSites(res.data))
      .catch(err => console.error("Failed to load sites", err));
  }, []);

  useEffect(() => {
    let cancelled = false;
    PreviewService.getPolicy()
      .then((res) => {
        if (!cancelled) setPreviewPolicy(res?.data || null);
      })
      .catch(() => {
        if (!cancelled) setPreviewPolicy(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setServiceReviewLoading(true);
    ServiceGroupService.list()
      .then((res) => {
        if (cancelled) return;
        const rows = Array.isArray(res?.data) ? res.data : [];
        setServiceReviewQueue(summarizeServiceReviewQueue(rows));
        setServiceReviewError('');
      })
      .catch((err) => {
        if (cancelled) return;
        setServiceReviewQueue([]);
        setServiceReviewError(err?.response?.data?.detail || err?.message || t('service_groups_review_queue_empty', 'No service groups need immediate review right now. Service posture is stable.'));
      })
      .finally(() => {
        if (!cancelled) setServiceReviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 2. 초기 로드 및 5초 주기 Polling
  // selectedSite가 변경될 때마다 Polling을 재설정하여 필터 적용
  useEffect(() => {
    loadData(true);
  }, [selectedSite]); // [IMP] Re-run when site changes

  useEffect(() => {
    if (!releaseEvidenceModalOpen) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        setReleaseEvidenceModalOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [releaseEvidenceModalOpen]);

  const releaseRefreshRunning = useMemo(() => {
    const status = normalizeStatusToken(releaseEvidence?.refresh?.status);
    return status === 'queued' || status === 'running';
  }, [releaseEvidence]);

  const dashboardHasActiveSignals = useMemo(() => {
    const issueCount = Array.isArray(stats?.issues)
      ? stats.issues.length
      : Number(stats?.active_issues || 0);
    const changeFailureRate = Number(stats?.change_kpi?.change_failure_rate_pct || 0);
    const closedLoopStatus = String(stats?.closed_loop_kpi?.status || '').toLowerCase();
    const closedLoopHealthy =
      closedLoopStatus === '' ||
      closedLoopStatus === 'healthy' ||
      closedLoopStatus === 'idle' ||
      closedLoopStatus === 'disabled';
    return issueCount > 0 || changeFailureRate > 0 || !closedLoopHealthy || releaseRefreshRunning;
  }, [stats, releaseRefreshRunning]);
  const dashboardPollIntervalMs = dashboardHasActiveSignals ? 5000 : 15000;
  const dashboardPollMinGapMs = dashboardHasActiveSignals ? 2000 : 6000;

  useVisiblePolling(() => loadData(false), dashboardPollIntervalMs, {
    enabled: true,
    immediate: false,
    runOnVisible: true,
    minGapMs: dashboardPollMinGapMs,
    backoffOnError: false,
    backoffMultiplier: 2,
    backoffMaxIntervalMs: 60000,
  });

  useEffect(() => {
    if (!isOperator()) {
      setSelfHealth(null);
    }
  }, [user?.role]);

  const selfHealthDegraded = useMemo(() => {
    const cpu = Number(selfHealth?.cpu?.percent || 0);
    const mem = Number(selfHealth?.memory?.used_percent || 0);
    const rootDisk = Array.isArray(selfHealth?.disks) ? selfHealth.disks.find((d) => d?.path === '/') : null;
    const disk = Number(rootDisk?.used_percent || 0);
    return cpu >= 80 || mem >= 80 || disk >= 85;
  }, [selfHealth]);
  const selfHealthPollIntervalMs = selfHealthDegraded ? 10000 : 30000;

  useVisiblePolling(
    async () => {
      if (!isOperator()) return;
      try {
        const res = await OpsService.getSelfHealth();
        setSelfHealth(res?.data?.data || res?.data || null);
      } catch (e) {
        setSelfHealth(null);
      }
    },
    selfHealthPollIntervalMs,
    {
      enabled: isOperator(),
      immediate: true,
      runOnVisible: true,
      minGapMs: selfHealthDegraded ? 4000 : 12000,
      backoffOnError: false,
      backoffMultiplier: 2,
      backoffMaxIntervalMs: 90000,
    },
  );

  const dashboardIssues = useMemo(() => {
    const rows = Array.isArray(stats?.issues) ? [...stats.issues] : [];
    rows.sort(compareServiceImpactAlerts);
    return rows;
  }, [stats?.issues]);
  const serviceImpactHotspots = useMemo(
    () => dashboardIssues
      .filter((issue) => Number(issue?.service_impact_summary?.count || 0) > 0)
      .map((issue) => {
        const focus = summarizeServiceImpactAlertFocus(issue, t);
        return {
          issueId: Number(issue?.id || 0),
          issueTitle: String(issue?.title || '').trim() || t('dashboard_priority_alerts', 'Priority Alerts'),
          issueDevice: String(issue?.device || '').trim() || '-',
          siteId: Number(issue?.site_id || 0) || null,
          siteName: String(issue?.site_name || '').trim() || null,
          primaryGroupId: focus?.groupId || null,
          primaryName: focus?.groupName || t('dashboard_service_impact_unknown_group', 'Mapped service group'),
          primaryHealthStatus: focus?.healthStatus || 'review',
          primaryHealthScore: Number(focus?.healthScore || 0),
          groupCount: Number(issue?.service_impact_summary?.count || 0),
          matchedMemberCount: Number(focus?.matchedAssets || 0),
          reviewGroupCount: Number(focus?.reviewGroups || 0),
          criticalGroupCount: Number(focus?.criticalGroups || 0),
        };
      })
      .slice(0, 4),
    [dashboardIssues],
  );
  const serviceImpactIssueCount = serviceImpactHotspots.length;
  const serviceImpactGroupCount = useMemo(() => {
    const names = new Set(
      serviceImpactHotspots
        .map((row) => String(row.primaryName || '').trim())
        .filter(Boolean),
    );
    return names.size;
  }, [serviceImpactHotspots]);
  const serviceImpactReviewHotspots = useMemo(
    () => serviceImpactHotspots.filter((row) => Number(row.reviewGroupCount || 0) > 0).length,
    [serviceImpactHotspots],
  );
  const serviceImpactCriticalHotspots = useMemo(
    () => serviceImpactHotspots.filter(
      (row) => row.primaryHealthStatus === 'critical' || Number(row.criticalGroupCount || 0) > 0,
    ).length,
    [serviceImpactHotspots],
  );
  const servicePriorityBoard = useMemo(() => {
    const priorityGroups = Array.isArray(serviceReviewQueue) ? serviceReviewQueue.slice(0, 3) : [];
    const posture = summarizeServiceReviewPosture(serviceReviewQueue);
    const totalGroups = Number(stats?.service_groups?.total || posture.totalGroups || 0);
    const averageHealthScore = Number(stats?.service_groups?.average_health_score || 0);
    const averageHealth = totalGroups > 0
      ? Math.round(averageHealthScore || getServiceReviewAverageHealth(posture))
      : 0;
    return {
      priorityGroups,
      discoveredOnlyPressure: Number(stats?.service_groups?.discovered_only_pressure || posture.discoveredOnlyPressure || 0),
      activeIssues: Number(stats?.service_groups?.active_issues || posture.activeIssues || 0),
      criticalServices: Number(stats?.service_groups?.critical || posture.criticalGroups || 0),
      reviewServices: Number(stats?.service_groups?.review || posture.reviewGroups || 0),
      averageHealth,
      totalGroups,
      pressureIndex: getServicePressureIndex({
        criticalGroups: Number(stats?.service_groups?.critical || posture.criticalGroups || 0),
        reviewGroups: Number(stats?.service_groups?.review || posture.reviewGroups || 0),
        discoveredOnlyPressure: Number(stats?.service_groups?.discovered_only_pressure || posture.discoveredOnlyPressure || 0),
        activeIssues: Number(stats?.service_groups?.active_issues || posture.activeIssues || 0),
        totalGroups,
      }),
    };
  }, [serviceReviewQueue, stats]);

  if (loading || !stats || !analytics) {
    return (
      <div className="flex h-full items-center justify-center bg-transparent">
        <InlineLoading label={t('dashboard_initializing', 'Initializing Dashboard...')} className="font-mono" />
      </div>
    );
  }

  const healthScore = stats.health_score || 0;
  const healthColor = healthScore >= 90 ? '#10b981' : healthScore >= 70 ? '#f59e0b' : '#ef4444';
  const serviceGroupSummary = stats.service_groups || {};
  const serviceGroupTotal = Number(serviceGroupSummary.total || 0);
  const serviceGroupReview = Number(serviceGroupSummary.review || 0);
  const serviceGroupCritical = Number(serviceGroupSummary.critical || 0);
  const serviceGroupAverageHealth = Number(serviceGroupSummary.average_health_score || 0);
  const dashboardPriorityServiceGroup = servicePriorityBoard.priorityGroups[0] || null;
  const dashboardPriorityWorkspace = recommendServiceWorkspace(dashboardPriorityServiceGroup);
  const dashboardPriorityWorkspaceLabel = getWorkspaceTitle(dashboardPriorityWorkspace.workspace, t);
  const openDashboardPrioritySurface = () => {
    if (dashboardPriorityWorkspace.workspace === 'discover') {
      navigate('/discovery');
      return;
    }
    if (dashboardPriorityWorkspace.workspace === 'govern') {
      if (dashboardPriorityServiceGroup?.id) {
        openFocusedServiceReview(dashboardPriorityServiceGroup.id, dashboardPriorityServiceGroup.name);
        return;
      }
      openServiceGroups();
      return;
    }
    openNotificationsWithServiceImpact(
      undefined,
      dashboardPriorityServiceGroup?.id,
      dashboardPriorityServiceGroup?.name,
    );
  };
  const stateHistorySummary = stats.state_history || {};
  const stateHistorySnapshotCount = Number(stateHistorySummary.snapshot_count || 0);
  const stateHistoryLatest = stateHistorySummary.latest_snapshot || {};
  const stateHistoryCompare = stateHistorySummary.latest_compare || {};
  const stateHistoryReviewCards = Number(stateHistoryCompare.review_cards || 0);
  const stateHistoryLatestAgeHours = stateHistoryLatest.age_hours;

  const formatBytes = (bytes) => {
    if (bytes === null || bytes === undefined) return '-';
    const n = Number(bytes);
    if (!Number.isFinite(n)) return '-';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let v = n;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i += 1;
    }
    return `${v.toFixed(i === 0 ? 0 : 1)}${units[i]}`;
  };

  const clampPct = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return null;
    return Math.max(0, Math.min(100, n));
  };

  const uptimeLabel = (seconds) => {
    const s = Number(seconds);
    if (!Number.isFinite(s) || s < 0) return '-';
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  };

  const formatMs = (value) => {
    if (value === null || value === undefined) return '-';
    const n = Number(value);
    if (!Number.isFinite(n)) return '-';
    if (n >= 1000) return `${(n / 1000).toFixed(2)}s`;
    return `${Math.round(n)}ms`;
  };

  const formatSeconds = (value) => {
    if (value === null || value === undefined) return '-';
    const n = Number(value);
    if (!Number.isFinite(n)) return '-';
    if (n >= 3600) return `${(n / 3600).toFixed(2)}h`;
    if (n >= 60) return `${(n / 60).toFixed(2)}m`;
    return `${n.toFixed(1)}s`;
  };
  const formatExecutionIdShort = (value) => {
    const raw = String(value || '').trim();
    if (!raw) return 'missing';
    if (raw.length <= 18) return raw;
    return `${raw.slice(0, 8)}...${raw.slice(-6)}`;
  };

  const controllerCpuPct = clampPct(selfHealth?.cpu?.percent);
  const controllerMemPct = clampPct(selfHealth?.memory?.used_percent);
  const rootDisk = Array.isArray(selfHealth?.disks) ? selfHealth.disks.find(d => d?.path === '/') : null;
  const controllerDiskPct = clampPct(rootDisk?.used_percent);
  const changeKpi = stats.change_kpi || {};
  const changeTotals = changeKpi.totals || {};
  const changeFailureRows = Array.isArray(changeKpi.failure_causes) ? changeKpi.failure_causes : [];
  const changeFailureTop = changeFailureRows.slice(0, 3);
  const changeFailureCounts = changeFailureRows.reduce((acc, row) => {
    const key = normalizeStatusToken(row?.cause);
    if (!key) return acc;
    acc[key] = Number(acc[key] || 0) + Number(row?.count || 0);
    return acc;
  }, {});
  const precheckFailureCount = Number(changeFailureCounts.precheck_failed || 0) + Number(changeFailureCounts.pre_check_failed || 0);
  const postcheckFailureCount = Number(changeFailureCounts.postcheck_failed || 0) + Number(changeFailureCounts.post_check_failed || 0);
  const changeTargets = changeKpi.targets || {};
  const changeMinSuccessTarget = Number(changeTargets.min_success_rate_pct ?? 98);
  const changeMaxFailureTarget = Number(changeTargets.max_failure_rate_pct ?? 1);
  const changeMaxRollbackP95Target = Number(changeTargets.max_rollback_p95_ms ?? 180000);
  const changeMinTraceTarget = Number(changeTargets.min_trace_coverage_pct ?? 100);
  const changeSuccessRateFallback = Number(changeTotals.events || 0) > 0
    ? (Number(changeTotals.success || 0) / Number(changeTotals.events || 1)) * 100
    : 100;
  const changeFailureRateFallback = Number(changeTotals.events || 0) > 0
    ? (Number(changeTotals.failed || 0) / Number(changeTotals.events || 1)) * 100
    : 0;
  const changeSuccessRate = Number(changeKpi.change_success_rate_pct ?? changeSuccessRateFallback);
  const changeFailureRate = Number(changeKpi.change_failure_rate_pct ?? changeFailureRateFallback);
  const rollbackP95 = changeKpi.rollback_p95_ms;
  const traceCoverage = Number(changeKpi.approval_execution_trace_coverage_pct || 0);
  const traceContextEvents = Number(changeTotals.approval_context_events || 0);
  const traceLinkedEvents = Number(changeTotals.approval_traced || 0);
  const changeTraceRows = Array.isArray(changeTraces) ? changeTraces.slice(0, 3) : [];
  const closedLoopKpi = stats.closed_loop_kpi || {};
  const closedLoopTotals = closedLoopKpi.totals || {};
  const closedLoopCycles = Number(closedLoopTotals.cycles || 0);
  const closedLoopTriggered = Number(closedLoopTotals.triggered || 0);
  const closedLoopExecuted = Number(closedLoopTotals.executed || 0);
  const closedLoopBlocked = Number(closedLoopTotals.blocked || 0);
  const closedLoopApprovals = Number(closedLoopTotals.approvals_opened || 0);
  const closedLoopExecutePct = Number(closedLoopKpi.execute_per_trigger_pct || 0);
  const closedLoopBlockedPct = Number(closedLoopKpi.blocked_per_trigger_pct || 0);
  const closedLoopApprovalPct = Number(closedLoopKpi.approvals_per_execution_pct || 0);
  const closedLoopAvgTriggered = Number(closedLoopKpi.avg_triggered_per_cycle || 0);
  const closedLoopAvgExecuted = Number(closedLoopKpi.avg_executed_per_cycle || 0);
  const closedLoopStatus = String(closedLoopKpi.status || (closedLoopKpi.engine_enabled ? 'healthy' : 'disabled')).toLowerCase();
  const closedLoopAlerts = Array.isArray(closedLoopKpi.alerts) ? closedLoopKpi.alerts : [];
  const closedLoopTopAlerts = closedLoopAlerts.slice(0, 3);
  const closedLoopStatusClass =
    closedLoopStatus === 'critical'
      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
      : closedLoopStatus === 'warning'
        ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
        : closedLoopStatus === 'healthy'
          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
          : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
  const northboundKpi = stats.northbound_kpi || {};
  const northboundTotals = northboundKpi.totals || {};
  const northboundModes = Array.isArray(northboundKpi.modes) ? northboundKpi.modes.slice(0, 3) : [];
  const northboundFailures = Array.isArray(northboundKpi.failure_causes) ? northboundKpi.failure_causes.slice(0, 3) : [];
  const northboundSuccessRate = Number(northboundKpi.success_rate_pct || 0);
  const northboundAvgAttempts = Number(northboundKpi.avg_attempts || 0);
  const northboundP95Attempts = Number(northboundKpi.p95_attempts || 0);
  const northboundStatus = String(northboundKpi.status || 'idle').toLowerCase();
  const northboundStatusClass =
    northboundStatus === 'critical'
      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
      : northboundStatus === 'warning'
        ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
        : northboundStatus === 'healthy'
          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
          : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
  const autonomyKpi = stats.autonomy_kpi || {};
  const autonomyTotals = autonomyKpi.totals || {};
  const autonomyMttd = autonomyKpi.mttd_seconds;
  const autonomyMttdP95 = autonomyKpi.mttd_p95_seconds;
  const autonomyMttr = autonomyKpi.mttr_seconds;
  const autonomyMttrP95 = autonomyKpi.mttr_p95_seconds;
  const autonomyAutoRate = Number(autonomyKpi.auto_action_rate_pct || 0);
  const autonomyOperatorRate = Number(autonomyKpi.operator_intervention_rate_pct || 0);
  const autonomyMttdCoverage = Number(autonomyKpi.mttd_signal_coverage_pct || 0);
  const autonomyMttrCoverage = Number(autonomyKpi.mttr_coverage_pct || 0);
  const autonomyTargets = autonomyKpi.targets || {};
  const autonomyMinAutoRateTarget = Number(autonomyTargets.min_auto_action_rate_pct ?? 60);
  const autonomyMaxOperatorRateTarget = Number(autonomyTargets.max_operator_intervention_rate_pct ?? 40);
  const autonomyTrend7d = Array.isArray(autonomyKpi.trend_7d) ? autonomyKpi.trend_7d.slice(-7) : [];
  const autonomyTrendMaxExecuted = autonomyTrend7d.reduce((max, row) => {
    const v = Number(row?.actions_executed || 0);
    return Number.isFinite(v) ? Math.max(max, v) : max;
  }, 1);
  const autonomyStatus = String(autonomyKpi.status || 'idle').toLowerCase();
  const autonomyStatusClass =
    autonomyStatus === 'critical'
      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
      : autonomyStatus === 'warning'
        ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
        : autonomyStatus === 'healthy'
          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
          : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
  const readinessData = readinessHistory || {};
  const readinessTotals = readinessData.totals || {};
  const readinessByStatus = readinessTotals.by_status || {};
  const readinessLatest = readinessData.latest || null;
  const readinessLatestSummary = readinessLatest?.readiness || {};
  const readinessStatus = String(readinessLatestSummary.status || 'insufficient_data').toLowerCase();
  const readinessPassCount = Number(readinessLatestSummary.pass_count || 0);
  const readinessFailCount = Number(readinessLatestSummary.fail_count || 0);
  const readinessUnknownCount = Number(readinessLatestSummary.unknown_count || 0);
  const readinessRequiredChecks = Number(readinessLatestSummary.required_checks_total || 0);
  const readinessCoverage = readinessData.coverage || {};
  const readinessComparison = readinessData.comparison || {};
  const readinessCurrentStreak = readinessData.current_streak || {};
  const readinessTopFailingChecks = Array.isArray(readinessData.top_failing_checks) ? readinessData.top_failing_checks.slice(0, 3) : [];
  const readinessLatestSampleCoverage = readinessData.sample_coverage_latest || readinessLatest?.evidence?.sample_coverage || {};
  const readinessTrend = Array.isArray(readinessData.trend_by_day) ? readinessData.trend_by_day.slice(-7) : [];
  const readinessTrendMaxTotal = readinessTrend.reduce((max, row) => {
    const total = Number(row?.total || 0);
    return Number.isFinite(total) ? Math.max(max, total) : max;
  }, 1);
  const readinessCoveragePct = Number(readinessCoverage.coverage_pct || 0);
  const readinessCoverageDays = Number(readinessCoverage.days_with_snapshots || 0);
  const readinessExpectedDays = Number(readinessCoverage.expected_days || 0);
  const readinessLatestAgeHours = readinessCoverage.latest_age_hours;
  const readinessStatusDirection = String(readinessComparison.status_direction || 'stable').toLowerCase();
  const readinessDirectionClass =
    readinessStatusDirection === 'regressed'
      ? 'text-red-500'
      : readinessStatusDirection === 'improved'
        ? 'text-emerald-500'
        : readinessStatusDirection === 'stable'
          ? 'text-cyan-500'
          : 'text-gray-500';
  const readinessSampleRatioBadges = [
    {
      key: 'discovery_jobs',
      label: 'D',
      value: readinessLatestSampleCoverage?.discovery_jobs?.coverage_pct,
    },
    {
      key: 'change_events',
      label: 'C',
      value: readinessLatestSampleCoverage?.change_events?.coverage_pct,
    },
    {
      key: 'northbound_deliveries',
      label: 'N',
      value: readinessLatestSampleCoverage?.northbound_deliveries?.coverage_pct,
    },
    {
      key: 'autonomy_actions_executed',
      label: 'A',
      value: readinessLatestSampleCoverage?.autonomy_actions_executed?.coverage_pct,
    },
  ];
  const readinessStatusClass =
    readinessStatus === 'critical'
      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
      : readinessStatus === 'warning'
        ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
        : readinessStatus === 'healthy'
          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
          : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
  const releaseData = releaseEvidence || {};
  const releaseSummary = releaseData.summary || {};
  const releaseSections = releaseData.sections || {};
  const releaseOverallStatus = String(releaseSummary.overall_status || 'unavailable').toLowerCase();
  const releaseOverallClass = statusBadgeClass(releaseOverallStatus);
  const releaseAcceptedGates = Number(releaseSummary.accepted_gates || 0);
  const releaseAvailableGates = Number(releaseSummary.available_gates || 0);
  const releaseTotalGates = Number(releaseSummary.total_gates || 0);
  const releaseBlockingGates = Array.isArray(releaseSummary.blocking_gates) ? releaseSummary.blocking_gates : [];
  const releaseInProgressGates = Array.isArray(releaseSummary.in_progress_gates) ? releaseSummary.in_progress_gates : [];
  const releaseRefresh = releaseData.refresh || {};
  const releaseRefreshStatus = normalizeStatusToken(releaseRefresh.status || 'idle');
  const releaseRefreshStage = normalizeStatusToken(releaseRefresh.stage || 'idle');
  const releaseRefreshClass =
    releaseRefreshStatus === 'failed'
      ? statusBadgeClass('critical')
      : releaseRefreshStatus === 'completed'
        ? statusBadgeClass('healthy')
        : releaseRefreshStatus === 'queued' || releaseRefreshStatus === 'running'
          ? statusBadgeClass('in_progress')
          : statusBadgeClass('unavailable');
  const releaseRefreshLastSummary = releaseRefresh.last_summary || {};
  const releaseAutomation = releaseData.automation || {};
  const releaseAutomationEnabled = !!releaseAutomation.enabled;
  const releaseAutomationProfile = normalizeStatusToken(releaseAutomation.profile || 'ci') || 'ci';
  const releaseAutomationIncludeSynthetic = !!releaseAutomation.include_synthetic;
  const releaseAutomationSchedule = releaseAutomation.schedule || {};
  const releaseAutomationNextRunAt = releaseAutomation.next_run_at || null;
  const releaseAutomationClass = releaseAutomationEnabled ? statusBadgeClass('healthy') : statusBadgeClass('unavailable');
  const releaseAutomationScheduleLabel =
    releaseAutomationSchedule.label
    || `${releaseAutomationSchedule.cadence || 'daily'} ${String(releaseAutomationSchedule.hour ?? '04').padStart(2, '0')}:${String(releaseAutomationSchedule.minute ?? '30').padStart(2, '0')} ${releaseAutomationSchedule.timezone || 'Asia/Seoul'}`;
  const releaseGateRows = [
    {
      key: 'kpi_readiness',
      label: t('dashboard_release_gate_kpi', '30d KPI'),
      section: releaseSections.kpi_readiness || {},
      detail: `${Number(releaseSections.kpi_readiness?.pass_count || 0)} / ${Number(releaseSections.kpi_readiness?.required_checks_total || 0)} pass`,
      subdetail:
        Number(releaseSections.kpi_readiness?.sample_coverage?.total || 0) > 0
          ? `${Number(releaseSections.kpi_readiness?.sample_coverage?.met_count || 0)} / ${Number(releaseSections.kpi_readiness?.sample_coverage?.total || 0)} samples`
          : null,
    },
    {
      key: 'vendor_support',
      label: t('dashboard_release_gate_vendor', 'Vendor Support'),
      section: releaseSections.vendor_support || {},
      detail: `${Number(releaseSections.vendor_support?.covered_device_types || 0)} / ${Number(releaseSections.vendor_support?.total_supported_device_types || 0)} covered`,
      subdetail: `full ${Number(releaseSections.vendor_support?.readiness?.full || 0)} / partial ${Number(releaseSections.vendor_support?.readiness?.partial || 0)}`,
    },
    {
      key: 'discovery_hinting',
      label: t('dashboard_release_gate_hinting', 'Discovery Hinting'),
      section: releaseSections.discovery_hinting || {},
      detail:
        releaseSections.discovery_hinting?.total_events > 0
          ? `${Number(releaseSections.discovery_hinting?.success_rate_pct || 0).toFixed(2)}% success`
          : t('dashboard_release_hint_runtime_only', 'Runtime summary only'),
      subdetail:
        releaseSections.discovery_hinting?.available
          ? `rules ${Number(releaseSections.discovery_hinting?.active_rules || 0)} / false positive ${Number(releaseSections.discovery_hinting?.false_positive_rate_pct || 0).toFixed(2)}%`
          : null,
    },
    {
      key: 'synthetic_validation',
      label: t('dashboard_release_gate_synthetic', 'Synthetic Matrix'),
      section: releaseSections.synthetic_validation || {},
      detail: `${Number(releaseSections.synthetic_validation?.scenario_count || 0)} scenarios / ${Number(releaseSections.synthetic_validation?.soak_runs || 0)} soak`,
      subdetail:
        Number(releaseSections.synthetic_validation?.total_processed_events || 0) > 0
          ? `${Number(releaseSections.synthetic_validation?.total_processed_events || 0)} events`
          : null,
    },
    {
      key: 'northbound_soak',
      label: t('dashboard_release_gate_northbound', 'Northbound Soak'),
      section: releaseSections.northbound_soak || {},
      detail:
        releaseSections.northbound_soak?.success_rate_pct === null || releaseSections.northbound_soak?.success_rate_pct === undefined
          ? `${Number(releaseSections.northbound_soak?.total_attempts || 0)} attempts`
          : `${Number(releaseSections.northbound_soak?.success_rate_pct || 0).toFixed(2)}% / ${Number(releaseSections.northbound_soak?.total_attempts || 0)}`,
      subdetail:
        Number(releaseSections.northbound_soak?.remaining_seconds || 0) > 0
          ? `${Math.round(Number(releaseSections.northbound_soak?.remaining_seconds || 0) / 3600)}h remaining`
          : null,
    },
  ];
  const panelClass = 'bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6 flex flex-col';
  const metricCardClass = `${panelClass} min-h-[350px]`;
  const previewEnabled = previewPolicy?.preview_enabled === true;
  const showProIssueGrafana = !previewEnabled;
  // Keep customer-facing dashboard focused on network operations.
  // Internal release/quality delivery widgets stay off the main dashboard by default.
  const showProOperations = false;
  const openExternal = (url) => {
    if (!url) return;
    window.open(url, '_blank', 'noopener,noreferrer');
  };
  const openIssueDevice = (deviceId) => {
    if (!deviceId) return;
    navigate(buildDevicePath(deviceId));
  };
  const openIssueTopology = (siteId) => {
    if (!siteId) return;
    navigate(buildTopologyPath({ siteId }));
  };
  const openIssueObservability = ({ deviceId, siteId } = {}) => {
    navigate(buildObservabilityPath({ deviceId, siteId }));
  };
  const openIssueGrafana = ({ deviceId, siteId } = {}) => {
    openExternal(buildGrafanaFleetHealthUrl({ deviceId, siteId }));
  };
  const openServiceGroups = (groupId, groupName) => {
    const numericGroupId = Number(groupId || 0);
    if (numericGroupId > 0) {
      const params = new URLSearchParams();
      params.set('focusGroupId', String(numericGroupId));
      if (String(groupName || '').trim()) {
        params.set('focusGroupName', String(groupName).trim());
      }
      navigate(`/service-groups?${params.toString()}`);
      return;
    }
    navigate('/service-groups');
  };
  const openFocusedServiceReview = (groupId, groupName) => {
    const numericGroupId = Number(groupId || 0);
    if (numericGroupId > 0) {
      const params = new URLSearchParams();
      params.set('focusGroupId', String(numericGroupId));
      if (String(groupName || '').trim()) {
        params.set('focusGroupName', String(groupName).trim());
      }
      navigate(`/operations-reports?${params.toString()}`);
      return;
    }
    navigate('/operations-reports');
  };
  const openFocusedServiceTopology = (groupId, groupName) => {
    const numericGroupId = Number(groupId || 0);
    if (numericGroupId > 0) {
      const params = new URLSearchParams();
      params.set('serviceGroupId', String(numericGroupId));
      params.set('serviceMap', '1');
      if (String(groupName || '').trim()) {
        params.set('focusGroupName', String(groupName).trim());
      }
      navigate(`/topology?${params.toString()}`);
      return;
    }
    navigate('/topology');
  };
  const openNotificationsWithServiceImpact = (issueId, groupId, groupName) => {
    const params = new URLSearchParams();
    params.set('serviceImpact', '1');
    if (Number(issueId || 0) > 0) {
      params.set('focusIssueId', String(Number(issueId)));
      params.set('openServiceImpact', '1');
    }
    if (Number(groupId || 0) > 0) {
      params.set('focusGroupId', String(Number(groupId)));
    }
    if (String(groupName || '').trim()) {
      params.set('focusGroupName', String(groupName).trim());
    }
    navigate(`/notifications?${params.toString()}`);
  };
  const mergeReleaseRefreshState = (refreshState) => {
    setReleaseEvidence((current) => ({
      ...(current || {}),
      summary: current?.summary || {},
      sections: current?.sections || {},
      refresh: refreshState || {},
    }));
  };
  const downloadReleaseBundle = async () => {
    if (releaseBundleDownloading) return;
    try {
      setReleaseBundleDownloading(true);
      const res = await OpsService.downloadReleaseEvidenceBundle();
      const filename = parseFilename(res?.headers?.['content-disposition']) || `release_evidence_bundle_${new Date().toISOString().replace(/[:.]/g, '-')}.zip`;
      downloadBlob(res?.data, filename, 'application/zip');
      toast.success(t('dashboard_release_bundle_downloaded', 'Release evidence bundle downloaded.'));
    } catch (err) {
      toast.error(err?.response?.data?.detail || err?.message || t('dashboard_release_bundle_download_failed', 'Failed to download release evidence bundle.'));
    } finally {
      setReleaseBundleDownloading(false);
    }
  };
  const startReleaseEvidenceRefresh = async () => {
    if (releaseRefreshStarting || releaseRefreshRunning) return;
    try {
      setReleaseRefreshStarting(true);
      const res = await OpsService.refreshReleaseEvidence({
        profile: releaseAutomationProfile || 'ci',
        include_synthetic: releaseAutomationIncludeSynthetic,
      });
      const payload = unwrapApiData(res);
      if (payload?.refresh) {
        mergeReleaseRefreshState(payload.refresh);
      }
      if (payload?.started) {
        toast.success(t('dashboard_release_refresh_started', 'Release evidence refresh started.'));
      } else {
        toast.info(t('dashboard_release_refresh_already_running', 'Release evidence refresh is already running.'));
      }
      await loadData(false);
    } catch (err) {
      toast.error(err?.response?.data?.detail || err?.message || t('dashboard_release_refresh_failed', 'Failed to start release evidence refresh.'));
    } finally {
      setReleaseRefreshStarting(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-w-0 gap-6 animate-fade-in text-gray-900 dark:text-white font-sans pb-6">

      {/* Header with Site Filter */}
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-end pb-4 border-b border-gray-200 dark:border-white/5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white/90">
              {t('dashboard_title', 'Network Assurance')}
            </h1>
          </div>
          <p className="text-xs text-gray-500 pl-4">{t('dashboard_subtitle', 'Real-time Infrastructure Health & Provisioning Status')}</p>
        </div>
        <div className="flex gap-3 items-center flex-wrap justify-end">
          {/* Site Filter */}
          <div className="relative group">
            <select
              value={selectedSite}
              onChange={(e) => setSelectedSite(e.target.value)}
              className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 pl-3 pr-8 focus:outline-none focus:border-primary/50 appearance-none cursor-pointer transition-all hover:bg-gray-50 dark:hover:bg-black/40 hover:border-gray-400 dark:hover:border-white/20"
            >
              <option value="">{t('dashboard_global_view', 'Global View')}</option>
              {sites.map(site => (
                <option key={site.id} value={site.id}>{site.name}</option>
              ))}
            </select>
            <MapPin size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none group-hover:text-primary transition-colors" />
          </div>

          <div className="px-3 py-1.5 bg-emerald-50 dark:bg-success/10 border border-emerald-200 dark:border-success/20 rounded-full text-xs font-bold text-emerald-600 dark:text-success flex items-center gap-2 shadow-sm dark:shadow-neon-success">
            <CheckCircle size={14} /> {t('dashboard_system_healthy', 'System Healthy')}
          </div>
          <button onClick={() => loadData(true)} className="p-2 bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors border border-transparent hover:border-gray-300 dark:hover:border-white/10">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* Global Health & Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 items-stretch">

        {/* Health Score Ring */}
        <div className={`${panelClass} items-center justify-center relative min-h-[350px]`}>
          {/* Gradient Glow */}
          <div className="absolute inset-0 bg-radial-gradient from-primary/5 to-transparent opacity-50 pointer-events-none"></div>

          <h3 className="absolute top-6 left-6 text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider flex items-center gap-2">
            <Activity size={16} className="text-blue-500 dark:text-primary" /> {t('dashboard_infra_health', 'Infrastructure Health')}
          </h3>
          <div className="w-full h-full max-h-[250px] mt-4 relative z-10">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={[{ value: healthScore }, { value: 100 - healthScore }]}
                  cx="50%" cy="50%"
                  innerRadius={75} outerRadius={95}
                  startAngle={90} endAngle={-270}
                  dataKey="value"
                  stroke="none"
                >
                  <Cell fill={healthColor} />
                  <Cell fill="rgba(255,255,255,0.05)" />
                </Pie>
              </PieChart>
            </ResponsiveContainer>

            {/* Center Text */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none mt-4">
              <span className="text-6xl font-black tracking-tighter drop-shadow-lg" style={{ color: healthColor }}>{healthScore}%</span>
              <span className="text-xs text-gray-500 mt-2 font-mono tracking-widest uppercase">{t('dashboard_score', 'Score')}</span>
            </div>
          </div>
        </div>

        {/* Inventory Status Grid */}
        <div className={panelClass}>
          <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-6 flex items-center gap-2">
            <Server size={16} className="text-blue-500 dark:text-primary" /> {t('dashboard_inventory_overview', 'Inventory Overview')}
          </h3>
          <div
            className="mb-5 rounded-2xl border border-violet-200/70 bg-violet-50/70 p-4 dark:border-violet-900/40 dark:bg-violet-950/10"
            data-testid="dashboard-service-priority-summary"
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-[10px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
                    {t('dashboard_service_priority_summary_title', 'Service operating priority')}
                  </div>
                  <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-bold ${pressureBadgeClass(servicePriorityBoard.pressureIndex)}`}>
                    {getOperationsPressureLabel(servicePriorityBoard.pressureIndex, t)}
                  </span>
                </div>
                <div className="mt-2 text-sm text-gray-700 dark:text-gray-200">
                  {dashboardPriorityServiceGroup?.name
                    ? t(
                      'dashboard_service_priority_summary_group_fmt',
                      '{group} is the current lead service review target.',
                    ).replace('{group}', dashboardPriorityServiceGroup.name)
                    : t(
                      'dashboard_service_priority_summary_default',
                      'Service posture is the leading operator signal right now.',
                    )}
                </div>
                <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
                  {getOperationsPressureGuidance(servicePriorityBoard.pressureIndex, t)}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  data-testid="dashboard-service-priority-summary-open-primary"
                  onClick={openDashboardPrioritySurface}
                  className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-[11px] font-semibold text-violet-700 transition-colors hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200 dark:hover:bg-violet-950/30"
                >
                  {dashboardPriorityWorkspace.workspace === 'discover'
                    ? t('ops_home_pressure_open_discovery', 'Open Discovery')
                    : dashboardPriorityWorkspace.workspace === 'govern'
                      ? t('dashboard_service_impact_open_review', 'Open service review')
                      : t('dashboard_service_impact_open_notifications', 'Open service-aware alerts')}
                </button>
                <button
                  type="button"
                  data-testid="dashboard-service-priority-summary-open-queue"
                  onClick={() => openNotificationsWithServiceImpact(undefined, dashboardPriorityServiceGroup?.id, dashboardPriorityServiceGroup?.name)}
                  className="rounded-full border border-gray-200 px-3 py-1 text-[11px] font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/10"
                >
                  {t('dashboard_service_priority_open_queue', 'Open service operations queue')}
                </button>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 flex-1 content-start">
            <StatusBox label={t('dashboard_sites', 'Sites')} value={stats.counts?.sites || 0} icon={MapPin} color="text-primary" />
            <StatusBox label={t('dashboard_nodes', 'Nodes')} value={stats.counts?.devices || 0} icon={Server} color="text-purple-400" />

            <StatusBox
              label={t('dashboard_active_aps', 'Active APs')}
              value={stats.counts?.wireless_aps || 0}
              icon={Wifi}
              color="text-emerald-400"
            />
            <StatusBox
              label={t('dashboard_clients', 'Clients')}
              value={stats.counts?.wireless_clients || 0}
              icon={Users}
              color="text-pink-400"
            />

            <StatusBox
              label={t('dashboard_nodes_reached', 'Nodes Reached')}
              value={(stats.counts?.online || 0)}
              icon={Activity}
              color="text-green-400"
            />

            <StatusBox
              label={t('dashboard_issues_found', 'Issues Found')}
              value={(stats.counts?.offline || 0) + (stats.counts?.alert || 0)}
              icon={AlertOctagon}
              color="text-red-500"
              alert={(stats.counts?.offline > 0) || (stats.counts?.alert > 0)}
            />
            <StatusBox
              label={t('dashboard_service_groups', 'Service Groups')}
              value={serviceGroupTotal}
              icon={LayoutGrid}
              color="text-sky-400"
            />
            <StatusBox
              label={t('dashboard_service_review', 'Services Need Review')}
              value={serviceGroupReview}
              icon={ShieldCheck}
              color="text-amber-400"
              alert={serviceGroupReview > 0}
            />
          </div>

          <div className="mt-8 pt-6 border-t border-white/10">
            <div className="flex justify-between items-center mb-2">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_config_compliance', 'Config Compliance')}</div>
              <div className="text-xs font-bold text-blue-600 dark:text-blue-300 font-mono">{stats.counts?.compliant || 0}/{stats.counts?.devices || 0} {t('dashboard_synced', 'Synced')}</div>
            </div>
            <div className="w-full bg-gray-200 dark:bg-black/40 h-1.5 rounded-full overflow-hidden border border-gray-200 dark:border-white/5">
              <div
                className="bg-primary h-full rounded-full transition-all duration-1000 shadow-[0_0_10px_#3b82f6]"
                style={{ width: `${stats.counts?.devices ? (stats.counts?.compliant / stats.counts?.devices) * 100 : 0}%` }}
              ></div>
            </div>
          </div>

          <div className="mt-5 pt-5 border-t border-white/10">
            <div className="flex justify-between items-center mb-2">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_service_health', 'Service Health')}</div>
              <div className="text-xs font-bold text-cyan-600 dark:text-cyan-300 font-mono">
                {serviceGroupAverageHealth}/100 | {t('dashboard_service_review_hint', '{value} critical').replace('{value}', String(serviceGroupCritical))}
              </div>
            </div>
            <div className="w-full bg-gray-200 dark:bg-black/40 h-1.5 rounded-full overflow-hidden border border-gray-200 dark:border-white/5">
              <div
                className="bg-cyan-500 h-full rounded-full transition-all duration-1000 shadow-[0_0_10px_#06b6d4]"
                style={{ width: `${Math.max(0, Math.min(100, serviceGroupAverageHealth))}%` }}
              ></div>
            </div>
            <div
              className="mt-3 rounded-xl border border-cyan-200/70 bg-cyan-50/70 p-3 dark:border-cyan-900/40 dark:bg-cyan-950/10"
              data-testid="dashboard-service-health-next-action"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-300">
                    {t('dashboard_service_health_next_action', 'Recommended next action')}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-bold ${pressureBadgeClass(servicePriorityBoard.pressureIndex)}`}>
                      {getOperationsPressureLabel(servicePriorityBoard.pressureIndex, t)}
                    </span>
                    <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                      {dashboardPriorityWorkspaceLabel}
                    </span>
                    {dashboardPriorityServiceGroup?.name ? (
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {dashboardPriorityServiceGroup.name}
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">
                    {getOperationsPressureGuidance(servicePriorityBoard.pressureIndex, t)}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    data-testid="dashboard-service-health-open-primary"
                    onClick={openDashboardPrioritySurface}
                    className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-semibold text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
                  >
                    {dashboardPriorityWorkspace.workspace === 'discover'
                      ? t('ops_home_pressure_open_discovery', 'Open Discovery')
                      : dashboardPriorityWorkspace.workspace === 'govern'
                        ? t('dashboard_service_impact_open_review', 'Open service review')
                        : t('dashboard_service_impact_open_notifications', 'Open service-aware alerts')}
                  </button>
                  <button
                    type="button"
                    data-testid="dashboard-service-health-open-queue"
                    onClick={() => openNotificationsWithServiceImpact(undefined, dashboardPriorityServiceGroup?.id, dashboardPriorityServiceGroup?.name)}
                    className="rounded-full border border-gray-200 px-3 py-1 text-[11px] font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/10"
                  >
                    {t('dashboard_service_priority_open_queue', 'Open service operations queue')}
                  </button>
                </div>
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3 text-[11px] text-gray-500 dark:text-gray-400">
              <div className="uppercase tracking-[0.14em] font-bold">{t('dashboard_state_history', 'State History')}</div>
              <div className="text-right font-mono">
                {t('dashboard_state_history_summary', '{count} snapshots | {result}')
                  .replace('{count}', String(stateHistorySnapshotCount))
                  .replace('{result}', String(stateHistoryCompare?.result || 'steady').toUpperCase())}
              </div>
            </div>
            <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
              {t('dashboard_state_history_hint', '{value} review cards | latest {age}h ago')
                .replace('{value}', String(stateHistoryReviewCards))
                .replace('{age}', stateHistoryLatestAgeHours == null ? '-' : Number(stateHistoryLatestAgeHours).toFixed(1))}
            </div>
          </div>
        </div>

        <div className={`${metricCardClass}`} data-testid="dashboard-service-priority-board">
          <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider flex items-center gap-2">
                <ShieldCheck size={16} className="text-violet-500" /> {t('dashboard_service_priority_board', 'Service Priority Board')}
              </h3>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                {t('dashboard_service_priority_board_desc', 'Start the day with the service groups that need the fastest operator review, then jump directly into alerts, reports, or topology.')}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="dashboard-service-priority-open-queue"
                onClick={() => openNotificationsWithServiceImpact()}
                className="inline-flex items-center gap-2 rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1.5 text-[11px] font-semibold text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
              >
                {t('dashboard_service_priority_open_queue', 'Open service operations queue')}
              </button>
              <button
                type="button"
                data-testid="dashboard-service-priority-open-groups"
                onClick={() => openServiceGroups()}
                className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 text-[11px] font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/10"
              >
                {t('dashboard_service_priority_open_groups', 'Open Service Groups')}
              </button>
            </div>
          </div>
          <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4" data-testid="dashboard-service-posture">
            <div className="rounded-xl border border-rose-200/70 bg-rose-50/70 p-3 dark:border-rose-900/40 dark:bg-rose-950/10">
              <div className="text-[10px] font-black uppercase tracking-widest text-rose-700 dark:text-rose-300">
                {t('dashboard_service_priority_critical', 'Critical services')}
              </div>
              <div className="mt-1 text-2xl font-black text-rose-700 dark:text-rose-200">{servicePriorityBoard.criticalServices}</div>
            </div>
            <div className="rounded-xl border border-amber-200/70 bg-amber-50/70 p-3 dark:border-amber-900/40 dark:bg-amber-950/10">
              <div className="text-[10px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
                {t('dashboard_service_priority_review', 'Needs review')}
              </div>
              <div className="mt-1 text-2xl font-black text-amber-700 dark:text-amber-200">{servicePriorityBoard.reviewServices}</div>
            </div>
            <div className="rounded-xl border border-cyan-200/70 bg-cyan-50/70 p-3 dark:border-cyan-900/40 dark:bg-cyan-950/10">
              <div className="text-[10px] font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-300">
                {t('dashboard_service_priority_discovered_only', 'Discovered-only pressure')}
              </div>
              <div className="mt-1 text-2xl font-black text-cyan-700 dark:text-cyan-200">{servicePriorityBoard.discoveredOnlyPressure}</div>
            </div>
            <div className="rounded-xl border border-indigo-200/70 bg-indigo-50/70 p-3 dark:border-indigo-900/40 dark:bg-indigo-950/10">
              <div className="text-[10px] font-black uppercase tracking-widest text-indigo-700 dark:text-indigo-300">
                {t('operations_reports_metric_service_issues', 'Service-Scoped Issues')}
              </div>
              <div className="mt-1 text-2xl font-black text-indigo-700 dark:text-indigo-200">{servicePriorityBoard.activeIssues}</div>
            </div>
          </div>
          <div className="mb-4 rounded-2xl border border-sky-200/70 bg-sky-50/70 p-4 dark:border-sky-900/40 dark:bg-sky-950/10">
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
              <div className="rounded-xl border border-sky-200/70 bg-white/80 p-3 dark:border-sky-900/40 dark:bg-[#10151d]">
                <div className="text-[10px] font-black uppercase tracking-widest text-sky-700 dark:text-sky-300">
                  {t('service_operating_posture_average_health', 'Average health')}
                </div>
                <div className="mt-1 text-2xl font-black text-sky-700 dark:text-sky-200">{servicePriorityBoard.averageHealth}</div>
              </div>
              <div className="rounded-xl border border-indigo-200/70 bg-white/80 p-3 dark:border-indigo-900/40 dark:bg-[#10151d]">
                <div className="text-[10px] font-black uppercase tracking-widest text-indigo-700 dark:text-indigo-300">
                  {t('service_operating_posture_groups_in_scope', 'Groups in scope')}
                </div>
                <div className="mt-1 text-2xl font-black text-indigo-700 dark:text-indigo-200">{servicePriorityBoard.totalGroups}</div>
              </div>
                <div className="rounded-xl border border-fuchsia-200/70 bg-white/80 p-3 dark:border-fuchsia-900/40 dark:bg-[#10151d]">
                  <div className="text-[10px] font-black uppercase tracking-widest text-fuchsia-700 dark:text-fuchsia-300">
                    {t('service_operating_posture_pressure_index', 'Pressure index')}
                  </div>
                  <div className="mt-1 text-2xl font-black text-fuchsia-700 dark:text-fuchsia-200">{servicePriorityBoard.pressureIndex}</div>
                  <div className="mt-2">
                    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-bold ${pressureBadgeClass(servicePriorityBoard.pressureIndex)}`}>
                      {getOperationsPressureLabel(servicePriorityBoard.pressureIndex, t)}
                    </span>
                  </div>
                  <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
                    {getOperationsPressureGuidance(servicePriorityBoard.pressureIndex, t)}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="space-y-3">
            {servicePriorityBoard.priorityGroups.length > 0 ? (
              servicePriorityBoard.priorityGroups.map((group) => (
                <div
                  key={`dashboard-service-priority-${group.id}`}
                  data-testid={`dashboard-service-priority-card-${group.id}`}
                  className="rounded-xl border border-violet-200/70 bg-white/90 p-3 shadow-sm dark:border-violet-900/40 dark:bg-black/20 dark:shadow-none"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${serviceHealthTone(group.healthStatus)}`}>
                          {t('service_groups_health_score', 'Health Score')}: {group.healthScore}
                        </span>
                        <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">{group.name}</span>
                      </div>
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {group.description || t('ops_home_service_review_no_description', 'Review this service group through topology, reports, and alerts.')}
                      </div>
                    </div>
                    <div className="text-right text-[11px] text-gray-500 dark:text-gray-400">
                      <div>{t('service_groups_health_active_issues', 'Active issues')}: {group.activeIssueCount}</div>
                      <div>{t('service_groups_health_offline_devices', 'Offline devices')}: {group.offlineDeviceCount}</div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      data-testid={`dashboard-service-priority-open-review-${group.id}`}
                      onClick={() => openFocusedServiceReview(group.id, group.name)}
                      className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-[11px] font-semibold text-violet-700 transition-colors hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200 dark:hover:bg-violet-950/30"
                    >
                      {t('service_groups_review_open', 'Open Review')}
                    </button>
                    <button
                      type="button"
                      data-testid={`dashboard-service-priority-open-notifications-${group.id}`}
                      onClick={() => openNotificationsWithServiceImpact(undefined, group.id, group.name)}
                      className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-semibold text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
                    >
                      {t('service_groups_review_open_notifications', 'Open service-aware alerts')}
                    </button>
                    <button
                      type="button"
                      data-testid={`dashboard-service-priority-open-topology-${group.id}`}
                      onClick={() => openFocusedServiceTopology(group.id, group.name)}
                      className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-200 dark:hover:bg-emerald-950/30"
                    >
                      {t('dashboard_service_impact_open_topology', 'Open Topology')}
                    </button>
                  </div>
                  <div className="mt-3 text-xs text-gray-600 dark:text-gray-300">
                    {group.nextAction}
                  </div>
                </div>
              ))
            ) : (
              <div className="flex h-full flex-col items-center justify-center text-center text-gray-600 italic dark:text-gray-400">
                <ShieldCheck size={28} className="mb-3 text-violet-300 dark:text-violet-700" />
                <p className="text-sm">{t('dashboard_service_priority_empty', 'No service groups are waiting in the immediate review queue.')}</p>
              </div>
            )}
          </div>
        </div>

        {/* Service Impact Watch */}
        <div className={`${metricCardClass}`}>
          <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <LayoutGrid size={16} className="text-cyan-500" /> {t('dashboard_service_impact_watch', 'Service Impact Watch')}
          </h3>
          <div className="mb-4 grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-cyan-200/70 bg-cyan-50/70 p-3 dark:border-cyan-900/40 dark:bg-cyan-950/10">
              <div className="text-[10px] font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-300">
                {t('dashboard_service_impact_issue_count', 'Impacted alerts')}
              </div>
              <div className="mt-1 text-2xl font-black text-cyan-700 dark:text-cyan-200">{serviceImpactIssueCount}</div>
            </div>
            <div className="rounded-xl border border-amber-200/70 bg-amber-50/70 p-3 dark:border-amber-900/40 dark:bg-amber-950/10">
              <div className="text-[10px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
                {t('dashboard_service_impact_groups', 'Mapped services')}
              </div>
              <div className="mt-1 text-2xl font-black text-amber-700 dark:text-amber-200">{serviceImpactGroupCount}</div>
            </div>
          </div>

          <div className="mb-4 flex flex-wrap items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
            <span className="rounded-full border border-gray-200 px-2.5 py-1 dark:border-white/10">
              {t('dashboard_service_impact_review_groups_fmt', 'Needs review {value}').replace('{value}', String(serviceImpactReviewHotspots))}
            </span>
            <span className="rounded-full border border-gray-200 px-2.5 py-1 dark:border-white/10">
              {t('dashboard_service_impact_critical_groups_fmt', 'Critical groups {value}').replace('{value}', String(serviceImpactCriticalHotspots))}
            </span>
            <button
              type="button"
              data-testid="dashboard-service-impact-open-notifications"
              onClick={() => openNotificationsWithServiceImpact()}
              className="inline-flex items-center gap-2 rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-semibold text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
            >
              {t('dashboard_service_impact_open_notifications', 'Open service-aware alerts')}
            </button>
            <button
              type="button"
              data-testid="dashboard-service-impact-open-service-groups"
              onClick={() => openServiceGroups()}
              className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1 text-[11px] font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/10"
            >
              {t('dashboard_service_impact_open_groups', 'Open Service Groups')}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto custom-scrollbar space-y-3 pr-2 -mr-2" data-testid="dashboard-service-impact-panel">
            {serviceImpactHotspots.length > 0 ? (
              serviceImpactHotspots.map((row) => (
                <div
                  key={`service-impact-${row.issueId}`}
                  data-testid={`dashboard-service-impact-card-${row.issueId}`}
                  className="rounded-xl border border-cyan-200/70 bg-white/90 p-3 shadow-sm dark:border-cyan-900/40 dark:bg-black/20 dark:shadow-none"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusBadgeClass(row.primaryHealthStatus)}`}>
                          {t('service_groups_health_score', 'Health Score')}: {row.primaryHealthScore}
                        </span>
                        <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">{row.primaryName}</span>
                      </div>
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {row.issueTitle}
                        {row.siteName ? ` · ${row.siteName}` : ''}
                      </div>
                    </div>
                    <div className="text-right text-[11px] text-gray-500 dark:text-gray-400">
                      <div>{t('dashboard_service_impact_group_count_fmt', 'Groups {value}').replace('{value}', String(row.groupCount))}</div>
                      <div>{t('dashboard_service_impact_assets_fmt', 'Matched assets {value}').replace('{value}', String(row.matchedMemberCount))}</div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                    <span>{t('dashboard_service_impact_review_groups_fmt', 'Needs review {value}').replace('{value}', String(row.reviewGroupCount))}</span>
                    <span>{t('dashboard_service_impact_critical_groups_fmt', 'Critical groups {value}').replace('{value}', String(row.criticalGroupCount))}</span>
                    <span>{row.issueDevice}</span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => openNotificationsWithServiceImpact(row.issueId)}
                      className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-semibold text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
                    >
                      {t('dashboard_service_impact_open_issue_flow', 'Open issue flow')}
                    </button>
                    <button
                      type="button"
                      data-testid={`dashboard-service-impact-open-review-${row.issueId}`}
                      onClick={() => openFocusedServiceReview(row.primaryGroupId, row.primaryName)}
                      className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-[11px] font-semibold text-violet-700 transition-colors hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200 dark:hover:bg-violet-950/30"
                    >
                      {t('dashboard_service_impact_open_review', 'Open service review')}
                    </button>
                    <button
                      type="button"
                      onClick={() => openServiceGroups(row.primaryGroupId, row.primaryName)}
                      className="rounded-full border border-gray-200 px-3 py-1 text-[11px] font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/10"
                    >
                      {t('dashboard_service_impact_open_groups', 'Open Service Groups')}
                    </button>
                    {row.siteId ? (
                      <button
                        type="button"
                        onClick={() => openIssueTopology(row.siteId)}
                        className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-200 dark:hover:bg-emerald-950/30"
                      >
                        {t('dashboard_service_impact_open_topology', 'Open Topology')}
                      </button>
                    ) : null}
                  </div>
                </div>
              ))
            ) : (
              <div className="flex h-full flex-col items-center justify-center text-center text-gray-600 italic dark:text-gray-400">
                <ShieldCheck size={28} className="mb-3 text-cyan-300 dark:text-cyan-700" />
                <p className="text-sm">{t('dashboard_service_impact_empty', 'No active service impact is mapped right now.')}</p>
                <p className="mt-1 text-xs not-italic text-gray-500 dark:text-gray-500">
                  {t('dashboard_service_impact_empty_hint', 'Link assets into service groups to make business impact the default operating view.')}
                </p>
              </div>
            )}
          </div>

          <div className="mt-5 border-t border-white/10 pt-5">
            <div className="mb-3 text-[10px] font-black uppercase tracking-widest text-gray-500">
              {t('dashboard_priority_alerts', 'Priority Alerts')}
            </div>
            <div className="space-y-3">
              {dashboardIssues.length > 0 ? (
                dashboardIssues.slice(0, 3).map((issue) => (
                  <IssueItem
                    key={issue.id}
                    issueId={issue.id}
                    title={issue.title}
                    device={issue.device}
                    severity={issue.severity}
                    time={formatRelativeTime(issue.time)}
                    siteName={issue.site_name}
                    serviceContextLabel={
                      Number(issue?.service_impact_summary?.count || 0) > 0
                        ? t('dashboard_priority_service_context_fmt', '{service} · groups {groups}')
                          .replace(
                            '{service}',
                            String(
                              issue?.service_impact_summary?.primary_name
                              || t('dashboard_service_impact_unknown_group', 'Mapped service group'),
                            ),
                          )
                          .replace('{groups}', String(Number(issue?.service_impact_summary?.count || 0)))
                        : ''
                    }
                    serviceHealthStatus={issue?.service_impact_summary?.primary_health_status}
                    serviceHealthScore={issue?.service_impact_summary?.primary_health_score}
                    serviceNextAction={
                      Number(issue?.service_impact_summary?.count || 0) > 0
                        ? getServiceIssueNextActionLabel(issue?.service_impact_summary || {})
                        : ''
                    }
                    showProActions={showProIssueGrafana}
                    onOpenDevice={issue.device_id ? () => openIssueDevice(issue.device_id) : null}
                    onOpenServiceReview={
                      Number(issue?.service_impact_summary?.primary_group_id || 0) > 0
                        ? () => openFocusedServiceReview(
                          issue?.service_impact_summary?.primary_group_id,
                          issue?.service_impact_summary?.primary_name,
                        )
                        : null
                    }
                    onOpenTopology={issue.site_id ? () => openIssueTopology(issue.site_id) : null}
                    onOpenObservability={() => openIssueObservability({ deviceId: issue.device_id, siteId: issue.site_id })}
                    onOpenGrafana={showProIssueGrafana ? () => openIssueGrafana({ deviceId: issue.device_id, siteId: issue.site_id }) : null}
                  />
                ))
              ) : (
                <div className="flex flex-col items-center justify-center py-4 text-gray-600 italic">
                  <CheckCircle size={28} className="mb-3 text-white/5" />
                  <p className="text-xs">{t('dashboard_no_active_issues', 'No active issues found.')}</p>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className={`${metricCardClass}`}>
          <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <LayoutGrid size={16} className="text-violet-500" /> {t('service_groups_review_queue_label', 'Service Review Queue')}
          </h3>
          <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
            {t('service_groups_review_queue_desc', 'Start with the service groups that need attention, then jump straight into topology, alerts, and operations reports.')}
          </p>
          <div className="mb-4 flex flex-wrap items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
            <span className="rounded-full border border-gray-200 px-2.5 py-1 dark:border-white/10">
              {t('service_groups_review_queue_count_fmt', 'Review queue {value}').replace('{value}', String(serviceReviewQueue.length))}
            </span>
            <button
              type="button"
              data-testid="dashboard-service-review-open-groups"
              onClick={() => openServiceGroups()}
              className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1 text-[11px] font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/10"
            >
              {t('dashboard_service_impact_open_groups', 'Open Service Groups')}
            </button>
          </div>
          <div className="space-y-3" data-testid="dashboard-service-review-queue">
            {serviceReviewLoading ? (
              <div className="text-sm text-gray-500 dark:text-gray-400">
                {t('ops_home_service_review_loading', 'Loading service review queue...')}
              </div>
            ) : serviceReviewQueue.length > 0 ? (
              serviceReviewQueue.map((group) => (
                (() => {
                  const recommendedWorkspace = recommendServiceWorkspace(group);
                  const recommendedWorkspaceLabel = t(
                    `ops_workspace_${recommendedWorkspace.workspace}_title`,
                    recommendedWorkspace.workspace === 'discover'
                      ? 'Discover'
                      : recommendedWorkspace.workspace === 'govern'
                        ? 'Govern'
                        : 'Observe',
                  );
                  return (
                    <div
                      key={`dashboard-service-review-${group.id}`}
                      data-testid={`dashboard-service-review-card-${group.id}`}
                      className="rounded-xl border border-violet-200/70 bg-white/90 p-3 shadow-sm dark:border-violet-900/40 dark:bg-black/20 dark:shadow-none"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${serviceHealthTone(group.healthStatus)}`}>
                              {t('service_groups_health_score', 'Health Score')}: {group.healthScore}
                            </span>
                            <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">{group.name}</span>
                          </div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                            {group.description || t('ops_home_service_review_no_description', 'Review this service group through topology, reports, and alerts.')}
                          </div>
                        </div>
                        <div className="text-right text-[11px] text-gray-500 dark:text-gray-400">
                          <div>{t('service_groups_health_active_issues', 'Active issues')}: {group.activeIssueCount}</div>
                          <div>{t('service_groups_health_offline_devices', 'Offline devices')}: {group.offlineDeviceCount}</div>
                        </div>
                      </div>
                      <div className="mt-3 text-[11px] text-gray-500 dark:text-gray-400">
                        {group.nextAction}
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          data-testid={`dashboard-service-review-open-workspace-${group.id}`}
                          onClick={() => navigate(`/automation?workspace=${recommendedWorkspace.workspace}`)}
                          className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-[11px] font-semibold text-sky-700 transition-colors hover:bg-sky-100 dark:border-sky-900/50 dark:bg-sky-950/20 dark:text-sky-200 dark:hover:bg-sky-950/30"
                        >
                          {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', recommendedWorkspaceLabel)}
                        </button>
                        <button
                          type="button"
                          data-testid={`dashboard-service-review-open-review-${group.id}`}
                          onClick={() => openFocusedServiceReview(group.id, group.name)}
                          className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-[11px] font-semibold text-violet-700 transition-colors hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200 dark:hover:bg-violet-950/30"
                        >
                          {t('service_groups_review_open', 'Open Review')}
                        </button>
                        <button
                          type="button"
                          data-testid={`dashboard-service-review-open-notifications-${group.id}`}
                          onClick={() => openNotificationsWithServiceImpact(undefined, group.id, group.name)}
                          className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-semibold text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
                        >
                          {t('service_groups_review_open_notifications', 'Open service-aware alerts')}
                        </button>
                        <button
                          type="button"
                          data-testid={`dashboard-service-review-open-topology-${group.id}`}
                          onClick={() => openFocusedServiceTopology(group.id, group.name)}
                          className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-200 dark:hover:bg-emerald-950/30"
                        >
                          {t('dashboard_service_impact_open_topology', 'Open Topology')}
                        </button>
                      </div>
                    </div>
                  );
                })()
              ))
            ) : (
              <div className="flex h-full flex-col items-center justify-center text-center text-gray-600 italic dark:text-gray-400">
                <LayoutGrid size={28} className="mb-3 text-violet-300 dark:text-violet-700" />
                <p className="text-sm">
                  {serviceReviewError || t('service_groups_review_queue_empty', 'No service groups need immediate review right now. Service posture is stable.')}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {showProOperations && (
        <div className={`${panelClass} gap-4`} data-testid="dashboard-pro-operations-panel">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Workflow size={16} className="text-violet-500" />
                <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                  {t('dashboard_pro_operations_title', 'Pro Operational Delivery')}
                </h3>
              </div>
              <p className="mt-2 max-w-3xl text-sm text-gray-500 dark:text-gray-300">
                {t('dashboard_pro_operations_desc', 'Move from the main NMS dashboard into observability, automation, and alert drilldowns without losing site context.')}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-gray-500">
                <span className="rounded-full border border-gray-200 px-2 py-0.5 dark:border-white/10">
                  {selectedSiteRow
                    ? `${t('dashboard_scope', 'Scope')}: ${selectedSiteRow.name}`
                    : t('dashboard_scope_global', 'Scope: Global')}
                </span>
                <span className={`rounded-full px-2 py-0.5 font-semibold ${statusBadgeClass(northboundStatus)}`}>
                  {t('dashboard_northbound_kpi', 'Northbound KPI')}: {northboundStatus}
                </span>
                <span className={`rounded-full px-2 py-0.5 font-semibold ${statusBadgeClass(closedLoopStatus)}`}>
                  {t('dashboard_closed_loop_kpi', 'Closed-Loop KPI')}: {closedLoopStatus}
                </span>
                <span className={`rounded-full px-2 py-0.5 font-semibold ${statusBadgeClass(releaseOverallStatus)}`}>
                  {t('dashboard_release_status', 'Release')}: {releaseOverallStatus}
                </span>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => navigate(buildObservabilityPath({ siteId: selectedSite || undefined }))}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 dark:border-white/10 dark:bg-black/20 dark:text-gray-200 dark:hover:border-blue-500/40 dark:hover:bg-blue-500/10 dark:hover:text-blue-300"
              >
                <Activity size={16} />
                {t('common_open_observability', 'Open Observability')}
              </button>
              <button
                type="button"
                onClick={() => navigate('/automation')}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:border-violet-300 hover:bg-violet-50 hover:text-violet-700 dark:border-white/10 dark:bg-black/20 dark:text-gray-200 dark:hover:border-violet-500/40 dark:hover:bg-violet-500/10 dark:hover:text-violet-300"
              >
                <Workflow size={16} />
                {t('ops_open_automation_hub', 'Open Operations Home')}
              </button>
              <button
                type="button"
                onClick={() => openExternal(buildGrafanaAlertingCenterUrl({ siteId: selectedSite || undefined }))}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:border-cyan-300 hover:bg-cyan-50 hover:text-cyan-700 dark:border-white/10 dark:bg-black/20 dark:text-gray-200 dark:hover:border-cyan-500/40 dark:hover:bg-cyan-500/10 dark:hover:text-cyan-300"
              >
                <ExternalLink size={16} />
                {t('obs_alert_dashboard', 'Alert Dashboard')}
              </button>
              <button
                type="button"
                onClick={() => navigate('/settings')}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:border-gray-300 hover:bg-gray-50 hover:text-gray-900 dark:border-white/10 dark:bg-black/20 dark:text-gray-200 dark:hover:border-white/20 dark:hover:bg-white/10 dark:hover:text-white"
              >
                <Settings size={16} />
                {t('ops_open_settings', 'Open Settings')}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-white/10 dark:bg-black/20">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                {t('dashboard_delivery_success', 'Delivery Success')}
              </div>
              <div className={`mt-2 text-2xl font-black ${northboundSuccessRate >= 95 ? 'text-emerald-500' : 'text-amber-500'}`}>
                {northboundSuccessRate.toFixed(2)}%
              </div>
              <div className="mt-1 text-xs text-gray-500">
                {Number(northboundTotals.success || 0)} / {Number(northboundTotals.deliveries || 0)} delivered
              </div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-white/10 dark:bg-black/20">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                {t('dashboard_execute_trigger', 'Execute / Trigger')}
              </div>
              <div className={`mt-2 text-2xl font-black ${closedLoopExecutePct >= 50 ? 'text-emerald-500' : 'text-amber-500'}`}>
                {closedLoopExecutePct.toFixed(2)}%
              </div>
              <div className="mt-1 text-xs text-gray-500">
                {closedLoopExecuted} / {closedLoopTriggered} executed
              </div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-white/10 dark:bg-black/20">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                {t('dashboard_release_status', 'Release')}
              </div>
              <div className="mt-2 text-2xl font-black text-gray-900 dark:text-white">
                {releaseAcceptedGates} / {releaseTotalGates}
              </div>
              <div className="mt-1 text-xs text-gray-500">
                {releaseBlockingGates.length > 0
                  ? `${releaseBlockingGates.length} blocking`
                  : t('dashboard_release_no_blockers', 'No blocking gates')}
              </div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-white/10 dark:bg-black/20">
              <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                {t('dashboard_active_issues_short', 'Active Issues')}
              </div>
              <div className={`mt-2 text-2xl font-black ${dashboardIssueCount > 0 ? 'text-amber-500' : 'text-emerald-500'}`}>
                {dashboardIssueCount}
              </div>
              <div className="mt-1 text-xs text-gray-500">
                {selectedSiteRow
                  ? `${selectedSiteRow.name} ${t('dashboard_scope_suffix', 'scope')}`
                  : t('dashboard_scope_global', 'Scope: Global')}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Performance Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-6 gap-6 items-stretch">

        {/* Traffic Chart Component */}
        <div className={`${showProOperations ? 'lg:col-span-2' : 'lg:col-span-3'} flex flex-col`}>
          <TrafficChart data={stats.trafficTrend} />
        </div>

        {/* Resource Chart (Real Data) */}
        <div className={`${metricCardClass} ${showProOperations ? 'lg:col-span-2' : 'lg:col-span-3'}`}>
          <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-2">
            <Activity size={16} className="text-emerald-500" /> Resource Health (Avg)
          </h3>
          <div className="flex-1 w-full min-h-0 relative">
            {/* Gradient Background for Chart */}
            <div className="absolute inset-0 bg-gradient-to-b from-white/5 to-transparent pointer-events-none rounded-xl"></div>

            {analytics.resourceTrend && analytics.resourceTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={analytics.resourceTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="time" stroke="#52525b" fontSize={10} hide />
                  <YAxis domain={[0, 100]} stroke="#52525b" fontSize={10} tick={{ fill: '#9ca3af' }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: 'rgba(20,20,30,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff', backdropFilter: 'blur(4px)' }}
                    itemStyle={{ fontSize: '12px' }}
                  />
                  <Line type="monotone" dataKey="cpu" stroke="#10b981" strokeWidth={2} dot={false} isAnimationActive={false} shadow="0 0 10px #10b981" />
                  <Line type="monotone" dataKey="memory" stroke="#f59e0b" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-xs text-gray-600">
                {t('dashboard_waiting_metrics', 'Waiting for metrics...')}
              </div>
            )}
          </div>
        </div>

        {showProOperations && (
        <>
        {/* Change Execution KPI */}
          <div className={`${metricCardClass} lg:col-span-2`} data-testid="dashboard-kpi-change">
          <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <Radio size={16} className="text-pink-500" /> Change KPI
          </h3>

          <div className="grid grid-cols-1 gap-3">
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_rollback_p95', 'Rollback P95')}</div>
              <div className={`mt-1 text-xl font-bold ${rollbackP95 !== null && Number(rollbackP95) <= changeMaxRollbackP95Target ? 'text-emerald-500' : 'text-amber-500'}`}>{formatMs(rollbackP95)}</div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                target &lt;= {formatMs(changeMaxRollbackP95Target)}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_trace_coverage', 'Trace Coverage')}</div>
              <div className={`mt-1 text-xl font-bold ${traceCoverage >= changeMinTraceTarget ? 'text-emerald-500' : 'text-amber-500'}`}>
                {traceCoverage.toFixed(2)}%
              </div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                {traceLinkedEvents} / {traceContextEvents}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_change_success', 'Change Success')}</div>
              <div className={`mt-1 text-xl font-bold ${changeSuccessRate >= changeMinSuccessTarget ? 'text-emerald-500' : 'text-amber-500'}`}>
                {changeSuccessRate.toFixed(2)}%
              </div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                fail {changeFailureRate.toFixed(2)}% (target &lt;= {changeMaxFailureTarget}%)
              </div>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-white/5">
            <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest mb-2">{t('dashboard_top_failure_causes', 'Top Failure Causes')}</div>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <div className="rounded border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 px-2 py-1 text-[11px] flex items-center justify-between">
                <span className="text-gray-500">pre-check</span>
                <span className={`font-mono font-bold ${precheckFailureCount > 0 ? 'text-red-500' : 'text-gray-500'}`}>{precheckFailureCount}</span>
              </div>
              <div className="rounded border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 px-2 py-1 text-[11px] flex items-center justify-between">
                <span className="text-gray-500">post-check</span>
                <span className={`font-mono font-bold ${postcheckFailureCount > 0 ? 'text-red-500' : 'text-gray-500'}`}>{postcheckFailureCount}</span>
              </div>
            </div>
            {changeFailureTop.length > 0 ? (
              <div className="space-y-2">
                {changeFailureTop.map((row) => (
                  <div key={`${row.cause}-${row.count}`} className="flex items-center justify-between text-xs">
                    <span className="text-gray-700 dark:text-gray-300 truncate mr-2">{formatFailureCauseLabel(row.cause)}</span>
                    <span className="px-2 py-0.5 rounded bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300 font-bold">
                      {Number(row.count || 0)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-gray-500">{t('dashboard_no_failure_data', 'No failure data')}</div>
            )}
          </div>

          <div className="mt-3 pt-3 border-t border-gray-200 dark:border-white/5">
            <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest mb-2">{t('dashboard_recent_approval_trace', 'Recent Approval Trace')}</div>
            {changeTraceRows.length > 0 ? (
              <div className="space-y-2">
                {changeTraceRows.map((row, idx) => {
                  const state = normalizeStatusToken(row?.status);
                  const statusClass = state === 'ok' || state === 'success'
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                    : state === 'precheck_failed' || state === 'pre_check_failed'
                      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                      : state === 'postcheck_failed' || state === 'post_check_failed'
                        ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300';
                  const failureCause = normalizeStatusToken(row?.failure_cause);
                  return (
                    <div
                      key={`${row?.approval_id ?? 'none'}-${row?.execution_id ?? 'none'}-${idx}`}
                      className="rounded-lg border border-gray-100 dark:border-white/5 bg-gray-50 dark:bg-black/20 p-2"
                    >
                      <div className="flex items-center justify-between text-[11px] gap-2">
                        <span className="font-mono text-gray-700 dark:text-gray-300 truncate">
                          A{row?.approval_id ?? '-'} -&gt; E{formatExecutionIdShort(row?.execution_id)}
                        </span>
                        <span className={`px-1.5 py-0.5 rounded font-bold uppercase ${statusClass}`}>
                          {formatExecutionStatusLabel(state)}
                        </span>
                      </div>
                      <div className="text-[10px] text-gray-500 mt-1 font-mono truncate">
                        {String(row?.change_type || '-')} / dev {row?.device_id ?? '-'} / {formatRelativeTime(row?.timestamp)}
                      </div>
                      {failureCause && (
                        <div className="text-[10px] text-red-500 mt-1 font-mono truncate">
                          cause: {formatFailureCauseLabel(failureCause)}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-xs text-gray-500">{t('dashboard_no_approval_trace', 'No approval trace events')}</div>
            )}
          </div>
        </div>

        {/* Ops KPI Readiness (30d) */}
          <div className={`${metricCardClass} lg:col-span-2`} data-testid="dashboard-kpi-readiness">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider flex items-center gap-2">
              <ShieldCheck size={16} className="text-emerald-500" /> {t('dashboard_ops_readiness_30d', 'Ops Readiness (30d)')}
            </h3>
            <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ${readinessStatusClass}`}>
              {readinessStatus}
            </span>
          </div>

          {readinessLatest ? (
            <>
              <div className="grid grid-cols-1 gap-3">
                <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
                  <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_required_checks', 'Required Checks')}</div>
                  <div className="mt-1 text-xl font-bold text-blue-500">{readinessRequiredChecks}</div>
                  <div className="text-[10px] text-gray-500 mt-1 font-mono">
                    pass {readinessPassCount} / fail {readinessFailCount} / unknown {readinessUnknownCount}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
                  <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_snapshot_coverage', 'Snapshot Coverage')}</div>
                  <div className="mt-1 text-xl font-bold text-cyan-500">{readinessCoveragePct.toFixed(2)}%</div>
                  <div className="text-[10px] text-gray-500 mt-1 font-mono">
                    {readinessCoverageDays} / {readinessExpectedDays}d • {Number(readinessTotals.count || 0)} {t('dashboard_snapshots_short', 'snaps')}
                  </div>
                  <div className="text-[10px] text-gray-500 mt-1 font-mono">
                    {t('dashboard_snapshot_age', 'age')} {readinessLatestAgeHours === null || readinessLatestAgeHours === undefined ? '-' : `${Number(readinessLatestAgeHours).toFixed(1)}h`}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
                  <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_snapshot_delta', 'Snapshot Delta')}</div>
                  <div className={`mt-1 text-xl font-bold ${readinessDirectionClass}`}>
                    {formatReadinessDirectionLabel(readinessStatusDirection)}
                  </div>
                  <div className="text-[10px] text-gray-500 mt-1 font-mono">
                    pass {formatSignedDelta(readinessComparison.pass_delta)} / fail {formatSignedDelta(readinessComparison.fail_delta)} / unknown {formatSignedDelta(readinessComparison.unknown_delta)}
                  </div>
                  <div className="text-[10px] text-gray-500 mt-1 font-mono">
                    {t('dashboard_current_streak', 'streak')} {String(readinessCurrentStreak.status || readinessStatus)} x{Number(readinessCurrentStreak.snapshots || 0)}
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-white/5">
                <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_status_trend_7d', 'Status Trend (7d)')}</div>
                {readinessTrend.length > 0 ? (
                  <div className="mt-2 grid grid-cols-7 gap-1 items-end h-12">
                    {readinessTrend.map((row) => {
                      const totalRaw = Number(row?.total || 0);
                      const total = Number.isFinite(totalRaw) ? Math.max(0, totalRaw) : 0;
                      const barHeightPct = Math.max(4, Math.min(100, (total / readinessTrendMaxTotal) * 100));
                      const critical = Number(row?.critical || 0);
                      const warning = Number(row?.warning || 0);
                      const healthy = Number(row?.healthy || 0);
                      const barClass = critical > 0
                        ? 'bg-red-500/80 dark:bg-red-400/80'
                        : warning > 0
                          ? 'bg-amber-500/80 dark:bg-amber-400/80'
                          : healthy > 0
                            ? 'bg-emerald-500/80 dark:bg-emerald-400/80'
                            : 'bg-gray-400/70 dark:bg-gray-500/70';
                      const label = String(row?.date || '').slice(5);
                      return (
                        <div key={`readiness-trend-${row?.date || label}`} className="flex flex-col items-center justify-end gap-1">
                          <div
                            className={`w-full rounded-sm ${barClass}`}
                            style={{ height: `${barHeightPct}%` }}
                            title={`${String(row?.date || '')} total=${total} h=${healthy} w=${warning} c=${critical}`}
                          />
                          <div className="text-[9px] leading-none text-gray-500 font-mono">{label || '--'}</div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-1 text-xs text-gray-500">{t('dashboard_no_readiness_7d', 'No 7d readiness data')}</div>
                )}

                <div className="mt-3 flex items-center justify-between text-[11px] text-gray-500">
                  <span>{t('dashboard_health_warning_critical', 'Healthy / Warning / Critical')}</span>
                  <span className="font-mono">
                    {Number(readinessByStatus.healthy || 0)} / {Number(readinessByStatus.warning || 0)} / {Number(readinessByStatus.critical || 0)}
                  </span>
                </div>

                <div className="mt-4 pt-4 border-t border-gray-200 dark:border-white/5">
                  <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest mb-2">{t('dashboard_sample_coverage', 'Sample Coverage')}</div>
                  <div className="grid grid-cols-2 gap-2 mb-3">
                    {readinessSampleRatioBadges.map((row) => (
                      <div key={row.key} className="rounded border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 px-2 py-1 text-[11px] flex items-center justify-between">
                        <span className="text-gray-500 font-mono">{row.label}</span>
                        <span className="font-mono font-bold text-violet-500">
                          {row.value === null || row.value === undefined ? '-' : `${Number(row.value).toFixed(0)}%`}
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest mb-2">{t('dashboard_top_failing_checks', 'Top Failing Checks')}</div>
                  {readinessTopFailingChecks.length > 0 ? (
                    <div className="space-y-2" data-testid="dashboard-readiness-top-failing">
                      {readinessTopFailingChecks.map((row) => (
                        <div key={`${row.id}-${row.fail_count}`} className="rounded-lg border border-gray-100 dark:border-white/5 bg-gray-50 dark:bg-black/20 p-2">
                          <div className="flex items-center justify-between gap-2 text-xs">
                            <span className="text-gray-700 dark:text-gray-300 truncate mr-2">{formatReadinessCheckLabel(row)}</span>
                            <span className="px-2 py-0.5 rounded bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300 font-bold">
                              {Number(row.fail_count || 0)}x
                            </span>
                          </div>
                          <div className="text-[10px] text-gray-500 mt-1 font-mono truncate">
                            {t('dashboard_threshold_short', 'threshold')} {row.latest_value ?? '-'} / {row.latest_threshold ?? '-'}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-gray-500">{t('dashboard_no_failing_checks', 'No failing checks in history')}</div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-gray-500">
              {t('dashboard_kpi_snapshots_unavailable', 'KPI readiness snapshots not available yet')}
            </div>
          )}
        </div>

        <div className={`${metricCardClass} lg:col-span-2`} data-testid="dashboard-release-evidence">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider flex items-center gap-2">
              <Activity size={16} className="text-cyan-500" /> {t('dashboard_release_evidence', 'Release Evidence')}
            </h3>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={startReleaseEvidenceRefresh}
                disabled={releaseRefreshStarting || releaseRefreshRunning}
                data-testid="dashboard-release-refresh"
                className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-900/20 px-2.5 py-1 text-[11px] font-bold text-emerald-700 dark:text-emerald-300 disabled:opacity-50"
              >
                <RefreshCw size={12} className={releaseRefreshStarting || releaseRefreshRunning ? 'animate-spin' : ''} />
                {t('dashboard_release_refresh', 'Refresh Evidence')}
              </button>
              <button
                type="button"
                onClick={() => setReleaseEvidenceModalOpen(true)}
                data-testid="dashboard-release-evidence-open"
                className="inline-flex items-center gap-1 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-2.5 py-1 text-[11px] font-bold text-gray-700 dark:text-gray-200"
              >
                {t('dashboard_release_details', 'View details')}
              </button>
              <button
                type="button"
                onClick={downloadReleaseBundle}
                disabled={releaseBundleDownloading}
                data-testid="dashboard-release-bundle-download"
                className="inline-flex items-center gap-1 rounded-lg border border-cyan-200 dark:border-cyan-500/30 bg-cyan-50 dark:bg-cyan-900/20 px-2.5 py-1 text-[11px] font-bold text-cyan-700 dark:text-cyan-300 disabled:opacity-50"
              >
                <Download size={12} />
                {t('dashboard_release_bundle_download', 'Download Bundle')}
              </button>
              <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ${releaseOverallClass}`}>
                {releaseOverallStatus.replace(/_/g, ' ')}
              </span>
            </div>
          </div>

          {releaseAvailableGates > 0 ? (
            <>
              <div className="grid grid-cols-1 gap-3">
                {releaseGateRows.map((row) => {
                  const section = row.section || {};
                  const available = !!section.available;
                  const sectionStatus = String(section.status || 'unavailable').toLowerCase();
                  const updatedLabel = formatRelativeTime(section.generated_at || releaseData.generated_at);
                  return (
                    <div
                      key={row.key}
                      className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{row.label}</div>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ${statusBadgeClass(sectionStatus)}`}>
                          {sectionStatus.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <div className="mt-1 text-sm font-bold text-gray-800 dark:text-gray-100">
                        {available ? row.detail : t('dashboard_release_no_evidence', 'No evidence')}
                      </div>
                      <div className="text-[10px] text-gray-500 mt-1 font-mono">
                        {available
                          ? row.subdetail || `${t('dashboard_release_updated', 'updated')} ${updatedLabel || '-'}`
                          : t('dashboard_release_no_evidence', 'No evidence')}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-white/5 space-y-2">
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-3 dark:border-white/5 dark:bg-black/20" data-testid="dashboard-release-refresh-status">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-500">{t('dashboard_release_refresh_job', 'Refresh Job')}</span>
                    <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase ${releaseRefreshClass}`}>
                      {formatReleaseRefreshStatusLabel(releaseRefreshStatus)}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] font-mono text-gray-500">
                    {formatReleaseRefreshStageLabel(releaseRefreshStage)}
                    {releaseRefresh.started_at ? ` · ${formatRelativeTime(releaseRefresh.started_at)}` : ''}
                  </div>
                  {releaseRefresh.last_success_at && (
                    <div className="mt-1 text-[11px] text-gray-500">
                      {t('dashboard_release_refresh_last_success', 'Last success')} {formatRelativeTime(releaseRefresh.last_success_at)}
                    </div>
                  )}
                  {releaseRefreshLastSummary?.total_gates ? (
                    <div className="mt-1 text-[11px] text-gray-500">
                      {t('dashboard_release_refresh_last_result', 'Last result')} {Number(releaseRefreshLastSummary.accepted_gates || 0)} / {Number(releaseRefreshLastSummary.total_gates || 0)}
                    </div>
                  ) : null}
                  {releaseRefresh?.error?.message && (
                    <div className="mt-1 truncate text-[11px] text-red-500">
                      {t('dashboard_release_refresh_error', 'Last error')}: {releaseRefresh.error.message}
                    </div>
                  )}
                </div>
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-3 dark:border-white/5 dark:bg-black/20" data-testid="dashboard-release-automation-policy">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-500">{t('dashboard_release_automation', 'Auto Collection')}</span>
                    <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase ${releaseAutomationClass}`}>
                      {formatReleaseAutomationLabel(releaseAutomationEnabled)}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-gray-500">
                    {t('dashboard_release_automation_profile', 'Profile')} {formatReleaseProfileLabel(releaseAutomationProfile)}
                    {' · '}
                    {t('dashboard_release_automation_synthetic', 'Synthetic')} {releaseAutomationIncludeSynthetic ? 'on' : 'off'}
                  </div>
                  <div className="mt-1 text-[11px] text-gray-500">
                    {releaseAutomationScheduleLabel}
                  </div>
                  <div className="mt-1 text-[11px] text-gray-500">
                    {t('dashboard_release_automation_next_run', 'Next run')} {releaseAutomationNextRunAt ? formatRelativeTime(releaseAutomationNextRunAt) : '-'}
                  </div>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">{t('dashboard_release_gates', 'Accepted Gates')}</span>
                  <span className="font-mono font-bold text-gray-700 dark:text-gray-200">
                    {releaseAcceptedGates} / {releaseTotalGates}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">{t('dashboard_release_available', 'Available Evidence')}</span>
                  <span className="font-mono font-bold text-gray-700 dark:text-gray-200">
                    {releaseAvailableGates} / {releaseTotalGates}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">{t('dashboard_release_blocking_gates', 'Blocking Gates')}</span>
                  <span className={`font-mono font-bold ${releaseBlockingGates.length > 0 ? 'text-red-500' : 'text-gray-500'}`}>
                    {releaseBlockingGates.length}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">{t('dashboard_release_in_progress_gates', 'In Progress')}</span>
                  <span className={`font-mono font-bold ${releaseInProgressGates.length > 0 ? 'text-cyan-500' : 'text-gray-500'}`}>
                    {releaseInProgressGates.length}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-gray-500">
              {t('dashboard_release_no_evidence', 'No evidence')}
            </div>
          )}
        </div>

        {/* Closed-loop KPI */}
          <div className={`${metricCardClass} lg:col-span-2`} data-testid="dashboard-kpi-closed-loop">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider flex items-center gap-2">
              <LayoutGrid size={16} className="text-indigo-500" /> {t('dashboard_closed_loop_kpi', 'Closed-Loop KPI')}
            </h3>
            <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ${closedLoopStatusClass}`}>
              {closedLoopStatus}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_execute_trigger', 'Execute / Trigger')}</div>
              <div className={`mt-1 text-xl font-bold ${closedLoopExecutePct >= 50 ? 'text-emerald-500' : 'text-amber-500'}`}>
                {closedLoopExecutePct.toFixed(2)}%
              </div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                {closedLoopExecuted} / {closedLoopTriggered}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_blocked_trigger', 'Blocked / Trigger')}</div>
              <div className={`mt-1 text-xl font-bold ${closedLoopBlockedPct <= 30 ? 'text-emerald-500' : 'text-amber-500'}`}>
                {closedLoopBlockedPct.toFixed(2)}%
              </div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                {closedLoopBlocked} / {closedLoopTriggered}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_approvals_execute', 'Approvals / Execute')}</div>
              <div className={`mt-1 text-xl font-bold ${closedLoopApprovalPct <= 80 ? 'text-emerald-500' : 'text-amber-500'}`}>
                {closedLoopApprovalPct.toFixed(2)}%
              </div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                {closedLoopApprovals} / {closedLoopExecuted}
              </div>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-white/5">
            <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-300">
              <span className="font-bold">{t('dashboard_cycles_30d', 'Cycles (30d)')}</span>
              <span className="font-mono">{closedLoopCycles}</span>
            </div>
            <div className="mt-2 flex items-center justify-between text-[11px] text-gray-500">
              <span>{t('dashboard_avg_triggered_cycle', 'Avg Triggered/Cycle')}</span>
              <span className="font-mono">{closedLoopAvgTriggered.toFixed(2)}</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-[11px] text-gray-500">
              <span>{t('dashboard_avg_executed_cycle', 'Avg Executed/Cycle')}</span>
              <span className="font-mono">{closedLoopAvgExecuted.toFixed(2)}</span>
            </div>
            <div className="mt-3 text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_top_alerts', 'Top Alerts')}</div>
            {closedLoopTopAlerts.length > 0 ? (
              <div className="mt-2 space-y-2">
                {closedLoopTopAlerts.map((row, idx) => (
                  <div key={`${row.code || row.title}-${idx}`} className="flex items-center justify-between text-xs">
                    <span className="text-gray-700 dark:text-gray-300 truncate mr-2">{row.title || row.code}</span>
                    <span className="font-mono text-gray-500">{Number(row.value || 0).toFixed(2)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-1 text-xs text-gray-500">{t('dashboard_no_alerts', 'No alerts')}</div>
            )}
          </div>
        </div>

        {/* Northbound Delivery KPI */}
        <div className={`${metricCardClass} lg:col-span-2`} data-testid="dashboard-kpi-northbound">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider flex items-center gap-2">
              <Globe size={16} className="text-cyan-500" /> {t('dashboard_northbound_kpi', 'Northbound KPI')}
            </h3>
            <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ${northboundStatusClass}`}>
              {northboundStatus}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_delivery_success', 'Delivery Success')}</div>
              <div className={`mt-1 text-xl font-bold ${northboundSuccessRate >= 95 ? 'text-emerald-500' : 'text-amber-500'}`}>
                {northboundSuccessRate.toFixed(2)}%
              </div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                {Number(northboundTotals.success || 0)} / {Number(northboundTotals.deliveries || 0)}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_attempts', 'Attempts')}</div>
              <div className="mt-1 text-xl font-bold text-blue-500">
                avg {northboundAvgAttempts.toFixed(2)}
              </div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                p95 {northboundP95Attempts.toFixed(0)}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_failures_24h', 'Failures (24h)')}</div>
              <div className={`mt-1 text-xl font-bold ${Number(northboundTotals.failed_24h || 0) > 5 ? 'text-amber-500' : 'text-emerald-500'}`}>
                {Number(northboundTotals.failed_24h || 0)}
              </div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                total failed {Number(northboundTotals.failed || 0)}
              </div>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-white/5">
            <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest mb-2">{t('dashboard_top_connector_modes', 'Top Connector Modes')}</div>
            {northboundModes.length > 0 ? (
              <div className="space-y-2">
                {northboundModes.map((row) => (
                  <div key={`${row.mode}-${row.count}`} className="flex items-center justify-between text-xs">
                    <span className="text-gray-700 dark:text-gray-300 truncate mr-2">{row.mode}</span>
                    <span className="font-mono text-gray-500">{Number(row.count || 0)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-gray-500">{t('dashboard_no_delivery_data', 'No delivery data')}</div>
            )}

            {northboundFailures.length > 0 && (
              <>
                <div className="mt-3 text-[10px] text-gray-500 uppercase font-black tracking-widest mb-2">{t('dashboard_top_failure_causes', 'Top Failure Causes')}</div>
                <div className="space-y-2">
                  {northboundFailures.map((row) => (
                    <div key={`${row.cause}-${row.count}`} className="flex items-center justify-between text-xs">
                      <span className="text-gray-700 dark:text-gray-300 truncate mr-2">{row.cause}</span>
                      <span className="font-mono text-gray-500">{Number(row.count || 0)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Autonomy KPI */}
        <div className={`${metricCardClass} lg:col-span-3`} data-testid="dashboard-kpi-autonomy">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider flex items-center gap-2">
              <Bot size={16} className="text-violet-500" /> {t('dashboard_autonomy_kpi', 'Autonomy KPI')}
            </h3>
            <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ${autonomyStatusClass}`}>
              {autonomyStatus}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_auto_action_rate', 'Auto Action Rate')}</div>
              <div className={`mt-1 text-xl font-bold ${autonomyAutoRate >= autonomyMinAutoRateTarget ? 'text-emerald-500' : 'text-amber-500'}`}>
                {autonomyAutoRate.toFixed(2)}%
              </div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                auto {Number(autonomyTotals.actions_auto || 0)} / all {Number(autonomyTotals.actions_executed || 0)}
              </div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                target {'>='} {Number.isFinite(autonomyMinAutoRateTarget) ? autonomyMinAutoRateTarget.toFixed(2) : '60.00'}%
              </div>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_mttd', 'MTTD')}</div>
              <div className="mt-1 text-xl font-bold text-blue-500">{formatSeconds(autonomyMttd)}</div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                p95 {formatSeconds(autonomyMttdP95)}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_mttr', 'MTTR')}</div>
              <div className="mt-1 text-xl font-bold text-cyan-500">{formatSeconds(autonomyMttr)}</div>
              <div className="text-[10px] text-gray-500 mt-1 font-mono">
                p95 {formatSeconds(autonomyMttrP95)}
              </div>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-white/5">
            <div className={`flex items-center justify-between text-[11px] ${autonomyOperatorRate <= autonomyMaxOperatorRateTarget ? 'text-emerald-600 dark:text-emerald-300' : 'text-amber-600 dark:text-amber-300'}`}>
              <span>{t('dashboard_operator_intervention', 'Operator Intervention')}</span>
              <span className="font-mono">{autonomyOperatorRate.toFixed(2)}%</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-[11px] text-gray-500">
              <span>{t('dashboard_operator_target', 'Operator Target')}</span>
              <span className="font-mono">{Number.isFinite(autonomyMaxOperatorRateTarget) ? autonomyMaxOperatorRateTarget.toFixed(2) : '40.00'}%</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-[11px] text-gray-500">
              <span>{t('dashboard_mttd_signal_coverage', 'MTTD Signal Coverage')}</span>
              <span className="font-mono">{autonomyMttdCoverage.toFixed(2)}%</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-[11px] text-gray-500">
              <span>{t('dashboard_mttr_coverage', 'MTTR Coverage')}</span>
              <span className="font-mono">{autonomyMttrCoverage.toFixed(2)}%</span>
            </div>
            <div className="mt-3 text-[10px] text-gray-500 uppercase font-black tracking-widest">{t('dashboard_auto_action_trend_7d', 'Auto Action Trend (7d)')}</div>
            {autonomyTrend7d.length > 0 ? (
              <div className="mt-2 grid grid-cols-7 gap-1 items-end h-12">
                {autonomyTrend7d.map((row) => {
                  const autoPctRaw = Number(row?.auto_action_rate_pct || 0);
                  const autoPct = Number.isFinite(autoPctRaw) ? Math.max(0, Math.min(100, autoPctRaw)) : 0;
                  const executed = Number(row?.actions_executed || 0);
                  const intensity = Math.max(0.35, Math.min(1, (Number.isFinite(executed) ? executed : 0) / autonomyTrendMaxExecuted));
                  const label = String(row?.date || '').slice(5);
                  return (
                    <div key={`autonomy-trend-${row?.date || label}`} className="flex flex-col items-center justify-end gap-1">
                      <div
                        className="w-full rounded-sm bg-violet-500/80 dark:bg-violet-400/80"
                        style={{ height: `${Math.max(4, autoPct)}%`, opacity: intensity }}
                        title={`${String(row?.date || '')} auto ${autoPct.toFixed(2)}% (exec ${Number.isFinite(executed) ? executed : 0})`}
                      />
                      <div className="text-[9px] leading-none text-gray-500 font-mono">{label || '--'}</div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="mt-1 text-xs text-gray-500">{t('dashboard_no_trend_7d', 'No 7d trend data')}</div>
            )}
          </div>
        </div>

        {/* Controller Self-Health */}
        <div className={`${metricCardClass} lg:col-span-3`} data-testid="dashboard-kpi-controller-health">
          <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <Server size={16} className="text-blue-500 dark:text-primary" /> {t('dashboard_controller_health', 'Controller Health')}
          </h3>

          {selfHealth ? (
            <div className="flex-1 flex flex-col gap-4">
              <div className="grid grid-cols-1 gap-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-bold text-gray-600 dark:text-gray-300">{t('dashboard_metric_cpu', 'CPU')}</div>
                  <div className="text-xs font-mono text-gray-500">{controllerCpuPct === null ? '-' : `${controllerCpuPct.toFixed(0)}%`}</div>
                </div>
                <div className="w-full bg-black/10 dark:bg-black/40 h-1.5 rounded-full overflow-hidden border border-gray-200 dark:border-white/5">
                  <div className="bg-blue-500 h-full rounded-full transition-all duration-700" style={{ width: `${controllerCpuPct ?? 0}%` }} />
                </div>

                <div className="flex items-center justify-between pt-2">
                  <div className="text-xs font-bold text-gray-600 dark:text-gray-300">{t('dashboard_metric_memory', 'Memory')}</div>
                  <div className="text-xs font-mono text-gray-500">
                    {formatBytes(selfHealth?.memory?.used_bytes)} / {formatBytes(selfHealth?.memory?.limit_bytes)}
                    {controllerMemPct === null ? '' : ` (${controllerMemPct.toFixed(0)}%)`}
                  </div>
                </div>
                <div className="w-full bg-black/10 dark:bg-black/40 h-1.5 rounded-full overflow-hidden border border-gray-200 dark:border-white/5">
                  <div className="bg-emerald-500 h-full rounded-full transition-all duration-700" style={{ width: `${controllerMemPct ?? 0}%` }} />
                </div>

                <div className="flex items-center justify-between pt-2">
                  <div className="text-xs font-bold text-gray-600 dark:text-gray-300">{t('dashboard_metric_disk', 'Disk (/)')}</div>
                  <div className="text-xs font-mono text-gray-500">
                    {formatBytes(rootDisk?.used_bytes)} / {formatBytes(rootDisk?.total_bytes)}
                    {controllerDiskPct === null ? '' : ` (${controllerDiskPct.toFixed(0)}%)`}
                  </div>
                </div>
                <div className="w-full bg-black/10 dark:bg-black/40 h-1.5 rounded-full overflow-hidden border border-gray-200 dark:border-white/5">
                  <div className="bg-orange-500 h-full rounded-full transition-all duration-700" style={{ width: `${controllerDiskPct ?? 0}%` }} />
                </div>
              </div>

              <div className="mt-auto pt-4 border-t border-gray-200 dark:border-white/5">
                <div className="flex items-center justify-between">
                  <div className="text-xs text-gray-500 uppercase font-black tracking-widest">{t('dashboard_uptime', 'Uptime')}</div>
                  <div className="text-xs font-mono text-gray-500">{uptimeLabel(selfHealth?.uptime_seconds)}</div>
                </div>
                {Array.isArray(selfHealth?.services) && (
                  <div className="mt-2 text-[11px] text-gray-500">
                    {t('dashboard_services_tracked', 'Services tracked')}: <span className="font-mono">{selfHealth.services.length}</span>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-gray-500">
              {t('dashboard_self_health_unavailable', 'Self-Health data unavailable')}
            </div>
          )}
        </div>
        </>
        )}
      </div>

      <ReleaseEvidenceModal
        isOpen={releaseEvidenceModalOpen}
        onClose={() => setReleaseEvidenceModalOpen(false)}
        releaseData={releaseData}
        releaseSummary={releaseSummary}
        releaseGateRows={releaseGateRows}
      />
    </div >
  );
};

const StatusBox = ({ label, value, icon: Icon, color, alert }) => (
  <div className={`p-4 rounded-xl border transition-all duration-300 group hover:translate-y-[-2px] ${alert ? 'bg-red-50 border-red-200 dark:bg-red-900/10 dark:border-red-500/30' : 'bg-gray-50 dark:bg-black/20 border-gray-100 dark:border-white/5 hover:border-blue-200 dark:hover:border-white/10 hover:bg-white dark:hover:bg-white/5'} flex flex-col justify-between`}>
    <div className="flex justify-between items-start">
      <Icon size={18} className={`${color} opacity-80 group-hover:opacity-100 transition-opacity`} />
      <span className={`text-2xl font-bold font-mono tracking-tight ${alert ? 'text-red-500 dark:text-red-400' : 'text-gray-900 dark:text-white'}`}>{value}</span>
    </div>
    <span className="text-[10px] text-gray-500 uppercase mt-2 font-bold tracking-wider group-hover:text-gray-400 transition-colors">{label}</span>
  </div>
);

const IssueItem = ({
  issueId,
  title,
  device,
  severity,
  time,
  siteName,
  serviceContextLabel,
  serviceHealthStatus,
  serviceHealthScore,
  serviceNextAction,
  showProActions = false,
  onOpenDevice,
  onOpenServiceReview,
  onOpenTopology,
  onOpenObservability,
  onOpenGrafana,
}) => {
  const color = severity === 'critical' ? 'bg-danger shadow-neon-danger' : severity === 'warning' ? 'bg-warning' : 'bg-primary';
  return (
    <div
      className="flex gap-3 p-3 rounded-xl bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5 hover:border-blue-200 dark:hover:border-white/20 hover:bg-white dark:hover:bg-white/5 transition-all group shadow-sm dark:shadow-none"
      data-testid={issueId ? `dashboard-issue-card-${issueId}` : undefined}
    >
      <div className={`w-1 h-full rounded-full ${color}`}></div>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between">
          <span className="text-xs font-bold text-gray-800 dark:text-gray-200 group-hover:text-blue-600 dark:group-hover:text-white transition-colors">{title}</span>
          <span className="text-[10px] text-gray-500 font-mono">{time}</span>
        </div>
        <div className="text-[11px] text-gray-500 truncate mt-0.5">{device}</div>
        {siteName ? (
          <div className="mt-1 text-[10px] uppercase tracking-widest text-gray-400">{siteName}</div>
        ) : null}
        {serviceContextLabel ? (
          <div className="mt-2 space-y-1.5" data-testid={issueId ? `dashboard-issue-service-context-${issueId}` : undefined}>
            <div className="text-[10px] font-semibold text-cyan-700 dark:text-cyan-300">
              {t('dashboard_service_impact_badge', 'Service impact')}: {serviceContextLabel}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${serviceHealthTone(serviceHealthStatus)}`}>
                {formatServiceHealthLabel(serviceHealthStatus)}
              </span>
              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${serviceHealthTone(serviceHealthStatus)}`}>
                {t('service_groups_health_score', 'Health Score')}: {Number.isFinite(Number(serviceHealthScore)) ? Number(serviceHealthScore) : 0}
              </span>
            </div>
            {serviceNextAction ? (
              <div className="text-[10px] text-gray-500 dark:text-gray-400">
                {serviceNextAction}
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          {onOpenServiceReview ? (
            <button
              type="button"
              data-testid={issueId ? `dashboard-issue-open-review-${issueId}` : undefined}
              onClick={onOpenServiceReview}
              className="rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-[10px] font-semibold text-violet-700 transition-colors hover:border-violet-300 hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200 dark:hover:border-violet-500/40 dark:hover:bg-violet-950/30"
            >
              {t('dashboard_service_impact_open_review', 'Open service review')}
            </button>
          ) : null}
          {onOpenDevice ? (
            <button
              type="button"
              onClick={onOpenDevice}
              className="rounded-full border border-gray-200 dark:border-white/10 px-2.5 py-1 text-[10px] font-semibold text-gray-600 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 dark:text-gray-300 dark:hover:border-blue-500/40 dark:hover:bg-blue-500/10 dark:hover:text-blue-300"
            >
              {t('obs_open_device', 'Open Device')}
            </button>
          ) : null}
          {onOpenTopology ? (
            <button
              type="button"
              onClick={onOpenTopology}
              className="rounded-full border border-gray-200 dark:border-white/10 px-2.5 py-1 text-[10px] font-semibold text-gray-600 transition-colors hover:border-cyan-300 hover:bg-cyan-50 hover:text-cyan-700 dark:text-gray-300 dark:hover:border-cyan-500/40 dark:hover:bg-cyan-500/10 dark:hover:text-cyan-300"
            >
              {t('obs_open_topology', 'Open Topology')}
            </button>
          ) : null}
          {onOpenObservability ? (
            <button
              type="button"
              onClick={onOpenObservability}
              className="rounded-full border border-gray-200 dark:border-white/10 px-2.5 py-1 text-[10px] font-semibold text-gray-600 transition-colors hover:border-violet-300 hover:bg-violet-50 hover:text-violet-700 dark:text-gray-300 dark:hover:border-violet-500/40 dark:hover:bg-violet-500/10 dark:hover:text-violet-300"
            >
              {t('common_open_observability', 'Open Observability')}
            </button>
          ) : null}
          {showProActions && onOpenGrafana ? (
            <button
              type="button"
              onClick={onOpenGrafana}
              className="rounded-full border border-gray-200 dark:border-white/10 px-2.5 py-1 text-[10px] font-semibold text-gray-600 transition-colors hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700 dark:text-gray-300 dark:hover:border-emerald-500/40 dark:hover:bg-emerald-500/10 dark:hover:text-emerald-300"
            >
              {t('notifications_open_grafana', 'Open Grafana')}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export default DashboardPage;
