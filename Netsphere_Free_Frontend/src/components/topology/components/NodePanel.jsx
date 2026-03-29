import React from 'react';
import {
  X,
  Activity,
  Box,
  Shield,
  Wifi,
  Globe,
  Layers,
  ExternalLink,
  BarChart3,
  Server,
  GitBranch,
} from 'lucide-react';
import { t } from '../../../i18n';
import {
  getCloudResourceStatusMeta,
  getManagedDeviceStatusMeta,
} from '../../../utils/deviceStatusTone';

const safeText = (value, fallback = '--') => {
  if (value == null) return fallback;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || fallback;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return fallback;
};

const metricFormatter = (value, suffix = '%') => {
  if (value == null || value === '') return '--';
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '--';
  return `${numeric.toFixed(1)}${suffix}`;
};

const getIcon = (role) => {
  switch (String(role || '').toLowerCase()) {
    case 'core':
      return <Globe size={18} className="text-blue-400" />;
    case 'distribution':
      return <Layers size={18} className="text-cyan-400" />;
    case 'security':
      return <Shield size={18} className="text-rose-400" />;
    case 'wlc':
    case 'access_point':
      return <Wifi size={18} className="text-violet-400" />;
    default:
      return <Box size={18} className="text-slate-300" />;
  }
};

const actionButtonClass =
  'inline-flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold transition-colors';

