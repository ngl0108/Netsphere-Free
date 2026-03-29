import React from 'react';
import { Panel } from 'reactflow';
import { AlertTriangle, CheckCircle, Clock3, Link2, RefreshCw, Sparkles, Target, XCircle } from 'lucide-react';
import { DiscoveryService, TopologyService } from '../../../api/services';
import { t } from '../../../i18n';

const BACKLOG_STATUSES = new Set(['low_confidence', 'unmatched', 'pending', 'queued', 'new', 'open', 'backlog', 'proposed']);
const RESOLVED_STATUSES = new Set(['promoted', 'ignored', 'approved']);

const PRIORITY_TONES = {
  critical: 'border-red-700 bg-red-900/30 text-red-200',
  high: 'border-orange-700 bg-orange-900/30 text-orange-200',
  medium: 'border-amber-700 bg-amber-900/30 text-amber-200',
  low: 'border-slate-700 bg-slate-900/40 text-slate-200',
};

const STATUS_TONES = {
  low_confidence: 'border-amber-700 bg-amber-900/25 text-amber-200',
  unmatched: 'border-sky-700 bg-sky-900/25 text-sky-200',
  promoted: 'border-emerald-700 bg-emerald-900/25 text-emerald-200',
  approved: 'border-emerald-700 bg-emerald-900/25 text-emerald-200',
  ignored: 'border-slate-700 bg-slate-900/40 text-slate-200',
};

const normalizeStatus = (value) => String(value || '').trim().toLowerCase();

const formatRelativeAge = (seconds) => {
  const total = Number(seconds || 0);
  if (!Number.isFinite(total) || total <= 0) return t('topology_seen_just_now', 'just now');
  if (total >= 86400) return t('topology_age_days', '{count}d').replace('{count}', String(Math.floor(total / 86400)));
  if (total >= 3600) return t('topology_age_hours', '{count}h').replace('{count}', String(Math.floor(total / 3600)));
  if (total >= 60) return t('topology_age_minutes', '{count}m').replace('{count}', String(Math.floor(total / 60)));
  return t('topology_age_seconds', '{count}s').replace('{count}', String(Math.floor(total)));
};

const formatTimestamp = (value) => {
  if (!value) return '-';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value);
  return dt.toLocaleString();
};

const statusTone = (status) => STATUS_TONES[normalizeStatus(status)] || 'border-gray-700 bg-gray-900/20 text-gray-200';
const priorityTone = (priorityBand) => PRIORITY_TONES[String(priorityBand || '').trim().toLowerCase()] || PRIORITY_TONES.low;
const isBacklogCandidate = (candidate) => BACKLOG_STATUSES.has(normalizeStatus(candidate?.status));

