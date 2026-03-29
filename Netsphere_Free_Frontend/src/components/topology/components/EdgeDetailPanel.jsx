import React from 'react';
import { Panel } from 'reactflow';
import { Link2, XCircle, RefreshCw } from 'lucide-react';
import { t } from '../../../i18n';

const EdgeDetailPanel = ({
  edgeDetailPanel,
  setEdgeDetailPanel,
  setEdgeEventDiff,
  setShowCandidates,
  setCandidateStatusFilter,
  setCandidateSourceDeviceId,
  setCandidateSearch,
  edgeEventWindowMin,
  setEdgeEventWindowMin,
  edgeEventStateFilter,
  setEdgeEventStateFilter,
  fetchLinkEvents,
  filteredEdgeEvents,
  onEdgeEventClick,
  edgeEventDiff,
  relatedSnapshotDiff,
  onRelatedDiffClick,
}) => {
  if (!(edgeDetailPanel?.open && edgeDetailPanel?.edge)) return null;

  return (
    <Panel position="top-right" className="m-4">
      <div className="w-[min(36rem,calc(100vw-2rem))] bg-[#1b1d1f] border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-4 text-white">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-bold flex items-center gap-2">
            <Link2 size={18} className="text-amber-400" /> {t('topology_link_evidence', 'Link Evidence')}
          </h3>
          <button onClick={() => {
            setEdgeDetailPanel({ open: false, edge: null, events: [], loading: false, error: '' });
            setEdgeEventDiff({ loading: false, error: '', data: null, eventId: null });
          }}>
            <XCircle size={18} className="text-gray-500 hover:text-white" />
          </button>
        </div>
        {(() => {
          const e = edgeDetailPanel.edge;
          const d = e?.data || {};
          const l3 = d?.l3 && typeof d.l3 === 'object' ? d.l3 : null;
          const overlay = d?.overlay && typeof d.overlay === 'object' ? d.overlay : null;
          const c = Number(d.confidence || 0);
          const q = String(d.quality || (c >= 0.9 ? 'high' : (c >= 0.7 ? 'medium' : 'low'))).toLowerCase();
          const qualityClass = q === 'high' ? 'bg-emerald-700/40 text-emerald-200' : (q === 'medium' ? 'bg-sky-700/40 text-sky-200' : 'bg-amber-700/40 text-amber-200');
          return (
            <div className="space-y-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="px-2 py-0.5 rounded-full bg-gray-800 text-gray-200 text-xs font-bold">{String(d.protocol || 'UNKNOWN').toUpperCase()}</span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${qualityClass}`}>{q}</span>
                <span className="px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 text-xs">{t('topology_confidence', 'confidence')} {Number.isFinite(c) ? c.toFixed(2) : '0.00'}</span>
                {!!d.discovery_source && <span className="px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 text-xs">{t('topology_source_short', 'src')}: {String(d.discovery_source)}</span>}
                {q === 'low' && (
                  <button
                    onClick={() => {
                      setShowCandidates(true);
                      setCandidateStatusFilter('unmatched');
                      setCandidateSourceDeviceId(String(e?.source || ''));
                      setCandidateSearch('');
                    }}
                    className="px-2 py-0.5 rounded bg-amber-700/40 hover:bg-amber-600/50 border border-amber-500 text-amber-100 text-xs font-bold"
                  >
                    {t('topology_jump_candidates', 'Jump Candidates')}
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 gap-1 text-gray-200">
                <div><span className="text-gray-400">{t('topology_from', 'From')}:</span> {String(e.source)} {d?.path?.fromPort ? `(${d.path.fromPort})` : ''}</div>
                <div><span className="text-gray-400">{t('topology_to', 'To')}:</span> {String(e.target)} {d?.path?.toPort ? `(${d.path.toPort})` : ''}</div>
              </div>
              {l3 && (
                <div className="grid grid-cols-1 gap-1 rounded-lg border border-gray-800 bg-black/20 p-3 text-xs text-gray-200">
                  {String(l3.protocol || '').toUpperCase() === 'BGP' && (
                    <>
                      {!!l3.relationship && <div><span className="text-gray-400">BGP:</span> {String(l3.relationship).toUpperCase()}</div>}
                      {!!l3.state && <div><span className="text-gray-400">Session:</span> {String(l3.state).toUpperCase()}</div>}
                      {(l3?.source?.local_as != null || l3?.target?.local_as != null) && (
                        <div><span className="text-gray-400">ASN:</span> {l3?.source?.local_as != null ? `AS${l3.source.local_as}` : 'AS?'} {' <-> '} {l3?.target?.local_as != null ? `AS${l3.target.local_as}` : 'AS?'}</div>
                      )}
                      {!!l3?.source?.neighbor_ip && <div><span className="text-gray-400">Source Peer:</span> {String(l3.source.neighbor_ip)}</div>}
                      {!!l3?.target?.neighbor_ip && <div><span className="text-gray-400">Target Peer:</span> {String(l3.target.neighbor_ip)}</div>}
                      {l3?.prefixes_received != null && <div><span className="text-gray-400">Prefixes:</span> {Number(l3.prefixes_received)}</div>}
                      {!!l3?.uptime && <div><span className="text-gray-400">Uptime:</span> {String(l3.uptime)}</div>}
                    </>
                  )}
                  {String(l3.protocol || '').toUpperCase() === 'OSPF' && (
                    <>
                      {!!l3.state && <div><span className="text-gray-400">Adjacency:</span> {String(l3.state).toUpperCase()}</div>}
                      {!!l3.area && <div><span className="text-gray-400">Area:</span> {String(l3.area)}</div>}
                      {!!l3?.source?.interface && <div><span className="text-gray-400">Source IF:</span> {String(l3.source.interface)}</div>}
                      {!!l3?.target?.interface && <div><span className="text-gray-400">Target IF:</span> {String(l3.target.interface)}</div>}
                      {!!l3?.source?.neighbor_id && <div><span className="text-gray-400">Source RID:</span> {String(l3.source.neighbor_id)}</div>}
                      {!!l3?.target?.neighbor_id && <div><span className="text-gray-400">Target RID:</span> {String(l3.target.neighbor_id)}</div>}
                    </>
                  )}
                </div>
              )}
              {overlay && (
                <div className="grid grid-cols-1 gap-1 rounded-lg border border-cyan-900/60 bg-cyan-950/10 p-3 text-xs text-cyan-50">
                  {!!overlay.transport && <div><span className="text-cyan-300/80">Overlay:</span> {String(overlay.transport).toUpperCase().replace(/_/g, ' ')}</div>}
                  {!!overlay.state && <div><span className="text-cyan-300/80">Tunnel:</span> {String(overlay.state).toUpperCase()}</div>}
                  {(overlay?.source?.local_vtep_ip || overlay?.target?.local_vtep_ip) && (
                    <div><span className="text-cyan-300/80">VTEP:</span> {String(overlay?.source?.local_vtep_ip || '?')} {' <-> '} {String(overlay?.target?.local_vtep_ip || '?')}</div>
                  )}
                  {(overlay?.source?.nve_interface || overlay?.target?.nve_interface) && (
                    <div><span className="text-cyan-300/80">NVE:</span> {String(overlay?.source?.nve_interface || '?')} {' <-> '} {String(overlay?.target?.nve_interface || '?')}</div>
                  )}
                  {Number.isFinite(Number(overlay?.vni_count)) && Number(overlay.vni_count) > 0 && (
                    <div><span className="text-cyan-300/80">VNIs:</span> {Number(overlay.vni_count)}</div>
                  )}
                  {Array.isArray(overlay?.vnis) && overlay.vnis.length > 0 && (
                    <div>
                      <span className="text-cyan-300/80">VNI List:</span>{' '}
                      {overlay.vnis.slice(0, 8).map((row) => {
                        const type = String(row?.type || '').trim().toLowerCase() === 'l3' ? 'L3' : 'L2';
                        return `VNI${row?.vni}(${type})`;
                      }).join(', ')}
                      {overlay.vnis.length > 8 ? ` +${overlay.vnis.length - 8}` : ''}
                    </div>
                  )}
                  {overlay?.evpn && (
                    <>
                      {!!overlay?.evpn?.relationship && <div><span className="text-cyan-300/80">EVPN:</span> {String(overlay.evpn.relationship).toUpperCase()}</div>}
                      {(overlay?.evpn?.source_as != null || overlay?.evpn?.target_as != null) && (
                        <div><span className="text-cyan-300/80">ASN:</span> {overlay?.evpn?.source_as != null ? `AS${overlay.evpn.source_as}` : 'AS?'} {' <-> '} {overlay?.evpn?.target_as != null ? `AS${overlay.evpn.target_as}` : 'AS?'}</div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })()}
        <div className="mt-4 text-xs text-gray-300 font-bold">{t('topology_recent_changes', 'Recent Changes')}</div>
        <div className="mt-2 mb-2 flex items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <select
              value={String(edgeEventWindowMin)}
              onChange={(e) => setEdgeEventWindowMin(Number(e.target.value || 15))}
              className="px-2 py-1 text-[11px] rounded border border-gray-700 bg-white/5 text-gray-200 outline-none"
              title={t('topology_recent_window', 'Recent window')}
            >
              <option value="5">5m</option>
              <option value="15">15m</option>
              <option value="60">60m</option>
            </select>
            {['all', 'active', 'degraded', 'down'].map((s) => (
              <button
                key={s}
                onClick={() => setEdgeEventStateFilter(s)}
                className={`px-2 py-1 text-[11px] rounded border ${edgeEventStateFilter === s ? 'bg-amber-600/40 border-amber-500 text-amber-100' : 'bg-white/5 border-gray-700 text-gray-300 hover:bg-white/10'}`}
              >
                {s}
              </button>
            ))}
          </div>
          <button
            onClick={async () => {
              const edge = edgeDetailPanel?.edge;
              if (!edge) return;
              setEdgeDetailPanel((prev) => ({ ...prev, loading: true, error: '' }));
              try {
                const events = await fetchLinkEvents(edge, 30);
                setEdgeDetailPanel((prev) => ({ ...prev, events, loading: false, error: '' }));
              } catch (e) {
                 setEdgeDetailPanel((prev) => ({ ...prev, loading: false, error: e?.response?.data?.detail || e?.message || t('topology_load_link_events_failed', 'Failed to load link events') }));
              }
            }}
            className="px-2 py-1 text-[11px] rounded bg-white/5 hover:bg-white/10 border border-gray-700 text-gray-200 flex items-center gap-1"
          >
            <RefreshCw size={12} /> {t('common_refresh', 'Refresh')}
          </button>
        </div>
        {edgeDetailPanel.loading ? (
          <div className="mt-2 text-sm text-gray-400">{t('common_loading', 'Loading...')}</div>
        ) : edgeDetailPanel.error ? (
          <div className="mt-2 text-sm text-red-400">{edgeDetailPanel.error}</div>
        ) : filteredEdgeEvents.length === 0 ? (
          <div className="mt-2 text-sm text-gray-500">{t('topology_no_recent_change_events', 'No recent change events for this link.')}</div>
        ) : (
          <div className="mt-2 max-h-64 overflow-y-auto border border-gray-800 rounded-lg divide-y divide-gray-800">
            {filteredEdgeEvents.map((ev) => {
              const p = ev?.payload || {};
              const ts = ev?.created_at ? new Date(ev.created_at).toLocaleString() : '-';
              const st = String(p.state || '').toLowerCase();
              const stateClass = st === 'active'
                ? 'text-emerald-300'
                : st === 'degraded'
                  ? 'text-amber-300'
                  : 'text-red-300';
              return (
                <button
                  key={String(ev.id)}
                  onClick={() => onEdgeEventClick(ev)}
                  className="w-full text-left px-3 py-2 text-xs hover:bg-white/5 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className={`font-bold ${stateClass}`}>{String(p.state || 'unknown').toUpperCase()} {String(p.protocol || '').toUpperCase()}</div>
                    <div className="text-gray-500">{ts}</div>
                  </div>
                  <div className="mt-1 text-gray-400">
                    {String(p.device_id ?? '?')}:{String(p.local_interface || '?')}{' -> '}{String(p.neighbor_device_id ?? '?')}:{String(p.remote_interface || '?')}
                  </div>
                </button>
              );
            })}
          </div>
        )}
        <div className="mt-4 text-xs text-gray-300 font-bold">{t('topology_snapshot_diff_event', 'Snapshot Diff @ Event')}</div>
        {edgeEventDiff.loading ? (
          <div className="mt-2 text-sm text-gray-400">{t('topology_loading_snapshot_diff', 'Loading snapshot diff...')}</div>
        ) : edgeEventDiff.error ? (
          <div className="mt-2 text-sm text-red-400">{edgeEventDiff.error}</div>
        ) : edgeEventDiff.data ? (
          <div className="mt-2 text-xs border border-gray-800 rounded-lg p-3 bg-black/20">
            <div className="text-gray-300 mb-1">
              #{edgeEventDiff.data?.snapshot_a?.id} ({edgeEventDiff.data?.snapshot_a?.created_at || '-'}){' -> '}#{edgeEventDiff.data?.snapshot_b?.id} ({edgeEventDiff.data?.snapshot_b?.created_at || '-'})
            </div>
            <div className="flex items-center gap-2 text-gray-200">
              <span className="px-2 py-0.5 rounded bg-emerald-700/30 text-emerald-200">{t('common_added', 'added')} {Number(edgeEventDiff.data?.counts?.added || 0)}</span>
              <span className="px-2 py-0.5 rounded bg-red-700/30 text-red-200">{t('common_removed', 'removed')} {Number(edgeEventDiff.data?.counts?.removed || 0)}</span>
              <span className="px-2 py-0.5 rounded bg-amber-700/30 text-amber-200">{t('common_changed', 'changed')} {Number(edgeEventDiff.data?.counts?.changed || 0)}</span>
            </div>
            <div className="mt-2 flex items-center gap-2 text-gray-200">
              <span className="px-2 py-0.5 rounded bg-emerald-900/30 text-emerald-200">related+ {relatedSnapshotDiff.added.length}</span>
              <span className="px-2 py-0.5 rounded bg-red-900/30 text-red-200">related- {relatedSnapshotDiff.removed.length}</span>
              <span className="px-2 py-0.5 rounded bg-amber-900/30 text-amber-200">related~ {relatedSnapshotDiff.changed.length}</span>
            </div>
            {(relatedSnapshotDiff.added.length > 0 || relatedSnapshotDiff.removed.length > 0 || relatedSnapshotDiff.changed.length > 0) && (
              <div className="mt-2 border border-gray-800 rounded p-2 bg-black/30 space-y-2">
                {relatedSnapshotDiff.changed.slice(0, 3).map((c, idx) => (
                  <button key={`chg-${idx}`} onClick={() => onRelatedDiffClick(c)} className="w-full text-left text-[11px] text-amber-200 hover:bg-white/5 rounded px-1 py-0.5">
                    CHANGED {String(c?.before?.source || '?')}:{String(c?.before?.src_port || '?')}{' -> '}{String(c?.before?.target || '?')}:{String(c?.before?.dst_port || '?')} [{String(c?.before?.protocol || c?.after?.protocol || 'LLDP').toUpperCase()}] {String(c?.before?.status || '?')}{' -> '}{String(c?.after?.status || '?')}
                  </button>
                ))}
                {relatedSnapshotDiff.added.slice(0, 3).map((l, idx) => (
                  <button key={`add-${idx}`} onClick={() => onRelatedDiffClick(l)} className="w-full text-left text-[11px] text-emerald-200 hover:bg-white/5 rounded px-1 py-0.5">
                    ADDED {String(l?.source || '?')}:{String(l?.src_port || '?')}{' -> '}{String(l?.target || '?')}:{String(l?.dst_port || '?')} [{String(l?.protocol || 'LLDP').toUpperCase()}]
                  </button>
                ))}
                {relatedSnapshotDiff.removed.slice(0, 3).map((l, idx) => (
                  <button key={`rm-${idx}`} onClick={() => onRelatedDiffClick(l)} className="w-full text-left text-[11px] text-red-200 hover:bg-white/5 rounded px-1 py-0.5">
                    REMOVED {String(l?.source || '?')}:{String(l?.src_port || '?')}{' -> '}{String(l?.target || '?')}:{String(l?.dst_port || '?')} [{String(l?.protocol || 'LLDP').toUpperCase()}]
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="mt-2 text-sm text-gray-500">{t('topology_click_event_for_diff', 'Click an event row to auto-open snapshot diff.')}</div>
        )}
      </div>
    </Panel>
  );
};

export default EdgeDetailPanel;
