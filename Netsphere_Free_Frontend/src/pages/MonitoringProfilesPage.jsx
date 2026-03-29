import React, { useEffect, useMemo, useState } from 'react';
import { Activity, Cpu, Gauge, Plus, RefreshCw, Save, ShieldCheck, Trash2 } from 'lucide-react';

import { MonitoringProfileService } from '../api/services';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';

const PANEL_CLASS = 'rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] shadow-sm';

const DEFAULT_FORM = {
  key: '',
  name: '',
  description: '',
  management_scope: 'managed',
  telemetry_mode: 'hybrid',
  priority: 100,
  polling_interval_override: '',
  status_interval_override: '',
  is_active: true,
  match_device_types_text: '',
  match_roles_text: '',
  match_vendor_patterns_text: '',
  match_model_patterns_text: '',
  match_site_ids_text: '',
  dashboard_tags_text: '',
};

const MetricCard = ({ icon: Icon, title, value, hint }) => (
  <div className={`${PANEL_CLASS} p-4`}>
    <div className="flex items-center justify-between">
      <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{title}</div>
      <Icon size={18} className="text-blue-500" />
    </div>
    <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{value}</div>
    {hint ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</div> : null}
  </div>
);

const Input = ({ value, onChange, placeholder, type = 'text', min, max, disabled = false }) => (
  <input
    type={type}
    value={value}
    min={min}
    max={max}
    disabled={disabled}
    onChange={(event) => onChange(event.target.value)}
    placeholder={placeholder}
    className="w-full rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 disabled:opacity-60"
  />
);

const TextArea = ({ value, onChange, placeholder, rows = 4, disabled = false }) => (
  <textarea
    value={value}
    onChange={(event) => onChange(event.target.value)}
    placeholder={placeholder}
    rows={rows}
    disabled={disabled}
    className="w-full rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 resize-y disabled:opacity-60"
  />
);

const Select = ({ value, onChange, children, disabled = false }) => (
  <select
    value={value}
    onChange={(event) => onChange(event.target.value)}
    disabled={disabled}
    className="w-full rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 disabled:opacity-60"
  >
    {children}
  </select>
);

const FieldLabel = ({ children }) => (
  <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold mb-2">{children}</div>
);

const splitTextList = (value) =>
  String(value || '')
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);

const splitIntList = (value) =>
  splitTextList(value)
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item));

const normalizeProfileToForm = (profile) => {
  if (!profile) return DEFAULT_FORM;
  return {
    key: String(profile.key || ''),
    name: String(profile.name || ''),
    description: String(profile.description || ''),
    management_scope: String(profile.management_scope || 'managed'),
    telemetry_mode: String(profile.telemetry_mode || 'hybrid'),
    priority: Number(profile.priority ?? 100),
    polling_interval_override:
      profile.polling_interval_override == null ? '' : String(profile.polling_interval_override),
    status_interval_override:
      profile.status_interval_override == null ? '' : String(profile.status_interval_override),
    is_active: profile.is_active !== false,
    match_device_types_text: (profile.match_device_types || []).join(', '),
    match_roles_text: (profile.match_roles || []).join(', '),
    match_vendor_patterns_text: (profile.match_vendor_patterns || []).join(', '),
    match_model_patterns_text: (profile.match_model_patterns || []).join(', '),
    match_site_ids_text: (profile.match_site_ids || []).join(', '),
    dashboard_tags_text: (profile.dashboard_tags || []).join(', '),
  };
};

const buildPayload = (form) => ({
  key: String(form.key || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-'),
  name: String(form.name || '').trim(),
  description: String(form.description || '').trim() || null,
  management_scope: String(form.management_scope || 'managed'),
  telemetry_mode: String(form.telemetry_mode || 'hybrid'),
  priority: Number(form.priority || 100),
  polling_interval_override:
    String(form.polling_interval_override || '').trim() === '' ? null : Number(form.polling_interval_override),
  status_interval_override:
    String(form.status_interval_override || '').trim() === '' ? null : Number(form.status_interval_override),
  is_active: Boolean(form.is_active),
  match_device_types: splitTextList(form.match_device_types_text).map((item) => item.toLowerCase()),
  match_roles: splitTextList(form.match_roles_text).map((item) => item.toLowerCase()),
  match_vendor_patterns: splitTextList(form.match_vendor_patterns_text).map((item) => item.toLowerCase()),
  match_model_patterns: splitTextList(form.match_model_patterns_text).map((item) => item.toLowerCase()),
  match_site_ids: splitIntList(form.match_site_ids_text),
  dashboard_tags: splitTextList(form.dashboard_tags_text).map((item) => item.toLowerCase()),
});

const scopeTone = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'discovered_only') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/40 dark:bg-amber-900/10 dark:text-amber-300';
  }
  if (normalized === 'any') {
    return 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/40 dark:bg-sky-900/10 dark:text-sky-300';
  }
  return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-900/10 dark:text-emerald-300';
};

