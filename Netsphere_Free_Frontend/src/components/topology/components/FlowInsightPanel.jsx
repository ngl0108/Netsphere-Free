import React from 'react';
import { Panel } from 'reactflow';
import { Activity, XCircle, RefreshCw } from 'lucide-react';
import { t } from '../../../i18n';

const FlowInsightPanel = ({
  showPathTrace,
  setShowFlowInsight,
  flowWindowSec,
  setFlowWindowSec,
  loadFlowInsight,
  flowLoading,
  flowTalkers,
  flowApps,
  flowSelectedApp,
  setFlowSelectedApp,
  flowFlows,
  flowAppLoading,
  flowSelectedAppFlows,
  formatBps,
}) => {
  return (
    <Panel position="top-right" className={`m-4 ${showPathTrace ? 'mt-[520px]' : ''}`}>
      <div className="w-[min(52rem,calc(100vw-2rem))] bg-[#1b1d1f] border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-4 text-white">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-bold flex items-center gap-2">
            <Activity size={18} className="text-emerald-400" /> {t('flow_insight_title', 'Flow Insight (NetFlow v5)')}
          </h3>
          <button onClick={() => setShowFlowInsight(false)}>
            <XCircle size={18} className="text-gray-500 hover:text-white" />
          </button>
        </div>

        <div className="flex items-center gap-2 mb-3">
          <select
            value={flowWindowSec}
            onChange={(e) => setFlowWindowSec(Number(e.target.value))}
            className="bg-[#0e1012] border border-gray-700 rounded px-2 py-2 text-sm text-white outline-none"
          >
            <option value={60}>{t('flow_window_60s', 'Last 60s')}</option>
            <option value={300}>{t('flow_window_5m', 'Last 5m')}</option>
            <option value={900}>{t('flow_window_15m', 'Last 15m')}</option>
          </select>
          <button
            onClick={loadFlowInsight}
            disabled={flowLoading}
            className="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 rounded font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <RefreshCw size={14} className={flowLoading ? 'animate-spin' : ''} />
            {t('common_refresh', 'Refresh')}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="border border-gray-700 rounded-lg overflow-hidden">
            <div className="px-3 py-2 bg-black/30 border-b border-gray-700 text-sm font-bold">{t('flow_top_talkers', 'Top Talkers')}</div>
            <div className="max-h-64 overflow-y-auto">
              {flowTalkers.length === 0 ? (
                <div className="p-3 text-sm text-gray-400">{t('flow_no_data', 'No flow data yet.')}</div>
              ) : (
                flowTalkers.map((row) => (
                  <div key={row.src_ip} className="px-3 py-2 border-b border-gray-700 last:border-b-0 flex items-center justify-between gap-2">
                    <div className="font-mono text-sm text-gray-200">{row.src_ip}</div>
                    <div className="text-xs text-gray-400">{formatBps(Number(row.bps || 0))}</div>
                  </div>
                ))
              )}
            </div>
          </div>
          <div className="border border-gray-700 rounded-lg overflow-hidden">
            <div className="px-3 py-2 bg-black/30 border-b border-gray-700 text-sm font-bold flex items-center justify-between gap-2">
              <span>{t('flow_top_apps', 'Top Apps')}</span>
              <select
                value={flowSelectedApp}
                onChange={(e) => setFlowSelectedApp(e.target.value)}
                className="bg-[#0e1012] border border-gray-700 rounded px-2 py-1 text-xs text-white outline-none"
                disabled={flowApps.length === 0}
              >
                {flowApps.length === 0 ? (
                  <option value="">-</option>
                ) : (
                  flowApps.map((row) => (
                    <option key={row.app} value={String(row.app || '')}>
                      {String(row.app || '')}
                    </option>
                  ))
                )}
              </select>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {flowApps.length === 0 ? (
                <div className="p-3 text-sm text-gray-400">{t('flow_no_app_data', 'No app data yet.')}</div>
              ) : (
                flowApps.map((row) => (
                  <button
                    type="button"
                    key={row.app}
                    onClick={() => setFlowSelectedApp(String(row.app || ''))}
                    className={`w-full text-left px-3 py-2 border-b border-gray-700 last:border-b-0 flex items-center justify-between gap-2 hover:bg-white/5 ${String(row.app || '') === String(flowSelectedApp || '') ? 'bg-white/10' : ''}`}
                  >
                    <div className="text-sm font-bold text-gray-200">{row.app}</div>
                    <div className="text-xs text-gray-400">{formatBps(Number(row.bps || 0))}</div>
                  </button>
                ))
              )}
            </div>
          </div>
          <div className="border border-gray-700 rounded-lg overflow-hidden">
            <div className="px-3 py-2 bg-black/30 border-b border-gray-700 text-sm font-bold">{t('flow_top_flows', 'Top Flows')}</div>
            <div className="max-h-64 overflow-y-auto">
              {flowFlows.length === 0 ? (
                <div className="p-3 text-sm text-gray-400">{t('flow_no_data', 'No flow data yet.')}</div>
              ) : (
                flowFlows.map((row, idx) => (
                  <div key={`${row.src_ip}-${row.dst_ip}-${row.src_port}-${row.dst_port}-${idx}`} className="px-3 py-2 border-b border-gray-700 last:border-b-0">
                    <div className="text-sm text-gray-200 font-mono truncate">
                      {row.src_ip}:{row.src_port}{' -> '}{row.dst_ip}:{row.dst_port}
                    </div>
                    <div className="text-xs text-gray-400 mt-1 flex items-center justify-between">
                      <span>{row.app ? `${row.app} / ` : ''}{t('flow_proto', 'proto')} {row.proto}</span>
                      <span>{formatBps(Number(row.bps || 0))}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="mt-3 border border-gray-700 rounded-lg overflow-hidden">
          <div className="px-3 py-2 bg-black/30 border-b border-gray-700 text-sm font-bold flex items-center justify-between gap-2">
            <span>{t('flow_selected_app_flows', 'Selected App Flows')}</span>
            <span className="text-xs text-gray-400">{flowSelectedApp || '-'}</span>
          </div>
          <div className="max-h-56 overflow-y-auto">
            {flowAppLoading ? (
              <div className="p-3 text-sm text-gray-400 flex items-center gap-2">
                <RefreshCw size={14} className="animate-spin" /> {t('endpoint_panel_loading', 'Loading...')}
              </div>
            ) : flowSelectedAppFlows.length === 0 ? (
              <div className="p-3 text-sm text-gray-400">{t('flow_no_selected_app_flows', 'No flows for selected app.')}</div>
            ) : (
              flowSelectedAppFlows.map((row, idx) => (
                <div key={`${row.src_ip}-${row.dst_ip}-${row.src_port}-${row.dst_port}-${idx}`} className="px-3 py-2 border-b border-gray-700 last:border-b-0">
                  <div className="text-sm text-gray-200 font-mono truncate">
                    {row.src_ip}:{row.src_port}{' -> '}{row.dst_ip}:{row.dst_port}
                  </div>
                  <div className="text-xs text-gray-400 mt-1 flex items-center justify-between">
                    <span>{t('flow_proto', 'proto')} {row.proto}</span>
                    <span>{formatBps(Number(row.bps || 0))}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
};

export default FlowInsightPanel;
