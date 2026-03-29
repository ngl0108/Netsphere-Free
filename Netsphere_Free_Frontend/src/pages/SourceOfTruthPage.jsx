import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Boxes,
  Cloud,
  FolderTree,
  MapPinned,
  Network,
  RefreshCw,
  Server,
  ShieldCheck,
  Tags,
} from 'lucide-react';

import { SourceOfTruthService } from '../api/services';
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';

const PANEL_CLASS = 'rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] shadow-sm';

const MetricCard = ({ icon: Icon, title, value, hint }) => (
  <div className={`${PANEL_CLASS} p-4`}>
    <div className="flex items-center justify-between gap-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{title}</div>
      <Icon size={18} className="text-blue-500" />
    </div>
    <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{value}</div>
    {hint ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</div> : null}
  </div>
);

const CoverageCard = ({ title, value, total, hint }) => {
  const safeTotal = Math.max(0, Number(total || 0));
  const safeValue = Math.max(0, Number(value || 0));
  const ratio = safeTotal > 0 ? Math.min(100, Math.round((safeValue / safeTotal) * 100)) : 0;
  return (
    <div className={`${PANEL_CLASS} p-4`}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{title}</div>
        <div className="text-xs font-black text-blue-600 dark:text-blue-300">{ratio}%</div>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-white/5">
        <div className="h-full rounded-full bg-blue-500" style={{ width: `${ratio}%` }} />
      </div>
      <div className="mt-2 text-sm font-semibold text-gray-800 dark:text-gray-100">
        {safeValue} / {safeTotal}
      </div>
      {hint ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</div> : null}
    </div>
  );
};

const DistributionList = ({ title, rows = [], emptyLabel }) => (
  <div className={`${PANEL_CLASS} p-5`}>
    <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{title}</div>
    <div className="mt-4 space-y-3">
      {(rows || []).length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-5 text-sm text-gray-500 dark:text-gray-400">
          {emptyLabel}
        </div>
      ) : (
        rows.map((row) => (
          <div key={`${title}-${row.key}`} className="flex items-center justify-between gap-3 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] px-4 py-3">
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">{row.key}</div>
            <div className="text-xs font-black text-blue-600 dark:text-blue-300">{row.count}</div>
          </div>
        ))
      )}
    </div>
  </div>
);

const formatTs = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('ko-KR', { hour12: false });
};

