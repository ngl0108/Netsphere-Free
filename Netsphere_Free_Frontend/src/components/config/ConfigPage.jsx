import React, { useState, useEffect, useMemo } from 'react';
import { ApprovalService, DeviceService, SettingsService } from '../../api/services';
import { useAuth } from '../../context/AuthContext'; // [RBAC]
import { useToast } from '../../context/ToastContext';
import { evaluateChangePolicy } from '../../utils/changePolicy';
import { DOMESTIC_DEVICE_VENDOR_OPTIONS, GLOBAL_DEVICE_VENDOR_OPTIONS } from '../../utils/deviceVendorCatalog';
import { t } from '../../i18n';
import { InlineEmpty } from '../common/PageState';
import {
    FileCode, Save, Plus, Trash2, Play, Server,
    CheckCircle, AlertTriangle, X, RefreshCw, Copy, Layers
} from 'lucide-react';

const parseBoolSetting = (value, fallback = false) => {
    if (typeof value === 'boolean') return value;
    if (value == null) return fallback;
    const t = String(value).trim().toLowerCase();
    if (['true', '1', 'yes', 'y', 'on'].includes(t)) return true;
    if (['false', '0', 'no', 'n', 'off'].includes(t)) return false;
    return fallback;
};

const parseNonNegativeIntSetting = (value, fallback = 0) => {
    const n = Number(value);
    if (!Number.isFinite(n)) return Math.max(0, Number(fallback) || 0);
    return Math.max(0, Math.trunc(n));
};

const parseNonNegativeFloatSetting = (value, fallback = 0) => {
    const n = Number(value);
    if (!Number.isFinite(n)) return Math.max(0, Number(fallback) || 0);
    return Math.max(0, n);
};

const extractChangePolicyFromSettings = (raw = {}) => ({
    templateDirectMaxDevices: parseNonNegativeIntSetting(raw?.change_policy_template_direct_max_devices, 3),
    fabricLiveRequiresApproval: parseBoolSetting(raw?.change_policy_fabric_live_requires_approval, true),
});

const createDefaultDeployOptions = () => ({
    save_pre_backup: true,
    rollback_on_failure: true,
    prepare_device_snapshot: true,
    post_check_enabled: true,
    canary_count: 0,
    wave_size: 0,
    stop_on_wave_failure: true,
    inter_wave_delay_seconds: 0,
});

const parseDeployErrorMessage = (err, fallback) => {
    const detail = err?.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (typeof detail?.message === 'string' && detail.message.trim()) return detail.message;
    if (typeof err?.response?.data?.message === 'string' && err.response.data.message.trim()) return err.response.data.message;
    return err?.message || fallback;
};

const extractChangePlan = (payload) => {
    if (payload && typeof payload === 'object' && payload.change_plan && typeof payload.change_plan === 'object') {
        return payload.change_plan;
    }
    return null;
};

const statusBadgeClass = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'success' || normalized === 'ok') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300';
    if (normalized === 'warning' || normalized === 'approval' || normalized === 'approval_required') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300';
    if (normalized === 'direct' || normalized === 'info') return 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300';
    if (normalized.startsWith('skipped')) return 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
    return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300';
};

const boolLabel = (value) => (value ? 'Yes' : 'No');
const humanizeToken = (value) => String(value || '').replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase());

