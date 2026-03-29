import React from 'react';
import { Cloud, ExternalLink, GitBranch, Settings2, XCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { t } from '../../../i18n';
import { buildCloudIntentPath } from '../../../utils/cloudIntentLinks';
import { buildTopologyPath } from '../../../utils/observabilityLinks';

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

const formatDateTime = (value) => {
  if (!value) return '--';
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return safeText(value);
    return new Intl.DateTimeFormat('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(date);
  } catch (e) {
    return safeText(value);
  }
};

const metricCard = (label, value, tone = 'slate') => (
  <div className={`rounded border px-2 py-1 ${tone}`}>
    <div className="text-[11px] text-gray-400">{label}</div>
    <div className="font-bold text-sm text-white">{value}</div>
  </div>
);

const freshnessLabel = (value) => {
  if (!value) return '';
  try {
    const syncedAt = new Date(value);
    if (Number.isNaN(syncedAt.getTime())) return '';
    const diffSeconds = Math.max(0, Math.floor((Date.now() - syncedAt.getTime()) / 1000));
    if (diffSeconds < 120) return 'fresh';
    if (diffSeconds < 900) return 'recent';
    return 'stale';
  } catch (e) {
    return '';
  }
};

const CloudDetailPanel = ({ cloudDetailPanel, setCloudDetailPanel }) => {
  const navigate = useNavigate();
  if (!(cloudDetailPanel?.open && cloudDetailPanel?.node)) return null;

  return (
    <div className="absolute bottom-4 right-4 z-30 m-0 w-[min(36rem,calc(100vw-2rem))] max-w-[calc(100%-2rem)]">
      <div data-testid="cloud-detail-panel" className="bg-[#1b1d1f] border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-4 text-white">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-bold flex items-center gap-2">
            <Cloud size={18} className="text-sky-400" /> {t('cloud_detail_title', 'Cloud Peer Detail')}
          </h3>
          <button onClick={() => setCloudDetailPanel({ open: false, node: null })}>
            <XCircle size={18} className="text-gray-500 hover:text-white" />
          </button>
        </div>
        {(() => {
          const n = cloudDetailPanel.node;
          const cloud = n?.data?.cloud || {};
          const hybrid = n?.data?.hybrid || {};
          const ev = n?.data?.evidence || {};
          const provider = safeText(cloud?.provider || ev?.provider || 'cloud', 'cloud').toUpperCase();
          const ip = safeText(n?.data?.ip, '');
          const asn = safeText(cloud?.asn || ev?.asn, '');
          const asName = safeText(cloud?.as_name || ev?.as_name, '');
          const org = safeText(cloud?.org_name || ev?.org_name, '');
          const src = safeText(cloud?.source || ev?.source, '');
          const region = safeText(cloud?.region || ev?.region, '');
          const accountId = cloud?.account_id ?? ev?.account_id;
          const accountName = safeText(cloud?.account_name || ev?.account_name, '');
          const kind = safeText(cloud?.kind || hybrid?.kind, '');
          const resourceName = safeText(cloud?.resource_name || ev?.resource_name, '');
          const resourceType = safeText(cloud?.resource_type_label || cloud?.resource_type || ev?.resource_type, '');
          const resourceId = safeText(cloud?.resource_id || ev?.resource_id, '');
          const providerState = safeText(cloud?.provider_state, '');
          const lastSyncedAt = formatDateTime(cloud?.last_synced_at);
          const syncFreshness = freshnessLabel(cloud?.last_synced_at);
          const syncStatus = safeText(cloud?.sync_status, '');
          const syncMessage = safeText(cloud?.sync_message, '');
          const executionReadiness = cloud?.execution_readiness && typeof cloud.execution_readiness === 'object'
            ? cloud.execution_readiness
            : {};
          const operationalSummary = cloud?.operational_summary && typeof cloud.operational_summary === 'object'
            ? cloud.operational_summary
            : {};
          const routeRefs = Array.isArray(operationalSummary?.route_refs) ? operationalSummary.route_refs : [];
          const securityRefs = Array.isArray(operationalSummary?.security_refs) ? operationalSummary.security_refs : [];
          const connectivityRefs = Array.isArray(operationalSummary?.connectivity_refs) ? operationalSummary.connectivity_refs : [];
          const attachedSecurityRefs = Array.isArray(operationalSummary?.attached_security_refs)
            ? operationalSummary.attached_security_refs
            : [];
          const inferred = cloud?.inferred_from || ev?.inferred_from;
          const refs = Array.isArray(cloud?.refs) ? cloud.refs : [];
          const hybridLinks = Number(hybrid?.hybrid_links || 0);
          const peerLinks = Number(hybrid?.peer_links || 0);
          const inventoryLinks = Number(hybrid?.inventory_links || 0);
          const changeEnabled = executionReadiness?.change_enabled === true;
          const changeModeReason = safeText(executionReadiness?.change_mode_reason, '');
          const missingFields = Array.isArray(executionReadiness?.missing_fields)
            ? executionReadiness.missing_fields.map((row) => safeText(row, '')).filter(Boolean)
            : [];
          const canCreateCloudIntent = Boolean(provider && (accountId != null || region || resourceType || resourceName || resourceId));
          const openCloudIntent = () => {
            navigate(
              buildCloudIntentPath({
                provider,
                accountId,
                region,
                resourceType: cloud?.resource_type || ev?.resource_type || resourceType,
                resourceName,
                resourceId,
                routeRefs,
                securityRefs,
                source: 'topology',
              }),
            );
          };
          const openTopologyImpact = () => {
            navigate(
              buildTopologyPath({
                cloudProvider: provider,
                cloudAccountId: accountId,
                cloudRegion: region,
                cloudResourceTypes: [cloud?.resource_type || ev?.resource_type || resourceType].filter(Boolean),
                cloudIntentImpact: true,
                focusCloudResourceId: resourceId,
                focusCloudResourceName: resourceName,
              }),
            );
          };
          const openRefTopologyImpact = (ref) => {
            const refType = ref?.resource_type || ref?.resource_type_label || '';
            const refId = ref?.resource_id || '';
            const refName = ref?.resource_name || refId || '';
            navigate(
              buildTopologyPath({
                cloudProvider: provider,
                cloudAccountId: accountId,
                cloudRegion: ref?.region || region,
                cloudResourceTypes: [refType].filter(Boolean),
                cloudIntentImpact: true,
                focusCloudResourceId: refId,
                focusCloudResourceName: refName,
              }),
            );
          };
          const openRefCloudIntent = (ref) => {
            navigate(
              buildCloudIntentPath({
                provider,
                accountId,
                region: ref?.region || region,
                resourceType: ref?.resource_type || ref?.resource_type_label || '',
                resourceName: ref?.resource_name || '',
                resourceId: ref?.resource_id || '',
                source: 'cloud-detail',
              }),
            );
          };
          const renderReferenceList = (titleKey, titleFallback, refsList, typeFallback) => {
            if (!Array.isArray(refsList) || refsList.length === 0) return null;
            return (
              <div className="space-y-2">
                <div className="text-gray-400">{t(titleKey, titleFallback)}</div>
                {refsList.map((ref, idx) => {
                  const refType = safeText(ref?.resource_type_label || ref?.resource_type, typeFallback);
                  const refName = safeText(ref?.resource_name || ref?.resource_id, '--');
                  const refRegion = safeText(ref?.region, '');
                  return (
                    <div
                      key={`${ref?.resource_id || ref?.resource_name || typeFallback || idx}`}
                      className="rounded-lg border border-gray-700 bg-black/20 px-3 py-2 space-y-2"
                    >
                      <div className="break-all">
                        <span className="text-gray-400">{refType}:</span>{' '}
                        <span className="text-gray-100 font-medium">{refName}</span>
                        {refRegion && <span className="text-gray-500"> ({refRegion})</span>}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => openRefTopologyImpact(ref)}
                          className="inline-flex items-center gap-1 rounded-md border border-violet-700/60 bg-violet-500/20 px-2.5 py-1.5 text-[11px] font-semibold text-violet-100 hover:bg-violet-500/30"
                        >
                          <ExternalLink size={12} />
                          {t('cloud_detail_open_topology_impact', 'Open Topology Impact')}
                        </button>
                        <button
                          type="button"
                          onClick={() => openRefCloudIntent(ref)}
                          className="inline-flex items-center gap-1 rounded-md border border-sky-700/60 bg-sky-500/20 px-2.5 py-1.5 text-[11px] font-semibold text-sky-100 hover:bg-sky-500/30"
                        >
                          <GitBranch size={12} />
                          {t('cloud_detail_open_intent', 'Create Cloud Intent')}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          };
          return (
            <div className="space-y-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="px-2 py-0.5 rounded-full bg-sky-900/40 text-sky-200 text-xs font-bold">{provider}</span>
                {kind && (
                  <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-200 text-xs font-bold">
                    {t('cloud_detail_kind', 'kind')}:{kind}
                  </span>
                )}
                {providerState && (
                  <span className="px-2 py-0.5 rounded-full bg-emerald-950/40 text-emerald-200 text-xs font-bold">
                    {t('cloud_detail_provider_state', 'provider')}:{providerState}
                  </span>
                )}
                {syncStatus && (
                  <span className="px-2 py-0.5 rounded-full bg-violet-950/40 text-violet-200 text-xs font-bold">
                    {t('cloud_detail_sync_status', 'sync')}:{syncStatus}
                  </span>
                )}
                {syncFreshness && (
                  <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                    syncFreshness === 'fresh'
                      ? 'bg-emerald-950/40 text-emerald-200'
                      : syncFreshness === 'recent'
                        ? 'bg-sky-950/40 text-sky-200'
                        : 'bg-amber-950/40 text-amber-200'
                  }`}>
                    {t('cloud_detail_sync_freshness', 'freshness')}:{t(`cloud_detail_sync_freshness_${syncFreshness}`, syncFreshness)}
                  </span>
                )}
                {asn && <span className="px-2 py-0.5 rounded-full bg-gray-800 text-gray-200 text-xs font-bold">AS{asn}</span>}
                {src && <span className="px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 text-xs">{t('cloud_detail_source', 'src')}:{src}</span>}
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${changeEnabled ? 'bg-emerald-950/40 text-emerald-200' : 'bg-amber-950/40 text-amber-200'}`}>
                  {changeEnabled ? t('cloud_accounts_change_enabled', 'Change enabled') : t('cloud_accounts_read_only_mode', 'Read-only')}
                </span>
                {hybridLinks > 0 && (
                  <span className="px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-200 text-xs font-bold">
                    HY {hybridLinks}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-1 gap-1 text-gray-200">
                <div><span className="text-gray-400">{t('cloud_detail_ip', 'IP')}:</span> <span className="font-mono">{ip}</span></div>
                {(accountName || accountId != null) && (
                  <div data-testid="cloud-detail-account" className="break-words">
                    <span className="text-gray-400">{t('cloud_detail_account', 'Account')}:</span> {accountName || `#${String(accountId)}`}{accountName && accountId != null ? ` (#${String(accountId)})` : ''}
                  </div>
                )}
                {resourceName && <div className="break-words"><span className="text-gray-400">{t('cloud_detail_resource_name', 'Resource')}:</span> {resourceName}</div>}
                {resourceType && <div><span className="text-gray-400">{t('cloud_detail_resource_type', 'Type')}:</span> {resourceType}</div>}
                {resourceId && <div className="break-all"><span className="text-gray-400">{t('cloud_detail_resource_id', 'Resource ID')}:</span> <span className="font-mono">{resourceId}</span></div>}
                {region && <div><span className="text-gray-400">{t('cloud_detail_region', 'Region')}:</span> {region}</div>}
                <div><span className="text-gray-400">{t('cloud_detail_last_sync', 'Last Sync')}:</span> {lastSyncedAt}</div>
                {syncMessage && syncMessage !== '--' && (
                  <div className="break-words">
                    <span className="text-gray-400">{t('cloud_detail_sync_message', 'Sync Message')}:</span> {syncMessage}
                  </div>
                )}
                {org && <div className="break-words"><span className="text-gray-400">{t('cloud_detail_org', 'Org')}:</span> {org}</div>}
                {asName && <div className="break-words"><span className="text-gray-400">{t('cloud_detail_as_name', 'AS Name')}:</span> {asName}</div>}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
                {metricCard(t('cloud_detail_account_inventory', 'Account Inventory'), safeText(operationalSummary?.account_resources, '0'), 'border-slate-700 bg-slate-950/30')}
                {metricCard(t('cloud_detail_region_inventory', 'Region Scope'), safeText(operationalSummary?.region_resources, '0'), 'border-slate-700 bg-slate-950/30')}
                {metricCard(t('cloud_detail_route_tables', 'Route Tables'), safeText(operationalSummary?.route_tables, '0'), 'border-cyan-900/40 bg-cyan-950/20')}
                {metricCard(t('cloud_detail_routes', 'Routes'), safeText(operationalSummary?.routes, '0'), 'border-cyan-900/40 bg-cyan-950/20')}
                {metricCard(t('cloud_detail_security_policies', 'Security Policies'), safeText(operationalSummary?.security_policies, '0'), 'border-amber-900/40 bg-amber-950/20')}
                {metricCard(t('cloud_detail_security_rules', 'Security Rules'), safeText(operationalSummary?.security_rules, '0'), 'border-amber-900/40 bg-amber-950/20')}
                {metricCard(t('cloud_detail_connectivity_objects', 'Connectivity'), safeText(operationalSummary?.connectivity_objects, '0'), 'border-fuchsia-900/40 bg-fuchsia-950/20')}
              </div>
              <div className="rounded border border-sky-900/40 bg-sky-950/20 p-3 text-xs text-sky-100">
                <div className="font-bold text-sky-200">{t('cloud_detail_intent_title', 'Cloud intent handoff')}</div>
                <div className="mt-1 text-sky-100/80">
                  {t(
                    'cloud_detail_intent_desc',
                    'Use this node as the starting scope for a Terraform-backed cloud intent. Provider, account, region, and resource type are prefilled.',
                  )}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={openCloudIntent}
                    disabled={!canCreateCloudIntent}
                    className="inline-flex items-center gap-2 rounded-lg border border-sky-700/60 bg-sky-500/20 px-3 py-2 font-semibold text-sky-100 transition-colors hover:bg-sky-500/30 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <GitBranch size={14} />
                    {t('cloud_detail_open_intent', 'Create Cloud Intent')}
                  </button>
                  <button
                    type="button"
                    onClick={openTopologyImpact}
                    className="inline-flex items-center gap-2 rounded-lg border border-violet-700/60 bg-violet-500/20 px-3 py-2 font-semibold text-violet-100 transition-colors hover:bg-violet-500/30"
                  >
                    <ExternalLink size={14} />
                    {t('cloud_detail_open_topology_impact', 'Open Topology Impact')}
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate(accountId != null ? `/cloud/accounts?focusAccountId=${encodeURIComponent(String(accountId))}` : '/cloud/accounts')}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 font-semibold text-slate-100 transition-colors hover:bg-slate-800"
                  >
                    <Settings2 size={14} />
                    {t('cloud_detail_open_accounts', 'Open Cloud Accounts')}
                  </button>
                </div>
                {changeModeReason && changeModeReason !== '--' && (
                  <div className="mt-3 rounded-lg border border-emerald-900/40 bg-black/20 px-3 py-2 text-xs text-gray-200">
                    <div className="font-bold text-gray-100">{t('cloud_detail_execution_mode', 'Execution Mode')}</div>
                    <div className="mt-1">{changeModeReason}</div>
                    {missingFields.length > 0 && (
                      <div className="mt-2 text-amber-200">
                        {t('cloud_accounts_exec_missing_fields', 'Missing')}: {missingFields.join(', ')}
                      </div>
                    )}
                  </div>
                )}
              </div>
              {(routeRefs.length > 0 || securityRefs.length > 0 || connectivityRefs.length > 0 || attachedSecurityRefs.length > 0) && (
                <div className="rounded border border-gray-700 bg-black/25 p-3 text-xs text-gray-200 space-y-3">
                  <div className="font-bold text-gray-300">{t('cloud_detail_operational_context', 'Operational Context')}</div>
                  {renderReferenceList('cloud_detail_route_summary', 'Related Routing', routeRefs, 'Route')}
                  {renderReferenceList('cloud_detail_security_summary', 'Related Security', securityRefs, 'Security')}
                  {attachedSecurityRefs.length > 0 && (
                    <div className="text-gray-400 break-all">
                      {t('cloud_detail_attached_security', 'Attached refs')}: {attachedSecurityRefs.join(', ')}
                    </div>
                  )}
                  {renderReferenceList('cloud_detail_connectivity_summary', 'Connectivity Objects', connectivityRefs, 'Connectivity')}
                </div>
              )}
              {(peerLinks > 0 || inventoryLinks > 0) && (
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="rounded border border-blue-900/40 bg-blue-950/20 px-2 py-1">
                    <div className="text-gray-400">{t('cloud_detail_hybrid_links', 'Hybrid')}</div>
                    <div className="font-bold text-blue-200">{hybridLinks}</div>
                  </div>
                  <div className="rounded border border-indigo-900/40 bg-indigo-950/20 px-2 py-1">
                    <div className="text-gray-400">{t('cloud_detail_peer_links', 'Peer')}</div>
                    <div className="font-bold text-indigo-200">{peerLinks}</div>
                  </div>
                  <div className="rounded border border-cyan-900/40 bg-cyan-950/20 px-2 py-1">
                    <div className="text-gray-400">{t('cloud_detail_inventory_links', 'Inventory')}</div>
                    <div className="font-bold text-cyan-200">{inventoryLinks}</div>
                  </div>
                </div>
              )}
              <div data-testid="cloud-detail-refs-count" className="text-xs text-gray-300">
                {t('cloud_detail_refs', 'Refs')}: {refs.length}
              </div>
              {refs.length > 0 && (
                <div className="mt-2 text-xs text-gray-200 bg-black/25 border border-gray-700 rounded p-2 space-y-1">
                  <div className="font-bold text-gray-300 mb-1">{t('cloud_detail_refs_title', 'Linked Cloud Resources')}</div>
                  {refs.slice(0, 5).map((ref, idx) => {
                    const refType = ref?.resource_type_label || ref?.resource_type || '-';
                    const refName = ref?.resource_name || ref?.resource_id || '-';
                    const refRegion = ref?.region ? ` (${String(ref.region)})` : '';
                    return (
                      <div key={`${ref?.resource_id || ref?.resource_name || idx}`} data-testid={`cloud-detail-ref-${idx}`} className="break-all">
                        <span className="text-gray-400">{refType}:</span> {refName}{refRegion}
                      </div>
                    );
                  })}
                  {refs.length > 5 && (
                    <div className="text-gray-400">
                      {t('cloud_detail_refs_more', 'More refs')}: +{refs.length - 5}
                    </div>
                  )}
                </div>
              )}
              {inferred && typeof inferred === 'object' && (
                <div className="mt-2 text-xs text-gray-200 bg-black/25 border border-gray-700 rounded p-2 space-y-0.5">
                  <div className="font-bold text-gray-300 mb-1">{t('cloud_detail_inferred_title', 'Inferred Evidence')}</div>
                  {inferred.reason && <div>{t('cloud_detail_inferred_reason', 'reason')}: {String(inferred.reason)}</div>}
                  {inferred.device_name && <div>{t('cloud_detail_inferred_from', 'from')}: {String(inferred.device_name)}</div>}
                  {inferred.device_id != null && <div>{t('cloud_detail_inferred_device_id', 'device_id')}: {String(inferred.device_id)}</div>}
                </div>
              )}
              <div className="rounded border border-gray-700 bg-black/25 p-2 text-[11px] text-gray-400">
                <span className="inline-flex items-center gap-1 font-semibold text-gray-200">
                  <ExternalLink size={12} />
                  {t('cloud_detail_nms_bridge_hint', 'This cloud node can now flow directly into Cloud Intents without leaving the topology context.')}
                </span>
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
};

export default CloudDetailPanel;
