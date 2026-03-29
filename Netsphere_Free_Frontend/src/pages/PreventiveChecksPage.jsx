import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Download,
  FileCheck,
  Play,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
} from 'lucide-react';

import { PreventiveCheckService } from '../api/services';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';

const PANEL_CLASS = 'rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] shadow-sm';

const CHECK_LIBRARY = [
  { key: 'device_offline', label: 'Offline device', desc: 'Flags devices currently marked offline.', defaultSeverity: 'critical' },
  { key: 'stale_last_seen', label: 'Stale last seen', desc: 'Flags devices that have not checked in within the threshold.', defaultSeverity: 'warning', thresholdKey: 'threshold_minutes', thresholdLabel: 'Threshold (minutes)' },
  { key: 'active_critical_issues', label: 'Active critical issues', desc: 'Flags devices with active critical issues.', defaultSeverity: 'critical' },
  { key: 'active_warning_issues', label: 'Active warning issues', desc: 'Flags devices with active warning issues.', defaultSeverity: 'warning' },
  { key: 'compliance_violation', label: 'Compliance violation', desc: 'Flags devices whose compliance score is below the threshold.', defaultSeverity: 'warning', thresholdKey: 'min_score', thresholdLabel: 'Minimum score' },
  { key: 'drift_detected', label: 'Drift detected', desc: 'Flags devices whose latest compliance report indicates drift.', defaultSeverity: 'warning' },
  { key: 'discovered_only_device', label: 'Discovered-only device', desc: 'Highlights devices outside the managed monitoring pool.', defaultSeverity: 'info' },
];

const DEFAULT_FORM = {
  name: '',
  description: '',
  rolesText: '',
  scopeMode: 'managed_only',
  cadence: 'manual',
  weekday: 'monday',
  hour: 9,
  minute: 0,
  isEnabled: true,
  checks: CHECK_LIBRARY.map((item) => ({
    key: item.key,
    enabled: ['device_offline', 'active_critical_issues', 'compliance_violation'].includes(item.key),
    severity: item.defaultSeverity,
    threshold_minutes: 180,
    min_score: 95,
  })),
};

const unwrapArray = (value) => (Array.isArray(value) ? value : []);

const severityTone = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'critical') return 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:border-rose-900/60';
  if (normalized === 'warning') return 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-900/60';
  if (normalized === 'info') return 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-900/60';
  return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-900/60';
};

const MetricCard = ({ title, value, hint }) => (
  <div className={`${PANEL_CLASS} p-4`}>
    <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{title}</div>
    <div className="mt-2 text-2xl font-black text-gray-900 dark:text-gray-100">{value}</div>
    {hint ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</div> : null}
  </div>
);

const FieldLabel = ({ children }) => (
  <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold mb-2">{children}</div>
);

const Input = ({ value, onChange, placeholder, type = 'text', min, max, disabled = false }) => (
  <input
    value={value}
    type={type}
    min={min}
    max={max}
    disabled={disabled}
    onChange={(event) => onChange(event.target.value)}
    placeholder={placeholder}
    className="w-full rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 disabled:opacity-60"
  />
);

const TextArea = ({ value, onChange, placeholder, rows = 4 }) => (
  <textarea
    value={value}
    onChange={(event) => onChange(event.target.value)}
    placeholder={placeholder}
    rows={rows}
    className="w-full rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 resize-y"
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

const formatTs = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('ko-KR', { hour12: false });
};

const parseFilename = (contentDisposition) => {
  const value = String(contentDisposition || '');
  const match = value.match(/filename="?([^"]+)"?/i);
  return match ? match[1] : null;
};

const downloadBlob = (blob, filename) => {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || 'preventive_check_run.csv';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
};