const NodePanel = ({
  node,
  onClose,
  onOpenDevice,
  onOpenObservability,
  onOpenGrafana,
  canManageNodes,
  onPromoteManaged,
  onReleaseManaged,
  activeServiceGroup,
  onOpenServiceGroups,
  onOpenEditionCompare,
}) => {
  if (!node) return null;

  const data = node.data || {};
  const cloudStatusMeta = data.role === 'cloud'
    ? getCloudResourceStatusMeta(data.status, data?.cloud?.resource_type)
    : null;
  const deviceStatusMeta = data.role === 'cloud'
    ? null
    : getManagedDeviceStatusMeta(data.status, data.management_state);
  const statusMeta = cloudStatusMeta || deviceStatusMeta;
  const statusChipClass = statusMeta?.chipClass || '';
  const statusDotClass = statusMeta?.dotClass || '';
  const statusTextClass = statusMeta?.textClass || '';
  const statusLabel = statusMeta?.label || 'OFFLINE';
  const statusSummary = statusMeta?.summary || 'Attention Needed';
  const metrics = data.metrics || {};
  const resolvedDeviceId = data?.device_id ?? (data?.role !== 'cloud' ? node?.id : null);
  const canOpenDevice = resolvedDeviceId !== null && resolvedDeviceId !== undefined && String(resolvedDeviceId).trim() !== '';
  const managementState = String(data.management_state || 'managed').trim().toLowerCase();
  const isDiscoveredOnly = managementState === 'discovered_only';
  const managementBadgeClass = isDiscoveredOnly
    ? 'border-slate-500/30 bg-slate-500/10 text-slate-200'
    : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  const canOpenOperations = canOpenDevice && !isDiscoveredOnly;
  const serviceOverlayMatch = !!data?.serviceGroupMatch;
  const serviceGroupName = safeText(data?.serviceGroupName, '');

  const openDevice = () => {
    if (!canOpenDevice) return;
    onOpenDevice?.(resolvedDeviceId);
  };
  const openObservability = () => {
    if (!canOpenOperations) return;
    onOpenObservability?.(resolvedDeviceId, data.site_id);
  };
  const openGrafana = () => {
    if (!canOpenOperations) return;
    onOpenGrafana?.(resolvedDeviceId, data.site_id);
  };

  const l3 = data.l3 || {};
  const overlay = data.overlay || {};
  const hybrid = data.hybrid || {};
  const nodeTitle = safeText(data.node_label, safeText(data.label, safeText(node?.id)));
  const nodeIp = safeText(data.ip);
  const siteName = safeText(data.site_name, '');
  const vendor = safeText(data.vendor, '');
  const model = safeText(data.model);
  const version = safeText(data.version, '');
  const roleLabel = safeText(String(data.role || 'device').replace(/_/g, ' '), 'device');

  return (
    <div data-testid="topology-node-panel" className="absolute right-4 top-4 z-30 w-[340px] max-w-[calc(100%-2rem)] overflow-hidden rounded-2xl border border-slate-700/80 bg-[#13171c]/95 text-white shadow-2xl backdrop-blur">
      <div className="border-b border-slate-800 bg-gradient-to-r from-slate-900 via-slate-900 to-slate-800 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-700 bg-slate-800/80">
              {getIcon(data.icon_role || data.role)}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="truncate text-sm font-bold text-white" title={nodeTitle}>
                  {nodeTitle}
                </h3>
                <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusChipClass}`}>
                  <span className={`h-2 w-2 rounded-full ${statusDotClass}`}></span>
                  {statusLabel}
                </span>
                {data.role !== 'cloud' ? (
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${managementBadgeClass}`}>
                    {isDiscoveredOnly
                      ? t('devices_filter_discovered_only', 'Discovered Only')
                      : t('devices_filter_managed', 'Managed')}
                  </span>
                ) : null}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                <span className="font-mono">{nodeIp}</span>
                {siteName && (
                  <span className="rounded-full border border-slate-700 bg-slate-800/70 px-2 py-0.5">
                    {siteName}
                  </span>
                )}
                {vendor && (
                  <span className="uppercase tracking-wide text-slate-500">{vendor}</span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-full border border-slate-700 bg-slate-800/70 p-1.5 text-slate-300 transition-colors hover:bg-slate-700 hover:text-white"
            aria-label={t('common_cancel', 'Cancel')}
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="space-y-4 p-4">
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {t('obs_status', 'Status')}
            </div>
            <div className={`mt-2 text-sm font-bold ${statusTextClass}`}>
              {statusSummary}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {t('topology_role', 'Role')}
            </div>
            <div className="mt-2 text-sm font-bold text-slate-100">
              {roleLabel}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">CPU</div>
            <div className="mt-2 text-sm font-bold text-slate-100">{metricFormatter(metrics.cpu)}</div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Memory</div>
            <div className="mt-2 text-sm font-bold text-slate-100">{metricFormatter(metrics.memory)}</div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-3">
          <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            <Activity size={13} />
            {t('obs_issue_live_snapshot', 'Live Snapshot')}
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2">
              <div className="text-slate-500">In</div>
              <div className="mt-1 font-semibold text-slate-100">{metricFormatter(metrics.traffic_in, ' bps')}</div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2">
              <div className="text-slate-500">Out</div>
              <div className="mt-1 font-semibold text-slate-100">{metricFormatter(metrics.traffic_out, ' bps')}</div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2">
              <div className="text-slate-500">{t('topology_vendor', 'Vendor')}</div>
              <div className="mt-1 truncate font-semibold text-slate-100" title={vendor}>{vendor || '--'}</div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2">
              <div className="text-slate-500">{t('topology_model', 'Model')}</div>
              <div className="mt-1 truncate font-semibold text-slate-100" title={model}>{model}</div>
            </div>
          </div>
          {version && version !== '--' && (
            <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs">
              <div className="text-slate-500">{t('topology_version', 'Version')}</div>
              <div className="mt-1 truncate font-semibold text-slate-100" title={version}>
                {version}
              </div>
            </div>
          )}
        </div>

        {canOpenDevice && isDiscoveredOnly ? (
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-200">
              {t('topology_discovered_only_title', 'Discovered Only')}
            </div>
            <div className="mt-2 text-xs leading-5 text-amber-50/90">
              {t(
                'topology_discovered_only_desc',
                'This asset remains visible in topology, but active monitoring, alerts, diagnosis, sync, and observability are disabled until a managed slot is assigned.',
              )}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {canManageNodes ? (
                <button
                  onClick={() => onPromoteManaged?.(resolvedDeviceId)}
                  className={`${actionButtonClass} border-emerald-500/30 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/20`}
                >
                  {t('devices_promote_managed', 'Make Managed')}
                </button>
              ) : null}
              <button
                onClick={() => onOpenEditionCompare?.()}
                className={`${actionButtonClass} border-amber-500/30 bg-transparent text-amber-100 hover:bg-amber-500/10`}
              >
                {t('topology_discovered_only_cta', 'Compare Free and Pro')}
              </button>
            </div>
          </div>
        ) : null}

        {canOpenDevice && !isDiscoveredOnly && canManageNodes ? (
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                  {t('devices_filter_managed', 'Managed')}
                </div>
                <div className="mt-1 text-xs text-emerald-50/85">
                  {t(
                    'topology_managed_node_desc',
                    'This node currently uses one NetSphere Free managed slot for active monitoring, alerts, and diagnosis.',
                  )}
                </div>
              </div>
              <button
                onClick={() => onReleaseManaged?.(resolvedDeviceId)}
                className={`${actionButtonClass} border-amber-500/30 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20`}
              >
                {t('devices_release_slot', 'Release Slot')}
              </button>
              <button
                onClick={() => onOpenEditionCompare?.()}
                className={`${actionButtonClass} border-emerald-500/30 bg-transparent text-emerald-100 hover:bg-emerald-500/10`}
              >
                {t('topology_managed_node_cta', 'See what Pro unlocks next')}
              </button>
            </div>
          </div>
        ) : null}

        {(l3.total || overlay.total || hybrid.total) ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-3">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {t('topology_context', 'Topology Context')}
            </div>
            <div className="flex flex-wrap gap-2 text-[11px]">
              {l3.total > 0 && (
                <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2.5 py-1 font-semibold text-violet-200">
                  L3 {l3.healthy || 0}/{l3.total}
                </span>
              )}
              {overlay.total > 0 && (
                <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 font-semibold text-cyan-200">
                  VXLAN {overlay.healthy || 0}/{overlay.total}
                </span>
              )}
              {hybrid.total > 0 && (
                <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2.5 py-1 font-semibold text-sky-200">
                  HY {hybrid.total}
                </span>
              )}
              {l3.primaryAs && (
                <span className="rounded-full border border-slate-700 bg-slate-950/70 px-2.5 py-1 font-semibold text-slate-200">
                  {l3.primaryAs}
                </span>
              )}
              {overlay.transportLabel && (
                <span className="rounded-full border border-slate-700 bg-slate-950/70 px-2.5 py-1 font-semibold text-slate-200">
                  {overlay.transportLabel}
                </span>
              )}
            </div>
          </div>
        ) : null}

        {serviceOverlayMatch && activeServiceGroup ? (
          <div className="rounded-2xl border p-3" style={{ borderColor: `${activeServiceGroup.color}55`, background: `${activeServiceGroup.color}12` }}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em]" style={{ color: activeServiceGroup.color }}>
                  {t('topology_service_overlay_title', 'Service Map')}
                </div>
                <div className="mt-1 text-sm font-bold text-white">
                  {serviceGroupName || activeServiceGroup.name}
                </div>
                <div className="mt-1 text-xs text-slate-200/85">
                  {t('topology_service_overlay_panel_desc', 'This node is currently highlighted as part of the selected service group overlay.')}
                </div>
              </div>
              <button
                onClick={() => onOpenServiceGroups?.()}
                className={`${actionButtonClass} border-slate-700 bg-slate-900/70 text-slate-100 hover:bg-slate-800`}
              >
                <GitBranch size={14} />
                {t('topology_service_overlay_open_groups', 'Open Service Groups')}
              </button>
            </div>
          </div>
        ) : null}

        {canOpenDevice ? (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <button
              onClick={openDevice}
              className={`${actionButtonClass} border-slate-700 bg-slate-800/80 text-slate-100 hover:bg-slate-700`}
            >
              <Server size={14} />
              {t('obs_open_device', 'Open Device')}
            </button>
            <button
              onClick={openObservability}
              disabled={!canOpenOperations}
              className={`${actionButtonClass} border-cyan-500/30 bg-cyan-500/10 text-cyan-100 hover:bg-cyan-500/20 ${!canOpenOperations ? 'cursor-not-allowed opacity-50 hover:bg-cyan-500/10' : ''}`}
            >
              <BarChart3 size={14} />
              {t('common_open_observability', 'Open Observability')}
            </button>
            <button
              onClick={openGrafana}
              disabled={!canOpenOperations}
              className={`${actionButtonClass} border-violet-500/30 bg-violet-500/10 text-violet-100 hover:bg-violet-500/20 ${!canOpenOperations ? 'cursor-not-allowed opacity-50 hover:bg-violet-500/10' : ''}`}
            >
              <ExternalLink size={14} />
              Grafana
            </button>
          </div>
        ) : (
          <div className="rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2 text-[11px] text-slate-400">
            {t('topology_cloud_resource_panel_hint', 'This topology node is an infrastructure resource. Use the map or cloud detail view for provider context.')}
          </div>
        )}

        <div className="rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2 text-[11px] text-slate-400">
          {t('topology_node_panel_hint', 'Single-click keeps you in the map. Double-click opens Device Detail directly.')}
        </div>
      </div>
    </div>
  );
};

export default NodePanel;
