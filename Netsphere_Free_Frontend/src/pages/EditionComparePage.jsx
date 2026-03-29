import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  CheckCircle2,
  Crown,
  Database,
  Eye,
  Layers,
  ShieldCheck,
  Sparkles,
  Workflow,
} from 'lucide-react';

import { PreviewService } from '../api/services';
import { SectionCard } from '../components/common/PageState';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';

const CAPABILITY_ROWS = [
  {
    key: 'discovery',
    labelKey: 'edition_compare_row_discovery',
    defaultLabel: 'Discovery and topology visibility',
    freeValueKey: 'edition_compare_value_full',
    freeValueDefault: 'Included',
    proValueKey: 'edition_compare_value_full',
    proValueDefault: 'Included',
  },
  {
    key: 'managed_capacity',
    labelKey: 'edition_compare_row_managed_capacity',
    defaultLabel: 'Active monitoring capacity',
    freeDynamic: 'managedLimit',
    proValueKey: 'edition_compare_value_expand',
    proValueDefault: 'Expanded operational capacity',
  },
  {
    key: 'alerts',
    labelKey: 'edition_compare_row_alerts',
    defaultLabel: 'Alerts, sync, diagnosis, and observability',
    freeValueKey: 'edition_compare_value_managed_only',
    freeValueDefault: 'Managed nodes only',
    proValueKey: 'edition_compare_value_full_scope',
    proValueDefault: 'Full operational scope',
  },
  {
    key: 'profiles',
    labelKey: 'edition_compare_row_profiles',
    defaultLabel: 'Monitoring profiles and operating baseline',
    freeValueKey: 'edition_compare_value_preview_only',
    freeValueDefault: 'Preview recommendation only',
    proValueKey: 'edition_compare_value_enabled',
    proValueDefault: 'Enabled',
  },
  {
    key: 'service_ops',
    labelKey: 'edition_compare_row_service_ops',
    defaultLabel: 'Service groups, service maps, and reports',
    freeValueKey: 'edition_compare_value_upgrade_needed',
    freeValueDefault: 'Upgrade when the team is ready',
    proValueKey: 'edition_compare_value_enabled',
    proValueDefault: 'Enabled',
  },
  {
    key: 'change_control',
    labelKey: 'edition_compare_row_change_control',
    defaultLabel: 'Approval, evidence, rollback, and cloud control',
    freeValueKey: 'edition_compare_value_not_included',
    freeValueDefault: 'Not included',
    proValueKey: 'edition_compare_value_enabled',
    proValueDefault: 'Enabled',
  },
  {
    key: 'contribution',
    labelKey: 'edition_compare_row_contribution',
    defaultLabel: 'Masked data contribution and parser feedback',
    freeValueKey: 'edition_compare_value_included',
    freeValueDefault: 'Included',
    proValueKey: 'edition_compare_value_optional',
    proValueDefault: 'Optional',
  },
];

const PRO_VALUE_ICONS = {
  enabled: CheckCircle2,
  expand: Sparkles,
  full_scope: Crown,
};

