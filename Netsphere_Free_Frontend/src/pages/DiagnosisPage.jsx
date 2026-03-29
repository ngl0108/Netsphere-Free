import React, { useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Info,
  Network,
  Play,
  RefreshCw,
  Route,
  ServerCrash,
  TerminalSquare,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { DiagnosisService } from '../api/services';
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';
import { InlineEmpty, SectionCard, SectionHeader } from '../components/common/PageState';
import { buildGrafanaFleetHealthUrl, buildObservabilityPath } from '../utils/observabilityLinks';

const JsonBlock = ({ value }) => {
  const text = useMemo(() => {
    try {
      return JSON.stringify(value ?? null, null, 2);
    } catch (e) {
      return String(value ?? '');
    }
  }, [value]);

  return (
    <pre className="text-xs whitespace-pre-wrap break-words bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl p-4 text-gray-800 dark:text-gray-200 max-h-[420px] overflow-auto">
      {text}
    </pre>
  );
};

const toneClass = (value) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'critical' || normalized === 'down' || normalized === 'failed') {
    return 'border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200';
  }
  if (normalized === 'warning' || normalized === 'degraded') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200';
  }
  if (normalized === 'healthy' || normalized === 'success' || normalized === 'reachable') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200';
  }
  return 'border-slate-200 bg-slate-50 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-100';
};

const formatConfidence = (value) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return '-';
  return `${Math.round(num * 100)}%`;
};

const formatMetric = (value) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return '-';
  return `${num.toFixed(1)}%`;
};

const formatCount = (value) => {
  const num = Number(value);
  return Number.isFinite(num) ? String(num) : '-';
};

