import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  CheckCircle2,
  FileCode2,
  GitBranch,
  Layers,
  ShieldCheck,
  Sparkles,
  Workflow,
} from 'lucide-react';

import { IntentTemplateService } from '../api/services';
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';
import { InlineLoading, SectionCard } from '../components/common/PageState';

const PANEL_CLASS = 'rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] shadow-sm';

const FIELD_LABEL_KEYS = {
  account_ids: ['cloud_intents_accounts', 'Accounts'],
  regions: ['cloud_intents_regions', 'Regions'],
  resource_types: ['cloud_intents_resource_types', 'Resource Types'],
  required_tags: ['cloud_intents_required_tags', 'Required Tags'],
  blocked_ingress_cidrs: ['cloud_intents_blocked_ingress', 'Blocked Ingress CIDRs'],
  protected_route_destinations: ['cloud_intents_protected_routes', 'Protected Route Destinations'],
  allowed_default_route_targets: ['cloud_intents_allowed_defaults', 'Allowed Default Route Targets'],
  enforce_private_only_next_hop: ['cloud_intents_private_next_hop', 'Enforce private-only next hop'],
};

const CATEGORY_STYLES = {
  guardrail: 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/20 dark:text-sky-300 dark:border-sky-800/50',
  security: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/20 dark:text-rose-300 dark:border-rose-800/50',
  routing: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-800/50',
  compliance: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300 dark:border-emerald-800/50',
};

