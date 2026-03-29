import React, { useEffect, useMemo, useState } from 'react';
import { Eye, History, Lock, ShieldCheck } from 'lucide-react';

import { PreviewService } from '../api/services';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';

const unwrapItems = (response) => {
  if (Array.isArray(response?.data?.items)) return response.data.items;
  if (Array.isArray(response?.data?.data?.items)) return response.data.data.items;
  return [];
};

const unwrapRecord = (response) => response?.data?.data || response?.data || null;

const PREVIEW_UPLOAD_TARGET_LABELS = {
  local_only: 'Local review only',
  remote_only: 'NetSphere Cloud intake',
  dual_write: 'Local review + NetSphere Cloud intake',
};

const PREVIEW_REGISTRATION_STATE_LABELS = {
  intake_server: 'NetSphere Cloud intake',
  local_only: 'Local review only',
  registered: 'Intake ready',
  pending_registration: 'Ready for intake registration',
  missing_credentials: 'Missing intake credentials',
  missing_remote_url: 'Missing intake upload URL',
  failed: 'Intake registration failed',
};

const PreviewContributionPage = () => {
  const { isAdmin } = useAuth();
  const { toast } = useToast();
  const canReviewAudit = isAdmin();
  const [policyLoading, setPolicyLoading] = useState(true);
  const [recentLoading, setRecentLoading] = useState(false);
  const [policy, setPolicy] = useState(null);
  const [recent, setRecent] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const uploadTargetLabel = t(
    `preview_upload_target_${policy?.upload_target_mode}`,
    PREVIEW_UPLOAD_TARGET_LABELS[policy?.upload_target_mode] || policy?.upload_target_mode || 'Local review only',
  );
  const registrationStateLabel = t(
    `preview_registration_state_${policy?.remote_upload_registration_state}`,
    PREVIEW_REGISTRATION_STATE_LABELS[policy?.remote_upload_registration_state] ||
      policy?.remote_upload_registration_state ||
      'Unknown',
  );
  const redactionSummaryItems = useMemo(
    () =>
      Object.entries(selectedRecord?.redaction_summary || {}).filter(([, value]) => Number(value || 0) > 0),
    [selectedRecord],
  );
  const allowedCommands = useMemo(
    () => (Array.isArray(policy?.allowed_commands) ? policy.allowed_commands : []),
    [policy],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const policyRes = await PreviewService.getPolicy();
        const nextPolicy = policyRes?.data || {};
        if (cancelled) return;
        setPolicy(nextPolicy);
      } catch (error) {
        if (!cancelled) {
          toast.error(error?.response?.data?.detail || error?.message || t('preview_load_failed'));
        }
      } finally {
        if (!cancelled) {
          setPolicyLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [toast]);

  useEffect(() => {
    if (policyLoading || !policy?.preview_enabled || !canReviewAudit) {
      setRecent([]);
      setRecentLoading(false);
      setSelectedId('');
      return;
    }

    let cancelled = false;
    setRecentLoading(true);
    (async () => {
      try {
        const recentRes = await PreviewService.listRecent({ limit: 20 });
        if (cancelled) return;
        const items = unwrapItems(recentRes);
        setRecent(items);
        setSelectedId((current) => {
          if (current && items.some((item) => String(item.id || '') === current)) {
            return current;
          }
          return items.length > 0 ? String(items[0].id || '') : '';
        });
      } catch (error) {
        if (!cancelled) {
          setRecent([]);
          setSelectedId('');
          toast.error(error?.response?.data?.detail || error?.message || t('preview_load_failed'));
        }
      } finally {
        if (!cancelled) {
          setRecentLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [canReviewAudit, policy?.preview_enabled, policyLoading, toast]);

  useEffect(() => {
    if (!selectedId || !canReviewAudit) {
      setSelectedRecord(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    (async () => {
      try {
        const response = await PreviewService.getContributionRecord(selectedId);
        if (!cancelled) {
          setSelectedRecord(unwrapRecord(response));
        }
      } catch (error) {
        if (!cancelled) {
          setSelectedRecord(null);
          toast.error(error?.response?.data?.detail || error?.message || t('preview_load_failed'));
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [canReviewAudit, selectedId, toast]);

  if (policyLoading) {
    return <div className="p-6 text-sm text-gray-500 dark:text-gray-300">{t('preview_loading')}</div>;
  }

  if (!policy?.preview_enabled) {
    return (
      <div className="p-6">
        <div className="rounded-2xl border border-amber-200 bg-amber-50/80 px-6 py-6 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
          {t('preview_not_enabled')}
        </div>
      </div>
    );
  }

  if (!canReviewAudit) {
    return (
      <div className="p-6">
        <div className="rounded-2xl border border-rose-200 bg-rose-50/80 px-6 py-6 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950/20 dark:text-rose-200">
          <div className="text-base font-semibold">
            {t('preview_audit_access_denied_title', 'Data handling audit is limited to administrators')}
          </div>
          <div className="mt-2">
            {t(
              'preview_audit_access_denied_desc',
              'Free collector review records stay hidden from regular operators. Administrators can inspect the locked installation policy, sanitized records, and masking evidence here when needed.',
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      <section className="rounded-3xl border border-gray-200 bg-white/90 shadow-sm dark:border-white/10 dark:bg-[#141618] overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-200 dark:border-white/10 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-amber-600/10 px-3 py-1 text-xs font-semibold text-amber-700 dark:text-amber-300">
              <ShieldCheck size={14} />
              {t('preview_audit_badge', 'Administrator audit')}
            </div>
            <h1 data-testid="preview-audit-title" className="mt-3 text-2xl font-bold text-gray-900 dark:text-white">
              {t('preview_audit_title', 'Data Handling Audit')}
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
              {t(
                'preview_audit_subtitle',
                'This administrator-only view shows installation policy, sanitized review records, and masking evidence. Original device output is never displayed here.',
              )}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs text-gray-600 dark:text-gray-300">
            <div className="rounded-2xl border border-gray-200 px-4 py-3 dark:border-white/10">
              <div className="font-semibold text-gray-900 dark:text-white">{t('preview_upload_label')}</div>
              <div>
                {policy?.upload_enabled
                  ? t('preview_enabled_locked', 'Enabled (locked)')
                  : policy?.upload_decision_recorded
                    ? t('preview_disabled_locked', 'Disabled (locked)')
                    : t('preview_upload_pending_consent', 'Awaiting first-run contribution choice')}
              </div>
            </div>
            <div className="rounded-2xl border border-gray-200 px-4 py-3 dark:border-white/10">
              <div className="font-semibold text-gray-900 dark:text-white">{t('preview_upload_target_label', 'Upload target')}</div>
              <div>{uploadTargetLabel}</div>
            </div>
            <div className="rounded-2xl border border-gray-200 px-4 py-3 dark:border-white/10 col-span-2">
              <div className="font-semibold text-gray-900 dark:text-white">{t('preview_remote_registration_label', 'Remote registration')}</div>
              <div>{registrationStateLabel}</div>
              {policy?.remote_upload_destination ? (
                <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                  {policy.remote_upload_destination}
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <div className="px-6 py-5 grid gap-4 lg:grid-cols-3">
          <div
            data-testid="preview-audit-policy-card"
            className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4 dark:border-amber-900 dark:bg-amber-950/10"
          >
            <div className="flex items-center gap-2 text-sm font-semibold text-amber-900 dark:text-amber-300">
              <Lock size={16} />
              {t('preview_audit_policy_title', 'Locked installation policy')}
            </div>
            <div className="mt-3 space-y-2 text-sm text-amber-800 dark:text-amber-200">
              <div>
                {t('preview_policy_state_fmt', 'State: {state} / Lock: {lock}')
                  .replace('{state}', policy?.upload_enabled ? t('preview_enabled', 'Enabled') : t('preview_disabled', 'Disabled'))
                  .replace('{lock}', policy?.upload_locked ? t('preview_policy_locked_badge', 'Locked') : t('common_unknown', 'Unknown'))}
              </div>
              <div>
                {t('preview_policy_scope_fmt', 'Scope: {scope}').replace(
                  '{scope}',
                  String(policy?.contribution_scope || 'allowlisted_read_only_commands_only'),
                )}
              </div>
              <div>
                {t('preview_audit_policy_change_path', 'Change path: {value}').replace(
                  '{value}',
                  policy?.upload_change_requires_reset
                    ? t('preview_audit_policy_reset_only', 'Reset or reinstall only')
                    : t('common_unknown', 'Unknown'),
                )}
              </div>
              {policy?.upload_opt_in_recorded_at ? (
                <div>
                  {t('preview_policy_recorded_fmt', 'Recorded: {when} / {actor}')
                    .replace('{when}', String(policy.upload_opt_in_recorded_at || ''))
                    .replace('{actor}', String(policy.upload_opt_in_actor || t('common_unknown', 'Unknown')))}
                </div>
              ) : null}
            </div>
          </div>

          <div
            data-testid="preview-audit-local-card"
            className="rounded-2xl border border-violet-200 bg-violet-50/70 p-4 dark:border-violet-900 dark:bg-violet-950/10"
          >
            <div className="text-sm font-semibold text-violet-900 dark:text-violet-300">
              {t('preview_local_boundary_title', 'What stays local')}
            </div>
            <ul className="mt-3 space-y-2 text-sm text-violet-800 dark:text-violet-200">
              <li>- {t('preview_local_boundary_item_raw', 'Raw command output before sanitize preview')}</li>
              <li>- {t('preview_local_boundary_item_credentials', 'Device credentials and login secrets')}</li>
              <li>- {t('preview_local_boundary_item_review', 'Local sanitize review and per-bundle consent')}</li>
              <li>- {t('preview_local_boundary_item_blocked', 'Commands outside the allowlist and blocked feature surfaces')}</li>
            </ul>
          </div>

          <div
            data-testid="preview-audit-outbound-card"
            className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4 dark:border-emerald-900 dark:bg-emerald-950/10"
          >
            <div className="text-sm font-semibold text-emerald-900 dark:text-emerald-300">
              {t('preview_outbound_boundary_title', 'What leaves this installation after review')}
            </div>
            <ul className="mt-3 space-y-2 text-sm text-emerald-800 dark:text-emerald-200">
              <li>- {t('preview_outbound_boundary_item_bundle', 'Only the sanitized bundle that you reviewed and confirmed for this upload')}</li>
              <li>- {t('preview_outbound_boundary_item_metadata', 'Contribution metadata such as command name, redaction summary, runtime route, and submission timestamp')}</li>
              <li>- {t('preview_outbound_boundary_item_notes', 'Optional notes that you choose to add for parser context')}</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <div className="rounded-3xl border border-gray-200 bg-white/90 shadow-sm dark:border-white/10 dark:bg-[#141618] overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-white/10">
            <div className="text-lg font-bold text-gray-900 dark:text-white">
              {t('preview_audit_allowed_commands_title', 'Allowed read-only command scope')}
            </div>
            <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
              {t(
                'preview_audit_allowed_commands_desc',
                'Only allowlisted read-only commands can ever contribute sanitized parser feedback from a Free collector.',
              )}
            </div>
          </div>
          <div className="p-6 space-y-2 max-h-[28rem] overflow-auto">
            {allowedCommands.map((command) => (
              <div
                key={command}
                className="rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700 dark:border-white/10 dark:text-gray-200"
              >
                {command}
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <section className="rounded-3xl border border-gray-200 bg-white/90 shadow-sm dark:border-white/10 dark:bg-[#141618] overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-white/10 flex items-center gap-2">
              <History size={18} className="text-gray-500" />
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                {t('preview_audit_recent_title', 'Recent processing records')}
              </h2>
            </div>
            <div className="p-6 space-y-3">
              {recentLoading ? (
                <div className="text-sm text-gray-500 dark:text-gray-400">{t('preview_loading')}</div>
              ) : !recent.length ? (
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  {t('preview_audit_recent_empty', 'No masked review records are stored yet.')}
                </div>
              ) : (
                recent.map((item) => {
                  const active = String(item.id || '') === selectedId;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      data-testid={`preview-audit-record-${String(item.id || '').replace(/[^a-zA-Z0-9_-]/g, '-')}`}
                      onClick={() => setSelectedId(String(item.id || ''))}
                      className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                        active
                          ? 'border-blue-500 bg-blue-50/70 dark:border-blue-400 dark:bg-blue-950/20'
                          : 'border-gray-200 hover:border-gray-300 dark:border-white/10 dark:hover:border-white/20'
                      }`}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-gray-900 dark:text-white">{item.id}</div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                            {item.device_type || t('common_unknown', 'unknown')} / {item.model || t('common_unknown', 'unknown')}
                          </div>
                        </div>
                        <div className="text-right text-xs text-gray-500 dark:text-gray-400">
                          <div>{String(item.entry_count || 0)} {t('preview_recent_commands')}</div>
                          <div className="mt-1">{String(item.submitted_at || '')}</div>
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>

          <section className="rounded-3xl border border-gray-200 bg-white/90 shadow-sm dark:border-white/10 dark:bg-[#141618] overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-white/10 flex items-center gap-2">
              <Eye size={18} className="text-gray-500" />
              <h2 data-testid="preview-audit-detail-title" className="text-lg font-bold text-gray-900 dark:text-white">
                {t('preview_audit_detail_title', 'Sanitized audit detail')}
              </h2>
            </div>
            <div className="p-6 space-y-4">
              {detailLoading ? (
                <div className="text-sm text-gray-500 dark:text-gray-400">{t('preview_loading')}</div>
              ) : !selectedRecord ? (
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  {t('preview_audit_detail_empty', 'Select a record to review sanitized content and masking evidence.')}
                </div>
              ) : (
                <>
                  <div
                    data-testid="preview-audit-raw-hidden-note"
                    className="rounded-2xl border border-sky-200 bg-sky-50/70 p-4 text-sm text-sky-900 dark:border-sky-900 dark:bg-sky-950/10 dark:text-sky-200"
                  >
                    {t(
                      'preview_audit_raw_hidden_note',
                      'Original device output is never displayed here. This audit view only shows sanitized review records and masking evidence.',
                    )}
                  </div>

                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 text-xs text-gray-600 dark:text-gray-300">
                    <div className="rounded-xl border border-gray-200 px-3 py-3 dark:border-white/10">
                      {t('preview_audit_meta_source', 'Recorded from: {value}').replace('{value}', String(selectedRecord.source || t('common_unknown', 'Unknown')))}
                    </div>
                    <div className="rounded-xl border border-gray-200 px-3 py-3 dark:border-white/10">
                      {t('preview_audit_meta_submitted', 'Processed: {value}').replace('{value}', String(selectedRecord.submitted_at || t('common_unknown', 'Unknown')))}
                    </div>
                    <div className="rounded-xl border border-gray-200 px-3 py-3 dark:border-white/10">
                      {t('preview_audit_meta_entries', 'Records: {value}').replace('{value}', String(selectedRecord.entry_count || 0))}
                    </div>
                    <div className="rounded-xl border border-gray-200 px-3 py-3 dark:border-white/10">
                      {t('preview_audit_meta_role', 'Recorded by role: {value}').replace('{value}', String(selectedRecord.submitter_role || t('common_unknown', 'Unknown')))}
                    </div>
                    <div className="rounded-xl border border-gray-200 px-3 py-3 dark:border-white/10 md:col-span-2">
                      {t('preview_audit_meta_device', 'Reviewed device context: {value}').replace(
                        '{value}',
                        [
                          selectedRecord?.device?.device_type,
                          selectedRecord?.device?.model,
                          selectedRecord?.device?.os_version,
                        ].filter(Boolean).join(' / ') || t('common_unknown', 'Unknown'),
                      )}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4 dark:border-emerald-900 dark:bg-emerald-950/10">
                    <div className="text-sm font-semibold text-emerald-900 dark:text-emerald-300">
                      {t('preview_audit_redactions_title', 'Masking results')}
                    </div>
                    {!redactionSummaryItems.length ? (
                      <div className="mt-2 text-sm text-emerald-800 dark:text-emerald-200">
                        {t('preview_no_redactions')}
                      </div>
                    ) : (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {redactionSummaryItems.map(([key, value]) => (
                          <span
                            key={key}
                            className="rounded-full border border-emerald-200 px-3 py-1 text-xs text-emerald-900 dark:border-emerald-900/50 dark:text-emerald-200"
                          >
                            {`${key}: ${value}`}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-gray-200 p-4 dark:border-white/10">
                    <div className="text-sm font-semibold text-gray-900 dark:text-white">
                      {t('preview_audit_notes_title', 'Review note')}
                    </div>
                    <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                      {selectedRecord.notes || t('preview_audit_no_notes', 'No review note was attached to this record.')}
                    </div>
                  </div>

                  <div className="space-y-4">
                    {(Array.isArray(selectedRecord.entries) ? selectedRecord.entries : []).map((entry, index) => (
                      <div key={`${entry.command}-${index}`} className="rounded-2xl border border-gray-200 overflow-hidden dark:border-white/10">
                        <div className="px-4 py-3 border-b border-gray-200 dark:border-white/10 flex items-center justify-between gap-3">
                          <div className="text-sm font-semibold text-gray-900 dark:text-white">{entry.command}</div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">
                            {Object.entries(entry.redaction_summary || {})
                              .filter(([, value]) => Number(value) > 0)
                              .map(([key, value]) => `${key}:${value}`)
                              .join(' / ') || t('preview_no_redactions')}
                          </div>
                        </div>
                        <pre className="max-h-80 overflow-auto bg-[#0b1220] p-4 text-xs leading-6 text-slate-100">
                          {entry.sanitized_output}
                        </pre>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </section>
        </div>
      </section>
    </div>
  );
};

export default PreviewContributionPage;