const normalizeTemplateToForm = (template) => {
  if (!template) return DEFAULT_FORM;
  const roles = Array.isArray(template?.target_scope?.roles) ? template.target_scope.roles : [];
  const states = Array.isArray(template?.target_scope?.management_states) ? template.target_scope.management_states : ['managed'];
  const checksByKey = new Map(unwrapArray(template?.checks).map((row) => [String(row.key || ''), row]));
  return {
    name: String(template.name || ''),
    description: String(template.description || ''),
    rolesText: roles.join(', '),
    scopeMode: states.includes('discovered_only') ? 'managed_and_discovered' : 'managed_only',
    cadence: String(template?.schedule?.cadence || 'manual'),
    weekday: String(template?.schedule?.weekday || 'monday'),
    hour: Number(template?.schedule?.hour ?? 9),
    minute: Number(template?.schedule?.minute ?? 0),
    isEnabled: Boolean(template?.is_enabled ?? true),
    checks: CHECK_LIBRARY.map((item) => {
      const source = checksByKey.get(item.key) || {};
      return {
        key: item.key,
        enabled: Boolean(source.enabled),
        severity: String(source.severity || item.defaultSeverity),
        threshold_minutes: Number(source.threshold_minutes ?? 180),
        min_score: Number(source.min_score ?? 95),
      };
    }),
  };
};

const buildPayload = (form) => ({
  name: String(form.name || '').trim(),
  description: String(form.description || '').trim(),
  is_enabled: Boolean(form.isEnabled),
  target_scope: {
    roles: String(form.rolesText || '')
      .split(/\r?\n|,/)
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean),
    management_states: form.scopeMode === 'managed_and_discovered' ? ['managed', 'discovered_only'] : ['managed'],
  },
  schedule: {
    cadence: String(form.cadence || 'manual'),
    weekday: String(form.weekday || 'monday'),
    hour: Number(form.hour || 0),
    minute: Number(form.minute || 0),
    timezone: 'Asia/Seoul',
  },
  checks: form.checks.filter((row) => row.enabled).map((row) => ({
    key: row.key,
    enabled: true,
    severity: row.severity,
    threshold_minutes: Number(row.threshold_minutes || 180),
    min_score: Number(row.min_score || 95),
  })),
});