const CandidatePanel = ({
  setShowCandidates,
  candidateJobId,
  setCandidateJobId,
  candidateSearch,
  setCandidateSearch,
  candidateStatusFilter,
  setCandidateStatusFilter,
  candidateSiteId,
  setCandidateSiteId,
  candidateTrendDays,
  setCandidateTrendDays,
  candidateOrderBy,
  setCandidateOrderBy,
  candidateOrderDir,
  setCandidateOrderDir,
  loadCandidates,
  candidateLoading,
  candidateSourceDeviceId,
  setCandidateSourceDeviceId,
  candidateAutoRefresh,
  setCandidateAutoRefresh,
  selectedCandidateIds,
  setSelectedCandidateIds,
  candidates,
  setCandidates,
  candidateEdits,
  setCandidateEdits,
  candidateRecommendations,
  setCandidateRecommendations,
  candidateRecOpen,
  setCandidateRecOpen,
  candidateRecLoading,
  setCandidateRecLoading,
  candidateActionError,
  setCandidateActionError,
  candidateSummaryLoading,
  candidateSummary,
  candidateTrend,
  sites,
  toast,
  navigate,
}) => {
  const [actionableOnly, setActionableOnly] = React.useState(false);
  const [staleOnly, setStaleOnly] = React.useState(false);

  const fmt = (key, fallback, vars = {}) => {
    let out = String(t(key, fallback));
    Object.entries(vars).forEach(([k, v]) => {
      out = out.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v ?? ''));
    });
    return out;
  };

  const visibleCandidates = React.useMemo(
    () =>
      (candidates || []).filter((candidate) => {
        if (actionableOnly && !candidate?.actionable) return false;
        if (staleOnly && !candidate?.stale) return false;
        return true;
      }),
    [actionableOnly, candidates, staleOnly],
  );

  const selectableCandidates = React.useMemo(
    () => visibleCandidates.filter((candidate) => isBacklogCandidate(candidate)),
    [visibleCandidates],
  );

  const selectedVisibleCount = React.useMemo(
    () => selectableCandidates.filter((candidate) => selectedCandidateIds.includes(candidate.id)).length,
    [selectableCandidates, selectedCandidateIds],
  );

  const allVisibleSelected = selectableCandidates.length > 0 && selectedVisibleCount === selectableCandidates.length;
  const visibleHighPriorityCount = React.useMemo(
    () => visibleCandidates.filter((candidate) => ['critical', 'high'].includes(String(candidate?.priority_band || '').toLowerCase()) && isBacklogCandidate(candidate)).length,
    [visibleCandidates],
  );
  const visibleActionableCount = React.useMemo(
    () => visibleCandidates.filter((candidate) => candidate?.actionable && isBacklogCandidate(candidate)).length,
    [visibleCandidates],
  );

  const refreshQueue = async () => {
    await loadCandidates();
  };

  const syncCandidateState = (candidateId, patch) => {
    setCandidates((prev) => prev.map((item) => (item.id === candidateId ? { ...item, ...patch } : item)));
  };

  const fetchRecommendations = async (candidateId, { toggle = false } = {}) => {
    const isOpen = !!candidateRecOpen[candidateId];
    if (toggle && isOpen) {
      setCandidateRecOpen((prev) => ({ ...prev, [candidateId]: false }));
      return candidateRecommendations[candidateId] || [];
    }

    setCandidateRecOpen((prev) => ({ ...prev, [candidateId]: true }));
    if (candidateRecommendations[candidateId]?.length) {
      return candidateRecommendations[candidateId];
    }

    setCandidateRecLoading((prev) => ({ ...prev, [candidateId]: true }));
    try {
      const res = await TopologyService.getCandidateRecommendations(candidateId, { limit: 5 });
      const list = Array.isArray(res.data) ? res.data : [];
      setCandidateRecommendations((prev) => ({ ...prev, [candidateId]: list }));
      return list;
    } catch (e) {
      toast.error(`${t('topology_load_recommendations_failed')}: ${e.response?.data?.detail || e.message}`);
      setCandidateRecOpen((prev) => ({ ...prev, [candidateId]: false }));
      throw e;
    } finally {
      setCandidateRecLoading((prev) => ({ ...prev, [candidateId]: false }));
    }
  };

  const promoteCandidate = async (candidate, payloadOverride = {}) => {
    const payload = {
      job_id: candidateJobId ? parseInt(candidateJobId, 10) : (candidate.discovery_job_id ?? undefined),
      ip_address: (payloadOverride.ip_address ?? candidateEdits[candidate.id] ?? candidate.mgmt_ip ?? '').trim(),
      hostname: payloadOverride.hostname ?? candidate.neighbor_name,
    };

    const promoted = await TopologyService.promoteCandidate(candidate.id, payload);
    syncCandidateState(candidate.id, {
      status: payloadOverride.status || 'promoted',
      mgmt_ip: payload.ip_address,
      actionable: false,
      backlog: false,
    });

    if (payloadOverride.approveDiscovered && promoted?.data?.discovered_id) {
      await DiscoveryService.approveDevice(promoted.data.discovered_id);
      syncCandidateState(candidate.id, {
        status: 'approved',
        actionable: false,
        backlog: false,
      });
    }

    if (payload.job_id) {
      navigate('/discovery', { state: { jobId: payload.job_id } });
    }
    return promoted;
  };

  const applyRecommendation = async (candidate, recommendation) => {
    setCandidateActionError((prev) => ({ ...prev, [candidate.id]: '' }));
    try {
      const ip = String(recommendation?.ip_address || '').trim();
      if (!ip) return;
      setCandidateEdits((prev) => ({ ...prev, [candidate.id]: ip }));
      await promoteCandidate(candidate, {
        ip_address: ip,
        hostname: recommendation?.hostname || candidate.neighbor_name,
        approveDiscovered: true,
        status: 'approved',
      });
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || t('topology_promote_failed');
      setCandidateActionError((prev) => ({ ...prev, [candidate.id]: String(msg) }));
    }
  };

  const applyTopRecommendation = async (candidate) => {
    setCandidateActionError((prev) => ({ ...prev, [candidate.id]: '' }));
    try {
      const recommendations = candidateRecommendations[candidate.id]?.length
        ? candidateRecommendations[candidate.id]
        : await fetchRecommendations(candidate.id);
      const best = recommendations.find((item) => item?.action_ready) || recommendations[0];
      if (!best) {
        toast.warning(t('topology_no_suggestions', 'No suggestions'));
        return;
      }
      await applyRecommendation(candidate, best);
    } catch (e) {
      if (!e) {
        toast.error(t('topology_promote_failed'));
      }
    }
  };

  const toggleSelectVisible = () => {
    const visibleIds = selectableCandidates.map((candidate) => candidate.id);
    setSelectedCandidateIds((prev) => {
      const prevSet = new Set(prev);
      if (visibleIds.length > 0 && visibleIds.every((id) => prevSet.has(id))) {
        return prev.filter((id) => !visibleIds.includes(id));
      }
      visibleIds.forEach((id) => prevSet.add(id));
      return Array.from(prevSet);
    });
  };

  return (
    <Panel position="top-left" className="m-4">
      <div
        data-testid="candidate-panel"
        className="w-[min(620px,calc(100vw-2rem))] bg-[#1b1d1f] border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-4 animate-slide-in-right text-white"
      >
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-bold flex items-center gap-2">
            <Link2 size={18} className="text-amber-400" /> {t('topology_candidate_links_title')}
          </h3>
          <button onClick={() => setShowCandidates(false)}>
            <XCircle size={18} className="text-gray-500 hover:text-white" />
          </button>
        </div>

        <div className="flex flex-col xl:flex-row xl:items-center gap-2 mb-3">
          <input
            type="text"
            value={candidateJobId}
            onChange={(e) => setCandidateJobId(e.target.value)}
            placeholder={t('topology_filter_job_id_placeholder')}
            className="flex-1 bg-[#0e1012] border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-amber-500 outline-none font-mono"
          />
          <input
            type="text"
            value={candidateSearch}
            onChange={(e) => setCandidateSearch(e.target.value)}
            placeholder={t('topology_search_placeholder')}
            className="w-full xl:w-40 bg-[#0e1012] border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-amber-500 outline-none"
          />
          <select
            value={candidateStatusFilter}
            onChange={(e) => setCandidateStatusFilter(e.target.value)}
            className="w-full xl:w-auto bg-[#0e1012] border border-gray-700 rounded px-2 py-2 text-sm text-white outline-none"
          >
            <option value="all">{t('topology_status_all')}</option>
            <option value="low_confidence">{t('topology_status_low_confidence')}</option>
            <option value="unmatched">{t('topology_status_unmatched')}</option>
            <option value="promoted">{t('topology_status_promoted')}</option>
            <option value="ignored">{t('topology_status_ignored')}</option>
          </select>
          <select
            value={candidateSiteId}
            onChange={(e) => setCandidateSiteId(e.target.value)}
            className="w-full xl:w-auto bg-[#0e1012] border border-gray-700 rounded px-2 py-2 text-sm text-white outline-none"
          >
            <option value="">{t('topology_all_sites')}</option>
            {(sites || []).map((site) => (
              <option key={`cand-site-${site.id}`} value={String(site.id)}>{String(site.name || `Site ${site.id}`)}</option>
            ))}
          </select>
          <select
            value={String(candidateTrendDays)}
            onChange={(e) => setCandidateTrendDays(Number(e.target.value || 7))}
            className="w-full xl:w-auto bg-[#0e1012] border border-gray-700 rounded px-2 py-2 text-sm text-white outline-none"
            title={t('topology_trend_window')}
          >
            <option value="7">{t('topology_trend_7d')}</option>
            <option value="30">{t('topology_trend_30d')}</option>
          </select>
          <select
            value={`${candidateOrderBy}:${candidateOrderDir}`}
            onChange={(e) => {
              const [orderBy, orderDir] = e.target.value.split(':');
              setCandidateOrderBy(orderBy);
              setCandidateOrderDir(orderDir);
            }}
            className="w-full xl:w-auto bg-[#0e1012] border border-gray-700 rounded px-2 py-2 text-sm text-white outline-none"
          >
            <option value="priority:desc">{t('topology_order_priority_desc', 'Priority desc')}</option>
            <option value="priority:asc">{t('topology_order_priority_asc', 'Priority asc')}</option>
            <option value="last_seen:desc">{t('topology_order_last_seen_desc')}</option>
            <option value="last_seen:asc">{t('topology_order_last_seen_asc')}</option>
            <option value="confidence:desc">{t('topology_order_confidence_desc')}</option>
            <option value="confidence:asc">{t('topology_order_confidence_asc')}</option>
          </select>
          <button
            onClick={refreshQueue}
            disabled={candidateLoading}
            className="w-full xl:w-auto px-3 py-2 bg-amber-600 hover:bg-amber-500 rounded font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <RefreshCw size={14} className={candidateLoading ? 'animate-spin' : ''} />
            {t('common_refresh')}
          </button>
        </div>

        {!!candidateSourceDeviceId && (
          <div className="mb-3 flex items-center gap-2 text-xs">
            <span className="px-2 py-1 rounded bg-amber-700/30 text-amber-200 border border-amber-600">
              source_device_id = {candidateSourceDeviceId}
            </span>
            <button
              onClick={() => setCandidateSourceDeviceId('')}
              className="px-2 py-1 rounded bg-white/5 hover:bg-white/10 border border-gray-700 text-gray-200"
            >
              {t('common_clear')}
            </button>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 mb-3 text-xs">
          <label className="flex items-center gap-2 select-none text-gray-300">
            <input
              type="checkbox"
              checked={candidateAutoRefresh}
              onChange={(e) => setCandidateAutoRefresh(e.target.checked)}
            />
            {t('topology_auto_refresh')}
          </label>
          <button
            type="button"
            data-testid="candidate-filter-actionable"
            onClick={() => setActionableOnly((prev) => !prev)}
            className={`px-2 py-1 rounded border ${actionableOnly ? 'border-emerald-600 bg-emerald-900/25 text-emerald-200' : 'border-gray-700 bg-[#0e1012] text-gray-300'}`}
          >
            {t('topology_actionable_only', 'Actionable only')}
          </button>
          <button
            type="button"
            data-testid="candidate-filter-stale"
            onClick={() => setStaleOnly((prev) => !prev)}
            className={`px-2 py-1 rounded border ${staleOnly ? 'border-red-600 bg-red-900/25 text-red-200' : 'border-gray-700 bg-[#0e1012] text-gray-300'}`}
          >
            {t('topology_stale_only', 'Stale only')}
          </button>
          <div className="ml-auto text-gray-400">
            {fmt('topology_showing_candidates', 'showing {visible} / {total}', {
              visible: visibleCandidates.length,
              total: candidates.length,
            })}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3">
          <div className="rounded border border-amber-800/60 bg-amber-900/20 px-3 py-2">
            <div className="text-[10px] text-amber-200">{t('topology_backlog')}</div>
            <div className="text-sm font-bold text-amber-100">
              {candidateSummaryLoading ? '...' : Number(candidateSummary?.totals?.backlog_total || 0)}
            </div>
            <div className="text-[10px] text-amber-300">
              {fmt('topology_backlog_low_unmatched', 'low {low} / unmatched {unmatched}', {
                low: Number(candidateSummary?.totals?.backlog_low_confidence || 0),
                unmatched: Number(candidateSummary?.totals?.backlog_unmatched || 0),
              })}
            </div>
          </div>
          <div className="rounded border border-red-800/60 bg-red-900/20 px-3 py-2">
            <div className="text-[10px] text-red-200">{t('topology_high_priority_visible', 'High priority visible')}</div>
            <div className="text-sm font-bold text-red-100">{visibleHighPriorityCount}</div>
            <div className="text-[10px] text-red-300">
              {fmt('topology_actionable_count', 'actionable {count}', { count: visibleActionableCount })}
            </div>
          </div>
          <div className="rounded border border-emerald-800/60 bg-emerald-900/20 px-3 py-2">
            <div className="text-[10px] text-emerald-200">{t('topology_processed_24h')}</div>
            <div className="text-sm font-bold text-emerald-100">
              {candidateSummaryLoading ? '...' : Number(candidateSummary?.totals?.resolved_24h || 0)}
            </div>
            <div className="text-[10px] text-emerald-300">
              {fmt('topology_stale', 'stale {count}', { count: Number(candidateSummary?.totals?.stale_backlog_24h || 0) })}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-2 mb-3">
          <div className="rounded border border-gray-700 bg-black/20 px-2 py-2">
            <div className="text-[10px] text-gray-300 mb-1">{t('topology_daily_queue_trend')} ({candidateTrendDays}d)</div>
            {(candidateTrend?.series || []).slice(-7).map((day) => {
              const backlog = Number(day?.backlog_total || 0);
              const resolved = Number(day?.resolved_total || 0);
              const maxValue = Math.max(backlog, resolved, 1);
              return (
                <div key={`tr-${String(day?.date || '')}`} className="grid grid-cols-[52px_1fr_1fr] items-center gap-2 text-[10px] mb-1">
                  <div className="text-gray-500 font-mono">{String(day?.date || '').slice(5)}</div>
                  <div className="flex items-center gap-1">
                    <div className="h-1.5 rounded bg-amber-500/70" style={{ width: `${Math.max(4, Math.round((backlog / maxValue) * 100))}%` }} />
                    <span className="text-amber-300">B {backlog}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="h-1.5 rounded bg-emerald-500/70" style={{ width: `${Math.max(4, Math.round((resolved / maxValue) * 100))}%` }} />
                    <span className="text-emerald-300">R {resolved}</span>
                  </div>
                </div>
              );
            })}
            {(!candidateTrend?.series || candidateTrend.series.length === 0) && (
              <div className="text-[10px] text-gray-500">{candidateSummaryLoading ? t('common_loading') : t('topology_trend_none')}</div>
            )}
          </div>

          <div className="rounded border border-gray-700 bg-black/20 px-2 py-2">
            <div className="text-[10px] text-gray-300 mb-1">{t('topology_top_jobs_by_queue')}</div>
            {(candidateTrend?.jobs || []).slice(0, 5).map((job) => (
              <div key={`tj-${job?.job_id}`} className="grid grid-cols-[58px_1fr_1fr] items-center gap-2 text-[10px] mb-1">
                <button
                  onClick={() => {
                    setCandidateJobId(String(job?.job_id || ''));
                    setCandidateStatusFilter('low_confidence');
                  }}
                  className="text-left font-mono text-blue-300 hover:text-blue-200 hover:underline"
                >
                  #{job?.job_id}
                </button>
                <div className="text-amber-300">{t('topology_backlog')} {Number(job?.backlog_total || 0)}</div>
                <div className="text-emerald-300">{t('topology_resolved')} {Number(job?.resolved_total || 0)}</div>
              </div>
            ))}
            {(!candidateTrend?.jobs || candidateTrend.jobs.length === 0) && (
              <div className="text-[10px] text-gray-500">{candidateSummaryLoading ? t('common_loading') : t('topology_job_data_none')}</div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between mb-3 text-xs text-gray-300">
          <div className="flex items-center gap-2">
            <button
              disabled={selectedCandidateIds.length === 0}
              onClick={async () => {
                try {
                  const jobId = candidateJobId ? parseInt(candidateJobId, 10) : null;
                  if (!jobId) {
                    toast.warning(t('topology_job_id_required_bulk_promote'));
                    return;
                  }
                  const items = selectedCandidateIds.map((id) => {
                    const candidate = candidates.find((item) => item.id === id);
                    return {
                      candidate_id: id,
                      ip_address: (candidateEdits[id] ?? candidate?.mgmt_ip ?? '').trim(),
                      hostname: candidate?.neighbor_name,
                    };
                  });
                  await TopologyService.bulkPromoteCandidates(jobId, items);
                  setCandidates((prev) =>
                    prev.map((item) => (selectedCandidateIds.includes(item.id)
                      ? { ...item, status: 'promoted', mgmt_ip: (candidateEdits[item.id] ?? item.mgmt_ip), actionable: false, backlog: false }
                      : item)),
                  );
                  navigate('/discovery', { state: { jobId } });
                } catch (e) {
                  toast.error(`${t('topology_bulk_promote_failed')}: ${e.response?.data?.detail || e.message}`);
                }
              }}
              className="px-2 py-1 bg-green-600 hover:bg-green-500 rounded font-bold disabled:opacity-50"
            >
              {t('topology_promote_selected')} ({selectedCandidateIds.length})
            </button>
            <button
              disabled={selectedCandidateIds.length === 0}
              onClick={async () => {
                try {
                  await TopologyService.bulkIgnoreCandidates(selectedCandidateIds);
                  setCandidates((prev) =>
                    prev.map((item) => (selectedCandidateIds.includes(item.id)
                      ? { ...item, status: 'ignored', actionable: false, backlog: false }
                      : item)),
                  );
                  setSelectedCandidateIds([]);
                  await refreshQueue();
                } catch (e) {
                  toast.error(t('topology_bulk_ignore_failed'));
                }
              }}
              className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded font-bold disabled:opacity-50"
            >
              {t('topology_ignore_selected')}
            </button>
            <button
              onClick={toggleSelectVisible}
              className="px-2 py-1 bg-[#0e1012] border border-gray-700 rounded font-bold"
            >
              {allVisibleSelected ? t('common_clear') : t('topology_select_all')}
            </button>
          </div>
          <div className="text-gray-400">
            {fmt('topology_selected_visible_fmt', '{selected} selected / {visible} visible', {
              selected: selectedVisibleCount,
              visible: selectableCandidates.length,
            })}
          </div>
        </div>

        <div className="max-h-[460px] overflow-y-auto border border-gray-700 rounded-lg bg-black/10">
          {visibleCandidates.length === 0 && !candidateLoading && (
            <div className="p-4 text-sm text-gray-400">{t('topology_no_candidates')}</div>
          )}

          {visibleCandidates.map((candidate) => {
            const rowStatus = normalizeStatus(candidate.status);
            const isBacklog = isBacklogCandidate(candidate);
            const isResolved = RESOLVED_STATUSES.has(rowStatus);
            const reasonLabel = candidate?.reason_meta?.label || candidate?.reason || t('topology_status_unmatched');
            const nextAction = candidate?.next_action?.label || t('topology_review_candidate', 'Review candidate');

            return (
              <div
                key={candidate.id}
                data-testid={`candidate-row-${candidate.id}`}
                className="p-3 border-b border-gray-800 last:border-b-0 hover:bg-white/[0.02]"
              >
                <div className="flex gap-3 items-start">
                  <div className="pt-1">
                    <input
                      type="checkbox"
                      checked={selectedCandidateIds.includes(candidate.id)}
                      disabled={!isBacklog}
                      onChange={(e) => {
                        setSelectedCandidateIds((prev) => {
                          if (e.target.checked) return Array.from(new Set([...prev, candidate.id]));
                          return prev.filter((id) => id !== candidate.id);
                        });
                      }}
                    />
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <div className="text-sm font-bold text-gray-100 truncate">{candidate.neighbor_name || t('topology_unknown_neighbor', 'Unknown neighbor')}</div>
                      <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide ${priorityTone(candidate.priority_band)}`}>
                        {candidate.priority_band || 'low'} {Number(candidate.priority_score || 0).toFixed(0)}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide ${statusTone(candidate.status)}`}>
                        {rowStatus || t('topology_status_unmatched')}
                      </span>
                      {candidate.stale && (
                        <span className="px-2 py-0.5 rounded-full border border-red-700 bg-red-900/20 text-[10px] font-semibold text-red-200 flex items-center gap-1">
                          <Clock3 size={11} /> {t('topology_stale', 'Stale')}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap gap-2 text-[11px] text-gray-300 mb-2">
                      <span className="px-2 py-1 rounded bg-white/5 border border-gray-700">
                        {fmt('topology_source_device_fmt', 'source {name}', {
                          name: candidate.source_device_name || candidate.source_device_id || '-',
                        })}
                      </span>
                      <span className="px-2 py-1 rounded bg-white/5 border border-gray-700">
                        {candidate.site_name || t('topology_site_unknown', 'No site')}
                      </span>
                      <span className="px-2 py-1 rounded bg-white/5 border border-gray-700 font-mono">
                        {candidate.protocol || 'UNKNOWN'}
                      </span>
                    </div>

                    <div className="text-xs text-gray-400 mb-1">
                      {fmt('topology_source_link_fmt', 'src:{src} {local} -> {remote} ({protocol})', {
                        src: candidate.source_device_ip || candidate.source_device_id,
                        local: candidate.local_interface || '-',
                        remote: candidate.remote_interface || '-',
                        protocol: candidate.protocol || 'UNKNOWN',
                      })}
                    </div>

                    <div className="text-xs text-gray-300 flex flex-wrap items-center gap-2 mb-1">
                      <span className="inline-flex items-center gap-1">
                        <AlertTriangle size={12} className="text-amber-400" /> {reasonLabel}
                      </span>
                      <span className="text-gray-500">conf {Number(candidate.confidence || 0).toFixed(2)}</span>
                      <span className="text-gray-500">{formatRelativeAge(candidate.age_seconds)}</span>
                    </div>

                    <div className="text-[11px] text-sky-300 flex flex-wrap items-center gap-2">
                      <Target size={12} /> {nextAction}
                      {candidate.reason_meta?.candidate_ids?.length > 0 && (
                        <span className="text-gray-500">
                          {fmt('topology_ambiguous_ids', 'ids {ids}', {
                            ids: candidate.reason_meta.candidate_ids.join(','),
                          })}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="w-[240px] shrink-0 flex flex-col gap-2">
                    <input
                      type="text"
                      value={candidateEdits[candidate.id] ?? candidate.mgmt_ip ?? ''}
                      onChange={(e) => setCandidateEdits((prev) => ({ ...prev, [candidate.id]: e.target.value }))}
                      placeholder={t('topology_mgmt_ip_placeholder')}
                      className="w-full bg-[#0e1012] border border-gray-700 rounded px-2 py-1.5 text-xs text-white focus:border-amber-500 outline-none font-mono"
                    />

                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={() => fetchRecommendations(candidate.id, { toggle: true })}
                        disabled={isResolved}
                        className="px-2 py-1.5 bg-[#0e1012] border border-gray-700 hover:border-amber-500 rounded text-xs font-bold disabled:opacity-40"
                        title={t('topology_load_recommendations_title')}
                      >
                        {candidateRecLoading[candidate.id] ? '...' : t('topology_suggest')}
                      </button>
                      <button
                        type="button"
                        data-testid={`candidate-use-top-${candidate.id}`}
                        onClick={() => applyTopRecommendation(candidate)}
                        disabled={isResolved || !candidate.actionable}
                        className="px-2 py-1.5 bg-sky-700 hover:bg-sky-600 rounded text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-40"
                      >
                        <Sparkles size={12} /> {t('topology_use_top', 'Use Top')}
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={async () => {
                          try {
                            await promoteCandidate(candidate);
                          } catch (e) {
                            toast.error(`${t('topology_promote_failed')}: ${e.response?.data?.detail || e.message}`);
                          }
                        }}
                        disabled={isResolved}
                        className="px-2 py-1.5 bg-green-600 hover:bg-green-500 rounded text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-40"
                      >
                        <CheckCircle size={12} /> {t('common_promote')}
                      </button>
                      <button
                        onClick={async () => {
                          try {
                            await TopologyService.ignoreCandidate(candidate.id);
                            syncCandidateState(candidate.id, {
                              status: 'ignored',
                              actionable: false,
                              backlog: false,
                            });
                            await refreshQueue();
                          } catch (e) {
                            toast.error(t('topology_ignore_failed'));
                          }
                        }}
                        disabled={isResolved}
                        className="px-2 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs font-bold disabled:opacity-40"
                      >
                        {t('common_ignore')}
                      </button>
                    </div>

                    <div className="text-[11px] text-gray-500">
                      {candidate.mgmt_ip ? candidate.mgmt_ip : t('topology_mgmt_ip_missing', 'Mgmt IP missing')}
                      {' / '}
                      {formatTimestamp(candidate.last_seen)}
                    </div>

                    {candidateRecOpen[candidate.id] && (
                      <div className="flex flex-col gap-1">
                        {(candidateRecommendations[candidate.id]?.length ?? 0) === 0 ? (
                          <div className="text-[11px] text-gray-500 text-right">{t('topology_no_suggestions')}</div>
                        ) : (
                          candidateRecommendations[candidate.id].map((recommendation) => (
                            <button
                              key={recommendation.discovered_id}
                              onClick={() => applyRecommendation(candidate, recommendation)}
                              className="text-left px-2 py-1.5 bg-[#0e1012] border border-gray-700 rounded hover:border-amber-500"
                              title={t('topology_fill_mgmt_ip_promote')}
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="min-w-0">
                                  <div className="text-[11px] text-gray-300 truncate">{recommendation.hostname || recommendation.ip_address}</div>
                                  <div className="text-[10px] text-gray-500 font-mono truncate">
                                    {recommendation.ip_address} / {recommendation.vendor || t('topology_vendor_unknown')} / {t('topology_score')} {Number(recommendation.score || 0).toFixed(2)}
                                  </div>
                                </div>
                                <div className="flex flex-col items-end gap-1">
                                  <div className="text-[10px] text-amber-400 font-bold">{t('topology_use')}</div>
                                  <div className={`px-1.5 py-0.5 rounded border text-[9px] uppercase ${recommendation.action_ready ? 'border-emerald-700 bg-emerald-900/25 text-emerald-200' : 'border-gray-700 bg-black/20 text-gray-300'}`}>
                                    {recommendation.match_band || 'low'}
                                  </div>
                                </div>
                              </div>
                            </button>
                          ))
                        )}
                      </div>
                    )}

                    {!!candidateActionError[candidate.id] && (
                      <div className="text-[11px] text-red-400 text-right break-words">
                        {candidateActionError[candidate.id]}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Panel>
  );
};

export default CandidatePanel;