const EditionComparePage = () => {
  const locale = useLocaleRerender();
  const navigate = useNavigate();
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await PreviewService.getPolicy();
        if (!alive) return;
        setPolicy(res?.data || null);
      } catch (error) {
        if (!alive) return;
        setPolicy(null);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const previewEnabled = policy?.preview_enabled === true;
  const managedLimit = Number(policy?.managed_node_limit || 50);
  const managedSummary = policy?.managed_nodes || {};
  const managed = Number(managedSummary?.managed || 0);
  const discoveredOnly = Number(managedSummary?.discovered_only || 0);
  const totalDiscovered = Number(managedSummary?.total_discovered || 0);
  const remainingSlots = Number(managedSummary?.remaining_slots || Math.max(managedLimit - managed, 0));

  const compareRows = useMemo(() => {
    return CAPABILITY_ROWS.map((row) => {
      let freeLabel = t(row.freeValueKey, row.freeValueDefault);
      if (row.freeDynamic === 'managedLimit') {
        freeLabel = t('edition_compare_value_managed_limit', 'Managed up to {count} nodes').replace('{count}', String(managedLimit));
      }
      return {
        ...row,
        label: t(row.labelKey, row.defaultLabel),
        freeLabel,
        proLabel: t(row.proValueKey, row.proValueDefault),
      };
    });
  }, [managedLimit, locale]);

  const currentEditionTitle = previewEnabled
    ? t('edition_compare_current_free_title', 'You are currently running NetSphere Free.')
    : t('edition_compare_current_pro_title', 'You are currently running a Pro-capable deployment.');
  const currentEditionDesc = previewEnabled
    ? t(
        'edition_compare_current_free_desc',
        'NetSphere Free keeps discovery, topology, and basic inventory visible for every discovered asset. Pro expands that visibility into active operations across a larger footprint.',
      )
    : t(
        'edition_compare_current_pro_desc',
        'This deployment already exposes the operational surfaces that turn discovered assets into managed services, approved changes, and operator evidence.',
      );

  const upgradeReason = previewEnabled && discoveredOnly > 0
    ? t(
        'edition_compare_upgrade_reason_discovered_only',
        '{count} discovered assets are currently outside the active monitoring pool. Pro turns those visible assets into fully managed operating scope.',
      ).replace('{count}', String(discoveredOnly))
    : t(
        'edition_compare_upgrade_reason_general',
        'NetSphere Free is designed to prove discovery, topology, and masked parser contribution. Pro is where larger-scale monitoring, service operations, and controlled change workflows start.',
      );

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012] min-h-full text-gray-900 dark:text-white animate-fade-in">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between mb-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.22em] text-blue-700 dark:border-blue-900/40 dark:bg-blue-950/20 dark:text-blue-300">
            <Sparkles size={12} />
            {t('edition_compare_eyebrow', 'Edition Path')}
          </div>
          <h1 className="mt-3 text-2xl font-bold text-gray-900 dark:text-white">
            {t('edition_compare_title', 'Free to Pro Operational Upgrade')}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
            {t(
              'edition_compare_desc',
              'Use this page to explain the product boundary clearly: NetSphere Free is for discovery and understanding. Pro expands that same topology into active monitoring, service operations, approvals, and evidence.',
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => navigate('/devices')}
            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2 text-sm font-bold text-gray-700 hover:bg-gray-50 dark:border-white/10 dark:bg-white/5 dark:text-gray-100 dark:hover:bg-white/10"
          >
            <Eye size={14} />
            {t('edition_compare_open_inventory', 'Open Inventory')}
          </button>
          <button
            onClick={() => navigate('/automation')}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white hover:bg-blue-500"
          >
            <Workflow size={14} />
            {previewEnabled
              ? t('edition_compare_open_free_ops', 'Open Free Operations')
              : t('edition_compare_open_automation', 'Open Operations Home')}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.1fr)_420px] gap-6">
        <div className="space-y-6">
          <SectionCard className="p-5">
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-lg font-bold text-gray-900 dark:text-white">{currentEditionTitle}</div>
              <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.18em] ${previewEnabled ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300' : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300'}`}>
                {previewEnabled ? t('edition_compare_badge_free', 'Free') : t('edition_compare_badge_pro', 'Pro')}
              </span>
            </div>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{currentEditionDesc}</p>
            <div className="mt-4 rounded-2xl border border-blue-200 bg-blue-50/70 p-4 text-sm text-blue-900 dark:border-blue-900/40 dark:bg-blue-950/10 dark:text-blue-100">
              {upgradeReason}
            </div>
          </SectionCard>

          <SectionCard className="p-5">
            <div className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
              <Database size={16} className="text-blue-500" />
              {t('edition_compare_matrix_title', 'Operational scope by edition')}
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-800 text-xs uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
                    <th className="px-3 py-3 font-bold">{t('edition_compare_matrix_capability', 'Capability')}</th>
                    <th className="px-3 py-3 font-bold">{t('edition_compare_matrix_free', 'Free')}</th>
                    <th className="px-3 py-3 font-bold">{t('edition_compare_matrix_pro', 'Pro')}</th>
                  </tr>
                </thead>
                <tbody>
                  {compareRows.map((row) => {
                    const iconKey =
                      row.key === 'managed_capacity'
                        ? 'expand'
                        : row.key === 'alerts'
                          ? 'full_scope'
                          : 'enabled';
                    const ProIcon = PRO_VALUE_ICONS[iconKey] || CheckCircle2;
                    return (
                      <tr key={row.key} className="border-b border-gray-100 dark:border-gray-900/60 align-top">
                        <td className="px-3 py-3 font-semibold text-gray-800 dark:text-gray-100">{row.label}</td>
                        <td className="px-3 py-3 text-gray-600 dark:text-gray-300">{row.freeLabel}</td>
                        <td className="px-3 py-3">
                          <div className="inline-flex items-center gap-2 font-semibold text-emerald-700 dark:text-emerald-300">
                            <ProIcon size={14} />
                            {row.proLabel}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard className="p-5">
            <div className="text-sm font-bold text-gray-900 dark:text-white">
              {t('edition_compare_upgrade_outcomes_title', 'What Pro adds to the same discovered assets')}
            </div>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                {
                  icon: ShieldCheck,
                  title: t('edition_compare_outcome_ops_title', 'Active monitoring at larger scale'),
                  desc: t('edition_compare_outcome_ops_desc', 'Keep health, alerts, sync, diagnosis, and observability active beyond the Free managed-node cap.'),
                },
                {
                  icon: Database,
                  title: t('edition_compare_outcome_baseline_title', 'Profiles and operating baseline'),
                  desc: t('edition_compare_outcome_baseline_desc', 'Turn discovered assets into profiled, tagged, service-aware operating records instead of leaving them as discovery snapshots only.'),
                },
                {
                  icon: Layers,
                  title: t('edition_compare_outcome_service_title', 'Service context and preventive operations'),
                  desc: t('edition_compare_outcome_service_desc', 'Group devices and cloud assets by service, run preventive checks, and export operational review bundles.'),
                },
                {
                  icon: Workflow,
                  title: t('edition_compare_outcome_control_title', 'Controlled change and evidence'),
                  desc: t('edition_compare_outcome_control_desc', 'Move from issue context to approvals, evidence, rollback, and cloud intent workflows with operator continuity.'),
                },
              ].map((item) => (
                <div key={item.title} className="rounded-2xl border border-gray-200 bg-white/80 p-4 dark:border-white/10 dark:bg-white/[0.03]">
                  <div className="inline-flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
                    <item.icon size={15} className="text-blue-500" />
                    {item.title}
                  </div>
                  <div className="mt-2 text-xs leading-5 text-gray-600 dark:text-gray-300">{item.desc}</div>
                </div>
              ))}
            </div>
          </SectionCard>
        </div>

        <div className="space-y-6">
          <SectionCard className="p-5">
            <div className="text-sm font-bold text-gray-900 dark:text-white">
              {t('edition_compare_current_scope_title', 'Current managed-node footprint')}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-2xl border border-gray-200 bg-white/80 p-4 dark:border-white/10 dark:bg-white/[0.03]">
                <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
                  {t('edition_compare_metric_discovered', 'Discovered')}
                </div>
                <div className="mt-2 text-2xl font-black text-gray-900 dark:text-white">{loading ? '--' : totalDiscovered}</div>
              </div>
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4 dark:border-emerald-900/30 dark:bg-emerald-900/10">
                <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-300">
                  {t('devices_filter_managed', 'Managed')}
                </div>
                <div className="mt-2 text-2xl font-black text-emerald-800 dark:text-emerald-200">{loading ? '--' : managed}</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4 dark:border-white/10 dark:bg-white/[0.03]">
                <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-600 dark:text-slate-300">
                  {t('devices_filter_discovered_only', 'Discovered Only')}
                </div>
                <div className="mt-2 text-2xl font-black text-slate-800 dark:text-slate-100">{loading ? '--' : discoveredOnly}</div>
              </div>
              <div className="rounded-2xl border border-blue-200 bg-blue-50/70 p-4 dark:border-blue-900/30 dark:bg-blue-900/10">
                <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-blue-700 dark:text-blue-300">
                  {t('edition_compare_metric_remaining', 'Remaining Slots')}
                </div>
                <div className="mt-2 text-2xl font-black text-blue-800 dark:text-blue-200">{loading ? '--' : remainingSlots}</div>
              </div>
            </div>
            <div className="mt-4 text-xs leading-5 text-gray-600 dark:text-gray-300">
              {t('edition_compare_capacity_desc', 'Free keeps every discovered asset visible. Managed slots decide where active monitoring, alerts, diagnosis, sync, and observability stay turned on.')}
            </div>
          </SectionCard>

          <SectionCard className="p-5">
            <div className="text-sm font-bold text-gray-900 dark:text-white">
              {t('edition_compare_transition_title', 'When Free is still enough, and when Pro becomes the next step')}
            </div>
            <div className="mt-4 space-y-3 text-sm">
              <div className="rounded-2xl border border-gray-200 bg-white/80 p-4 dark:border-white/10 dark:bg-white/[0.03]">
                <div className="font-bold text-gray-900 dark:text-white">{t('edition_compare_transition_free_title', 'Stay on Free when you are still validating asset visibility')}</div>
                <div className="mt-2 text-xs leading-5 text-gray-600 dark:text-gray-300">
                  {t('edition_compare_transition_free_desc', 'Use Free when discovery, topology, masked parser contribution, and a small managed monitoring pool are enough for the current team and footprint.')}
                </div>
              </div>
              <div className="rounded-2xl border border-blue-200 bg-blue-50/70 p-4 dark:border-blue-900/30 dark:bg-blue-900/10">
                <div className="font-bold text-blue-900 dark:text-blue-100">{t('edition_compare_transition_pro_title', 'Move to Pro when operations are broader than the discovery preview')}</div>
                <div className="mt-2 text-xs leading-5 text-blue-900/90 dark:text-blue-100/90">
                  {t('edition_compare_transition_pro_desc', 'Pro is the right next step once more than the Free managed-node pool needs active monitoring, or when service operations, preventive checks, approvals, evidence, and cloud control become daily work.')}
                </div>
              </div>
            </div>
          </SectionCard>

          <SectionCard className="p-5">
            <div className="text-sm font-bold text-gray-900 dark:text-white">
              {t('edition_compare_next_actions_title', 'Suggested next actions')}
            </div>
            <div className="mt-4 space-y-2">
              {[
                {
                  label: t('edition_compare_next_inventory', 'Review which discovered-only nodes matter most operationally'),
                  action: () => navigate('/devices'),
                },
                {
                  label: t('edition_compare_next_topology', 'Open topology and confirm which assets should stay visible but not actively monitored'),
                  action: () => navigate('/topology'),
                },
                {
                  label: previewEnabled
                    ? t('edition_compare_next_policy', 'Review how the installation policy keeps masked parser contribution controlled and optional')
                    : t('edition_compare_next_automation', 'Review the Pro operational surfaces already enabled in Operations Home'),
                  action: () => navigate('/automation'),
                },
              ].map((item) => (
                <button
                  key={item.label}
                  onClick={item.action}
                  className="flex w-full items-center justify-between rounded-2xl border border-gray-200 bg-white/80 px-4 py-3 text-left text-sm font-semibold text-gray-700 hover:bg-gray-50 dark:border-white/10 dark:bg-white/[0.03] dark:text-gray-100 dark:hover:bg-white/[0.05]"
                >
                  <span>{item.label}</span>
                  <ArrowRight size={16} className="text-blue-500" />
                </button>
              ))}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
};

export default EditionComparePage;
