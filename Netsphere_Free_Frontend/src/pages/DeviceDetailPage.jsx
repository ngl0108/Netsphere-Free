import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DeviceService, MonitoringProfileService } from '../api/services';
import { useAuth } from '../context/AuthContext'; // [RBAC]
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';
import useVisiblePolling from '../hooks/useVisiblePolling';
import { InlineEmpty, InlineError, InlineLoading, SectionCard } from '../components/common/PageState';
import { buildGrafanaFleetHealthUrl, buildObservabilityPath } from '../utils/observabilityLinks';
import { getDeviceStatusChipClass, isDeviceOnline } from '../utils/deviceStatusTone';
import {
  ArrowLeft, Activity, Server, Clock, Cpu,
  CheckCircle, RefreshCw, FileText, Network, Slash, AlertTriangle,
  Search, Filter, ListFilter, Tag, Radio, Users, Wifi, ShieldAlert, BarChart3, Workflow as WorkflowIcon
} from 'lucide-react';

const parseFilename = (contentDisposition) => {
  const v = contentDisposition || '';
  const m = v.match(/filename="?([^"]+)"?/i);
  return m ? m[1] : null;
};

const downloadBlob = (data, filename, contentType) => {
  const blob = data instanceof Blob ? data : new Blob([data], { type: contentType || 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || 'download';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

const DeviceDetailPage = () => {
  useLocaleRerender();
  const { id } = useParams();
  const navigate = useNavigate();
  const { isOperator, isAtLeast } = useAuth(); // [RBAC]
  const { toast } = useToast();
  const canOperateProfiles = isAtLeast('operator');

  const [device, setDevice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [profileCatalog, setProfileCatalog] = useState([]);
  const [profileSelection, setProfileSelection] = useState('');
  const [profileSelectionDirty, setProfileSelectionDirty] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [activeTab, setActiveTab] = useState('interfaces'); // interfaces, config
  const [inventory, setInventory] = useState([]);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryTreeOpen, setInventoryTreeOpen] = useState({});
  const [exportingInventory, setExportingInventory] = useState(false);
  const devicePollingIntervalMs = activeTab === 'interfaces' ? 5000 : 12000;
  const devicePollingMinGapMs = activeTab === 'interfaces' ? 1500 : 4000;

  // 1. Load device details
  const loadDevice = async () => {
    try {
      const res = await DeviceService.getDetail(id);
      setDevice(res.data);
      if (!profileSelectionDirty) {
        setProfileSelection(String(res?.data?.monitoring_profile?.profile_id || ''));
      }
    } catch (err) {
      console.error("Failed to load device detail", err);
    } finally {
      setLoading(false);
    }
  };

  useVisiblePolling(() => {
    if (!syncing) {
      void loadDevice();
    }
  }, devicePollingIntervalMs, {
    enabled: true,
    immediate: true,
    runOnVisible: true,
    minGapMs: devicePollingMinGapMs,
    backoffOnError: false,
  });

  useEffect(() => {
    if (activeTab !== 'inventory') return;
    let alive = true;
    const run = async () => {
      setInventoryLoading(true);
      try {
        const res = await DeviceService.getInventory(id);
        if (alive) setInventory(Array.isArray(res.data) ? res.data : []);
      } catch (e) {
        if (alive) setInventory([]);
      } finally {
        if (alive) setInventoryLoading(false);
      }
    };
    run();
    return () => { alive = false; };
  }, [activeTab, id]);

  useEffect(() => {
    if (!canOperateProfiles) return undefined;
    let alive = true;
    (async () => {
      try {
        const res = await MonitoringProfileService.getCatalog();
        if (!alive) return;
        const profiles = Array.isArray(res?.data?.profiles) ? res.data.profiles : [];
        setProfileCatalog(profiles);
      } catch (error) {
        if (alive) {
          setProfileCatalog([]);
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [id, canOperateProfiles]);

  // 2. Sync handler
  const handleSync = async () => {
    if (!window.confirm(t('device_detail_sync_confirm', 'Fetch latest device state via SSH?'))) return;

    setSyncing(true);
    try {
      await DeviceService.syncDevice(id);
      toast.success(t('device_detail_sync_done', 'Device sync completed.'));
      await loadDevice(); // 理쒖???곗씠?곕줈 媛깆??
    } catch (err) {
      console.error(err);
      toast.error(`${t('device_detail_sync_failed', 'Sync failed')}: ${err.response?.data?.detail || t('device_detail_sync_unreachable', 'Device unreachable')}`);
    } finally {
      setSyncing(false);
    }
  };

  const handleExportInventory = async (format) => {
    setExportingInventory(true);
    try {
      const res = await DeviceService.exportInventory(id, format);
      const filename = parseFilename(res.headers?.['content-disposition']) || `inventory_${id}.${format}`;
      const contentType = res.headers?.['content-type'];
      downloadBlob(res.data, filename, contentType);
      toast.success(t('device_detail_download_started', 'Download started.'));
    } catch (err) {
      toast.error(`${t('device_detail_export_failed', 'Export failed')}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setExportingInventory(false);
    }
  };

  const handleRecomputeMonitoringProfile = async () => {
    setProfileBusy(true);
    try {
      const res = await MonitoringProfileService.recomputeForDevice(id);
      const recommendation = res?.data?.recommendation || null;
      setDevice((current) => (current ? { ...current, monitoring_profile: recommendation } : current));
      setProfileSelection(String(recommendation?.profile_id || ''));
      setProfileSelectionDirty(false);
      toast.success(t('device_detail_profile_recomputed', 'Monitoring profile recommendation refreshed.'));
    } catch (error) {
      toast.error(
        `${t('device_detail_profile_recompute_failed', 'Failed to refresh monitoring profile recommendation')}: ${
          error?.response?.data?.detail || error.message
        }`,
      );
    } finally {
      setProfileBusy(false);
    }
  };

  const handleAssignMonitoringProfile = async () => {
    if (!profileSelection) return;
    setProfileBusy(true);
    try {
      const res = await MonitoringProfileService.assignToDevice(id, Number(profileSelection));
      const recommendation = res?.data?.recommendation || null;
      setDevice((current) => (current ? { ...current, monitoring_profile: recommendation } : current));
      setProfileSelection(String(recommendation?.profile_id || ''));
      setProfileSelectionDirty(false);
      toast.success(t('device_detail_profile_assigned', 'Monitoring profile assigned.'));
    } catch (error) {
      toast.error(
        `${t('device_detail_profile_assign_failed', 'Failed to assign monitoring profile')}: ${
          error?.response?.data?.detail || error.message
        }`,
      );
    } finally {
      setProfileBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <InlineLoading label={t('device_detail_loading', 'Loading device details...')} />
      </div>
    );
  }
  if (!device) {
    return (
      <div className="h-full flex items-center justify-center px-4">
        <InlineError label={t('device_detail_no_data', 'Device data not available.')} />
      </div>
    );
  }

  const isOnline = isDeviceOnline(device.status);
  const isManaged = device.management_state === 'managed';
  const monitoringProfile = device.monitoring_profile || null;
  const observabilityHref = buildObservabilityPath({ deviceId: id, siteId: device.site_id });
  const grafanaHref = buildGrafanaFleetHealthUrl({ deviceId: id, siteId: device.site_id });

  // KPI data (use latest metrics point)
  const lastMetric = device.metrics && device.metrics.length > 0
    ? device.metrics[device.metrics.length - 1]
    : { cpu_usage: 0, memory_usage: 0 };

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-[#f4f5f9] dark:bg-[#0e1012] h-full min-h-0 flex flex-col animate-fade-in text-gray-900 dark:text-white overflow-y-auto">

      {/* 1. Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate(-1)} className="p-2 hover:bg-gray-200 dark:hover:bg-gray-800 rounded-full transition-colors">
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              {device.name}
              {device.hostname && device.hostname !== device.name && (
                <span className="text-sm font-normal text-gray-400">({device.hostname})</span>
              )}
              <span className={`px-2 py-0.5 text-xs rounded-full uppercase border font-bold ${getDeviceStatusChipClass(device.status)}`}>
                {device.status?.toUpperCase() || t('devices_status_unknown', 'UNKNOWN')}
              </span>
              <span
                className={`px-2 py-0.5 text-xs rounded-full uppercase border font-bold ${
                  isManaged
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300'
                    : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300'
                }`}
              >
                {isManaged ? t('devices_filter_managed', 'Managed') : t('devices_filter_discovered_only', 'Discovered Only')}
              </span>
            </h1>
            <p className="text-sm text-gray-500 flex items-center gap-2 mt-1">
              <span className="font-mono bg-gray-100 dark:bg-gray-800 px-1.5 rounded">{device.ip_address}</span>
              <span>|</span>
              <span>{device.model || t('device_detail_unknown_model', 'Unknown Model')}</span>
            </p>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2 w-full md:w-auto md:justify-end">
          <button
            onClick={() => isManaged && navigate(observabilityHref)}
            disabled={!isManaged}
            className={`h-10 min-w-[150px] flex items-center justify-center gap-2 px-4 text-sm font-bold rounded-lg border transition-colors ${
              isManaged
                ? 'border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/10'
                : 'border-gray-200 dark:border-gray-800 bg-gray-100 dark:bg-gray-900 text-gray-400 cursor-not-allowed'
            }`}
          >
            <BarChart3 size={16} />
            {t('common_open_observability', 'Open Observability')}
          </button>
          <a
            href={isManaged ? grafanaHref : undefined}
            target="_blank"
            rel="noreferrer"
            onClick={(event) => {
              if (!isManaged) {
                event.preventDefault();
              }
            }}
            className={`h-10 min-w-[132px] flex items-center justify-center gap-2 px-4 text-sm font-bold rounded-lg border transition-colors ${
              isManaged
                ? 'border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/10'
                : 'border-gray-200 dark:border-gray-800 bg-gray-100 dark:bg-gray-900 text-gray-400 cursor-not-allowed'
            }`}
          >
            <Activity size={16} />
            {t('obs_grafana', 'Grafana')}
          </a>
          {isOperator() && (
            <button
              onClick={handleSync}
              disabled={syncing || !isManaged}
              className={`h-10 min-w-[150px] flex items-center justify-center gap-2 px-4 text-white text-sm font-bold rounded-lg transition-all shadow-lg
                ${syncing || !isManaged ? 'bg-indigo-400 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 shadow-indigo-500/20'}`}
            >
              <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
              {syncing ? t('device_detail_syncing', 'Syncing...') : t('device_detail_sync_device', 'Sync Device')}
            </button>
          )}
        </div>
      </div>

      {!isManaged && (
        <SectionCard className="p-4 mb-6 border border-amber-200 dark:border-amber-900/40 bg-amber-50/80 dark:bg-amber-900/10">
          <div className="flex items-start gap-3">
            <AlertTriangle size={18} className="text-amber-600 mt-0.5" />
            <div>
              <div className="text-sm font-bold text-amber-800 dark:text-amber-200">
                {t('device_detail_discovered_only_title', 'This asset is visible, but not actively managed.')}
              </div>
              <div className="text-xs text-amber-700 dark:text-amber-300 mt-1">
                {t(
                  'device_detail_discovered_only_desc',
                  'NetSphere Free keeps all discovered assets visible in inventory and topology. Active monitoring, alerts, diagnosis, sync, and observability are enabled only for managed nodes within the Free limit.',
                )}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => navigate('/edition/compare')}
                  className="inline-flex items-center gap-2 rounded-xl border border-amber-300 bg-white/80 px-3 py-2 text-xs font-bold text-amber-800 hover:bg-amber-100 dark:border-amber-900/50 dark:bg-black/10 dark:text-amber-200 dark:hover:bg-amber-900/20"
                >
                  {t('device_detail_discovered_only_cta', 'See how Pro expands active operations')}
                </button>
              </div>
            </div>
          </div>
        </SectionCard>
      )}

      <SectionCard className="p-4 mb-6" data-testid="device-detail-ops-review-panel">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-sm font-bold text-gray-500 uppercase mb-2 flex items-center gap-2">
              <WorkflowIcon size={16} /> {t('device_detail_ops_review_title', 'Operational Setup Review')}
            </h3>
            <div className="text-sm text-gray-600 dark:text-gray-300 max-w-3xl">
              {t(
                'device_detail_ops_review_desc',
                'Use device detail as an operating checkpoint: confirm management scope, site ownership, monitoring profile, and service context before you move into monitoring or change work.',
              )}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => navigate('/discovery')}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-2 text-xs font-bold text-gray-700 dark:text-gray-100"
            >
              <Search size={14} />
              {t('device_detail_open_discovery_review', 'Open Discovery Review')}
            </button>
            <button
              type="button"
              onClick={() => navigate('/sites')}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-2 text-xs font-bold text-gray-700 dark:text-gray-100"
            >
              <Radio size={14} />
              {t('device_detail_open_sites', 'Open Sites')}
            </button>
            <button
              type="button"
              onClick={() => navigate('/service-groups')}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-2 text-xs font-bold text-gray-700 dark:text-gray-100"
            >
              <Users size={14} />
              {t('device_detail_open_service_groups', 'Open Service Groups')}
            </button>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">
              {t('device_detail_ops_review_management', 'Management Scope')}
            </div>
            <div className="mt-2 text-sm font-black text-gray-900 dark:text-gray-100">
              {isManaged ? t('devices_filter_managed', 'Managed') : t('devices_filter_discovered_only', 'Discovered Only')}
            </div>
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              {isManaged
                ? t('device_detail_ops_review_management_managed_desc', 'Active monitoring, sync, and observability are available for this device.')
                : t('device_detail_ops_review_management_discovered_desc', 'This device stays visible in inventory and topology, but active operations stay limited until it is promoted.')}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">
              {t('device_detail_ops_review_site', 'Site Ownership')}
            </div>
            <div className="mt-2 text-sm font-black text-gray-900 dark:text-gray-100">
              {device.site_id ? `${t('device_detail_site_prefix', 'Site')} #${device.site_id}` : t('device_detail_unassigned', 'Unassigned')}
            </div>
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              {device.site_id
                ? t('device_detail_ops_review_site_assigned_desc', 'Site ownership is already assigned and will follow observability and service reporting scope.')
                : t('device_detail_ops_review_site_unassigned_desc', 'Assign a site so observability, reports, and service context stay organized.')}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">
              {t('device_detail_ops_review_profile', 'Monitoring Profile')}
            </div>
            <div className="mt-2 text-sm font-black text-gray-900 dark:text-gray-100">
              {monitoringProfile?.name || t('device_detail_ops_review_profile_missing_title', 'No recommendation yet')}
            </div>
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              {monitoringProfile
                ? t('device_detail_ops_review_profile_ready_desc', 'Telemetry behavior is defined and can be refined from the monitoring profile catalog.')
                : t('device_detail_ops_review_profile_missing_desc', 'Refresh or assign a monitoring profile before relying on this device for steady monitoring.')}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">
              {t('device_detail_ops_review_service', 'Service Context')}
            </div>
            <div className="mt-2 text-sm font-black text-gray-900 dark:text-gray-100">
              {t('device_detail_ops_review_service_pending', 'Review in Service Groups')}
            </div>
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              {t(
                'device_detail_ops_review_service_desc',
                'Use Service Groups to connect this device to a business or technical service before reports and approvals depend on that context.',
              )}
            </div>
          </div>
        </div>
      </SectionCard>

      {/* 2. KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KpiCard icon={<Cpu className="text-blue-500" />} title={t('device_detail_cpu_usage', 'CPU Usage')} value={`${lastMetric.cpu_usage}%`} sub={t('device_detail_current_load', 'Current Load')} />
        <KpiCard icon={<Activity className="text-purple-500" />} title={t('device_detail_memory', 'Memory')} value={`${lastMetric.memory_usage}%`} sub={t('device_detail_used', 'Used')} />
        <KpiCard icon={<Clock className="text-green-500" />} title={t('device_detail_uptime', 'Uptime')} value={device.uptime || "0d 0h"} sub={t('device_detail_since_reboot', 'Since Reboot')} />
        <KpiCard icon={<Network className="text-orange-500" />} title={t('device_detail_ports', 'Ports')} value={device.interfaces?.length || 0} sub={t('device_detail_total_ports', 'Total Ports')} />
        {device.latest_parsed_data?.wireless && (
          <>
            <KpiCard
              icon={<Wifi className="text-emerald-500" />}
              title={t('device_detail_active_aps', 'Active APs')}
              value={`${device.latest_parsed_data.wireless.up_aps || 0} / ${device.latest_parsed_data.wireless.total_aps || 0}`}
              sub={t('device_detail_registration_status', 'Registration Status')}
            />
            <KpiCard
              icon={<Users className="text-pink-500" />}
              title={t('device_detail_wireless_clients', 'Wireless Clients')}
              value={device.latest_parsed_data.wireless.total_clients || 0}
              sub={t('device_detail_connected_everywhere', 'Connected Everywhere')}
            />
          </>
        )}
      </div>

      {/* 2.5 Device Info Panel */}
      <SectionCard className="p-4 mb-6">
        <h3 className="text-sm font-bold text-gray-500 uppercase mb-3 flex items-center gap-2">
          <Server size={16} /> {t('device_detail_device_information', 'Device Information')}
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 text-sm">
          <InfoItem label={t('device_detail_info_hostname', 'Hostname')} value={device.hostname || t('device_detail_unknown', 'Unknown')} />
          <InfoItem label={t('device_detail_info_model', 'Model')} value={device.model || t('device_detail_unknown', 'Unknown')} />
          <InfoItem label={t('device_detail_info_os_version', 'OS Version')} value={device.os_version || t('device_detail_unknown', 'Unknown')} />
          <InfoItem label={t('device_detail_info_serial_number', 'Serial Number')} value={device.serial_number || t('settings_not_available', 'N/A')} />
          <InfoItem label={t('device_detail_info_device_type', 'Device Type')} value={device.device_type?.toUpperCase() || 'CISCO_IOS'} />
          <InfoItem label={t('device_detail_info_site', 'Site')} value={device.site_id ? `${t('device_detail_site_prefix', 'Site')} #${device.site_id}` : t('device_detail_unassigned', 'Unassigned')} />
        </div>
      </SectionCard>

      <SectionCard className="p-4 mb-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h3 className="text-sm font-bold text-gray-500 uppercase mb-2 flex items-center gap-2">
              <Tag size={16} /> {t('device_detail_monitoring_profile_title', 'Monitoring Profile')}
            </h3>
            <div className="text-sm text-gray-600 dark:text-gray-300 max-w-3xl">
              {t(
                'device_detail_monitoring_profile_desc',
                'Monitoring profiles translate discovery context into actual polling and telemetry behavior. They stay visible even for discovered-only nodes so operators can see what will activate when a slot is promoted.',
              )}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => navigate('/monitoring-profiles')}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-2 text-xs font-bold text-gray-700 dark:text-gray-100"
            >
              <Tag size={14} />
              {t('device_detail_open_monitoring_profiles', 'Open Monitoring Profiles')}
            </button>
            {canOperateProfiles && (
              <button
                onClick={handleRecomputeMonitoringProfile}
                disabled={profileBusy}
                className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-2 text-xs font-bold text-blue-700 disabled:opacity-60 dark:border-blue-900/40 dark:bg-blue-900/10 dark:text-blue-300"
              >
                <RefreshCw size={14} className={profileBusy ? 'animate-spin' : ''} />
                {t('device_detail_recompute_profile', 'Recompute Recommendation')}
              </button>
            )}
          </div>
        </div>

        {monitoringProfile ? (
          <div className="mt-4 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4">
            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] p-4">
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-lg font-bold text-gray-900 dark:text-gray-100">{monitoringProfile.name}</div>
                <span className="inline-flex rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[10px] font-bold uppercase text-blue-700 dark:border-blue-900/40 dark:bg-blue-900/10 dark:text-blue-300">
                  {monitoringProfile.telemetry_mode || t('common_unknown', 'Unknown')}
                </span>
                <span
                  className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${
                    monitoringProfile.activation_state === 'active'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-900/10 dark:text-emerald-300'
                      : monitoringProfile.activation_state === 'ready_when_managed'
                        ? 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/40 dark:bg-amber-900/10 dark:text-amber-300'
                        : 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900/30 dark:text-slate-300'
                  }`}
                >
                  {monitoringProfile.activation_state || t('common_unknown', 'Unknown')}
                </span>
              </div>
              <div className="mt-2 text-sm text-gray-500 dark:text-gray-400 font-mono">{monitoringProfile.key}</div>
              <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <InfoItem label={t('device_detail_profile_assignment_source', 'Assignment')} value={monitoringProfile.assignment_source || t('common_unknown', 'Unknown')} />
                <InfoItem label={t('device_detail_profile_confidence', 'Confidence')} value={monitoringProfile.confidence != null ? `${monitoringProfile.confidence}` : t('common_unknown', 'Unknown')} />
                <InfoItem label={t('device_detail_profile_polling', 'Polling')} value={monitoringProfile.polling_interval_override ? `${monitoringProfile.polling_interval_override}s` : t('settings_not_available', 'N/A')} />
                <InfoItem label={t('device_detail_profile_status_interval', 'Status')} value={monitoringProfile.status_interval_override ? `${monitoringProfile.status_interval_override}s` : t('settings_not_available', 'N/A')} />
              </div>
              <div className="mt-4">
                <div className="text-xs uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400 font-bold mb-2">
                  {t('device_detail_profile_reasons', 'Why this profile matched')}
                </div>
                <div className="flex flex-wrap gap-2">
                  {(monitoringProfile.recommendation_reasons || []).length > 0 ? (
                    monitoringProfile.recommendation_reasons.map((reason) => (
                      <span
                        key={reason}
                        className="inline-flex rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#16181b] px-2 py-1 text-[11px] font-semibold text-gray-600 dark:text-gray-300"
                      >
                        {reason}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {t('device_detail_profile_no_reasons', 'No recommendation reasons were recorded.')}
                    </span>
                  )}
                </div>
              </div>
              {(monitoringProfile.dashboard_tags || []).length > 0 ? (
                <div className="mt-4">
                  <div className="text-xs uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400 font-bold mb-2">
                    {t('device_detail_profile_tags', 'Dashboard Tags')}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {monitoringProfile.dashboard_tags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex rounded-full border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-900/10 px-2 py-1 text-[11px] font-semibold text-sky-700 dark:text-sky-300"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">
                {t('device_detail_profile_policy_actions', 'Profile Actions')}
              </div>
              <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                {t(
                  'device_detail_profile_policy_actions_desc',
                  'Operators can override the automatic recommendation for this node. Manual overrides stay in place until you recompute or choose a new profile.',
                )}
              </div>

              {canOperateProfiles ? (
                <>
                  <div className="mt-4">
                    <div className="text-xs font-bold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400 mb-2">
                      {t('device_detail_profile_select_label', 'Assigned Profile')}
                    </div>
                    <select
                      value={profileSelection}
                      onChange={(event) => {
                        setProfileSelection(event.target.value);
                        setProfileSelectionDirty(true);
                      }}
                      className="w-full rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] px-4 py-3 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
                    >
                      <option value="">{t('device_detail_profile_select_placeholder', 'Select a monitoring profile')}</option>
                      {profileCatalog.map((profile) => (
                        <option key={profile.id} value={profile.id}>
                          {profile.name} ({profile.key})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      onClick={handleAssignMonitoringProfile}
                      disabled={profileBusy || !profileSelection}
                      className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-60"
                    >
                      <Tag size={14} />
                      {t('device_detail_profile_assign_cta', 'Assign Profile')}
                    </button>
                  </div>
                </>
              ) : (
                <div className="mt-4 text-xs font-semibold text-amber-700 dark:text-amber-300">
                  {t('device_detail_profile_viewer_note', 'Viewer access can review the recommendation, but operators manage overrides.')}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="mt-4 rounded-2xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
            {t('device_detail_profile_empty', 'No monitoring profile recommendation is available for this device yet.')}
          </div>
        )}
      </SectionCard>

      {/* 3. Tabs */}
      <div className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden flex flex-col flex-1 min-h-[420px]">
        <div className="flex border-b border-gray-200 dark:border-gray-800 overflow-x-auto custom-scrollbar">
          <TabBtn active={activeTab === 'interfaces'} onClick={() => setActiveTab('interfaces')} icon={<Server size={16} />} label={t('device_detail_tab_interfaces', 'Interfaces')} />
          {device.latest_parsed_data?.wireless && (
            <TabBtn active={activeTab === 'wireless'} onClick={() => setActiveTab('wireless')} icon={<Radio size={16} />} label={t('device_detail_tab_wireless', 'Wireless Summary')} />
          )}
          <TabBtn active={activeTab === 'inventory'} onClick={() => setActiveTab('inventory')} icon={<ListFilter size={16} />} label={t('device_detail_tab_inventory', 'Inventory')} />
          <TabBtn active={activeTab === 'config'} onClick={() => setActiveTab('config')} icon={<FileText size={16} />} label={t('device_detail_tab_running_config', 'Running Config')} />
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {activeTab === 'interfaces' && (
            <InterfaceTable interfaces={device.interfaces || []} />
          )}

          {activeTab === 'wireless' && device.latest_parsed_data?.wireless && (
            <WirelessSummary data={device.latest_parsed_data.wireless} />
          )}

          {activeTab === 'inventory' && (
            <div className="p-6 flex-1 overflow-auto">
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-bold text-gray-600 dark:text-gray-300">{t('device_detail_inventory_title', 'Chassis / Modules (ENTITY-MIB)')}</div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleExportInventory('xlsx')}
                    disabled={exportingInventory}
                    className="px-3 py-1.5 text-xs font-bold rounded bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    {t('device_detail_export_xlsx', 'Export XLSX')}
                  </button>
                  <button
                    onClick={() => handleExportInventory('pdf')}
                    disabled={exportingInventory}
                    className="px-3 py-1.5 text-xs font-bold rounded bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    {t('device_detail_export_pdf', 'Export PDF')}
                  </button>
                  <button
                    onClick={async () => {
                      setInventoryLoading(true);
                      try {
                        const res = await DeviceService.getInventory(id);
                        setInventory(Array.isArray(res.data) ? res.data : []);
                      } finally {
                        setInventoryLoading(false);
                      }
                    }}
                    className="px-3 py-1.5 text-xs font-bold rounded bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-700"
                  >
                    <RefreshCw size={14} className={inventoryLoading ? "animate-spin inline mr-2" : "inline mr-2"} />
                    {t('common_refresh', 'Refresh')}
                  </button>
                </div>
              </div>

              {inventoryLoading && <InlineLoading label={t('device_detail_inventory_loading', 'Loading inventory...')} />}

              {!inventoryLoading && inventory.length === 0 && (
                <InlineEmpty label={t('device_detail_inventory_empty', 'No inventory data. Run Sync Device, and ensure SNMP community is correct.')} />
              )}

              {!inventoryLoading && inventory.length > 0 && (
                <InventoryTree
                  items={inventory}
                  openMap={inventoryTreeOpen}
                  setOpenMap={setInventoryTreeOpen}
                />
              )}
            </div>
          )}

          {activeTab === 'config' && (
            <div className="p-6 flex-1 overflow-auto">
              <div className="h-full bg-[#282c34] text-gray-300 p-4 rounded-lg font-mono text-xs overflow-auto whitespace-pre leading-relaxed border border-gray-700">
                {device.config_backups && device.config_backups.length > 0
                  ? device.config_backups[device.config_backups.length - 1].raw_config
                  : `// ${t('device_detail_config_backup_missing', 'No configuration backup found.')}\n// ${t('device_detail_config_sync_hint', "Click 'Sync Device' to fetch the latest configuration.")}`}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// --- Sub Components ---

const TabBtn = ({ active, onClick, icon, label }) => (
  <button
    onClick={onClick}
    className={`px-6 py-4 text-sm font-bold flex items-center gap-2 border-b-2 transition-colors shrink-0 whitespace-nowrap ${active ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400' : 'border-transparent text-gray-500 hover:text-gray-700'
      }`}
  >
    {icon} {label}
  </button>
);

const KpiCard = ({ icon, title, value, sub }) => (
  <div className="bg-white dark:bg-[#1b1d1f] p-4 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm flex items-center gap-4">
    <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">{icon}</div>
    <div>
      <p className="text-xs text-gray-500 font-bold uppercase">{title}</p>
      <h3 className="text-xl font-bold text-gray-900 dark:text-white">{value}</h3>
      <p className="text-xs text-gray-400">{sub}</p>
    </div>
  </div>
);

const InfoItem = ({ label, value }) => (
  <div>
    <p className="text-xs text-gray-400 uppercase font-medium">{label}</p>
    <p className="text-gray-900 dark:text-white font-medium truncate" title={value}>{value}</p>
  </div>
);

const InterfaceTable = ({ interfaces }) => {
  const [filter, setFilter] = useState('all'); // all, up, down, admin_down
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all'); // all, physical, virtual, vlan

  const stats = useMemo(() => {
    return {
      total: interfaces.length,
      up: interfaces.filter(i => i.status?.toLowerCase() === 'up').length,
      down: interfaces.filter(i => i.status?.toLowerCase() === 'down').length,
      adminDown: interfaces.filter(i => i.status?.toLowerCase() === 'admin_down').length,
    };
  }, [interfaces]);

  const filteredInterfaces = useMemo(() => {
    return interfaces.filter(iface => {
      const matchStatus = filter === 'all' || iface.status?.toLowerCase() === filter;
      const matchSearch = iface.name.toLowerCase().includes(search.toLowerCase()) ||
        (iface.description && iface.description.toLowerCase().includes(search.toLowerCase()));

      let matchType = true;
      if (typeFilter === 'physical') {
        matchType = /Ethernet|Gigabit|TenGigabit|FastEthernet/i.test(iface.name) && !/Vlan|Loopback|Port-channel/i.test(iface.name);
      } else if (typeFilter === 'vlan') {
        matchType = /Vlan/i.test(iface.name);
      } else if (typeFilter === 'virtual') {
        matchType = /Loopback|Port-channel|Tunnel/i.test(iface.name);
      }

      return matchStatus && matchSearch && matchType;
    });
  }, [interfaces, filter, search, typeFilter]);

  if (interfaces.length === 0) {
    return (
      <div className="p-6 h-full flex flex-col items-center justify-center text-gray-500">
        <Server size={48} className="mb-4 opacity-20" />
        <p>{t('device_detail_interfaces_empty', 'No interface data available. Please sync the device.')}</p>
      </div>
    );
  }

  const renderStatus = (status) => {
    const s = status?.toLowerCase() || '';
    if (s === 'admin_down') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-500 border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
          <Slash size={10} /> {t('device_detail_status_admin_down', 'ADMIN DOWN')}
        </span>
      );
    }
    if (s === 'up') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-green-50 text-green-600 border border-green-200 dark:bg-green-900/20 dark:text-green-400 dark:border-green-800">
          <CheckCircle size={10} /> {t('device_detail_status_up', 'UP')}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-red-50 text-red-600 border border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800">
        <AlertTriangle size={10} /> {t('device_detail_status_down', 'DOWN')}
      </span>
    );
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 1. Summary Bar */}
      <div className="px-6 py-4 bg-gray-50 dark:bg-[#151719] border-b border-gray-200 dark:border-gray-800 flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">{t('device_detail_summary', 'Summary')}:</span>
          <div className="flex gap-3">
            <span className="text-sm font-bold text-gray-900 dark:text-white">{stats.total} {t('device_detail_total', 'total')}</span>
            <span className="text-sm font-bold text-green-500">{stats.up} {t('device_detail_up', 'up')}</span>
            <span className="text-sm font-bold text-red-500">{stats.down} {t('device_detail_down', 'down')}</span>
            <span className="text-sm font-bold text-gray-500">{stats.adminDown} {t('device_detail_disabled', 'disabled')}</span>
          </div>
        </div>

        <div className="h-4 w-px bg-gray-300 dark:bg-gray-700 hidden md:block" />

        <div className="flex-1 flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-4 min-w-0">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
            <input
              type="text"
              placeholder={t('device_detail_search_interfaces', 'Search interfaces...')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all font-medium"
            />
          </div>

          <div className="flex flex-nowrap overflow-x-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-0.5 shadow-sm">
            <FilterBtn active={filter === 'all'} onClick={() => setFilter('all')} label={t('device_detail_filter_all', 'All')} />
            <FilterBtn active={filter === 'up'} onClick={() => setFilter('up')} label={t('device_detail_filter_up', 'Up')} />
            <FilterBtn active={filter === 'down'} onClick={() => setFilter('down')} label={t('device_detail_filter_down', 'Down')} />
            <FilterBtn active={filter === 'admin_down'} onClick={() => setFilter('admin_down')} label={t('device_detail_filter_disabled', 'Disabled')} />
          </div>

          <div className="flex flex-nowrap overflow-x-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-0.5 shadow-sm">
            <FilterBtn active={typeFilter === 'all'} onClick={() => setTypeFilter('all')} label={t('device_detail_filter_all_types', 'All Types')} />
            <FilterBtn active={typeFilter === 'physical'} onClick={() => setTypeFilter('physical')} label={t('device_detail_filter_physical', 'Physical')} />
            <FilterBtn active={typeFilter === 'vlan'} onClick={() => setTypeFilter('vlan')} label="VLAN" />
            <FilterBtn active={typeFilter === 'virtual'} onClick={() => setTypeFilter('virtual')} label={t('device_detail_filter_logical', 'Logical')} />
          </div>
        </div>
      </div>

      {/* 2. Table Context */}
      <div className="flex-1 overflow-auto p-6 pt-0">
        <table className="w-full text-left border-collapse text-sm">
          <thead className="sticky top-0 bg-white dark:bg-[#1b1d1f] z-10 shadow-[0_1px_0_0_rgba(0,0,0,0.1)] dark:shadow-[0_1px_0_0_rgba(255,255,255,0.05)]">
            <tr>
              <th className="py-4 px-4 font-bold text-gray-500 uppercase tracking-tighter text-[11px] w-48">{t('device_detail_col_interface', 'Interface')}</th>
              <th className="py-4 px-4 font-bold text-gray-500 uppercase tracking-tighter text-[11px] w-32 text-center">{t('device_detail_col_status', 'Status')}</th>
              <th className="py-4 px-4 font-bold text-gray-500 uppercase tracking-tighter text-[11px] w-24 text-center">{t('device_detail_col_mode', 'Mode')}</th>
              <th className="py-4 px-4 font-bold text-gray-500 uppercase tracking-tighter text-[11px] w-40">{t('device_detail_col_info', 'Info')}</th>
              <th className="py-4 px-4 font-bold text-gray-500 uppercase tracking-tighter text-[11px]">{t('device_detail_col_description', 'Description')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {filteredInterfaces.length > 0 ? filteredInterfaces.map((iface) => (
              <tr key={iface.id} className="hover:bg-gray-50/80 dark:hover:bg-white/[0.02] transition-colors group">
                <td className="py-3.5 px-4">
                  <div className="flex flex-col">
                    <span className="font-mono font-bold text-gray-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                      {iface.name}
                    </span>
                    <span className="text-[10px] text-gray-400 font-medium">
                      {iface.name.toLowerCase().includes('gigabit') ? '1 Gbps' : iface.name.toLowerCase().includes('tengigabit') ? '10 Gbps' : t('settings_not_available', 'N/A')}
                    </span>
                  </div>
                </td>
                <td className="py-3.5 px-4 text-center">
                  {renderStatus(iface.status)}
                </td>
                <td className="py-3.5 px-4 text-center">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${iface.mode === 'trunk' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' :
                    iface.mode === 'routed' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                      'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                    }`}>
                    {iface.mode || t('device_detail_access', 'Access')}
                  </span>
                </td>
                <td className="py-3.5 px-4">
                  <div className="font-mono text-xs flex flex-col gap-0.5">
                    {iface.ip_address ? (
                      <span className="text-blue-600 dark:text-blue-400 font-bold">{iface.ip_address}</span>
                    ) : (
                      <span className="text-gray-500 flex items-center gap-1">
                        <Tag size={10} className="opacity-40" />
                        VLAN {iface.vlan || 1}
                      </span>
                    )}
                    {iface.mac_address && (
                      <span className="text-[10px] text-gray-400 opacity-70 truncate max-w-[140px] uppercase">
                        {iface.mac_address}
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-3.5 px-4">
                  <div className="text-gray-600 dark:text-gray-400 italic text-sm truncate max-w-sm" title={iface.description}>
                    {iface.description || <span className="text-gray-300 dark:text-gray-700 not-italic">-</span>}
                  </div>
                </td>
              </tr>
            )) : (
              <tr>
                <td colSpan="5" className="py-20 text-center text-gray-400 italic">
                  {t('device_detail_interfaces_filter_empty', 'No interfaces match the current filter / search criteria.')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const InventoryTree = ({ items, openMap, setOpenMap }) => {
  const nodesById = useMemo(() => {
    const m = new Map();
    for (const it of items) {
      m.set(it.ent_physical_index, { ...it, children: [] });
    }
    for (const it of items) {
      const parentId = it.parent_index;
      if (parentId && m.has(parentId)) {
        m.get(parentId).children.push(m.get(it.ent_physical_index));
      }
    }
    return m;
  }, [items]);

  const roots = useMemo(() => {
    const rootList = [];
    for (const it of items) {
      const parentId = it.parent_index;
      if (!parentId || !nodesById.has(parentId)) {
        rootList.push(nodesById.get(it.ent_physical_index));
      }
    }
    const score = (n) => {
      const cls = String(n.class_name || '').toLowerCase();
      if (cls === 'chassis') return 0;
      if (cls === 'stack') return 1;
      if (cls === 'module') return 2;
      return 3;
    };
    rootList.sort((a, b) => score(a) - score(b) || a.ent_physical_index - b.ent_physical_index);
    return rootList;
  }, [items, nodesById]);

  const toggle = (id) => setOpenMap(prev => ({ ...prev, [id]: !prev[id] }));

  const renderNode = (n, depth) => {
    const hasChildren = (n.children || []).length > 0;
    const isOpen = !!openMap[n.ent_physical_index];
    const label = n.name || n.model_name || n.description || `Index ${n.ent_physical_index}`;
    const cls = n.class_name || n.class_id || '-';
    const secondary = [n.model_name, n.serial_number, n.mfg_name].filter(Boolean).join(' / ');

    return (
      <div key={n.ent_physical_index}>
        <div
          className="flex items-center gap-2 px-3 py-2 border border-gray-200 dark:border-gray-800 rounded-md bg-white dark:bg-[#1b1d1f] hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          style={{ marginLeft: depth * 14 }}
        >
          <button
            onClick={() => hasChildren && toggle(n.ent_physical_index)}
            className={`w-5 h-5 flex items-center justify-center rounded border ${hasChildren ? 'border-gray-300 dark:border-gray-700 hover:border-indigo-500' : 'border-transparent'}`}
            disabled={!hasChildren}
          >
            {hasChildren ? (isOpen ? '-' : '+') : ''}
          </button>

          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
            {cls}
          </span>

          <div className="min-w-0 flex-1">
            <div className="font-bold text-sm text-gray-900 dark:text-gray-100 truncate">{label}</div>
            {secondary && <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{secondary}</div>}
          </div>

          <span className="text-[11px] text-gray-400 font-mono">#{n.ent_physical_index}</span>
        </div>

        {hasChildren && isOpen && (
          <div className="mt-2 space-y-2">
            {n.children
              .slice()
              .sort((a, b) => (a.class_id || 999) - (b.class_id || 999) || a.ent_physical_index - b.ent_physical_index)
              .map((c) => renderNode(c, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-2">
      {roots.map((r) => renderNode(r, 0))}
    </div>
  );
};

const FilterBtn = ({ active, onClick, label }) => (
  <button
    onClick={onClick}
    className={`px-3 py-1.5 text-[11px] font-bold rounded-md transition-all ${active
      ? 'bg-indigo-600 text-white shadow-md'
      : 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700'
      }`}
  >
    {label}
  </button>
);

const WirelessSummary = ({ data }) => {
  const [search, setSearch] = useState('');

  const apList = data.ap_list || [];
  const wlanList = data.wlan_summary || [];

  const filteredAps = apList.filter(ap =>
    (ap.name || ap.ap_name || '').toLowerCase().includes(search.toLowerCase()) ||
    (ap.ip_address || '').includes(search)
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 1. Header & Quick Stats */}
      <div className="px-6 py-4 bg-gray-50 dark:bg-[#151719] border-b border-gray-200 dark:border-gray-800 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-6">
          <div className="flex flex-col">
            <span className="text-[10px] text-gray-400 font-bold uppercase">{t('device_detail_wlan_configured', 'WLANs Configured')}</span>
            <span className="text-lg font-black text-indigo-500">{wlanList.length} {t('device_detail_ssids', 'SSIDs')}</span>
          </div>
          <div className="h-8 w-px bg-gray-300 dark:bg-gray-700" />
          <div className="flex flex-col">
            <span className="text-[10px] text-gray-400 font-bold uppercase">{t('device_detail_active_clients', 'Active Clients')}</span>
            <span className="text-lg font-black text-pink-500">{data.total_clients} {t('device_detail_users', 'Users')}</span>
          </div>
        </div>

        <div className="relative w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
          <input
            type="text"
            placeholder={t('device_detail_search_aps', 'Search APs...')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all font-medium"
          />
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6 space-y-8">
        {/* Section 1: WLAN Summary */}
        <div className="space-y-3">
          <h4 className="text-xs font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
            <Wifi size={14} className="text-indigo-500" /> {t('device_detail_ssid_status', 'SSID / WLAN Status')}
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {wlanList.map((wl, idx) => (
              <div key={idx} className="bg-white dark:bg-[#1b1d1f] p-3 rounded-lg border border-gray-200 dark:border-gray-800 flex items-center justify-between shadow-sm">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-full ${wl.status === 'UP' || wl.status === 'Enabled' || wl.status === 'online' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500'}`}>
                    <Radio size={14} />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-gray-900 dark:text-white">{wl.ssid}</p>
                    <p className="text-[10px] text-gray-400">{t('device_detail_wlan_id_prefix', 'ID')}: {wl.id} / {wl.profile}</p>
                  </div>
                </div>
                <span className={`text-[10px] font-black px-1.5 py-0.5 rounded ${(wl.status === 'UP' || wl.status === 'Enabled' || wl.status === 'online') ? 'bg-emerald-500 text-white' : 'bg-red-500 text-white'}`}>
                  {wl.status}
                </span>
              </div>
            ))}
            {wlanList.length === 0 && (
              <div className="col-span-full py-4 text-center text-xs text-gray-500 italic bg-gray-50 dark:bg-gray-800/20 rounded-lg">
                {t('device_detail_wlan_empty', 'No WLAN configurations found.')}
              </div>
            )}
          </div>
        </div>

        {/* Section 2: AP Inventory */}
        <div className="space-y-3">
          <h4 className="text-xs font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
            <Server size={14} className="text-indigo-500" /> {t('device_detail_ap_inventory', 'Access Point Inventory')}
          </h4>
          <div className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-[720px] w-full text-left border-collapse text-sm">
                <thead className="bg-gray-50/50 dark:bg-gray-800/50">
                  <tr>
                    <th className="py-3 px-4 font-bold text-gray-500 text-[10px] uppercase">{t('device_detail_col_host_name', 'Host / Name')}</th>
                    <th className="py-3 px-4 font-bold text-gray-500 text-[10px] uppercase text-center">{t('device_detail_col_status', 'Status')}</th>
                    <th className="py-3 px-4 font-bold text-gray-500 text-[10px] uppercase">{t('device_detail_col_model_details', 'Model Details')}</th>
                    <th className="py-3 px-4 font-bold text-gray-500 text-[10px] uppercase">{t('device_detail_col_ip_network', 'IP / Network')}</th>
                    <th className="py-3 px-4 font-bold text-gray-500 text-[10px] uppercase">{t('device_detail_uptime', 'Uptime')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {filteredAps.map((ap, idx) => {
                    const name = ap.name || ap.ap_name || t('device_detail_unknown', 'Unknown');
                    const status = (ap.status || ap.state || '').toLowerCase();
                    const isUp = status.includes('up') || status.includes('reg') || status.includes('online');

                    return (
                      <tr key={idx} className="hover:bg-gray-50/80 dark:hover:bg-white/[0.02]">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2 font-bold text-gray-900 dark:text-white">
                            <Radio size={14} className={isUp ? "text-emerald-500" : "text-gray-400"} />
                            {name}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-center">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${isUp ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400' : 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400'
                            }`}>
                            {status || t('device_detail_unknown', 'Unknown')}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex flex-col">
                            <span className="text-xs text-gray-700 dark:text-gray-300 font-medium">{ap.model || 'Cisco AP'}</span>
                            <span className="text-[10px] text-gray-400 font-mono tracking-tighter">{t('device_detail_serial_prefix', 'SN')}: {ap.serial_number || t('settings_not_available', 'N/A')}</span>
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <div className="font-mono text-xs text-blue-600 dark:text-blue-400 flex flex-col">
                            {ap.ip_address || t('settings_not_available', 'N/A')}
                            <span className="text-[9px] text-gray-400 uppercase font-sans">{t('device_detail_management', 'Management')}</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-xs text-gray-500 uppercase font-medium">
                          {ap.uptime || t('settings_not_available', 'N/A')}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DeviceDetailPage;