const MonitoringProfilesPage = () => {
  useLocaleRerender();
  const { isAtLeast } = useAuth();
  const { toast } = useToast();
  const canOperate = isAtLeast('operator');
  const canAdmin = isAtLeast('admin');

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState({ profiles: [], coverage: {} });
  const [selectedProfileId, setSelectedProfileId] = useState(null);
  const [form, setForm] = useState(DEFAULT_FORM);

  const profiles = Array.isArray(catalog?.profiles) ? catalog.profiles : [];
  const coverage = catalog?.coverage || {};

  const selectedProfile = useMemo(
    () => profiles.find((item) => Number(item.id) === Number(selectedProfileId)) || null,
    [profiles, selectedProfileId],
  );

  const loadCatalog = async (preferredProfileId = null) => {
    setLoading(true);
    try {
      const response = await MonitoringProfileService.getCatalog();
      const nextCatalog = response?.data || { profiles: [], coverage: {} };
      const nextProfiles = Array.isArray(nextCatalog?.profiles) ? nextCatalog.profiles : [];
      setCatalog({
        profiles: nextProfiles,
        coverage: nextCatalog?.coverage || {},
      });
      const nextSelected =
        nextProfiles.find((item) => Number(item.id) === Number(preferredProfileId || selectedProfileId)) ||
        nextProfiles[0] ||
        null;
      setSelectedProfileId(nextSelected?.id || null);
      setForm(normalizeProfileToForm(nextSelected));
    } catch (error) {
      toast.error(
        `${t('monitoring_profiles_load_failed', 'Failed to load monitoring profiles')}: ${
          error?.response?.data?.detail || error.message
        }`,
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadCatalog();
  }, []);

  const handleSelectProfile = (profile) => {
    setSelectedProfileId(profile?.id || null);
    setForm(normalizeProfileToForm(profile));
  };

  const handleNew = () => {
    setSelectedProfileId(null);
    setForm(DEFAULT_FORM);
  };

  const handleSave = async () => {
    const payload = buildPayload(form);
    if (!payload.key || !payload.name) {
      toast.error(t('monitoring_profiles_name_key_required', 'Profile key and name are required.'));
      return;
    }
    setSaving(true);
    try {
      const response = selectedProfileId
        ? await MonitoringProfileService.update(selectedProfileId, payload)
        : await MonitoringProfileService.create(payload);
      const nextId = response?.data?.id || selectedProfileId;
      toast.success(
        selectedProfileId
          ? t('monitoring_profiles_saved', 'Monitoring profile updated.')
          : t('monitoring_profiles_created', 'Monitoring profile created.'),
      );
      await loadCatalog(nextId);
    } catch (error) {
      toast.error(
        `${t('monitoring_profiles_save_failed', 'Failed to save monitoring profile')}: ${
          error?.response?.data?.detail || error.message
        }`,
      );
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedProfileId) return;
    if (!window.confirm(t('monitoring_profiles_delete_confirm', 'Delete this monitoring profile?'))) return;
    setSaving(true);
    try {
      await MonitoringProfileService.delete(selectedProfileId);
      toast.success(t('monitoring_profiles_deleted', 'Monitoring profile deleted.'));
      setSelectedProfileId(null);
      setForm(DEFAULT_FORM);
      await loadCatalog();
    } catch (error) {
      toast.error(
        `${t('monitoring_profiles_delete_failed', 'Failed to delete monitoring profile')}: ${
          error?.response?.data?.detail || error.message
        }`,
      );
    } finally {
      setSaving(false);
    }
  };

  const metricCards = [
    {
      title: t('monitoring_profiles_metric_profiles', 'Profiles'),
      value: Number(profiles.length || 0),
      hint: t('monitoring_profiles_metric_profiles_hint', '{value} active').replace(
        '{value}',
        String(coverage.active_profiles || 0),
      ),
      icon: ShieldCheck,
    },
    {
      title: t('monitoring_profiles_metric_devices', 'Devices'),
      value: Number(coverage.total_devices || 0),
      hint: t('monitoring_profiles_metric_devices_hint', '{value} managed').replace(
        '{value}',
        String(coverage.managed_devices || 0),
      ),
      icon: Cpu,
    },
    {
      title: t('monitoring_profiles_metric_assigned', 'Assignments'),
      value: Number(coverage.assigned_devices || 0),
      hint: t('monitoring_profiles_metric_assigned_hint', '{value} manual overrides').replace(
        '{value}',
        String(coverage.manual_overrides || 0),
      ),
      icon: Activity,
    },
    {
      title: t('monitoring_profiles_metric_modes', 'Telemetry Modes'),
      value: [...new Set(profiles.map((item) => item.telemetry_mode).filter(Boolean))].length,
      hint: t('monitoring_profiles_metric_modes_hint', 'Profile coverage for managed and discovered assets'),
      icon: Gauge,
    },
  ];

  return (
    <div
      data-testid="monitoring-profiles-page"
      className="p-3 sm:p-4 md:p-6 bg-[#f4f5f9] dark:bg-[#0e1012] h-full min-h-0 flex flex-col overflow-y-auto animate-fade-in text-gray-900 dark:text-white"
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between mb-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-blue-700 dark:border-blue-900/50 dark:bg-blue-500/10 dark:text-blue-300">
            <ShieldCheck size={14} />
            {t('monitoring_profiles_badge', 'Monitoring Profiles')}
          </div>
          <h1 className="mt-3 text-2xl font-black tracking-tight">
            {t('monitoring_profiles_title', 'Monitoring Profiles')}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
            {t(
              'monitoring_profiles_desc',
              'Turn discovery into active monitoring policy. Match vendor, role, model, and management state so devices land on the right polling and telemetry profile before operators tune them manually.',
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            data-testid="monitoring-profiles-refresh"
            onClick={() => loadCatalog(selectedProfileId)}
            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] px-4 py-2 text-sm font-bold text-gray-700 dark:text-gray-100"
          >
            <RefreshCw size={16} />
            {t('common_refresh', 'Refresh')}
          </button>
          {canAdmin && (
            <button
              data-testid="monitoring-profiles-new"
              onClick={handleNew}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 dark:bg-white px-4 py-2 text-sm font-bold text-white dark:text-slate-900"
            >
              <Plus size={16} />
              {t('monitoring_profiles_new', 'New Profile')}
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        {metricCards.map((card) => (
          <MetricCard key={card.title} {...card} />
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-4">
        <section className={`${PANEL_CLASS} p-4`}>
          <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">
            {t('monitoring_profiles_catalog_label', 'Profile Catalog')}
          </div>
          <div className="mt-4 space-y-2">
            {loading ? (
              <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                {t('common_loading', 'Loading...')}
              </div>
            ) : profiles.length === 0 ? (
              <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                {t('monitoring_profiles_empty', 'No monitoring profiles yet.')}
              </div>
            ) : (
              profiles.map((profile) => {
                const active = Number(profile.id) === Number(selectedProfileId);
                return (
                  <button
                    key={profile.id}
                    onClick={() => handleSelectProfile(profile)}
                    className={`w-full rounded-xl border px-4 py-3 text-left transition-colors ${
                      active
                        ? 'border-blue-500 bg-blue-50/90 dark:border-blue-500 dark:bg-blue-500/10'
                        : 'border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] hover:border-blue-300 dark:hover:border-blue-800'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-bold text-sm">{profile.name}</div>
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${scopeTone(profile.management_scope)}`}>
                        {profile.management_scope}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 font-mono">{profile.key}</div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                      <span>{t('monitoring_profiles_telemetry_label', 'Telemetry')}: {profile.telemetry_mode}</span>
                      <span>·</span>
                      <span>{t('monitoring_profiles_assigned_short', 'Assigned')}: {profile.assigned_devices || 0}</span>
                      <span>·</span>
                      <span>{t('monitoring_profiles_priority_short', 'Priority')}: {profile.priority}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className={`${PANEL_CLASS} p-5`}>
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">
                {t('monitoring_profiles_editor_label', 'Profile Editor')}
              </div>
              <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                {selectedProfile
                  ? t(
                      'monitoring_profiles_editor_existing',
                      'Adjust matching rules, telemetry mode, and interval overrides. Device recommendations will follow these rules unless operators manually override them.',
                    )
                  : t(
                      'monitoring_profiles_editor_new',
                      'Create a new monitoring profile to guide automatic recommendations after discovery or when devices are promoted into managed monitoring.',
                    )}
              </div>
            </div>
            {selectedProfile && canAdmin ? (
              <button
                data-testid="monitoring-profiles-delete"
                onClick={handleDelete}
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-bold text-rose-700 disabled:opacity-60 dark:border-rose-900/40 dark:bg-rose-900/10 dark:text-rose-300"
              >
                <Trash2 size={16} />
                {t('common_remove', 'Remove')}
              </button>
            ) : null}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-6">
            <div>
              <FieldLabel>{t('monitoring_profiles_key_label', 'Profile Key')}</FieldLabel>
              <Input
                value={form.key}
                onChange={(value) => setForm((current) => ({ ...current, key: value }))}
                placeholder={t('monitoring_profiles_key_placeholder', 'core-network')}
                disabled={!canAdmin}
              />
            </div>
            <div>
              <FieldLabel>{t('monitoring_profiles_name_label', 'Profile Name')}</FieldLabel>
              <Input
                value={form.name}
                onChange={(value) => setForm((current) => ({ ...current, name: value }))}
                placeholder={t('monitoring_profiles_name_placeholder', 'Core Network')}
                disabled={!canAdmin}
              />
            </div>
          </div>

          <div className="mt-4">
            <FieldLabel>{t('monitoring_profiles_description_label', 'Description')}</FieldLabel>
            <TextArea
              value={form.description}
              onChange={(value) => setForm((current) => ({ ...current, description: value }))}
              placeholder={t(
                'monitoring_profiles_description_placeholder',
                'Explain when this profile should be recommended and what operators should expect from it.',
              )}
              disabled={!canAdmin}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
            <div>
              <FieldLabel>{t('monitoring_profiles_scope_label', 'Management Scope')}</FieldLabel>
              <Select
                value={form.management_scope}
                onChange={(value) => setForm((current) => ({ ...current, management_scope: value }))}
                disabled={!canAdmin}
              >
                <option value="managed">{t('monitoring_profiles_scope_managed', 'Managed only')}</option>
                <option value="discovered_only">{t('monitoring_profiles_scope_discovered', 'Discovered only')}</option>
                <option value="any">{t('monitoring_profiles_scope_any', 'Any device state')}</option>
              </Select>
            </div>
            <div>
              <FieldLabel>{t('monitoring_profiles_telemetry_label', 'Telemetry Mode')}</FieldLabel>
              <Select
                value={form.telemetry_mode}
                onChange={(value) => setForm((current) => ({ ...current, telemetry_mode: value }))}
                disabled={!canAdmin}
              >
                <option value="hybrid">{t('monitoring_profiles_telemetry_hybrid', 'Hybrid')}</option>
                <option value="snmp">{t('monitoring_profiles_telemetry_snmp', 'SNMP')}</option>
                <option value="ssh">{t('monitoring_profiles_telemetry_ssh', 'SSH')}</option>
                <option value="gnmi">{t('monitoring_profiles_telemetry_gnmi', 'gNMI')}</option>
              </Select>
            </div>
            <div>
              <FieldLabel>{t('monitoring_profiles_priority_label', 'Priority')}</FieldLabel>
              <Input
                type="number"
                min={1}
                max={400}
                value={String(form.priority)}
                onChange={(value) => setForm((current) => ({ ...current, priority: Number(value || 100) }))}
                disabled={!canAdmin}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
            <div>
              <FieldLabel>{t('monitoring_profiles_polling_label', 'Polling Interval Override')}</FieldLabel>
              <Input
                type="number"
                min={0}
                value={String(form.polling_interval_override)}
                onChange={(value) => setForm((current) => ({ ...current, polling_interval_override: value }))}
                placeholder={t('monitoring_profiles_polling_placeholder', 'Leave empty to inherit')}
                disabled={!canAdmin}
              />
            </div>
            <div>
              <FieldLabel>{t('monitoring_profiles_status_label', 'Status Interval Override')}</FieldLabel>
              <Input
                type="number"
                min={0}
                value={String(form.status_interval_override)}
                onChange={(value) => setForm((current) => ({ ...current, status_interval_override: value }))}
                placeholder={t('monitoring_profiles_status_placeholder', 'Leave empty to inherit')}
                disabled={!canAdmin}
              />
            </div>
            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3">
              <label className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-bold text-gray-900 dark:text-gray-100">
                    {t('monitoring_profiles_enabled_label', 'Active')}
                  </div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {t('monitoring_profiles_enabled_desc', 'Inactive profiles stay in the catalog but are skipped during recommendation.')}
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={Boolean(form.is_active)}
                  onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))}
                  disabled={!canAdmin}
                  className="h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
              </label>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-4">
            <div>
              <FieldLabel>{t('monitoring_profiles_match_device_types', 'Device Type Match')}</FieldLabel>
              <TextArea
                value={form.match_device_types_text}
                onChange={(value) => setForm((current) => ({ ...current, match_device_types_text: value }))}
                placeholder={t('monitoring_profiles_match_device_types_placeholder', 'cisco_ios, dasan_nos, fortinet')}
                rows={3}
                disabled={!canAdmin}
              />
            </div>
            <div>
              <FieldLabel>{t('monitoring_profiles_match_roles', 'Role Match')}</FieldLabel>
              <TextArea
                value={form.match_roles_text}
                onChange={(value) => setForm((current) => ({ ...current, match_roles_text: value }))}
                placeholder={t('monitoring_profiles_match_roles_placeholder', 'core, distribution, access')}
                rows={3}
                disabled={!canAdmin}
              />
            </div>
            <div>
              <FieldLabel>{t('monitoring_profiles_match_vendor_patterns', 'Vendor Pattern Match')}</FieldLabel>
              <TextArea
                value={form.match_vendor_patterns_text}
                onChange={(value) => setForm((current) => ({ ...current, match_vendor_patterns_text: value }))}
                placeholder={t('monitoring_profiles_match_vendor_patterns_placeholder', 'wireless, domestic, security')}
                rows={3}
                disabled={!canAdmin}
              />
            </div>
            <div>
              <FieldLabel>{t('monitoring_profiles_match_model_patterns', 'Model Pattern Match')}</FieldLabel>
              <TextArea
                value={form.match_model_patterns_text}
                onChange={(value) => setForm((current) => ({ ...current, match_model_patterns_text: value }))}
                placeholder={t('monitoring_profiles_match_model_patterns_placeholder', '9800, mx, aggregation')}
                rows={3}
                disabled={!canAdmin}
              />
            </div>
            <div>
              <FieldLabel>{t('monitoring_profiles_match_site_ids', 'Site Match')}</FieldLabel>
              <Input
                value={form.match_site_ids_text}
                onChange={(value) => setForm((current) => ({ ...current, match_site_ids_text: value }))}
                placeholder={t('monitoring_profiles_match_site_ids_placeholder', '1, 2, 8')}
                disabled={!canAdmin}
              />
            </div>
            <div>
              <FieldLabel>{t('monitoring_profiles_tags_label', 'Dashboard Tags')}</FieldLabel>
              <Input
                value={form.dashboard_tags_text}
                onChange={(value) => setForm((current) => ({ ...current, dashboard_tags_text: value }))}
                placeholder={t('monitoring_profiles_tags_placeholder', 'core, routing, critical')}
                disabled={!canAdmin}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 mt-6">
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {selectedProfile
                ? t('monitoring_profiles_editor_hint_existing', 'Assignments stay automatic unless operators manually override a device.')
                : t('monitoring_profiles_editor_hint_new', 'New profiles are available immediately after save and will participate in recommendation scoring.')}
            </div>
            {canAdmin && (
              <button
                data-testid="monitoring-profiles-save"
                onClick={handleSave}
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
              >
                <Save size={16} />
                {saving ? t('monitoring_profiles_saving', 'Saving...') : t('monitoring_profiles_save', 'Save Profile')}
              </button>
            )}
            {!canAdmin && canOperate && (
              <div className="text-xs font-bold text-amber-700 dark:text-amber-300">
                {t('monitoring_profiles_operator_note', 'Operators can review recommendations here. Administrators manage profile definitions.')}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default MonitoringProfilesPage;
