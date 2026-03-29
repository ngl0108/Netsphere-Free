import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ComplianceService, DeviceService, JobService } from '../../api/services';
import { useToast } from '../../context/ToastContext';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import { InlineEmpty } from '../common/PageState';
import {
    buildDevicePath,
    buildGrafanaAlertingCenterUrl,
    buildGrafanaFleetHealthUrl,
    buildObservabilityPath,
    buildTopologyPath,
} from '../../utils/observabilityLinks';
import {
    Shield, CheckCircle, XCircle, AlertTriangle, Plus, Trash2,
    Search, RefreshCw, ChevronDown, ChevronRight, FileText, Play, Activity, GitBranch, ExternalLink
} from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import DriftView from './DriftView'; // [NEW] Import

const parseFilename = (contentDisposition) => {
    const v = contentDisposition || '';
    const m = v.match(/filename="?([^"]+)"?/i);
    return m ? m[1] : null;
};

const downloadBlob = (data, filename, contentType) => {
    const blob = data instanceof Blob ? data : new Blob([data], { type: contentType || 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'download';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
};

const collectLegacyViolations = (standards) => {
    const rows = [];
    Object.entries(standards || {}).forEach(([standardName, raw]) => {
        if (!raw || typeof raw !== 'object' || !Array.isArray(raw.violations)) return;
        raw.violations.forEach((item) => {
            if (!item || typeof item !== 'object') return;
            rows.push({ standard: standardName, ...item });
        });
    });
    return rows;
};

const parseReportDetails = (report) => {
    const raw = report?.details;
    let parsed = {};
    if (raw && typeof raw === 'object') {
        parsed = raw;
    } else if (typeof raw === 'string' && raw.trim()) {
        try {
            parsed = JSON.parse(raw);
        } catch (err) {
            parsed = {};
        }
    }

    const standards = parsed?.standards && typeof parsed.standards === 'object'
        ? parsed.standards
        : (parsed && typeof parsed === 'object' ? Object.fromEntries(
            Object.entries(parsed).filter(([key, value]) => (
                !['summary', 'automation', 'violations'].includes(String(key))
                && value
                && typeof value === 'object'
                && !Array.isArray(value)
            ))
        ) : {});

    const violations = Array.isArray(report?.violations)
        ? report.violations
        : (Array.isArray(parsed?.violations) ? parsed.violations : collectLegacyViolations(standards));

    const summary = report?.summary && typeof report.summary === 'object'
        ? report.summary
        : (parsed?.summary && typeof parsed.summary === 'object' ? parsed.summary : {});

    const automation = report?.automation && typeof report.automation === 'object'
        ? report.automation
        : (parsed?.automation && typeof parsed.automation === 'object' ? parsed.automation : {});

    return {
        standards,
        violations,
        summary,
        automation,
    };
};

const automationToneClass = (status) => {
    switch (String(status || '').trim().toLowerCase()) {
        case 'auto_ready':
            return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300';
        case 'approval_required':
        case 'partial_auto_approval':
            return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300';
        case 'partial_auto':
        case 'manual_guided':
            return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300';
        case 'blocked':
            return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300';
        default:
            return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
    }
};

const automationStatusLabel = (status) => {
    switch (String(status || '').trim().toLowerCase()) {
        case 'auto_ready':
            return 'Automation Ready';
        case 'approval_required':
            return 'Approval Required';
        case 'partial_auto':
            return 'Partial Automation';
        case 'partial_auto_approval':
            return 'Partial Auto + Approval';
        case 'manual_guided':
            return 'Guided Manual Fix';
        case 'missing_golden':
            return 'Golden Needed';
        case 'baseline_review':
            return 'Review Baseline';
        case 'blocked':
            return 'Automation Blocked';
        case 'healthy':
            return 'Healthy';
        default:
            return 'Review Required';
    }
};

const canOpenDrift = (automation) => {
    if (Array.isArray(automation?.actions)) {
        return automation.actions.some((action) => action?.code === 'open_drift' && action?.available);
    }
    return Boolean(automation?.drift?.has_golden);
};

const CompliancePage = () => {
    useLocaleRerender();
    const { toast } = useToast();
    const [activeTab, setActiveTab] = useState('dashboard');
    // ... (skip lines) ...

    const [loading, setLoading] = useState(false);
    const [standards, setStandards] = useState([]);
    const [reports, setReports] = useState([]);
    const [devices, setDevices] = useState([]);
    const [exportingReports, setExportingReports] = useState(false);
    const [reportDeviceId, setReportDeviceId] = useState('');
    const [driftKpi, setDriftKpi] = useState(null);
    const [driftKpiDays, setDriftKpiDays] = useState(30);
    const [driftKpiLoading, setDriftKpiLoading] = useState(false);

    // Modal States
    const [showStdModal, setShowStdModal] = useState(false);
    const [showRuleModal, setShowRuleModal] = useState(false);
    const [selectedStdId, setSelectedStdId] = useState(null);
    const [selectedReport, setSelectedReport] = useState(null);
    const [driftFocusDeviceId, setDriftFocusDeviceId] = useState(null);

    // Data Fetching
    const loadData = async () => {
        setLoading(true);
        try {
            const [stdRes, reportRes, devRes] = await Promise.all([
                ComplianceService.getStandards(),
                ComplianceService.getReports(),
                DeviceService.getAll()
            ]);
            setStandards(stdRes.data || []);
            setReports(reportRes.data || []);
            setDevices(devRes.data || []);
        } catch (err) {
            console.error("Failed to load compliance data", err);
        } finally {
            setLoading(false);
        }
    };

    const loadDriftKpi = async () => {
        setDriftKpiLoading(true);
        try {
            const res = await ComplianceService.getDriftKpiSummary({ days: Number(driftKpiDays) || 30 });
            setDriftKpi(res.data || null);
        } catch (err) {
            console.error("Failed to load drift KPI", err);
            setDriftKpi(null);
        } finally {
            setDriftKpiLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    useEffect(() => {
        loadDriftKpi();
    }, [driftKpiDays]);

    // --- Actions ---

    const handleCreateStandard = async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const payload = {
            name: formData.get('name'),
            description: formData.get('description'),
            device_family: formData.get('device_family')
        };
        try {
            await ComplianceService.createStandard(payload);
            setShowStdModal(false);
            loadData();
        } catch (err) {
            toast.error(t('compliance_create_standard_failed', 'Failed to create standard'));
        }
    };

    const handleAddRule = async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const payload = {
            name: formData.get('name'),
            description: formData.get('description'),
            severity: formData.get('severity'),
            check_type: formData.get('check_type'),
            pattern: formData.get('pattern'),
            remediation: formData.get('remediation')
        };
        try {
            await ComplianceService.addRule(selectedStdId, payload);
            setShowRuleModal(false);
            loadData(); // Refresh to see new rule
        } catch (err) {
            toast.error(t('compliance_add_rule_failed', 'Failed to add rule'));
        }
    };

    const handleDeleteStandard = async (id) => {
        if (!window.confirm(t('compliance_delete_standard_confirm', 'Delete this standard and all its rules?'))) return;
        try {
            await ComplianceService.deleteStandard(id);
            loadData();
        } catch (err) { toast.error(t('compliance_delete_standard_failed', 'Failed to delete standard')); }
    };

    const handleDeleteRule = async (id) => {
        if (!window.confirm(t('compliance_delete_rule_confirm', 'Delete this rule?'))) return;
        try {
            await ComplianceService.deleteRule(id);
            loadData();
        } catch (err) { toast.error(t('compliance_delete_rule_failed', 'Failed to delete rule')); }
    };

    const handleScan = async () => {
        const targetIds = devices.map(d => d.id); // Scan all for simplicity, or add selection logic
        if (targetIds.length === 0) return toast.warning(t('compliance_no_devices_to_scan', 'No devices to scan'));

        setLoading(true);
        try {
            const res = await ComplianceService.runScan({ device_ids: targetIds });
            const jobId = res?.data?.job_id;
            if (!jobId) {
                toast.success(t('compliance_scan_completed', 'Scan completed successfully'));
                loadData();
                return;
            }
            toast.success(`${t('compliance_scan_queued', 'Scan queued')} (job: ${jobId})`);
            const start = Date.now();
            while (Date.now() - start < 120000) {
                const s = await JobService.getStatus(jobId);
                if (s?.data?.ready) {
                    if (s?.data?.successful) {
                        toast.success(t('compliance_scan_finished', 'Scan finished'));
                    } else {
                        toast.error(t('compliance_scan_failed', 'Scan failed'));
                    }
                    break;
                }
                await new Promise(r => setTimeout(r, 1000));
            }
            loadData();
            loadDriftKpi();
        } catch (err) {
            toast.error(`${t('compliance_scan_failed', 'Scan failed')}: ${err.message}`);
        } finally {
            setLoading(false);
        }
    };

    const handleExportReports = async (format) => {
        setExportingReports(true);
        try {
            const params = reportDeviceId ? { format, device_id: reportDeviceId } : { format };
            const res = await ComplianceService.exportReports(params);
            const suffix = reportDeviceId ? `_device_${reportDeviceId}` : '';
            const filename = parseFilename(res.headers?.['content-disposition']) || `compliance_reports${suffix}.${format}`;
            const contentType = res.headers?.['content-type'];
            downloadBlob(res.data, filename, contentType);
            toast.success(t('compliance_download_started', 'Download started.'));
        } catch (err) {
            toast.error(`${t('compliance_export_failed', 'Export failed')}: ${err.response?.data?.detail || err.message}`);
        } finally {
            setExportingReports(false);
        }
    };

    const openReportDetails = (report) => {
        setSelectedReport(report || null);
    };

    const closeReportDetails = () => {
        setSelectedReport(null);
    };

    const openDriftFromReport = (report) => {
        const deviceId = report?.device_id;
        if (!deviceId) return;
        setDriftFocusDeviceId(deviceId);
        setSelectedReport(null);
        setActiveTab('drift');
    };

    // --- Components ---

    const DashboardView = () => {
        const totalReports = reports.length;
        const compliant = reports.filter(r => r.status === 'compliant').length;
        const violations = totalReports - compliant;
        const score = totalReports > 0 ? Math.round((compliant / totalReports) * 100) : 100;

        const pieData = [
            { name: t('compliance_compliant', 'Compliant'), value: compliant, color: '#10b981' },
            { name: t('compliance_violation', 'Violation'), value: violations, color: '#ef4444' }
        ];
        const driftKpiObj = driftKpi?.kpi || {};
        const driftTotals = driftKpi?.totals || {};
        const driftTargets = driftKpiObj.targets || {};
        const minSuccessTarget = Number(driftTargets.min_success_rate_pct ?? 98);
        const maxFailureTarget = Number(driftTargets.max_failure_rate_pct ?? 1);
        const maxRollbackP95Target = Number(driftTargets.max_rollback_p95_ms ?? 180000);
        const minTraceTarget = Number(driftTargets.min_trace_coverage_pct ?? 100);
        const rollbackP95 = driftKpiObj.rollback_p95_ms;
        const traceCoverage = Number(driftKpiObj.approval_execution_trace_coverage_pct || 0);
        const traceContextEvents = Number(driftTotals.approval_context_events || 0);
        const traceLinkedEvents = Number(driftTotals.approval_traced || 0);
        const changeSuccessFallback = Number(driftTotals.events || 0) > 0
            ? (Number(driftTotals.success || 0) / Number(driftTotals.events || 1)) * 100
            : 100;
        const changeFailureFallback = Number(driftTotals.events || 0) > 0
            ? (Number(driftTotals.failed || 0) / Number(driftTotals.events || 1)) * 100
            : 0;
        const changeSuccessRate = Number(driftKpiObj.change_success_rate_pct ?? changeSuccessFallback);
        const changeFailureRate = Number(driftKpiObj.change_failure_rate_pct ?? changeFailureFallback);
        const topFailureCauses = Array.isArray(driftKpi?.failure_causes) ? driftKpi.failure_causes.slice(0, 5) : [];
        const formatDuration = (ms) => {
            if (ms === null || ms === undefined) return '-';
            const val = Number(ms || 0);
            if (val >= 1000) return `${(val / 1000).toFixed(2)}s`;
            return `${val}ms`;
        };

        return (
            <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm">
                        <h3 className="text-gray-500 font-medium text-sm uppercase">{t('compliance_overall', 'Overall Compliance')}</h3>
                        <div className="mt-2 text-4xl font-bold text-gray-900 dark:text-white">{score}%</div>
                        <p className="text-xs text-green-500 mt-1">{`${t('compliance_based_on', 'Based on')} ${totalReports} ${t('compliance_devices', 'devices')}`}</p>
                    </div>
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm">
                        <h3 className="text-gray-500 font-medium text-sm uppercase">{t('compliance_compliant_devices', 'Compliant Devices')}</h3>
                        <div className="mt-2 text-4xl font-bold text-green-500">{compliant}</div>
                    </div>
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm">
                        <h3 className="text-gray-500 font-medium text-sm uppercase">{t('compliance_devices_with_violations', 'Devices with Violations')}</h3>
                        <div className="mt-2 text-4xl font-bold text-red-500">{violations}</div>
                    </div>
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm flex items-center justify-center">
                        {/* Scan Button */}
                        <button onClick={handleScan} disabled={loading} className="w-full h-full flex flex-col items-center justify-center gap-2 text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-xl transition-all">
                            <Play size={32} />
                            <span className="font-bold">{t('compliance_run_full_scan', 'Run Full Scan')}</span>
                        </button>
                    </div>
                </div>

                <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm">
                    <div className="flex items-center justify-between mb-4">
                        <div>
                            <h3 className="font-bold text-gray-900 dark:text-white">{t('compliance_drift_kpi', 'Drift Remediation KPI')}</h3>
                            <p className="text-xs text-gray-500 mt-1">{t('compliance_drift_kpi_desc', 'Post-check failure auto rollback and approval-trace quality')}</p>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                                <button
                                    onClick={() => setDriftKpiDays(7)}
                                    className={`px-3 py-1.5 text-xs font-bold ${Number(driftKpiDays) === 7 ? 'bg-blue-600 text-white' : 'bg-white dark:bg-[#1b1d1f] text-gray-600 dark:text-gray-300'}`}
                                >
                                    7d
                                </button>
                                <button
                                    onClick={() => setDriftKpiDays(30)}
                                    className={`px-3 py-1.5 text-xs font-bold border-l border-gray-200 dark:border-gray-700 ${Number(driftKpiDays) === 30 ? 'bg-blue-600 text-white' : 'bg-white dark:bg-[#1b1d1f] text-gray-600 dark:text-gray-300'}`}
                                >
                                    30d
                                </button>
                            </div>
                            <button
                                onClick={loadDriftKpi}
                                disabled={driftKpiLoading}
                                className="px-3 py-1.5 text-xs font-bold rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#1b1d1f] text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50"
                            >
                                {driftKpiLoading ? t('common_loading', 'Loading...') : t('common_refresh', 'Refresh')}
                            </button>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                        <div className="p-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-black/20">
                            <div className="text-xs uppercase font-bold text-gray-500">{t('dashboard_rollback_p95', 'Rollback P95')}</div>
                            <div className={`mt-2 text-2xl font-bold ${rollbackP95 !== null && Number(rollbackP95) <= maxRollbackP95Target ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'}`}>{formatDuration(rollbackP95)}</div>
                            <div className="mt-1 text-xs text-gray-500">{t('compliance_target', 'Target')}: &lt;= {formatDuration(maxRollbackP95Target)}</div>
                        </div>
                        <div className="p-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-black/20">
                            <div className="text-xs uppercase font-bold text-gray-500">{t('dashboard_trace_coverage', 'Trace Coverage')}</div>
                            <div className={`mt-2 text-2xl font-bold ${traceCoverage >= minTraceTarget ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'}`}>
                                {traceCoverage.toFixed(2)}%
                            </div>
                            <div className="mt-1 text-xs text-gray-500">
                                approval_id -&gt; execution_id {traceLinkedEvents} / {traceContextEvents}
                            </div>
                        </div>
                        <div className="p-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-black/20">
                            <div className="text-xs uppercase font-bold text-gray-500">{t('compliance_change_success_rate', 'Change Success Rate')}</div>
                            <div className={`mt-2 text-2xl font-bold ${changeSuccessRate >= minSuccessTarget ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'}`}>
                                {changeSuccessRate.toFixed(2)}%
                            </div>
                            <div className="mt-1 text-xs text-gray-500">
                                {t('compliance_failure', 'failure')} {changeFailureRate.toFixed(2)}% ({t('compliance_target', 'target')} &lt;= {maxFailureTarget}%)
                            </div>
                        </div>
                    </div>

                    <div className="p-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#25282c]">
                        <div className="text-xs uppercase font-bold text-gray-500 mb-3">{t('dashboard_top_failure_causes', 'Top Failure Causes')}</div>
                        {topFailureCauses.length === 0 ? (
                            <div className="text-sm text-gray-500">{t('compliance_no_failure_window', 'No failure data for selected window.')}</div>
                        ) : (
                            <div className="space-y-2">
                                {topFailureCauses.map((item) => (
                                    <div key={`${item.cause}-${item.count}`} className="flex items-center justify-between">
                                        <div className="text-sm text-gray-700 dark:text-gray-200">{item.cause}</div>
                                        <div className="text-xs font-bold px-2 py-0.5 rounded bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300">
                                            {Number(item.count || 0)}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Chart */}
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 h-80">
                        <h3 className="font-bold text-gray-900 dark:text-white mb-4">{t('compliance_status_distribution', 'Compliance Status Distribution')}</h3>
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
                                    {pieData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} />
                                    ))}
                                </Pie>
                                <Tooltip />
                                <Legend />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Recent Violations List */}
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 h-80 overflow-y-auto custom-scrollbar">
                        <h3 className="font-bold text-gray-900 dark:text-white mb-4">{t('compliance_recent_violations', 'Recent Violations')}</h3>
                        <div className="space-y-3">
                            {reports.filter(r => r.status === 'violation').slice(0, 5).map(r => (
                                <div key={r.device_id} className="flex items-center justify-between p-3 bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 rounded-lg">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-full text-red-500"><XCircle size={16} /></div>
                                        <div>
                                            <div className="font-medium text-gray-900 dark:text-white">{r.device_name}</div>
                                            <div className="text-xs text-red-500">{t('compliance_score', 'Compliance Score')}: {Math.round(r.score)}%</div>
                                        </div>
                                    </div>
                                    <button onClick={() => openReportDetails(r)} className="text-xs text-gray-500 hover:text-gray-900 dark:hover:text-white">{t('compliance_view', 'View')}</button>
                                </div>
                            ))}
                            {reports.filter(r => r.status === 'violation').length === 0 && (
                                <InlineEmpty label={t('compliance_no_violations', 'No violations found.')} className="py-10" />
                            )}
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    const ReportsView = () => {
        const filteredReports = reportDeviceId
            ? reports.filter(r => String(r.device_id) === String(reportDeviceId))
            : reports;
        return (
            <div className="bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-[#25282c]">
                    <h3 className="font-bold text-gray-900 dark:text-white">{t('compliance_reports', 'Compliance Reports')}</h3>
                    <div className="flex items-center gap-2">
                        <select
                            value={reportDeviceId}
                            onChange={(e) => setReportDeviceId(e.target.value)}
                            className="h-8 px-2 text-sm rounded-lg bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200"
                        >
                            <option value="">{t('compliance_all_devices', 'All devices')}</option>
                            {devices
                                .slice()
                                .sort((a, b) => String(a?.name || '').localeCompare(String(b?.name || '')))
                                .map(d => (
                                    <option key={d.id} value={d.id}>{d.name} ({d.ip_address})</option>
                                ))}
                        </select>
                        <button onClick={() => handleExportReports('xlsx')} disabled={exportingReports} className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 rounded-lg text-sm">
                            <FileText size={14} /> {t('device_detail_export_xlsx', 'Export XLSX')}
                        </button>
                        <button onClick={() => handleExportReports('pdf')} disabled={exportingReports} className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 rounded-lg text-sm">
                            <FileText size={14} /> {t('device_detail_export_pdf', 'Export PDF')}
                        </button>
                        <button onClick={handleScan} disabled={loading} className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white rounded-lg text-sm">
                            <Play size={14} /> {t('compliance_run_new_scan', 'Run New Scan')}
                        </button>
                    </div>
                </div>
                <table className="w-full text-left text-sm">
                    <thead className="bg-gray-50 dark:bg-[#25282c] text-gray-500 font-medium border-b border-gray-200 dark:border-gray-700">
                        <tr>
                            <th className="px-6 py-4">{t('devices_col_device', 'Device')}</th>
                            <th className="px-6 py-4">{t('devices_col_status', 'Status')}</th>
                            <th className="px-6 py-4">{t('compliance_score_short', 'Score')}</th>
                            <th className="px-6 py-4">{t('compliance_last_checked', 'Last Checked')}</th>
                            <th className="px-6 py-4 text-right">{t('devices_col_actions', 'Actions')}</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {filteredReports.map(r => {
                            const details = parseReportDetails(r);
                            const automation = details.automation || {};
                            const openDriftAvailable = canOpenDrift(automation);
                            return (
                            <tr key={r.device_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                                <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{r.device_name}</td>
                                <td className="px-6 py-4">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${r.status === 'compliant' ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}`}>
                                            {r.status.toUpperCase()}
                                        </span>
                                        {automation?.status && (
                                            <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${automationToneClass(automation.status)}`}>
                                                {automationStatusLabel(automation.status)}
                                            </span>
                                        )}
                                    </div>
                                </td>
                                <td className="px-6 py-4">
                                    <div className="w-24 bg-gray-200 rounded-full h-2 overflow-hidden">
                                        <div className={`h-full ${r.score >= 100 ? 'bg-green-500' : r.score >= 80 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${r.score}%` }}></div>
                                    </div>
                                    <span className="text-xs text-gray-500 mt-1 block">{Math.round(r.score)}%</span>
                                </td>
                                <td className="px-6 py-4 text-gray-500">{new Date(r.last_checked).toLocaleString()}</td>
                                <td className="px-6 py-4 text-right">
                                    <div className="inline-flex items-center gap-3">
                                        {openDriftAvailable && (
                                            <button
                                                data-testid={`compliance-open-drift-${r.device_id}`}
                                                onClick={() => openDriftFromReport(r)}
                                                className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white"
                                            >
                                                Open Drift
                                            </button>
                                        )}
                                        <button
                                            data-testid={`compliance-report-details-${r.device_id}`}
                                            onClick={() => openReportDetails(r)}
                                            className="text-blue-500 hover:underline"
                                        >
                                            {t('compliance_view_details', 'View Details')}
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        )})}
                        {filteredReports.length === 0 && (
                            <tr>
                                <td colSpan="5" className="px-6 py-10">
                                    <InlineEmpty label={t('compliance_reports_empty', 'No reports generated yet. Run a scan.')} />
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        );
    };

    const StandardsView = () => {
        const [expandedStd, setExpandedStd] = useState(null);

        return (
            <div className="space-y-6">
                <div className="flex justify-end">
                    <button onClick={() => setShowStdModal(true)} className="h-10 inline-flex items-center gap-2 px-4 bg-blue-600 hover:bg-blue-500 text-white rounded-lg">
                        <Plus size={16} /> {t('compliance_create_standard', 'Create Standard')}
                    </button>
                </div>

                <div className="space-y-4">
                    {standards.map(std => (
                        <div key={std.id} className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
                            <div
                                className="p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                                onClick={() => setExpandedStd(expandedStd === std.id ? null : std.id)}
                            >
                                <div className="flex items-center gap-4">
                                    {expandedStd === std.id ? <ChevronDown size={20} className="text-gray-400" /> : <ChevronRight size={20} className="text-gray-400" />}
                                    <div>
                                        <h3 className="font-bold text-gray-900 dark:text-white">{std.name}</h3>
                                        <p className="text-xs text-gray-500">{std.description} / {std.device_family}</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-800 rounded text-gray-500">{std.rules.length} {t('compliance_rules', 'Rules')}</span>
                                    <button onClick={(e) => { e.stopPropagation(); handleDeleteStandard(std.id); }} className="p-2 hover:bg-red-50 text-gray-400 hover:text-red-500 rounded"><Trash2 size={16} /></button>
                                </div>
                            </div>

                            {/* Rules List */}
                            {expandedStd === std.id && (
                                <div className="border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-black/20 p-4">
                                    <div className="mb-4 flex justify-between items-center">
                                        <h4 className="text-sm font-bold text-gray-700 dark:text-gray-300">{t('compliance_rules_title', 'Compliance Rules')}</h4>
                                        <button
                                            onClick={() => { setSelectedStdId(std.id); setShowRuleModal(true); }}
                                            className="text-xs flex items-center gap-1 bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 px-3 py-1.5 rounded-lg hover:border-blue-500 text-gray-600 dark:text-gray-400"
                                        >
                                            <Plus size={12} /> {t('compliance_add_rule', 'Add Rule')}
                                        </button>
                                    </div>

                                    <div className="space-y-2">
                                        {std.rules.map(rule => (
                                            <div key={rule.id} className="flex items-start justify-between p-3 bg-white dark:bg-[#25282c] rounded-lg border border-gray-200 dark:border-gray-700 text-sm">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <span className={`w-2 h-2 rounded-full ${rule.severity === 'critical' ? 'bg-red-500' : rule.severity === 'warning' ? 'bg-orange-500' : 'bg-blue-500'}`}></span>
                                                        <span className="font-bold text-gray-800 dark:text-gray-200">{rule.name}</span>
                                                        <span className="text-[10px] uppercase bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-gray-500">{rule.check_type}</span>
                                                    </div>
                                                    <p className="text-gray-500 dark:text-gray-400 text-xs mb-2">{rule.description}</p>
                                                    <code className="block bg-gray-100 dark:bg-black/30 p-2 rounded text-xs font-mono text-gray-700 dark:text-gray-300 overflow-x-auto">
                                                        {rule.pattern}
                                                    </code>
                                                </div>
                                                <button onClick={() => handleDeleteRule(rule.id)} className="text-gray-400 hover:text-red-500 ml-4"><Trash2 size={14} /></button>
                                            </div>
                                        ))}
                                        {std.rules.length === 0 && <p className="text-center text-gray-400 text-xs py-2">{t('compliance_rules_empty', 'No rules defined yet.')}</p>}
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    const ReportDetailModal = () => {
        if (!selectedReport) return null;

        const { violations, automation, summary } = parseReportDetails(selectedReport);
        const drift = automation?.drift || {};
        const support = automation?.support || {};
        const fixCoverage = automation?.fix_coverage || {};
        const preChecks = Array.isArray(automation?.pre_check_commands) ? automation.pre_check_commands : [];
        const nextSteps = Array.isArray(automation?.next_steps) ? automation.next_steps : [];
        const openDriftAvailable = canOpenDrift(automation);
        const deviceRecord = devices.find((device) => String(device?.id) === String(selectedReport?.device_id)) || null;
        const contextSiteId = deviceRecord?.site_id ?? selectedReport?.site_id ?? null;
        const contextSiteName = deviceRecord?.site_name ?? selectedReport?.site_name ?? null;

        return (
            <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                <div data-testid="compliance-report-modal" className="bg-white dark:bg-[#1b1d1f] w-full max-w-4xl rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
                    <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between gap-4">
                        <div>
                            <div className="flex items-center gap-3">
                                <h2 className="text-xl font-bold text-gray-900 dark:text-white">{selectedReport.device_name}</h2>
                                <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${automationToneClass(automation?.status)}`}>
                                    {automationStatusLabel(automation?.status)}
                                </span>
                            </div>
                            <div className="mt-1 text-xs text-gray-500">
                                Score {Math.round(Number(selectedReport.score || summary?.score || 0))}% · violations {Number(summary?.violations_total || violations.length || 0)}
                            </div>
                        </div>
                        <div className="flex items-center gap-2 flex-wrap justify-end">
                            <Link
                                data-testid="compliance-report-open-device"
                                to={buildDevicePath(selectedReport.device_id)}
                                className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 inline-flex items-center gap-2"
                            >
                                <Activity size={14} /> {t('compliance_open_device', 'Open Device')}
                            </Link>
                            {contextSiteId && (
                                <Link
                                    data-testid="compliance-report-open-topology"
                                    to={buildTopologyPath({ siteId: contextSiteId })}
                                    className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 inline-flex items-center gap-2"
                                >
                                    <GitBranch size={14} /> {t('compliance_open_topology', 'Open Topology')}
                                </Link>
                            )}
                            <Link
                                data-testid="compliance-report-open-observability"
                                to={buildObservabilityPath({ deviceId: selectedReport.device_id, siteId: contextSiteId })}
                                className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 inline-flex items-center gap-2"
                            >
                                <Activity size={14} /> {t('compliance_open_observability', 'Open Observability')}
                            </Link>
                            <a
                                data-testid="compliance-report-open-grafana"
                                href={buildGrafanaFleetHealthUrl({ deviceId: selectedReport.device_id, siteId: contextSiteId })}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="px-3 py-2 rounded-lg border border-blue-500 bg-blue-600 hover:bg-blue-500 text-sm text-white inline-flex items-center gap-2"
                            >
                                <ExternalLink size={14} /> {t('compliance_open_grafana', 'Open Grafana')}
                            </a>
                            <a
                                data-testid="compliance-report-open-alert-dashboard"
                                href={buildGrafanaAlertingCenterUrl({ deviceId: selectedReport.device_id, siteId: contextSiteId })}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 inline-flex items-center gap-2"
                            >
                                <ExternalLink size={14} /> {t('compliance_open_alert_dashboard', 'Alert Dashboard')}
                            </a>
                            {openDriftAvailable && (
                                <button
                                    data-testid="compliance-report-open-drift"
                                    onClick={() => openDriftFromReport(selectedReport)}
                                    className="px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium"
                                >
                                    Open Drift
                                </button>
                            )}
                            <button onClick={closeReportDetails} className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800">
                                {t('common_close', 'Close')}
                            </button>
                        </div>
                    </div>

                    <div className="p-6 space-y-6 max-h-[80vh] overflow-y-auto custom-scrollbar">
                        {(contextSiteName || contextSiteId) && (
                            <div className="rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50/60 dark:bg-blue-950/10 p-4">
                                <div className="text-xs uppercase font-bold text-blue-600 dark:text-blue-300">Operational Context</div>
                                <div className="mt-2 text-sm text-gray-800 dark:text-gray-100">
                                    {contextSiteName || `Site ${contextSiteId}`}
                                </div>
                                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                    {deviceRecord?.ip_address ? `${deviceRecord.ip_address} · ` : ''}{deviceRecord?.device_type || selectedReport?.device_type || 'device'}
                                </div>
                            </div>
                        )}
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-black/20 p-4">
                                <div className="text-xs uppercase font-bold text-gray-500">Primary Action</div>
                                <div className="mt-2 text-sm font-bold text-gray-900 dark:text-white">
                                    {automation?.primary_action?.label || 'Review violations'}
                                </div>
                            </div>
                            <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-black/20 p-4">
                                <div className="text-xs uppercase font-bold text-gray-500">Golden Coverage</div>
                                <div className="mt-2 text-sm font-bold text-gray-900 dark:text-white">
                                    {Number(fixCoverage?.golden_fixable || 0)} / {Number(fixCoverage?.total || violations.length || 0)}
                                </div>
                            </div>
                            <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-black/20 p-4">
                                <div className="text-xs uppercase font-bold text-gray-500">Drift</div>
                                <div className="mt-2 text-sm font-bold text-gray-900 dark:text-white">
                                    {String(drift?.status || 'unknown')}
                                </div>
                            </div>
                            <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-black/20 p-4">
                                <div className="text-xs uppercase font-bold text-gray-500">Support Tier</div>
                                <div className="mt-2 text-sm font-bold text-gray-900 dark:text-white">
                                    {String(support?.tier || 'unknown')}
                                </div>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                            <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#25282c] p-4">
                                <div className="text-sm font-bold text-gray-900 dark:text-white mb-3">Automation Plan</div>
                                <div className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
                                    <div>Approval required: <span className="font-mono">{automation?.requires_approval ? 'yes' : 'no'}</span></div>
                                    <div>Config supported: <span className="font-mono">{support?.config_supported ? 'yes' : 'no'}</span></div>
                                    <div>Rollback supported: <span className="font-mono">{support?.rollback_supported ? 'yes' : 'no'}</span></div>
                                    <div>Manual guidance: <span className="font-mono">{Number(fixCoverage?.manual_guided || 0)}</span></div>
                                    <div>Manual review: <span className="font-mono">{Number(fixCoverage?.manual_review || 0)}</span></div>
                                </div>
                                {nextSteps.length > 0 && (
                                    <div className="mt-4">
                                        <div className="text-xs uppercase font-bold text-gray-500 mb-2">Next Steps</div>
                                        <div className="space-y-2">
                                            {nextSteps.map((step, idx) => (
                                                <div key={`${selectedReport.device_id}-step-${idx}`} className="text-sm text-gray-700 dark:text-gray-200">
                                                    {step}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {preChecks.length > 0 && (
                                    <div className="mt-4">
                                        <div className="text-xs uppercase font-bold text-gray-500 mb-2">Pre-Check Commands</div>
                                        <div className="flex flex-wrap gap-2">
                                            {preChecks.map((cmd) => (
                                                <span key={`${selectedReport.device_id}-${cmd}`} className="px-2 py-1 rounded bg-gray-100 dark:bg-black/30 text-xs font-mono text-gray-700 dark:text-gray-200">
                                                    {cmd}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#25282c] p-4">
                                <div className="text-sm font-bold text-gray-900 dark:text-white mb-3">Violations</div>
                                <div className="space-y-3">
                                    {violations.map((violation, idx) => (
                                        <div key={`${selectedReport.device_id}-violation-${idx}`} className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-black/20 p-3">
                                            <div className="flex items-center justify-between gap-3">
                                                <div className="font-bold text-gray-900 dark:text-white">{violation.rule}</div>
                                                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300">
                                                    {String(violation.severity || 'warning')}
                                                </span>
                                            </div>
                                            <div className="mt-1 text-xs text-gray-500">{violation.standard}</div>
                                            {violation.description && (
                                                <div className="mt-2 text-sm text-gray-700 dark:text-gray-200">{violation.description}</div>
                                            )}
                                            <div className="mt-2 text-xs text-gray-500">Remediation</div>
                                            <div className="mt-1 text-sm text-gray-700 dark:text-gray-200">
                                                {violation.remediation || 'No remediation guidance recorded.'}
                                            </div>
                                        </div>
                                    ))}
                                    {violations.length === 0 && (
                                        <InlineEmpty label={t('compliance_no_violations', 'No violations found.')} />
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    return (
        <div className="p-3 sm:p-4 md:p-6 h-full min-h-0 flex flex-col bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white overflow-hidden">

            {/* Header */}
            <div className="flex flex-col gap-3 xl:flex-row xl:justify-between xl:items-center mb-6 shrink-0">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <Shield className="text-green-500" /> {t('layout_page_compliance', 'Security Compliance Audit')}
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">{t('compliance_header_desc', 'Automated configuration compliance scanning and enforcement')}</p>
                </div>

                <div className="flex flex-wrap bg-white dark:bg-[#1b1d1f] p-1 rounded-xl border border-gray-200 dark:border-gray-700">
                    {['dashboard', 'reports', 'standards', 'drift'].map(tab => {
                        const tabLabel =
                            tab === 'dashboard'
                                ? t('sidebar_dashboard', 'Dashboard')
                                : tab === 'reports'
                                    ? t('compliance_reports', 'Reports')
                                    : tab === 'standards'
                                        ? t('compliance_standards', 'Standards')
                                        : t('compliance_drift', 'Drift');
                        return (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-all ${activeTab === tab
                                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                                    }`}
                            >
                                {tabLabel}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
                {activeTab === 'dashboard' && <DashboardView />}
                {activeTab === 'reports' && <ReportsView />}
                {activeTab === 'standards' && <StandardsView />}
                {activeTab === 'drift' && <DriftView devices={devices} focusDeviceId={driftFocusDeviceId} />}
            </div>

            {/* Modals */}
            <ReportDetailModal />
            {showStdModal && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-md rounded-2xl p-6 shadow-2xl animate-scale-in">
                        <h2 className="text-xl font-bold mb-4">{t('compliance_create_new_standard', 'Create New Standard')}</h2>
                        <form onSubmit={handleCreateStandard}>
                            <div className="space-y-4">
                                <input name="name" placeholder={t('compliance_standard_name', 'Standard Name')} required className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg" />
                                <input name="description" placeholder={t('compliance_description', 'Description')} className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg" />
                                <select name="device_family" className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg">
                                    <option value="cisco_ios">{t('compliance_device_family_cisco_ios', 'Cisco IOS')}</option>
                                    <option value="cisco_nxos">{t('compliance_device_family_cisco_nxos', 'Cisco NX-OS')}</option>
                                </select>
                            </div>
                            <div className="flex justify-end gap-2 mt-6">
                                <button type="button" onClick={() => setShowStdModal(false)} className="px-4 py-2 text-gray-500 hover:bg-gray-100 rounded-lg">{t('common_cancel', 'Cancel')}</button>
                                <button type="submit" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg">{t('common_create', 'Create')}</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {showRuleModal && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-lg rounded-2xl p-6 shadow-2xl animate-scale-in">
                        <h2 className="text-xl font-bold mb-4">{t('compliance_add_rule_modal', 'Add Compliance Rule')}</h2>
                        <form onSubmit={handleAddRule}>
                            <div className="space-y-4">
                                <input name="name" placeholder={t('compliance_rule_name', 'Rule Name')} required className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg" />
                                <textarea name="description" placeholder={t('compliance_rule_description', 'Description & Rationale')} className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg" />

                                <div className="grid grid-cols-2 gap-4">
                                    <select name="severity" className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg">
                                        <option value="critical">{t('compliance_severity_critical', 'Critical')}</option>
                                        <option value="warning">{t('compliance_severity_warning', 'Warning')}</option>
                                        <option value="info">{t('compliance_severity_info', 'Info')}</option>
                                    </select>
                                    <select name="check_type" className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg">
                                        <option value="simple_match">{t('compliance_check_must_contain', 'Must Contain (String)')}</option>
                                        <option value="absent_match">{t('compliance_check_must_not_contain', 'Must NOT Contain')}</option>
                                        <option value="regex_match">{t('compliance_check_regex', 'Regex Match')}</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="text-xs text-gray-500 mb-1 block ml-1">{t('compliance_pattern_label', 'Pattern to match in config')}</label>
                                    <textarea name="pattern" placeholder={t('compliance_pattern_placeholder', 'e.g. service password-encryption')} required rows={3} className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg font-mono text-sm" />
                                </div>
                            </div>
                            <div className="flex justify-end gap-2 mt-6">
                                <button type="button" onClick={() => setShowRuleModal(false)} className="px-4 py-2 text-gray-500 hover:bg-gray-100 rounded-lg">{t('common_cancel', 'Cancel')}</button>
                                <button type="submit" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg">{t('compliance_add_rule', 'Add Rule')}</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

        </div>
    );
};

export default CompliancePage;