const ConfigPage = () => {
    const { isOperator, isAdmin } = useAuth(); // [RBAC]
    const { toast } = useToast();

    // --- States ---
    const [templates, setTemplates] = useState([]);
    const [devices, setDevices] = useState([]); // Deployment device list
    const [loading, setLoading] = useState(false);

    // Selected Template (Editing)
    const [selectedTemplate, setSelectedTemplate] = useState(null);
    const [editName, setEditName] = useState("");
    const [editCategory, setEditCategory] = useState("User-Defined");
    const [editVendor, setEditVendor] = useState("any"); // [NEW] Vendor State
    const [editContent, setEditContent] = useState("");

    // Deploy Modal State
    const [isDeployModalOpen, setIsDeployModalOpen] = useState(false);
    const [selectedDeviceIds, setSelectedDeviceIds] = useState([]);
    const [deployResult, setDeployResult] = useState(null);
    const [deployTotals, setDeployTotals] = useState(null);
    const [deployExecution, setDeployExecution] = useState(null);
    const [deployChangePlan, setDeployChangePlan] = useState(null);
    const [deploying, setDeploying] = useState(false);
    const [dryRunning, setDryRunning] = useState(false);
    const [dryRunResult, setDryRunResult] = useState(null);
    const [dryRunTotals, setDryRunTotals] = useState(null);
    const [approvalSubmitting, setApprovalSubmitting] = useState(false);
    const [deployOptions, setDeployOptions] = useState(() => createDefaultDeployOptions());
    const [changePolicy, setChangePolicy] = useState(() => ({
        templateDirectMaxDevices: 3,
        fabricLiveRequiresApproval: true,
    }));

    // Snippet Import Modal State
    const [isSnippetModalOpen, setIsSnippetModalOpen] = useState(false);

    // --- Initial Load ---
    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [tmplRes, devRes, settingsRes] = await Promise.all([
                DeviceService.getTemplates(),
                DeviceService.getDevices(),
                SettingsService.getGeneral().catch(() => ({ data: {} })),
            ]);
            setTemplates(tmplRes.data || []);
            setDevices(devRes.data || []);
            setChangePolicy(extractChangePolicyFromSettings(settingsRes?.data || {}));
        } catch (err) {
            console.error("Failed to load config data:", err);
        } finally {
            setLoading(false);
        }
    };

    // --- Template Handlers ---

    // 1. Enter new template creation mode
    const handleCreateNew = () => {
        setSelectedTemplate({ id: 'new' });
        setEditName("New Template");
        setEditCategory("User-Defined");
        setEditVendor("any");
        setEditContent("! -- NetSphere Config Template --\nhostname {{ device.name }}\nservice password-encryption\n!");
    };

    // 2. Select Template
    const handleSelectTemplate = (tmpl) => {
        setSelectedTemplate(tmpl);
        setEditName(tmpl.name);
        setEditCategory(tmpl.category || "User-Defined");
        setEditContent(tmpl.content);

        // Parse vendor from tags (Format: "vendor:cisco,v1")
        if (tmpl.tags && tmpl.tags.includes('vendor:')) {
            const tag = tmpl.tags.split(',').find(t => t.startsWith('vendor:'));
            setEditVendor(tag ? tag.split(':')[1] : 'any');
        } else {
            setEditVendor('any');
        }
    };

    // 3. Save (Create or Update)
    const handleSave = async () => {
        if (!editName || !editContent) return toast.warning(t('config_name_content_required'));
        setLoading(true);

        try {
            // Build tags string
            const tagsList = ["v1"];
            if (editVendor && editVendor !== 'any') {
                tagsList.push(`vendor:${editVendor}`);
            }

            const payload = {
                name: editName,
                category: editCategory,
                content: editContent,
                tags: tagsList.join(',')
            };

            if (selectedTemplate.id === 'new') {
                // Create
                await DeviceService.createTemplate(payload);
                toast.success(t('config_template_created'));
            } else {
                // Update
                if (DeviceService.updateTemplate) {
                    await DeviceService.updateTemplate(selectedTemplate.id, payload);
                    toast.success(t('config_template_updated'));
                } else {
                    toast.warning(t('config_update_api_not_implemented'));
                    return;
                }
            }

            // Refresh list & reset selection
            await loadData();
            setSelectedTemplate(null);
        } catch (err) {
            console.error(err);
            toast.error(`${t('config_save_failed')}: ${err.response?.data?.detail || err.message}`);
        } finally {
            setLoading(false);
        }
    };

    // 4. Delete
    const handleDelete = async () => {
        if (!selectedTemplate || selectedTemplate.id === 'new') return;
        if (!window.confirm("Delete this template?")) return;

        setLoading(true);
        try {
            if (DeviceService.deleteTemplate) {
                await DeviceService.deleteTemplate(selectedTemplate.id);
                toast.success(t('config_template_deleted'));
            } else {
                toast.warning(t('config_delete_api_not_implemented'));
                return;
            }
            await loadData();
            setSelectedTemplate(null);
        } catch (err) {
            console.error(err);
            toast.error(`${t('config_delete_failed')}: ${err.response?.data?.detail || err.message}`);
        } finally {
            setLoading(false);
        }
    };

    // 5. Merge Snippet (Import Snippet)
    const handleImportSnippet = (snippetContent, snippetName) => {
        const separator = `\n! ========================================\n! [Imported] ${snippetName}\n! ========================================\n`;
        setEditContent(prev => prev + separator + snippetContent + "\n");
        setIsSnippetModalOpen(false);
    };

    // --- Deploy Logic ---

    const resetDeployRunState = ({ clearPlan = true } = {}) => {
        setDeployResult(null);
        setDeployTotals(null);
        setDeployExecution(null);
        setDryRunResult(null);
        setDryRunTotals(null);
        if (clearPlan) {
            setDeployChangePlan(null);
        }
    };

    const handleDeployOptionChange = (key, value) => {
        resetDeployRunState();
        setDeployOptions((prev) => ({ ...prev, [key]: value }));
    };

    const buildDeployPayload = () => ({
        device_ids: selectedDeviceIds.map((id) => Number(id)),
        variables: {},
        save_pre_backup: !!deployOptions.save_pre_backup,
        rollback_on_failure: !!deployOptions.rollback_on_failure,
        prepare_device_snapshot: !!deployOptions.prepare_device_snapshot,
        pre_check_commands: [],
        post_check_enabled: !!deployOptions.post_check_enabled,
        post_check_commands: [],
        canary_count: parseNonNegativeIntSetting(deployOptions.canary_count, 0),
        wave_size: parseNonNegativeIntSetting(deployOptions.wave_size, 0),
        stop_on_wave_failure: !!deployOptions.stop_on_wave_failure,
        inter_wave_delay_seconds: parseNonNegativeFloatSetting(deployOptions.inter_wave_delay_seconds, 0),
    });

    const handleOpenDeploy = () => {
        if (!selectedTemplate || selectedTemplate.id === 'new') return toast.warning(t('config_save_template_first'));
        setSelectedDeviceIds([]);
        setDeployOptions(createDefaultDeployOptions());
        resetDeployRunState();
        setIsDeployModalOpen(true);
    };

    const handleToggleDevice = (id) => {
        if (deploying || dryRunning || approvalSubmitting) return;

        resetDeployRunState();
        setSelectedDeviceIds(prev =>
            prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id]
        );
    };

    // Execute deployment (API call)
    const handleExecuteDeploy = async () => {
        if (selectedDeviceIds.length === 0) return toast.warning(t('config_select_at_least_one_device'));

        setDeploying(true);
        setDeployResult(null);
        setDeployTotals(null);
        setDeployExecution(null);

        try {
            const res = await DeviceService.deployTemplate(selectedTemplate.id, buildDeployPayload());
            const summary = res.data.summary || [];
            setDeployResult(summary);
            setDeployTotals(res.data.totals || null);
            setDeployExecution(res.data.execution || null);
            setDeployChangePlan(extractChangePlan(res.data));

            if (summary.length === 0) {
                toast.info(t('config_deploy_no_summary'));
            }
        } catch (err) {
            console.error("Deploy Error:", err);
            const responseData = err?.response?.data;
            const changePlan = extractChangePlan(responseData?.detail) || extractChangePlan(responseData);
            if (changePlan) {
                setDeployChangePlan(changePlan);
            }
            const message = parseDeployErrorMessage(err, t('config_deploy_failed'));
            if (Number(err?.response?.status) === 409) {
                toast.warning(message);
            } else {
                toast.error(`${t('config_deploy_failed')}: ${message}`);
            }
        } finally {
            setDeploying(false);
        }
    };

    const handleExecuteDryRun = async () => {
        if (selectedDeviceIds.length === 0) return toast.warning(t('config_select_at_least_one_device'));

        setDryRunning(true);
        setDryRunResult(null);
        setDryRunTotals(null);

        try {
            const res = await DeviceService.dryRunTemplate(selectedTemplate.id, selectedDeviceIds, {
                includeRendered: false,
                rollbackOnFailure: deployOptions.rollback_on_failure,
                postCheckEnabled: deployOptions.post_check_enabled,
                postCheckCommands: [],
                canaryCount: deployOptions.canary_count,
                waveSize: deployOptions.wave_size,
                stopOnWaveFailure: deployOptions.stop_on_wave_failure,
                interWaveDelaySeconds: deployOptions.inter_wave_delay_seconds,
            });
            const summary = res.data.summary || [];
            setDryRunResult(summary);
            setDryRunTotals(res.data.totals || null);
            setDeployChangePlan(extractChangePlan(res.data));
            if (summary.length === 0) toast.info(t('config_dry_run_no_summary'));
        } catch (err) {
            console.error("Dry Run Error:", err);
            const responseData = err?.response?.data;
            const changePlan = extractChangePlan(responseData?.detail) || extractChangePlan(responseData);
            if (changePlan) {
                setDeployChangePlan(changePlan);
            }
            const message = parseDeployErrorMessage(err, t('config_dry_run_failed'));
            if (Number(err?.response?.status) === 409) {
                toast.warning(message);
            } else {
                toast.error(`${t('config_dry_run_failed')}: ${message}`);
            }
        } finally {
            setDryRunning(false);
        }
    };

    const handleRequestDeployApproval = async () => {
        if (!selectedTemplate || selectedTemplate.id === 'new') {
            toast.warning(t('config_save_template_first'));
            return;
        }
        if (selectedDeviceIds.length === 0) {
            toast.warning(t('config_select_at_least_one_device'));
            return;
        }
        if ((deployChangePlan?.route || '') === 'blocked') {
            toast.warning('Deployment is blocked by the current support policy. Review the change plan first.');
            return;
        }

        setApprovalSubmitting(true);
        try {
            const selectedSet = new Set(selectedDeviceIds.map(Number));
            const targetNames = devices
                .filter((d) => selectedSet.has(Number(d.id)))
                .map((d) => d.name || d.ip_address || `device-${d.id}`)
                .slice(0, 8);
            const remaining = Math.max(0, selectedDeviceIds.length - targetNames.length);
            const targetText = remaining > 0
                ? `${targetNames.join(', ')} (+${remaining} more)`
                : targetNames.join(', ');

            await ApprovalService.create({
                title: `[Template] ${selectedTemplate.name} deploy (${selectedDeviceIds.length} devices)`,
                description: [
                    "Template deployment approval request",
                    `Template: ${selectedTemplate.name} (#${selectedTemplate.id})`,
                    `Targets: ${targetText || selectedDeviceIds.join(', ')}`,
                    `Route: ${(deployChangePlan?.route || templateDeployPolicy.route || 'approval').toUpperCase()}`,
                ].join('\n'),
                request_type: "template_deploy",
                payload: {
                    template_id: Number(selectedTemplate.id),
                    ...buildDeployPayload(),
                },
            });
            toast.success(t('config_approval_submitted'));
            setIsDeployModalOpen(false);
        } catch (err) {
            console.error("Approval request failed:", err);
            const message = parseDeployErrorMessage(err, t('config_approval_failed'));
            toast.error(`${t('config_approval_failed')}: ${message}`);
        } finally {
            setApprovalSubmitting(false);
        }
    };

    // Template Filter (System vs User)
    const systemTemplates = templates.filter(t => t.category !== 'User-Defined');
    const userTemplates = templates.filter(t => t.category === 'User-Defined');
    const templateDeployPolicy = useMemo(
        () => evaluateChangePolicy({
            kind: "template_deploy",
            targetCount: selectedDeviceIds.length,
            policy: changePolicy,
        }),
        [selectedDeviceIds.length, changePolicy],
    );
    const effectiveChangePlan = deployChangePlan || {
        route: templateDeployPolicy.route,
        reason: templateDeployPolicy.reason,
        requires_approval: templateDeployPolicy.route === "approval",
        approval_bound: false,
        target_count: selectedDeviceIds.length,
        direct_max_devices: changePolicy.templateDirectMaxDevices,
        rollback_on_failure: !!deployOptions.rollback_on_failure,
        blocked_config_devices: [],
        blocked_rollback_devices: [],
        rollout: {
            canary_count: parseNonNegativeIntSetting(deployOptions.canary_count, 0),
            wave_size: parseNonNegativeIntSetting(deployOptions.wave_size, 0),
            waves_total: 0,
            stop_on_wave_failure: !!deployOptions.stop_on_wave_failure,
            inter_wave_delay_seconds: parseNonNegativeFloatSetting(deployOptions.inter_wave_delay_seconds, 0),
        },
        summary: {
            config_supported: selectedDeviceIds.length,
            rollback_supported: selectedDeviceIds.length,
            blocked_config: 0,
            blocked_rollback: 0,
        },
    };
    const smartRoute = effectiveChangePlan?.route || templateDeployPolicy.route;
    const smartRouteIsApproval = smartRoute === "approval";
    const smartRouteIsBlocked = smartRoute === "blocked";
    const smartSubmitting = smartRouteIsApproval ? approvalSubmitting : deploying;
    const handleSmartDeploy = async () => {
        if (smartRouteIsBlocked) {
            toast.warning('Deployment is blocked by the current support policy. Review the change plan first.');
            return;
        }
        if (smartRouteIsApproval) {
            await handleRequestDeployApproval();
            return;
        }
        await handleExecuteDeploy();
    };
    const smartActionLabel = smartRouteIsBlocked
        ? 'Blocked by Policy'
        : smartRouteIsApproval
            ? 'Request Approval'
            : 'Execute Deploy';
    const blockedConfigDevices = Array.isArray(effectiveChangePlan?.blocked_config_devices)
        ? effectiveChangePlan.blocked_config_devices
        : [];
    const blockedRollbackDevices = Array.isArray(effectiveChangePlan?.blocked_rollback_devices)
        ? effectiveChangePlan.blocked_rollback_devices
        : [];
    const rolloutSummary = effectiveChangePlan?.rollout || {};
    const planSummary = effectiveChangePlan?.summary || {};

    return (
        <div className="flex flex-col lg:flex-row h-full min-h-0 bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white transition-colors">

            {/* 1. Left Sidebar: Template List */}
            <div className="w-full lg:w-[320px] lg:min-w-[300px] border-b lg:border-b-0 lg:border-r border-gray-200 dark:border-gray-800 flex flex-col bg-white dark:bg-[#15171a] max-h-[42dvh] lg:max-h-none">
                <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex justify-between items-center">
                    <h2 className="font-bold flex items-center gap-2 text-lg">
                        <FileCode className="text-blue-500" size={20} /> Templates
                    </h2>
                    {/* [RBAC] Only Network Admin+ can create */}
                    {isOperator() && (
                        <button onClick={handleCreateNew} className="p-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg shadow-lg shadow-blue-500/20 transition-all">
                            <Plus size={18} />
                        </button>
                    )}
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-6">
                    {/* User Templates */}
                    <div>
                        <h3 className="text-xs font-bold text-gray-500 dark:text-gray-500 uppercase mb-3 flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-blue-500"></span> User Defined ({userTemplates.length})
                        </h3>
                        <div className="space-y-2">
                            {userTemplates.length === 0 && <InlineEmpty label="No templates yet." className="justify-start pl-4" />}
                            {userTemplates.map(tmpl => (
                                <div
                                    key={tmpl.id}
                                    data-testid={`config-template-${tmpl.id}`}
                                    onClick={() => handleSelectTemplate(tmpl)}
                                    className={`p-3 rounded-lg cursor-pointer text-sm flex justify-between items-center group transition-colors
                    ${selectedTemplate?.id === tmpl.id ? 'bg-blue-100 text-blue-600 border border-blue-300 dark:bg-blue-600/20 dark:text-blue-400 dark:border-blue-500/30' : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 border border-transparent'}`}
                                >
                                    <div className="flex flex-col gap-1 w-full overflow-hidden">
                                        <span className="truncate font-medium">{tmpl.name}</span>
                                        {tmpl.tags && tmpl.tags.includes('vendor:') && (
                                            <span className="text-[9px] px-1 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 capitalize w-fit">
                                                {tmpl.tags.split(',').find(t => t.startsWith('vendor:')).split(':')[1]}
                                            </span>
                                        )}
                                    </div>
                                    <span className="text-[10px] bg-gray-200 dark:bg-gray-800 px-1.5 py-0.5 rounded text-gray-600 dark:text-gray-500 group-hover:bg-gray-300 dark:group-hover:bg-black group-hover:text-gray-800 dark:group-hover:text-gray-300 transition-colors ml-2 shrink-0">
                                        {tmpl.category}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* System Templates */}
                    <div>
                        <h3 className="text-xs font-bold text-gray-500 dark:text-gray-500 uppercase mb-3 flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-purple-500"></span> System / Global ({systemTemplates.length})
                        </h3>
                        <div className="space-y-2">
                            {systemTemplates.length === 0 && <InlineEmpty label="No system templates." className="justify-start pl-4" />}
                            {systemTemplates.map(tmpl => (
                                <div
                                    key={tmpl.id}
                                    data-testid={`config-template-${tmpl.id}`}
                                    onClick={() => handleSelectTemplate(tmpl)}
                                    className={`p-3 rounded-lg cursor-pointer text-sm flex justify-between items-center group transition-colors
                    ${selectedTemplate?.id === tmpl.id ? 'bg-purple-100 text-purple-600 border border-purple-300 dark:bg-purple-600/20 dark:text-purple-400 dark:border-purple-500/30' : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 border border-transparent'}`}
                                >
                                    <div className="flex flex-col gap-1 w-full overflow-hidden">
                                        <span className="truncate font-medium">{tmpl.name}</span>
                                        {tmpl.tags && tmpl.tags.includes('vendor:') && (
                                            <span className="text-[9px] px-1 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 capitalize w-fit">
                                                {tmpl.tags.split(',').find(t => t.startsWith('vendor:')).split(':')[1]}
                                            </span>
                                        )}
                                    </div>
                                    <span className="text-[10px] bg-gray-200 dark:bg-gray-800 px-1.5 py-0.5 rounded text-gray-600 dark:text-gray-500 group-hover:bg-gray-300 dark:group-hover:bg-black group-hover:text-gray-800 dark:group-hover:text-gray-300 transition-colors ml-2 shrink-0">
                                        {tmpl.category}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* 2. Main Editor Area */}
            <div className="flex-1 min-h-0 flex flex-col min-w-0 bg-gray-50 dark:bg-[#0e1012]">
                {selectedTemplate ? (
                    <>
                        {/* Toolbar */}
                        <div className="h-16 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between px-3 sm:px-4 md:px-6 bg-white dark:bg-[#15171a]">
                            <div className="flex items-center gap-4 flex-1 mr-4">
                                <input
                                    data-testid="config-template-name-input"
                                    className="bg-transparent text-lg font-bold text-gray-900 dark:text-white outline-none w-full placeholder-gray-400 dark:placeholder-gray-600 focus:placeholder-gray-500"
                                    value={editName}
                                    onChange={(e) => setEditName(e.target.value)}
                                    placeholder={t('config_template_name_placeholder', 'Template Name...')}
                                />
                                {/* Vendor Selection */}
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-gray-500 uppercase font-bold whitespace-nowrap">Vendor:</span>
                                    <select
                                        value={editVendor}
                                        onChange={(e) => setEditVendor(e.target.value)}
                                        className="bg-gray-100 dark:bg-[#202327] border border-gray-300 dark:border-gray-700 rounded text-xs px-2 py-1 text-gray-900 dark:text-gray-300 outline-none focus:border-blue-500"
                                    >
                                        <option value="any">Any / Global</option>
                                        <optgroup label={t('devices_vendor_global', 'Global Vendors')}>
                                            {GLOBAL_DEVICE_VENDOR_OPTIONS.map((option) => (
                                                <option key={option.value} value={option.value}>{option.label}</option>
                                            ))}
                                        </optgroup>
                                        <optgroup label={t('devices_vendor_domestic', 'Domestic Vendors (Korea)')}>
                                            {DOMESTIC_DEVICE_VENDOR_OPTIONS.map((option) => (
                                                <option key={option.value} value={option.value}>{option.label}</option>
                                            ))}
                                        </optgroup>
                                    </select>
                                </div>
                                {/* Category Selection */}
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-gray-500 uppercase font-bold whitespace-nowrap">Group:</span>
                                    <select
                                        value={editCategory}
                                        onChange={(e) => setEditCategory(e.target.value)}
                                        className="bg-gray-100 dark:bg-[#202327] border border-gray-300 dark:border-gray-700 rounded text-xs px-2 py-1 text-gray-900 dark:text-gray-300 outline-none focus:border-blue-500"
                                    >
                                        <option value="User-Defined">User Defined</option>
                                        <option value="Global">Global</option>
                                        <option value="Branch">Branch Site</option>
                                        <option value="DC">Data Center</option>
                                        <option value="Switching">Switching</option>
                                        <option value="Routing">Routing</option>
                                        <option value="Security">Security</option>
                                    </select>
                                </div>
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => setIsSnippetModalOpen(true)}
                                    data-testid="config-open-merge-snippet"
                                    className="flex items-center gap-2 px-3 py-2 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 rounded border border-gray-300 dark:border-gray-700 transition-colors text-xs font-bold mr-2"
                                    title={t('config_merge_snippet_title', 'Merge another template into this one')}
                                >
                                    <Copy size={14} /> {t('config_merge_snippet', 'Merge Snippet')}
                                </button>

                                {selectedTemplate.id !== 'new' && (
                                    <>
                                        {/* [RBAC] Only Admin can delete */}
                                        {isAdmin() && (
                                            <button
                                                onClick={handleDelete}
                                                className="flex items-center gap-2 px-4 py-2 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors text-sm font-medium"
                                            >
                                                <Trash2 size={16} /> Delete
                                            </button>
                                        )}
                                        {/* [RBAC] Network Admin+ can deploy */}
                                        {isOperator() && (
                                            <button
                                                onClick={handleOpenDeploy}
                                                data-testid="config-open-deploy"
                                                className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded shadow-lg shadow-green-900/20 transition-colors text-sm font-bold"
                                            >
                                                <Play size={16} /> Deploy
                                            </button>
                                        )}
                                    </>
                                )}
                                <button
                                    onClick={handleSave}
                                    data-testid="config-save-template"
                                    disabled={loading}
                                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded shadow-lg shadow-blue-900/20 transition-colors text-sm font-bold disabled:opacity-50"
                                >
                                    {loading ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
                                    Save
                                </button>
                            </div>
                        </div>

                        {/* Code Editor */}
                        <div className="flex-1 p-6 relative flex flex-col">
                            <textarea
                                className="flex-1 w-full bg-white dark:bg-[#1b1d1f] text-gray-900 dark:text-gray-300 font-mono text-sm p-6 rounded-xl border border-gray-200 dark:border-gray-800 outline-none resize-none focus:border-blue-500/50 transition-colors leading-relaxed custom-scrollbar shadow-inner"
                                value={editContent}
                                onChange={(e) => setEditContent(e.target.value)}
                                placeholder={t('config_template_editor_placeholder', '# Write your Jinja2 configuration template here...&#10;hostname {{ device.name }}&#10;interface GigabitEthernet1&#10; ip address {{ device.ip_address }} 255.255.255.0')}
                                spellCheck="false"
                            />
                            <div className="absolute bottom-4 right-8 flex items-center gap-4 pointer-events-none">
                                <div className="text-xs text-gray-300 dark:text-gray-600 bg-gray-900/80 dark:bg-black/50 px-2 py-1 rounded backdrop-blur">
                                    Variables available: {`{{ hostname }}, {{ management_ip }}, {{ device.model }}`}
                                </div>
                                <div className="text-xs text-blue-300 dark:text-blue-500/50 bg-gray-900/80 dark:bg-black/50 px-2 py-1 rounded backdrop-blur font-bold">
                                    Jinja2 Syntax Supported
                                </div>
                            </div>
                        </div>
                    </>
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-gray-600">
                        <div className="p-8 bg-white dark:bg-[#15171a] rounded-full mb-6 animate-pulse shadow-sm">
                            <FileCode size={64} className="opacity-20 text-blue-500" />
                        </div>
                        <p className="text-xl font-bold text-gray-500 dark:text-gray-400">Select a template to edit</p>
                        <p className="text-sm mt-2 text-gray-400">or create a new one to start building configurations.</p>
                        <button data-testid="config-create-first-template" onClick={handleCreateNew} className="mt-8 px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold shadow-lg shadow-blue-500/20 transition-all flex items-center gap-2">
                            <Plus size={18} /> Create First Template
                        </button>
                    </div>
                )}
            </div>

            {/* 3. Deployment Modal */}
            {isDeployModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 dark:bg-black/80 backdrop-blur-sm animate-fade-in">
                    <div data-testid="config-deploy-modal" className="bg-white dark:bg-[#1b1d1f] w-full max-w-4xl h-[80vh] rounded-2xl border border-gray-200 dark:border-gray-800 shadow-2xl flex flex-col overflow-hidden animate-scale-in">

                        {/* Modal Header */}
                        <div className="p-6 border-b border-gray-200 dark:border-gray-800 flex justify-between items-center bg-gray-50 dark:bg-[#202327]">
                            <div>
                                <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                    <Play className="text-green-500" /> Deploy Configuration
                                </h2>
                                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                    Applying template <span className="text-blue-500 dark:text-blue-400 font-mono">'{selectedTemplate.name}'</span>
                                </p>
                            </div>
                            <button data-testid="config-close-deploy-modal" onClick={() => setIsDeployModalOpen(false)} className="p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors">
                                <X className="text-gray-400 hover:text-gray-900 dark:hover:text-white" />
                            </button>
                        </div>

                        {/* Modal Body */}
                        <div className="flex-1 overflow-hidden flex">

                            {/* Left: Device Selection + Guard Options */}
                            <div className="w-[44%] p-6 border-r border-gray-200 dark:border-gray-800 overflow-y-auto custom-scrollbar space-y-5">
                                <div>
                                    <div className="flex justify-between items-center mb-4">
                                        <h3 className="text-sm font-bold text-gray-500 dark:text-gray-400 uppercase">Target Devices</h3>
                                        <span className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-2 py-1 rounded font-bold border border-blue-200 dark:border-blue-500/30">
                                            {selectedDeviceIds.length} Selected
                                        </span>
                                    </div>
                                    <div className="space-y-2">
                                        {devices.length === 0 && <InlineEmpty label="No devices found." />}
                                        {devices.map(dev => (
                                            <div
                                                key={dev.id}
                                                data-testid={`config-device-${dev.id}`}
                                                onClick={() => handleToggleDevice(dev.id)}
                                                className={`flex items-center gap-3 p-3 rounded-lg border transition-all cursor-pointer group
                        ${selectedDeviceIds.includes(dev.id)
                                                        ? 'bg-blue-50 border-blue-200 dark:bg-blue-600/10 dark:border-blue-500/50'
                                                        : 'bg-white dark:bg-[#25282c] border-transparent hover:bg-gray-50 dark:hover:bg-[#2d3136]'
                                                    } ${(deploying || dryRunning || approvalSubmitting) ? 'pointer-events-none opacity-50' : ''}`}
                                            >
                                                <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors
                        ${selectedDeviceIds.includes(dev.id) ? 'bg-blue-500 border-blue-500' : 'border-gray-300 dark:border-gray-600 group-hover:border-gray-400'}`}>
                                                    {selectedDeviceIds.includes(dev.id) && <CheckCircle size={12} className="text-white" />}
                                                </div>
                                                <div className="min-w-0">
                                                    <div className="text-sm font-bold text-gray-900 dark:text-gray-200 truncate">{dev.name}</div>
                                                    <div className="text-xs text-gray-500 truncate">{dev.ip_address}</div>
                                                </div>
                                                <div className={`ml-auto px-2 py-0.5 rounded text-[10px] uppercase font-bold ${dev.status === 'online' ? 'text-green-600 bg-green-50 dark:text-emerald-500 dark:bg-emerald-500/10' : 'text-red-600 bg-red-50 dark:text-red-500 dark:bg-red-500/10'}`}>
                                                    {dev.status}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                <div data-testid="config-deploy-options" className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#0e1012] p-4 space-y-4">
                                    <div>
                                        <h3 className="text-sm font-bold text-gray-900 dark:text-gray-200">Deploy Guard Options</h3>
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Changing options clears the current dry-run or deploy result.</p>
                                    </div>
                                    <div className="grid grid-cols-1 gap-2 text-sm text-gray-700 dark:text-gray-300">
                                        <label className="flex items-center gap-2">
                                            <input
                                                type="checkbox"
                                                checked={!!deployOptions.save_pre_backup}
                                                disabled={deploying || dryRunning || approvalSubmitting}
                                                onChange={(e) => handleDeployOptionChange('save_pre_backup', e.target.checked)}
                                            />
                                            <span>Save pre-backup</span>
                                        </label>
                                        <label className="flex items-center gap-2">
                                            <input
                                                type="checkbox"
                                                checked={!!deployOptions.rollback_on_failure}
                                                disabled={deploying || dryRunning || approvalSubmitting}
                                                onChange={(e) => handleDeployOptionChange('rollback_on_failure', e.target.checked)}
                                            />
                                            <span>Rollback on failure</span>
                                        </label>
                                        <label className="flex items-center gap-2">
                                            <input
                                                type="checkbox"
                                                checked={!!deployOptions.prepare_device_snapshot}
                                                disabled={deploying || dryRunning || approvalSubmitting}
                                                onChange={(e) => handleDeployOptionChange('prepare_device_snapshot', e.target.checked)}
                                            />
                                            <span>Prepare device snapshot</span>
                                        </label>
                                        <label className="flex items-center gap-2">
                                            <input
                                                type="checkbox"
                                                checked={!!deployOptions.post_check_enabled}
                                                disabled={deploying || dryRunning || approvalSubmitting}
                                                onChange={(e) => handleDeployOptionChange('post_check_enabled', e.target.checked)}
                                            />
                                            <span>Enable post-check</span>
                                        </label>
                                        <label className="flex items-center gap-2">
                                            <input
                                                type="checkbox"
                                                checked={!!deployOptions.stop_on_wave_failure}
                                                disabled={deploying || dryRunning || approvalSubmitting}
                                                onChange={(e) => handleDeployOptionChange('stop_on_wave_failure', e.target.checked)}
                                            />
                                            <span>Stop on wave failure</span>
                                        </label>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <label className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">
                                            {t('config_deploy_canary_count', 'Canary Count')}
                                            <input
                                                aria-label={t('config_deploy_canary_count_aria', 'Canary count')}
                                                type="number"
                                                min="0"
                                                value={deployOptions.canary_count}
                                                disabled={deploying || dryRunning || approvalSubmitting}
                                                onChange={(e) => handleDeployOptionChange('canary_count', parseNonNegativeIntSetting(e.target.value, 0))}
                                                className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#15171a] px-3 py-2 text-sm font-medium text-gray-900 dark:text-gray-200"
                                            />
                                        </label>
                                        <label className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">
                                            {t('config_deploy_wave_size', 'Wave Size')}
                                            <input
                                                aria-label={t('config_deploy_wave_size_aria', 'Wave size')}
                                                type="number"
                                                min="0"
                                                value={deployOptions.wave_size}
                                                disabled={deploying || dryRunning || approvalSubmitting}
                                                onChange={(e) => handleDeployOptionChange('wave_size', parseNonNegativeIntSetting(e.target.value, 0))}
                                                className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#15171a] px-3 py-2 text-sm font-medium text-gray-900 dark:text-gray-200"
                                            />
                                        </label>
                                        <label className="col-span-2 text-xs font-bold uppercase text-gray-500 dark:text-gray-400">
                                            {t('config_deploy_inter_wave_delay', 'Inter-wave Delay (seconds)')}
                                            <input
                                                aria-label={t('config_deploy_inter_wave_delay_aria', 'Inter-wave delay')}
                                                type="number"
                                                min="0"
                                                step="0.5"
                                                value={deployOptions.inter_wave_delay_seconds}
                                                disabled={deploying || dryRunning || approvalSubmitting}
                                                onChange={(e) => handleDeployOptionChange('inter_wave_delay_seconds', parseNonNegativeFloatSetting(e.target.value, 0))}
                                                className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#15171a] px-3 py-2 text-sm font-medium text-gray-900 dark:text-gray-200"
                                            />
                                        </label>
                                    </div>
                                </div>
                            </div>

                            {/* Right: Change Plan + Execution */}
                            <div className="w-[56%] p-6 bg-gray-50 dark:bg-black flex flex-col gap-4 overflow-y-auto custom-scrollbar">
                                <div data-testid="config-change-plan" className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#0e1012] p-4 space-y-3">
                                    <div className="flex items-start justify-between gap-3">
                                        <div>
                                            <h3 className="text-sm font-bold text-gray-900 dark:text-gray-200 flex items-center gap-2">
                                                <Server size={16} /> Change Plan
                                            </h3>
                                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{effectiveChangePlan?.reason || 'Select devices to evaluate deployment policy.'}</p>
                                        </div>
                                        <span className={`text-[10px] px-2 py-1 rounded uppercase font-bold ${statusBadgeClass(smartRoute)}`}>
                                            {smartRoute}
                                        </span>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3 text-xs">
                                        <div className="rounded-lg bg-gray-50 dark:bg-[#15171a] p-3">
                                            <div className="text-gray-500 dark:text-gray-400">Targets</div>
                                            <div className="mt-1 text-sm font-bold text-gray-900 dark:text-gray-200">{effectiveChangePlan?.target_count ?? selectedDeviceIds.length}</div>
                                        </div>
                                        <div className="rounded-lg bg-gray-50 dark:bg-[#15171a] p-3">
                                            <div className="text-gray-500 dark:text-gray-400">Direct Threshold</div>
                                            <div className="mt-1 text-sm font-bold text-gray-900 dark:text-gray-200">{effectiveChangePlan?.direct_max_devices ?? changePolicy.templateDirectMaxDevices}</div>
                                        </div>
                                        <div className="rounded-lg bg-gray-50 dark:bg-[#15171a] p-3">
                                            <div className="text-gray-500 dark:text-gray-400">Rollback on Failure</div>
                                            <div className="mt-1 text-sm font-bold text-gray-900 dark:text-gray-200">{boolLabel(effectiveChangePlan?.rollback_on_failure)}</div>
                                        </div>
                                        <div className="rounded-lg bg-gray-50 dark:bg-[#15171a] p-3">
                                            <div className="text-gray-500 dark:text-gray-400">Approval Bound</div>
                                            <div className="mt-1 text-sm font-bold text-gray-900 dark:text-gray-200">{boolLabel(effectiveChangePlan?.approval_bound)}</div>
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3 text-xs">
                                        <div className="rounded-lg border border-gray-200 dark:border-gray-800 p-3">
                                            <div className="font-bold text-gray-700 dark:text-gray-300">Rollout</div>
                                            <div className="mt-2 space-y-1 text-gray-500 dark:text-gray-400">
                                                <div>Canary: <span className="font-semibold text-gray-800 dark:text-gray-200">{rolloutSummary.canary_count ?? 0}</span></div>
                                                <div>Wave size: <span className="font-semibold text-gray-800 dark:text-gray-200">{rolloutSummary.wave_size ?? 0}</span></div>
                                                <div>Waves: <span className="font-semibold text-gray-800 dark:text-gray-200">{rolloutSummary.waves_total ?? 0}</span></div>
                                                <div>Stop on failure: <span className="font-semibold text-gray-800 dark:text-gray-200">{boolLabel(rolloutSummary.stop_on_wave_failure)}</span></div>
                                                <div>Delay: <span className="font-semibold text-gray-800 dark:text-gray-200">{rolloutSummary.inter_wave_delay_seconds ?? 0}s</span></div>
                                            </div>
                                        </div>
                                        <div className="rounded-lg border border-gray-200 dark:border-gray-800 p-3">
                                            <div className="font-bold text-gray-700 dark:text-gray-300">Policy Summary</div>
                                            <div className="mt-2 space-y-1 text-gray-500 dark:text-gray-400">
                                                <div>Config supported: <span className="font-semibold text-gray-800 dark:text-gray-200">{planSummary.config_supported ?? selectedDeviceIds.length}</span></div>
                                                <div>Rollback supported: <span className="font-semibold text-gray-800 dark:text-gray-200">{planSummary.rollback_supported ?? selectedDeviceIds.length}</span></div>
                                                <div>Blocked config: <span className="font-semibold text-gray-800 dark:text-gray-200">{planSummary.blocked_config ?? 0}</span></div>
                                                <div>Blocked rollback: <span className="font-semibold text-gray-800 dark:text-gray-200">{planSummary.blocked_rollback ?? 0}</span></div>
                                            </div>
                                        </div>
                                    </div>
                                    {blockedConfigDevices.length > 0 && (
                                        <div className="rounded-lg border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/10 p-3 text-xs text-red-700 dark:text-red-300">
                                            <div className="font-bold mb-1">Blocked Config Devices</div>
                                            <div>{blockedConfigDevices.map((row) => row.name || row.ip_address || row.id).join(', ')}</div>
                                        </div>
                                    )}
                                    {blockedRollbackDevices.length > 0 && (
                                        <div className="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/10 p-3 text-xs text-amber-700 dark:text-amber-300">
                                            <div className="font-bold mb-1">Blocked Rollback Devices</div>
                                            <div>{blockedRollbackDevices.map((row) => row.name || row.ip_address || row.id).join(', ')}</div>
                                        </div>
                                    )}
                                    {dryRunTotals && (
                                        <div className="text-xs text-gray-500 dark:text-gray-400">
                                            Dry-run totals: total {dryRunTotals.total ?? 0}, ok {dryRunTotals.ok ?? 0}, missing variables {dryRunTotals.missing_variables ?? 0}
                                        </div>
                                    )}
                                    {deployTotals && (
                                        <div className="text-xs text-gray-500 dark:text-gray-400">
                                            Deploy totals: total {deployTotals.total ?? 0}, success {deployTotals.success ?? 0}, failed {deployTotals.failed ?? 0}, post-check failed {deployTotals.postcheck_failed ?? 0}, rollback attempted {deployTotals.rollback_attempted ?? 0}
                                        </div>
                                    )}
                                    {deployExecution && (
                                        <div className="text-xs text-gray-500 dark:text-gray-400">
                                            Execution: waves {deployExecution.waves_executed ?? 0}/{deployExecution.waves_total ?? 0}, halted {String(!!deployExecution.halted)}, execution id {deployExecution.execution_id || deployExecution.id || 'n/a'}
                                        </div>
                                    )}
                                </div>
                                <div className="flex-1 bg-white dark:bg-[#0e1012] border border-gray-200 dark:border-gray-800 rounded-lg p-4 text-xs overflow-y-auto custom-scrollbar">
                                    <h3 className="text-sm font-bold text-gray-500 dark:text-gray-400 uppercase mb-4">Execution Output</h3>
                                    {!deployResult && !deploying && !dryRunResult && !dryRunning && (
                                        <div className="text-gray-500 dark:text-gray-600 flex flex-col items-center justify-center h-full">
                                            <p>Select devices and run Dry-Run or Execute.</p>
                                        </div>
                                    )}
                                    {dryRunning && (
                                        <div className="text-gray-500 dark:text-gray-400 flex flex-col items-center justify-center h-full gap-3">
                                            <RefreshCw className="animate-spin text-blue-500" size={24} />
                                            <p className="animate-pulse">Running dry-run...</p>
                                        </div>
                                    )}
                                    {dryRunResult && (
                                        <div data-testid="config-dry-run-results" className="space-y-4">
                                            {dryRunResult.map((res, idx) => {
                                                const diffSummary = res.diff_summary || {};
                                                const guard = res.change_guard || {};
                                                const supportPolicy = res.support_policy || {};
                                                const previewLines = Array.isArray(diffSummary.preview) && diffSummary.preview.length > 0
                                                    ? diffSummary.preview
                                                    : Array.isArray(res.diff_lines)
                                                        ? res.diff_lines.slice(0, 12)
                                                        : [];
                                                return (
                                                    <div key={`${res.device_id || idx}`} className="rounded-xl border border-gray-200 dark:border-gray-800 p-4 space-y-3">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            {res.status === 'ok' ? <CheckCircle size={14} className="text-sky-500" /> : <AlertTriangle size={14} className="text-amber-500" />}
                                                            <span className="font-bold text-gray-900 dark:text-gray-300">{res.device_name || res.device_id}</span>
                                                            {res.ip_address && <span className="text-xs text-gray-500 dark:text-gray-400">{res.ip_address}</span>}
                                                            <span className={`text-[10px] px-1.5 rounded uppercase font-bold ${statusBadgeClass(res.status)}`}>
                                                                {res.status}
                                                            </span>
                                                        </div>
                                                        <div className="grid grid-cols-2 gap-2 text-xs">
                                                            <div className="rounded-lg bg-gray-50 dark:bg-[#15171a] p-3">
                                                                <div className="text-gray-500 dark:text-gray-400">Support Tier</div>
                                                                <div className="mt-1 font-bold text-gray-900 dark:text-gray-200">{supportPolicy.tier || 'unknown'} / {supportPolicy.readiness || 'unknown'}</div>
                                                            </div>
                                                            <div className="rounded-lg bg-gray-50 dark:bg-[#15171a] p-3">
                                                                <div className="text-gray-500 dark:text-gray-400">Change Guard</div>
                                                                <div className="mt-1 font-bold text-gray-900 dark:text-gray-200">
                                                                    Deploy {boolLabel(guard.deploy_allowed)} / Rollback {boolLabel(guard.rollback_supported)}
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
                                                            <div>Pre-check commands: <span className="font-semibold text-gray-800 dark:text-gray-200">{(res.pre_check_commands || []).join(', ') || 'default none'}</span></div>
                                                            <div>Post-check commands: <span className="font-semibold text-gray-800 dark:text-gray-200">{(res.post_check_commands || []).join(', ') || 'disabled'}</span></div>
                                                            {(supportPolicy.rollback_strategy?.label || supportPolicy.rollback_strategy?.mode) && (
                                                                <div>Rollback strategy: <span className="font-semibold text-gray-800 dark:text-gray-200">{supportPolicy.rollback_strategy?.label || supportPolicy.rollback_strategy?.mode}</span></div>
                                                            )}
                                                        </div>
                                                        {Array.isArray(guard.blocked_reasons) && guard.blocked_reasons.length > 0 && (
                                                            <div className="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/10 p-3 text-xs text-amber-700 dark:text-amber-300">
                                                                {guard.blocked_reasons.map((reason) => humanizeToken(reason)).join(', ')}
                                                            </div>
                                                        )}
                                                        {res.status !== 'ok' && Array.isArray(res.missing_variables) && res.missing_variables.length > 0 && (
                                                            <div className="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/10 p-3 text-xs text-amber-700 dark:text-amber-300">
                                                                Missing variables: {res.missing_variables.join(', ')}
                                                            </div>
                                                        )}
                                                        <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#15171a] p-3 text-xs text-gray-600 dark:text-gray-400">
                                                            <div className="font-bold text-gray-700 dark:text-gray-300 mb-2">
                                                                Diff Summary: +{diffSummary.added_lines ?? 0} / -{diffSummary.removed_lines ?? 0} / changed {diffSummary.changed_lines_estimate ?? 0}
                                                            </div>
                                                            <pre className="whitespace-pre-wrap font-mono text-[11px]">{previewLines.length > 0 ? previewLines.join('\n') : 'No diff (or no current backup found).'}</pre>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                    {deploying && (
                                        <div className="text-gray-500 dark:text-gray-400 flex flex-col items-center justify-center h-full gap-3">
                                            <RefreshCw className="animate-spin text-blue-500" size={24} />
                                            <p className="animate-pulse">Deploying configuration...</p>
                                        </div>
                                    )}
                                    {deployResult && (
                                        <div data-testid="config-deploy-results" className="space-y-4">
                                            {deployResult.map((res, idx) => {
                                                const preCheck = res.pre_check || {};
                                                const postCheck = res.post_check || null;
                                                const rollback = res.rollback || {};
                                                const backup = res.backup || {};
                                                const supportPolicy = res.support_policy || {};
                                                return (
                                                    <div key={`${res.device_id || idx}`} className="rounded-xl border border-gray-200 dark:border-gray-800 p-4 space-y-3">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            {String(res.status || '').toLowerCase() === 'success' ? <CheckCircle size={14} className="text-green-500" /> : <AlertTriangle size={14} className="text-red-500" />}
                                                            <span className="font-bold text-gray-900 dark:text-gray-300">{res.device_name || res.device_id}</span>
                                                            {res.ip_address && <span className="text-xs text-gray-500 dark:text-gray-400">{res.ip_address}</span>}
                                                            <span className={`text-[10px] px-1.5 rounded uppercase font-bold ${statusBadgeClass(res.status)}`}>
                                                                {res.status}
                                                            </span>
                                                            {res.failure_cause && (
                                                                <span className="text-[10px] px-1.5 rounded uppercase font-bold bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                                                                    {res.failure_cause}
                                                                </span>
                                                            )}
                                                        </div>
                                                        <div className="grid grid-cols-2 gap-2 text-xs">
                                                            <div className="rounded-lg bg-gray-50 dark:bg-[#15171a] p-3">
                                                                <div className="text-gray-500 dark:text-gray-400">Validation</div>
                                                                <div className="mt-1 font-bold text-gray-900 dark:text-gray-200">
                                                                    Pre-check {preCheck.ok === false ? 'Failed' : 'Passed'}
                                                                    {' / '}
                                                                    Post-check {postCheck ? (postCheck.ok ? 'Passed' : 'Failed') : 'Skipped'}
                                                                </div>
                                                            </div>
                                                            <div className="rounded-lg bg-gray-50 dark:bg-[#15171a] p-3">
                                                                <div className="text-gray-500 dark:text-gray-400">Rollback</div>
                                                                <div className="mt-1 font-bold text-gray-900 dark:text-gray-200">
                                                                    Attempted {boolLabel(rollback.attempted)} / Success {boolLabel(rollback.success)}
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
                                                            <div>Support: <span className="font-semibold text-gray-800 dark:text-gray-200">{supportPolicy.tier || 'unknown'} / {supportPolicy.readiness || 'unknown'}</span></div>
                                                            <div>Backup: <span className="font-semibold text-gray-800 dark:text-gray-200">{backup.id || 'n/a'}</span></div>
                                                            <div>Rollback ref: <span className="font-semibold text-gray-800 dark:text-gray-200">{rollback.ref || 'n/a'}</span></div>
                                                            <div>Rollback prepared: <span className="font-semibold text-gray-800 dark:text-gray-200">{boolLabel(rollback.prepared)}</span></div>
                                                        </div>
                                                        {Array.isArray(preCheck.rows) && preCheck.rows.length > 0 && (
                                                            <div className="rounded-lg border border-gray-200 dark:border-gray-800 p-3 text-xs text-gray-600 dark:text-gray-400">
                                                                <div className="font-bold text-gray-700 dark:text-gray-300 mb-2">Pre-check Results</div>
                                                                <div className="space-y-1">
                                                                    {preCheck.rows.map((row, rowIdx) => (
                                                                        <div key={`${res.device_id || idx}-pre-${rowIdx}`}>
                                                                            {row.command}: {row.ok ? 'ok' : 'failed'}
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </div>
                                                        )}
                                                        {postCheck && (
                                                            <div className="rounded-lg border border-gray-200 dark:border-gray-800 p-3 text-xs text-gray-600 dark:text-gray-400">
                                                                <div className="font-bold text-gray-700 dark:text-gray-300 mb-2">Post-check Results</div>
                                                                <div className="space-y-1">
                                                                    {postCheck.command && <div>Selected command: {postCheck.command}</div>}
                                                                    {Array.isArray(postCheck.tried) && postCheck.tried.map((row, rowIdx) => (
                                                                        <div key={`${res.device_id || idx}-post-${rowIdx}`}>
                                                                            {row.command}: {row.ok ? 'ok' : 'failed'}
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </div>
                                                        )}
                                                        {(rollback.output || rollback.error) && (
                                                            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#15171a] p-3 text-xs text-gray-600 dark:text-gray-400">
                                                                <div className="font-bold text-gray-700 dark:text-gray-300 mb-2">Rollback Output</div>
                                                                <pre className="whitespace-pre-wrap font-mono text-[11px]">{rollback.output || rollback.error}</pre>
                                                            </div>
                                                        )}
                                                        {(res.output || res.message || res.error) && (
                                                            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#15171a] p-3 text-xs text-gray-600 dark:text-gray-400">
                                                                <div className="font-bold text-gray-700 dark:text-gray-300 mb-2">Execution Output</div>
                                                                <pre className="whitespace-pre-wrap font-mono text-[11px]">{res.output || res.message || res.error}</pre>
                                                            </div>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Modal Footer */}
                        <div className="p-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#202327] flex justify-end gap-3 items-center">
                            <button
                                onClick={() => setIsDeployModalOpen(false)}
                                disabled={deploying || dryRunning || approvalSubmitting}
                                className="px-6 py-3 text-sm font-bold text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition-colors disabled:opacity-50 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg"
                            >
                                Close
                            </button>
                            {!deployResult && (
                                <button
                                    onClick={handleExecuteDryRun}
                                    disabled={dryRunning || deploying || selectedDeviceIds.length === 0}
                                    className={`px-6 py-3 rounded-lg text-sm font-bold text-white flex items-center gap-2 shadow-lg transition-all
                    ${dryRunning || deploying || selectedDeviceIds.length === 0
                                            ? 'bg-gray-400 dark:bg-gray-600 cursor-not-allowed opacity-50'
                                            : 'bg-sky-600 hover:bg-sky-500 shadow-sky-500/20 hover:shadow-sky-500/40 transform hover:-translate-y-0.5'}`}
                                >
                                    {dryRunning ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} />}
                                    {dryRunning ? 'Dry-Running...' : 'Dry-Run (Diff)'}
                                </button>
                            )}
                            {!deployResult && (
                                <button
                                    onClick={handleSmartDeploy}
                                    disabled={deploying || dryRunning || approvalSubmitting || selectedDeviceIds.length === 0 || smartRouteIsBlocked}
                                    className={`px-6 py-3 rounded-lg text-sm font-bold text-white flex items-center gap-2 shadow-lg transition-all
                    ${deploying || dryRunning || approvalSubmitting || selectedDeviceIds.length === 0 || smartRouteIsBlocked
                                            ? 'bg-gray-400 dark:bg-gray-600 cursor-not-allowed opacity-50'
                                            : smartRouteIsApproval
                                                ? 'bg-amber-600 hover:bg-amber-500 shadow-amber-500/20 hover:shadow-amber-500/40 transform hover:-translate-y-0.5'
                                                : 'bg-green-600 hover:bg-green-500 shadow-green-500/20 hover:shadow-green-500/40 transform hover:-translate-y-0.5'}`}
                                >
                                    {smartSubmitting ? <RefreshCw size={16} className="animate-spin" /> : smartRouteIsApproval ? <CheckCircle size={16} /> : <Play size={16} />}
                                    {smartSubmitting ? 'Processing...' : smartActionLabel}
                                </button>
                            )}
                            {!deployResult && (
                                <div className="self-center text-xs text-gray-500 dark:text-gray-400">
                                    {effectiveChangePlan?.reason || templateDeployPolicy.reason}
                                </div>
                            )}
                        </div>

                    </div>
                </div>
            )}

            {/* 4. Snippet Import Modal (New) */}
            {isSnippetModalOpen && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 dark:bg-black/80 backdrop-blur-sm animate-fade-in">
                    <div data-testid="config-snippet-modal" className="bg-white dark:bg-[#1b1d1f] w-full max-w-2xl rounded-2xl border border-gray-200 dark:border-gray-800 shadow-2xl overflow-hidden animate-scale-in">
                        <div className="p-6 border-b border-gray-200 dark:border-gray-800 flex justify-between items-center bg-gray-50 dark:bg-[#202327]">
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                <Layers className="text-purple-500 dark:text-purple-400" /> Merge Snippet
                            </h3>
                            <button data-testid="config-close-snippet-modal" onClick={() => setIsSnippetModalOpen(false)}><X className="text-gray-400 hover:text-gray-900 dark:hover:text-white" /></button>
                        </div>
                        <div className="p-6 bg-white dark:bg-[#0e1012] max-h-[60vh] overflow-y-auto custom-scrollbar">
                            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Select a template to append to your current configuration:</p>

                            <div className="grid grid-cols-1 gap-2">
                                {templates.map(tmpl => (
                                    <div
                                        key={tmpl.id}
                                        onClick={() => handleImportSnippet(tmpl.content, tmpl.name)}
                                        className="p-4 bg-gray-50 dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 hover:border-purple-400 dark:hover:border-purple-500/50 hover:bg-purple-50 dark:hover:bg-purple-900/10 rounded-xl cursor-pointer transition-all group"
                                    >
                                        <div className="flex justify-between items-center">
                                            <div className="font-bold text-gray-900 dark:text-gray-200 group-hover:text-purple-600 dark:group-hover:text-purple-300">{tmpl.name}</div>
                                            <div className="text-[10px] bg-gray-200 dark:bg-gray-800 px-2 py-1 rounded text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-700">{tmpl.category}</div>
                                        </div>
                                        <div className="text-xs text-gray-500 dark:text-gray-600 mt-2 font-mono truncate opacity-60">
                                            {tmpl.content.slice(0, 60)}...
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}

        </div>
    );
};

export default ConfigPage;