const RISK_STYLES = {
  low: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300 dark:border-emerald-800/50',
  moderate: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-800/50',
  high: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/20 dark:text-rose-300 dark:border-rose-800/50',
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

const friendlyFieldLabel = (fieldKey) => {
  const [key, fallback] = FIELD_LABEL_KEYS[fieldKey] || [null, fieldKey];
  return key ? t(key, fallback) : String(fallback || fieldKey);
};

const riskNoteLabel = (note) => {
  const normalized = String(note || '').trim().toLowerCase();
  const map = {
    approval_required: t('intent_templates_note_approval_required', 'Approval stays required'),
    verify_post_check: t('intent_templates_note_verify_post_check', 'Post-check should be reviewed'),
    narrow_scope_first: t('intent_templates_note_narrow_scope_first', 'Start narrow and expand later'),
    public_edge_review: t('intent_templates_note_public_edge_review', 'Review internet-facing edge resources'),
    service_owner_signoff: t('intent_templates_note_service_owner_signoff', 'Get service-owner signoff'),
    default_route_guardrail: t('intent_templates_note_default_route_guardrail', 'Default route changes are high impact'),
    rollback_ready: t('intent_templates_note_rollback_ready', 'Confirm rollback path before apply'),
    good_first_template: t('intent_templates_note_good_first_template', 'Good first template for baseline rollout'),
    wide_scope_ready: t('intent_templates_note_wide_scope_ready', 'Safe candidate for broader scope after review'),
  };
  return map[normalized] || normalized;
};

const templateDisplayName = (template) =>
  t(`intent_templates_${template?.key}_name`, String(template?.name || '').trim() || String(template?.key || '').trim());

const templateDisplaySummary = (template) =>
  t(`intent_templates_${template?.key}_summary`, String(template?.summary || '').trim());

const IntentTemplatesPage = () => {
  const locale = useLocaleRerender();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState({ templates: [], coverage: {} });

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const response = await IntentTemplateService.getCatalog();
        if (!alive) return;
        setCatalog(response?.data || { templates: [], coverage: {} });
      } catch (error) {
        if (!alive) return;
        toast.error(`${t('intent_templates_load_failed', 'Failed to load intent templates')}: ${error?.response?.data?.detail || error.message}`);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [toast]);

  const templates = Array.isArray(catalog?.templates) ? catalog.templates : [];
  const coverage = catalog?.coverage || {};

  const sortedTemplates = useMemo(
    () =>
      [...templates].sort((a, b) =>
        templateDisplayName(a).localeCompare(templateDisplayName(b)),
      ),
    [templates, locale],
  );

  const handleUseTemplate = (template) => {
    navigate('/cloud/intents', {
      state: {
        intentTemplatePrefill: template,
      },
    });
  };

  if (loading) {
    return <InlineLoading label={t('intent_templates_loading', 'Loading intent template catalog...')} />;
  }

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012] min-h-full text-gray-900 dark:text-white animate-fade-in">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between mb-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.22em] text-blue-700 dark:border-blue-900/40 dark:bg-blue-950/20 dark:text-blue-300">
            <Sparkles size={12} />
            {t('intent_templates_eyebrow', 'Template Studio')}
          </div>
          <h1 className="mt-3 text-2xl font-bold text-gray-900 dark:text-white">
            {t('intent_templates_title', 'Intent Templates')}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
            {t(
              'intent_templates_desc',
              'Use curated operating templates as the starting point for Cloud Intents so teams move from a proven policy shape into validation, preview, approval, and evidence without rebuilding the same draft every time.',
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => navigate('/cloud/intents')}
            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2 text-sm font-bold text-gray-700 hover:bg-gray-50 dark:border-white/10 dark:bg-white/5 dark:text-gray-100 dark:hover:bg-white/10"
          >
            <GitBranch size={14} />
            {t('intent_templates_open_cloud_intents', 'Open Cloud Intents')}
          </button>
          <button
            onClick={() => navigate('/automation')}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white hover:bg-blue-500"
          >
            <Workflow size={14} />
            {t('intent_templates_open_automation', 'Open Operations Home')}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <MetricCard
          icon={FileCode2}
          title={t('intent_templates_metric_count', 'Templates')}
          value={Number(coverage.template_count || templates.length || 0)}
          hint={t('intent_templates_metric_count_hint', 'Curated starting points for cloud policy intent drafts')}
        />
        <MetricCard
          icon={Layers}
          title={t('intent_templates_metric_providers', 'Providers')}
          value={Number(coverage.provider_count || 0)}
          hint={Array.isArray(coverage.providers) && coverage.providers.length > 0 ? coverage.providers.join(', ').toUpperCase() : t('intent_templates_metric_providers_hint', 'Provider coverage')}
        />
        <MetricCard
          icon={ShieldCheck}
          title={t('intent_templates_metric_categories', 'Categories')}
          value={Array.isArray(coverage.categories) ? coverage.categories.length : 0}
          hint={Array.isArray(coverage.categories) && coverage.categories.length > 0 ? coverage.categories.join(', ') : t('intent_templates_metric_categories_hint', 'Guardrail, security, routing, compliance')}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {sortedTemplates.map((template) => {
          const starter = template?.starter_payload || {};
          const category = String(template?.category || '').trim().toLowerCase();
          const risk = String(template?.risk_level || '').trim().toLowerCase();
          return (
            <SectionCard key={template.key} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-bold text-gray-900 dark:text-white">
                    {templateDisplayName(template)}
                  </div>
                  <div className="mt-2 text-sm text-gray-600 dark:text-gray-300 max-w-2xl">
                    {templateDisplaySummary(template)}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${CATEGORY_STYLES[category] || CATEGORY_STYLES.guardrail}`}>
                    {t(`intent_templates_category_${category}`, category || 'template')}
                  </span>
                  <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${RISK_STYLES[risk] || RISK_STYLES.moderate}`}>
                    {t(`intent_templates_risk_${risk}`, risk || 'moderate')}
                  </span>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2 text-[11px]">
                {Array.isArray(template.supported_providers) && template.supported_providers.length > 0 ? (
                  <span className="inline-flex items-center rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 font-bold text-sky-700 dark:border-sky-900/40 dark:bg-sky-950/20 dark:text-sky-300">
                    {t('intent_templates_supported_providers', 'Providers')}: {template.supported_providers.join(', ').toUpperCase()}
                  </span>
                ) : null}
                {Array.isArray(starter.resource_types) && starter.resource_types.length > 0 ? (
                  <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 font-bold text-gray-700 dark:border-white/10 dark:bg-white/5 dark:text-gray-300">
                    {t('intent_templates_resource_scope', 'Resources')}: {starter.resource_types.join(', ')}
                  </span>
                ) : null}
              </div>

              <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-black/20 p-4">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">
                    {t('intent_templates_parameters_title', 'Parameter Schema')}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {Array.isArray(template.parameter_schema) && template.parameter_schema.length > 0 ? (
                      template.parameter_schema.map((field) => (
                        <span
                          key={`${template.key}-${field.field_key}`}
                          className="inline-flex items-center rounded-full border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-gray-700 dark:border-white/10 dark:bg-white/5 dark:text-gray-200"
                        >
                          {friendlyFieldLabel(field.field_key)}
                          {field.required ? ` • ${t('intent_templates_required_short', 'Required')}` : ''}
                        </span>
                      ))
                    ) : (
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {t('intent_templates_parameters_empty', 'Template fields are not available yet.')}
                      </div>
                    )}
                  </div>
                </div>

                <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-black/20 p-4">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">
                    {t('intent_templates_risk_notes_title', 'Operating Notes')}
                  </div>
                  <div className="mt-3 space-y-2">
                    {Array.isArray(template.risk_notes) && template.risk_notes.length > 0 ? (
                      template.risk_notes.map((note) => (
                        <div key={`${template.key}-${note}`} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
                          <CheckCircle2 size={14} className="mt-0.5 text-emerald-500" />
                          <span>{riskNoteLabel(note)}</span>
                        </div>
                      ))
                    ) : (
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {t('intent_templates_risk_notes_empty', 'No operating notes registered for this template yet.')}
                      </div>
                    )}
                  </div>
                  {template.recommended_scope ? (
                    <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 px-3 py-3 text-sm text-blue-900 dark:border-blue-900/40 dark:bg-blue-950/20 dark:text-blue-200">
                      {t(`intent_templates_${template.key}_recommended_scope`, template.recommended_scope)}
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="mt-5 flex flex-wrap gap-2">
                <button
                  onClick={() => handleUseTemplate(template)}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white hover:bg-blue-500"
                >
                  <GitBranch size={14} />
                  {t('intent_templates_use_template', 'Use Template')}
                </button>
                <button
                  onClick={() => navigate('/cloud/intents')}
                  className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2 text-sm font-bold text-gray-700 hover:bg-gray-50 dark:border-white/10 dark:bg-white/5 dark:text-gray-100 dark:hover:bg-white/10"
                >
                  <ArrowRight size={14} />
                  {t('intent_templates_open_intents_secondary', 'Open Cloud Intents')}
                </button>
              </div>
            </SectionCard>
          );
        })}
      </div>
    </div>
  );
};

export default IntentTemplatesPage;
