import React, { useEffect, useMemo, useState } from 'react';
import { ArrowRightLeft, Camera, Clock3, RefreshCw, Server, ShieldAlert, TimerReset, Workflow } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import { StateHistoryService } from '../api/services';
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';

const PANEL_CLASS = 'rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] shadow-sm';

const formatTs = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('ko-KR', { hour12: false });
};

const MetricCard = ({ icon: Icon, title, value, hint }) => (
  <div className={`${PANEL_CLASS} p-4`}>
    <div className="flex items-center justify-between gap-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{title}</div>
      <Icon size={18} className="text-blue-500" />
    </div>
    <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{value}</div>
    {hint ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</div> : null}
  </div>
);

const toneClass = (tone) => {
  const normalized = String(tone || '').trim().toLowerCase();
  if (normalized === 'good') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-500/10 dark:text-emerald-300';
  }
  if (normalized === 'warn' || normalized === 'bad') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/40 dark:bg-amber-500/10 dark:text-amber-300';
  }
  return 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-500/10 dark:text-slate-300';
};

const StateHistoryPage = () => {
  useLocaleRerender();
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [capturing, setCapturing] = useState(false);
  const [currentSnapshot, setCurrentSnapshot] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState(null);
  const pageContext = useMemo(() => {
    const params = new URLSearchParams(location.search);
    const focusSnapshotId = Number(params.get('focusSnapshotId') || 0);
    const focusIssueId = Number(params.get('focusIssueId') || 0);
    const focusRequestId = Number(params.get('focusRequestId') || 0);
    const entry = String(params.get('entry') || '').trim().toLowerCase();
    return {
      focusSnapshotId: focusSnapshotId > 0 ? focusSnapshotId : null,
      focusIssueId: focusIssueId > 0 ? focusIssueId : null,
      focusRequestId: focusRequestId > 0 ? focusRequestId : null,
      entry,
    };
  }, [location.search]);

  const loadPage = async ({ preferredSnapshotId = null } = {}) => {
    setLoading(true);
    try {
      const [currentRes, listRes] = await Promise.all([
        StateHistoryService.getCurrent(),
        StateHistoryService.listSnapshots({ limit: 12 }),
      ]);
      const current = currentRes?.data || null;
      const rows = Array.isArray(listRes?.data) ? listRes.data : [];
      setCurrentSnapshot(current);
      setSnapshots(rows);

      const targetId = preferredSnapshotId || rows?.[0]?.event_log_id || null;
      setSelectedSnapshotId(targetId);
      if (targetId) {
        const compareRes = await StateHistoryService.compareSnapshot(targetId);
        setComparison(compareRes?.data || null);
      } else {
        setComparison(null);
      }
    } catch (error) {
      toast.error(`${t('state_history_load_failed', 'Failed to load state history')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPage({ preferredSnapshotId: pageContext.focusSnapshotId });
  }, [pageContext.focusSnapshotId]);

  const handleCapture = async () => {
    setCapturing(true);
    try {
      const contextLabel = pageContext.focusRequestId
        ? t('state_history_context_approval_label_fmt', 'Approval #{value} review snapshot').replace('{value}', String(pageContext.focusRequestId))
        : pageContext.focusIssueId
          ? t('state_history_context_issue_label_fmt', 'Issue #{value} review snapshot').replace('{value}', String(pageContext.focusIssueId))
          : undefined;
      const contextNote = pageContext.focusRequestId
        ? t('state_history_context_approval_note_fmt', 'Captured while reviewing approval request #{value}.').replace('{value}', String(pageContext.focusRequestId))
        : pageContext.focusIssueId
          ? t('state_history_context_issue_note_fmt', 'Captured while reviewing issue #{value}.').replace('{value}', String(pageContext.focusIssueId))
          : undefined;
      const res = await StateHistoryService.createSnapshot({
        label: contextLabel,
        note: contextNote,
      });
      const created = res?.data || null;
      if (created?.event_log_id) {
        const nextParams = new URLSearchParams(location.search);
        nextParams.set('focusSnapshotId', String(created.event_log_id));
        navigate(`/state-history?${nextParams.toString()}`, { replace: true });
      }
      toast.success(t('state_history_capture_success', 'State snapshot captured.'));
      await loadPage({ preferredSnapshotId: created?.event_log_id || null });
    } catch (error) {
      toast.error(`${t('state_history_capture_failed', 'Failed to capture state snapshot')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setCapturing(false);
    }
  };

  const handleCompare = async (snapshotId) => {
    setSelectedSnapshotId(snapshotId);
    try {
      const res = await StateHistoryService.compareSnapshot(snapshotId);
      setComparison(res?.data || null);
    } catch (error) {
      toast.error(`${t('state_history_compare_failed', 'Failed to compare state snapshot')}: ${error?.response?.data?.detail || error.message}`);
    }
  };

  const metrics = currentSnapshot?.metrics || {};
  const contextBanner = useMemo(() => {
    if (pageContext.focusRequestId) {
      return {
        title: t('state_history_context_approval_title', 'Approval review context'),
        desc: t('state_history_context_approval_desc', 'You opened State History from an approval review. Compare the current posture with a saved baseline before you finalize change approval or rollback decisions.'),
        badge: t('state_history_context_focus_request_fmt', 'Approval #{value}').replace('{value}', String(pageContext.focusRequestId)),
        openLabel: t('state_history_context_open_approval', 'Return to Approval'),
        openPath: `/approval?focusRequestId=${encodeURIComponent(String(pageContext.focusRequestId))}`,
      };
    }
    if (pageContext.focusIssueId) {
      return {
        title: t('state_history_context_issue_title', 'Issue flow context'),
        desc: t('state_history_context_issue_desc', 'You opened State History from an active issue flow. Use this compare view to explain what changed before the issue was escalated, handed off, or closed.'),
        badge: t('state_history_context_focus_issue_fmt', 'Issue #{value}').replace('{value}', String(pageContext.focusIssueId)),
        openLabel: t('state_history_context_open_issue_flow', 'Return to Issue Flow'),
        openPath: `/notifications?focusIssueId=${encodeURIComponent(String(pageContext.focusIssueId))}&openActions=1&openApproval=1&openKnowledge=1&openSop=1&openServiceImpact=1`,
      };
    }
    return null;
  }, [pageContext.focusIssueId, pageContext.focusRequestId]);
  const topCards = useMemo(
    () => [
      {
        title: t('state_history_metric_devices', 'Devices'),
        value: Number(metrics.devices_total || 0),
        hint: t('state_history_metric_devices_hint', '{managed} managed / {discovered} discovered only')
          .replace('{managed}', String(metrics.managed_devices || 0))
          .replace('{discovered}', String(metrics.discovered_only_devices || 0)),
        icon: Server,
      },
      {
        title: t('state_history_metric_issues', 'Active Issues'),
        value: Number(metrics.active_issues_total || 0),
        hint: t('state_history_metric_issues_hint', '{critical} critical').replace('{critical}', String(metrics.critical_issues_total || 0)),
        icon: ShieldAlert,
      },
      {
        title: t('state_history_metric_actions', 'Open Actions'),
        value: Number(metrics.open_actions_total || 0) + Number(metrics.investigating_actions_total || 0),
        hint: t('state_history_metric_actions_hint', '{mitigated} mitigated').replace('{mitigated}', String(metrics.mitigated_actions_total || 0)),
        icon: Workflow,
      },
      {
        title: t('state_history_metric_approvals', 'Pending Approvals'),
        value: Number(metrics.pending_approvals_total || 0),
        hint: t('state_history_metric_approvals_hint', '{evidence} evidence-ready').replace('{evidence}', String(metrics.evidence_ready_approvals_total || 0)),
        icon: ArrowRightLeft,
      },
    ],
    [metrics],
  );

  return (
    <div
      data-testid="state-history-page"
      className="p-3 sm:p-4 md:p-6 bg-[#f4f5f9] dark:bg-[#0e1012] h-full min-h-0 flex flex-col overflow-y-auto animate-fade-in text-gray-900 dark:text-white"
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between mb-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-cyan-700 dark:border-cyan-900/50 dark:bg-cyan-500/10 dark:text-cyan-300">
            <TimerReset size={14} />
            {t('state_history_badge', 'State History')}
          </div>
          <h1 className="mt-3 text-2xl font-black tracking-tight">{t('state_history_title', 'State History')}</h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
            {t(
              'state_history_desc',
              "Capture lightweight operating snapshots, then compare today's posture with the last review point. This gives operators a time-travel baseline without introducing a heavy replay engine.",
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            data-testid="state-history-refresh"
            onClick={() => void loadPage({ preferredSnapshotId: selectedSnapshotId })}
            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] px-4 py-2 text-sm font-bold text-gray-700 dark:text-gray-100"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            {t('common_refresh', 'Refresh')}
          </button>
          <button
            data-testid="state-history-capture"
            onClick={handleCapture}
            disabled={capturing}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 dark:bg-white px-4 py-2 text-sm font-bold text-white dark:text-slate-900 disabled:opacity-60"
          >
            <Camera size={16} />
            {capturing ? t('state_history_capturing', 'Capturing...') : t('state_history_capture', 'Capture Snapshot')}
          </button>
        </div>
      </div>

      {contextBanner ? (
        <div className="mb-6 rounded-2xl border border-cyan-200 dark:border-cyan-900/40 bg-cyan-50/80 dark:bg-cyan-950/10 px-4 py-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-sm font-black text-cyan-900 dark:text-cyan-100">{contextBanner.title}</div>
              <div className="mt-2 text-sm text-cyan-800 dark:text-cyan-200 max-w-3xl">{contextBanner.desc}</div>
            </div>
            <div className="flex flex-wrap gap-2 items-center">
              <span className="inline-flex items-center px-3 py-1 rounded-full border border-cyan-300 dark:border-cyan-800 bg-white/80 dark:bg-cyan-950/20 text-xs font-bold text-cyan-800 dark:text-cyan-200">
                {contextBanner.badge}
              </span>
              <button
                type="button"
                onClick={() => navigate(contextBanner.openPath)}
                className="inline-flex items-center gap-2 rounded-xl border border-cyan-300 dark:border-cyan-800 bg-white/80 dark:bg-cyan-950/30 px-4 py-2 text-xs font-bold text-cyan-800 dark:text-cyan-100 hover:bg-white dark:hover:bg-cyan-900/40"
              >
                <Workflow size={14} />
                {contextBanner.openLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        {topCards.map((card) => (
          <MetricCard key={card.title} {...card} />
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.18fr)] gap-4">
        <section className="space-y-4">
          <div className={`${PANEL_CLASS} p-5`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('state_history_current_title', 'Current Operating Snapshot')}</div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {t('state_history_current_desc', 'Use the current posture as the live reference point before you compare it to the last weekly review or change baseline.')}
                </div>
              </div>
              <div className="text-xs font-semibold text-gray-500 dark:text-gray-400">{formatTs(currentSnapshot?.generated_at)}</div>
            </div>
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] px-4 py-3">
                <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('state_history_current_profiles', 'Monitoring Coverage')}</div>
                <div className="mt-2 text-sm font-semibold text-gray-800 dark:text-gray-100">
                  {(currentSnapshot?.coverage?.devices_with_monitoring_profile || 0)} / {(currentSnapshot?.metrics?.devices_total || 0)} {t('state_history_assets', 'assets')}
                </div>
              </div>
              <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] px-4 py-3">
                <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('state_history_current_services', 'Service Mapping')}</div>
                <div className="mt-2 text-sm font-semibold text-gray-800 dark:text-gray-100">
                  {(currentSnapshot?.coverage?.cloud_resources_mapped_to_services || 0)} {t('state_history_mapped_cloud', 'mapped cloud')} / {(currentSnapshot?.coverage?.service_groups_with_owner || 0)} {t('state_history_owned_groups', 'owned groups')}
                </div>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {(currentSnapshot?.highlights || []).map((item) => (
                <span
                  key={`highlight-${item.key}`}
                  className="inline-flex items-center gap-2 rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-3 py-1 text-xs font-semibold text-gray-600 dark:text-gray-300"
                >
                  {item.value || item.key}
                  {item.count != null ? <span className="text-blue-600 dark:text-blue-300">{item.count}</span> : null}
                </span>
              ))}
            </div>
          </div>

          <div className={`${PANEL_CLASS} p-5`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('state_history_list_title', 'Recent Snapshots')}</div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {t('state_history_list_desc', 'Compare the current operating state with a previous baseline captured during a weekly review, maintenance window, or post-change handoff.')}
                </div>
              </div>
              <button
                onClick={() => navigate('/operations-reports')}
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
              >
                {t('state_history_open_operations_reports', 'Open Operations Reports')}
              </button>
            </div>
            <div className="mt-4 space-y-3">
              {snapshots.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-5 text-sm text-gray-500 dark:text-gray-400">
                  {t('state_history_list_empty', 'No saved snapshots yet. Capture a snapshot after a weekly review or before a major change.')}
                </div>
              ) : (
                snapshots.map((snapshot) => {
                  const active = Number(selectedSnapshotId || 0) === Number(snapshot.event_log_id || 0);
                  return (
                    <button
                      key={`snapshot-${snapshot.event_log_id}`}
                      onClick={() => void handleCompare(snapshot.event_log_id)}
                      className={`w-full text-left rounded-xl border px-4 py-4 transition ${active ? 'border-blue-300 bg-blue-50/80 dark:border-blue-500/40 dark:bg-blue-500/10' : 'border-gray-200 bg-gray-50/70 hover:bg-gray-100 dark:border-gray-800 dark:bg-[#111315] dark:hover:bg-white/5'}`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{snapshot.label || t('state_history_snapshot_default_label', 'State snapshot')}</div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{formatTs(snapshot.generated_at)}</div>
                        </div>
                        <div className="inline-flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400">
                          <Clock3 size={14} />
                          {snapshot.metrics.managed_devices} {t('state_history_managed_short', 'managed')}
                        </div>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-gray-600 dark:text-gray-300">
                        <div>{t('state_history_snapshot_devices', 'Devices')}: {snapshot.metrics.devices_total}</div>
                        <div>{t('state_history_snapshot_cloud', 'Cloud')}: {snapshot.metrics.cloud_resources_total}</div>
                        <div>{t('state_history_snapshot_issues', 'Issues')}: {snapshot.metrics.active_issues_total}</div>
                        <div>{t('state_history_snapshot_approvals', 'Pending approvals')}: {snapshot.metrics.pending_approvals_total}</div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </section>

        <section className={`${PANEL_CLASS} p-5`}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('state_history_compare_title', 'Current vs Baseline')}</div>
              <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                {t('state_history_compare_desc', 'Compare the current operating posture with a saved baseline so teams can explain drift, pressure, and service coverage changes before a handoff or approval review.')}
              </div>
            </div>
            {comparison?.summary ? (
              <span
                className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-black uppercase tracking-[0.18em] ${toneClass(
                  comparison.summary.result === 'review' ? 'warn' : comparison.summary.result === 'improved' ? 'good' : 'info',
                )}`}
              >
                {t(`state_history_result_${comparison.summary.result}`, comparison.summary.result)}
              </span>
            ) : null}
          </div>

          {!comparison ? (
            <div className="mt-4 rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
              {t('state_history_compare_empty', 'Select or capture a snapshot to compare it with the current state.')}
            </div>
          ) : (
            <>
              <div className="mt-4 grid grid-cols-1 sm:grid-cols-4 gap-3">
                <MetricCard
                  icon={TimerReset}
                  title={t('state_history_compare_changed', 'Changed')}
                  value={Number(comparison.summary.changed_cards || 0)}
                  hint={t('state_history_compare_changed_hint', 'Posture cards that moved without turning into an immediate risk')}
                />
                <MetricCard
                  icon={Server}
                  title={t('state_history_compare_improved', 'Improved')}
                  value={Number(comparison.summary.improved_cards || 0)}
                  hint={t('state_history_compare_improved_hint', 'Coverage or readiness improved since the saved baseline')}
                />
                <MetricCard
                  icon={ShieldAlert}
                  title={t('state_history_compare_review', 'Needs Review')}
                  value={Number(comparison.summary.review_cards || 0)}
                  hint={t('state_history_compare_review_hint', 'Cards that now deserve operator attention')}
                />
                <MetricCard
                  icon={Clock3}
                  title={t('state_history_compare_steady', 'Steady')}
                  value={Number(comparison.summary.steady_cards || 0)}
                  hint={t('state_history_compare_steady_hint', 'No meaningful drift from the saved baseline')}
                />
              </div>

              <div className="mt-4 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                <span className="font-bold text-gray-900 dark:text-gray-100">{comparison.baseline.label || t('state_history_snapshot_default_label', 'State snapshot')}</span>
                <span className="mx-2">-&gt;</span>
                <span>{formatTs(comparison.current.generated_at)}</span>
              </div>

              <div className="mt-4 space-y-3">
                {(comparison.cards || []).map((card) => (
                  <div key={card.key} className={`${PANEL_CLASS} border p-4`}>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{card.title}</div>
                      <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-black uppercase tracking-[0.18em] ${toneClass(card.tone)}`}>
                        {t(`state_history_card_status_${card.status}`, card.status)}
                      </span>
                    </div>
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] px-3 py-3">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('state_history_before', 'Before')}</div>
                        <div className="mt-2 font-semibold text-gray-800 dark:text-gray-100">{card.before}</div>
                      </div>
                      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] px-3 py-3">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('state_history_after', 'Current')}</div>
                        <div className="mt-2 font-semibold text-gray-800 dark:text-gray-100">{card.current}</div>
                      </div>
                      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] px-3 py-3">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('state_history_delta', 'Delta')}</div>
                        <div className="mt-2 font-semibold text-gray-800 dark:text-gray-100">{card.delta}</div>
                      </div>
                    </div>
                    {card.recommendation ? <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">{card.recommendation}</div> : null}
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
};

export default StateHistoryPage;
