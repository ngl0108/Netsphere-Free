import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApprovalService, ComplianceService, DeviceService, JobService, StateHistoryService } from '../../api/services';
import { useToast } from '../../context/ToastContext';
import { useAuth } from '../../context/AuthContext';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import { InlineEmpty, InlineLoading, SectionCard } from '../common/PageState';
import {
    buildDevicePath,
    buildGrafanaAlertingCenterUrl,
    buildGrafanaFleetHealthUrl,
    buildObservabilityPath,
    buildTopologyPath,
} from '../../utils/observabilityLinks';
import { buildCloudIntentPath } from '../../utils/cloudIntentLinks';
import {
    getOperationalStatusBadgeClass,
    getOperationalStatusHint,
    getOperationalStatusLabel,
} from '../../utils/deviceStatusTone';
import {
    CheckCircle, XCircle, Clock, FileText, User,
    ShieldAlert, Activity, GitBranch, ExternalLink, Download, Cloud, Camera, TimerReset
} from 'lucide-react';

const collectApprovalDeviceIds = (payload) => {
    const values = [];
    const pushValue = (value) => {
        if (value === undefined || value === null || value === '') return;
        values.push(String(value).trim());
    };
    const pushList = (items) => {
        if (!Array.isArray(items)) return;
        items.forEach((item) => pushValue(item));
    };
    pushValue(payload?.device_id);
    pushList(payload?.device_ids);
    pushList(payload?.spine_ids);
    pushList(payload?.leaf_ids);
    return [...new Set(values.filter(Boolean))];
};

const parseFilename = (contentDisposition) => {
    const value = String(contentDisposition || '');
    const match = value.match(/filename="?([^"]+)"?/i);
    return match ? match[1] : null;
};