const SourceOfTruthPage = () => {
  useLocaleRerender();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);

  const loadSummary = async () => {
    setLoading(true);
    try {
      const response = await SourceOfTruthService.getSummary();
      setSummary(response?.data || null);
    } catch (error) {
      toast.error(`${t('sot_load_failed', 'Failed to load source of truth summary')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadSummary();
  }, []);

  const metrics = summary?.metrics || {};
  const coverage = summary?.coverage || {};
  const distributions = summary?.distributions || {};
  const recentChanges = Array.isArray(summary?.recent_changes) ? summary.recent_changes : [];

  const topCards = useMemo(
    () => [
      {
        title: t('sot_metric_devices', 'Devices'),
        value: Number(metrics.devices_total || 0),
        hint: t('sot_metric_devices_hint', '{managed} managed / {discovered} discovered only')
          .replace('{managed}', String(metrics.managed_devices || 0))
          .replace('{discovered}', String(metrics.discovered_only_devices || 0)),
        icon: Server,
      },
      {
        title: t('sot_metric_cloud_resources', 'Cloud Resources'),
        value: Number(metrics.cloud_resources_total || 0),
        hint: t('sot_metric_cloud_resources_hint', '{accounts} accounts tracked').replace('{accounts}', String(metrics.cloud_accounts_total || 0)),
        icon: Cloud,
      },
      {
        title: t('sot_metric_service_groups', 'Service Groups'),
        value: Number(metrics.service_groups_total || 0),
        hint: t('sot_metric_service_groups_hint', '{members} mapped members').replace('{members}', String(metrics.service_group_members_total || 0)),
        icon: FolderTree,
      },
      {
        title: t('sot_metric_online_posture', 'Online Posture'),
        value: Number(metrics.online_devices || 0),
        hint: t('sot_metric_online_posture_hint', '{offline} offline').replace('{offline}', String(metrics.offline_devices || 0)),
        icon: ShieldCheck,
      },
    ],
    [metrics],
  );

  return (
    <div
      data-testid="source-of-truth-page"
      className="p-3 sm:p-4 md:p-6 bg-[#f4f5f9] dark:bg-[#0e1012] h-full min-h-0 flex flex-col overflow-y-auto animate-fade-in text-gray-900 dark:text-white"
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between mb-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-indigo-700 dark:border-indigo-900/50 dark:bg-indigo-500/10 dark:text-indigo-300">
            <Tags size={14} />
            {t('sot_badge', 'Source of Truth Lite')}
          </div>
          <h1 className="mt-3 text-2xl font-black tracking-tight">{t('sot_title', 'Source of Truth')}</h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
            {t(
              'sot_desc',
              'Keep the current operating asset baseline visible in one place. Review device coverage, cloud footprint, service ownership, and the latest asset changes without turning NetSphere into a heavy CMDB.',
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            data-testid="source-of-truth-refresh"
            onClick={() => void loadSummary()}
            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] px-4 py-2 text-sm font-bold text-gray-700 dark:text-gray-100"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            {t('common_refresh', 'Refresh')}
          </button>
          <button
            data-testid="source-of-truth-open-inventory"
            onClick={() => navigate('/devices')}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 dark:bg-white px-4 py-2 text-sm font-bold text-white dark:text-slate-900"
          >
            <ArrowRight size={16} />
            {t('sot_open_inventory', 'Open Inventory')}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        {topCards.map((card) => (
          <MetricCard key={card.title} {...card} />
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,0.95fr)] gap-4">
        <section className="space-y-4">
          <div className={`${PANEL_CLASS} p-5`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('sot_coverage_title', 'Coverage Posture')}</div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {t('sot_coverage_desc', 'Check whether the current asset baseline is complete enough for monitoring, service mapping, and reporting.')}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  data-testid="source-of-truth-open-monitoring-profiles"
                  onClick={() => navigate('/monitoring-profiles')}
                  className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                >
                  {t('sot_open_monitoring_profiles', 'Open Monitoring Profiles')}
                </button>
                <button
                  data-testid="source-of-truth-open-service-groups"
                  onClick={() => navigate('/service-groups')}
                  className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                >
                  {t('sot_open_service_groups', 'Open Service Groups')}
                </button>
                <button
                  data-testid="source-of-truth-open-state-history"
                  onClick={() => navigate('/state-history')}
                  className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                >
                  {t('sot_open_state_history', 'Open State History')}
                </button>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              <CoverageCard
                title={t('sot_coverage_sites', 'Devices with Site')}
                value={coverage.devices_with_site}
                total={metrics.devices_total}
                hint={t('sot_coverage_sites_hint', 'Site ownership is the minimum baseline for operating reports.')}
              />
              <CoverageCard
                title={t('sot_coverage_hostnames', 'Devices with Hostname')}
                value={coverage.devices_with_hostname}
                total={metrics.devices_total}
                hint={t('sot_coverage_hostnames_hint', 'Hostnames make topology, alerting, and service impact more readable.')}
              />
              <CoverageCard
                title={t('sot_coverage_serials', 'Devices with Serial')}
                value={coverage.devices_with_serial}
                total={metrics.devices_total}
                hint={t('sot_coverage_serials_hint', 'Serial coverage improves asset handoff and audit confidence.')}
              />
              <CoverageCard
                title={t('sot_coverage_profiles', 'Devices with Monitoring Profile')}
                value={coverage.devices_with_monitoring_profile}
                total={metrics.devices_total}
                hint={t('sot_coverage_profiles_hint', 'Profile coverage shows how many assets are already aligned to a monitoring policy.')}
              />
              <CoverageCard
                title={t('sot_coverage_group_owners', 'Service Groups with Owner')}
                value={coverage.service_groups_with_owner}
                total={metrics.service_groups_total}
                hint={t('sot_coverage_group_owners_hint', 'Owner teams keep service review and handoff accountable.')}
              />
              <CoverageCard
                title={t('sot_coverage_cloud_mapping', 'Cloud Resources in Services')}
                value={coverage.cloud_resources_mapped_to_services}
                total={metrics.cloud_resources_total}
                hint={t('sot_coverage_cloud_mapping_hint', 'Mapped cloud resources can participate in service impact and review bundles.')}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <DistributionList
              title={t('sot_distribution_roles', 'Role Distribution')}
              rows={distributions.device_roles}
              emptyLabel={t('sot_distribution_empty', 'No distribution data yet.')}
            />
            <DistributionList
              title={t('sot_distribution_types', 'Device Type Distribution')}
              rows={distributions.device_types}
              emptyLabel={t('sot_distribution_empty', 'No distribution data yet.')}
            />
            <DistributionList
              title={t('sot_distribution_providers', 'Cloud Provider Distribution')}
              rows={distributions.cloud_providers}
              emptyLabel={t('sot_distribution_empty', 'No distribution data yet.')}
            />
          </div>
        </section>

        <section className="space-y-4">
          <div className={`${PANEL_CLASS} p-5`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('sot_recent_changes_title', 'Recent Asset Changes')}</div>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  {t('sot_recent_changes_desc', 'Track the most recent service-group, cloud-account, and monitoring alignment changes that affected the operating baseline.')}
                </div>
              </div>
              <button
                onClick={() => navigate('/topology')}
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
              >
                <Network size={14} />
                {t('sot_open_topology', 'Open Topology')}
              </button>
            </div>

            <div className="mt-4 space-y-3">
              {loading ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('common_loading', 'Loading...')}
                </div>
              ) : recentChanges.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  {t('sot_recent_changes_empty', 'No asset changes have been recorded yet. Recent service, cloud, and monitoring updates will appear here.')}
                </div>
              ) : (
                recentChanges.map((row) => (
                  <div key={`change-${row.id}`} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="inline-flex rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-blue-700 dark:border-blue-900/50 dark:bg-blue-500/10 dark:text-blue-300">
                            {row.asset_kind}
                          </span>
                          <span className="inline-flex rounded-full border border-gray-200 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-gray-600 dark:border-gray-700 dark:bg-[#0f1113] dark:text-gray-300">
                            {row.action}
                          </span>
                          <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{row.asset_name || row.asset_key}</div>
                        </div>
                        <div className="mt-2 text-sm text-gray-700 dark:text-gray-200">{row.summary}</div>
                        <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                          {t('sot_recent_changes_meta', '{actor} · {time}')
                            .replace('{actor}', row.actor_name || row.actor_role || t('common_unknown', 'Unknown'))
                            .replace('{time}', formatTs(row.created_at))}
                        </div>
                      </div>
                      <div className="text-[11px] font-semibold text-gray-500 dark:text-gray-400">{row.asset_key}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className={`${PANEL_CLASS} p-5`}>
            <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('sot_quick_actions_title', 'Quick Actions')}</div>
            <div className="mt-4 grid grid-cols-1 gap-2">
              {[
                { icon: Server, label: t('sot_action_inventory', 'Review device inventory'), path: '/devices' },
                { icon: MapPinned, label: t('sot_action_topology', 'Check topology posture'), path: '/topology' },
                { icon: Boxes, label: t('sot_action_service_groups', 'Refine service groups'), path: '/service-groups' },
                { icon: ShieldCheck, label: t('sot_action_profiles', 'Tune monitoring profiles'), path: '/monitoring-profiles' },
              ].map((item) => (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className="inline-flex items-center justify-between gap-3 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-3 text-sm font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                >
                  <span className="inline-flex items-center gap-2">
                    <item.icon size={16} className="text-blue-500" />
                    {item.label}
                  </span>
                  <ArrowRight size={16} />
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default SourceOfTruthPage;
