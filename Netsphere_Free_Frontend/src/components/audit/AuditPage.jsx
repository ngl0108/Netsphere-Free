import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PreviewService, SDNService } from '../../api/services';
import { Shield, RefreshCw } from 'lucide-react';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import { InlineEmpty, InlineLoading, SectionCard } from '../common/PageState';
import { useAuth } from '../../context/AuthContext';
import PreviewContributionPage from '../../pages/PreviewContributionPage';

const StandardAuditLogs = ({ user }) => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState('all');

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await SDNService.getAuditLogs({ action: actionFilter });
      setLogs(Array.isArray(res?.data) ? res.data : []);
    } catch (err) {
      console.error('Failed to fetch logs', err);
    } finally {
      setLoading(false);
    }
  }, [actionFilter]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const parseDetailPayload = (details) => {
    if (details && typeof details === 'object') return details;
    const text = String(details || '').trim();
    if (!text || !(text.startsWith('{') || text.startsWith('['))) return null;
    try {
      const parsed = JSON.parse(text);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (_e) {
      return null;
    }
  };

  const formatDetails = (log) => {
    const raw = log?.details;
    if (!raw) return '-';
    const payload = parseDetailPayload(raw);
    if (!payload || Array.isArray(payload)) return String(raw);

    if (String(payload.event || '').trim().toLowerCase() === 'cloud_bootstrap_path_update') {
      const provider = String(payload.provider || '').trim().toUpperCase() || '-';
      const accountId = String(payload.account_id || '-');
      const name = String(payload.name || '-');
      const before = String(payload.bootstrap_path_before || 'auto');
      const after = String(payload.bootstrap_path_after || 'auto');
      return t(
        'audit_cloud_bootstrap_path_update_fmt',
        'Cloud bootstrap path updated ({provider} #{accountId} {name}): {before} -> {after}',
      )
        .replace('{provider}', provider)
        .replace('{accountId}', accountId)
        .replace('{name}', name)
        .replace('{before}', before)
        .replace('{after}', after);
    }
    return String(raw);
  };

  const getActionBadge = (action) => {
    const colors = {
      CREATE: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
      UPDATE: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
      DELETE: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
      DEPLOY: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
      LOGIN: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
    };
    return (
      <span className={`px-2 py-0.5 rounded textxs font-bold ${colors[action] || 'bg-gray-100 text-gray-600'}`}>
        {action}
      </span>
    );
  };

  const summary = useMemo(() => {
    const counts = {
      total: Array.isArray(logs) ? logs.length : 0,
      deploy: 0,
      destructive: 0,
      latestTimestamp: null,
    };

    for (const log of Array.isArray(logs) ? logs : []) {
      const action = String(log?.action || '').trim().toUpperCase();
      if (action === 'DEPLOY') counts.deploy += 1;
      if (action === 'DELETE') counts.destructive += 1;
      const timestamp = Date.parse(log?.timestamp || '');
      if (!Number.isNaN(timestamp) && (counts.latestTimestamp === null || timestamp > counts.latestTimestamp)) {
        counts.latestTimestamp = timestamp;
      }
    }
    return counts;
  }, [logs]);

  const roleKey = String(user?.role || 'viewer').toLowerCase();
  const roleLabel = t(`role_${roleKey}`, roleKey || t('common_unknown', 'Unknown'));
  const roleAuditCopy =
    roleKey === 'admin'
      ? t(
          'audit_access_desc_admin',
          'Administrators own privileged change review, sign-in verification, and the evidence trail for deployments and destructive actions.',
        )
      : roleKey === 'operator'
        ? t(
            'audit_access_desc_operator',
            'Operators can review execution history, approval evidence, and recent high-risk changes, while administrative policy ownership stays with administrators.',
          )
        : t(
            'audit_access_desc_viewer',
            'Viewers can inspect audit evidence and recent activity, but policy changes, approvals, and administrative ownership remain read-only.',
          );

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-[#f4f5f9] dark:bg-[#0e1012] h-full min-h-0 flex flex-col animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Shield className="text-indigo-500" /> {t('audit_title', 'Audit Logs')}
          </h1>
          <p className="text-sm text-gray-500">
            {t('audit_desc', 'Track and monitor all system activities and changes.')}
          </p>
        </div>
        <button
          onClick={fetchLogs}
          title={t('common_refresh', 'Refresh')}
          className="h-10 w-10 inline-flex items-center justify-center bg-white dark:bg-[#1e293b] border border-gray-200 dark:border-gray-700 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
        >
          <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-[1.15fr_0.85fr] mb-4">
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50/80 dark:border-indigo-900/50 dark:bg-indigo-950/10 px-4 py-4">
          <div className="text-sm font-semibold text-indigo-900 dark:text-indigo-300">
            {t('audit_access_title', 'Audit access boundary')}
          </div>
          <p className="mt-2 text-sm leading-6 text-indigo-800 dark:text-indigo-200">
            {roleAuditCopy}
          </p>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-indigo-700 dark:text-indigo-300">
            <span>
              {t('audit_access_role_fmt', 'Current role: {role}').replace('{role}', roleLabel)}
            </span>
            <span>
              {t(
                'audit_access_review_hint',
                'Review deploy and delete actions first when you need the shortest high-risk trail.',
              )}
            </span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-white/5 px-4 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
              {t('audit_summary_total', 'Visible records')}
            </div>
            <div className="mt-2 text-2xl font-black text-gray-900 dark:text-white">{summary.total}</div>
          </div>
          <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/80 dark:bg-white/5 px-4 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
              {t('audit_summary_latest', 'Latest activity')}
            </div>
            <div className="mt-2 text-sm font-semibold text-gray-900 dark:text-white">
              {summary.latestTimestamp ? new Date(summary.latestTimestamp).toLocaleString() : t('audit_empty', 'No audit records found.')}
            </div>
          </div>
          <div className="rounded-2xl border border-purple-200 dark:border-purple-900/40 bg-purple-50 dark:bg-purple-900/10 px-4 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-purple-700 dark:text-purple-300">
              {t('audit_summary_deploy', 'Deploy actions')}
            </div>
            <div className="mt-2 text-2xl font-black text-purple-700 dark:text-purple-300">{summary.deploy}</div>
          </div>
          <div className="rounded-2xl border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-900/10 px-4 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-rose-700 dark:text-rose-300">
              {t('audit_summary_destructive', 'Delete actions')}
            </div>
            <div className="mt-2 text-2xl font-black text-rose-700 dark:text-rose-300">{summary.destructive}</div>
          </div>
        </div>
      </div>

      <div className="flex gap-2 mb-4 overflow-x-auto pb-2">
        {['all', 'CREATE', 'UPDATE', 'DELETE', 'DEPLOY', 'LOGIN'].map((act) => (
          <button
            key={act}
            onClick={() => setActionFilter(act)}
            className={`px-3 py-1.5 text-sm rounded-full transition-colors whitespace-nowrap ${
              actionFilter === act
                ? 'bg-indigo-600 text-white'
                : 'bg-white dark:bg-[#1f2225] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700'
            }`}
          >
            {act === 'all' ? t('audit_all_activities', 'All Activities') : act}
          </button>
        ))}
      </div>

      <SectionCard className="overflow-hidden flex-1 flex flex-col">
        <div className="overflow-x-auto overflow-y-auto custom-scrollbar flex-1">
          <table className="w-full text-left border-collapse">
            <thead className="bg-gray-50 dark:bg-[#25282c] sticky top-0 z-10">
              <tr>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">
                  {t('audit_col_timestamp', 'Timestamp')}
                </th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">
                  {t('audit_col_user', 'User')}
                </th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">
                  {t('audit_col_action', 'Action')}
                </th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">
                  {t('audit_col_resource', 'Resource')}
                </th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">
                  {t('audit_col_details', 'Details')}
                </th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">
                  {t('audit_col_ip', 'IP Addr')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {loading && (
                <tr>
                  <td colSpan={6} className="px-6 py-10">
                    <InlineLoading label={t('common_loading', 'Loading...')} />
                  </td>
                </tr>
              )}
              {logs.map((log) => {
                const renderedDetails = formatDetails(log);
                return (
                  <tr key={log.id} className="hover:bg-gray-50 dark:hover:bg-[#25282c] transition-colors">
                    <td className="px-6 py-4 text-sm text-gray-500 whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center text-xs font-bold text-indigo-600 dark:text-indigo-400">
                          {log.username?.charAt(0).toUpperCase() || '?'}
                        </div>
                        <span className="text-sm font-medium text-gray-900 dark:text-white">{log.username}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">{getActionBadge(log.action)}</td>
                    <td className="px-6 py-4">
                      <div className="text-sm text-gray-900 dark:text-white font-medium">{log.resource_type}</div>
                      <div className="text-xs text-gray-500">{log.resource_name}</div>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-300 max-w-[32rem] truncate" title={renderedDetails}>
                      {renderedDetails}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">{log.ip_address || '-'}</td>
                  </tr>
                );
              })}
              {!loading && logs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-12">
                    <InlineEmpty label={t('audit_empty', 'No audit records found.')} />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
};

const AuditPage = () => {
  const { user } = useAuth();
  const [previewLoading, setPreviewLoading] = useState(true);
  const [previewEnabled, setPreviewEnabled] = useState(false);

  useLocaleRerender();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await PreviewService.getPolicy();
        if (!cancelled) {
          setPreviewEnabled(res?.data?.preview_enabled === true);
        }
      } catch (_error) {
        if (!cancelled) {
          setPreviewEnabled(false);
        }
      } finally {
        if (!cancelled) {
          setPreviewLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (previewLoading) {
    return <div className="p-6 text-sm text-gray-500 dark:text-gray-300">{t('common_loading', 'Loading...')}</div>;
  }

  if (previewEnabled) {
    return <PreviewContributionPage />;
  }

  return <StandardAuditLogs user={user} />;
};

export default AuditPage;
