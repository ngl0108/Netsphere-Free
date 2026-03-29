import React, { useEffect, useMemo, useRef, useState } from 'react';
import { DeviceService } from '../../api/services';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import {
  Search,
  RefreshCw,
  Plus,
  Trash2,
  Edit2,
  MapPin,
  Filter,
  Server,
  Shield,
  Wifi,
  Router,
  Box,
  Cloud,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import DeviceAddModal from './DeviceAddModal';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import useVirtualRows from '../../hooks/useVirtualRows';
import { InlineEmpty, InlineLoading, SectionCard } from '../common/PageState';
import { getManagedDeviceStatusMeta } from '../../utils/deviceStatusTone';

const DeviceListPage = () => {
  const navigate = useNavigate();
  const { isOperator, isAdmin } = useAuth();
  const { toast } = useToast();
  useLocaleRerender();

  const [devices, setDevices] = useState([]);
  const [sites, setSites] = useState([]);
  const [managedSummary, setManagedSummary] = useState(null);
  const [selectedSiteId, setSelectedSiteId] = useState('all');
  const [managementFilter, setManagementFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const tableScrollRef = useRef(null);
  const hasManagedQuota = Number(managedSummary?.managed_limit || 0) > 0;

  const loadData = async () => {
    setLoading(true);
    try {
      const summaryRes = await DeviceService.getManagedSummary().catch(() => ({ data: null }));
      const [devRes, siteRes] = await Promise.all([DeviceService.getAll(), DeviceService.getSites()]);
      setDevices(Array.isArray(devRes?.data) ? devRes.data : []);
      setSites(Array.isArray(siteRes?.data) ? siteRes.data : []);
      setManagedSummary(summaryRes?.data || null);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePromote = async (event, device) => {
    event.stopPropagation();
    try {
      const res = await DeviceService.promoteToManaged(device.id);
      setManagedSummary(res?.data?.summary || null);
      toast.success(t('devices_manage_promoted', 'This node is now actively managed.'));
      await loadData();
    } catch (error) {
      const message =
        error?.response?.data?.detail?.message ||
        error?.response?.data?.message ||
        t('devices_manage_promote_failed', 'Unable to assign a managed slot.');
      toast.error(message);
    }
  };

  const handleRelease = async (event, device) => {
    event.stopPropagation();
    try {
      const res = await DeviceService.releaseManagement(device.id);
      setManagedSummary(res?.data?.summary || null);
      toast.success(t('devices_manage_released', 'The managed slot was released.'));
      await loadData();
    } catch (error) {
      const message =
        error?.response?.data?.detail?.message ||
        error?.response?.data?.message ||
        t('devices_manage_release_failed', 'Unable to release this managed slot.');
      toast.error(message);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    if (
      !window.confirm(
        t('devices_delete_confirm', 'Are you sure you want to delete this device? This action cannot be undone.'),
      )
    ) {
      return;
    }

    try {
      await DeviceService.delete(id);
      setDevices((prev) => prev.filter((d) => d.id !== id));
    } catch (error) {
      console.error(error);
      toast.error(t('devices_delete_failed', 'Failed to delete device.'));
    }
  };

  const handleEdit = (e, device) => {
    e.stopPropagation();
    setSelectedDevice(device);
    setIsModalOpen(true);
  };

  const handleAdd = () => {
    setSelectedDevice(null);
    setIsModalOpen(true);
  };

  const getDeviceIcon = (type) => {
    switch (type) {
      case 'core':
        return <Box size={18} className="text-purple-500" />;
      case 'dist':
        return <Router size={18} className="text-blue-500" />;
      case 'access':
        return <Server size={18} className="text-green-500" />;
      case 'router':
        return <Cloud size={18} className="text-orange-500" />;
      case 'ap':
        return <Wifi size={18} className="text-cyan-500" />;
      default:
        return <Shield size={18} className="text-gray-500" />;
    }
  };

  const siteNameById = useMemo(() => {
    const next = new Map();
    for (const site of sites || []) {
      next.set(Number(site?.id), site?.name || t('devices_unknown_site', 'Unknown Site'));
    }
    return next;
  }, [sites]);

  const filteredDevices = useMemo(() => {
    return devices.filter((device) => {
      const name = String(device?.name || '').toLowerCase();
      const ip = String(device?.ip_address || '');
      const matchesSearch =
        name.includes(String(searchTerm || '').toLowerCase()) || ip.includes(String(searchTerm || ''));
      const matchesSite = selectedSiteId === 'all' || device.site_id === parseInt(selectedSiteId, 10);
      const state = String(device?.management_state || 'managed');
      const matchesManagement =
        managementFilter === 'all' ||
        (managementFilter === 'managed' && state === 'managed') ||
        (managementFilter === 'discovered_only' && state !== 'managed');
      return matchesSearch && matchesSite && matchesManagement;
    });
  }, [devices, searchTerm, selectedSiteId, managementFilter]);

  const {
    visibleItems: visibleDevices,
    totalCount: totalDeviceCount,
    startIndex: visibleStartIndex,
    endIndex: visibleEndIndex,
    paddingTop: virtualPaddingTop,
    paddingBottom: virtualPaddingBottom,
    onScroll: onVirtualScroll,
  } = useVirtualRows(filteredDevices, {
    containerRef: tableScrollRef,
    rowHeight: 72,
    overscan: 12,
    enabled: filteredDevices.length > 120,
  });

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012] h-full min-h-0 flex flex-col animate-fade-in relative text-gray-900 dark:text-white transition-colors">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t('devices_title', 'Device Inventory')}
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-500">
            {t('devices_desc', 'Manage infrastructure nodes and connections.')}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={loadData}
            title={t('common_refresh', 'Refresh')}
            className="h-10 w-10 inline-flex items-center justify-center bg-white dark:bg-[#1e293b] border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-gray-700 dark:text-gray-300"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>

          {isOperator() && (
            <button
              onClick={handleAdd}
              className="h-10 inline-flex items-center gap-2 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-bold shadow-lg shadow-blue-500/20 transition-colors"
            >
              <Plus size={18} /> {t('devices_add', 'Add Device')}
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-4 mb-4">
        <SectionCard className="flex-1 p-4 relative">
          <Search className="absolute left-7 top-6.5 text-gray-500 dark:text-gray-400" size={18} />
          <input
            type="text"
            placeholder={t('devices_search_placeholder', 'Search by Hostname or IP...')}
            className="w-full pl-10 pr-4 py-2 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500 transition-all"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </SectionCard>

        <SectionCard className="px-4 flex items-center w-full sm:w-56">
          <Filter size={18} className="text-gray-500 dark:text-gray-400 mr-2" />
          <select
            className="w-full bg-transparent text-sm text-gray-900 dark:text-white outline-none cursor-pointer"
            value={selectedSiteId}
            onChange={(e) => setSelectedSiteId(e.target.value)}
          >
            <option value="all">{t('devices_all_sites', 'All Sites (Global)')}</option>
            {sites.map((site) => (
              <option key={site.id} value={site.id}>
                {site.name}
              </option>
            ))}
          </select>
        </SectionCard>
        <SectionCard className="px-4 flex items-center w-full sm:w-56">
          <Filter size={18} className="text-gray-500 dark:text-gray-400 mr-2" />
          <select
            className="w-full bg-transparent text-sm text-gray-900 dark:text-white outline-none cursor-pointer"
            value={managementFilter}
            onChange={(e) => setManagementFilter(e.target.value)}
          >
            <option value="all">{t('devices_all_management_states', 'All Nodes')}</option>
            <option value="managed">{t('devices_filter_managed', 'Managed')}</option>
            <option value="discovered_only">{t('devices_filter_discovered_only', 'Discovered Only')}</option>
          </select>
        </SectionCard>
      </div>

      {hasManagedQuota && managedSummary && (
        <SectionCard className="mb-4 p-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm font-bold text-gray-900 dark:text-white">
                {t('devices_free_management_title', 'NetSphere Free managed-node capacity')}
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                {t(
                  'devices_free_management_desc',
                  'Discovery remains visible for all assets. Active monitoring, alerts, diagnosis, and history are enabled only for managed nodes.',
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2 text-xs font-bold">
              <span className="px-2 py-1 rounded bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300">
                {t('devices_filter_managed', 'Managed')}: {managedSummary.managed}/{managedSummary.managed_limit}
              </span>
              <span className="px-2 py-1 rounded bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                {t('devices_filter_discovered_only', 'Discovered Only')}: {managedSummary.discovered_only}
              </span>
              <span className="px-2 py-1 rounded bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300">
                {t('devices_slots_remaining', 'Slots Remaining')}: {managedSummary.remaining_slots}
              </span>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => navigate('/edition/compare')}
              className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-bold text-blue-700 hover:bg-blue-100 dark:border-blue-900/40 dark:bg-blue-900/10 dark:text-blue-300 dark:hover:bg-blue-900/20"
            >
              {t('devices_free_management_compare_cta', 'Compare Free and Pro')}
            </button>
          </div>
        </SectionCard>
      )}

      {/* ── Monitoring Profile Missing Alert ── */}
      {!loading && (() => {
        const managedWithoutProfile = devices.filter(
          d => d.management_state === 'managed' && !d.monitoring_profile?.name
        );
        if (managedWithoutProfile.length === 0) return null;
        return (
          <SectionCard className="mb-4 p-4 border-amber-200 dark:border-amber-900/40 bg-amber-50/80 dark:bg-amber-900/10">
            <div className="flex items-start gap-3">
              <Shield size={18} className="text-amber-600 mt-0.5 shrink-0" />
              <div className="flex-1">
                <div className="text-sm font-bold text-amber-800 dark:text-amber-200">
                  {t('devices_profile_missing_title', '{count} managed device(s) have no monitoring profile assigned').replace('{count}', String(managedWithoutProfile.length))}
                </div>
                <div className="text-xs text-amber-700 dark:text-amber-300 mt-1">
                  {t('devices_profile_missing_desc', 'These devices are in Managed state but are NOT being actively monitored because no profile defines their polling behavior. Assign a profile to start collecting metrics.')}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {managedWithoutProfile.slice(0, 6).map(d => (
                    <span key={d.id} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white/70 dark:bg-black/20 border border-amber-200 dark:border-amber-800 text-[11px] font-mono text-amber-800 dark:text-amber-200">
                      {d.name || d.ip_address}
                    </span>
                  ))}
                  {managedWithoutProfile.length > 6 && (
                    <span className="text-[11px] text-amber-600 dark:text-amber-400 font-bold">+{managedWithoutProfile.length - 6} more</span>
                  )}
                </div>
                <div className="mt-3">
                  <button
                    type="button"
                    onClick={() => navigate('/monitoring-profiles')}
                    className="inline-flex items-center gap-2 rounded-xl border border-amber-300 bg-white/80 px-3 py-2 text-xs font-bold text-amber-800 hover:bg-amber-100 dark:border-amber-900/50 dark:bg-black/10 dark:text-amber-200 dark:hover:bg-amber-900/20"
                  >
                    {t('devices_profile_missing_cta', 'Go to Monitoring Profiles')}
                  </button>
                </div>
              </div>
            </div>
          </SectionCard>
        );
      })()}

      <SectionCard data-testid="device-inventory-panel" className="flex-1 overflow-hidden flex flex-col mb-10">
        <div className="overflow-auto flex-1" ref={tableScrollRef} onScroll={onVirtualScroll}>
          <table data-testid="device-inventory-table" className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-gray-50 dark:bg-[#25282c] border-b border-gray-200 dark:border-gray-800">
                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">
                  {t('devices_col_device', 'Device')}
                </th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">
                  {t('devices_col_type', 'Type')}
                </th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">
                  {t('devices_col_site', 'Site')}
                </th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">
                  {t('devices_col_ip', 'IP Address')}
                </th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">
                  {t('devices_col_status', 'Status')}
                </th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase text-right">
                  {t('devices_col_actions', 'Actions')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {virtualPaddingTop > 0 && (
                <tr aria-hidden="true">
                  <td colSpan="6" style={{ height: `${virtualPaddingTop}px`, padding: 0, border: 0 }} />
                </tr>
              )}
              {loading ? (
                <tr>
                  <td colSpan="6" className="px-6 py-10 text-center text-gray-600 dark:text-gray-500">
                    <InlineLoading label={t('common_loading', 'Loading...')} />
                  </td>
                </tr>
              ) : visibleDevices.map((device) => (
                <tr
                  key={device.id}
                  onClick={() => navigate(`/devices/${device.id}`)}
                  className="group hover:bg-gray-50 dark:hover:bg-[#25282c] cursor-pointer transition-colors"
                >
                  <td className="px-6 py-4 flex items-center gap-3">
                    {getDeviceIcon(device.device_type)}
                      <div>
                        <div className="text-sm font-bold text-gray-900 dark:text-white">{device.name}</div>
                        <div className="text-xs text-gray-600 dark:text-gray-500">
                          {device.model || t('devices_unknown_model', 'Unknown Model')}
                        </div>
                        {device.monitoring_profile?.name ? (
                          <div className="mt-1 text-[11px] text-blue-700 dark:text-blue-300 font-semibold">
                            {t('devices_monitoring_profile_inline', 'Profile')}: {device.monitoring_profile.name}
                            <span className="ml-1 text-[10px] font-medium uppercase text-gray-500 dark:text-gray-400">
                              ({device.monitoring_profile.activation_state || t('common_unknown', 'Unknown')})
                            </span>
                          </div>
                        ) : null}
                        <div className="mt-1">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              device.management_state === 'managed'
                                ? 'text-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 dark:text-emerald-300'
                                : 'text-amber-700 bg-amber-50 dark:bg-amber-900/20 dark:text-amber-300'
                            }`}
                          >
                            {device.management_state === 'managed'
                              ? t('devices_filter_managed', 'Managed')
                              : t('devices_filter_discovered_only', 'Discovered Only')}
                          </span>
                        </div>
                      </div>
                    </td>
                  <td className="px-6 py-4 text-xs font-medium text-gray-600 dark:text-gray-500 uppercase">
                    {device.device_type}
                  </td>
                  <td className="px-6 py-4">
                    {device.site_id ? (
                      <span className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-500 bg-blue-50 dark:bg-blue-900/20 px-2 py-1 rounded w-fit">
                        <MapPin size={10} />
                        {siteNameById.get(Number(device.site_id)) || t('devices_unknown_site', 'Unknown Site')}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-500 dark:text-gray-400">-</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-300 font-mono">
                    {device.ip_address}
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        device.management_state === 'managed'
                          ? device.status === 'online'
                            ? 'text-green-600 bg-green-50 dark:bg-green-900/20'
                            : 'text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800'
                          : 'text-slate-700 bg-slate-100 dark:bg-slate-800 dark:text-slate-300'
                      }`}
                    >
                      {device.management_state === 'managed'
                        ? (getManagedDeviceStatusMeta(device.status, device.management_state)?.label || t('devices_status_unknown', 'UNKNOWN'))
                        : t('devices_status_discovered', 'DISCOVERED')}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    {hasManagedQuota && isOperator() && device.management_state !== 'managed' && (
                      <button
                        onClick={(e) => handlePromote(e, device)}
                        className="px-2 py-1 text-xs font-bold rounded bg-emerald-600 text-white hover:bg-emerald-700 transition-colors"
                      >
                        {t('devices_promote_managed', 'Make Managed')}
                      </button>
                    )}
                    {hasManagedQuota && isOperator() && device.management_state === 'managed' && (
                      <button
                        onClick={(e) => handleRelease(e, device)}
                        className="px-2 py-1 text-xs font-bold rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors"
                      >
                        {t('devices_release_slot', 'Release Slot')}
                      </button>
                    )}
                    {isOperator() && (
                      <button
                        onClick={(e) => handleEdit(e, device)}
                        className="p-2 text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400 transition-colors"
                      >
                        <Edit2 size={16} />
                      </button>
                    )}
                    {isAdmin() && (
                      <button
                        onClick={(e) => handleDelete(e, device.id)}
                        className="p-2 text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400 transition-colors"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && filteredDevices.length === 0 && (
                <tr>
                  <td colSpan="6" className="px-6 py-10 text-center text-gray-600 dark:text-gray-500">
                    <InlineEmpty label={t('devices_empty', 'No devices found.')} />
                  </td>
                </tr>
              )}
              {virtualPaddingBottom > 0 && (
                <tr aria-hidden="true">
                  <td colSpan="6" style={{ height: `${virtualPaddingBottom}px`, padding: 0, border: 0 }} />
                </tr>
              )}
              {filteredDevices.length > 0 && (
                <tr>
                  <td colSpan="6" className="px-6 py-3 text-center text-xs text-gray-500 dark:text-gray-400">
                    {t('devices_rendering_progress', 'Rendering {visible}/{total}')
                      .replace('{visible}', String(visibleEndIndex - visibleStartIndex))
                      .replace('{total}', String(totalDeviceCount))}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <DeviceAddModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onDeviceAdded={loadData}
        deviceToEdit={selectedDevice}
      />
    </div>
  );
};

export default DeviceListPage;
