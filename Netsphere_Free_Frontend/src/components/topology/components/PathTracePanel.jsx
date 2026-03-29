import React from 'react';
import { Panel } from 'reactflow';
import { Route, XCircle, RefreshCw, Play, Pause, AlertCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { t } from '../../../i18n';

const PathTracePanel = ({
  setShowPathTrace,
  srcIp,
  setSrcIp,
  dstIp,
  setDstIp,
  handleTrace,
  tracing,
  pathResult,
  clearTrace,
  pathPlayback,
  setPathPlayback,
  setPathActiveEdgeIndex,
  pathPlaybackSpeed,
  setPathPlaybackSpeed,
  pathBadgesEnabled,
  setPathBadgesEnabled,
  pathEdgeLabelMaxLen,
  setPathEdgeLabelMaxLen,
  pathEdgeLabelTruncateMode,
  setPathEdgeLabelTruncateMode,
  pathEvidenceOpen,
  setPathEvidenceOpen,
  buildEvidenceParts,
  pathActiveEdgeIndex,
}) => {
  const summary = pathResult?.summary && typeof pathResult.summary === 'object' ? pathResult.summary : null;
  const summaryHealth = String(summary?.health || '').trim().toLowerCase();
  const summaryConfidence = Number.isFinite(Number(summary?.confidence_avg))
    ? Number(summary.confidence_avg).toFixed(2)
    : 'n/a';
  const summaryWarnings = Array.isArray(summary?.warnings) ? summary.warnings.filter(Boolean) : [];
  const headerTone = summaryHealth === 'broken'
    ? 'text-red-400'
    : (summaryHealth === 'degraded' || summaryHealth === 'at_risk')
      ? 'text-yellow-400'
      : 'text-green-400';

  return (
    <Panel position="top-right" className="m-4">
      <div data-testid="path-trace-panel" className="w-80 bg-[#1b1d1f] border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-4 animate-slide-in-right text-white">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-bold flex items-center gap-2"><Route size={18} className="text-indigo-400" /> {t('topology_path_trace', 'Path Trace')}</h3>
          <button onClick={() => setShowPathTrace(false)}><XCircle size={18} className="text-gray-500 hover:text-white" /></button>
        </div>

        <div className="space-y-3 mb-4">
          <div>
            <label className="text-xs text-gray-400 block mb-1">{t('diagnosis_source_ip', 'Source IP')}</label>
            <input
              data-testid="path-trace-src-input"
              type="text"
              value={srcIp}
              onChange={(e) => setSrcIp(e.target.value)}
              placeholder={t('path_trace_src_placeholder', 'e.g. 192.168.10.100')}
              className="w-full bg-[#0e1012] border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">{t('diagnosis_destination_ip', 'Destination IP')}</label>
            <input
              data-testid="path-trace-dst-input"
              type="text"
              value={dstIp}
              onChange={(e) => setDstIp(e.target.value)}
              placeholder={t('path_trace_dst_placeholder', 'e.g. 10.20.30.50')}
              className="w-full bg-[#0e1012] border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none font-mono"
            />
          </div>

          <div className="flex gap-2">
            <button
              data-testid="path-trace-run"
              onClick={handleTrace}
              disabled={tracing || !srcIp || !dstIp}
              className="flex-1 bg-indigo-600 hover:bg-indigo-500 text-white py-2 rounded font-bold text-sm flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
            >
              {tracing ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} fill="currentColor" />}
              {t('topology_path_trace', 'Path Trace')}
            </button>
            {pathResult && (
              <button onClick={clearTrace} className="px-3 bg-gray-700 hover:bg-gray-600 rounded text-white">
                {t('common_clear', 'Clear')}
              </button>
            )}
          </div>
        </div>

        {pathResult && (
          <div className="border-t border-gray-700 pt-3">
            {pathResult.status === 'success' && summaryHealth !== 'broken' && summaryHealth !== 'degraded' && summaryHealth !== 'at_risk' ? (
              <div className={`${headerTone} text-sm font-bold flex items-center gap-2 mb-2`}>
                <AlertCircle size={14} /> {t('path_trace_found_fmt', 'Path Found ({value} Hops)').replace('{value}', String(pathResult.path.length))}
              </div>
            ) : (
              <div className={`${headerTone} text-sm font-bold flex items-center gap-2 mb-2`}>
                <AlertCircle size={14} /> {pathResult.status === 'success'
                  ? `Path Found (${String(pathResult.path.length)} Hops, ${summaryHealth || 'at risk'})`
                  : (pathResult.message || t('path_trace_incomplete', 'Path Incomplete'))}
              </div>
            )}

            {summary && (
              <div data-testid="path-trace-summary" className="mb-3 grid grid-cols-2 gap-2 text-[11px]">
                <div className="rounded-lg border border-gray-700 bg-[#111315] px-3 py-2">
                  <div className="text-gray-500 uppercase tracking-wide">Mode</div>
                  <div data-testid="path-trace-summary-mode" className="mt-1 font-bold text-gray-100 break-all">{String(summary.mode || pathResult.mode || 'unknown')}</div>
                </div>
                <div className="rounded-lg border border-gray-700 bg-[#111315] px-3 py-2">
                  <div className="text-gray-500 uppercase tracking-wide">Health</div>
                  <div data-testid="path-trace-summary-health" className={`mt-1 font-bold uppercase ${headerTone}`}>{summaryHealth || 'unknown'}</div>
                </div>
                <div className="rounded-lg border border-gray-700 bg-[#111315] px-3 py-2">
                  <div className="text-gray-500 uppercase tracking-wide">Segments</div>
                  <div data-testid="path-trace-summary-segments" className="mt-1 font-bold text-gray-100">{String(summary.segment_count ?? Math.max(0, (pathResult.path?.length || 1) - 1))}</div>
                </div>
                <div className="rounded-lg border border-gray-700 bg-[#111315] px-3 py-2">
                  <div className="text-gray-500 uppercase tracking-wide">Confidence</div>
                  <div data-testid="path-trace-summary-confidence" className="mt-1 font-bold text-gray-100">{summaryConfidence}</div>
                </div>
              </div>
            )}

            {(pathResult.message || summaryWarnings.length > 0) && (
              <div data-testid="path-trace-warning-list" className="mb-3 space-y-1">
                {pathResult.message && (
                  <div className="rounded-lg border border-amber-700/50 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
                    {String(pathResult.message)}
                  </div>
                )}
                {summaryWarnings.slice(0, 3).map((warning, idx) => (
                  <div key={idx} className="rounded-lg border border-gray-700 bg-black/20 px-3 py-2 text-[11px] text-gray-300">
                    {String(warning)}
                  </div>
                ))}
              </div>
            )}

            {pathResult?.path?.length > 1 && (
              <div className="flex gap-2 mb-2">
                <button
                  onClick={() => {
                    const next = !pathPlayback;
                    setPathPlayback(next);
                    if (next) setPathActiveEdgeIndex((i) => (i == null ? 0 : i));
                  }}
                  className="flex-1 px-3 py-2 bg-emerald-700 hover:bg-emerald-600 rounded text-white text-xs font-bold flex items-center justify-center gap-2"
                >
                  {pathPlayback ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
                  {pathPlayback ? t('common_pause', 'Pause') : t('common_play', 'Play')}
                </button>
                <button
                  onClick={() => {
                    setPathPlayback(false);
                    setPathActiveEdgeIndex(null);
                  }}
                  className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white text-xs font-bold"
                >
                  {t('common_reset', 'Reset')}
                </button>
                <select
                  value={String(pathPlaybackSpeed)}
                  onChange={(e) => setPathPlaybackSpeed(Number(e.target.value))}
                  className="px-2 py-2 bg-[#0e1012] border border-gray-700 rounded text-white text-xs font-bold outline-none"
                  title={t('path_trace_playback_speed', 'Playback speed')}
                >
                  <option value="0.5">0.5x</option>
                  <option value="1">1x</option>
                  <option value="2">2x</option>
                </select>
                <label className="flex items-center gap-2 px-2 py-2 bg-[#0e1012] border border-gray-700 rounded text-white text-xs font-bold select-none">
                  <input
                    type="checkbox"
                    checked={pathBadgesEnabled}
                    onChange={(e) => setPathBadgesEnabled(e.target.checked)}
                  />
                  {t('path_trace_badge', 'Badge')}
                </label>
                <select
                  value={String(pathEdgeLabelMaxLen)}
                  onChange={(e) => setPathEdgeLabelMaxLen(Number(e.target.value))}
                  className="px-2 py-2 bg-[#0e1012] border border-gray-700 rounded text-white text-xs font-bold outline-none"
                  title={t('path_trace_edge_label_length', 'Edge label length')}
                >
                  <option value="24">{t('common_short', 'Short')}</option>
                  <option value="42">{t('common_normal', 'Normal')}</option>
                  <option value="60">{t('common_long', 'Long')}</option>
                  <option value="90">{t('common_full', 'Full')}</option>
                </select>
                <label className="flex items-center gap-2 px-2 py-2 bg-[#0e1012] border border-gray-700 rounded text-white text-xs font-bold select-none">
                  <input
                    type="checkbox"
                    checked={pathEdgeLabelTruncateMode === 'path'}
                    onChange={(e) => setPathEdgeLabelTruncateMode(e.target.checked ? 'path' : 'all')}
                  />
                  {t('path_trace_path_only', 'Path only')}
                </label>
              </div>
            )}

            <div className="max-h-52 overflow-y-auto space-y-2 text-xs">
              {pathResult.path.map((node, i) => (
                <div
                  data-testid={`path-trace-hop-${i}`}
                  key={i}
                  onClick={() => {
                    setPathPlayback(false);
                    const maxIdx = Math.max(0, (pathResult.path.length || 0) - 2);
                    setPathActiveEdgeIndex(Math.min(Math.max(0, i), maxIdx));
                  }}
                  className={`w-full text-left flex flex-col relative pl-4 border-l border-gray-700 pb-2 last:pb-0 rounded cursor-pointer ${pathActiveEdgeIndex != null && (i === pathActiveEdgeIndex || i === pathActiveEdgeIndex + 1) ? 'bg-white/5' : ''}`}
                >
                  <div className={`absolute left-[-4px] top-0 w-2 h-2 rounded-full ${pathActiveEdgeIndex != null && (i === pathActiveEdgeIndex || i === pathActiveEdgeIndex + 1) ? 'bg-emerald-400' : 'bg-indigo-500'}`} />
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-gray-300 truncate">{t('path_trace_hop_fmt', 'Hop {value} -').replace('{value}', String(i + 1))} {node.name}</div>
                      <div className="text-gray-500 font-mono truncate">{node.ip}</div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setPathEvidenceOpen((prev) => {
                          const key = String(i);
                          const next = { ...prev };
                          next[key] = !next[key];
                          return next;
                        });
                      }}
                      className="shrink-0 px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-200 text-[10px] font-bold flex items-center gap-1"
                    >
                      {pathEvidenceOpen[String(i)] ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      {t('path_trace_evidence', 'Evidence')}
                    </button>
                  </div>
                  {node.ingress_intf && <div className="text-indigo-300 mt-0.5">{t('path_trace_in', 'In')}: {node.ingress_intf}</div>}
                  {node.egress_intf && <div className="text-indigo-300">{t('path_trace_out', 'Out')}: {node.egress_intf}</div>}
                  {(() => {
                    const segment = Array.isArray(pathResult?.segments) ? pathResult.segments[i] : null;
                    if (!segment) return null;
                    const protocol = String(segment?.protocol || '').trim().toUpperCase();
                    const status = String(segment?.status || '').trim().toLowerCase();
                    const confidence = Number.isFinite(Number(segment?.confidence))
                      ? Number(segment.confidence).toFixed(2)
                      : null;
                    const tone = status === 'degraded'
                      ? 'bg-amber-500/20 text-amber-200 border-amber-600/40'
                      : status === 'down' || status === 'unresolved'
                        ? 'bg-red-500/20 text-red-200 border-red-600/40'
                        : 'bg-emerald-500/20 text-emerald-200 border-emerald-600/40';
                    return (
                      <div data-testid={`path-trace-segment-${i}`} className="mt-1 flex flex-wrap gap-1">
                        {protocol && <span className="px-2 py-0.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-[10px] font-semibold text-indigo-200">{protocol}</span>}
                        {status && <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase ${tone}`}>{status}</span>}
                        {confidence && <span className="px-2 py-0.5 rounded-full border border-gray-600 bg-gray-800 text-[10px] font-semibold text-gray-200">conf {confidence}</span>}
                      </div>
                    );
                  })()}

                  {(() => {
                    const { summaryText, detailLines } = buildEvidenceParts(node);
                    const open = !!pathEvidenceOpen[String(i)];
                    if (!summaryText && (!open || detailLines.length === 0)) return null;
                    return (
                      <div className="mt-1">
                        {summaryText && <div className="text-[10px] text-gray-400">{summaryText}</div>}
                        {open && detailLines.length > 0 && (
                          <div className="mt-1 text-[10px] text-gray-200 bg-black/25 border border-gray-700 rounded p-2 space-y-0.5">
                            {detailLines.map((t, idx) => (
                              <div key={idx} className="break-all">{t}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
};

export default PathTracePanel;

