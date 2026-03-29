import React from 'react';
import { Panel } from 'reactflow';
import { Layers, XCircle, RefreshCw } from 'lucide-react';
import { t } from '../../../i18n';

const EndpointGroupPanel = ({
  endpointGroupPanel,
  setEndpointGroupPanel,
  showPathTrace,
}) => {
  if (!endpointGroupPanel?.open) return null;

  return (
    <Panel position="top-right" className={`m-4 ${showPathTrace ? 'mt-[520px]' : ''}`}>
      <div className="w-[min(24rem,calc(100vw-2rem))] bg-[#1b1d1f] border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-4 text-white">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-bold flex items-center gap-2">
            <Layers size={18} className="text-cyan-400" /> {t('endpoint_panel_title', 'Port Endpoints')}
          </h3>
          <button onClick={() => setEndpointGroupPanel({ open: false, loading: false, error: '', group: null, endpoints: [] })}>
            <XCircle size={18} className="text-gray-500 hover:text-white" />
          </button>
        </div>

        <div className="text-xs text-gray-300 mb-3">
          <div className="font-mono">
            {t('endpoint_panel_device_port_fmt', 'device {device} / port {port}')
              .replace('{device}', String(endpointGroupPanel.group?.device_id ?? '-'))
              .replace('{port}', String(endpointGroupPanel.group?.port ?? '-'))}
          </div>
          {typeof endpointGroupPanel.group?.count === 'number' && (
            <div className="text-gray-400 mt-1">
              {t('endpoint_panel_endpoints_count_fmt', 'endpoints: {count}').replace('{count}', String(endpointGroupPanel.group.count))}
            </div>
          )}
        </div>

        {endpointGroupPanel.loading && (
          <div className="text-sm text-gray-400 flex items-center gap-2">
            <RefreshCw size={14} className="animate-spin" /> {t('endpoint_panel_loading', 'Loading...')}
          </div>
        )}

        {!!endpointGroupPanel.error && (
          <div className="text-sm text-red-400">{endpointGroupPanel.error}</div>
        )}

        {!endpointGroupPanel.loading && !endpointGroupPanel.error && (
          <div className="max-h-[360px] overflow-y-auto border border-gray-700 rounded-lg">
            {endpointGroupPanel.endpoints.length === 0 ? (
              <div className="p-3 text-sm text-gray-400">{t('endpoint_panel_no_endpoints', 'No endpoints found.')}</div>
            ) : (
              endpointGroupPanel.endpoints.map((ep) => (
                <div key={ep.endpoint_id} className="p-3 border-b border-gray-700 last:border-b-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-bold text-gray-200 truncate">
                        {ep.hostname || ep.ip_address || ep.mac_address}
                      </div>
                      <div className="text-[11px] text-gray-500 font-mono truncate">
                        {ep.mac_address}{ep.ip_address ? ` / ${ep.ip_address}` : ''}{ep.vlan ? ` / vlan ${ep.vlan}` : ''}
                      </div>
                      <div className="text-[11px] text-gray-400 mt-1 truncate">
                        {(ep.endpoint_type || t('endpoint_panel_unknown_type', 'unknown')).toUpperCase()} / {ep.vendor || t('endpoint_panel_unknown_vendor', 'Unknown')}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {ep.private_mac && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-yellow-400 text-black font-bold">{t('endpoint_panel_private_mac', 'Private MAC')}</span>
                      )}
                      {!!ep.last_seen && (
                        <span className="text-[10px] text-gray-500">{ep.last_seen.slice(0, 19).replace('T', ' ')}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </Panel>
  );
};

export default EndpointGroupPanel;