const Badge = ({ value, label }) => (
  <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${toneClass(value)}`}>
    {label || String(value || '-')}
  </span>
);

const StatCard = ({ label, value, tone = '' }) => (
  <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
    <div className="text-[10px] uppercase tracking-widest text-gray-500 dark:text-gray-400 font-bold">{label}</div>
    <div className={`mt-1 text-sm font-black ${tone || 'text-gray-900 dark:text-white'}`}>{value}</div>
  </div>
);

const DiagnosisPage = () => {
  useLocaleRerender();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [srcIp, setSrcIp] = useState('');
  const [dstIp, setDstIp] = useState('');
  const [includeShow, setIncludeShow] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const canRun = String(srcIp).trim().length > 0 && String(dstIp).trim().length > 0 && !loading;
  const openDevice = (deviceId) => {
    if (!deviceId) return;
    navigate(`/devices/${deviceId}`);
  };
  const openObservability = (deviceId) => {
    if (!deviceId) return;
    navigate(buildObservabilityPath({ deviceId }));
  };
  const openGrafana = (deviceId) => {
    if (!deviceId) return;
    window.open(buildGrafanaFleetHealthUrl({ deviceId }), '_blank', 'noopener,noreferrer');
  };

  const run = async () => {
    if (!canRun) return;
    setLoading(true);
    try {
      const res = await DiagnosisService.oneClick(String(srcIp).trim(), String(dstIp).trim(), includeShow);
      setResult(res.data);
      showToast(t('diagnosis_completed', 'One-click diagnosis completed'), 'success');
    } catch (e) {
      const msg = e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t('diagnosis_failed', 'Diagnosis failed');
      showToast(String(msg), 'error');
    } finally {
      setLoading(false);
    }
  };

  const summary = result?.summary || {};
  const diagnosis = result?.diagnosis || null;
  const abnormal = Array.isArray(result?.abnormal) ? result.abnormal : [];
  const deviceHealth = Array.isArray(result?.device_health) ? result.device_health : [];
  const showBlocks = Array.isArray(result?.show) ? result.show : [];
  const pathSummary = result?.path_trace?.summary || {};
  const pathWarnings = Array.isArray(diagnosis?.warnings) ? diagnosis.warnings : [];

  return (
    <div className="h-full min-h-0 w-full bg-[#f4f5f9] dark:bg-[#0e1012] p-3 sm:p-4 md:p-6 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Activity className="text-indigo-500" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">{t('diagnosis_title')}</h1>
        </div>
        <button
          onClick={() => setResult(null)}
          className="h-10 inline-flex items-center gap-2 px-3 rounded-xl text-sm font-semibold bg-white dark:bg-surface/40 border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5"
        >
          <RefreshCw size={16} /> {t('common_reset', 'Reset')}
        </button>
      </div>

      <div data-testid="diagnosis-evidence-panel" className="mt-5 space-y-4">
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <SectionCard className="p-5">
          <SectionHeader
            title={t('diagnosis_inputs', 'Inputs')}
            subtitle={t('diagnosis_ready', 'Enter source and destination IPs to trace the fault domain.')}
          />

          <div className="mt-4 space-y-3">
            <div>
              <div className="text-xs font-semibold text-gray-700 dark:text-gray-200">{t('diagnosis_source_ip', 'Source IP')}</div>
              <input
                value={srcIp}
                onChange={(e) => setSrcIp(e.target.value)}
                placeholder={t('diagnosis_source_ip_placeholder', 'e.g. 10.0.0.10')}
                className="mt-1 w-full px-3 py-2 rounded-xl text-sm bg-white dark:bg-black/20 border border-gray-300 dark:border-white/10 text-gray-800 dark:text-gray-100 outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>
            <div>
              <div className="text-xs font-semibold text-gray-700 dark:text-gray-200">{t('diagnosis_destination_ip', 'Destination IP')}</div>
              <input
                value={dstIp}
                onChange={(e) => setDstIp(e.target.value)}
                placeholder={t('diagnosis_destination_ip_placeholder', 'e.g. 10.0.1.20')}
                className="mt-1 w-full px-3 py-2 rounded-xl text-sm bg-white dark:bg-black/20 border border-gray-300 dark:border-white/10 text-gray-800 dark:text-gray-100 outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>

            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
              <input
                type="checkbox"
                checked={includeShow}
                onChange={(e) => setIncludeShow(e.target.checked)}
                className="rounded border-gray-300 dark:border-white/10"
              />
              {t('diagnosis_collect_show', 'Collect show commands on abnormal hops')}
            </label>

            <button
              onClick={run}
              disabled={!canRun}
              className={`w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition-colors border ${
                canRun
                  ? 'bg-indigo-600 text-white border-indigo-600 hover:bg-indigo-700'
                  : 'bg-gray-200 dark:bg-white/10 text-gray-500 border-gray-200 dark:border-white/10 cursor-not-allowed'
              }`}
            >
              <Play size={16} />
              {loading ? t('diagnosis_running', 'Running...') : t('diagnosis_run', 'Run')}
            </button>
          </div>
          </SectionCard>

          <SectionCard className="p-5 xl:col-span-2" data-testid="diagnosis-verdict">
          <SectionHeader
            title={t('diagnosis_verdict', 'Diagnosis Verdict')}
            subtitle={result?.ts ? `${t('diagnosis_collected_at', 'Collected at')} ${String(result.ts)}` : ''}
            right={diagnosis ? <Badge value={diagnosis.severity} label={String(diagnosis.severity || '').toUpperCase() || '-'} /> : null}
          />

          {diagnosis ? (
            <>
              <div className="mt-4 flex items-start gap-3">
                {String(diagnosis.severity).toLowerCase() === 'critical' ? (
                  <ServerCrash className="mt-0.5 shrink-0 text-red-500" size={22} />
                ) : String(diagnosis.severity).toLowerCase() === 'warning' ? (
                  <AlertTriangle className="mt-0.5 shrink-0 text-amber-500" size={22} />
                ) : (
                  <CheckCircle2 className="mt-0.5 shrink-0 text-emerald-500" size={22} />
                )}
                <div className="min-w-0">
                  <div className="text-lg font-black text-gray-900 dark:text-white">{diagnosis.headline || '-'}</div>
                  <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{diagnosis.summary || t('diagnosis_no_result', 'Run diagnosis to view the verdict.')}</p>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <Badge value={diagnosis.severity} label={`${t('diagnosis_severity', 'Severity')}: ${String(diagnosis.severity || '-').toUpperCase()}`} />
                <Badge value={summary.path_health || diagnosis.path_health} label={`${t('diagnosis_path_health', 'Path Health')}: ${String(summary.path_health || diagnosis.path_health || '-')}`} />
                <Badge value="info" label={`${t('diagnosis_root_cause', 'Root Cause')}: ${String(diagnosis.verdict || '-')}`} />
                <Badge value="info" label={`${t('diagnosis_confidence', 'Confidence')}: ${formatConfidence(diagnosis.confidence)}`} />
              </div>

              <div className="mt-5">
                <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">{t('diagnosis_recommended_actions', 'Recommended Actions')}</div>
                <div className="mt-2 grid grid-cols-1 lg:grid-cols-2 gap-2">
                  {(Array.isArray(diagnosis.next_actions) ? diagnosis.next_actions : []).map((action) => (
                    <div key={String(action)} className="flex items-start gap-2 rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 px-3 py-2 text-sm text-gray-700 dark:text-gray-200">
                      <ChevronRight size={16} className="mt-0.5 shrink-0 text-indigo-500" />
                      <span>{String(action)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <InlineEmpty className="py-16" label={t('diagnosis_no_result', 'Run diagnosis to view the verdict.')} />
          )}

          <div className="mt-5 grid grid-cols-2 lg:grid-cols-6 gap-3">
            <StatCard label={t('diagnosis_mode', 'Mode')} value={summary.mode || '-'} />
            <StatCard label={t('devices_col_status', 'Status')} value={summary.status || '-'} />
            <StatCard label={t('diagnosis_path_health', 'Path Health')} value={summary.path_health || '-'} />
            <StatCard label={t('diagnosis_abnormal', 'Abnormal')} value={formatCount(summary.abnormal_count)} />
            <StatCard label={t('diagnosis_show', 'Show')} value={formatCount(summary.show_collected)} />
            <StatCard label={t('diagnosis_confidence', 'Confidence')} value={formatConfidence(summary.confidence)} />
          </div>
          </SectionCard>
        </div>

        <SectionCard className="p-5">
          <SectionHeader
            title={t('diagnosis_abnormal_hops', 'Abnormal Hops')}
            subtitle={t('diagnosis_abnormal_hints', 'Abnormal hints')}
            right={abnormal.length > 0 ? <Badge value={summary.severity} label={`${formatCount(abnormal.length)} ${t('diagnosis_abnormal', 'Abnormal')}`} /> : null}
          />
          {abnormal.length > 0 ? (
            <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
              {abnormal.map((item, idx) => (
                <SectionCard key={`${item.device_id}-${idx}`} className="p-4 border-dashed" data-testid={`diagnosis-abnormal-card-${item.device_id}-${idx}`}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="text-sm font-black text-gray-900 dark:text-white">{item.title || '-'}</div>
                    <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">{item.summary || '-'}</div>
                    <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      {t('diagnosis_device', 'Device')}: {item.device_name || item.device_ip || item.device_id}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <Badge value={item.severity} label={String(item.severity || '').toUpperCase() || '-'} />
                    {item.device_id ? (
                      <>
                        <button
                          onClick={() => openDevice(item.device_id)}
                          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-2.5 py-1.5 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                        >
                          <Route size={13} />
                          {t('obs_open_device', 'Open Device')}
                        </button>
                        <button
                          onClick={() => openObservability(item.device_id)}
                          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-2.5 py-1.5 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                        >
                          <BarChart3 size={13} />
                          {t('common_open_observability', 'Open Observability')}
                        </button>
                        <button
                          onClick={() => openGrafana(item.device_id)}
                          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-2.5 py-1.5 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                        >
                          <Activity size={13} />
                          {t('obs_grafana', 'Grafana')}
                        </button>
                      </>
                    ) : null}
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge value="info" label={`${t('diagnosis_root_cause', 'Root Cause')}: ${item.root_cause || '-'}`} />
                  <Badge value="info" label={`${t('diagnosis_confidence', 'Confidence')}: ${formatConfidence(item.confidence)}`} />
                  {item.segment?.protocol ? <Badge value="info" label={`${t('diagnosis_protocol', 'Protocol')}: ${item.segment.protocol}`} /> : null}
                  {item.segment?.layer ? <Badge value="info" label={`${t('diagnosis_layer', 'Layer')}: ${item.segment.layer}`} /> : null}
                  {item.segment?.status ? <Badge value={item.segment.status} label={`${t('devices_col_status', 'Status')}: ${item.segment.status}`} /> : null}
                  {item.segment?.hop !== undefined ? <Badge value="info" label={`${t('diagnosis_hop', 'Hop')}: ${String(item.segment.hop)}`} /> : null}
                </div>

                {(item.segment?.from_port || item.segment?.peer_name) ? (
                  <div className="mt-3 rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 px-3 py-2 text-sm text-gray-700 dark:text-gray-200">
                    {item.segment?.from_port ? `${item.segment.from_port}` : '-'}
                    {item.segment?.to_port ? ` -> ${item.segment.to_port}` : ''}
                    {item.segment?.peer_name ? ` (${t('diagnosis_peer', 'Peer')}: ${item.segment.peer_name})` : ''}
                  </div>
                ) : null}

                <div className="mt-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">{t('diagnosis_evidence', 'Evidence')}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(Array.isArray(item.evidence) ? item.evidence : []).map((evidence) => (
                      <Badge key={`${item.device_id}-${evidence.kind}-${evidence.label}`} value={evidence.status} label={`${evidence.label}: ${evidence.value}`} />
                    ))}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">{t('diagnosis_recommended_actions', 'Recommended Actions')}</div>
                  <div className="mt-2 space-y-2">
                    {(Array.isArray(item.next_actions) ? item.next_actions : []).map((action) => (
                      <div key={`${item.device_id}-${action}`} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
                        <ChevronRight size={16} className="mt-0.5 shrink-0 text-indigo-500" />
                        <span>{String(action)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                </SectionCard>
              ))}
            </div>
          ) : (
            <InlineEmpty className="py-12" label={t('diagnosis_no_abnormal_hops', 'No abnormal hops were detected.')} />
          )}
        </SectionCard>
      </div>

      <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-4">
        <SectionCard className="p-5 xl:col-span-2">
          <SectionHeader title={t('diagnosis_device_cards', 'Device Health')} subtitle={t('diagnosis_device_health', 'Device Health')} />
          {deviceHealth.length > 0 ? (
            <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
              {deviceHealth.map((device) => (
                <SectionCard key={String(device.device_id)} className="p-4 border-dashed" data-testid={`diagnosis-device-card-${device.device_id}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-black text-gray-900 dark:text-white">{device.name || device.ip_address || device.device_id}</div>
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{device.ip_address || '-'}</div>
                    </div>
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      <Badge value={device.risk_level} label={String(device.risk_level || '-').toUpperCase() || '-'} />
                      {device.device_id ? (
                        <>
                          <button
                            onClick={() => openDevice(device.device_id)}
                            className="inline-flex items-center gap-1 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-2.5 py-1.5 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                          >
                            <Route size={13} />
                            {t('obs_open_device', 'Open Device')}
                          </button>
                          <button
                            onClick={() => openObservability(device.device_id)}
                            className="inline-flex items-center gap-1 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-2.5 py-1.5 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                          >
                            <BarChart3 size={13} />
                            {t('common_open_observability', 'Open Observability')}
                          </button>
                          <button
                            onClick={() => openGrafana(device.device_id)}
                            className="inline-flex items-center gap-1 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-2.5 py-1.5 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                          >
                            <Activity size={13} />
                            {t('obs_grafana', 'Grafana')}
                          </button>
                        </>
                      ) : null}
                    </div>
                  </div>

                  <div className="mt-3 grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <StatCard label={t('diagnosis_ping', 'Ping')} value={device.ping_ok ? 'reachable' : 'failed'} tone={device.ping_ok ? 'text-emerald-700 dark:text-emerald-200' : 'text-red-700 dark:text-red-200'} />
                    <StatCard label={t('diagnosis_score', 'Score')} value={formatCount(device.health_score)} />
                    <StatCard label={t('diagnosis_cpu', 'CPU')} value={formatMetric(device.cpu_usage)} />
                    <StatCard label={t('diagnosis_memory', 'Memory')} value={formatMetric(device.memory_usage)} />
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <Badge value="info" label={`${t('diagnosis_recent_issues', 'Recent Issues')}: C${formatCount(device.critical_issues)} / W${formatCount(device.warning_issues)}`} />
                    <Badge value="info" label={`${t('diagnosis_primary_signal', 'Primary Signal')}: ${device.primary_signal || '-'}`} />
                  </div>

                  {(Array.isArray(device.notes) ? device.notes : []).length > 0 ? (
                    <div className="mt-4">
                      <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">{t('diagnosis_notes', 'Notes')}</div>
                      <div className="mt-2 space-y-2">
                        {device.notes.map((note) => (
                          <div key={`${device.device_id}-${note}`} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
                            <Info size={16} className="mt-0.5 shrink-0 text-slate-500" />
                            <span>{String(note)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {(Array.isArray(device.recent_issues) ? device.recent_issues : []).length > 0 ? (
                    <div className="mt-4">
                      <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">{t('diagnosis_recent_issues', 'Recent Issues')}</div>
                      <div className="mt-2 space-y-2">
                        {device.recent_issues.slice(0, 3).map((issue) => (
                          <div key={`${device.device_id}-${issue.id}`} className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 px-3 py-2 text-sm text-gray-700 dark:text-gray-200">
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-semibold">{issue.title || '-'}</span>
                              <Badge value={issue.severity} label={String(issue.severity || '').toUpperCase() || '-'} />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </SectionCard>
              ))}
            </div>
          ) : (
            <InlineEmpty className="py-12" label={t('diagnosis_no_result', 'Run diagnosis to view the verdict.')} />
          )}
        </SectionCard>

        <SectionCard className="p-5">
          <SectionHeader
            title={t('diagnosis_path_context', 'Path Context')}
            subtitle={t('diagnosis_path_trace', 'Path Trace')}
            right={<Network size={16} className="text-slate-500" />}
          />
          <div className="mt-4 grid grid-cols-2 gap-3">
            <StatCard label={t('diagnosis_path_health', 'Path Health')} value={summary.path_health || pathSummary.health || '-'} />
            <StatCard label={t('diagnosis_mode', 'Mode')} value={summary.mode || pathSummary.mode || '-'} />
            <StatCard label={t('diagnosis_protocol', 'Protocol')} value={Array.isArray(pathSummary.protocols) && pathSummary.protocols.length > 0 ? pathSummary.protocols.join(', ') : '-'} />
            <StatCard label={t('diagnosis_layer', 'Layer')} value={Array.isArray(pathSummary.layers) && pathSummary.layers.length > 0 ? pathSummary.layers.join(', ') : '-'} />
          </div>

          {pathWarnings.length > 0 ? (
            <div className="mt-4">
              <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">{t('diagnosis_path_warnings', 'Path Warnings')}</div>
              <div data-testid="diagnosis-path-warning-list" className="mt-2 space-y-2">
                {pathWarnings.map((warning) => (
                  <div key={String(warning)} className="flex items-start gap-2 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-3 py-2 text-sm text-amber-900 dark:text-amber-200">
                    <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                    <span>{String(warning)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <details className="mt-4 rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
            <summary className="cursor-pointer text-sm font-bold text-gray-800 dark:text-gray-100">{t('diagnosis_raw_payload', 'Raw Payload')}</summary>
            <div className="mt-3">
              <JsonBlock value={result?.path_trace || null} />
            </div>
          </details>
        </SectionCard>
      </div>

      <SectionCard className="mt-4 p-5">
        <SectionHeader title={t('diagnosis_show_outputs', 'Show Outputs')} subtitle={t('diagnosis_show_plan', 'Show Plan')} right={<TerminalSquare size={16} className="text-slate-500" />} />
        {showBlocks.length > 0 ? (
          <div className="mt-4 space-y-4">
            {showBlocks.map((block) => (
              <SectionCard key={String(block.device_id)} className="p-4 border-dashed" data-testid={`diagnosis-show-device-${block.device_id}`}>
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Route size={16} className="text-indigo-500" />
                      <div className="text-sm font-black text-gray-900 dark:text-white">{block.device_name || block.device_ip || block.device_id}</div>
                    </div>
                    <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{block.device_ip || '-'}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(Array.isArray(block.reasons) ? block.reasons : []).map((reason) => (
                      <Badge key={`${block.device_id}-${reason}`} value="info" label={String(reason)} />
                    ))}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-widest text-gray-500 dark:text-gray-400">{t('diagnosis_show_plan', 'Show Plan')}</div>
                  <div className="mt-2 grid grid-cols-1 xl:grid-cols-2 gap-3">
                    {(Array.isArray(block.plan) ? block.plan : []).map((item, idx) => (
                      <div key={`${block.device_id}-${item.command}-${idx}`} className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 px-3 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge value={item.priority} label={String(item.priority || '-').toUpperCase() || '-'} />
                          <Badge value="info" label={String(item.area || '-')} />
                        </div>
                        <div className="mt-2 font-mono text-xs text-gray-900 dark:text-white break-all">{item.command || '-'}</div>
                        <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">{item.purpose || '-'}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <details className="mt-4 rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
                  <summary className="cursor-pointer text-sm font-bold text-gray-800 dark:text-gray-100">{t('diagnosis_command_results', 'Command Results')}</summary>
                  <div className="mt-3 space-y-3">
                    {(Array.isArray(block.results) ? block.results : []).map((item, idx) => (
                      <div key={`${block.device_id}-${item.command || 'error'}-${idx}`} className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-black/20 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          {item.command ? <div className="font-mono text-xs text-gray-900 dark:text-white break-all">{item.command}</div> : null}
                          <Badge value={item.priority} label={String(item.priority || '-').toUpperCase() || '-'} />
                          <Badge value="info" label={String(item.area || '-')} />
                        </div>
                        <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">{item.purpose || '-'}</div>
                        <div className="mt-3">
                          <JsonBlock value={item.output || '-'} />
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              </SectionCard>
            ))}
          </div>
        ) : (
          <InlineEmpty className="py-12" label={t('diagnosis_no_show_outputs', 'No show outputs were collected.')} />
        )}
      </SectionCard>
    </div>
  );
};

export default DiagnosisPage;
