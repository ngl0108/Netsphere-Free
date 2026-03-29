import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
    DiscoveryService,
    DeviceService,
    MonitoringProfileService,
    ServiceGroupService,
    SettingsService,
    TopologyService,
} from '../../api/services';
import { useToast } from '../../context/ToastContext';
import {
    Radar, Play, RefreshCw, CheckCircle, Server, Terminal, AlertTriangle, Plus, MapPin, Shield, Workflow
} from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import useVisiblePolling from '../../hooks/useVisiblePolling';
import { startAuthenticatedSse } from '../../utils/sseClient';
import { getApiBaseUrl } from '../../api/baseUrl';

// ... (imports remain the same)

const DiscoveryPage = () => {
    useLocaleRerender();
    const navigate = useNavigate();
    const location = useLocation();
    const { toast } = useToast();
    const [step, setStep] = useState(1); // 1: Input, 2: Scanning, 3: Results
    const [jobId, setJobId] = useState(null);

    // Input State
    const [scanMode, setScanMode] = useState('cidr'); // 'cidr' | 'seed'
    const [cidr, setCidr] = useState("192.168.1.0/24");
    const [community, setCommunity] = useState("public");
    const [seedDeviceId, setSeedDeviceId] = useState('');
    const [seedIp, setSeedIp] = useState('');
    const [maxDepth, setMaxDepth] = useState(2);
    const [plugAndScanMode, setPlugAndScanMode] = useState(true);

    const [snmpVersion, setSnmpVersion] = useState('v2c');
    const [snmpPort, setSnmpPort] = useState(161);
    const [snmpV3Username, setSnmpV3Username] = useState('');
    const [snmpV3SecurityLevel, setSnmpV3SecurityLevel] = useState('authPriv');
    const [snmpV3AuthProto, setSnmpV3AuthProto] = useState('sha');
    const [snmpV3AuthKey, setSnmpV3AuthKey] = useState('');
    const [snmpV3PrivProto, setSnmpV3PrivProto] = useState('aes');
    const [snmpV3PrivKey, setSnmpV3PrivKey] = useState('');
    const [seedDevices, setSeedDevices] = useState([]);
    const [loadingSeeds, setLoadingSeeds] = useState(false);
    const [generalSettings, setGeneralSettings] = useState({});
    const [sites, setSites] = useState([]);
    const [kpiWindowDays, setKpiWindowDays] = useState(7);
    const [kpiSiteId, setKpiSiteId] = useState('');

    // Job State
    const [jobStatus, setJobStatus] = useState(null);
    const [logs, setLogs] = useState("");
    const [progress, setProgress] = useState(0);

    // Results State
    const [results, setResults] = useState([]);
    const [managedSummary, setManagedSummary] = useState(null);
    const [profileCatalog, setProfileCatalog] = useState([]);
    const [serviceGroups, setServiceGroups] = useState([]);
    const [jobKpi, setJobKpi] = useState(null);
    const [kpiSummary, setKpiSummary] = useState(null);
    const [kpiSummaryLoading, setKpiSummaryLoading] = useState(false);
    const [candidateQueueSummary, setCandidateQueueSummary] = useState(null);
    const [candidateQueueTrend, setCandidateQueueTrend] = useState(null);
    const [opsAlerts, setOpsAlerts] = useState(null);
    const [autoApproveReport, setAutoApproveReport] = useState(null);
    const [expanded, setExpanded] = useState({});
    const [reviewContext, setReviewContext] = useState(null);
    const [reviewLoading, setReviewLoading] = useState(false);
    const [reviewActionLoading, setReviewActionLoading] = useState('');
    const [reviewSiteId, setReviewSiteId] = useState('');
    const [reviewProfileId, setReviewProfileId] = useState('');
    const [reviewServiceGroupId, setReviewServiceGroupId] = useState('');
    const logEndRef = useRef(null);
    const esRef = useRef(null);
    const autoPostActionDoneRef = useRef(false);
    const terminalPollingHandledRef = useRef(false);
    const [streamConnected, setStreamConnected] = useState(false);
    const jobPollingIntervalMs = streamConnected ? 5000 : 2000;
    const hasManagedQuota = Number(managedSummary?.managed_limit || 0) > 0;

    const trendRows = useMemo(() => {
        const raw = Array.isArray(candidateQueueTrend?.series) ? candidateQueueTrend.series : [];
        if (raw.length === 0) return [];
        if (Number(kpiWindowDays) < 30) return raw.slice(-Math.min(Number(kpiWindowDays || 7), 10));

        // 30d mode: compress to weekly buckets for readability.
        const weekly = [];
        for (let i = 0; i < raw.length; i += 7) {
            const chunk = raw.slice(i, i + 7);
            if (chunk.length === 0) continue;
            const first = chunk[0];
            const last = chunk[chunk.length - 1];
            const sum = (key) => chunk.reduce((acc, x) => acc + Number(x?.[key] || 0), 0);
            weekly.push({
                label: `${String(first?.date || '').slice(5)}~${String(last?.date || '').slice(5)}`,
                backlog_total: sum('backlog_total'),
                resolved_total: sum('resolved_total'),
            });
        }
        return weekly.slice(-6);
    }, [candidateQueueTrend, kpiWindowDays]);

    const parseCidrList = (raw) => {
        const parts = String(raw || '').replaceAll('\n', ',').split(',');
        return parts.map(s => s.trim()).filter(Boolean);
    };

    const ipv4ToInt = (ip) => {
        const s = String(ip || '').trim();
        const m = s.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
        if (!m) return null;
        const octets = [m[1], m[2], m[3], m[4]].map(x => Number(x));
        if (octets.some(o => Number.isNaN(o) || o < 0 || o > 255)) return null;
        return ((octets[0] << 24) >>> 0) + (octets[1] << 16) + (octets[2] << 8) + octets[3];
    };

    const cidrContains = (cidr, ip) => {
        const s = String(cidr || '').trim();
        const m = s.match(/^(.+)\/(\d{1,2})$/);
        if (!m) return false;
        const baseIp = ipv4ToInt(m[1]);
        if (baseIp === null) return false;
        const maskBits = Number(m[2]);
        if (Number.isNaN(maskBits) || maskBits < 0 || maskBits > 32) return false;
        const ipInt = ipv4ToInt(ip);
        if (ipInt === null) return false;
        const mask = maskBits === 0 ? 0 : (0xffffffff << (32 - maskBits)) >>> 0;
        return (baseIp & mask) === (ipInt & mask);
    };

    const checkScopeAllowed = (ip, includeCidrs, excludeCidrs) => {
        const ipStr = String(ip || '').trim();
        if (!ipStr) return { ok: true, reason: '' };
        if (ipv4ToInt(ipStr) === null) return { ok: false, reason: t('discovery_invalid_ip', 'Invalid IP format.') };
        const excludes = Array.isArray(excludeCidrs) ? excludeCidrs : [];
        const includes = Array.isArray(includeCidrs) ? includeCidrs : [];
        if (excludes.some(c => cidrContains(c, ipStr))) return { ok: false, reason: t('discovery_scope_excluded', 'Included in Exclude CIDR range.') };
        if (includes.length > 0 && !includes.some(c => cidrContains(c, ipStr))) return { ok: false, reason: t('discovery_scope_not_included', 'Outside Include CIDR range.') };
        return { ok: true, reason: '' };
    };

    useEffect(() => {
        let cancelled = false;
        const run = async () => {
            try {
                const [settingsRes, sitesRes, managedSummaryRes] = await Promise.all([
                    SettingsService.getGeneral(),
                    DeviceService.getSites(),
                    DeviceService.getManagedSummary().catch(() => ({ data: null })),
                ]);
                if (cancelled) return;
                setGeneralSettings(settingsRes.data || {});
                setSites(Array.isArray(sitesRes?.data) ? sitesRes.data : []);
                setManagedSummary(managedSummaryRes?.data || null);
            } catch (e) {
                if (!cancelled) {
                    setGeneralSettings({});
                    setSites([]);
                    setManagedSummary(null);
                }
            }
        };
        run();
        return () => { cancelled = true; };
    }, []);

    useEffect(() => {
        loadKpiSummary();
    }, [
        kpiWindowDays,
        kpiSiteId,
        generalSettings?.ops_alerts_min_auto_reflection_pct,
        generalSettings?.ops_alerts_max_false_positive_pct,
        generalSettings?.ops_alerts_max_low_confidence_rate_pct,
        generalSettings?.ops_alerts_max_candidate_backlog,
        generalSettings?.ops_alerts_max_stale_backlog_24h,
    ]);

    const runPostCompleteActions = async (completedJobId) => {
        if (!plugAndScanMode || scanMode !== 'seed') return;
        if (!completedJobId) return;
        if (autoPostActionDoneRef.current) return;
        autoPostActionDoneRef.current = true;
        try {
            const approveRes = await DiscoveryService.approveAll(completedJobId, { policy: true });
            const approvedCount = Number(approveRes?.data?.approved_count || 0);
            const skippedCount = Number(approveRes?.data?.skipped_count || 0);
            const skipBreakdown = approveRes?.data?.skip_breakdown || {};
            const policyMeta = approveRes?.data?.policy || {};
            setAutoApproveReport({
                approved_count: approvedCount,
                skipped_count: skippedCount,
                skip_breakdown: skipBreakdown,
                policy: policyMeta,
            });
            const skipText = Object.entries(skipBreakdown)
                .map(([k, v]) => `${k}:${v}`)
                .join(', ');
            try {
                await TopologyService.createSnapshot({
                    label: `plug-and-scan ${new Date().toISOString().slice(0, 19).replace('T', ' ')}`,
                    metadata: { trigger: 'plug_and_scan', job_id: Number(completedJobId) },
                });
            } catch (e) {
                // Snapshot failure should not block provisioning flow
            }
            toast.success(t('discovery_plug_scan_completed_fmt', 'Plug and Scan completed: approved {approved}, skipped {skipped}{details}').replace('{approved}', String(approvedCount)).replace('{skipped}', String(skippedCount)).replace('{details}', skipText ? ` (${skipText})` : ''));
            const lowConfSkip = Number(skipBreakdown?.low_confidence_link || 0);
            if (lowConfSkip > 0) {
                navigate('/topology', {
                    state: {
                        showCandidates: true,
                        candidateJobId: Number(completedJobId),
                        candidateStatus: 'low_confidence',
                    }
                });
            } else {
                navigate('/topology');
            }
        } catch (e) {
            autoPostActionDoneRef.current = false;
            toast.error(t('discovery_plug_scan_failed', 'Plug and Scan auto-provision failed'));
        }
    };

    const loadKpiSummary = async () => {
        try {
            setKpiSummaryLoading(true);
            const siteParam = kpiSiteId ? { site_id: Number(kpiSiteId) } : {};
            const _num = (v) => {
                const n = Number(v);
                return Number.isFinite(n) ? n : undefined;
            };
            const alertThresholdParams = {
                min_auto_reflection_pct: _num(generalSettings?.ops_alerts_min_auto_reflection_pct),
                max_false_positive_pct: _num(generalSettings?.ops_alerts_max_false_positive_pct),
                max_low_confidence_rate_pct: _num(generalSettings?.ops_alerts_max_low_confidence_rate_pct),
                max_candidate_backlog: _num(generalSettings?.ops_alerts_max_candidate_backlog),
                max_stale_backlog_24h: _num(generalSettings?.ops_alerts_max_stale_backlog_24h),
            };
            const [kpiRes, queueRes, trendRes, alertsRes] = await Promise.all([
                DiscoveryService.getKpiSummary({ days: Number(kpiWindowDays) || 7, limit: 100, ...siteParam }),
                TopologyService.getCandidateSummary({ ...siteParam }),
                TopologyService.getCandidateSummaryTrend({ days: Number(kpiWindowDays) || 7, limit: 5, ...siteParam }),
                DiscoveryService.getKpiAlerts({ days: Number(kpiWindowDays) || 7, limit: 100, ...siteParam, ...alertThresholdParams }),
            ]);
            setKpiSummary(kpiRes?.data || null);
            setCandidateQueueSummary(queueRes?.data || null);
            setCandidateQueueTrend(trendRes?.data || null);
            setOpsAlerts(alertsRes?.data || null);
        } catch (e) {
            setKpiSummary(null);
            setCandidateQueueSummary(null);
            setCandidateQueueTrend(null);
            setOpsAlerts(null);
        } finally {
            setKpiSummaryLoading(false);
        }
    };

    useVisiblePolling(async () => {
        if (step !== 2 || !jobId) return;
        try {
            const res = await DiscoveryService.getJobStatus(jobId);
            const nextStatus = String(res?.data?.status || '');
            setJobStatus(nextStatus);
            setLogs(res?.data?.logs || '');
            setProgress(Number(res?.data?.progress || 0));

            if ((nextStatus === 'completed' || nextStatus === 'failed') && !terminalPollingHandledRef.current) {
                terminalPollingHandledRef.current = true;
                if (nextStatus === 'completed') {
                    await runPostCompleteActions(jobId);
                    window.setTimeout(() => {
                        void loadResults();
                    }, 600);
                }
            }
        } catch (err) {
            console.error("Polling failed", err);
        }
    }, jobPollingIntervalMs, {
        enabled: step === 2 && !!jobId && jobStatus !== 'completed' && jobStatus !== 'failed',
        immediate: true,
        runOnVisible: true,
        minGapMs: streamConnected ? 2500 : 1200,
        backoffOnError: false,
    });

    useEffect(() => {
        if (step !== 2 || !jobId) {
            setStreamConnected(false);
            return;
        }
        if (esRef.current) {
            try { esRef.current.close(); } catch (e) { void e; }
            esRef.current = null;
        }
        setStreamConnected(false);

        const API_BASE_URL = getApiBaseUrl();
        const authToken = localStorage.getItem('authToken');
        const url = `${API_BASE_URL}/discovery/jobs/${jobId}/stream`;
        const stream = startAuthenticatedSse({
            url,
            token: authToken,
            retryMs: 0,
            onOpen: () => {
                setStreamConnected(true);
            },
            onClose: () => {
                setStreamConnected(false);
            },
            onEvent: ({ event, data }) => {
                if (event === 'device') {
                    try {
                        const dev = JSON.parse(data || '{}');
                        setResults(prev => {
                            const idx = prev.findIndex(x => x.id === dev.id);
                            if (idx >= 0) {
                                const copy = prev.slice();
                                copy[idx] = { ...copy[idx], ...dev };
                                return copy;
                            }
                            return [...prev, dev];
                        });
                    } catch (e) { void e; }
                    return;
                }

                if (event === 'progress') {
                    try {
                        const p = JSON.parse(data || '{}');
                        if (typeof p.progress === 'number') setProgress(p.progress);
                        if (p.status) setJobStatus(p.status);
                    } catch (e) { void e; }
                    return;
                }

                if (event === 'done') {
                    setStreamConnected(false);
                    try { stream.close(); } catch (e) { void e; }
                    if (esRef.current === stream) {
                        esRef.current = null;
                    }
                }
            },
            onError: () => {
                setStreamConnected(false);
                if (esRef.current === stream) {
                    try { stream.close(); } catch (e) { void e; }
                    esRef.current = null;
                }
            },
        });
        esRef.current = stream;

        return () => {
            setStreamConnected(false);
            try { stream.close(); } catch (e) { void e; }
            esRef.current = null;
        };
    }, [step, jobId]);

    // Auto-scroll logs
    useEffect(() => {
        logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [logs]);

    useEffect(() => {
        if (step !== 1) return;
        if (scanMode !== 'seed') return;
        let cancelled = false;
        const run = async () => {
            try {
                setLoadingSeeds(true);
                const res = await DeviceService.getAll();
                if (cancelled) return;
                const devices = Array.isArray(res.data) ? res.data : [];
                setSeedDevices(devices);
                if (!seedDeviceId && devices.length > 0) {
                    setSeedDeviceId(String(devices[0].id));
                }
            } catch (e) {
                toast.error(t('discovery_seed_device_load_failed', 'Failed to load devices for seed crawl'));
            } finally {
                if (!cancelled) setLoadingSeeds(false);
            }
        };
        run();
        return () => {
            cancelled = true;
        };
    }, [step, scanMode]);

    const buildSnmpPayload = () => {
        const base = { snmp_version: snmpVersion, snmp_port: Number(snmpPort) || 161 };
        if (String(snmpVersion).toLowerCase() !== 'v3') {
            return { ...base, community };
        }
        return {
            ...base,
            community,
            snmp_v3_username: snmpV3Username || null,
            snmp_v3_security_level: snmpV3SecurityLevel || null,
            snmp_v3_auth_proto: snmpV3AuthProto || null,
            snmp_v3_auth_key: snmpV3AuthKey || null,
            snmp_v3_priv_proto: snmpV3PrivProto || null,
            snmp_v3_priv_key: snmpV3PrivKey || null,
        };
    };

    const scopeForMode = () => {
        const discoveryInclude = parseCidrList(generalSettings.discovery_scope_include_cidrs);
        const discoveryExclude = parseCidrList(generalSettings.discovery_scope_exclude_cidrs);
        const preferPrivate = String(generalSettings.discovery_prefer_private ?? 'true').trim().toLowerCase();
        const preferPrivateBool = ['true', '1', 'yes', 'y', 'on'].includes(preferPrivate);

        if (scanMode !== 'seed') {
            return { includeCidrs: discoveryInclude, excludeCidrs: discoveryExclude, preferPrivate: preferPrivateBool, mode: 'discovery' };
        }

        const crawlIncludeRaw = String(generalSettings.neighbor_crawl_scope_include_cidrs || '').trim();
        const crawlExcludeRaw = String(generalSettings.neighbor_crawl_scope_exclude_cidrs || '').trim();
        const crawlPreferRaw = String(generalSettings.neighbor_crawl_prefer_private || '').trim();
        const crawlInclude = crawlIncludeRaw ? parseCidrList(crawlIncludeRaw) : discoveryInclude;
        const crawlExclude = crawlExcludeRaw ? parseCidrList(crawlExcludeRaw) : discoveryExclude;
        const crawlPrefer = crawlPreferRaw
            ? ['true', '1', 'yes', 'y', 'on'].includes(crawlPreferRaw.toLowerCase())
            : preferPrivateBool;
        return { includeCidrs: crawlInclude, excludeCidrs: crawlExclude, preferPrivate: crawlPrefer, mode: 'crawl' };
    };

    const selectedSeedDeviceIp = (() => {
        if (!seedDeviceId) return '';
        const idNum = Number(seedDeviceId);
        const d = seedDevices.find(x => Number(x.id) === idNum);
        return String(d?.ip_address || '').trim();
    })();

    const effectiveSeedIp = scanMode === 'seed' ? (String(seedIp || '').trim() || selectedSeedDeviceIp) : '';
    const currentScope = scopeForMode();
    const seedScopeCheck = scanMode === 'seed'
        ? checkScopeAllowed(effectiveSeedIp, currentScope.includeCidrs, currentScope.excludeCidrs)
        : { ok: true, reason: '' };

    const handleStartScan = async (e) => {
        e.preventDefault();
        try {
            if (scanMode === 'seed') {
                if (!effectiveSeedIp) {
                    toast.error(t('discovery_seed_required', 'Select a Seed IP or Seed Device.'));
                    return;
                }
                if (!seedScopeCheck.ok) {
                    toast.error(t('discovery_seed_scope_out_fmt', 'Seed target is outside current scope: {reason}').replace('{reason}', String(seedScopeCheck.reason || '')));
                    return;
                }
            }
            const snmp = buildSnmpPayload();
            const res = scanMode === 'seed'
                ? await DiscoveryService.startNeighborCrawl({
                    seed_device_id: seedIp ? null : Number(seedDeviceId),
                    seed_ip: seedIp ? String(seedIp).trim() : null,
                    max_depth: Number(maxDepth) || 2,
                    ...snmp
                })
                : await DiscoveryService.startScan({ cidr, ...snmp });
            setJobId(res.data.id);
            setResults([]);
            setJobKpi(null);
            setExpanded({});
            setStep(2);
            setJobStatus('running');
            setLogs(t('discovery_initializing_scan', 'Initializing scan job...'));
            setProgress(0);
            setAutoApproveReport(null);
            autoPostActionDoneRef.current = false;
            terminalPollingHandledRef.current = false;
        } catch (err) {
            toast.error(t('discovery_start_failed_fmt', 'Failed to start scan: {message}').replace('{message}', String(err?.message || '')));
        }
    };

    const loadResults = async () => {
        try {
            const res = await DiscoveryService.getJobResults(jobId);
            setResults(res.data);
            try {
                const kpiRes = await DiscoveryService.getJobKpi(jobId);
                setJobKpi(kpiRes?.data || null);
            } catch (e) {
                setJobKpi(null);
            }
            setExpanded({});
            setStep(3);
            loadKpiSummary();
        } catch (err) {
            toast.error(t('discovery_results_load_failed', 'Failed to load results'));
        }
    };

    useEffect(() => {
        const incomingJobId = location.state?.jobId;
        if (!incomingJobId) return;

        const run = async () => {
            try {
                setJobId(incomingJobId);
                const res = await DiscoveryService.getJobResults(incomingJobId);
                setResults(res.data);
                try {
                    const kpiRes = await DiscoveryService.getJobKpi(incomingJobId);
                    setJobKpi(kpiRes?.data || null);
                } catch (e) {
                    setJobKpi(null);
                }
                setStep(3);
                loadKpiSummary();
            } catch (e) {
                toast.error(t('discovery_results_load_failed_all', 'Failed to load discovery results'));
            }
        };
        run();
    }, [location.state]);

    const getIssues = (dev) => Array.isArray(dev?.issues) ? dev.issues : [];

    const getEvidence = (dev) => (dev && typeof dev.evidence === 'object' && dev.evidence !== null) ? dev.evidence : {};

    const getHintEngine = (dev) => {
        const evidence = getEvidence(dev);
        return (evidence && typeof evidence.hint_engine === 'object' && evidence.hint_engine !== null) ? evidence.hint_engine : null;
    };

    const getHintTelemetry = (dev) => {
        const evidence = getEvidence(dev);
        return (evidence && typeof evidence.hint_telemetry === 'object' && evidence.hint_telemetry !== null) ? evidence.hint_telemetry : null;
    };

    const getSshProbe = (dev) => {
        const evidence = getEvidence(dev);
        return (evidence && typeof evidence.ssh_probe === 'object' && evidence.ssh_probe !== null) ? evidence.ssh_probe : null;
    };

    const hasHintEvidence = (dev) => {
        return !!getHintEngine(dev) || !!getHintTelemetry(dev) || String(getSshProbe(dev)?.method || '').trim() === 'hint_driven_ssh';
    };

    const getHintOutcome = (dev) => {
        const telemetry = getHintTelemetry(dev);
        const sshProbe = getSshProbe(dev);
        if (telemetry?.success || String(sshProbe?.method || '').trim() === 'hint_driven_ssh') {
            return 'success';
        }
        if (telemetry && telemetry?.success === false) {
            return 'failed';
        }
        if (getHintEngine(dev)) {
            return 'available';
        }
        return null;
    };

    const getHintOutcomeMeta = (dev) => {
        const outcome = getHintOutcome(dev);
        if (outcome === 'success') {
            return {
                label: t('discovery_hint_status_success', 'Hint-driven SSH success'),
                description: t('discovery_hint_status_success_desc', 'SNMP did not finish identification, but MAC/OUI and neighbor context selected the right SSH driver.'),
                className: 'bg-emerald-100 text-emerald-700 border-emerald-200',
            };
        }
        if (outcome === 'failed') {
            return {
                label: t('discovery_hint_status_failed', 'Hint fallback attempted'),
                description: t('discovery_hint_status_failed_desc', 'A MAC/OUI hint was available, but the targeted SSH retry did not finish identification yet.'),
                className: 'bg-amber-100 text-amber-700 border-amber-200',
            };
        }
        if (outcome === 'available') {
            return {
                label: t('discovery_hint_status_available', 'Hint available'),
                description: t('discovery_hint_status_available_desc', 'The engine found a MAC/OUI hint and ranked likely SSH drivers for fallback.'),
                className: 'bg-blue-100 text-blue-700 border-blue-200',
            };
        }
        return null;
    };

    const formatDriverLabel = (driver) => {
        const value = String(driver || '').trim();
        if (!value) return t('common_unknown', 'Unknown');
        return value;
    };

    const formatHintReason = (reason) => {
        const value = String(reason || '').trim();
        const labels = {
            oui_match: t('discovery_hint_reason_oui_match', 'OUI match'),
            fdb_port_seen: t('discovery_hint_reason_fdb_port_seen', 'MAC seen on seed port'),
            lldp_context: t('discovery_hint_reason_lldp_context', 'LLDP neighbor context'),
            ssh_open: t('discovery_hint_reason_ssh_open', 'SSH port open'),
            seed_context: t('discovery_hint_reason_seed_context', 'Seed device context'),
            neighbor_pattern: t('discovery_hint_reason_neighbor_pattern', 'Neighbor naming pattern'),
            domestic_seed_affinity: t('discovery_hint_reason_domestic_seed_affinity', 'Domestic seed affinity'),
            chipset_driver_fit: t('discovery_hint_reason_chipset_driver_fit', 'Chipset driver fit'),
        };
        return labels[value] || value.replaceAll('_', ' ');
    };

    const hintResultSummary = useMemo(() => {
        const summary = {
            hinted: 0,
            success: 0,
            failed: 0,
            available: 0,
            topVendor: '',
        };
        const vendorCounts = {};
        for (const dev of Array.isArray(results) ? results : []) {
            if (!hasHintEvidence(dev)) continue;
            summary.hinted += 1;
            const outcome = getHintOutcome(dev);
            if (outcome === 'success') summary.success += 1;
            else if (outcome === 'failed') summary.failed += 1;
            else if (outcome === 'available') summary.available += 1;
            const vendor = String(getHintEngine(dev)?.normalized_vendor || getHintTelemetry(dev)?.normalized_vendor || '').trim().toLowerCase();
            if (vendor) vendorCounts[vendor] = (vendorCounts[vendor] || 0) + 1;
        }
        const topVendorEntry = Object.entries(vendorCounts).sort((a, b) => b[1] - a[1])[0];
        if (topVendorEntry) summary.topVendor = topVendorEntry[0];
        return summary;
    }, [results]);

    const toggleExpanded = (id) => {
        setExpanded(prev => ({ ...prev, [id]: !prev?.[id] }));
    };

    const getSeverityStyle = (sev) => {
        const s = String(sev || 'info').toLowerCase();
        if (s === 'error') return 'bg-red-100 text-red-700 border-red-200';
        if (s === 'warn' || s === 'warning') return 'bg-amber-100 text-amber-700 border-amber-200';
        return 'bg-gray-100 text-gray-700 border-gray-200';
    };

    const renderIssuesAndEvidence = (dev) => {
        const issues = getIssues(dev);
        const evidence = getEvidence(dev);
        const openPorts = Array.isArray(evidence?.open_ports) ? evidence.open_ports : [];
        const probe = (evidence && typeof evidence.snmp_probe === 'object' && evidence.snmp_probe !== null) ? evidence.snmp_probe : null;
        const hintEngine = getHintEngine(dev);
        const hintTelemetry = getHintTelemetry(dev);
        const sshProbe = getSshProbe(dev);
        const hintOutcome = getHintOutcomeMeta(dev);
        const hintCandidates = Array.isArray(hintEngine?.driver_candidates)
            ? hintEngine.driver_candidates.slice(0, 3)
            : Array.isArray(hintTelemetry?.candidates)
                ? hintTelemetry.candidates.slice(0, 3)
                : [];
        const hintCacheContext = (hintEngine && typeof hintEngine.cache_context === 'object' && hintEngine.cache_context !== null)
            ? hintEngine.cache_context
            : {};
        const hasHintCard = hasHintEvidence(dev);

        return (
            <div className={`grid grid-cols-1 ${hasHintCard ? 'xl:grid-cols-3' : 'md:grid-cols-2'} gap-4`}>
                <div className="bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                    <div className="font-bold mb-2">Issues</div>
                    {issues.length === 0 ? (
                        <div className="text-sm text-gray-500">No issues detected.</div>
                    ) : (
                        <div className="space-y-2">
                            {issues.map((it, idx) => (
                                <div key={`${it?.code || 'issue'}-${idx}`} className="flex items-start gap-2">
                                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold border ${getSeverityStyle(it?.severity)}`}>
                                        {String(it?.severity || 'info').toUpperCase()}
                                    </span>
                                    <div className="text-sm">
                                        <div className="font-semibold text-gray-900 dark:text-white">{it?.message || it?.code || 'Issue'}</div>
                                        {it?.hint && <div className="text-gray-600 dark:text-gray-400 mt-0.5">{it.hint}</div>}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
                {hasHintCard && (
                    <div className="bg-sky-50/70 dark:bg-sky-950/10 border border-sky-200 dark:border-sky-900 rounded-lg p-4">
                        <div className="flex items-start justify-between gap-3 mb-2">
                            <div>
                                <div className="font-bold text-sky-900 dark:text-sky-100">{t('discovery_hint_title', 'Hint-driven identification')}</div>
                                {hintOutcome && (
                                    <div className="text-xs text-sky-800 dark:text-sky-200 mt-1">
                                        {hintOutcome.description}
                                    </div>
                                )}
                            </div>
                            {hintOutcome && (
                                <span className={`px-2 py-1 rounded-full text-xs font-bold border ${hintOutcome.className}`}>
                                    {hintOutcome.label}
                                </span>
                            )}
                        </div>
                        <div className="space-y-3 text-sm">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                <div className="rounded-lg border border-sky-100 dark:border-sky-900/60 bg-white/70 dark:bg-black/20 px-3 py-2">
                                    <div className="text-xs text-gray-500">{t('discovery_hint_vendor_family', 'Vendor family')}</div>
                                    <div className="font-semibold text-gray-900 dark:text-white">{hintEngine?.normalized_vendor || hintTelemetry?.normalized_vendor || dev?.vendor || t('common_unknown', 'Unknown')}</div>
                                </div>
                                <div className="rounded-lg border border-sky-100 dark:border-sky-900/60 bg-white/70 dark:bg-black/20 px-3 py-2">
                                    <div className="text-xs text-gray-500">{t('discovery_hint_oui', 'OUI')}</div>
                                    <div className="font-mono text-xs text-gray-900 dark:text-white">{hintEngine?.oui_prefix || hintTelemetry?.oui_prefix || '-'}</div>
                                </div>
                                <div className="rounded-lg border border-sky-100 dark:border-sky-900/60 bg-white/70 dark:bg-black/20 px-3 py-2">
                                    <div className="text-xs text-gray-500">{t('discovery_hint_seed_ip', 'Seed IP')}</div>
                                    <div className="font-mono text-xs text-gray-900 dark:text-white">{hintCacheContext?.seed_ip || hintTelemetry?.seed_ip || '-'}</div>
                                </div>
                                <div className="rounded-lg border border-sky-100 dark:border-sky-900/60 bg-white/70 dark:bg-black/20 px-3 py-2">
                                    <div className="text-xs text-gray-500">{t('discovery_hint_seed_vendor', 'Seed vendor')}</div>
                                    <div className="font-semibold text-gray-900 dark:text-white">{hintCacheContext?.seed_vendor || hintTelemetry?.seed_vendor || '-'}</div>
                                </div>
                                <div className="rounded-lg border border-sky-100 dark:border-sky-900/60 bg-white/70 dark:bg-black/20 px-3 py-2">
                                    <div className="text-xs text-gray-500">{t('discovery_hint_neighbor', 'Neighbor')}</div>
                                    <div className="font-mono text-xs text-gray-900 dark:text-white">{hintCacheContext?.neighbor_name || hintTelemetry?.neighbor_name || hintTelemetry?.neighbor_mgmt_ip || '-'}</div>
                                </div>
                                <div className="rounded-lg border border-sky-100 dark:border-sky-900/60 bg-white/70 dark:bg-black/20 px-3 py-2">
                                    <div className="text-xs text-gray-500">{t('discovery_hint_interface', 'Seed interface')}</div>
                                    <div className="font-mono text-xs text-gray-900 dark:text-white">{hintCacheContext?.local_interface || hintTelemetry?.local_interface || '-'}</div>
                                </div>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                <div className="rounded-lg border border-sky-100 dark:border-sky-900/60 bg-white/70 dark:bg-black/20 px-3 py-2">
                                    <div className="text-xs text-gray-500">{t('discovery_hint_chosen_driver', 'Chosen driver')}</div>
                                    <div className="font-mono text-xs text-gray-900 dark:text-white">{formatDriverLabel(hintTelemetry?.chosen_driver || sshProbe?.driver)}</div>
                                </div>
                                <div className="rounded-lg border border-sky-100 dark:border-sky-900/60 bg-white/70 dark:bg-black/20 px-3 py-2">
                                    <div className="text-xs text-gray-500">{t('discovery_hint_final_driver', 'Final driver')}</div>
                                    <div className="font-mono text-xs text-gray-900 dark:text-white">{formatDriverLabel(hintTelemetry?.final_driver || dev?.device_type)}</div>
                                </div>
                            </div>
                            <div>
                                <div className="text-xs text-gray-500 mb-1">{t('discovery_hint_candidate_drivers', 'Candidate drivers')}</div>
                                {hintCandidates.length === 0 ? (
                                    <div className="text-xs text-gray-400">{t('discovery_hint_no_candidates', 'No ranked driver candidates were stored for this result.')}</div>
                                ) : (
                                    <div className="space-y-2">
                                        {hintCandidates.map((candidate, idx) => (
                                            <div key={`${candidate?.driver || 'candidate'}-${idx}`} className="rounded-lg border border-sky-100 dark:border-sky-900/60 bg-white/70 dark:bg-black/20 px-3 py-2">
                                                <div className="flex items-center justify-between gap-2">
                                                    <span className="font-mono text-xs text-gray-900 dark:text-white">{formatDriverLabel(candidate?.driver)}</span>
                                                    <span className="text-[11px] font-bold px-2 py-1 rounded bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-200 border border-sky-200 dark:border-sky-800">
                                                        {Math.round(Number(candidate?.score || 0) * 100)}%
                                                    </span>
                                                </div>
                                                <div className="flex flex-wrap gap-1 mt-2">
                                                    {(Array.isArray(candidate?.reasons) ? candidate.reasons : []).map((reason, reasonIdx) => (
                                                        <span key={`${candidate?.driver || 'candidate'}-reason-${reasonIdx}`} className="px-2 py-0.5 rounded-full text-[11px] border border-sky-200 dark:border-sky-800 bg-sky-50 dark:bg-sky-950/20 text-sky-800 dark:text-sky-200">
                                                            {formatHintReason(reason)}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                            {hintTelemetry?.failure_reason && (
                                <div className="rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50/70 dark:bg-amber-950/20 px-3 py-2">
                                    <div className="text-xs text-amber-700 dark:text-amber-300">{t('discovery_hint_failure_reason', 'Fallback result')}</div>
                                    <div className="font-mono text-xs text-amber-900 dark:text-amber-100 mt-1">
                                        {String(hintTelemetry.failure_reason || '')}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}
                <div className="bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                    <div className="font-bold mb-2">Evidence</div>
                    <div className="text-sm space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-gray-500">Open ports:</span>
                            {openPorts.length > 0 ? (
                                openPorts.slice(0, 20).map((p) => (
                                    <span key={p} className="text-xs font-mono px-2 py-1 rounded bg-white dark:bg-black/30 border border-gray-200 dark:border-gray-700">
                                        {p}
                                    </span>
                                ))
                            ) : (
                                <span className="text-xs text-gray-400">-</span>
                            )}
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-gray-500">SNMP probe:</span>
                            {probe ? (
                                <>
                                    <span className={`text-xs font-mono px-2 py-1 rounded border ${probe.lldp ? 'bg-green-100 text-green-700 border-green-200' : 'bg-gray-100 text-gray-600 border-gray-200'}`}>LLDP {probe.lldp ? 'OK' : 'NO'}</span>
                                    <span className={`text-xs font-mono px-2 py-1 rounded border ${probe.bridge ? 'bg-green-100 text-green-700 border-green-200' : 'bg-gray-100 text-gray-600 border-gray-200'}`}>BRIDGE {probe.bridge ? 'OK' : 'NO'}</span>
                                    <span className={`text-xs font-mono px-2 py-1 rounded border ${probe.qbridge ? 'bg-green-100 text-green-700 border-green-200' : 'bg-gray-100 text-gray-600 border-gray-200'}`}>Q-BRIDGE {probe.qbridge ? 'OK' : 'NO'}</span>
                                </>
                            ) : (
                                <span className="text-xs text-gray-400">-</span>
                            )}
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-gray-500">sysObjectID:</span>
                            <span className="text-xs font-mono px-2 py-1 rounded bg-white dark:bg-black/30 border border-gray-200 dark:border-gray-700">
                                {evidence?.snmp_sys_oid || dev?.sys_object_id || '-'}
                            </span>
                            <span className="text-gray-500">SNMP ver:</span>
                            <span className="text-xs font-mono px-2 py-1 rounded bg-white dark:bg-black/30 border border-gray-200 dark:border-gray-700">
                                {evidence?.snmp_version || (typeof evidence?.snmp_mp_model === 'number' ? (evidence.snmp_mp_model === 1 ? 'v2c' : 'v1') : '-') }
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    const needsLowConfidenceConfirm = (dev) => {
        const conf = typeof dev?.vendor_confidence === 'number' ? dev.vendor_confidence : null;
        const lowVendor = conf !== null ? conf < 0.5 : true;
        const snmpUnreachable = dev?.snmp_status !== 'reachable';
        return lowVendor || snmpUnreachable;
    };

    const getInventoryDeviceId = (dev) => {
        const raw = dev?.inventory_device_id ?? dev?.matched_device_id ?? null;
        const deviceId = Number(raw || 0);
        return Number.isFinite(deviceId) && deviceId > 0 ? deviceId : null;
    };

    const hydrateReviewContext = async (inventoryDeviceId, discoveredId = null) => {
        if (!inventoryDeviceId) return;
        setReviewLoading(true);
        try {
            const needsCatalog = profileCatalog.length === 0;
            const needsGroups = serviceGroups.length === 0;
            const [deviceRes, summaryRes, recommendationRes, catalogRes, groupsRes] = await Promise.all([
                DeviceService.getDetail(inventoryDeviceId),
                DeviceService.getManagedSummary().catch(() => ({ data: null })),
                MonitoringProfileService.getRecommendation(inventoryDeviceId).catch(() => ({ data: null })),
                needsCatalog ? MonitoringProfileService.getCatalog().catch(() => ({ data: { profiles: [] } })) : Promise.resolve(null),
                needsGroups ? ServiceGroupService.list().catch(() => ({ data: [] })) : Promise.resolve(null),
            ]);

            const device = deviceRes?.data || null;
            const recommendation = recommendationRes?.data?.recommendation || null;
            const nextSummary = summaryRes?.data || null;
            const nextCatalog = needsCatalog
                ? (Array.isArray(catalogRes?.data?.profiles) ? catalogRes.data.profiles : [])
                : profileCatalog;
            const nextGroups = needsGroups
                ? (Array.isArray(groupsRes?.data) ? groupsRes.data : [])
                : serviceGroups;

            setManagedSummary(nextSummary);
            if (needsCatalog) setProfileCatalog(nextCatalog);
            if (needsGroups) setServiceGroups(nextGroups);
            setReviewSiteId(device?.site_id ? String(device.site_id) : '');
            setReviewProfileId(recommendation?.profile_id ? String(recommendation.profile_id) : '');
            setReviewServiceGroupId('');
            setReviewContext({
                discoveredId,
                inventoryDeviceId,
                device,
                recommendation,
            });
        } catch (error) {
            toast.error(t('discovery_post_review_load_failed', 'Failed to load post-discovery review.'));
        } finally {
            setReviewLoading(false);
        }
    };

    const handleOpenPostDiscoveryReview = async (dev) => {
        const inventoryDeviceId = getInventoryDeviceId(dev);
        if (!inventoryDeviceId) {
            toast.error(t('discovery_post_review_missing_device', 'No managed inventory device is linked to this discovery result yet.'));
            return;
        }
        await hydrateReviewContext(inventoryDeviceId, dev?.id || null);
    };

    const handlePromoteManagedFromReview = async () => {
        if (!reviewContext?.inventoryDeviceId) return;
        setReviewActionLoading('manage');
        try {
            const res = await DeviceService.promoteToManaged(reviewContext.inventoryDeviceId);
            setManagedSummary(res?.data?.summary || managedSummary);
            toast.success(t('devices_manage_promoted', 'This node is now actively managed.'));
            await hydrateReviewContext(reviewContext.inventoryDeviceId, reviewContext?.discoveredId || null);
        } catch (error) {
            const message =
                error?.response?.data?.detail?.message ||
                error?.response?.data?.message ||
                t('devices_manage_promote_failed', 'Unable to assign a managed slot.');
            toast.error(message);
        } finally {
            setReviewActionLoading('');
        }
    };

    const handleReleaseManagedFromReview = async () => {
        if (!reviewContext?.inventoryDeviceId) return;
        setReviewActionLoading('release');
        try {
            const res = await DeviceService.releaseManagement(reviewContext.inventoryDeviceId);
            setManagedSummary(res?.data?.summary || managedSummary);
            toast.success(t('devices_manage_released', 'The managed slot was released.'));
            await hydrateReviewContext(reviewContext.inventoryDeviceId, reviewContext?.discoveredId || null);
        } catch (error) {
            const message =
                error?.response?.data?.detail?.message ||
                error?.response?.data?.message ||
                t('devices_manage_release_failed', 'Unable to release this managed slot.');
            toast.error(message);
        } finally {
            setReviewActionLoading('');
        }
    };

    const handleAssignSiteFromReview = async () => {
        if (!reviewContext?.inventoryDeviceId || !reviewSiteId) return;
        setReviewActionLoading('site');
        try {
            await DeviceService.assignDevicesToSite(Number(reviewSiteId), [reviewContext.inventoryDeviceId]);
            toast.success(t('discovery_post_review_site_saved', 'Site assignment saved.'));
            await hydrateReviewContext(reviewContext.inventoryDeviceId, reviewContext?.discoveredId || null);
        } catch (error) {
            toast.error(t('discovery_post_review_site_failed', 'Failed to assign the site.'));
        } finally {
            setReviewActionLoading('');
        }
    };

    const handleAssignProfileFromReview = async () => {
        if (!reviewContext?.inventoryDeviceId || !reviewProfileId) return;
        setReviewActionLoading('profile');
        try {
            const res = await MonitoringProfileService.assignToDevice(reviewContext.inventoryDeviceId, Number(reviewProfileId));
            setReviewContext((prev) => prev ? { ...prev, recommendation: res?.data?.recommendation || prev.recommendation } : prev);
            toast.success(t('discovery_post_review_profile_saved', 'Monitoring profile applied.'));
            await hydrateReviewContext(reviewContext.inventoryDeviceId, reviewContext?.discoveredId || null);
        } catch (error) {
            toast.error(t('discovery_post_review_profile_failed', 'Failed to apply the monitoring profile.'));
        } finally {
            setReviewActionLoading('');
        }
    };

    const handleRecomputeProfileFromReview = async () => {
        if (!reviewContext?.inventoryDeviceId) return;
        setReviewActionLoading('profile-recompute');
        try {
            const res = await MonitoringProfileService.recomputeForDevice(reviewContext.inventoryDeviceId);
            setReviewContext((prev) => prev ? { ...prev, recommendation: res?.data?.recommendation || prev.recommendation } : prev);
            setReviewProfileId(String(res?.data?.recommendation?.profile_id || ''));
            toast.success(t('discovery_post_review_profile_recomputed', 'Monitoring profile recommendation refreshed.'));
        } catch (error) {
            toast.error(t('discovery_post_review_profile_recompute_failed', 'Failed to refresh the monitoring recommendation.'));
        } finally {
            setReviewActionLoading('');
        }
    };

    const handleAddServiceGroupFromReview = async () => {
        if (!reviewContext?.inventoryDeviceId || !reviewServiceGroupId) return;
        setReviewActionLoading('group');
        try {
            await ServiceGroupService.addDevice(Number(reviewServiceGroupId), reviewContext.inventoryDeviceId);
            toast.success(t('discovery_post_review_group_saved', 'Service group linked.'));
            setReviewServiceGroupId('');
        } catch (error) {
            toast.error(t('discovery_post_review_group_failed', 'Failed to link the service group.'));
        } finally {
            setReviewActionLoading('');
        }
    };

    const closeReviewContext = () => {
        setReviewContext(null);
        setReviewSiteId('');
        setReviewProfileId('');
        setReviewServiceGroupId('');
    };

    const handleApprove = async (id) => {
        const dev = results.find(r => r.id === id);
        if (dev && needsLowConfidenceConfirm(dev)) {
            const confPct = typeof dev.vendor_confidence === 'number' ? `${Math.round(dev.vendor_confidence * 100)}%` : 'unknown';
            const ok = window.confirm(
                t('discovery_low_conf_confirm_fmt', 'Low-confidence discovery result.\n\nIP: {ip}\nVendor: {vendor} ({confidence})\nSNMP: {snmp}\n\nAdd to inventory anyway?').replace('{ip}', String(dev.ip_address || '')).replace('{vendor}', String(dev.vendor || t('discovery_unknown', 'Unknown'))).replace('{confidence}', String(confPct)).replace('{snmp}', String(dev.snmp_status || ''))
            );
            if (!ok) return;
        }
        try {
            const res = await DiscoveryService.approveDevice(id);
            const inventoryDeviceId = Number(res?.data?.device_id || 0) || null;
            // Update UI
            setResults(prev => prev.map(dev =>
                dev.id === id
                    ? {
                        ...dev,
                        status: 'approved',
                        inventory_device_id: inventoryDeviceId || getInventoryDeviceId(dev),
                    }
                    : dev
            ));
            if (inventoryDeviceId) {
                await hydrateReviewContext(inventoryDeviceId, id);
            }
        } catch (err) {
            toast.error(t('discovery_approve_failed', 'Failed to approve device'));
        }
    };

    const handleIgnore = async (id) => {
        try {
            await DiscoveryService.ignoreDevice(id);
            setResults(prev => prev.map(dev =>
                dev.id === id ? { ...dev, status: 'ignored' } : dev
            ));
        } catch (err) {
            toast.error(t('discovery_ignore_failed', 'Failed to ignore device'));
        }
    };

    const handleApproveAll = async () => {
        const low = results.filter(d => d.status === 'new' && needsLowConfidenceConfirm(d));
        if (low.length > 0) {
            const ok = window.confirm(
                t('discovery_approve_all_confirm_fmt', 'Approve all new devices includes {count} low-confidence result(s).\n\nProceed anyway?')
                    .replace('{count}', String(low.length))
            );
            if (!ok) return;
        }
        try {
            await DiscoveryService.approveAll(jobId, { policy: false });
            await loadResults();
        } catch (err) {
            toast.error(t('discovery_approve_all_failed', 'Failed to approve all devices'));
        }
    };

    const renderSkipReasonAction = (reason, count) => {
        const r = String(reason || '').trim();
        const n = Number(count || 0);
        if (n <= 0) return null;
        if (r === 'low_confidence_link') {
            return (
                <button
                    key={r}
                    onClick={() => navigate('/topology', { state: { showCandidates: true, candidateJobId: jobId, candidateStatus: 'low_confidence' } })}
                    className="px-2 py-1 rounded border border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-200 hover:bg-amber-100/70 dark:hover:bg-amber-900/30"
                >
                    {r}:{n} ({t('discovery_review_queue', 'Review Queue')})
                </button>
            );
        }
        return (
            <span key={r} className="px-2 py-1 rounded border border-blue-300 dark:border-blue-700 text-blue-800 dark:text-blue-200">
                {r}:{n}
            </span>
        );
    };

    const queueInsightsPanel = (
        <div className="space-y-3">
            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] p-3">
                <div className="text-xs font-semibold text-gray-700 dark:text-gray-200 mb-2">{t('discovery_queue_insights', 'Queue Insights')}</div>
                <div className="inline-flex rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden w-full mb-2">
                    <button
                        type="button"
                        onClick={() => setKpiWindowDays(7)}
                        className={`flex-1 px-3 py-1.5 text-xs font-bold ${kpiWindowDays === 7 ? 'bg-blue-600 text-white' : 'bg-white dark:bg-[#1b1d1f] text-gray-600 dark:text-gray-300'}`}
                    >
                        7d
                    </button>
                    <button
                        type="button"
                        onClick={() => setKpiWindowDays(30)}
                        className={`flex-1 px-3 py-1.5 text-xs font-bold border-l border-gray-200 dark:border-gray-800 ${kpiWindowDays === 30 ? 'bg-blue-600 text-white' : 'bg-white dark:bg-[#1b1d1f] text-gray-600 dark:text-gray-300'}`}
                    >
                        30d
                    </button>
                </div>
                <select
                    value={kpiSiteId}
                    onChange={(e) => setKpiSiteId(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] outline-none"
                >
                    <option value="">{t('obs_all_sites', 'All Sites')}</option>
                    {(sites || []).map((s) => (
                        <option key={`disc-site-${s.id}`} value={String(s.id)}>{String(s.name || `Site ${s.id}`)}</option>
                    ))}
                </select>
            </div>

            <div className="grid grid-cols-2 gap-2">
                <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] px-3 py-2.5">
                    <div className="text-[11px] text-gray-500">{t('discovery_first_map', 'First Map')}</div>
                    <div className="text-sm font-semibold">{kpiSummaryLoading ? '...' : `${kpiSummary?.kpi?.first_map_seconds_avg ?? '-'}s`}</div>
                </div>
                <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] px-3 py-2.5">
                    <div className="text-[11px] text-gray-500">{t('dashboard_auto_action_rate', 'Auto Reflection')}</div>
                    <div className="text-sm font-semibold">{kpiSummaryLoading ? '...' : `${Number(kpiSummary?.kpi?.auto_reflection_rate_pct || 0).toFixed(2)}%`}</div>
                </div>
                <div className="rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50/40 dark:bg-amber-950/10 px-3 py-2.5">
                    <div className="text-[11px] text-amber-700 dark:text-amber-300">{t('discovery_backlog', 'Backlog')}</div>
                    <div className="text-sm font-semibold text-amber-800 dark:text-amber-200">{kpiSummaryLoading ? '...' : Number(candidateQueueSummary?.totals?.backlog_total || 0)}</div>
                </div>
                <div className="rounded-xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50/40 dark:bg-emerald-950/10 px-3 py-2.5">
                    <div className="text-[11px] text-emerald-700 dark:text-emerald-300">{t('discovery_resolved_24h', 'Resolved (24h)')}</div>
                    <div className="text-sm font-semibold text-emerald-800 dark:text-emerald-200">{kpiSummaryLoading ? '...' : Number(candidateQueueSummary?.totals?.resolved_24h || 0)}</div>
                </div>
            </div>

            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] px-3 py-3">
                <div className="flex items-center justify-between mb-2">
                    <div className="text-xs font-semibold text-gray-700 dark:text-gray-200">{t('discovery_operational_alerts', 'Operational Alerts')}</div>
                    <div className={`text-[11px] font-bold ${
                        opsAlerts?.status === 'critical'
                            ? 'text-red-600 dark:text-red-300'
                            : opsAlerts?.status === 'warning'
                                ? 'text-amber-600 dark:text-amber-300'
                                : 'text-emerald-600 dark:text-emerald-300'
                    }`}>
                        {kpiSummaryLoading ? t('common_loading', 'Loading...') : String(opsAlerts?.status || t('discovery_healthy', 'healthy'))}
                    </div>
                </div>
                <div className="space-y-1.5">
                    {(opsAlerts?.alerts || []).slice(0, 4).map((a) => (
                        <div key={`ops-alert-${a?.code}`} className="text-[11px] rounded-lg border border-gray-100 dark:border-gray-800 px-2 py-1.5">
                            <div className={`font-bold ${
                                a?.severity === 'critical'
                                    ? 'text-red-600 dark:text-red-300'
                                    : 'text-amber-600 dark:text-amber-300'
                            }`}>
                                {String(a?.severity || 'warning').toUpperCase()} - {String(a?.title || a?.code || '')}
                            </div>
                            <div className="text-gray-500 mt-0.5">
                                {Number(a?.value || 0).toFixed(2)} / {Number(a?.threshold || 0).toFixed(2)}
                            </div>
                        </div>
                    ))}
                    {(!opsAlerts?.alerts || opsAlerts.alerts.length === 0) && (
                        <div className="text-xs text-emerald-700 dark:text-emerald-300">{t('discovery_no_active_alerts', 'No active alerts.')}</div>
                    )}
                </div>
            </div>

            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] px-3 py-3">
                <div className="text-xs font-semibold text-gray-700 dark:text-gray-200 mb-2">
                    {Number(kpiWindowDays) >= 30
                        ? t('discovery_queue_weekly_trend_fmt', 'Queue Weekly Trend ({days}d)').replace('{days}', String(Number(kpiWindowDays || 30)))
                        : t('discovery_queue_daily_trend_fmt', 'Queue Daily Trend ({days}d)').replace('{days}', String(Number(kpiWindowDays || 7)))}
                </div>
                <div className="space-y-2">
                    {trendRows.map((d, idx) => {
                        const backlog = Number(d?.backlog_total || 0);
                        const resolved = Number(d?.resolved_total || 0);
                        const maxv = Math.max(backlog, resolved, 1);
                        return (
                            <div key={`trend-side-${idx}-${String(d?.label || d?.date || '')}`} className="grid grid-cols-[80px_1fr_1fr] items-center gap-2 text-[11px]">
                                <div className="text-gray-500">{String(d?.label || d?.date || '').slice(5, 11)}</div>
                                <div className="flex items-center gap-1">
                                    <div className="h-1.5 w-full rounded-full bg-amber-100 dark:bg-amber-900/30 overflow-hidden">
                                        <div className="h-1.5 rounded-full bg-amber-500/80" style={{ width: `${Math.max(4, Math.round((backlog / maxv) * 100))}%` }} />
                                    </div>
                                    <span className="text-amber-700 dark:text-amber-300 tabular-nums">{backlog}</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <div className="h-1.5 w-full rounded-full bg-emerald-100 dark:bg-emerald-900/30 overflow-hidden">
                                        <div className="h-1.5 rounded-full bg-emerald-500/80" style={{ width: `${Math.max(4, Math.round((resolved / maxv) * 100))}%` }} />
                                    </div>
                                    <span className="text-emerald-700 dark:text-emerald-300 tabular-nums">{resolved}</span>
                                </div>
                            </div>
                        );
                    })}
                    {trendRows.length === 0 && (
                        <div className="text-xs text-gray-500">{kpiSummaryLoading ? t('common_loading', 'Loading...') : t('discovery_no_trend_data', 'No trend data.')}</div>
                    )}
                </div>
            </div>

            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] px-3 py-3">
                <div className="text-xs font-semibold text-gray-700 dark:text-gray-200 mb-2">Top Jobs by Queue</div>
                <div className="space-y-1.5">
                    {(candidateQueueTrend?.jobs || []).slice(0, 5).map((j) => (
                        <button
                            key={`job-side-${j?.job_id}`}
                            onClick={() => navigate('/topology', { state: { showCandidates: true, candidateJobId: j?.job_id, candidateStatus: 'low_confidence' } })}
                            className="w-full text-left rounded-lg border border-gray-100 dark:border-gray-800 px-2 py-1.5 text-[11px] hover:bg-gray-50 dark:hover:bg-gray-800/40"
                        >
                            <div className="font-semibold text-blue-600 dark:text-blue-400">Job #{j?.job_id}</div>
                            <div className="mt-0.5 flex items-center gap-2">
                                <span className="text-amber-700 dark:text-amber-300">B {Number(j?.backlog_total || 0)}</span>
                                <span className="text-emerald-700 dark:text-emerald-300">R {Number(j?.resolved_total || 0)}</span>
                            </div>
                        </button>
                    ))}
                    {(!candidateQueueTrend?.jobs || candidateQueueTrend.jobs.length === 0) && (
                        <div className="text-xs text-gray-500">{kpiSummaryLoading ? t('common_loading', 'Loading...') : t('discovery_no_job_data', 'No job data.')}</div>
                    )}
                </div>
            </div>
        </div>
    );

    return (
        <div className="p-3 sm:p-4 md:p-6 h-full min-h-0 bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white overflow-hidden">
            <div className="h-full min-h-0 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_340px] gap-4">
                <div className="min-w-0 min-h-0 h-full overflow-y-auto custom-scrollbar">
                {/* Step 1: Input Analysis */}
            {step === 1 && (
                <div className="max-w-2xl mx-auto w-full bg-white dark:bg-[#1b1d1f] p-6 sm:p-8 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-800 animate-scale-in">
                    <div className="flex justify-center mb-6">
                        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-full text-blue-500 animate-pulse">
                            <Radar size={48} />
                        </div>
                    </div>
                    <h2 className="text-2xl font-bold text-center text-gray-900 dark:text-white mb-2">{t('discovery_title', 'Network Discovery')}</h2>
                    <div className="flex justify-center mb-4">
                        <div className="inline-flex p-1 rounded-xl bg-gray-100 dark:bg-black/30 border border-gray-200 dark:border-gray-800">
                            <button
                                type="button"
                                onClick={() => setScanMode('cidr')}
                                data-testid="discovery-mode-cidr"
                                className={`px-4 py-2 rounded-lg text-sm font-bold transition-colors ${scanMode === 'cidr' ? 'bg-white dark:bg-[#1b1d1f] shadow text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'}`}
                            >
                                {t('discovery_mode_cidr', 'CIDR Scan')}
                            </button>
                            <button
                                type="button"
                                onClick={() => setScanMode('seed')}
                                data-testid="discovery-mode-seed"
                                className={`px-4 py-2 rounded-lg text-sm font-bold transition-colors ${scanMode === 'seed' ? 'bg-white dark:bg-[#1b1d1f] shadow text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'}`}
                            >
                                {t('discovery_mode_seed', 'Seed Crawl')}
                            </button>
                        </div>
                    </div>
                    <p className="text-center text-gray-500 mb-8">
                        {scanMode === 'seed'
                            ? t('discovery_seed_desc', 'Start from a seed device and crawl neighbors recursively.')
                            : t('discovery_cidr_desc', 'Scan a subnet to automatically find and identify devices.')}
                    </p>

                    <div className="mb-6 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
                        <div className="flex items-center justify-between gap-3">
                            <div className="font-bold text-sm">{t('discovery_scope_current', 'Current Scope (Read Only)')}</div>
                            <div className="text-[11px] text-gray-500">
                                {currentScope.mode === 'crawl' ? t('discovery_mode_seed_applied', 'Seed Crawl applied') : t('discovery_mode_cidr_applied', 'CIDR Scan applied')}
                            </div>
                        </div>
                        <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                            <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-lg p-3">
                                <div className="font-bold text-gray-700 dark:text-gray-200 mb-1">{t('discovery_scope_include', 'Include CIDRs')}</div>
                                <div className="text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                                    {currentScope.includeCidrs.length ? currentScope.includeCidrs.join(', ') : t('discovery_scope_empty_allow_all', '(empty = allow all)')}
                                </div>
                            </div>
                            <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-lg p-3">
                                <div className="font-bold text-gray-700 dark:text-gray-200 mb-1">{t('discovery_scope_exclude', 'Exclude CIDRs')}</div>
                                <div className="text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                                    {currentScope.excludeCidrs.length ? currentScope.excludeCidrs.join(', ') : t('discovery_scope_empty', '(empty)')}
                                </div>
                            </div>
                            <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-lg p-3 sm:col-span-2">
                                <div className="font-bold text-gray-700 dark:text-gray-200 mb-1">{t('discovery_scope_prefer_private', 'Prefer Private')}</div>
                                <div className="text-gray-600 dark:text-gray-400">{currentScope.preferPrivate ? t('common_active', 'active') : t('common_inactive', 'inactive')}</div>
                            </div>
                        </div>
                    </div>

                    <form onSubmit={handleStartScan} className="space-y-4">
                        {scanMode === 'cidr' ? (
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('discovery_target_network', 'Target Network (CIDR)')}</label>
                                <input
                                    type="text"
                                    value={cidr}
                                    onChange={(e) => setCidr(e.target.value)}
                                    data-testid="discovery-cidr-input"
                                    placeholder={t('discovery_cidr_placeholder', 'e.g. 192.168.1.0/24')}
                                    className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                    required
                                />
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('discovery_seed_ip', 'Seed IP')}</label>
                                    <input
                                        type="text"
                                        value={seedIp}
                                        onChange={(e) => setSeedIp(e.target.value)}
                                        data-testid="discovery-seed-ip"
                                        placeholder={t('discovery_seed_ip_placeholder', 'e.g. 192.168.0.1')}
                                        className={`w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all ${seedIp && !seedScopeCheck.ok ? 'border-red-400 dark:border-red-600' : 'border-gray-200 dark:border-gray-700'}`}
                                    />
                                    <div className="text-xs text-gray-500 mt-1">
                                        {t('discovery_seed_optional', 'If set, Seed Device selection is optional.')}
                                    </div>
                                    {effectiveSeedIp && !seedScopeCheck.ok && (
                                        <div className="mt-2 text-xs font-bold text-red-600 dark:text-red-400 flex items-start gap-2">
                                            <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                                            <div>
                                                {t('discovery_scope_warning_fmt', 'Scope warning: {reason}').replace('{reason}', String(seedScopeCheck.reason || ''))}
                                                <div className="text-[11px] text-gray-600 dark:text-gray-500 font-medium mt-0.5">
                                                    {t('discovery_scope_hint', 'Check Include/Exclude CIDR in Settings > Auto Discovery Scope.')}
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('discovery_seed_device', 'Seed Device')}</label>
                                    <select
                                        value={seedDeviceId}
                                        onChange={(e) => setSeedDeviceId(e.target.value)}
                                        className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                        disabled={loadingSeeds}
                                    >
                                        {seedDevices.length === 0 ? (
                                            <option value="">{loadingSeeds ? t('common_loading', 'Loading...') : t('discovery_no_devices', 'No devices found')}</option>
                                        ) : (
                                            seedDevices.map((d) => (
                                                <option key={d.id} value={String(d.id)}>
                                                    {d.name || d.hostname || `Device ${d.id}`} ({d.ip_address})
                                                </option>
                                            ))
                                        )}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('discovery_max_depth', 'Max Depth')}</label>
                                    <input
                                        type="number"
                                        min={1}
                                        max={6}
                                        value={maxDepth}
                                        onChange={(e) => setMaxDepth(Number(e.target.value))}
                                        className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                    />
                                </div>
                                <div className="sm:col-span-2">
                                    <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                                        <input
                                            type="checkbox"
                                            checked={plugAndScanMode}
                                            onChange={(e) => setPlugAndScanMode(e.target.checked)}
                                        />
                                        {t('discovery_plug_scan_mode', 'Plug and Scan mode (auto approve new + auto topology jump on completion)')}
                                    </label>
                                </div>
                            </div>
                        )}

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('discovery_snmp_version', 'SNMP Version')}</label>
                                <select
                                    value={snmpVersion}
                                    onChange={(e) => setSnmpVersion(e.target.value)}
                                    className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                >
                                    <option value="v2c">v2c</option>
                                    <option value="v3">v3</option>
                                    <option value="v1">v1</option>
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SNMP Port</label>
                                <input
                                    type="number"
                                    min={1}
                                    max={65535}
                                    value={snmpPort}
                                    onChange={(e) => setSnmpPort(Number(e.target.value))}
                                    className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                />
                            </div>
                        </div>

                        {String(snmpVersion).toLowerCase() !== 'v3' ? (
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SNMP Community</label>
                                <input
                                    type="password"
                                    value={community}
                                    onChange={(e) => setCommunity(e.target.value)}
                                    placeholder={t('discovery_snmp_community_placeholder', 'public')}
                                    className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                />
                            </div>
                        ) : (
                            <div className="space-y-4">
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">v3 Username</label>
                                        <input
                                            type="text"
                                            value={snmpV3Username}
                                            onChange={(e) => setSnmpV3Username(e.target.value)}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                            required
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Security Level</label>
                                        <select
                                            value={snmpV3SecurityLevel}
                                            onChange={(e) => setSnmpV3SecurityLevel(e.target.value)}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                        >
                                            <option value="authPriv">authPriv</option>
                                            <option value="authNoPriv">authNoPriv</option>
                                            <option value="noAuthNoPriv">noAuthNoPriv</option>
                                        </select>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Auth Protocol</label>
                                        <select
                                            value={snmpV3AuthProto}
                                            onChange={(e) => setSnmpV3AuthProto(e.target.value)}
                                            disabled={snmpV3SecurityLevel === 'noAuthNoPriv'}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all disabled:opacity-60"
                                        >
                                            <option value="sha">SHA</option>
                                            <option value="md5">MD5</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Auth Key</label>
                                        <input
                                            type="password"
                                            value={snmpV3AuthKey}
                                            onChange={(e) => setSnmpV3AuthKey(e.target.value)}
                                            disabled={snmpV3SecurityLevel === 'noAuthNoPriv'}
                                            required={snmpV3SecurityLevel === 'authNoPriv' || snmpV3SecurityLevel === 'authPriv'}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all disabled:opacity-60"
                                        />
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Priv Protocol</label>
                                        <select
                                            value={snmpV3PrivProto}
                                            onChange={(e) => setSnmpV3PrivProto(e.target.value)}
                                            disabled={snmpV3SecurityLevel !== 'authPriv'}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all disabled:opacity-60"
                                        >
                                            <option value="aes">AES</option>
                                            <option value="des">DES</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Priv Key</label>
                                        <input
                                            type="password"
                                            value={snmpV3PrivKey}
                                            onChange={(e) => setSnmpV3PrivKey(e.target.value)}
                                            disabled={snmpV3SecurityLevel !== 'authPriv'}
                                            required={snmpV3SecurityLevel === 'authPriv'}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all disabled:opacity-60"
                                        />
                                    </div>
                                </div>
                            </div>
                        )}
                        <button
                            type="submit"
                            data-testid="discovery-start"
                            disabled={scanMode === 'seed' && (!effectiveSeedIp || !seedScopeCheck.ok)}
                            className={`w-full py-3 text-white font-bold rounded-lg shadow-lg shadow-blue-500/30 transition-all flex items-center justify-center gap-2 ${scanMode === 'seed' && (!effectiveSeedIp || !seedScopeCheck.ok) ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500'}`}
                        >
                            <Play size={20} /> {scanMode === 'seed' ? 'Start Crawl' : 'Start Scan'}
                        </button>
                    </form>
                </div>
            )}

            {/* Step 2: Scanning Progress */}
            {step === 2 && (
                <div data-testid="discovery-progress-panel" className="max-w-3xl mx-auto w-full space-y-6 animate-fade-in">
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-lg">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-xl font-bold flex items-center gap-2">
                                <RefreshCw className="animate-spin text-blue-500" /> Scanning Network...
                            </h2>
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-mono bg-gray-100 dark:bg-black/30 px-2 py-1 rounded">Found {results.length}</span>
                                <span className="text-sm font-mono bg-gray-100 dark:bg-black/30 px-2 py-1 rounded">{progress}%</span>
                            </div>
                        </div>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5 mb-6 overflow-hidden">
                            <div className="bg-blue-600 h-2.5 rounded-full transition-all duration-500" style={{ width: `${progress}%` }}></div>
                        </div>
                        {scanMode === 'seed' && plugAndScanMode && (
                            <div className="mb-4 text-xs px-3 py-2 rounded border border-emerald-200 bg-emerald-50 text-emerald-700">
                                Plug & Scan active: when crawl completes, system will auto-approve discovered devices and move to topology.
                            </div>
                        )}
                        {autoApproveReport && (
                            <div className="mb-4 text-xs px-3 py-2 rounded border border-blue-200 bg-blue-50 text-blue-700">
                                Auto-Approve report: approved {Number(autoApproveReport.approved_count || 0)}, skipped {Number(autoApproveReport.skipped_count || 0)}
                                {Object.keys(autoApproveReport.skip_breakdown || {}).length > 0 && (
                                    <span> | {Object.entries(autoApproveReport.skip_breakdown).map(([k, v]) => `${k}:${v}`).join(', ')}</span>
                                )}
                            </div>
                        )}

                        {/* Terminal Output */}
                        <div className="bg-black rounded-lg p-4 font-mono text-xs h-64 overflow-y-auto custom-scrollbar border border-gray-800 shadow-inner">
                            <pre className="text-green-400 whitespace-pre-wrap">{logs}</pre>
                            <div ref={logEndRef} />
                        </div>
                    </div>

                    {results.length > 0 && (
                        <div className="bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm">
                            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
                                <div className="font-bold">Live Results</div>
                                <div className="text-xs text-gray-500">Updates stream while scanning</div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left">
                                    <thead className="bg-gray-50 dark:bg-[#25282c] border-b border-gray-200 dark:border-gray-700 text-gray-500 font-medium">
                                        <tr>
                                            <th className="px-6 py-3">IP</th>
                                            <th className="px-6 py-3">Hostname</th>
                                            <th className="px-6 py-3">Vendor</th>
                                            <th className="px-6 py-3">Issues</th>
                                            <th className="px-6 py-3">SNMP</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                                        {results.slice(0, 20).flatMap(dev => {
                                            const isOpen = !!expanded?.[dev.id];
                                            return [
                                                (
                                                    <tr key={dev.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                                                        <td className="px-6 py-3 font-mono text-sm">{dev.ip_address}</td>
                                                        <td className="px-6 py-3 font-bold text-gray-900 dark:text-white">{dev.hostname || '-'}</td>
                                                        <td className="px-6 py-3">{dev.vendor || 'Unknown'}</td>
                                                        <td className="px-6 py-3">
                                                            {getIssues(dev).length > 0 || Object.keys(getEvidence(dev)).length > 0 ? (
                                                                <button
                                                                    onClick={() => toggleExpanded(dev.id)}
                                                                    className="text-xs font-bold text-amber-700 dark:text-amber-400 flex items-center gap-1"
                                                                    title={t('discovery_show_details', 'Show details')}
                                                                >
                                                                    <AlertTriangle size={12} /> {getIssues(dev).length || 0}
                                                                </button>
                                                            ) : (
                                                                <span className="text-xs text-gray-400">-</span>
                                                            )}
                                                        </td>
                                                        <td className="px-6 py-3">
                                                            {dev.snmp_status === 'reachable' ? (
                                                                <span className="text-green-500 flex items-center gap-1 text-xs"><CheckCircle size={12} /> {t('discovery_reachable', 'Reachable')}</span>
                                                            ) : (
                                                                <span className="text-red-500 flex items-center gap-1 text-xs"><AlertTriangle size={12} /> {t('discovery_unreachable', 'Unreachable')}</span>
                                                            )}
                                                        </td>
                                                    </tr>
                                                ),
                                                isOpen ? (
                                                    <tr key={`${dev.id}-details`} className="bg-gray-50/50 dark:bg-black/10">
                                                        <td colSpan={5} className="px-6 py-4">
                                                            {renderIssuesAndEvidence(dev)}
                                                        </td>
                                                    </tr>
                                                ) : null,
                                            ].filter(Boolean);
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {jobStatus === 'completed' && (
                        <div className="flex justify-center">
                            <button data-testid="discovery-view-results" onClick={loadResults} className="px-6 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg font-bold shadow-lg shadow-green-500/30 animate-bounce">
                                {t('discovery_view_results', 'View Results')}
                            </button>
                        </div>
                    )}
                </div>
            )}

            {/* Step 3: Results Table */}
            {step === 3 && (
                <div data-testid="discovery-results-panel" className="space-y-6 animate-fade-in h-full flex flex-col">
                    <div className="flex justify-between items-center mb-2">
                        <h2 className="text-2xl font-bold flex items-center gap-2">
                            <CheckCircle className="text-green-500" /> {t('discovery_scan_results', 'Scan Results')}
                        </h2>
                        <div className="flex gap-2">
                            <button onClick={() => setStep(1)} className="px-4 py-2 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">{t('discovery_new_scan', 'New Scan')}</button>
                            <button onClick={handleApproveAll} className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg">{t('discovery_approve_all_new', 'Approve All New')}</button>
                            <button onClick={() => navigate('/devices')} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg">{t('discovery_go_inventory', 'Go to Inventory')}</button>
                        </div>
                    </div>

                    {/* ── Onboarding Celebration Banner ── */}
                    {results.length > 0 && (() => {
                        const approved = results.filter(d => d.status === 'approved');
                        if (approved.length === 0) return null;
                        const vendorMap = {};
                        approved.forEach(d => { const v = d.vendor || 'Unknown'; vendorMap[v] = (vendorMap[v] || 0) + 1; });
                        const vendorEntries = Object.entries(vendorMap).sort((a, b) => b[1] - a[1]);
                        const onlineCount = approved.filter(d => d.snmp_status === 'reachable').length;
                        const colors = ['bg-emerald-500', 'bg-blue-500', 'bg-purple-500', 'bg-orange-500', 'bg-pink-500'];
                        return (
                            <div className="rounded-2xl border-2 border-emerald-300 dark:border-emerald-800 bg-gradient-to-r from-emerald-50 to-green-50 dark:from-emerald-950/20 dark:to-green-950/20 px-5 py-4 animate-scale-in">
                                <div className="flex items-center gap-3 mb-3">
                                    <div className="p-2 bg-emerald-100 dark:bg-emerald-900/30 rounded-full">
                                        <CheckCircle size={24} className="text-emerald-600 dark:text-emerald-400" />
                                    </div>
                                    <div>
                                        <div className="text-lg font-black text-emerald-900 dark:text-emerald-100">
                                            🎉 {approved.length} {t('discovery_onboarding_registered', 'devices successfully registered to NMS!')}
                                        </div>
                                        <div className="text-xs text-emerald-700 dark:text-emerald-300">
                                            {t('discovery_onboarding_subtitle', 'Monitoring, topology links, and configuration sync are now active.')}
                                        </div>
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                    <div className="rounded-xl bg-white/70 dark:bg-black/20 border border-emerald-200 dark:border-emerald-800 px-3 py-2">
                                        <div className="text-[10px] font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400 mb-1.5">{t('discovery_onboarding_vendors', 'Vendor Breakdown')}</div>
                                        <div className="flex flex-wrap gap-1.5">
                                            {vendorEntries.slice(0, 5).map(([vendor, count], idx) => (
                                                <span key={vendor} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold text-white ${colors[idx % colors.length]}`}>
                                                    {vendor} <span className="bg-white/30 px-1 rounded">{count}</span>
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                    <div className="rounded-xl bg-white/70 dark:bg-black/20 border border-emerald-200 dark:border-emerald-800 px-3 py-2">
                                        <div className="text-[10px] font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400 mb-1.5">{t('discovery_onboarding_health', 'Initial Health')}</div>
                                        <div className="flex items-center gap-3">
                                            <span className="text-xl font-black text-emerald-700 dark:text-emerald-300">{onlineCount}</span>
                                            <span className="text-xs text-gray-500">/ {approved.length} {t('discovery_onboarding_reachable', 'reachable')}</span>
                                        </div>
                                        <div className="mt-1 w-full h-2 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
                                            <div className="h-full bg-emerald-500 rounded-full transition-all" style={{ width: `${approved.length > 0 ? (onlineCount / approved.length) * 100 : 0}%` }} />
                                        </div>
                                    </div>
                                    <div className="rounded-xl bg-white/70 dark:bg-black/20 border border-emerald-200 dark:border-emerald-800 px-3 py-2 flex flex-col gap-1.5">
                                        <div className="text-[10px] font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400 mb-0.5">{t('discovery_onboarding_next', 'Next Steps')}</div>
                                        <button onClick={() => navigate('/topology')} className="text-left text-xs font-bold text-blue-700 dark:text-blue-300 hover:underline">🗺️ {t('discovery_onboarding_go_topology', 'View Auto-Topology Map')}</button>
                                        <button onClick={() => navigate('/devices')} className="text-left text-xs font-bold text-blue-700 dark:text-blue-300 hover:underline">📋 {t('discovery_onboarding_go_devices', 'Review Device Inventory')}</button>
                                    </div>
                                </div>
                            </div>
                        );
                    })()}

                    {jobKpi && (
                        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] px-4 py-3">
                                <div className="text-xs text-gray-500">{t('discovery_first_map_time', 'First Map Time')}</div>
                                <div className="text-lg font-bold">
                                    {jobKpi?.kpi?.first_map_seconds === null || jobKpi?.kpi?.first_map_seconds === undefined
                                        ? '-'
                                        : `${jobKpi.kpi.first_map_seconds}s`}
                                </div>
                            </div>
                            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] px-4 py-3">
                                <div className="text-xs text-gray-500">{t('dashboard_auto_action_rate', 'Auto Reflection')}</div>
                                <div className="text-lg font-bold">{Number(jobKpi?.kpi?.auto_reflection_rate_pct || 0).toFixed(2)}%</div>
                            </div>
                            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] px-4 py-3">
                                <div className="text-xs text-gray-500">{t('discovery_false_positive', 'False Positive')}</div>
                                <div className="text-lg font-bold">{Number(jobKpi?.kpi?.false_positive_rate_pct || 0).toFixed(2)}%</div>
                            </div>
                            <div className="rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50/40 dark:bg-amber-950/10 px-4 py-3">
                                <div className="text-xs text-amber-700 dark:text-amber-300">{t('discovery_low_conf_links', 'Low-Confidence Links')}</div>
                                <div className="flex items-end justify-between gap-2">
                                    <div className="text-lg font-bold text-amber-800 dark:text-amber-200">
                                        {Number(jobKpi?.totals?.low_confidence_candidates || 0)}
                                    </div>
                                    <button
                                        data-testid="discovery-review-queue-results"
                                        onClick={() => navigate('/topology', { state: { showCandidates: true, candidateJobId: jobId, candidateStatus: 'low_confidence' } })}
                                        className="px-2 py-1 text-xs font-bold rounded border border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-200 hover:bg-amber-100/70 dark:hover:bg-amber-900/30"
                                    >
                                        {t('discovery_review_queue', 'Review Queue')}
                                    </button>
                                </div>
                                <div className="mt-1 text-[11px] text-amber-700 dark:text-amber-300">
                                    {t('discovery_rate', 'rate')} {Number(jobKpi?.kpi?.low_confidence_rate_pct || 0).toFixed(2)}%
                                </div>
                                {Array.isArray(jobKpi?.kpi?.low_confidence_top_reasons) && jobKpi.kpi.low_confidence_top_reasons.length > 0 && (
                                    <div className="mt-2 space-y-1">
                                        {jobKpi.kpi.low_confidence_top_reasons.slice(0, 3).map((r, idx) => (
                                            <button
                                                key={`${r?.reason || 'unknown'}-${idx}`}
                                                onClick={() => navigate('/topology', {
                                                    state: {
                                                        showCandidates: true,
                                                        candidateJobId: jobId,
                                                        candidateStatus: 'low_confidence',
                                                        candidateSearch: String(r?.reason || 'unknown'),
                                                    }
                                                })}
                                                className="w-full flex items-center justify-between text-[11px] text-amber-900 dark:text-amber-200 hover:bg-amber-100/70 dark:hover:bg-amber-900/25 rounded px-1 py-0.5"
                                                title={`Filter queue by reason: ${String(r?.reason || 'unknown')}`}
                                            >
                                                <span className="truncate max-w-[70%]">{String(r?.reason || 'unknown')}</span>
                                                <span className="font-bold">{Number(r?.count || 0)}</span>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                    {autoApproveReport && (
                        <div className="rounded-xl border border-blue-200 dark:border-blue-900 bg-blue-50/40 dark:bg-blue-950/10 px-4 py-3 text-sm">
                            <div className="font-bold text-blue-700 dark:text-blue-300 mb-1">{t('discovery_auto_approve_execution', 'Auto-Approve Execution')}</div>
                            <div className="text-blue-800 dark:text-blue-200">
                                {t('discovery_approved_skipped_fmt', 'approved {approved}, skipped {skipped}').replace('{approved}', String(Number(autoApproveReport.approved_count || 0))).replace('{skipped}', String(Number(autoApproveReport.skipped_count || 0)))}
                            </div>
                            {Object.keys(autoApproveReport.skip_breakdown || {}).length > 0 && (
                                <div className="text-xs text-blue-700 dark:text-blue-300 mt-2 flex flex-wrap gap-1.5">
                                    {Object.entries(autoApproveReport.skip_breakdown).map(([k, v]) => renderSkipReasonAction(k, v))}
                                </div>
                            )}
                        </div>
                    )}
                    {/* ── Discovery Failure Analysis Banner ── */}
                    {results.length > 0 && (() => {
                        const snmpFailed = results.filter(d => d.snmp_status !== 'reachable');
                        const lowConf = results.filter(d => typeof d.vendor_confidence === 'number' && d.vendor_confidence < 0.5 && d.snmp_status === 'reachable');
                        const totalIssues = snmpFailed.length + lowConf.length;
                        if (totalIssues === 0) return null;
                        return (
                            <div className="rounded-xl border border-rose-200 dark:border-rose-900/50 bg-rose-50/60 dark:bg-rose-950/10 px-4 py-3">
                                <div className="flex items-center gap-2 mb-2">
                                    <AlertTriangle size={16} className="text-rose-600 dark:text-rose-400" />
                                    <span className="text-sm font-bold text-rose-800 dark:text-rose-200">
                                        {t('discovery_failure_analysis_title', 'Failure Analysis')} — {totalIssues} {t('discovery_failure_analysis_devices', 'device(s) need attention')}
                                    </span>
                                </div>
                                {snmpFailed.length > 0 && (
                                    <div className="mb-2">
                                        <div className="text-xs font-bold text-rose-700 dark:text-rose-300 mb-1">
                                            ⛔ SNMP {t('discovery_unreachable', 'Unreachable')} ({snmpFailed.length})
                                        </div>
                                        <div className="flex flex-wrap gap-1.5">
                                            {snmpFailed.slice(0, 8).map(d => (
                                                <span key={d.id} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white/70 dark:bg-black/20 border border-rose-200 dark:border-rose-800 text-[11px] font-mono text-rose-800 dark:text-rose-200">
                                                    {d.ip_address}
                                                    <span className="text-[10px] font-sans text-rose-600 dark:text-rose-400 ml-1">
                                                        {d.snmp_status === 'timeout' ? 'Timeout' : d.snmp_status === 'no_response' ? 'No Response' : String(d.snmp_status || 'Failed')}
                                                    </span>
                                                </span>
                                            ))}
                                            {snmpFailed.length > 8 && (
                                                <span className="text-[11px] text-rose-600 dark:text-rose-400 font-bold">+{snmpFailed.length - 8} more</span>
                                            )}
                                        </div>
                                        <div className="mt-1.5 text-[11px] text-rose-700/80 dark:text-rose-300/80">
                                            💡 {t('discovery_failure_snmp_hint', 'Check SNMP community string, verify firewall allows UDP/161, and confirm the device has SNMP enabled.')}
                                        </div>
                                    </div>
                                )}
                                {lowConf.length > 0 && (
                                    <div>
                                        <div className="text-xs font-bold text-amber-700 dark:text-amber-300 mb-1">
                                            ⚠️ {t('discovery_low_confidence_vendor', 'Low Vendor Confidence')} ({lowConf.length})
                                        </div>
                                        <div className="flex flex-wrap gap-1.5">
                                            {lowConf.slice(0, 8).map(d => (
                                                <span key={d.id} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white/70 dark:bg-black/20 border border-amber-200 dark:border-amber-800 text-[11px] font-mono text-amber-800 dark:text-amber-200">
                                                    {d.ip_address}
                                                    <span className="text-[10px] font-sans text-amber-600 dark:text-amber-400 ml-1">
                                                        {typeof d.vendor_confidence === 'number' ? `${Math.round(d.vendor_confidence * 100)}%` : '?'}
                                                    </span>
                                                </span>
                                            ))}
                                            {lowConf.length > 8 && (
                                                <span className="text-[11px] text-amber-600 dark:text-amber-400 font-bold">+{lowConf.length - 8} more</span>
                                            )}
                                        </div>
                                        <div className="mt-1.5 text-[11px] text-amber-700/80 dark:text-amber-300/80">
                                            💡 {t('discovery_failure_lowconf_hint', 'sysObjectID could not be matched to a known vendor. Approve manually or update the vendor fingerprint database.')}
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })()}
                    {hintResultSummary.hinted > 0 && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                            <div className="rounded-xl border border-sky-200 dark:border-sky-900 bg-sky-50/50 dark:bg-sky-950/10 px-4 py-3">
                                <div className="text-xs text-sky-700 dark:text-sky-300">{t('discovery_hint_summary_total', 'Hint-aware devices')}</div>
                                <div className="text-lg font-bold text-sky-900 dark:text-sky-100">{Number(hintResultSummary.hinted || 0)}</div>
                            </div>
                            <div className="rounded-xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50/50 dark:bg-emerald-950/10 px-4 py-3">
                                <div className="text-xs text-emerald-700 dark:text-emerald-300">{t('discovery_hint_summary_success', 'Hint-driven SSH success')}</div>
                                <div className="text-lg font-bold text-emerald-900 dark:text-emerald-100">{Number(hintResultSummary.success || 0)}</div>
                            </div>
                            <div className="rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50/50 dark:bg-amber-950/10 px-4 py-3">
                                <div className="text-xs text-amber-700 dark:text-amber-300">{t('discovery_hint_summary_followup', 'Hint follow-up needed')}</div>
                                <div className="text-lg font-bold text-amber-900 dark:text-amber-100">
                                    {Number((hintResultSummary.failed || 0) + (hintResultSummary.available || 0))}
                                </div>
                                <div className="mt-1 text-[11px] text-amber-700 dark:text-amber-300">
                                    {t('discovery_hint_summary_followup_breakdown', 'failed {failed} / ranked {available}')
                                        .replace('{failed}', String(Number(hintResultSummary.failed || 0)))
                                        .replace('{available}', String(Number(hintResultSummary.available || 0)))}
                                </div>
                            </div>
                            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] px-4 py-3">
                                <div className="text-xs text-gray-500">{t('discovery_hint_summary_top_vendor', 'Top hinted vendor')}</div>
                                <div className="text-lg font-bold text-gray-900 dark:text-white">
                                    {hintResultSummary.topVendor || t('common_unknown', 'Unknown')}
                                </div>
                            </div>
                        </div>
                    )}

                    {(reviewContext || reviewLoading) && (
                        <div
                            data-testid="discovery-post-review-panel"
                            className="rounded-2xl border border-blue-200 dark:border-blue-900/40 bg-blue-50/50 dark:bg-blue-950/10 px-4 py-4 space-y-4"
                        >
                            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                <div>
                                    <div className="flex items-center gap-2 text-sm font-black text-blue-900 dark:text-blue-100">
                                        <Workflow size={16} />
                                        {t('discovery_post_review_title', 'Post-Discovery Review')}
                                    </div>
                                    <div className="mt-1 text-sm text-blue-900/80 dark:text-blue-100/80">
                                        {t(
                                            'discovery_post_review_desc',
                                            'Turn this discovery result into an operating device by assigning management, monitoring, site ownership, and service context in one place.',
                                        )}
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    {reviewContext?.inventoryDeviceId ? (
                                        <button
                                            type="button"
                                            onClick={() => navigate(`/devices/${reviewContext.inventoryDeviceId}`)}
                                            className="px-3 py-1.5 rounded-lg border border-blue-200 dark:border-blue-800 text-xs font-bold text-blue-700 dark:text-blue-200 hover:bg-blue-100/70 dark:hover:bg-blue-950/30"
                                        >
                                            {t('discovery_post_review_open_device', 'Open Device')}
                                        </button>
                                    ) : null}
                                    <button
                                        type="button"
                                        onClick={closeReviewContext}
                                        className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-xs font-bold text-gray-600 dark:text-gray-300 hover:bg-white/80 dark:hover:bg-black/20"
                                    >
                                        {t('common_close', 'Close')}
                                    </button>
                                </div>
                            </div>

                            {reviewLoading ? (
                                <div className="rounded-xl border border-blue-200 dark:border-blue-900/40 bg-white/80 dark:bg-black/20 px-4 py-4 text-sm text-blue-700 dark:text-blue-200">
                                    {t('common_loading', 'Loading...')}
                                </div>
                            ) : reviewContext?.device ? (
                                <>
                                    <div className="grid grid-cols-1 xl:grid-cols-4 gap-3">
                                        <div className="rounded-xl border border-white/70 dark:border-white/10 bg-white/80 dark:bg-black/20 px-4 py-3">
                                            <div className="text-[11px] text-gray-500">{t('discovery_post_review_device', 'Device')}</div>
                                            <div className="mt-1 text-sm font-bold text-gray-900 dark:text-white">
                                                {reviewContext.device.name || reviewContext.device.hostname || reviewContext.device.ip_address || '-'}
                                            </div>
                                            <div className="mt-1 text-xs text-gray-500 font-mono">{reviewContext.device.ip_address || '-'}</div>
                                        </div>
                                        <div className="rounded-xl border border-white/70 dark:border-white/10 bg-white/80 dark:bg-black/20 px-4 py-3">
                                            <div className="text-[11px] text-gray-500">{t('discovery_post_review_management', 'Management')}</div>
                                            <div className="mt-1 text-sm font-bold text-gray-900 dark:text-white">
                                                {reviewContext.device.management_state === 'managed'
                                                    ? t('discovery_post_review_managed', 'Managed')
                                                    : t('discovery_post_review_discovered_only', 'Discovered only')}
                                            </div>
                                            <div className="mt-1 text-xs text-gray-500">
                                                {reviewContext.device.management_reason || t('common_unknown', 'Unknown')}
                                            </div>
                                        </div>
                                        <div className="rounded-xl border border-white/70 dark:border-white/10 bg-white/80 dark:bg-black/20 px-4 py-3">
                                            <div className="text-[11px] text-gray-500">{t('discovery_post_review_site', 'Site')}</div>
                                            <div className="mt-1 text-sm font-bold text-gray-900 dark:text-white">
                                                {sites.find((site) => Number(site.id) === Number(reviewContext.device.site_id))?.name || t('discovery_post_review_unassigned', 'Unassigned')}
                                            </div>
                                            <div className="mt-1 text-xs text-gray-500">{reviewContext.device.vendor || t('common_unknown', 'Unknown')} / {reviewContext.device.model || '-'}</div>
                                        </div>
                                        <div className="rounded-xl border border-white/70 dark:border-white/10 bg-white/80 dark:bg-black/20 px-4 py-3">
                                            <div className="text-[11px] text-gray-500">{t('discovery_post_review_profile', 'Monitoring Profile')}</div>
                                            <div className="mt-1 text-sm font-bold text-gray-900 dark:text-white">
                                                {reviewContext.recommendation?.name || t('discovery_post_review_no_profile', 'No recommendation')}
                                            </div>
                                            <div className="mt-1 text-xs text-gray-500">
                                                {reviewContext.recommendation?.activation_state || t('common_unknown', 'Unknown')}
                                            </div>
                                        </div>
                                    </div>

                                    {hasManagedQuota && (
                                        <div className="rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50/60 dark:bg-amber-950/10 px-4 py-3">
                                            <div className="flex flex-wrap items-center gap-3 text-sm">
                                                <span className="font-bold text-amber-900 dark:text-amber-100">
                                                    {t('discovery_post_review_managed_limit_fmt', 'NetSphere Free manages up to {count} nodes.').replace('{count}', String(Number(managedSummary?.managed_limit || 0)))}
                                                </span>
                                                <span className="text-amber-800 dark:text-amber-200">
                                                    {t('discovery_post_review_managed_summary_fmt', 'managed {managed}, discovered only {discovered}, remaining {remaining}')
                                                        .replace('{managed}', String(Number(managedSummary?.managed || 0)))
                                                        .replace('{discovered}', String(Number(managedSummary?.discovered_only || 0)))
                                                        .replace('{remaining}', String(Number(managedSummary?.remaining_slots || 0)))}
                                                </span>
                                            </div>
                                        </div>
                                    )}

                                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                                        <div className="rounded-xl border border-white/70 dark:border-white/10 bg-white/80 dark:bg-black/20 px-4 py-4 space-y-3">
                                            <div className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
                                                <Shield size={16} />
                                                {t('discovery_post_review_scope_title', 'Managed monitoring scope')}
                                            </div>
                                            <div className="text-xs text-gray-500">
                                                {t('discovery_post_review_scope_desc', 'Choose whether this asset should stay discovered-only or become an actively managed node.')}
                                            </div>
                                            <div className="flex flex-wrap gap-2">
                                                {reviewContext.device.management_state === 'managed' ? (
                                                    <button
                                                        type="button"
                                                        onClick={handleReleaseManagedFromReview}
                                                        disabled={reviewActionLoading === 'release'}
                                                        className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-60"
                                                    >
                                                        {t('discovery_post_review_release_slot', 'Keep as discovered only')}
                                                    </button>
                                                ) : (
                                                    <button
                                                        type="button"
                                                        onClick={handlePromoteManagedFromReview}
                                                        disabled={reviewActionLoading === 'manage'}
                                                        className="px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold disabled:opacity-60"
                                                    >
                                                        {t('discovery_post_review_promote', 'Promote to Managed')}
                                                    </button>
                                                )}
                                            </div>
                                        </div>

                                        <div className="rounded-xl border border-white/70 dark:border-white/10 bg-white/80 dark:bg-black/20 px-4 py-4 space-y-3">
                                            <div className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
                                                <MapPin size={16} />
                                                {t('discovery_post_review_site_title', 'Site ownership')}
                                            </div>
                                            <select
                                                value={reviewSiteId}
                                                onChange={(e) => setReviewSiteId(e.target.value)}
                                                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#151618] text-sm"
                                            >
                                                <option value="">{t('discovery_post_review_unassigned', 'Unassigned')}</option>
                                                {(sites || []).map((site) => (
                                                    <option key={`review-site-${site.id}`} value={String(site.id)}>
                                                        {String(site.name || `Site ${site.id}`)}
                                                    </option>
                                                ))}
                                            </select>
                                            <button
                                                type="button"
                                                onClick={handleAssignSiteFromReview}
                                                disabled={!reviewSiteId || reviewActionLoading === 'site'}
                                                className="px-3 py-2 rounded-lg border border-blue-200 dark:border-blue-800 text-xs font-bold text-blue-700 dark:text-blue-200 hover:bg-blue-50 dark:hover:bg-blue-950/20 disabled:opacity-60"
                                            >
                                                {t('discovery_post_review_assign_site', 'Assign Site')}
                                            </button>
                                        </div>

                                        <div className="rounded-xl border border-white/70 dark:border-white/10 bg-white/80 dark:bg-black/20 px-4 py-4 space-y-3">
                                            <div className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
                                                <Radar size={16} />
                                                {t('discovery_post_review_profile_title', 'Monitoring profile')}
                                            </div>
                                            <div className="text-xs text-gray-500">
                                                {reviewContext.recommendation?.recommendation_reasons?.length > 0
                                                    ? reviewContext.recommendation.recommendation_reasons.join(' · ')
                                                    : t('discovery_post_review_profile_hint', 'Use the recommended monitoring profile or pin a different one.')}
                                            </div>
                                            <select
                                                value={reviewProfileId}
                                                onChange={(e) => setReviewProfileId(e.target.value)}
                                                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#151618] text-sm"
                                            >
                                                <option value="">{t('discovery_post_review_select_profile', 'Select a monitoring profile')}</option>
                                                {(profileCatalog || []).map((profile) => (
                                                    <option key={`review-profile-${profile.id}`} value={String(profile.id)}>
                                                        {String(profile.name || profile.key || `Profile ${profile.id}`)}
                                                    </option>
                                                ))}
                                            </select>
                                            <div className="flex flex-wrap gap-2">
                                                <button
                                                    type="button"
                                                    onClick={handleAssignProfileFromReview}
                                                    disabled={!reviewProfileId || reviewActionLoading === 'profile'}
                                                    className="px-3 py-2 rounded-lg border border-blue-200 dark:border-blue-800 text-xs font-bold text-blue-700 dark:text-blue-200 hover:bg-blue-50 dark:hover:bg-blue-950/20 disabled:opacity-60"
                                                >
                                                    {t('discovery_post_review_apply_profile', 'Apply Profile')}
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={handleRecomputeProfileFromReview}
                                                    disabled={reviewActionLoading === 'profile-recompute'}
                                                    className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-60"
                                                >
                                                    {t('discovery_post_review_refresh_profile', 'Refresh Recommendation')}
                                                </button>
                                            </div>
                                        </div>

                                        <div className="rounded-xl border border-white/70 dark:border-white/10 bg-white/80 dark:bg-black/20 px-4 py-4 space-y-3">
                                            <div className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
                                                <Workflow size={16} />
                                                {t('discovery_post_review_service_title', 'Service context')}
                                            </div>
                                            <select
                                                value={reviewServiceGroupId}
                                                onChange={(e) => setReviewServiceGroupId(e.target.value)}
                                                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#151618] text-sm"
                                            >
                                                <option value="">{t('discovery_post_review_select_group', 'Select a service group')}</option>
                                                {(serviceGroups || []).map((group) => (
                                                    <option key={`review-group-${group.id}`} value={String(group.id)}>
                                                        {String(group.name || `Group ${group.id}`)}
                                                    </option>
                                                ))}
                                            </select>
                                            <button
                                                type="button"
                                                onClick={handleAddServiceGroupFromReview}
                                                disabled={!reviewServiceGroupId || reviewActionLoading === 'group'}
                                                className="px-3 py-2 rounded-lg border border-blue-200 dark:border-blue-800 text-xs font-bold text-blue-700 dark:text-blue-200 hover:bg-blue-50 dark:hover:bg-blue-950/20 disabled:opacity-60"
                                            >
                                                {t('discovery_post_review_add_group', 'Link Service Group')}
                                            </button>
                                        </div>
                                    </div>
                                </>
                            ) : null}
                        </div>
                    )}

                    <div data-testid="discovery-results-table" className="flex-1 bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm flex flex-col">
                        <div className="overflow-y-auto flex-1 custom-scrollbar">
                            <table className="w-full text-left">
                                <thead className="bg-gray-50 dark:bg-[#25282c] border-b border-gray-200 dark:border-gray-700 text-gray-500 font-medium">
                                    <tr>
                                        <th className="px-6 py-4">{t('obs_table_status', 'Status')}</th>
                                        <th className="px-6 py-4">{t('obs_table_ip', 'IP Address')}</th>
                                        <th className="px-6 py-4">{t('obs_table_name', 'Hostname')}</th>
                                        <th className="px-6 py-4">{t('discovery_vendor', 'Vendor')}</th>
                                        <th className="px-6 py-4">{t('discovery_confidence', 'Confidence')}</th>
                                        <th className="px-6 py-4">{t('discovery_chassis', 'Chassis')}</th>
                                        <th className="px-6 py-4">{t('discovery_model', 'Model')}</th>
                                        <th className="px-6 py-4">{t('discovery_type', 'Type')}</th>
                                        <th className="px-6 py-4">{t('discovery_issues', 'Issues')}</th>
                                        <th className="px-6 py-4">SNMP</th>
                                        <th className="px-6 py-4 text-right">{t('discovery_action', 'Action')}</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                                    {results.length === 0 ? (
                                        <tr><td colSpan="11" className="px-6 py-10 text-center text-gray-500">{t('discovery_no_devices_network', 'No devices found. Check network connectivity and try again.')}</td></tr>
                                    ) : results.flatMap(dev => {
                                        const isOpen = !!expanded?.[dev.id];
                                        return [
                                            (
                                                <tr key={dev.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                                                    <td className="px-6 py-4">
                                                        {dev.status === 'existing' ? (
                                                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-yellow-100 text-yellow-700 border border-yellow-200">{t('discovery_managed', 'Managed')}</span>
                                                        ) : dev.status === 'approved' ? (
                                                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-green-100 text-green-700 border border-green-200">{t('discovery_approved', 'Approved')}</span>
                                                        ) : (
                                                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-700 border border-blue-200">{t('discovery_new_found', 'New Found')}</span>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-4 font-mono text-sm">{dev.ip_address}</td>
                                                    <td className="px-6 py-4 font-bold text-gray-900 dark:text-white">{dev.hostname || '-'}</td>
                                                    <td className="px-6 py-4">
                                                        <div className="flex flex-col gap-1">
                                                            <span>{dev.vendor || t('discovery_unknown', 'Unknown')}</span>
                                                            {hasHintEvidence(dev) && (
                                                                <span className="inline-flex w-fit px-2 py-0.5 rounded-full text-[11px] font-bold border bg-sky-100 text-sky-700 border-sky-200">
                                                                    {t('discovery_hint_badge', 'Hinted')}
                                                                </span>
                                                            )}
                                                        </div>
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        {typeof dev.vendor_confidence === 'number' ? (
                                                            <span className="text-xs font-mono px-2 py-1 rounded bg-gray-100 dark:bg-black/30 border border-gray-200 dark:border-gray-700">
                                                                {Math.round(dev.vendor_confidence * 100)}%
                                                            </span>
                                                        ) : (
                                                            <span className="text-xs text-gray-400">-</span>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        {dev.chassis_candidate ? (
                                                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-purple-100 text-purple-700 border border-purple-200">{t('discovery_likely', 'Likely')}</span>
                                                        ) : (
                                                            <span className="text-xs text-gray-400">-</span>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-4 font-mono text-xs">{dev.model || '-'}</td>
                                                    <td className="px-6 py-4 font-mono text-xs">{dev.device_type || '-'}</td>
                                                    <td className="px-6 py-4">
                                                        {getIssues(dev).length > 0 || Object.keys(getEvidence(dev)).length > 0 ? (
                                                            <button
                                                                onClick={() => toggleExpanded(dev.id)}
                                                                className="text-xs font-bold text-amber-700 dark:text-amber-400 flex items-center gap-1"
                                                                title={t('discovery_show_details', 'Show details')}
                                                            >
                                                                <AlertTriangle size={12} /> {getIssues(dev).length || 0}
                                                            </button>
                                                        ) : (
                                                            <span className="text-xs text-gray-400">-</span>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        {dev.snmp_status === 'reachable' ? (
                                                            <span className="text-green-500 flex items-center gap-1 text-xs"><CheckCircle size={12} /> {t('discovery_reachable', 'Reachable')}</span>
                                                        ) : (
                                                            <span className="text-red-500 flex items-center gap-1 text-xs"><AlertTriangle size={12} /> {t('discovery_unreachable', 'Unreachable')}</span>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-4 text-right">
                                                        {dev.status === 'new' && (
                                                            <div className="flex items-center justify-end gap-2">
                                                                <button
                                                                    onClick={() => handleIgnore(dev.id)}
                                                                    className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-xs font-bold hover:bg-gray-100 dark:hover:bg-gray-800"
                                                                >
                                                                    {t('discovery_ignore', 'Ignore')}
                                                                </button>
                                                                <button
                                                                    onClick={() => handleApprove(dev.id)}
                                                                    className={`px-3 py-1.5 text-white rounded-lg text-xs font-bold shadow-md flex items-center gap-1 ${needsLowConfidenceConfirm(dev) ? 'bg-amber-600 hover:bg-amber-500 shadow-amber-500/20' : 'bg-blue-600 hover:bg-blue-500 shadow-blue-500/20'}`}
                                                                >
                                                                    <Plus size={14} /> {t('discovery_add_inventory', 'Add to Inventory')}
                                                                </button>
                                                                {needsLowConfidenceConfirm(dev) && (
                                                                    <span className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
                                                                        <AlertTriangle size={12} /> {t('discovery_low_confidence', 'Low confidence')}
                                                                    </span>
                                                                )}
                                                            </div>
                                                        )}
                                                        {dev.status === 'existing' && (
                                                            <div className="flex items-center justify-end gap-2">
                                                                <button
                                                                    onClick={() => handleOpenPostDiscoveryReview(dev)}
                                                                    className="px-3 py-1.5 border border-blue-200 dark:border-blue-800 rounded-lg text-xs font-bold text-blue-700 dark:text-blue-200 hover:bg-blue-50 dark:hover:bg-blue-950/20"
                                                                >
                                                                    {t('discovery_post_review_cta', 'Review Ops')}
                                                                </button>
                                                                <button disabled className="px-3 py-1.5 text-gray-400 bg-gray-100 dark:bg-gray-800 rounded-lg text-xs cursor-not-allowed">
                                                                    {t('discovery_already_added', 'Already Added')}
                                                                </button>
                                                            </div>
                                                        )}
                                                        {dev.status === 'approved' && (
                                                            <div className="flex items-center justify-end gap-2">
                                                                <button
                                                                    onClick={() => handleOpenPostDiscoveryReview(dev)}
                                                                    className="px-3 py-1.5 border border-blue-200 dark:border-blue-800 rounded-lg text-xs font-bold text-blue-700 dark:text-blue-200 hover:bg-blue-50 dark:hover:bg-blue-950/20"
                                                                >
                                                                    {t('discovery_post_review_cta', 'Review Ops')}
                                                                </button>
                                                                <button disabled className="px-3 py-1.5 text-green-500 bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-900 rounded-lg text-xs cursor-not-allowed flex items-center gap-1">
                                                                    <CheckCircle size={14} /> {t('discovery_added', 'Added')}
                                                                </button>
                                                            </div>
                                                        )}
                                                        {dev.status === 'ignored' && (
                                                            <button disabled className="px-3 py-1.5 text-gray-500 bg-gray-50 dark:bg-gray-900/10 border border-gray-200 dark:border-gray-800 rounded-lg text-xs cursor-not-allowed ml-auto">
                                                                {t('discovery_ignored', 'Ignored')}
                                                            </button>
                                                        )}
                                                    </td>
                                                </tr>
                                            ),
                                            isOpen ? (
                                                <tr key={`${dev.id}-details`} className="bg-gray-50/50 dark:bg-black/10">
                                                    <td colSpan={11} className="px-6 py-4">
                                                        {renderIssuesAndEvidence(dev)}
                                                    </td>
                                                </tr>
                                            ) : null,
                                        ].filter(Boolean);
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}

                </div>
                <aside className="hidden lg:block min-h-0 h-full overflow-y-auto pr-1 custom-scrollbar">
                    {queueInsightsPanel}
                </aside>
            </div>
            <div className="lg:hidden mt-4">
                {queueInsightsPanel}
            </div>
        </div>
    );
};

export default DiscoveryPage;