const PreventiveChecksPage = () => {
  useLocaleRerender();
  const { isAtLeast } = useAuth();
  const { toast } = useToast();
  const canOperate = isAtLeast('operator');

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [runningTemplateId, setRunningTemplateId] = useState(null);
  const [summary, setSummary] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [form, setForm] = useState(DEFAULT_FORM);

  const selectedTemplate = useMemo(
    () => templates.find((item) => Number(item.id) === Number(selectedTemplateId)) || null,
    [templates, selectedTemplateId],
  );
  const selectedRun = useMemo(
    () => runs.find((item) => Number(item.id) === Number(selectedRunId)) || null,
    [runs, selectedRunId],
  );

  const loadAll = async ({ preferredTemplateId = null, preferredRunId = null } = {}) => {
    setLoading(true);
    try {
      const [summaryRes, templatesRes, runsRes] = await Promise.all([
        PreventiveCheckService.getSummary(),
        PreventiveCheckService.listTemplates(),
        PreventiveCheckService.listRuns(),
      ]);
      const templateRows = unwrapArray(templatesRes?.data);
      const runRows = unwrapArray(runsRes?.data);
      setSummary(summaryRes?.data || null);
      setTemplates(templateRows);
      setRuns(runRows);

      const nextTemplate =
        templateRows.find((item) => Number(item.id) === Number(preferredTemplateId || selectedTemplateId)) ||
        templateRows[0] ||
        null;
      setSelectedTemplateId(nextTemplate?.id || null);
      setForm(normalizeTemplateToForm(nextTemplate));

      const nextRun =
        runRows.find((item) => Number(item.id) === Number(preferredRunId || selectedRunId)) ||
        runRows[0] ||
        null;
      setSelectedRunId(nextRun?.id || null);
    } catch (error) {
      toast.error(`${t('preventive_checks_load_failed', 'Failed to load preventive checks')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, []);

  const handleNewTemplate = () => {
    setSelectedTemplateId(null);
    setForm(DEFAULT_FORM);
  };

  const handleSelectTemplate = (template) => {
    setSelectedTemplateId(template?.id || null);
    setForm(normalizeTemplateToForm(template));
  };

  const handleSave = async () => {
    const payload = buildPayload(form);
    if (!payload.name) {
      toast.error(t('preventive_checks_name_required', 'Template name is required.'));
      return;
    }
    if (!payload.checks.length) {
      toast.error(t('preventive_checks_check_required', 'Enable at least one preventive check.'));
      return;
    }
    setSaving(true);
    try {
      const response = selectedTemplateId
        ? await PreventiveCheckService.updateTemplate(selectedTemplateId, payload)
        : await PreventiveCheckService.createTemplate(payload);
      const nextTemplateId = response?.data?.id || selectedTemplateId;
      toast.success(
        selectedTemplateId
          ? t('preventive_checks_template_updated', 'Preventive check template updated.')
          : t('preventive_checks_template_created', 'Preventive check template created.'),
      );
      await loadAll({ preferredTemplateId: nextTemplateId, preferredRunId: selectedRunId });
    } catch (error) {
      toast.error(`${t('preventive_checks_save_failed', 'Failed to save preventive check template')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedTemplateId) return;
    if (!window.confirm(t('preventive_checks_delete_confirm', 'Delete this preventive check template?'))) return;
    setSaving(true);
    try {
      await PreventiveCheckService.deleteTemplate(selectedTemplateId);
      toast.success(t('preventive_checks_template_deleted', 'Preventive check template deleted.'));
      setSelectedTemplateId(null);
      setForm(DEFAULT_FORM);
      await loadAll();
    } catch (error) {
      toast.error(`${t('preventive_checks_delete_failed', 'Failed to delete preventive check template')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRunTemplate = async (templateId) => {
    if (!templateId) return;
    setRunningTemplateId(templateId);
    try {
      const response = await PreventiveCheckService.runTemplate(templateId);
      const runId = response?.data?.id || null;
      toast.success(t('preventive_checks_run_completed', 'Preventive check completed.'));
      await loadAll({ preferredTemplateId: templateId, preferredRunId: runId });
    } catch (error) {
      toast.error(`${t('preventive_checks_run_failed', 'Failed to run preventive check')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setRunningTemplateId(null);
    }
  };

  const handleExportRun = async (runId, format = 'csv') => {
    if (!runId) return;
    try {
      const response = await PreventiveCheckService.exportRun(runId, { format });
      const fallbackExt =
        format === 'pdf' ? 'pdf' : format === 'md' ? 'md' : format === 'json' ? 'json' : 'csv';
      const filename = parseFilename(response?.headers?.['content-disposition']) || `preventive_check_run_${runId}.${fallbackExt}`;
      downloadBlob(response.data, filename);
    } catch (error) {
      toast.error(`${t('preventive_checks_export_failed', 'Failed to export preventive check run')}: ${error?.response?.data?.detail || error.message}`);
    }
  };

  const updateCheck = (key, patch) => {
    setForm((current) => ({
      ...current,
      checks: current.checks.map((row) => (row.key === key ? { ...row, ...patch } : row)),
    }));
  };

  const summaryCards = [
    {
      title: t('preventive_checks_templates_total', 'Templates'),
      value: Number(summary?.templates_total || 0),
      hint: t('preventive_checks_templates_enabled_hint', '{value} enabled').replace('{value}', String(summary?.enabled_templates || 0)),
    },
    {
      title: t('preventive_checks_recent_runs_total', 'Recent Runs'),
      value: Number(summary?.recent_runs_total || 0),
      hint: summary?.last_run_at ? `${t('preventive_checks_last_run', 'Last run')} ${formatTs(summary.last_run_at)}` : t('preventive_checks_no_runs_yet', 'No runs yet'),
    },
    {
      title: t('preventive_checks_critical_devices', 'Critical Devices'),
      value: Number(summary?.recent_critical_devices || 0),
      hint: t('preventive_checks_failed_total_hint', '{value} failed checks in recent runs').replace('{value}', String(summary?.recent_failed_checks_total || 0)),
    },
  ];

  return (
    <div className="space-y-6">
      <div className={`${PANEL_CLASS} p-6`}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-blue-700 dark:border-blue-900/60 dark:bg-blue-500/10 dark:text-blue-300">
              <ShieldCheck size={14} />
              {t('preventive_checks_header_badge', 'Operational Preventive Checks')}
            </div>
            <h1 className="mt-3 text-2xl font-black text-gray-900 dark:text-gray-100">{t('preventive_checks_title', 'Preventive Checks')}</h1>
            <p className="mt-2 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
              {t(
                'preventive_checks_desc',
                'Turn recurring infrastructure review into a repeatable operating workflow. Define preventive check templates, run them on demand, and export results for operational evidence.',
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => void loadAll()}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2 text-sm font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5"
            >
              <RefreshCw size={16} />
              {t('common_refresh', 'Refresh')}
            </button>
            <button
              onClick={handleNewTemplate}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-600 hover:bg-blue-500 px-4 py-2 text-sm font-bold text-white shadow-sm"
            >
              <Plus size={16} />
              {t('preventive_checks_new_template', 'New Template')}
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {summaryCards.map((card) => (
          <MetricCard key={card.title} title={card.title} value={card.value} hint={card.hint} />
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
        <section className={`${PANEL_CLASS} p-5`}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">{t('preventive_checks_templates_label', 'Templates')}</div>
              <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">{t('preventive_checks_templates_help', 'Choose a template to edit or run.')}</div>
            </div>
            <FileCheck className="text-blue-500" size={18} />
          </div>
          <div className="mt-4 space-y-3">
            {loading ? (
              <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">{t('common_loading', 'Loading...')}</div>
            ) : templates.length === 0 ? (
              <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">{t('preventive_checks_no_templates', 'No preventive check templates yet.')}</div>
            ) : (
              templates.map((template) => {
                const active = Number(template.id) === Number(selectedTemplateId);
                const running = Number(runningTemplateId) === Number(template.id);
                return (
                  <button
                    key={template.id}
                    onClick={() => handleSelectTemplate(template)}
                    className={`w-full rounded-2xl border px-4 py-4 text-left transition ${
                      active
                        ? 'border-blue-500 bg-blue-50/70 dark:border-blue-500 dark:bg-blue-500/10'
                        : 'border-gray-200 bg-white hover:border-blue-300 hover:bg-gray-50 dark:border-gray-800 dark:bg-[#111315] dark:hover:border-blue-800/80 dark:hover:bg-white/5'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{template.name}</div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{template.description || t('preventive_checks_no_description', 'No description')}</div>
                      </div>
                      <span className={`inline-flex rounded-full px-2 py-1 text-[10px] font-bold uppercase tracking-[0.16em] ${template.is_enabled ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300' : 'bg-gray-100 text-gray-600 dark:bg-white/5 dark:text-gray-400'}`}>
                        {template.is_enabled ? t('common_enabled', 'Enabled') : t('common_disabled', 'Disabled')}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                      <span>{t('preventive_checks_scope_short', 'Scope')}: {Array.isArray(template?.target_scope?.management_states) && template.target_scope.management_states.includes('discovered_only') ? t('preventive_checks_scope_managed_and_discovered', 'Managed + discovered only') : t('preventive_checks_scope_managed_only', 'Managed only')}</span>
                      <span>•</span>
                      <span>{t('preventive_checks_next_run_short', 'Next')}: {template.next_run_at ? formatTs(template.next_run_at) : t('preventive_checks_manual_only', 'Manual')}</span>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleRunTemplate(template.id);
                        }}
                        disabled={!canOperate || running}
                        className="inline-flex items-center gap-1 rounded-lg border border-blue-200 px-2.5 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-50 dark:border-blue-900/60 dark:text-blue-300 dark:hover:bg-blue-500/10 disabled:opacity-60"
                      >
                        <Play size={13} />
                        {running ? t('preventive_checks_running', 'Running...') : t('preventive_checks_run_now', 'Run now')}
                      </button>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className={`${PANEL_CLASS} p-5`}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">{t('preventive_checks_editor_label', 'Template Editor')}</div>
              <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                {selectedTemplateId
                  ? t('preventive_checks_editing_existing', 'Update the selected template and rerun it when you are ready.')
                  : t('preventive_checks_editing_new', 'Create a new preventive check template for recurring operational review.')}
              </div>
            </div>
            {selectedTemplateId ? (
              <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-bold text-gray-600 dark:bg-white/5 dark:text-gray-300">#{selectedTemplateId}</span>
            ) : null}
          </div>

          <div className="mt-5 grid gap-5 md:grid-cols-2">
            <div className="md:col-span-2">
              <FieldLabel>{t('preventive_checks_name_label', 'Template name')}</FieldLabel>
              <Input value={form.name} onChange={(value) => setForm((current) => ({ ...current, name: value }))} placeholder={t('preventive_checks_name_placeholder', 'Weekly Core Preventive Review')} />
            </div>
            <div className="md:col-span-2">
              <FieldLabel>{t('preventive_checks_description_label', 'Description')}</FieldLabel>
              <TextArea value={form.description} onChange={(value) => setForm((current) => ({ ...current, description: value }))} placeholder={t('preventive_checks_description_placeholder', 'Explain what this preventive review should validate.')} rows={3} />
            </div>
            <div>
              <FieldLabel>{t('preventive_checks_scope_label', 'Monitoring scope')}</FieldLabel>
              <Select value={form.scopeMode} onChange={(value) => setForm((current) => ({ ...current, scopeMode: value }))}>
                <option value="managed_only">{t('preventive_checks_scope_managed_only', 'Managed only')}</option>
                <option value="managed_and_discovered">{t('preventive_checks_scope_managed_and_discovered', 'Managed + discovered only')}</option>
              </Select>
            </div>
            <div>
              <FieldLabel>{t('preventive_checks_roles_label', 'Role filter')}</FieldLabel>
              <Input value={form.rolesText} onChange={(value) => setForm((current) => ({ ...current, rolesText: value }))} placeholder={t('preventive_checks_roles_placeholder', 'core, access, edge')} />
            </div>
            <div>
              <FieldLabel>{t('preventive_checks_cadence_label', 'Cadence')}</FieldLabel>
              <Select value={form.cadence} onChange={(value) => setForm((current) => ({ ...current, cadence: value }))}>
                <option value="manual">{t('preventive_checks_cadence_manual', 'Manual only')}</option>
                <option value="daily">{t('preventive_checks_cadence_daily', 'Daily')}</option>
                <option value="weekly">{t('preventive_checks_cadence_weekly', 'Weekly')}</option>
              </Select>
            </div>
            <div>
              <FieldLabel>{t('preventive_checks_enabled_label', 'Enabled')}</FieldLabel>
              <label className="inline-flex items-center gap-3 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-3 text-sm text-gray-700 dark:text-gray-200">
                <input type="checkbox" checked={form.isEnabled} onChange={(event) => setForm((current) => ({ ...current, isEnabled: event.target.checked }))} />
                <span>{t('preventive_checks_enabled_desc', 'Include this template in scheduled review')}</span>
              </label>
            </div>
            {form.cadence === 'weekly' ? (
              <div>
                <FieldLabel>{t('preventive_checks_weekday_label', 'Weekday')}</FieldLabel>
                <Select value={form.weekday} onChange={(value) => setForm((current) => ({ ...current, weekday: value }))}>
                  <option value="monday">{t('weekday_monday', 'Monday')}</option>
                  <option value="tuesday">{t('weekday_tuesday', 'Tuesday')}</option>
                  <option value="wednesday">{t('weekday_wednesday', 'Wednesday')}</option>
                  <option value="thursday">{t('weekday_thursday', 'Thursday')}</option>
                  <option value="friday">{t('weekday_friday', 'Friday')}</option>
                  <option value="saturday">{t('weekday_saturday', 'Saturday')}</option>
                  <option value="sunday">{t('weekday_sunday', 'Sunday')}</option>
                </Select>
              </div>
            ) : null}
            {form.cadence !== 'manual' ? (
              <>
                <div>
                  <FieldLabel>{t('preventive_checks_hour_label', 'Hour')}</FieldLabel>
                  <Input type="number" min={0} max={23} value={form.hour} onChange={(value) => setForm((current) => ({ ...current, hour: value }))} />
                </div>
                <div>
                  <FieldLabel>{t('preventive_checks_minute_label', 'Minute')}</FieldLabel>
                  <Input type="number" min={0} max={59} value={form.minute} onChange={(value) => setForm((current) => ({ ...current, minute: value }))} />
                </div>
              </>
            ) : null}
          </div>

          <div className="mt-6">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
              <ShieldCheck size={14} />
              {t('preventive_checks_checks_label', 'Checks')}
            </div>
            <div className="mt-4 space-y-3">
              {CHECK_LIBRARY.map((item) => {
                const row = form.checks.find((check) => check.key === item.key) || {};
                return (
                  <div key={item.key} className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
                    <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                      <div>
                        <div className="flex items-center gap-3">
                          <label className="inline-flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-gray-100">
                            <input
                              type="checkbox"
                              checked={Boolean(row.enabled)}
                              onChange={(event) => updateCheck(item.key, { enabled: event.target.checked })}
                            />
                            <span>{item.label}</span>
                          </label>
                          <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${severityTone(row.severity)}`}>
                            {row.severity || item.defaultSeverity}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{item.desc}</div>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 xl:min-w-[280px]">
                        <Select value={row.severity || item.defaultSeverity} onChange={(value) => updateCheck(item.key, { severity: value })} disabled={!row.enabled}>
                          <option value="info">{t('preventive_checks_severity_info', 'Info')}</option>
                          <option value="warning">{t('preventive_checks_severity_warning', 'Warning')}</option>
                          <option value="critical">{t('preventive_checks_severity_critical', 'Critical')}</option>
                        </Select>
                        {item.thresholdKey ? (
                          <Input
                            type="number"
                            value={row[item.thresholdKey]}
                            disabled={!row.enabled}
                            onChange={(value) => updateCheck(item.key, { [item.thresholdKey]: value })}
                            placeholder={item.thresholdLabel}
                          />
                        ) : (
                          <div className="rounded-xl border border-dashed border-gray-200 dark:border-gray-800 px-3 py-3 text-xs text-gray-400 dark:text-gray-500">
                            {t('preventive_checks_no_threshold', 'No threshold')}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              onClick={handleSave}
              disabled={!canOperate || saving}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-600 hover:bg-blue-500 px-4 py-2 text-sm font-bold text-white shadow-sm disabled:opacity-60"
            >
              <Save size={16} />
              {saving ? t('preventive_checks_saving', 'Saving...') : t('preventive_checks_save_template', 'Save Template')}
            </button>
            {selectedTemplateId ? (
              <>
                <button
                  onClick={() => void handleRunTemplate(selectedTemplateId)}
                  disabled={!canOperate || Number(runningTemplateId) === Number(selectedTemplateId)}
                  className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 px-4 py-2 text-sm font-bold text-emerald-700 hover:bg-emerald-50 dark:border-emerald-900/60 dark:text-emerald-300 dark:hover:bg-emerald-500/10 disabled:opacity-60"
                >
                  <Play size={16} />
                  {Number(runningTemplateId) === Number(selectedTemplateId)
                    ? t('preventive_checks_running', 'Running...')
                    : t('preventive_checks_run_selected', 'Run Selected Template')}
                </button>
                <button
                  onClick={handleDelete}
                  disabled={!canOperate || saving}
                  className="inline-flex items-center gap-2 rounded-xl border border-rose-200 px-4 py-2 text-sm font-bold text-rose-700 hover:bg-rose-50 dark:border-rose-900/60 dark:text-rose-300 dark:hover:bg-rose-500/10 disabled:opacity-60"
                >
                  <Trash2 size={16} />
                  {t('common_remove', 'Remove')}
                </button>
              </>
            ) : null}
          </div>
        </section>

        <section className={`${PANEL_CLASS} p-5`}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">{t('preventive_checks_runs_label', 'Recent Runs')}</div>
              <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">{t('preventive_checks_runs_help', 'Review the latest preventive check results and export them as operational evidence.')}</div>
            </div>
            <Clock3 className="text-blue-500" size={18} />
          </div>

          <div className="mt-4 space-y-3">
            {loading ? (
              <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">{t('common_loading', 'Loading...')}</div>
            ) : runs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">{t('preventive_checks_no_runs', 'No preventive check runs yet.')}</div>
            ) : (
              runs.map((run) => {
                const active = Number(run.id) === Number(selectedRunId);
                const summaryData = run.summary || {};
                return (
                  <button
                    key={run.id}
                    onClick={() => setSelectedRunId(run.id)}
                    className={`w-full rounded-2xl border px-4 py-4 text-left transition ${
                      active
                        ? 'border-blue-500 bg-blue-50/70 dark:border-blue-500 dark:bg-blue-500/10'
                        : 'border-gray-200 bg-white hover:border-blue-300 hover:bg-gray-50 dark:border-gray-800 dark:bg-[#111315] dark:hover:border-blue-800/80 dark:hover:bg-white/5'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{run.template_name || t('preventive_checks_unknown_template', 'Unknown template')}</div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{formatTs(run.started_at)}</div>
                      </div>
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${severityTone(summaryData.critical_devices ? 'critical' : summaryData.warning_devices ? 'warning' : summaryData.info_devices ? 'info' : 'healthy')}`}>
                        {summaryData.critical_devices ? t('preventive_checks_run_status_critical', 'Critical') : summaryData.warning_devices ? t('preventive_checks_run_status_warning', 'Warning') : summaryData.info_devices ? t('preventive_checks_run_status_info', 'Info') : t('preventive_checks_run_status_healthy', 'Healthy')}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2 text-xs text-gray-600 dark:text-gray-300">
                      <div>{t('preventive_checks_devices_total', 'Devices')}: {summaryData.devices_total || 0}</div>
                      <div>{t('preventive_checks_failed_checks_total', 'Failed checks')}: {summaryData.failed_checks_total || 0}</div>
                      <div>{t('preventive_checks_warning_devices', 'Warning devices')}: {summaryData.warning_devices || 0}</div>
                      <div>{t('preventive_checks_critical_devices', 'Critical devices')}: {summaryData.critical_devices || 0}</div>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {selectedRun ? (
            <div className="mt-6 rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{selectedRun.template_name}</div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {t('preventive_checks_triggered_by', 'Triggered by')} {selectedRun.triggered_by || 'operator'} | {formatTs(selectedRun.finished_at || selectedRun.started_at)}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => void handleExportRun(selectedRun.id, 'pdf')}
                    className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-bold text-blue-700 hover:bg-blue-100 dark:border-blue-900/60 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/20"
                  >
                    <Download size={14} />
                    {t('preventive_checks_export_pdf', 'Export PDF')}
                  </button>
                  <button
                    onClick={() => void handleExportRun(selectedRun.id, 'csv')}
                    className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                  >
                    <Download size={14} />
                    {t('preventive_checks_export_csv', 'Export CSV')}
                  </button>
                  <button
                    onClick={() => void handleExportRun(selectedRun.id, 'md')}
                    className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
                  >
                    <Download size={14} />
                    {t('preventive_checks_export_markdown', 'Export Markdown')}
                  </button>
                </div>
              </div>

              <div className="mt-4 space-y-3 max-h-[520px] overflow-y-auto pr-1">
                {unwrapArray(selectedRun.findings).map((row) => (
                  <div key={`${selectedRun.id}-${row.device_id}`} className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#15181a] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-bold text-gray-900 dark:text-gray-100">{row.device_name}</div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {row.ip_address || '—'} | {row.role || t('common_unknown', 'Unknown')} | {row.management_state || t('common_unknown', 'Unknown')}
                        </div>
                      </div>
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${severityTone(row.status)}`}>
                        {row.status || 'healthy'}
                      </span>
                    </div>
                    <div className="mt-3 space-y-2">
                      {unwrapArray(row.findings).length === 0 ? (
                        <div className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-500/10 dark:text-emerald-300">
                          <CheckCircle2 size={14} />
                          {t('preventive_checks_no_findings', 'No findings for this device.')}
                        </div>
                      ) : (
                        unwrapArray(row.findings).map((finding, index) => (
                          <div key={`${row.device_id}-${finding.check_key}-${index}`} className="rounded-xl border border-gray-200 dark:border-gray-800 px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <div className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-gray-100">
                                <AlertTriangle size={14} className={String(finding.severity || '').toLowerCase() === 'critical' ? 'text-rose-500' : 'text-amber-500'} />
                                {String(finding.check_key || '').replaceAll('_', ' ')}
                              </div>
                              <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${severityTone(finding.severity)}`}>
                                {finding.severity || 'warning'}
                              </span>
                            </div>
                            <div className="mt-2 text-xs text-gray-600 dark:text-gray-300">{finding.message}</div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
};

export default PreventiveChecksPage;