const downloadBlob = (data, filename, contentType) => {
    const blob = data instanceof Blob ? data : new Blob([data], { type: contentType || 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename || 'download';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
};

const collectExecutionRows = (req) => {
    const executionResult = req?.payload?.execution_result;
    if (!executionResult || typeof executionResult !== 'object') return [];
    if (Array.isArray(executionResult.summary)) return executionResult.summary;
    if (Array.isArray(executionResult.results)) return executionResult.results;
    if (executionResult.execution_actions && typeof executionResult.execution_actions === 'object' && Array.isArray(executionResult.execution_actions.results)) {
        return executionResult.execution_actions.results;
    }
    return [];
};

const collectCloudIntentExecutionRow = (req) => {
    const rows = collectExecutionRows(req);
    return rows.find((row) => String(row?.type || '').trim().toLowerCase() === 'cloud_intent_apply') || null;
};

const ApprovalPage = () => {
    useLocaleRerender();
    const { toast } = useToast();
    const { user } = useAuth();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const [requests, setRequests] = useState([]);
    const [loading, setLoading] = useState(false);
    const [filterStatus, setFilterStatus] = useState('pending');
    const [selectedReq, setSelectedReq] = useState(null);
    const [comment, setComment] = useState('');
    const [actionLoading, setActionLoading] = useState(false);
    const [driftDetails, setDriftDetails] = useState(null);
    const [driftLoading, setDriftLoading] = useState(false);
    const [jobStatus, setJobStatus] = useState(null);
    const [jobLoading, setJobLoading] = useState(false);
    const [devices, setDevices] = useState([]);
    const [evidenceLoading, setEvidenceLoading] = useState(false);
    const [serviceImpact, setServiceImpact] = useState(null);
    const [serviceImpactLoading, setServiceImpactLoading] = useState(false);
    const [stateHistoryAction, setStateHistoryAction] = useState('');
    const focusRequestId = Number(searchParams.get('focusRequestId') || 0);

    useEffect(() => {
        loadRequests();
    }, [filterStatus]);

    useEffect(() => {
        const loadDevices = async () => {
            try {
                const res = await DeviceService.getAll();
                setDevices(Array.isArray(res?.data) ? res.data : []);
            } catch (err) {
                setDevices([]);
            }
        };
        loadDevices();
    }, []);

    useEffect(() => {
        const loadFocusedRequest = async () => {
            if (focusRequestId <= 0) return;
            try {
                const res = await ApprovalService.getRequest(focusRequestId);
                const requestBody = res?.data || null;
                if (!requestBody) return;
                if (requestBody?.status && requestBody.status !== filterStatus) {
                    setFilterStatus(String(requestBody.status));
                }
                setSelectedReq(requestBody);
            } catch (err) {
                console.error('Failed to load focused approval request', err);
            }
        };
        void loadFocusedRequest();
    }, [focusRequestId]);

    useEffect(() => {
        const loadExtras = async () => {
            setDriftDetails(null);
            setJobStatus(null);
            setServiceImpact(null);
            if (!selectedReq) return;

            const p = selectedReq.payload || {};
            if (selectedReq.request_type === 'config_drift_remediate' && p.device_id) {
                setDriftLoading(true);
                try {
                    const res = await ComplianceService.checkDrift(p.device_id);
                    setDriftDetails(res.data);
                } catch (e) {
                    setDriftDetails({ status: 'error', message: t('approval_failed_load_drift', 'Failed to load drift details') });
                } finally {
                    setDriftLoading(false);
                }
            }

            if (p.job_id) {
                setJobLoading(true);
                try {
                    const res = await JobService.getStatus(p.job_id);
                    setJobStatus(res.data);
                } catch (e) {
                    setJobStatus({ error: t('approval_failed_load_job_status', 'Failed to load job status') });
                } finally {
                    setJobLoading(false);
                }
            }
        };
        loadExtras();
    }, [selectedReq]);

    useEffect(() => {
        const loadServiceImpact = async () => {
            const requestId = Number(selectedReq?.id || 0);
            if (requestId <= 0) {
                setServiceImpact(null);
                return;
            }
            setServiceImpactLoading(true);
            try {
                const res = await ApprovalService.getServiceImpact(requestId);
                setServiceImpact(res?.data || null);
            } catch (err) {
                console.error('Failed to load approval service impact', err);
                setServiceImpact(null);
            } finally {
                setServiceImpactLoading(false);
            }
        };
        void loadServiceImpact();
    }, [selectedReq?.id]);

    const loadRequests = async () => {
        setLoading(true);
        try {
            const res = await ApprovalService.getRequests({ status: filterStatus });
            setRequests(res.data);
        } catch (err) {
            console.error("Failed to load requests", err);
        } finally {
            setLoading(false);
        }
    };

    const handleAction = async (type) => { // type: 'approve' | 'reject'
        if (!selectedReq) return;
        if (!window.confirm(t('approval_confirm_action', `Are you sure you want to ${type} this request?`))) return;

        setActionLoading(true);
        try {
            if (type === 'approve') {
                await ApprovalService.approve(selectedReq.id, comment);
            } else {
                await ApprovalService.reject(selectedReq.id, comment);
            }
            setSelectedReq(null);
            setComment('');
            loadRequests();
        } catch (err) {
            toast.error(`${t('approval_action_failed', 'Action failed')}: ${err.response?.data?.detail || err.message}`);
        } finally {
            setActionLoading(false);
        }
    };

    const roleLabel = (() => {
        const roleKey = String(user?.role || '').trim().toLowerCase();
        if (roleKey === 'admin') return t('role_admin', 'Administrator');
        if (roleKey === 'operator') return t('role_operator', 'Operator');
        if (roleKey === 'viewer') return t('role_viewer', 'Viewer');
        return t('common_unknown', 'Unknown');
    })();

    const roleApprovalCopy = (() => {
        const roleKey = String(user?.role || '').trim().toLowerCase();
        if (roleKey === 'admin') {
            return t(
                'approval_access_desc_admin',
                'Administrators review change scope, keep approval policy aligned, and follow verification, rollback, and evidence trails before allowing execution.',
            );
        }
        if (roleKey === 'operator') {
            return t(
                'approval_access_desc_operator',
                'Operators review requests, approve guarded changes, and use topology, observability, and evidence links to validate operational impact.',
            );
        }
        return t(
            'approval_access_desc_viewer',
            'Viewers can inspect approval context and evidence, but approval decisions and execution actions stay restricted.',
        );
    })();

    const handleDownloadEvidence = async () => {
        if (!selectedReq) return;
        setEvidenceLoading(true);
        try {
            const res = await ApprovalService.downloadEvidencePackage(selectedReq.id);
            const filename = parseFilename(res?.headers?.['content-disposition']) || `approval_evidence_${selectedReq.id}.zip`;
            downloadBlob(res?.data, filename, res?.headers?.['content-type']);
            toast.success(t('approval_evidence_downloaded', 'Evidence package downloaded.'));
        } catch (err) {
            toast.error(`${t('approval_evidence_download_failed', 'Failed to download evidence package')}: ${err.response?.data?.detail || err.message}`);
        } finally {
            setEvidenceLoading(false);
        }
    };

    const openStateHistoryForApproval = async ({ capture = false } = {}) => {
        const requestId = Number(selectedReq?.id || 0);
        if (requestId <= 0) return;

        const params = new URLSearchParams();
        params.set('focusRequestId', String(requestId));
        params.set('entry', 'approval');

        if (capture) {
            setStateHistoryAction('capture');
            try {
                const requestTypeLabel = getRequestTypeMeta(selectedReq?.request_type).label;
                const res = await StateHistoryService.createSnapshot({
                    label: t('approval_state_history_label_fmt', 'Approval #{value} review').replace('{value}', String(requestId)),
                    note: `${requestTypeLabel} · ${String(selectedReq?.title || '').trim() || t('approval_center', 'Approval Center')}`,
                });
                const createdId = Number(res?.data?.event_log_id || 0);
                if (createdId > 0) params.set('focusSnapshotId', String(createdId));
                toast.success(t('approval_state_history_capture_success', 'State snapshot captured from this approval review.'));
            } catch (err) {
                toast.error(`${t('approval_state_history_capture_failed', 'Failed to capture state history snapshot')}: ${err?.response?.data?.detail || err?.message}`);
                return;
            } finally {
                setStateHistoryAction('');
            }
        }

        navigate(`/state-history?${params.toString()}`);
    };

    const statusColors = {
        pending: 'bg-yellow-100 text-yellow-700 border-yellow-200',
        approved: 'bg-green-100 text-green-700 border-green-200',
        rejected: 'bg-red-100 text-red-700 border-red-200',
        cancelled: 'bg-gray-100 text-gray-700 border-gray-200',
    };
    const requestTypeMeta = {
        config_drift_remediate: { label: 'Drift Remediate', className: 'bg-indigo-100 text-indigo-700 border-indigo-200' },
        template_deploy: { label: 'Template Deploy', className: 'bg-cyan-100 text-cyan-700 border-cyan-200' },
        fabric_deploy: { label: 'Fabric Deploy', className: 'bg-fuchsia-100 text-fuchsia-700 border-fuchsia-200' },
        intent_apply: { label: 'Cloud Intent', className: 'bg-sky-100 text-sky-700 border-sky-200' },
    };
    const getRequestTypeMeta = (requestType) => (
        requestTypeMeta[String(requestType || '').trim()] || {
            label: String(requestType || 'generic'),
            className: 'bg-gray-100 text-gray-700 border-gray-200',
        }
    );
    const normalizeExecutionKey = (value) => String(value || '').trim().toLowerCase().replace(/\s+/g, '_');
    const formatExecutionLabel = (value) => {
        const key = normalizeExecutionKey(value);
        if (!key) return '-';
        const labelMap = {
            ok: 'ok',
            success: 'success',
            failed: 'failed',
            precheck_failed: 'pre-check failed',
            pre_check_failed: 'pre-check failed',
            postcheck_failed: 'post-check failed',
            post_check_failed: 'post-check failed',
            skipped_wave_halt: 'skipped (wave halt)',
            skipped_idempotent: 'skipped (idempotent)',
        };
        return labelMap[key] || key.replace(/_/g, ' ');
    };
    const summarizeExecution = (req) => {
        const result = req?.payload?.execution_result;
        if (!result || typeof result !== 'object') return null;

        const summary = result.summary;
        if (Array.isArray(summary)) {
            const total = summary.length;
            const success = summary.filter((r) => String(r?.status || '').toLowerCase() === 'success').length;
            const failed = summary.filter((r) => String(r?.status || '').toLowerCase().includes('fail')).length;
            const skipped = summary.filter((r) => String(r?.status || '').toLowerCase().startsWith('skipped')).length;
            return `total ${total}, success ${success}, failed ${failed}, skipped ${skipped}`;
        }
        if (summary && typeof summary === 'object') {
            const total = Number(summary.total || 0);
            const success = Number(summary.success || 0);
            const failed = Number(summary.failed || 0);
            const skipped = Number(summary.skipped || 0);
            return `total ${total}, success ${success}, failed ${failed}, skipped ${skipped}`;
        }
        return null;
    };
    const extractExecutionDiagnostics = (req) => {
        const rows = collectExecutionRows(req);
        if (rows.length === 0) return null;

        let precheckFailed = 0;
        let postcheckFailed = 0;
        let rollbackAttempted = 0;
        let rollbackSuccess = 0;
        const causeCounts = {};

        rows.forEach((row) => {
            const status = normalizeExecutionKey(row?.status || row?.result?.status);
            if (status === 'precheck_failed' || status === 'pre_check_failed') {
                precheckFailed += 1;
            }
            if (status === 'postcheck_failed' || status === 'post_check_failed') {
                postcheckFailed += 1;
            }

            const postCheckFlag = row?.post_check_failed ?? row?.result?.post_check_failed;
            if (postCheckFlag && !(status === 'postcheck_failed' || status === 'post_check_failed')) {
                postcheckFailed += 1;
            }

            const cause = normalizeExecutionKey(row?.failure_cause || row?.result?.failure_cause);
            if (cause) {
                causeCounts[cause] = Number(causeCounts[cause] || 0) + 1;
            }

            const rollbackAttempt = row?.rollback_attempted ?? row?.result?.rollback_attempted;
            if (rollbackAttempt) rollbackAttempted += 1;
            const rollbackOk = row?.rollback_success ?? row?.result?.rollback_success;
            if (rollbackOk) rollbackSuccess += 1;
        });

        const topCauses = Object.entries(causeCounts)
            .sort((a, b) => Number(b[1]) - Number(a[1]))
            .slice(0, 3)
            .map(([cause, count]) => ({ cause, count: Number(count || 0) }));

        return {
            precheckFailed,
            postcheckFailed,
            rollbackAttempted,
            rollbackSuccess,
            topCauses,
        };
    };
    const selectedExecutionDiagnostics = extractExecutionDiagnostics(selectedReq);
    const selectedCloudExecutionRow = React.useMemo(() => collectCloudIntentExecutionRow(selectedReq), [selectedReq]);
    const selectedExecutionStages = React.useMemo(() => {
        const payload = selectedReq?.payload || {};
        const executionStatus = normalizeExecutionKey(payload?.execution_status);
        const executionResult = payload?.execution_result && typeof payload.execution_result === 'object'
            ? payload.execution_result
            : {};
        const summaryRows = collectExecutionRows(selectedReq);
        const diagnostics = selectedExecutionDiagnostics || {
            precheckFailed: 0,
            postcheckFailed: 0,
            rollbackAttempted: 0,
            rollbackSuccess: 0,
            topCauses: [],
        };
        const rollbackEnabled = payload?.rollback_on_failure !== false;
        const postCheckEnabled = payload?.post_check_enabled !== false;
        const hasEvidence = Boolean(payload?.execution_status || payload?.execution_result || payload?.execution_trace);

        const stage = (key, title, status, description, icon) => ({
            key,
            title,
            status,
            description,
            icon,
        });

        const dispatchStatus = (() => {
            if (!executionStatus) return 'pending';
            if (executionStatus === 'dispatch_failed') return 'dispatch_failed';
            if (['dispatching', 'queued', 'running', 'in_progress'].includes(executionStatus)) return executionStatus;
            if (['executed', 'completed', 'success', 'ok'].includes(executionStatus)) return 'success';
            if (['failed', 'error', 'pre_check_failed', 'precheck_failed', 'post_check_failed', 'postcheck_failed'].includes(executionStatus)) return executionStatus;
            return executionStatus;
        })();

        const verificationStatus = (() => {
            if (!postCheckEnabled) return 'disabled';
            if (diagnostics.postcheckFailed > 0) return 'post_check_failed';
            if (summaryRows.length > 0) return 'success';
            if (['dispatching', 'queued', 'running', 'in_progress'].includes(dispatchStatus)) return 'in_progress';
            return 'pending';
        })();

        const rollbackStatus = (() => {
            if (!rollbackEnabled) return 'disabled';
            if (diagnostics.rollbackAttempted > 0 && diagnostics.rollbackSuccess >= diagnostics.rollbackAttempted) return 'success';
            if (diagnostics.rollbackAttempted > 0 && diagnostics.rollbackSuccess < diagnostics.rollbackAttempted) return 'failed';
            if (diagnostics.postcheckFailed > 0) return 'warning';
            if (summaryRows.length > 0) return 'healthy';
            if (['dispatching', 'queued', 'running', 'in_progress'].includes(dispatchStatus)) return 'in_progress';
            return 'pending';
        })();

        const evidenceStatus = hasEvidence
            ? 'healthy'
            : (['dispatching', 'queued', 'running', 'in_progress'].includes(dispatchStatus) ? 'in_progress' : 'pending');

        return [
            stage(
                'dispatch',
                t('approval_stage_dispatch', 'Dispatch'),
                dispatchStatus,
                executionStatus === 'dispatch_failed'
                    ? t('approval_stage_dispatch_failed_desc', 'The execution request could not be dispatched. Review the error and operator notes before retrying.')
                    : ['dispatching', 'queued', 'running', 'in_progress'].includes(dispatchStatus)
                        ? t('approval_stage_dispatch_progress_desc', 'The request has been accepted and is waiting for execution workers or live completion updates.')
                        : t('approval_stage_dispatch_ready_desc', 'The approved request has been handed off to the execution pipeline.'),
                Clock,
            ),
            stage(
                'verification',
                t('approval_stage_verification', 'Verification'),
                verificationStatus,
                !postCheckEnabled
                    ? t('approval_stage_verification_disabled_desc', 'Post-check verification is disabled for this request.')
                    : diagnostics.postcheckFailed > 0
                        ? t('approval_stage_verification_failed_desc', 'Post-check verification reported blocking failures and escalated the change for rollback review.')
                        : summaryRows.length > 0
                            ? t('approval_stage_verification_success_desc', 'Execution rows include completed verification results for the approved change.')
                            : t('approval_stage_verification_pending_desc', 'Verification results will appear here once execution rows are recorded.'),
                CheckCircle,
            ),
            stage(
                'rollback',
                t('approval_stage_rollback', 'Rollback'),
                rollbackStatus,
                !rollbackEnabled
                    ? t('approval_stage_rollback_disabled_desc', 'Automatic rollback is disabled for this change request.')
                    : diagnostics.rollbackAttempted > 0 && diagnostics.rollbackSuccess >= diagnostics.rollbackAttempted
                        ? t('approval_stage_rollback_success_desc', 'Automatic rollback completed successfully after a failed validation step.')
                        : diagnostics.rollbackAttempted > 0
                            ? t('approval_stage_rollback_partial_desc', 'Rollback was attempted, but at least one execution row still requires operator review.')
                            : diagnostics.postcheckFailed > 0
                                ? t('approval_stage_rollback_pending_desc', 'Post-check failed, but no automatic rollback result is recorded yet.')
                                : t('approval_stage_rollback_not_needed_desc', 'No rollback was needed for the currently recorded execution results.'),
                GitBranch,
            ),
            stage(
                'evidence',
                t('approval_stage_evidence', 'Evidence'),
                evidenceStatus,
                hasEvidence
                    ? t('approval_stage_evidence_ready_desc', 'The operator evidence package is ready with request context, summaries, and execution traces.')
                    : t('approval_stage_evidence_pending_desc', 'Evidence will become downloadable as soon as execution metadata is stored.'),
                FileText,
            ),
        ];
    }, [selectedExecutionDiagnostics, selectedReq]);
    const selectedIntentPreview = React.useMemo(() => {
        if (selectedReq?.request_type !== 'intent_apply') return null;
        const payload = selectedReq?.payload || {};
        const preview = payload?.change_preview_summary && typeof payload.change_preview_summary === 'object'
            ? payload.change_preview_summary
            : {};
        const terraformPlan = payload?.terraform_plan_preview && typeof payload.terraform_plan_preview === 'object'
            ? payload.terraform_plan_preview
            : {};
        const simulationSnapshot = payload?.simulation_snapshot && typeof payload.simulation_snapshot === 'object'
            ? payload.simulation_snapshot
            : {};
        const cloudExecutionRow = collectCloudIntentExecutionRow(selectedReq);
        const postCheckPlan = terraformPlan?.post_check_plan && typeof terraformPlan.post_check_plan === 'object'
            ? terraformPlan.post_check_plan
            : null;
        const evidencePlan = terraformPlan?.evidence_plan && typeof terraformPlan.evidence_plan === 'object'
            ? terraformPlan.evidence_plan
            : null;
        const operationalGuardrails = simulationSnapshot?.operational_guardrails && typeof simulationSnapshot.operational_guardrails === 'object'
            ? simulationSnapshot.operational_guardrails
            : null;
        const preCheck = simulationSnapshot?.pre_check && typeof simulationSnapshot.pre_check === 'object'
            ? simulationSnapshot.pre_check
            : null;
        const beforeAfterCompare = simulationSnapshot?.before_after_compare && typeof simulationSnapshot.before_after_compare === 'object'
            ? simulationSnapshot.before_after_compare
            : null;
        return {
            riskScore: Number(preview?.risk_score ?? simulationSnapshot?.risk_score ?? 0),
            blastRadius: preview?.blast_radius || simulationSnapshot?.blast_radius || {},
            cloudScope: preview?.cloud_scope || simulationSnapshot?.cloud_scope || {},
            changeSummary: Array.isArray(preview?.change_summary)
                ? preview.change_summary
                : Array.isArray(simulationSnapshot?.change_summary)
                    ? simulationSnapshot.change_summary
                    : [],
            terraformPlan,
            postCheckPlan,
            evidencePlan,
            operationalGuardrails,
            preCheck,
            beforeAfterCompare,
            executionStatus: String(payload?.execution_status || '').trim(),
            postCheckResult: cloudExecutionRow?.post_check_result && typeof cloudExecutionRow.post_check_result === 'object'
                ? cloudExecutionRow.post_check_result
                : null,
            rollbackPlan: cloudExecutionRow?.rollback_plan && typeof cloudExecutionRow.rollback_plan === 'object'
                ? cloudExecutionRow.rollback_plan
                : (terraformPlan?.rollback_plan && typeof terraformPlan.rollback_plan === 'object' ? terraformPlan.rollback_plan : null),
            rollbackResult: cloudExecutionRow?.rollback_result && typeof cloudExecutionRow.rollback_result === 'object'
                ? cloudExecutionRow.rollback_result
                : null,
        };
    }, [selectedReq]);
    const selectedIntentImpact = React.useMemo(() => {
        if (!selectedIntentPreview) return null;
        const cloudScope = selectedIntentPreview.cloudScope && typeof selectedIntentPreview.cloudScope === 'object'
            ? selectedIntentPreview.cloudScope
            : {};
        const targetProviders = Array.isArray(cloudScope?.target_providers)
            ? cloudScope.target_providers.map((row) => String(row || '').trim().toLowerCase()).filter(Boolean)
            : [];
        const firstProvider = String(targetProviders[0] || '').trim().toLowerCase();
        const targetAccounts = Array.isArray(cloudScope?.target_accounts)
            ? cloudScope.target_accounts.map((row) => String(row || '').trim()).filter(Boolean)
            : [];
        const accountId = String(targetAccounts[0] || '').trim();
        const regionsByProvider = cloudScope?.regions_by_provider && typeof cloudScope.regions_by_provider === 'object'
            ? cloudScope.regions_by_provider
            : {};
        const providerRegions = firstProvider && Array.isArray(regionsByProvider[firstProvider]) ? regionsByProvider[firstProvider] : [];
        const specTargets = selectedReq?.payload?.spec?.targets && typeof selectedReq.payload.spec.targets === 'object'
            ? selectedReq.payload.spec.targets
            : {};
        const specRegions = Array.isArray(specTargets?.regions) ? specTargets.regions.map((row) => String(row || '').trim()).filter(Boolean) : [];
        const region = String(providerRegions[0] || specRegions[0] || '').trim();
        let resourceTypes = cloudScope?.resources_by_type && typeof cloudScope.resources_by_type === 'object'
            ? Object.keys(cloudScope.resources_by_type).filter(Boolean)
            : [];
        if (resourceTypes.length === 0) {
            resourceTypes = Array.isArray(specTargets?.resource_types)
                ? specTargets.resource_types.map((row) => String(row || '').trim()).filter(Boolean)
                : [];
        }
        const resourcesByType = cloudScope?.resources_by_type && typeof cloudScope.resources_by_type === 'object'
            ? Object.entries(cloudScope.resources_by_type)
                .map(([key, value]) => ({ key: String(key || '').trim(), count: Number(value || 0) }))
                .filter((row) => row.key)
                .sort((a, b) => (b.count - a.count) || a.key.localeCompare(b.key))
            : [];
        const focusResourceName = String(specTargets?.resource_name || '').trim();
        const focusResourceId = String(specTargets?.resource_id || '').trim();
        const topologyPath = buildTopologyPath({
            cloudProvider: firstProvider,
            cloudAccountId: accountId,
            cloudRegion: region,
            cloudResourceTypes: resourceTypes,
            cloudIntentImpact: true,
            focusCloudResourceId: focusResourceId,
            focusCloudResourceName: focusResourceName,
        });
        const cloudIntentPath = buildCloudIntentPath({
            provider: firstProvider,
            accountId,
            region,
            resourceTypes,
            resourceName: focusResourceName,
            resourceId: focusResourceId,
            source: 'approval',
        });
        return {
            provider: firstProvider,
            accountId,
            region,
            resourceTypes,
            resourcesByType,
            scopedResources: Number(cloudScope?.scoped_resources || 0),
            topologyPath,
            cloudIntentPath,
            cloudAccountsPath: accountId ? `/cloud/accounts?focusAccountId=${encodeURIComponent(accountId)}` : '/cloud/accounts',
        };
    }, [selectedIntentPreview, selectedReq]);
    const deviceById = React.useMemo(
        () => new Map((devices || []).map((device) => [String(device?.id), device])),
        [devices],
    );
    const approvalContext = React.useMemo(() => {
        const payload = selectedReq?.payload || {};
        const deviceIds = collectApprovalDeviceIds(payload);
        const linkedDevices = deviceIds
            .map((deviceId) => deviceById.get(String(deviceId)))
            .filter(Boolean);
        const primaryDeviceId = deviceIds[0] || null;
        const primaryDevice = primaryDeviceId ? deviceById.get(String(primaryDeviceId)) || null : null;
        const siteIds = [...new Set(
            linkedDevices
                .map((device) => device?.site_id)
                .filter((value) => value !== undefined && value !== null && String(value).trim() !== ''),
                )];
        const siteId = siteIds.length === 1
            ? siteIds[0]
            : (payload?.site_id !== undefined && payload?.site_id !== null && String(payload.site_id).trim() !== '' ? payload.site_id : null);
        const siteName = linkedDevices.find((device) => device?.site_name)?.site_name || payload?.site_name || null;
        return {
            deviceIds,
            deviceCount: deviceIds.length,
            primaryDeviceId,
            primaryDevice,
            siteId,
            siteName,
        };
    }, [deviceById, selectedReq]);
    const selectedApprovalServiceImpact = React.useMemo(() => {
        if (!serviceImpact || typeof serviceImpact !== 'object') return { summary: null, groups: [] };
        return {
            summary: serviceImpact.summary && typeof serviceImpact.summary === 'object' ? serviceImpact.summary : null,
            groups: Array.isArray(serviceImpact.groups) ? serviceImpact.groups : [],
        };
    }, [serviceImpact]);

    const renderDiff = (diffLines) => {
        if (!diffLines || diffLines.length === 0) return <div className="text-gray-500 italic p-4">{t('approval_no_diff_found', 'No differences found.')}</div>;
        return (
            <div className="font-mono text-xs overflow-x-auto bg-[#1e1e1e] text-gray-300 p-4 rounded-lg shadow-inner h-[360px] overflow-y-auto">
                {diffLines.map((line, idx) => {
                    let style = {};
                    if (line.startsWith('---') || line.startsWith('+++')) style = { color: '#888' };
                    else if (line.startsWith('@@')) style = { color: '#aaa', fontStyle: 'italic' };
                    else if (line.startsWith('+')) style = { backgroundColor: '#1e3a29', color: '#4ade80', display: 'block' };
                    else if (line.startsWith('-')) style = { backgroundColor: '#451e1e', color: '#f87171', display: 'block' };

                    return (
                        <div key={idx} style={style} className="whitespace-pre px-1 py-0.5">
                            {line}
                        </div>
                    );
                })}
            </div>
        );
    };

    return (
        <div className="p-3 sm:p-4 md:p-6 h-full min-h-0 flex flex-col bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white">

            {/* Header */}
            <div className="flex flex-col gap-3 lg:flex-row lg:justify-between lg:items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <ShieldAlert className="text-blue-500" /> {t('approval_center', 'Approval Center')}
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">{t('approval_review_manage_desc', 'Review and manage change requests')}</p>
                </div>
                <div className="flex gap-2 flex-wrap">
                    {['pending', 'approved', 'rejected', 'all'].map(status => (
                        <button
                            key={status}
                            onClick={() => setFilterStatus(status === 'all' ? null : status)}
                            className={`h-10 px-4 inline-flex items-center rounded-lg text-sm font-medium capitalize transition-all ${(status === 'all' && !filterStatus) || filterStatus === status
                                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                                    : 'bg-white dark:bg-[#1b1d1f] text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-700'
                                }`}
                        >
                            {status === 'all' ? t('common_all', 'all') : t(`approval_status_${status}`, status)}
                        </button>
                    ))}
                </div>
            </div>

            <div className="mb-4 rounded-2xl border border-blue-200 dark:border-blue-900/40 bg-blue-50/80 dark:bg-blue-950/10 px-4 py-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                        <div className="text-sm font-black text-blue-900 dark:text-blue-100">
                            {t('approval_access_title', 'Approval and rollback boundary')}
                        </div>
                        <div className="mt-2 text-sm text-blue-800 dark:text-blue-200">
                            {roleApprovalCopy}
                        </div>
                    </div>
                    <div className="text-xs text-blue-700 dark:text-blue-300 shrink-0">
                        {t('approval_access_role_fmt', 'Current role: {role}').replace('{role}', roleLabel)}
                    </div>
                </div>
            </div>

            {/* Content Grid */}
            <div className="flex-1 min-h-0 flex flex-col xl:flex-row gap-6 overflow-hidden">

                {/* Request List */}
                <SectionCard className="w-full xl:w-[340px] xl:min-w-[320px] max-h-[38vh] xl:max-h-none flex flex-col overflow-hidden shadow-sm">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700 font-bold flex justify-between items-center">
                        <span>{t('approval_requests', 'Requests')}</span>
                        <span className="text-xs font-normal text-gray-500">{requests.length} {t('approval_items', 'items')}</span>
                    </div>

                    <div className="flex-1 overflow-y-auto p-2 space-y-2">
                        {loading ? (
                            <InlineLoading label={t('common_loading', 'Loading...')} className="p-8" />
                        ) : requests.length === 0 ? (
                            <InlineEmpty label={t('approval_no_requests_found', 'No requests found.')} className="p-8 text-sm" />
                        ) : (
                            requests.map(req => (
                                <div
                                    key={req.id}
                                    onClick={() => setSelectedReq(req)}
                                    className={`p-4 rounded-xl border cursor-pointer transition-all ${selectedReq?.id === req.id
                                            ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700 ring-1 ring-blue-300 dark:ring-blue-700'
                                            : 'bg-white dark:bg-[#25282c] border-gray-100 dark:border-gray-700 hover:border-blue-200 dark:hover:border-blue-800'
                                        }`}
                                >
                                    <div className="flex justify-between items-start mb-2">
                                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${statusColors[req.status]}`}>
                                            {req.status}
                                        </span>
                                        <span className="text-xs text-gray-400 flex items-center gap-1">
                                            <Clock size={10} /> {new Date(req.created_at).toLocaleDateString()}
                                        </span>
                                    </div>
                                    <h3 className="font-bold text-sm mb-1 line-clamp-1">{req.title}</h3>
                                    <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
                                        <User size={12} /> {req.requester_name || `User #${req.requester_id}`}
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${getRequestTypeMeta(req.request_type).className}`}>
                                            {getRequestTypeMeta(req.request_type).label}
                                        </span>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </SectionCard>

                {/* Detail View */}
                <SectionCard className="flex-1 min-w-0 flex flex-col overflow-hidden shadow-sm relative">
                    {selectedReq ? (
                        <div className="flex-1 flex flex-col h-full overflow-hidden">
                            {/* Detail Header */}
                            <div className="p-6 border-b border-gray-200 dark:border-gray-700 shrink-0">
                                <div className="flex flex-col gap-4 xl:flex-row xl:justify-between xl:items-start">
                                    <div>
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className={`px-2 py-1 rounded-md text-xs font-bold uppercase border ${statusColors[selectedReq.status]}`}>
                                                {selectedReq.status}
                                            </span>
                                            <span className={`px-2 py-1 rounded-md text-xs font-bold border ${getRequestTypeMeta(selectedReq.request_type).className}`}>
                                                {getRequestTypeMeta(selectedReq.request_type).label}
                                            </span>
                                            <span className="text-xs text-gray-500">ID: #{selectedReq.id}</span>
                                        </div>
                                        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">{selectedReq.title}</h2>
                                        <p className="text-gray-600 dark:text-gray-400 text-sm whitespace-pre-wrap">{selectedReq.description || t('layout_no_description', 'No description')}</p>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-sm font-medium text-gray-900 dark:text-white mb-1">{t('approval_requested_by', 'Requested by')}</div>
                                        <div className="flex items-center xl:justify-end gap-2 text-sm text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-black/20 px-3 py-1.5 rounded-lg border border-gray-100 dark:border-gray-800">
                                            <User size={14} />
                                            {selectedReq.requester_name}
                                        </div>
                                        <div className="mt-3 flex flex-wrap justify-end gap-2">
                                            <button
                                                type="button"
                                                data-testid="approval-open-state-history"
                                                onClick={() => openStateHistoryForApproval()}
                                                className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-[#202326] border border-gray-200 dark:border-gray-700 text-xs font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
                                            >
                                                <TimerReset size={14} />
                                                {t('approval_open_state_history', 'Open State History')}
                                            </button>
                                            <button
                                                type="button"
                                                data-testid="approval-capture-state-history"
                                                onClick={() => openStateHistoryForApproval({ capture: true })}
                                                disabled={stateHistoryAction === 'capture'}
                                                className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold ${
                                                    stateHistoryAction === 'capture'
                                                        ? 'bg-gray-200 dark:bg-gray-800 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                                                        : 'bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-gray-100 text-white dark:text-slate-900'
                                                }`}
                                            >
                                                <Camera size={14} />
                                                {stateHistoryAction === 'capture'
                                                    ? t('approval_state_history_capturing', 'Capturing...')
                                                    : t('approval_capture_state_history', 'Capture Snapshot')}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Payload Viewer */}
                            <div className="flex-1 overflow-y-auto p-6 bg-gray-50/50 dark:bg-black/5">
                                <h3 className="font-bold text-sm text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                                    <FileText size={16} /> {t('approval_request_payload', 'Request Payload')}
                                </h3>
                                <div className="bg-[#1e1e1e] rounded-lg p-4 font-mono text-xs text-gray-300 overflow-x-auto shadow-inner border border-gray-700">
                                    <pre>{JSON.stringify(selectedReq.payload, null, 2)}</pre>
                                </div>

                                {(approvalContext.primaryDeviceId || approvalContext.siteId) && (
                                    <div className="mt-6 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#202326] p-4">
                                        <div className="flex items-start justify-between gap-3 mb-3">
                                            <div>
                                                <h3 className="font-bold text-sm text-gray-700 dark:text-gray-300 flex items-center gap-2">
                                                    <Activity size={16} /> {t('approval_operational_context', 'Operational Context')}
                                                </h3>
                                                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                                    {approvalContext.primaryDevice
                                                        ? `${approvalContext.primaryDevice.name || `#${approvalContext.primaryDeviceId}`} · ${approvalContext.primaryDevice.ip_address || ''}`.trim()
                                                        : (approvalContext.deviceCount > 0
                                                            ? `${approvalContext.deviceCount} ${t('devices_col_device', 'Device').toLowerCase()}${approvalContext.deviceCount > 1 ? 's' : ''}`
                                                            : t('approval_context_no_device', 'No linked device context detected.'))}
                                                </p>
                                            </div>
                                            {(approvalContext.siteName || approvalContext.siteId) && (
                                                <span className="px-2 py-1 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                                                    {approvalContext.siteName || `Site ${approvalContext.siteId}`}
                                                </span>
                                            )}
                                        </div>
                                        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2">
                                            {approvalContext.primaryDeviceId && (
                                                <Link
                                                    data-testid="approval-open-device"
                                                    to={buildDevicePath(approvalContext.primaryDeviceId)}
                                                    className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 dark:bg-black/20 dark:hover:bg-black/30 border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-800 dark:text-gray-100"
                                                >
                                                    <Activity size={14} /> {t('approval_open_device', 'Open Device')}
                                                </Link>
                                            )}
                                            {approvalContext.siteId && (
                                                <Link
                                                    data-testid="approval-open-topology"
                                                    to={buildTopologyPath({ siteId: approvalContext.siteId })}
                                                    className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 dark:bg-black/20 dark:hover:bg-black/30 border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-800 dark:text-gray-100"
                                                >
                                                    <GitBranch size={14} /> {t('approval_open_topology', 'Open Topology')}
                                                </Link>
                                            )}
                                            {approvalContext.primaryDeviceId && (
                                                <Link
                                                    data-testid="approval-open-observability"
                                                    to={buildObservabilityPath({ deviceId: approvalContext.primaryDeviceId, siteId: approvalContext.siteId })}
                                                    className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 dark:bg-black/20 dark:hover:bg-black/30 border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-800 dark:text-gray-100"
                                                >
                                                    <Activity size={14} /> {t('approval_open_observability', 'Open Observability')}
                                                </Link>
                                            )}
                                            {(approvalContext.primaryDeviceId || approvalContext.siteId) && (
                                                <a
                                                    data-testid="approval-open-grafana"
                                                    href={buildGrafanaFleetHealthUrl({ deviceId: approvalContext.primaryDeviceId, siteId: approvalContext.siteId })}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 border border-blue-500 text-sm font-medium text-white"
                                                >
                                                    <ExternalLink size={14} /> {t('approval_open_grafana', 'Open Grafana')}
                                                </a>
                                            )}
                                        </div>
                                        {selectedReq?.payload?.execution_status && (
                                            <div className="mt-3">
                                                <a
                                                    data-testid="approval-open-alert-dashboard"
                                                    href={buildGrafanaAlertingCenterUrl({ deviceId: approvalContext.primaryDeviceId, siteId: approvalContext.siteId })}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="inline-flex items-center gap-2 text-xs font-semibold text-blue-600 dark:text-blue-300 hover:text-blue-500"
                                                >
                                                    <ExternalLink size={12} /> {t('approval_open_alert_dashboard', 'Open Alert Dashboard')}
                                                </a>
                                            </div>
                                        )}
                                    </div>
                                )}

                                <div className="mt-6 rounded-xl border border-cyan-200 dark:border-cyan-900/40 bg-cyan-50/70 dark:bg-cyan-950/10 p-4 space-y-3">
                                    <div className="flex flex-wrap items-start justify-between gap-3">
                                        <div>
                                            <h3 className="font-bold text-sm text-gray-800 dark:text-gray-100 flex items-center gap-2">
                                                <Activity size={16} /> {t('approval_service_impact_title', 'Service Impact')}
                                            </h3>
                                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                                {t('approval_service_impact_desc', 'Translate request scope into mapped business services before you approve, rollback, or collect evidence.')}
                                            </p>
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            <Link
                                                to="/service-groups"
                                                className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-[#0e1012] hover:bg-gray-100 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-700 dark:text-gray-300"
                                            >
                                                <Cloud size={14} /> {t('approval_open_service_groups', 'Open Service Groups')}
                                            </Link>
                                            {selectedApprovalServiceImpact.groups[0] && (
                                                <Link
                                                    to={`/topology?serviceOverlay=1&serviceGroupId=${encodeURIComponent(String(selectedApprovalServiceImpact.groups[0].id))}`}
                                                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-[#0e1012] hover:bg-gray-100 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-700 dark:text-gray-300"
                                                >
                                                    <GitBranch size={14} /> {t('approval_open_service_impact_map', 'Open Service Map')}
                                                </Link>
                                            )}
                                        </div>
                                    </div>

                                    {serviceImpactLoading ? (
                                        <div className="text-sm text-gray-500 dark:text-gray-400">
                                            {t('approval_service_impact_loading', 'Loading service impact...')}
                                        </div>
                                    ) : selectedApprovalServiceImpact.groups.length > 0 ? (
                                        <>
                                            <div className="grid grid-cols-2 xl:grid-cols-4 gap-2">
                                                <div className="rounded-lg border border-cyan-200 dark:border-cyan-900/40 bg-white dark:bg-[#14171a] p-3">
                                                    <div className="text-[10px] uppercase tracking-wide text-gray-500">{t('approval_service_impact_groups', 'Mapped Groups')}</div>
                                                    <div className="mt-1 text-lg font-bold text-cyan-700 dark:text-cyan-300">{Number(selectedApprovalServiceImpact.summary?.count || 0)}</div>
                                                </div>
                                                <div className="rounded-lg border border-cyan-200 dark:border-cyan-900/40 bg-white dark:bg-[#14171a] p-3">
                                                    <div className="text-[10px] uppercase tracking-wide text-gray-500">{t('approval_service_impact_primary', 'Primary Service')}</div>
                                                    <div className="mt-1 text-sm font-semibold text-gray-800 dark:text-gray-100">{selectedApprovalServiceImpact.summary?.primary_name || '-'}</div>
                                                </div>
                                                <div className="rounded-lg border border-cyan-200 dark:border-cyan-900/40 bg-white dark:bg-[#14171a] p-3">
                                                    <div className="text-[10px] uppercase tracking-wide text-gray-500">{t('approval_service_impact_criticality', 'Highest Criticality')}</div>
                                                    <div className="mt-1 text-sm font-semibold text-gray-800 dark:text-gray-100">
                                                        {selectedApprovalServiceImpact.summary?.highest_criticality
                                                            ? t(`service_groups_criticality_${String(selectedApprovalServiceImpact.summary.highest_criticality || 'standard').toLowerCase()}`, selectedApprovalServiceImpact.summary.highest_criticality)
                                                            : '-'}
                                                    </div>
                                                </div>
                                                <div className="rounded-lg border border-cyan-200 dark:border-cyan-900/40 bg-white dark:bg-[#14171a] p-3">
                                                    <div className="text-[10px] uppercase tracking-wide text-gray-500">{t('approval_service_impact_assets', 'Matched Assets')}</div>
                                                    <div className="mt-1 text-lg font-bold text-cyan-700 dark:text-cyan-300">{Number(selectedApprovalServiceImpact.summary?.matched_member_count || 0)}</div>
                                                </div>
                                            </div>

                                            <div className="space-y-3">
                                                {selectedApprovalServiceImpact.groups.map((group) => (
                                                    <div
                                                        key={`approval-svc-${group.id}`}
                                                        className="rounded-lg border border-cyan-200 dark:border-cyan-900/40 bg-white dark:bg-[#14171a] p-3"
                                                    >
                                                        <div className="flex flex-wrap items-start justify-between gap-3">
                                                            <div>
                                                                <div className="flex flex-wrap items-center gap-2">
                                                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-[#0e1012] text-[10px] text-gray-600 dark:text-gray-300">
                                                                        {t(`service_groups_criticality_${String(group.criticality || 'standard').toLowerCase()}`, group.criticality)}
                                                                    </span>
                                                                    <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                                                                        {group.name}
                                                                    </span>
                                                                </div>
                                                                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                                                    {t('approval_service_impact_owner_fmt', 'Owner team {value}').replace('{value}', group.owner_team || '-')}
                                                                </div>
                                                            </div>
                                                            <div className="flex flex-wrap gap-2">
                                                                <Link
                                                                    to={`/service-groups?focusGroupId=${encodeURIComponent(String(group.id))}`}
                                                                    className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white dark:bg-[#0e1012] hover:bg-gray-100 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-700 dark:text-gray-300"
                                                                >
                                                                    {t('approval_open_service_group', 'Open Group')}
                                                                </Link>
                                                                <Link
                                                                    to={`/topology?serviceOverlay=1&serviceGroupId=${encodeURIComponent(String(group.id))}`}
                                                                    className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white dark:bg-[#0e1012] hover:bg-gray-100 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-700 dark:text-gray-300"
                                                                >
                                                                    <GitBranch size={14} /> {t('service_groups_open_topology', 'Open Topology')}
                                                                </Link>
                                                            </div>
                                                        </div>
                                                        <div className="mt-3 flex flex-wrap gap-2">
                                                            {(Array.isArray(group.matched_members) ? group.matched_members : []).map((member) => (
                                                                <span
                                                                    key={`${group.id}-${member.member_id}`}
                                                                    className="inline-flex items-center gap-1 px-2 py-1 rounded-full border border-cyan-200 dark:border-cyan-900/40 bg-cyan-50 dark:bg-cyan-950/20 text-[11px] text-cyan-700 dark:text-cyan-300"
                                                                >
                                                                    {member.display_name}
                                                                    {member.role_label ? ` / ${member.role_label}` : ''}
                                                                    {member.match_reason ? ` / ${t(`approval_service_impact_reason_${member.match_reason}`, member.match_reason)}` : ''}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </>
                                    ) : (
                                        <div className="text-sm text-gray-500 dark:text-gray-400">
                                            {t('approval_service_impact_empty', 'No mapped service group is linked to this request yet.')}
                                        </div>
                                    )}
                                </div>

                                {selectedReq.request_type === 'config_drift_remediate' && (
                                    <div className="mt-6 space-y-3">
                                        <div className="flex items-center justify-between">
                                            <h3 className="font-bold text-sm text-gray-700 dark:text-gray-300">{t('approval_drift_details', 'Drift Details')}</h3>
                                            <div className="text-xs text-gray-500">
                                                {driftLoading ? t('common_loading', 'Loading...') : (driftDetails?.status || t('devices_status_unknown', 'unknown'))}
                                            </div>
                                        </div>
                                        {driftDetails?.diff_lines ? renderDiff(driftDetails.diff_lines) : (
                                            <div className="text-sm text-gray-500 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                                                {driftDetails?.message || t('approval_no_drift_diff', 'No drift diff available')}
                                            </div>
                                        )}
                                    </div>
                                )}

                                {selectedIntentPreview && (
                                    <div className="mt-6 space-y-3">
                                        <div className="flex items-center justify-between gap-3">
                                            <h3 className="font-bold text-sm text-gray-700 dark:text-gray-300">{t('approval_cloud_intent_preview', 'Cloud Intent Preview')}</h3>
                                            <div className="flex flex-wrap gap-2 text-[11px]">
                                                <span className={`px-2 py-1 rounded-full font-extrabold uppercase ${getOperationalStatusBadgeClass(
                                                    selectedIntentPreview.riskScore >= 70 ? 'critical' : selectedIntentPreview.riskScore >= 40 ? 'warning' : 'healthy',
                                                )}`}>
                                                    {t('approval_risk_score', 'Risk')} {selectedIntentPreview.riskScore}
                                                </span>
                                                <span className="px-2 py-1 rounded-full font-extrabold uppercase bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-200">
                                                    {t('approval_scoped_resources', 'Scoped Resources')} {Number(selectedIntentPreview.cloudScope?.scoped_resources || 0)}
                                                </span>
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-2 xl:grid-cols-4 gap-2 text-xs">
                                            <div className="rounded-md border border-gray-200 dark:border-gray-700 px-2 py-1">
                                                {t('approval_estimated_devices', 'Estimated Devices')}: <span className="font-mono font-bold">{Number(selectedIntentPreview.blastRadius?.estimated_devices || 0)}</span>
                                            </div>
                                            <div className="rounded-md border border-gray-200 dark:border-gray-700 px-2 py-1">
                                                {t('approval_estimated_networks', 'Estimated Networks')}: <span className="font-mono font-bold">{Number(selectedIntentPreview.blastRadius?.estimated_networks || 0)}</span>
                                            </div>
                                            <div className="rounded-md border border-gray-200 dark:border-gray-700 px-2 py-1">
                                                {t('approval_estimated_rules', 'Estimated Rules')}: <span className="font-mono font-bold">{Number(selectedIntentPreview.blastRadius?.estimated_rules || 0)}</span>
                                            </div>
                                            <div className="rounded-md border border-gray-200 dark:border-gray-700 px-2 py-1">
                                                {t('approval_target_providers', 'Target Providers')}: <span className="font-mono font-bold">{Number((selectedIntentPreview.cloudScope?.target_providers || []).length || 0)}</span>
                                            </div>
                                        </div>

                                        {selectedIntentImpact && (
                                            <div className="rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 p-3 space-y-3">
                                                <div className="flex flex-wrap items-start justify-between gap-3">
                                                    <div>
                                                        <div className="text-[11px] uppercase tracking-[0.2em] text-sky-700 dark:text-sky-300 font-bold">
                                                            {t('approval_cloud_scope', 'Cloud Scope')}
                                                        </div>
                                                        <div className="mt-1 text-xs text-sky-800 dark:text-sky-200">
                                                            {t('approval_cloud_scope_desc', 'Review the target provider scope before approval and jump into the filtered topology impact view if you need more context.')}
                                                        </div>
                                                    </div>
                                                    <Link
                                                        data-testid="approval-open-topology-impact"
                                                        to={selectedIntentImpact.topologyPath}
                                                        className="inline-flex items-center gap-2 rounded-lg border border-sky-300 dark:border-sky-800 bg-white/80 dark:bg-sky-950/30 px-3 py-2 text-xs font-semibold text-sky-700 dark:text-sky-200 hover:bg-white dark:hover:bg-sky-900/40"
                                                    >
                                                        <GitBranch size={14} /> {t('approval_open_topology_impact', 'Open Topology Impact')}
                                                    </Link>
                                                </div>
                                                <div className="flex flex-wrap gap-2 text-[11px]">
                                                    {selectedIntentImpact.provider ? (
                                                        <span className="inline-flex items-center px-2 py-1 rounded-full border border-sky-200 dark:border-sky-800 bg-white/80 dark:bg-sky-950/20 font-bold text-sky-700 dark:text-sky-200">
                                                            {t('cloud_accounts_provider', 'Provider')}: {String(selectedIntentImpact.provider).toUpperCase()}
                                                        </span>
                                                    ) : null}
                                                    {selectedIntentImpact.accountId ? (
                                                        <span className="inline-flex items-center px-2 py-1 rounded-full border border-sky-200 dark:border-sky-800 bg-white/80 dark:bg-sky-950/20 font-bold text-sky-700 dark:text-sky-200">
                                                            {t('cloud_detail_account', 'Account')}: #{selectedIntentImpact.accountId}
                                                        </span>
                                                    ) : null}
                                                    {selectedIntentImpact.region ? (
                                                        <span className="inline-flex items-center px-2 py-1 rounded-full border border-sky-200 dark:border-sky-800 bg-white/80 dark:bg-sky-950/20 font-bold text-sky-700 dark:text-sky-200">
                                                            {t('cloud_detail_region', 'Region')}: {selectedIntentImpact.region}
                                                        </span>
                                                    ) : null}
                                                    <span className="inline-flex items-center px-2 py-1 rounded-full border border-sky-200 dark:border-sky-800 bg-white/80 dark:bg-sky-950/20 font-bold text-sky-700 dark:text-sky-200">
                                                        {t('approval_scoped_resources', 'Scoped Resources')} {selectedIntentImpact.scopedResources}
                                                    </span>
                                                    {selectedIntentImpact.resourceTypes.length > 0 ? (
                                                        <span className="inline-flex items-center px-2 py-1 rounded-full border border-sky-200 dark:border-sky-800 bg-white/80 dark:bg-sky-950/20 font-bold text-sky-700 dark:text-sky-200">
                                                            {t('cloud_intents_resource_types', 'Resource Types')}: {selectedIntentImpact.resourceTypes.join(', ')}
                                                        </span>
                                                    ) : null}
                                                </div>
                                                {selectedIntentImpact.resourcesByType.length > 0 ? (
                                                    <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
                                                        {selectedIntentImpact.resourcesByType.slice(0, 6).map((row) => (
                                                            <div key={`approval-cloud-scope-${row.key}`} className="rounded-lg border border-sky-200 dark:border-sky-800 bg-white/80 dark:bg-sky-950/20 px-3 py-2 text-xs text-sky-800 dark:text-sky-200 flex items-center justify-between gap-3">
                                                                <span className="font-semibold">{row.key}</span>
                                                                <span className="font-mono font-bold">{row.count}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : null}
                                                <div className="flex flex-wrap gap-2">
                                                    <Link
                                                        to={selectedIntentImpact.cloudIntentPath}
                                                        className="inline-flex items-center gap-2 rounded-lg border border-violet-300 dark:border-violet-800 bg-white/80 dark:bg-violet-950/30 px-3 py-2 text-xs font-semibold text-violet-700 dark:text-violet-200 hover:bg-white dark:hover:bg-violet-900/40"
                                                    >
                                                        <GitBranch size={14} /> {t('approval_open_cloud_intent', 'Open Cloud Intent')}
                                                    </Link>
                                                    <Link
                                                        to={selectedIntentImpact.cloudAccountsPath}
                                                        className="inline-flex items-center gap-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white/80 dark:bg-black/20 px-3 py-2 text-xs font-semibold text-gray-700 dark:text-gray-200 hover:bg-white dark:hover:bg-gray-900/40"
                                                    >
                                                        <Cloud size={14} /> {t('cloud_detail_open_accounts', 'Open Cloud Accounts')}
                                                    </Link>
                                                </div>
                                            </div>
                                        )}

                                        {selectedIntentPreview.changeSummary.length > 0 && (
                                            <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#202326] p-3">
                                                <div className="text-xs font-bold uppercase tracking-[0.2em] text-gray-500 dark:text-gray-400">
                                                    {t('approval_change_summary', 'Change Summary')}
                                                </div>
                                                <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                                                    {selectedIntentPreview.changeSummary.map((row) => (
                                                        <span
                                                            key={row}
                                                            className="inline-flex items-center px-2 py-1 rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#0f1113] text-gray-600 dark:text-gray-300"
                                                        >
                                                            {row}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {selectedIntentPreview.preCheck && (
                                            <div data-testid="approval-cloud-precheck" className="rounded-lg border border-violet-200 dark:border-violet-900/40 bg-violet-50 dark:bg-violet-950/20 p-3 space-y-3">
                                                <div className="flex flex-wrap items-start justify-between gap-3">
                                                    <div>
                                                        <div className="text-[11px] uppercase tracking-[0.2em] text-violet-700 dark:text-violet-300 font-bold">
                                                            {t('cloud_intents_precheck_title', 'Pre-Check Findings')}
                                                        </div>
                                                        <div className="mt-1 text-xs text-violet-800 dark:text-violet-200">
                                                            {t('cloud_intents_precheck_desc', 'Digital Twin Lite reviews scope, exposure, readiness, and verification coverage before this intent moves into approval.')}
                                                        </div>
                                                    </div>
                                                    <div className="flex flex-wrap gap-2 text-[11px]">
                                                        <span className={`px-2 py-1 rounded-full font-extrabold uppercase ${getOperationalStatusBadgeClass(
                                                            String(selectedIntentPreview.preCheck?.summary?.result || '').toLowerCase() === 'block'
                                                                ? 'critical'
                                                                : String(selectedIntentPreview.preCheck?.summary?.result || '').toLowerCase() === 'warn'
                                                                    ? 'warning'
                                                                    : 'healthy',
                                                        )}`}>
                                                            {t('cloud_intents_precheck_result', 'Result')} {String(selectedIntentPreview.preCheck?.summary?.result || 'pass').toUpperCase()}
                                                        </span>
                                                        <span className={`px-2 py-1 rounded-full font-extrabold uppercase ${Number(selectedIntentPreview.preCheck?.summary?.blockers || 0) > 0 ? getOperationalStatusBadgeClass('critical') : getOperationalStatusBadgeClass('healthy')}`}>
                                                            {t('cloud_intents_precheck_blockers', 'Blockers')} {Number(selectedIntentPreview.preCheck?.summary?.blockers || 0)}
                                                        </span>
                                                        <span className={`px-2 py-1 rounded-full font-extrabold uppercase ${Number(selectedIntentPreview.preCheck?.summary?.warnings || 0) > 0 ? getOperationalStatusBadgeClass('warning') : getOperationalStatusBadgeClass('healthy')}`}>
                                                            {t('cloud_intents_precheck_warnings', 'Warnings')} {Number(selectedIntentPreview.preCheck?.summary?.warnings || 0)}
                                                        </span>
                                                        <span className="px-2 py-1 rounded-full font-extrabold uppercase bg-white/80 dark:bg-violet-950/30 text-violet-700 dark:text-violet-200 border border-violet-200 dark:border-violet-800">
                                                            {t('cloud_intents_precheck_checks_run', 'Checks')} {Number(selectedIntentPreview.preCheck?.summary?.checks_run || 0)}
                                                        </span>
                                                    </div>
                                                </div>

                                                <div className="flex flex-wrap gap-2 text-[11px]">
                                                    <span className="inline-flex items-center px-2 py-1 rounded-full border border-violet-200 dark:border-violet-800 bg-white/80 dark:bg-violet-950/20 font-bold text-violet-700 dark:text-violet-200">
                                                        {t('cloud_intents_precheck_rule_pack', 'Rule Pack')}: {String(selectedIntentPreview.preCheck?.rule_pack?.name || 'Digital Twin Lite')}
                                                    </span>
                                                    <span className="inline-flex items-center px-2 py-1 rounded-full border border-violet-200 dark:border-violet-800 bg-white/80 dark:bg-violet-950/20 font-bold text-violet-700 dark:text-violet-200">
                                                        {t('cloud_intents_precheck_mode', 'Mode')}: {String(selectedIntentPreview.preCheck?.rule_pack?.mode || 'explainable')}
                                                    </span>
                                                </div>

                                                {Array.isArray(selectedIntentPreview.preCheck?.findings) && selectedIntentPreview.preCheck.findings.length > 0 ? (
                                                    <div className="space-y-2">
                                                        {selectedIntentPreview.preCheck.findings.slice(0, 5).map((finding, idx) => {
                                                            const severity = String(finding?.severity || 'info').toLowerCase();
                                                            const toneClass =
                                                                severity === 'critical'
                                                                    ? 'border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300'
                                                                    : severity === 'warning'
                                                                        ? 'border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300'
                                                                        : 'border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 text-sky-700 dark:text-sky-300';
                                                            return (
                                                                <div key={`${String(finding?.key || finding?.title || 'precheck')}-${idx}`} className={`rounded-lg border p-3 ${toneClass}`}>
                                                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                                                        <div className="text-sm font-semibold">{String(finding?.title || '-')}</div>
                                                                        <div className="flex flex-wrap gap-2">
                                                                            <span className={`px-2 py-1 rounded-full text-[10px] font-extrabold uppercase ${severity === 'critical' ? getOperationalStatusBadgeClass('critical') : severity === 'warning' ? getOperationalStatusBadgeClass('warning') : getOperationalStatusBadgeClass('healthy')}`}>
                                                                                {String(severity).toUpperCase()}
                                                                            </span>
                                                                            {finding?.blocking ? (
                                                                                <span className={`px-2 py-1 rounded-full text-[10px] font-extrabold uppercase ${getOperationalStatusBadgeClass('critical')}`}>
                                                                                    {t('cloud_intents_precheck_blocking', 'Review blocker')}
                                                                                </span>
                                                                            ) : null}
                                                                        </div>
                                                                    </div>
                                                                    <div className="mt-2 text-xs">{String(finding?.message || '')}</div>
                                                                    {finding?.recommendation ? (
                                                                        <div className="mt-2 text-xs font-medium opacity-90">{String(finding.recommendation)}</div>
                                                                    ) : null}
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                ) : (
                                                    <div className="text-sm text-violet-700 dark:text-violet-200">
                                                        {t('cloud_intents_precheck_clear', 'No pre-check issues are currently blocking approval review for this preview.')}
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {selectedIntentPreview.beforeAfterCompare && Array.isArray(selectedIntentPreview.beforeAfterCompare?.cards) && selectedIntentPreview.beforeAfterCompare.cards.length > 0 && (
                                            <div data-testid="approval-cloud-before-after" className="rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 p-3 space-y-3">
                                                <div className="flex flex-wrap items-start justify-between gap-3">
                                                    <div>
                                                        <div className="text-[11px] uppercase tracking-[0.2em] text-sky-700 dark:text-sky-300 font-bold">
                                                            {t('cloud_intents_before_after_title', 'Before / After Compare')}
                                                        </div>
                                                        <div className="mt-1 text-xs text-sky-800 dark:text-sky-200">
                                                            {t('cloud_intents_before_after_desc', 'Use this compare view to explain what changes in scope discipline, readiness, and operating posture before the intent moves into execution.')}
                                                        </div>
                                                    </div>
                                                    <div className="flex flex-wrap gap-2 text-[11px]">
                                                        <span className={`px-2 py-1 rounded-full font-extrabold uppercase ${getOperationalStatusBadgeClass(
                                                            String(selectedIntentPreview.beforeAfterCompare?.summary?.result || '').toLowerCase() === 'blocked'
                                                                ? 'critical'
                                                                : String(selectedIntentPreview.beforeAfterCompare?.summary?.result || '').toLowerCase() === 'ready'
                                                                    ? 'healthy'
                                                                    : 'warning',
                                                        )}`}>
                                                            {t('cloud_intents_before_after_result', 'Compare Result')} {String(selectedIntentPreview.beforeAfterCompare?.summary?.result || 'review').toUpperCase()}
                                                        </span>
                                                        <span className="px-2 py-1 rounded-full font-extrabold uppercase bg-white/80 dark:bg-sky-950/30 text-sky-700 dark:text-sky-200 border border-sky-200 dark:border-sky-800">
                                                            {t('cloud_intents_before_after_cards', 'Cards')} {Number(selectedIntentPreview.beforeAfterCompare?.summary?.cards || 0)}
                                                        </span>
                                                        <span className="px-2 py-1 rounded-full font-extrabold uppercase bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-200 border border-emerald-200 dark:border-emerald-900/40">
                                                            {t('cloud_intents_before_after_ready', 'Ready')} {Number(selectedIntentPreview.beforeAfterCompare?.summary?.ready_cards || 0)}
                                                        </span>
                                                        <span className="px-2 py-1 rounded-full font-extrabold uppercase bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-200 border border-amber-200 dark:border-amber-900/40">
                                                            {t('cloud_intents_before_after_review', 'Review')} {Number(selectedIntentPreview.beforeAfterCompare?.summary?.review_cards || 0)}
                                                        </span>
                                                    </div>
                                                </div>

                                                <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                                                    {selectedIntentPreview.beforeAfterCompare.cards.map((card, idx) => {
                                                        const tone = String(card?.tone || 'info').toLowerCase();
                                                        const toneClass =
                                                            tone === 'bad'
                                                                ? 'border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300'
                                                                : tone === 'warn'
                                                                    ? 'border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300'
                                                                    : tone === 'good'
                                                                        ? 'border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300'
                                                                        : 'border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 text-sky-700 dark:text-sky-300';
                                                        return (
                                                            <div key={`${String(card?.key || 'compare')}-${idx}`} className={`rounded-lg border p-3 ${toneClass}`}>
                                                                <div className="flex flex-wrap items-center justify-between gap-2">
                                                                    <div className="text-sm font-semibold">{String(card?.title || '-')}</div>
                                                                    <span className={`px-2 py-1 rounded-full text-[10px] font-extrabold uppercase ${tone === 'bad' ? getOperationalStatusBadgeClass('critical') : tone === 'warn' ? getOperationalStatusBadgeClass('warning') : tone === 'good' ? getOperationalStatusBadgeClass('healthy') : getOperationalStatusBadgeClass('unknown')}`}>
                                                                        {String(card?.status || 'review').toUpperCase()}
                                                                    </span>
                                                                </div>
                                                                <div className="mt-3 space-y-3 text-xs">
                                                                    <div>
                                                                        <div className="uppercase tracking-[0.18em] font-bold opacity-75">
                                                                            {t('cloud_intents_before_after_before', 'Current')}
                                                                        </div>
                                                                        <div className="mt-1">{String(card?.before || '')}</div>
                                                                    </div>
                                                                    <div>
                                                                        <div className="uppercase tracking-[0.18em] font-bold opacity-75">
                                                                            {t('cloud_intents_before_after_after', 'With intent')}
                                                                        </div>
                                                                        <div className="mt-1">{String(card?.after || '')}</div>
                                                                    </div>
                                                                    {card?.recommendation ? (
                                                                        <div className="font-medium opacity-90">{String(card.recommendation)}</div>
                                                                    ) : null}
                                                                </div>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        )}

                                        <div data-testid="approval-cloud-execution-continuity" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#202326] p-3 space-y-3">
                                            <div className="flex flex-wrap items-start justify-between gap-3">
                                                <div>
                                                    <div className="text-[11px] uppercase tracking-[0.2em] text-gray-500 dark:text-gray-400 font-bold">
                                                        {t('approval_cloud_execution_continuity', 'Execution Continuity')}
                                                    </div>
                                                    <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                                        {t('approval_cloud_execution_continuity_desc', 'Review what will be verified after apply, how rollback is handled, and which evidence artifacts are expected before approving the change.')}
                                                    </div>
                                                </div>
                                                <div className="flex flex-wrap gap-2 text-[11px]">
                                                    <span className="inline-flex items-center px-2 py-1 rounded-full border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 font-bold text-emerald-700 dark:text-emerald-300">
                                                        {t('approval_stage_verification', 'Verification')} {Array.isArray(selectedIntentPreview.postCheckPlan?.steps) ? selectedIntentPreview.postCheckPlan.steps.length : 0}
                                                    </span>
                                                    <span className={`inline-flex items-center px-2 py-1 rounded-full border font-bold ${
                                                        selectedIntentPreview.rollbackPlan?.automatic_enabled
                                                            ? 'border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300'
                                                            : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-black/20 text-gray-700 dark:text-gray-300'
                                                    }`}>
                                                        {selectedIntentPreview.rollbackPlan?.automatic_enabled
                                                            ? t('approval_rollback_auto_enabled', 'Auto rollback enabled')
                                                            : t('approval_rollback_manual_review', 'Manual rollback review')}
                                                    </span>
                                                    <span className="inline-flex items-center px-2 py-1 rounded-full border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 font-bold text-sky-700 dark:text-sky-300">
                                                        {t('approval_evidence_package', 'Evidence package')} {Array.isArray(selectedIntentPreview.evidencePlan?.artifacts) ? selectedIntentPreview.evidencePlan.artifacts.length : 0}
                                                    </span>
                                                </div>
                                            </div>

                                            <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
                                                <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 p-3 space-y-2">
                                                    <div className="text-[11px] uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-300 font-bold">
                                                        {t('approval_stage_verification', 'Verification')}
                                                    </div>
                                                    {Array.isArray(selectedIntentPreview.postCheckPlan?.steps) && selectedIntentPreview.postCheckPlan.steps.length > 0 ? (
                                                        <ul className="space-y-1 text-xs text-emerald-800 dark:text-emerald-200 list-disc ml-5">
                                                            {selectedIntentPreview.postCheckPlan.steps.slice(0, 4).map((row) => <li key={row}>{row}</li>)}
                                                        </ul>
                                                    ) : (
                                                        <div className="text-xs text-emerald-800 dark:text-emerald-200">
                                                            {t('approval_post_check_not_defined', 'No post-check plan is defined yet.')}
                                                        </div>
                                                    )}
                                                    {selectedIntentPreview.postCheckResult?.status ? (
                                                        <div className="text-xs text-emerald-900 dark:text-emerald-100">
                                                            {t('approval_result_summary', 'result summary')}: <span className="font-mono">{String(selectedIntentPreview.postCheckResult.status)}</span>
                                                        </div>
                                                    ) : null}
                                                </div>

                                                <div className="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 p-3 space-y-2">
                                                    <div className="text-[11px] uppercase tracking-[0.2em] text-amber-700 dark:text-amber-300 font-bold">
                                                        {t('approval_stage_rollback', 'Rollback')}
                                                    </div>
                                                    <div className="text-xs text-amber-900 dark:text-amber-100">
                                                        {t('approval_rollback_strategy', 'Strategy')}: <span className="font-mono">{String(selectedIntentPreview.rollbackPlan?.strategy || 'terraform_state_reconcile')}</span>
                                                    </div>
                                                    {Array.isArray(selectedIntentPreview.rollbackPlan?.operator_steps) && selectedIntentPreview.rollbackPlan.operator_steps.length > 0 ? (
                                                        <ul className="space-y-1 text-xs text-amber-800 dark:text-amber-200 list-disc ml-5">
                                                            {selectedIntentPreview.rollbackPlan.operator_steps.slice(0, 4).map((row) => <li key={row}>{row}</li>)}
                                                        </ul>
                                                    ) : (
                                                        <div className="text-xs text-amber-800 dark:text-amber-200">
                                                            {t('approval_rollback_steps_pending', 'Rollback operator steps will be prepared after execution metadata is stored.')}
                                                        </div>
                                                    )}
                                                    {selectedIntentPreview.rollbackResult ? (
                                                        <div className="text-xs text-amber-900 dark:text-amber-100">
                                                            {t('approval_result_summary', 'result summary')}: <span className="font-mono">{String(selectedIntentPreview.rollbackResult.message || selectedIntentPreview.rollbackResult.status || '-')}</span>
                                                        </div>
                                                    ) : null}
                                                </div>

                                                <div className="rounded-lg border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 p-3 space-y-2">
                                                    <div className="flex items-start justify-between gap-3">
                                                        <div className="text-[11px] uppercase tracking-[0.2em] text-sky-700 dark:text-sky-300 font-bold">
                                                            {t('approval_stage_evidence', 'Evidence')}
                                                        </div>
                                                        {selectedIntentPreview.executionStatus ? (
                                                            <button
                                                                type="button"
                                                                onClick={handleDownloadEvidence}
                                                                disabled={evidenceLoading}
                                                                className="inline-flex items-center gap-1.5 rounded-lg border border-sky-300 dark:border-sky-800 bg-white/80 dark:bg-sky-950/30 px-2.5 py-1.5 text-[11px] font-semibold text-sky-700 dark:text-sky-200 hover:bg-white dark:hover:bg-sky-900/40 disabled:opacity-50"
                                                            >
                                                                <Download size={12} />
                                                                {evidenceLoading ? t('approval_downloading', 'Downloading...') : t('approval_download_evidence', 'Download Evidence')}
                                                            </button>
                                                        ) : null}
                                                    </div>
                                                    {Array.isArray(selectedIntentPreview.evidencePlan?.artifacts) && selectedIntentPreview.evidencePlan.artifacts.length > 0 ? (
                                                        <ul className="space-y-1 text-xs text-sky-800 dark:text-sky-200 list-disc ml-5">
                                                            {selectedIntentPreview.evidencePlan.artifacts.slice(0, 5).map((row) => <li key={row}>{row}</li>)}
                                                        </ul>
                                                    ) : (
                                                        <div className="text-xs text-sky-800 dark:text-sky-200">
                                                            {t('approval_evidence_pending', 'Evidence artifacts will appear after plan rendering and execution traces are stored.')}
                                                        </div>
                                                    )}
                                                    {Array.isArray(selectedIntentPreview.evidencePlan?.operator_package_sections) && selectedIntentPreview.evidencePlan.operator_package_sections.length > 0 ? (
                                                        <div className="text-xs text-sky-900 dark:text-sky-100">
                                                            {t('approval_operator_package_sections', 'Operator package')}: <span className="font-medium">{selectedIntentPreview.evidencePlan.operator_package_sections.join(' · ')}</span>
                                                        </div>
                                                    ) : null}
                                                </div>
                                            </div>
                                        </div>

                                        {selectedIntentPreview.operationalGuardrails && (
                                            <div data-testid="approval-cloud-guardrails" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#202326] p-3 space-y-3">
                                                <div className="flex flex-wrap items-start justify-between gap-3">
                                                    <div>
                                                        <div className="text-[11px] uppercase tracking-[0.2em] text-gray-500 dark:text-gray-400 font-bold">
                                                            {t('approval_cloud_guardrails', 'Operational Guardrails')}
                                                        </div>
                                                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                                            {t('approval_cloud_guardrails_desc', 'These guardrails explain why a cloud change stays read-only, approval-only, or change-enabled before execution.')}
                                                        </div>
                                                    </div>
                                                    <div className="flex flex-wrap gap-2 text-[11px]">
                                                        <span className="inline-flex items-center px-2 py-1 rounded-full border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 font-bold text-emerald-700 dark:text-emerald-300">
                                                            {t('cloud_intents_guardrails_change_enabled', 'Change-enabled')} {Number(selectedIntentPreview.operationalGuardrails?.summary?.change_enabled_accounts || 0)}
                                                        </span>
                                                        <span className="inline-flex items-center px-2 py-1 rounded-full border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 font-bold text-amber-700 dark:text-amber-300">
                                                            {t('cloud_intents_guardrails_read_only', 'Read-only')} {Number(selectedIntentPreview.operationalGuardrails?.summary?.read_only_accounts || 0)}
                                                        </span>
                                                        <span className={`inline-flex items-center px-2 py-1 rounded-full border font-bold ${
                                                            Number(selectedIntentPreview.operationalGuardrails?.summary?.critical_findings || 0) > 0
                                                                ? 'border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300'
                                                                : 'border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 text-sky-700 dark:text-sky-300'
                                                        }`}>
                                                            {t('cloud_intents_guardrails_critical', 'Critical')} {Number(selectedIntentPreview.operationalGuardrails?.summary?.critical_findings || 0)}
                                                        </span>
                                                    </div>
                                                </div>

                                                {Array.isArray(selectedIntentPreview.operationalGuardrails?.findings) && selectedIntentPreview.operationalGuardrails.findings.length > 0 ? (
                                                    <div className="space-y-2">
                                                        {selectedIntentPreview.operationalGuardrails.findings.slice(0, 3).map((finding, idx) => {
                                                            const severity = String(finding?.severity || 'info').toLowerCase();
                                                            const toneClass =
                                                                severity === 'critical'
                                                                    ? 'border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300'
                                                                    : severity === 'warning'
                                                                        ? 'border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300'
                                                                        : 'border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 text-sky-700 dark:text-sky-300';
                                                            return (
                                                                <div key={`${String(finding?.key || finding?.title || 'finding')}-${idx}`} className={`rounded-lg border p-3 ${toneClass}`}>
                                                                    <div className="flex items-center justify-between gap-3">
                                                                        <div className="font-bold text-sm">{String(finding?.title || '-')}</div>
                                                                        <span className="text-[11px] font-extrabold uppercase">{String(severity || 'info')}</span>
                                                                    </div>
                                                                    <div className="mt-1 text-xs">{String(finding?.message || '')}</div>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                ) : null}

                                                {Array.isArray(selectedIntentPreview.operationalGuardrails?.account_modes) && selectedIntentPreview.operationalGuardrails.account_modes.length > 0 ? (
                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                                        {selectedIntentPreview.operationalGuardrails.account_modes.map((row) => (
                                                            <div key={`${row.provider}-${row.account_id}`} className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-black/20 px-3 py-2">
                                                                <div className="flex flex-wrap items-center gap-2">
                                                                    <span className="inline-flex items-center px-2 py-1 rounded-full border border-sky-200 dark:border-sky-900/40 bg-sky-50 dark:bg-sky-950/20 text-[11px] font-bold text-sky-700 dark:text-sky-300">
                                                                        {String(row.provider || '').toUpperCase()}
                                                                    </span>
                                                                    <span className={`inline-flex items-center px-2 py-1 rounded-full border text-[11px] font-bold ${
                                                                        row.change_enabled
                                                                            ? 'border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300'
                                                                            : 'border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300'
                                                                    }`}>
                                                                        {row.change_enabled ? t('cloud_intents_guardrails_change_enabled_single', 'Change-enabled') : t('cloud_intents_guardrails_read_only_single', 'Read-only')}
                                                                    </span>
                                                                    <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{String(row.name || row.account_id)}</span>
                                                                </div>
                                                                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{String(row.change_mode_reason || '')}</div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : null}
                                            </div>
                                        )}

                                        {Array.isArray(selectedIntentPreview.terraformPlan?.change_blocks) && selectedIntentPreview.terraformPlan.change_blocks.length > 0 && (
                                            <div className="space-y-2">
                                                {selectedIntentPreview.terraformPlan.change_blocks.map((block, idx) => (
                                                    <div
                                                        key={`${block.provider}-${block.module}-${idx}`}
                                                        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#202326] p-3"
                                                    >
                                                        <div className="flex flex-wrap items-center gap-2 text-[11px]">
                                                            <span className="inline-flex items-center px-2 py-1 rounded-full border border-sky-100 bg-sky-50 text-sky-700 dark:border-sky-800/40 dark:bg-sky-900/20 dark:text-sky-300">
                                                                {String(block.provider || '').toUpperCase()}
                                                            </span>
                                                            <span className="inline-flex items-center px-2 py-1 rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#0f1113] text-gray-600 dark:text-gray-300">
                                                                {block.module || 'module'}
                                                            </span>
                                                        </div>
                                                        {Array.isArray(block.changes) && block.changes.length > 0 && (
                                                            <ul className="mt-3 space-y-1 text-xs text-gray-600 dark:text-gray-300 list-disc ml-5">
                                                                {block.changes.map((line) => <li key={line}>{line}</li>)}
                                                            </ul>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {selectedIntentPreview.postCheckResult && (
                                            <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/20 p-3 space-y-2">
                                                <div className="flex items-center justify-between gap-3">
                                                    <div className="text-[11px] uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-300 font-bold">
                                                        {t('approval_stage_verification', 'Verification')}
                                                    </div>
                                                    <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold uppercase ${getOperationalStatusBadgeClass(selectedIntentPreview.postCheckResult.status || 'unknown')}`}>
                                                        {getOperationalStatusLabel(selectedIntentPreview.postCheckResult.status || 'unknown')}
                                                    </span>
                                                </div>
                                                <div className="grid grid-cols-2 gap-2 text-xs text-emerald-900 dark:text-emerald-100">
                                                    <div>
                                                        {t('cloud_intents_scanned_resources', 'Scanned Resources')}: <span className="font-mono font-bold">{Number(selectedIntentPreview.postCheckResult.scanned_resources || 0)}</span>
                                                    </div>
                                                    <div>
                                                        {t('cloud_intents_failed_accounts', 'Failed Accounts')}: <span className="font-mono font-bold">{Number(selectedIntentPreview.postCheckResult.failed_accounts || 0)}</span>
                                                    </div>
                                                </div>
                                                {Array.isArray(selectedIntentPreview.postCheckResult.blocking_failures) && selectedIntentPreview.postCheckResult.blocking_failures.length > 0 && (
                                                    <ul className="space-y-1 text-xs text-emerald-800 dark:text-emerald-200 list-disc ml-5">
                                                        {selectedIntentPreview.postCheckResult.blocking_failures.map((row, idx) => (
                                                            <li key={`${row.account_id || idx}-${row.provider || 'provider'}`}>
                                                                {String(row.provider || '').toUpperCase()} #{row.account_id}: {row.message || `${row.preflight_status}/${row.scan_status}`}
                                                            </li>
                                                        ))}
                                                    </ul>
                                                )}
                                                <div className="pt-1">
                                                    <Link
                                                        to={selectedIntentImpact?.topologyPath || '/topology'}
                                                        className="inline-flex items-center gap-2 rounded-lg border border-emerald-300 dark:border-emerald-800 bg-white/80 dark:bg-emerald-950/20 px-3 py-2 text-xs font-semibold text-emerald-700 dark:text-emerald-200 hover:bg-white dark:hover:bg-emerald-900/30"
                                                    >
                                                        <GitBranch size={14} /> {t('approval_open_topology_impact', 'Open Topology Impact')}
                                                    </Link>
                                                </div>
                                            </div>
                                        )}

                                        {selectedIntentPreview.rollbackPlan && (
                                            <div className="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 p-3 space-y-2">
                                                <div className="flex items-center justify-between gap-3">
                                                    <div className="text-[11px] uppercase tracking-[0.2em] text-amber-700 dark:text-amber-300 font-bold">
                                                        {t('approval_stage_rollback', 'Rollback')}
                                                    </div>
                                                    <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold uppercase ${getOperationalStatusBadgeClass(selectedIntentPreview.rollbackPlan.status || 'unknown')}`}>
                                                        {getOperationalStatusLabel(selectedIntentPreview.rollbackPlan.status || 'unknown')}
                                                    </span>
                                                </div>
                                                {Array.isArray(selectedIntentPreview.rollbackPlan.operator_steps) && selectedIntentPreview.rollbackPlan.operator_steps.length > 0 && (
                                                    <ul className="space-y-1 text-xs text-amber-800 dark:text-amber-200 list-disc ml-5">
                                                        {selectedIntentPreview.rollbackPlan.operator_steps.map((row) => <li key={row}>{row}</li>)}
                                                    </ul>
                                                )}
                                                {selectedIntentPreview.rollbackResult && (
                                                    <div className="text-xs text-amber-900 dark:text-amber-100">
                                                        {t('approval_result_summary', 'result summary')}: <span className="font-mono">{String(selectedIntentPreview.rollbackResult.message || selectedIntentPreview.rollbackResult.status || '-')}</span>
                                                    </div>
                                                )}
                                                <div className="flex flex-wrap gap-2 pt-1">
                                                    <Link
                                                        to={selectedIntentImpact?.cloudIntentPath || '/cloud/intents'}
                                                        className="inline-flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-800 bg-white/80 dark:bg-amber-950/20 px-3 py-2 text-xs font-semibold text-amber-700 dark:text-amber-200 hover:bg-white dark:hover:bg-amber-900/30"
                                                    >
                                                        <GitBranch size={14} /> {t('approval_open_cloud_intent', 'Open Cloud Intent')}
                                                    </Link>
                                                    <Link
                                                        to={selectedIntentImpact?.cloudAccountsPath || '/cloud/accounts'}
                                                        className="inline-flex items-center gap-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white/80 dark:bg-black/20 px-3 py-2 text-xs font-semibold text-gray-700 dark:text-gray-200 hover:bg-white dark:hover:bg-gray-900/40"
                                                    >
                                                        <Cloud size={14} /> {t('cloud_detail_open_accounts', 'Open Cloud Accounts')}
                                                    </Link>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {selectedReq?.payload?.execution_status && (
                                    <div className="mt-6 space-y-3">
                                        <div className="flex items-center justify-between">
                                            <h3 className="font-bold text-sm text-gray-700 dark:text-gray-300">{t('approval_execution', 'Execution')}</h3>
                                            <div className="flex items-center gap-2">
                                                <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold uppercase ${getOperationalStatusBadgeClass(selectedReq.payload.execution_status)}`}>
                                                    {getOperationalStatusLabel(selectedReq.payload.execution_status)}
                                                </span>
                                                <button
                                                    type="button"
                                                    onClick={handleDownloadEvidence}
                                                    disabled={evidenceLoading}
                                                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 dark:bg-black/20 dark:hover:bg-black/30 border border-gray-200 dark:border-gray-700 text-xs font-semibold text-gray-800 dark:text-gray-100 disabled:opacity-50"
                                                >
                                                    <Download size={12} />
                                                    {evidenceLoading ? t('approval_downloading', 'Downloading...') : t('approval_download_evidence', 'Download Evidence')}
                                                </button>
                                            </div>
                                        </div>
                                        <div className="text-xs text-gray-500 dark:text-gray-400">
                                            {getOperationalStatusHint(selectedReq.payload.execution_status)}
                                        </div>
                                        {(selectedReq?.payload?.approval_id !== undefined || selectedReq?.payload?.execution_id) && (
                                            <div className="text-xs text-gray-600 dark:text-gray-400 flex flex-wrap gap-4">
                                                <div>
                                                    approval_id: <span className="font-mono">{String(selectedReq?.payload?.approval_id ?? '-')}</span>
                                                </div>
                                                <div>
                                                    execution_id: <span className="font-mono">{String(selectedReq?.payload?.execution_id ?? '-')}</span>
                                                </div>
                                            </div>
                                        )}
                                        {summarizeExecution(selectedReq) && (
                                            <div className="text-xs text-gray-600 dark:text-gray-400">
                                                {t('approval_result_summary', 'result summary')}: <span className="font-mono">{summarizeExecution(selectedReq)}</span>
                                            </div>
                                        )}
                                        {selectedExecutionStages.length > 0 && (
                                            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                                                {selectedExecutionStages.map((stage) => {
                                                    const Icon = stage.icon;
                                                    return (
                                                        <div
                                                            key={stage.key}
                                                            className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#202326] p-3 space-y-3"
                                                        >
                                                            <div className="flex items-start justify-between gap-3">
                                                                <div className="flex items-center gap-2">
                                                                    <div className="h-9 w-9 rounded-lg bg-gray-100 dark:bg-[#14171a] border border-gray-200 dark:border-gray-700 inline-flex items-center justify-center text-gray-700 dark:text-gray-200">
                                                                        <Icon size={16} />
                                                                    </div>
                                                                    <div>
                                                                        <div className="text-[11px] uppercase tracking-[0.2em] text-gray-400">{t('approval_execution_workflow', 'Execution Workflow')}</div>
                                                                        <div className="font-bold text-sm text-gray-900 dark:text-gray-100">{stage.title}</div>
                                                                    </div>
                                                                </div>
                                                                <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold uppercase ${getOperationalStatusBadgeClass(stage.status)}`}>
                                                                    {getOperationalStatusLabel(stage.status)}
                                                                </span>
                                                            </div>
                                                            <div className="text-xs text-gray-600 dark:text-gray-300">
                                                                {stage.description}
                                                            </div>
                                                            <div className="text-[11px] text-gray-500 dark:text-gray-400">
                                                                {getOperationalStatusHint(stage.status)}
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                        {selectedExecutionDiagnostics && (
                                            <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#202326] p-3 space-y-2">
                                                <div className="grid grid-cols-2 gap-2 text-xs">
                                                    <div className="rounded-md border border-gray-200 dark:border-gray-700 px-2 py-1">
                                                        {t('approval_precheck_failed', 'Pre-check failed')}: <span className="font-mono font-bold">{selectedExecutionDiagnostics.precheckFailed}</span>
                                                    </div>
                                                    <div className="rounded-md border border-gray-200 dark:border-gray-700 px-2 py-1">
                                                        {t('approval_postcheck_failed', 'Post-check failed')}: <span className="font-mono font-bold">{selectedExecutionDiagnostics.postcheckFailed}</span>
                                                    </div>
                                                    <div className="rounded-md border border-gray-200 dark:border-gray-700 px-2 py-1">
                                                        {t('approval_rollback_attempted', 'Rollback attempted')}: <span className="font-mono font-bold">{selectedExecutionDiagnostics.rollbackAttempted}</span>
                                                    </div>
                                                    <div className="rounded-md border border-gray-200 dark:border-gray-700 px-2 py-1">
                                                        {t('approval_rollback_success', 'Rollback success')}: <span className="font-mono font-bold">{selectedExecutionDiagnostics.rollbackSuccess}</span>
                                                    </div>
                                                </div>
                                                {selectedExecutionDiagnostics.topCauses.length > 0 && (
                                                    <div className="text-xs text-gray-600 dark:text-gray-400">
                                                        {t('approval_top_causes', 'Top causes')}:{' '}
                                                        {selectedExecutionDiagnostics.topCauses.map((row) => (
                                                            <span key={`${row.cause}-${row.count}`} className="inline-flex items-center mr-2 mt-1 px-2 py-0.5 rounded bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300 border border-red-100 dark:border-red-800/40">
                                                                {formatExecutionLabel(row.cause)} {row.count}
                                                            </span>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                        <div className="rounded-lg border border-dashed border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#15181b] p-3">
                                            <div className="text-xs font-bold uppercase tracking-[0.2em] text-gray-500 dark:text-gray-400">
                                                {t('approval_evidence_contents', 'Evidence Package Contents')}
                                            </div>
                                            <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                                                {[
                                                    t('approval_evidence_item_request', 'approval request'),
                                                    t('approval_evidence_item_summary', 'execution summary'),
                                                    t('approval_evidence_item_traces', 'change traces'),
                                                    t('approval_evidence_item_result', 'execution result'),
                                                    t('approval_evidence_item_trace', 'execution trace'),
                                                ].map((label) => (
                                                    <span
                                                        key={label}
                                                        className="inline-flex items-center px-2 py-1 rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#0f1113] text-gray-600 dark:text-gray-300"
                                                    >
                                                        {label}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                        {selectedReq?.payload?.job_id && (
                                            <div className="text-xs text-gray-600 dark:text-gray-400">
                                                Job ID: <span className="font-mono">{selectedReq.payload.job_id}</span>
                                            </div>
                                        )}
                                        {jobStatus && (
                                            <div className="bg-[#1e1e1e] rounded-lg p-4 font-mono text-xs text-gray-300 overflow-x-auto shadow-inner border border-gray-700">
                                                <pre>{JSON.stringify(jobStatus, null, 2)}</pre>
                                            </div>
                                        )}
                                        {selectedReq?.payload?.job_id && (
                                            <button
                                                onClick={async () => {
                                                    setJobLoading(true);
                                                    try {
                                                        const res = await JobService.getStatus(selectedReq.payload.job_id);
                                                        setJobStatus(res.data);
                                                    } catch (e) {
                                                        setJobStatus({ error: t('approval_failed_load_job_status', 'Failed to load job status') });
                                                    } finally {
                                                        setJobLoading(false);
                                                    }
                                                }}
                                                disabled={jobLoading}
                                                className="px-3 py-2 text-xs bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50"
                                            >
                                                {jobLoading ? t('approval_refreshing', 'Refreshing...') : t('approval_refresh_job_status', 'Refresh Job Status')}
                                            </button>
                                        )}
                                    </div>
                                )}

                                {/* Comments Section */}
                                <div className="mt-6 space-y-4">
                                    {selectedReq.requester_comment && (
                                        <div className="bg-blue-50 dark:bg-blue-900/10 p-4 rounded-xl border border-blue-100 dark:border-blue-900/30">
                                            <div className="text-xs font-bold text-blue-600 dark:text-blue-400 mb-1">{t('approval_requester_note', 'Requester Note')}</div>
                                            <p className="text-sm text-gray-800 dark:text-gray-200">{selectedReq.requester_comment}</p>
                                        </div>
                                    )}
                                    {selectedReq.approver_comment && (
                                        <div className={`p-4 rounded-xl border ${selectedReq.status === 'approved' ? 'bg-green-50 dark:bg-green-900/10 border-green-100 dark:border-green-900/30' : 'bg-red-50 dark:bg-red-900/10 border-red-100 dark:border-red-900/30'}`}>
                                            <div className={`text-xs font-bold mb-1 ${selectedReq.status === 'approved' ? 'text-green-600' : 'text-red-600'}`}>{t('approval_approver_decision_note', 'Approver Decision Note')}</div>
                                            <p className="text-sm text-gray-800 dark:text-gray-200">{selectedReq.approver_comment}</p>
                                            <div className="text-xs text-gray-500 mt-2 text-right">
                                                - {selectedReq.approver_name} at {new Date(selectedReq.decided_at).toLocaleString()}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Action Footer */}
                            {selectedReq.status === 'pending' && (
                                <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-[#1b1d1f] shrink-0">
                                    <div className="mb-3">
                                        <label className="text-xs font-bold text-gray-500 mb-1 block">{t('approval_reject_or_approve_comment', 'Approval/Rejection Comment')}</label>
                                        <textarea
                                            value={comment}
                                            onChange={(e) => setComment(e.target.value)}
                                            placeholder={t('approval_comment_placeholder', 'Enter reason or feedback...')}
                                            className="w-full px-3 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none resize-none h-20"
                                        />
                                    </div>
                                    <div className="flex gap-3 justify-end">
                                        <button
                                            onClick={() => handleAction('reject')}
                                            disabled={actionLoading}
                                            className="px-6 py-2 bg-red-50 hover:bg-red-100 text-red-600 font-medium rounded-lg transition-colors border border-red-200 disabled:opacity-50"
                                        >
                                            {t('approval_reject', 'Reject')}
                                        </button>
                                        <button
                                            onClick={() => handleAction('approve')}
                                            disabled={actionLoading}
                                            className="px-6 py-2 bg-green-600 hover:bg-green-500 text-white font-medium rounded-lg shadow-lg shadow-green-500/30 transition-all disabled:opacity-50 flex items-center gap-2"
                                        >
                                            {actionLoading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <CheckCircle size={16} />}
                                            {t('approval_approve_request', 'Approve Request')}
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    ) : (
                        <InlineEmpty label={t('approval_select_request', 'Select a request to view details')} className="flex-1" />
                    )}
                </SectionCard>
            </div>
        </div>
    );
};

export default ApprovalPage;
