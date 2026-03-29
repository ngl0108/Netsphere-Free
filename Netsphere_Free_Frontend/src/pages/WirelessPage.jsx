import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Wifi, Users, Radio, Server, Search, RefreshCw,
  ChevronRight, ShieldCheck, Globe,
} from 'lucide-react';
import { DeviceService } from '../api/services';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';
import useVisiblePolling from '../hooks/useVisiblePolling';
import { InlineError, InlineLoading } from '../components/common/PageState';

const WirelessPage = () => {
  useLocaleRerender();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const loadData = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await DeviceService.getWirelessOverview();
      setData(res.data);
    } catch (err) {
      console.error('Failed to load wireless data', err);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useVisiblePolling(() => loadData(true), 5000, {
    enabled: true,
    immediate: false,
    runOnVisible: true,
    backoffMultiplier: 3,
    backoffMaxIntervalMs: 120000,
  });

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500 dark:text-gray-400 animate-pulse">
        <InlineLoading label={t('wireless_loading_telemetry', 'Gathering global wireless telemetry...')} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="h-full p-10 text-center text-red-600 dark:text-red-400">
        <InlineError label={t('wireless_unavailable', 'Wireless services temporarily unavailable.')} />
      </div>
    );
  }

  const aps = Array.isArray(data.aps) ? data.aps : [];
  const wlans = Array.isArray(data.wlans) ? data.wlans : [];
  const summary = data.summary || {};

  const filteredAps = aps.filter((ap) =>
    (ap.name || '').toLowerCase().includes(search.toLowerCase())
    || (ap.wlc_name || '').toLowerCase().includes(search.toLowerCase())
    || (ap.ip_address || '').includes(search));

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-[#f4f5f9] dark:bg-[#0b0c0e] h-full min-h-0 flex flex-col gap-6 overflow-y-auto animate-fade-in text-gray-900 dark:text-white">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-end border-b border-gray-200 dark:border-gray-800 pb-4">
        <div>
          <h1 className="text-2xl font-black flex items-center gap-3">
            <Radio className="text-pink-500" size={28} /> {t('wireless_title')}
          </h1>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 uppercase tracking-widest font-bold">
            {t('wireless_subtitle', 'Comprehensive control for mixed wireless infrastructure')}
          </p>
        </div>
        <button
          onClick={loadData}
          className="h-10 w-10 inline-flex items-center justify-center bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors border border-gray-200 dark:border-gray-700 shadow-sm dark:shadow-lg text-gray-700 dark:text-gray-200"
          title={t('common_refresh', 'Refresh')}
        >
          <RefreshCw size={18} />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard icon={<Server className="text-blue-500" />} title={t('wireless_stat_control_planes', 'Control Planes')} value={summary.total_wlc ?? 0} sub={t('wireless_stat_active_wlcs', 'Active WLCs')} />
        <StatCard icon={<Wifi className="text-emerald-500" />} title={t('wireless_stat_total_aps', 'Total Access Points')} value={summary.total_aps ?? 0} sub={t('wireless_stat_physical_radios', 'Physical Radios')} />
        <StatCard icon={<Globe className="text-indigo-500" />} title={t('wireless_stat_broadcast_ssids', 'Broadcast SSIDs')} value={summary.total_wlans ?? 0} sub={t('wireless_stat_logical_services', 'Logical Services')} />
        <StatCard icon={<Users className="text-pink-500" />} title={t('wireless_stat_mobile_clients', 'Mobile Clients')} value={summary.total_clients ?? 0} sub={t('wireless_stat_active_sessions', 'Active Sessions')} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl overflow-hidden shadow-sm dark:shadow-xl flex flex-col">
          <div className="p-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/30 flex justify-between items-center">
            <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase flex items-center gap-2">
              <ShieldCheck size={16} className="text-indigo-500" /> {t('wireless_service_directory', 'Service Directory')}
            </h3>
            <span className="text-[10px] bg-indigo-500/20 text-indigo-500 dark:text-indigo-400 px-2 py-0.5 rounded-full font-bold">
              {t('wireless_global_badge', 'Global')}
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
            {wlans.map((wl, idx) => (
              <div
                key={idx}
                className="p-3 bg-gray-50 dark:bg-gray-800/40 rounded-xl border border-gray-200 dark:border-gray-700/50 hover:border-indigo-300 dark:hover:border-indigo-500/50 transition-all group"
              >
                <div className="flex justify-between items-start mb-1">
                  <span className="text-sm font-bold text-gray-900 dark:text-white group-hover:text-indigo-500 dark:group-hover:text-indigo-400 transition-colors uppercase">
                    {wl.ssid}
                  </span>
                  <span className={`text-[9px] font-black px-1.5 py-0.5 rounded ${wl.status === 'UP' ? 'bg-emerald-500 text-white' : 'bg-red-500 text-white'}`}>
                    {wl.status}
                  </span>
                </div>
                <div className="flex justify-between text-[10px] text-gray-500 dark:text-gray-400 font-medium">
                  <span>ID: {wl.id} / {wl.profile}</span>
                  <span className="italic">{t('wireless_via', 'via')} {wl.wlc_name}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="lg:col-span-2 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl overflow-hidden shadow-sm dark:shadow-xl flex flex-col">
          <div className="p-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/30 flex flex-wrap justify-between items-center gap-4">
            <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase flex items-center gap-2">
              <Wifi size={16} className="text-emerald-500" /> {t('wireless_ap_inventory', 'AP Radio Inventory')}
            </h3>
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500" size={14} />
              <input
                type="text"
                placeholder={t('wireless_search_placeholder', 'Search AP name, IP or controller...')}
                className="bg-white dark:bg-[#0b0c0e] border border-gray-300 dark:border-gray-700 rounded-lg pl-9 pr-4 py-1.5 text-xs text-gray-800 dark:text-gray-200 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:ring-2 focus:ring-emerald-500 outline-none w-full transition-all"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
          <div className="flex-1 overflow-x-auto custom-scrollbar">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="bg-gray-50 dark:bg-[#0b0c0e] sticky top-0 z-10 border-b border-gray-200 dark:border-gray-800">
                <tr>
                  <th className="p-4 font-bold text-gray-600 dark:text-gray-500 uppercase tracking-tighter">{t('wireless_col_ap_info', 'AP Information')}</th>
                  <th className="p-4 font-bold text-gray-600 dark:text-gray-500 uppercase tracking-tighter text-center">{t('devices_col_status', 'Status')}</th>
                  <th className="p-4 font-bold text-gray-600 dark:text-gray-500 uppercase tracking-tighter">{t('wireless_col_controller', 'Controller')}</th>
                  <th className="p-4 font-bold text-gray-600 dark:text-gray-500 uppercase tracking-tighter">{t('wireless_col_management_ip', 'Management IP')}</th>
                  <th className="p-4 font-bold text-gray-600 dark:text-gray-500 uppercase tracking-tighter" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-800/50">
                {filteredAps.map((ap, idx) => (
                  <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors group">
                    <td className="p-4">
                      <div className="flex flex-col">
                        <span className="font-bold text-gray-800 dark:text-gray-200 uppercase">{ap.name || t('wireless_unknown_ap', 'Unknown AP')}</span>
                        <span className="text-[10px] text-gray-500 dark:text-gray-400">{ap.model || t('wireless_na', 'N/A')} / {ap.serial_number || t('wireless_na', 'N/A')}</span>
                      </div>
                    </td>
                    <td className="p-4 text-center">
                      <div className="flex justify-center">
                        <StatusBadge status={ap.status} />
                      </div>
                    </td>
                    <td className="p-4">
                      <span className="bg-blue-500/10 text-blue-600 dark:text-blue-400 px-2 py-1 rounded font-bold">{ap.wlc_name}</span>
                    </td>
                    <td className="p-4 font-mono text-gray-600 dark:text-gray-400">
                      {ap.ip_address}
                    </td>
                    <td className="p-4 text-right">
                      <button
                        onClick={() => navigate(`/devices/${ap.wlc_ip}`)}
                        className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-all transform hover:scale-110"
                        title={t('device_detail_summary', 'Summary')}
                      >
                        <ChevronRight size={18} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

const StatCard = ({ icon, title, value, sub }) => (
  <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 p-5 rounded-2xl shadow-sm dark:shadow-lg flex items-center gap-5">
    <div className="p-4 bg-gray-100 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700/50">{icon}</div>
    <div>
      <p className="text-[10px] font-black text-gray-500 dark:text-gray-400 uppercase tracking-widest">{title}</p>
      <h3 className="text-2xl font-black text-gray-900 dark:text-white">{value}</h3>
      <p className="text-[10px] text-gray-500 dark:text-gray-400 italic mt-0.5">{sub}</p>
    </div>
  </div>
);

const StatusBadge = ({ status }) => {
  const s = String(status).toLowerCase();
  const isUp = s.includes('up') || s.includes('reg') || s.includes('online');
  return (
    <span className={`px-2 py-1 rounded text-[9px] font-black uppercase tracking-tighter ${isUp ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20' : 'bg-red-500/10 text-red-500 border border-red-500/20'}`}>
      {status || t('devices_status_unknown', 'Unknown')}
    </span>
  );
};

export default WirelessPage;
