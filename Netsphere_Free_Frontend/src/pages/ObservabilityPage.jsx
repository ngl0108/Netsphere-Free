import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { Activity, RefreshCw, ExternalLink, Server, Map as MapIcon, Bell, Workflow, Globe, Settings } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { DeviceService, IntentService, IssueService, ObservabilityService, PreviewService, ServiceGroupService } from '../api/services';
import { useAuth } from '../context/AuthContext';
import { useIssuePolling } from '../context/IssuePollingContext';
import { useProductPolicy } from '../context/ProductPolicyContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';
import useVisiblePolling from '../hooks/useVisiblePolling';
import useVirtualRows from '../hooks/useVirtualRows';
import { InlineEmpty, InlineLoading } from '../components/common/PageState';
import { buildGrafanaAlertingCenterUrl, buildGrafanaFleetHealthUrl } from '../utils/observabilityLinks';
import { getWorkspaceTitle, recommendServiceWorkspace } from '../utils/serviceOperations';
import {
  getDeviceStatusChipClass,
  getDeviceStatusDotClass,
  getDeviceStatusTextClass,
  getOperationalStatusBadgeClass,
  getOperationalStatusHint,
  getOperationalStatusLabel,
  isDeviceOnline,
} from '../utils/deviceStatusTone';

const formatTime = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const formatRelativeTime = (iso) => {
  if (!iso) return '';
  const date = new Date(iso);
  const now = new Date();
  const diffInSeconds = Math.floor((now - date) / 1000);
  if (diffInSeconds < 60) return t('dashboard_time_seconds_ago', '{value}s ago').replace('{value}', String(diffInSeconds));
  if (diffInSeconds < 3600) {
    return t('dashboard_time_minutes_ago', '{value}m ago').replace('{value}', String(Math.floor(diffInSeconds / 60)));
  }
  if (diffInSeconds < 86400) {
    return t('dashboard_time_hours_ago', '{value}h ago').replace('{value}', String(Math.floor(diffInSeconds / 3600)));
  }
  return t('dashboard_time_days_ago', '{value}d ago').replace('{value}', String(Math.floor(diffInSeconds / 86400)));
};

const formatBps = (v) => {
  const n = Number(v || 0);
  if (!Number.isFinite(n)) return '0 bps';
  const units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps'];
  let value = n;
  let idx = 0;
  while (value >= 1000 && idx < units.length - 1) {
    value /= 1000;
    idx += 1;
  }
  return `${value.toFixed(value >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
};

const statusBadgeClass = (value) => getOperationalStatusBadgeClass(value);

const StatCard = ({ title, value, sub }) => {
  return (
    <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
      <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{title}</div>
      <div className="mt-2 text-3xl font-black tracking-tight text-gray-900 dark:text-white">{value}</div>
      {sub ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-300">{sub}</div> : null}
    </div>
  );
};

const ObservabilityPage = ({ mode = 'overview' }) => {
  useLocaleRerender();
  const { isAtLeast } = useAuth();
  const { alerts: issueAlerts, loadAlerts: loadIssueAlerts, markAsRead: markIssueAsRead } = useIssuePolling();
  const { manifest: productPolicyManifest } = useProductPolicy();
  const canView = isAtLeast('operator');
  const location = useLocation();
  const navigate = useNavigate();
  const isDeepDive = mode === 'deep-dive';

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [summary, setSummary] = useState(null);
  const [devices, setDevices] = useState([]);
  const [sites, setSites] = useState([]);
  const [previewPolicy, setPreviewPolicy] = useState(null);
  const [opsStats, setOpsStats] = useState(null);
  const [closedLoopStatus, setClosedLoopStatus] = useState(null);
  const [serviceGroups, setServiceGroups] = useState([]);
  const [serviceImpactIssues, setServiceImpactIssues] = useState([]);
  const [selectedSiteId, setSelectedSiteId] = useState('');
  const [filterText, setFilterText] = useState('');
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [timeseries, setTimeseries] = useState([]);
  const [interfaces, setInterfaces] = useState([]);
  const [selectedInterface, setSelectedInterface] = useState('');
  const [interfaceTimeseries, setInterfaceTimeseries] = useState([]);
  const [statusEvents, setStatusEvents] = useState([]);

  const loadInFlightRef = useRef(null);
  const prevStatusRef = useRef(new Map());
  const statusRestoreDoneRef = useRef(false);
  const deviceTableScrollRef = useRef(null);

  const urls = useMemo(() => {
    return {
      grafanaHome: buildGrafanaFleetHealthUrl({
        deviceId: selectedDeviceId || undefined,
        siteId: selectedSiteId || undefined,
      }),
      grafanaAlerts: buildGrafanaAlertingCenterUrl({
        deviceId: selectedDeviceId || undefined,
        siteId: selectedSiteId || undefined,
      }),
      prometheusHome: '/prometheus/',
      alertmanagerHome: '/alertmanager/',
    };
  }, [selectedDeviceId, selectedSiteId]);

  const observabilityQuery = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return {
      deviceId: String(params.get('deviceId') || '').trim(),
      siteId: String(params.get('siteId') || '').trim(),
    };
  }, [location.search]);

  const previewModeResolved = useMemo(() => {
    if (typeof previewPolicy?.preview_enabled === 'boolean') return previewPolicy.preview_enabled;
    if (typeof productPolicyManifest?.preview_enabled === 'boolean') return productPolicyManifest.preview_enabled;
    return null;
  }, [previewPolicy?.preview_enabled, productPolicyManifest?.preview_enabled]);

  const previewEnabled = previewModeResolved === true;
  const showProOperations = useMemo(() => {
    if (previewModeResolved === false) return true;
    const edition = String(productPolicyManifest?.edition || '').trim().toLowerCase();
    return edition === 'pro' || edition === 'enterprise';
  }, [previewModeResolved, productPolicyManifest?.edition]);

  const sitesById = useMemo(() => {
    const map = new Map();
    for (const s of sites || []) {
      map.set(String(s.id), s);
    }
    return map;
  }, [sites]);

  const devicesById = useMemo(() => {
    const map = new Map();
    for (const d of devices || []) {
      map.set(String(d.id), d);
    }
    return map;
  }, [devices]);

  const filteredDevices = useMemo(() => {
    const siteKey = String(selectedSiteId || '');
    const q = String(filterText || '').trim().toLowerCase();
    return (devices || []).filter((d) => {
      if (siteKey && String(d.site_id || '') !== siteKey) return false;
      if (!q) return true;
      const tags = Array.isArray(d.tags) ? d.tags : [];
      const hay = [d.name, d.ip, d.device_type, d.role, ...tags].map((v) => String(v || '').toLowerCase()).join(' ');
      return hay.includes(q);
    });
  }, [devices, selectedSiteId, filterText]);

  const {
    visibleItems: visibleDeviceRows,
    totalCount: totalDeviceRowsCount,
    startIndex: visibleDeviceStartIndex,
    endIndex: visibleDeviceEndIndex,
    paddingTop: virtualDevicePaddingTop,
    paddingBottom: virtualDevicePaddingBottom,
    onScroll: onDeviceTableVirtualScroll,
  } = useVirtualRows(filteredDevices, {
    containerRef: deviceTableScrollRef,
    rowHeight: 44,
    overscan: 14,
    enabled: filteredDevices.length > 160,
  });

  const filteredDeviceIdSet = useMemo(() => {
    return new Set(filteredDevices.map((d) => String(d.id)));
  }, [filteredDevices]);

  const unreadIssues = useMemo(() => {
    return (Array.isArray(issueAlerts) ? issueAlerts : []).filter((item) => !item?.is_read);
  }, [issueAlerts]);

  const filteredIssues = useMemo(() => {
    return unreadIssues.filter((i) => {
      const did = i?.device_id;
      if (!selectedSiteId) return true;
      if (did == null) return false;
      return filteredDeviceIdSet.has(String(did));
    });
  }, [unreadIssues, selectedSiteId, filteredDeviceIdSet]);

  const sortedInterfaces = useMemo(() => {
    const list = Array.isArray(interfaces) ? interfaces : [];
    return [...list].sort((a, b) => {
      const av = Number(a?.traffic_in_bps || 0) + Number(a?.traffic_out_bps || 0);
      const bv = Number(b?.traffic_in_bps || 0) + Number(b?.traffic_out_bps || 0);
      return bv - av;
    });
  }, [interfaces]);

  const selectedDevice = useMemo(() => {
    return (devices || []).find((d) => String(d.id) === String(selectedDeviceId)) || null;
  }, [devices, selectedDeviceId]);

  const selectedSite = useMemo(() => {
    return selectedSiteId ? (sitesById.get(String(selectedSiteId)) || null) : null;
  }, [selectedSiteId, sitesById]);

  const buildObservabilityPath = (nextMode = 'overview', overrides = {}) => {
    const params = new URLSearchParams();
    const nextSiteId = overrides.siteId !== undefined ? overrides.siteId : selectedSiteId;
    const nextDeviceId = overrides.deviceId !== undefined ? overrides.deviceId : selectedDeviceId;
    if (nextSiteId) params.set('siteId', String(nextSiteId));
    if (nextDeviceId) params.set('deviceId', String(nextDeviceId));
    const basePath = nextMode === 'deep-dive' ? '/observability/deep-dive' : '/observability';
    const query = params.toString();
    return query ? `${basePath}?${query}` : basePath;
  };

  useEffect(() => {
    if (!canView) return;
    void loadIssueAlerts({ silent: true });
  }, [canView, loadIssueAlerts]);

  const selectedDeviceIssues = useMemo(() => {
    if (!selectedDeviceId) return [];
    return unreadIssues.filter((item) => String(item?.device_id || '') === String(selectedDeviceId));
  }, [unreadIssues, selectedDeviceId]);

  const contextIssues = useMemo(() => {
    if (selectedDevice) return selectedDeviceIssues;
    return filteredIssues;
  }, [selectedDevice, selectedDeviceIssues, filteredIssues]);

  const relatedSiteIssues = useMemo(() => {
    if (!selectedDevice) return [];
    return filteredIssues.filter((item) => String(item?.device_id || '') !== String(selectedDeviceId));
  }, [filteredIssues, selectedDevice, selectedDeviceId]);

  const contextSummary = useMemo(() => ({
    hasScopedContext: Boolean(selectedDevice || selectedSite),
    unreadCount: selectedDevice ? selectedDeviceIssues.length : filteredIssues.length,
  }), [selectedDevice, selectedSite, selectedDeviceIssues.length, filteredIssues.length]);

  const eventStats = useMemo(() => {
    const now = Date.now();
    const ttlMs = 6 * 60 * 60 * 1000;
    const flapWindowMs = 30 * 60 * 1000;
    const recentMs = 60 * 60 * 1000;
    const byFilter = (statusEvents || []).filter((e) => {
      const ts = Date.parse(e?.ts || '');
      if (!Number.isFinite(ts) || now - ts > ttlMs) return false;
      const did = e?.device_id;
      if (did == null) return false;
      if (!selectedSiteId && !filterText) return true;
      return filteredDeviceIdSet.has(String(did));
    });
    const sorted = [...byFilter].sort((a, b) => Date.parse(b?.ts || '') - Date.parse(a?.ts || ''));
    const recent = sorted.filter((e) => now - Date.parse(e.ts) <= recentMs).slice(0, 20);
    const inWindow = sorted.filter((e) => now - Date.parse(e.ts) <= flapWindowMs);

    const counts = new Map();
    for (const e of inWindow) {
      const did = String(e.device_id);
      const cur = counts.get(did) || { count: 0, lastTs: 0, name: e.name, ip: e.ip, site_id: e.site_id };
      cur.count += 1;
      const ts = Date.parse(e.ts);
      if (Number.isFinite(ts) && ts > cur.lastTs) cur.lastTs = ts;
      if (!cur.name && e.name) cur.name = e.name;
      if (!cur.ip && e.ip) cur.ip = e.ip;
      if (cur.site_id == null && e.site_id != null) cur.site_id = e.site_id;
      counts.set(did, cur);
    }
    const flappers = Array.from(counts.entries())
      .map(([deviceId, v]) => ({ deviceId, ...v }))
      .sort((a, b) => (b.count - a.count) || (b.lastTs - a.lastTs))
      .slice(0, 8);

    return { recent, flappers, ttlMs };
  }, [statusEvents, filteredDeviceIdSet, selectedSiteId, filterText]);
  
  const hotspots = useMemo(() => {
    const list = Array.isArray(filteredDevices) ? filteredDevices : [];
    const nowMs = Date.now();
    const topCpu = [...list]
      .sort((a, b) => Number(b?.cpu || 0) - Number(a?.cpu || 0))
      .slice(0, 5);
    const topMem = [...list]
      .sort((a, b) => Number(b?.memory || 0) - Number(a?.memory || 0))
      .slice(0, 5);
    const offlineLongest = list
      .filter((d) => String(d?.status || '').toLowerCase() !== 'online')
      .map((d) => {
        const t = Date.parse(d?.last_seen || '');
        const lastSeenMs = Number.isFinite(t) ? t : 0;
        return { ...d, _offlineMs: lastSeenMs ? Math.max(0, nowMs - lastSeenMs) : Number.POSITIVE_INFINITY };
      })
      .sort((a, b) => Number(b?._offlineMs || 0) - Number(a?._offlineMs || 0))
      .slice(0, 5);
    return { topCpu, topMem, offlineLongest };
  }, [filteredDevices]);

  const recommendedDeepDiveDevice = useMemo(() => {
    if (selectedDevice) return selectedDevice;
    return hotspots.topCpu[0] || hotspots.topMem[0] || hotspots.offlineLongest[0] || filteredDevices[0] || null;
  }, [selectedDevice, hotspots, filteredDevices]);

  const recommendedDeepDivePath = useMemo(() => {
    return buildObservabilityPath('deep-dive', {
      deviceId: recommendedDeepDiveDevice ? String(recommendedDeepDiveDevice.id) : '',
    });
  }, [recommendedDeepDiveDevice, selectedSiteId, selectedDeviceId]);

  const recommendedFocusLabel = useMemo(() => {
    if (!recommendedDeepDiveDevice) return '';
    return recommendedDeepDiveDevice.name || recommendedDeepDiveDevice.ip || `#${recommendedDeepDiveDevice.id}`;
  }, [recommendedDeepDiveDevice]);

  const load = async (isInitial = false) => {
    if (loadInFlightRef.current) return loadInFlightRef.current;
    if (isInitial) setLoading(true);
    const request = (async () => {
      try {
        setLoadError('');
        const previewRes = await PreviewService.getPolicy().catch(() => ({ data: null }));
        const nextPreviewPolicy = previewRes?.data || null;
        setPreviewPolicy(nextPreviewPolicy);

        if (nextPreviewPolicy?.preview_enabled === true) {
          setSummary(null);
          setDevices([]);
          setSelectedDeviceId('');
          return;
        }

        const [summaryRes, devicesRes] = await Promise.all([
          ObservabilityService.summary(),
          ObservabilityService.devices(),
        ]);
        setSummary(summaryRes.data);
        setDevices(Array.isArray(devicesRes.data) ? devicesRes.data : []);

        const existingSelected = selectedDeviceId && (devicesRes.data || []).some((d) => String(d.id) === String(selectedDeviceId));
        if (!existingSelected) {
          const first = (devicesRes.data || [])[0];
          setSelectedDeviceId(first ? String(first.id) : '');
        }
      } catch (e) {
        console.error('Observability load failed:', e);
        const msg = e?.response?.data?.detail || e?.message || t('obs_load_failed', 'Failed to load observability');
        setLoadError(String(msg));
      } finally {
        if (isInitial) setLoading(false);
      }
    })().finally(() => {
      loadInFlightRef.current = null;
    });
    loadInFlightRef.current = request;
    return request;
  };

  const loadOperationalContext = async () => {
    const [statsRes, closedLoopRes, previewRes] = await Promise.all([
      DeviceService.getDashboardStats(selectedSiteId || null).catch(() => ({ data: null })),
      IntentService.getClosedLoopStatus().catch(() => ({ data: null })),
      PreviewService.getPolicy().catch(() => ({ data: null })),
    ]);
    const nextPreviewPolicy = previewRes?.data || null;
    setOpsStats(statsRes?.data || null);
    setClosedLoopStatus(closedLoopRes?.data || null);
    setPreviewPolicy(nextPreviewPolicy);

    if (nextPreviewPolicy?.preview_enabled === false) {
      const [groupsRes, issuesRes] = await Promise.all([
        ServiceGroupService.list().catch(() => ({ data: [] })),
        IssueService.getActiveIssues({ limit: 50 }).catch(() => ({ data: [] })),
      ]);
      setServiceGroups(Array.isArray(groupsRes?.data) ? groupsRes.data : []);
      setServiceImpactIssues(Array.isArray(issuesRes?.data) ? issuesRes.data : []);
    } else {
      setServiceGroups([]);
      setServiceImpactIssues([]);
    }
  };

  const loadTimeseries = async (deviceId) => {
    if (!deviceId) {
      setTimeseries([]);
      return;
    }
    try {
      const res = await ObservabilityService.deviceTimeseries(deviceId, 360, 720);
      const points = (res.data && res.data.points) || [];
      setTimeseries(
        points.map((p) => ({
          time: formatTime(p.ts),
          cpu: p.cpu,
          memory: p.memory,
          in: p.traffic_in_bps,
          out: p.traffic_out_bps,
        }))
      );
    } catch (e) {
      console.error('Timeseries load failed:', e);
      setTimeseries([]);
    }
  };

  const loadInterfaces = async (deviceId) => {
    if (!deviceId) {
      setInterfaces([]);
      setSelectedInterface('');
      return;
    }
    try {
      const res = await ObservabilityService.deviceInterfaces(deviceId);
      const list = Array.isArray(res.data) ? res.data : [];
      setInterfaces(list);
      const exists = selectedInterface && list.some((x) => String(x.interface) === String(selectedInterface));
      if (!exists) {
        setSelectedInterface(list[0]?.interface || '');
      }
    } catch (e) {
      console.error('Interfaces load failed:', e);
      setInterfaces([]);
      setSelectedInterface('');
    }
  };

  const loadInterfaceTimeseries = async (deviceId, name) => {
    if (!deviceId || !name) {
      setInterfaceTimeseries([]);
      return;
    }
    try {
      const res = await ObservabilityService.interfaceTimeseries(deviceId, name, 360, 720);
      const points = (res.data && res.data.points) || [];
      setInterfaceTimeseries(
        points.map((p) => ({
          time: formatTime(p.ts),
          in: p.traffic_in_bps,
          out: p.traffic_out_bps,
          inErr: p.in_errors_per_sec,
          outErr: p.out_errors_per_sec,
          inDrop: p.in_discards_per_sec,
          outDrop: p.out_discards_per_sec,
          errors: Number(p.in_errors_per_sec || 0) + Number(p.out_errors_per_sec || 0),
          drops: Number(p.in_discards_per_sec || 0) + Number(p.out_discards_per_sec || 0),
        }))
      );
    } catch (e) {
      console.error('Interface timeseries load failed:', e);
      setInterfaceTimeseries([]);
    }
  };

  useEffect(() => {
    if (!canView) return;
    load(true);
  }, [canView]);

  useEffect(() => {
    if (!canView) return;
    loadOperationalContext();
  }, [canView, selectedSiteId]);

  const hasOfflineDevices = useMemo(
    () => (Array.isArray(devices) ? devices.some((d) => String(d?.status || '').toLowerCase() !== 'online') : false),
    [devices],
  );
  const observabilityHasActiveSignals = hasOfflineDevices || unreadIssues.length > 0 || !!loadError;
  const observabilityPollIntervalMs = observabilityHasActiveSignals ? 10000 : 20000;
  const observabilityPollMinGapMs = observabilityHasActiveSignals ? 3000 : 8000;

  useVisiblePolling(() => {
    load(false);
    loadOperationalContext();
  }, observabilityPollIntervalMs, {
    enabled: canView,
    immediate: false,
    runOnVisible: true,
    minGapMs: observabilityPollMinGapMs,
    backoffMultiplier: 3,
    backoffMaxIntervalMs: 120000,
  });

  useEffect(() => {
    if (statusRestoreDoneRef.current) return;
    try {
      const raw = sessionStorage.getItem('observability.statusEvents.v1');
      if (raw) {
        const now = Date.now();
        const ttlMs = 6 * 60 * 60 * 1000;
        const parsed = JSON.parse(raw);
        const next = Array.isArray(parsed)
          ? parsed.filter((e) => {
              const ts = Date.parse(e?.ts || '');
              return Number.isFinite(ts) && (now - ts) <= ttlMs;
            })
          : [];
        setStatusEvents(next);
      }
    } catch (e) {
      console.error(e);
    } finally {
      statusRestoreDoneRef.current = true;
    }
  }, []);

  useEffect(() => {
    if (!statusRestoreDoneRef.current) return;
    try {
      sessionStorage.setItem('observability.statusEvents.v1', JSON.stringify(statusEvents.slice(0, 500)));
    } catch (e) {
      console.error(e);
    }
  }, [statusEvents]);

  useEffect(() => {
    if (!canView) return;
    if (!Array.isArray(devices) || devices.length === 0) return;
    const normalizeStatus = (s) => {
      const v = String(s || '').toLowerCase().trim();
      return v === 'online' ? 'online' : 'offline';
    };
    const nowIso = new Date().toISOString();
    const prev = prevStatusRef.current;
    const nextMap = new Map();
    for (const d of devices) {
      const id = d?.id;
      if (id == null) continue;
      nextMap.set(String(id), { status: normalizeStatus(d.status), last_seen: d.last_seen || null, name: d.name, ip: d.ip, site_id: d.site_id });
    }
    if (prev.size === 0) {
      prevStatusRef.current = nextMap;
      return;
    }
    const newEvents = [];
    for (const [id, cur] of nextMap.entries()) {
      const p = prev.get(id);
      if (!p) continue;
      if (p.status !== cur.status) {
        newEvents.push({
          id: `${Date.now()}-${id}-${cur.status}`,
          ts: nowIso,
          device_id: Number.isFinite(Number(id)) ? Number(id) : id,
          name: cur.name || p.name,
          ip: cur.ip || p.ip,
          site_id: cur.site_id ?? p.site_id,
          from: p.status,
          to: cur.status,
        });
      }
    }
    prevStatusRef.current = nextMap;
    if (newEvents.length) {
      setStatusEvents((prevEvents) => [...newEvents, ...(Array.isArray(prevEvents) ? prevEvents : [])].slice(0, 500));
    }
  }, [canView, devices]);

  useEffect(() => {
    if (!canView) return;
    DeviceService.getSites()
      .then((res) => setSites(Array.isArray(res.data) ? res.data : []))
      .catch((e) => console.error('Failed to load sites:', e));
  }, [canView]);

  useEffect(() => {
    if (!canView) return;
    if (!observabilityQuery.siteId) return;
    setSelectedSiteId(String(observabilityQuery.siteId));
  }, [canView, observabilityQuery.siteId]);

  useEffect(() => {
    if (!canView) return;
    if (observabilityQuery.deviceId && filteredDevices.some((d) => String(d.id) === String(observabilityQuery.deviceId))) {
      if (String(selectedDeviceId) !== String(observabilityQuery.deviceId)) {
        setSelectedDeviceId(String(observabilityQuery.deviceId));
      }
      return;
    }
    const exists = filteredDevices.some((d) => String(d.id) === String(selectedDeviceId));
    if (!exists) {
      const first = filteredDevices[0];
      setSelectedDeviceId(first ? String(first.id) : '');
    }
  }, [canView, filteredDevices, observabilityQuery.deviceId, selectedDeviceId]);

  useEffect(() => {
    if (!canView) return;
    loadTimeseries(selectedDeviceId);
  }, [canView, selectedDeviceId]);

  useEffect(() => {
    if (!canView) return;
    loadInterfaces(selectedDeviceId);
  }, [canView, selectedDeviceId]);

  useEffect(() => {
    if (!canView) return;
    loadInterfaceTimeseries(selectedDeviceId, selectedInterface);
  }, [canView, selectedDeviceId, selectedInterface]);


  if (!canView) {
    return (
      <div className="p-6">
        <div className="max-w-3xl bg-white/90 dark:bg-[#1b1d1f]/90 border border-gray-200 dark:border-white/5 rounded-2xl p-6 shadow-sm">
          <div className="text-lg font-bold text-gray-900 dark:text-white">{t('app_access_denied_title', 'Access denied')}</div>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            {t('access_denied_desc', 'Operations Home requires Operator role or higher.')}
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-transparent text-primary-glow font-mono">
        <InlineLoading label={t('common_loading', 'Loading...')} />
      </div>
    );
  }

  const globalCounts = summary?.counts || {};
  const filteredCounts = {
    devices: filteredDevices.length,
    online: filteredDevices.filter((d) => String(d.status || '').toLowerCase() === 'online').length,
    offline: filteredDevices.filter((d) => String(d.status || '').toLowerCase() !== 'online').length,
  };

  const severityBadge = (severity) => {
    const s = String(severity || '').toLowerCase();
    if (s === 'critical') return 'bg-rose-50 text-rose-700 dark:bg-danger/10 dark:text-danger';
    if (s === 'warning') return 'bg-amber-50 text-amber-800 dark:bg-warning/10 dark:text-warning';
    return 'bg-gray-100 text-gray-700 dark:bg-white/5 dark:text-gray-300';
  };

  const serviceHealthBadge = (status) => {
    const value = String(status || '').trim().toLowerCase();
    if (value === 'critical') return 'bg-rose-50 text-rose-700 dark:bg-danger/10 dark:text-danger';
    if (value === 'degraded' || value === 'review') return 'bg-amber-50 text-amber-800 dark:bg-warning/10 dark:text-warning';
    return 'bg-emerald-50 text-emerald-700 dark:bg-success/10 dark:text-success';
  };

  const handleMarkRead = async (id) => {
    try {
      await markIssueAsRead(id);
    } catch (e) {
      console.error('markAsRead failed:', e);
    }
  };

  const renderIssueSnapshot = (issue) => {
    const issueDevice = issue?.device_id != null ? devicesById.get(String(issue.device_id)) : null;
    if (!issueDevice) return null;
    const issueSiteName =
      sitesById.get(String(issueDevice.site_id || ''))?.name ||
      issue.site_name ||
      t('obs_no_site', 'No Site');
    const isOnline = isDeviceOnline(issueDevice.status);

    return (
      <div className="mt-3 rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50/70 dark:bg-white/[0.03] p-3">
        <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
          {t('obs_issue_live_snapshot', 'Live Snapshot')}
        </div>
        <div className="mt-2 grid grid-cols-2 xl:grid-cols-5 gap-2">
          <div className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2">
            <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
              {t('obs_status', 'Status')}
            </div>
            <div className={`mt-1 text-sm font-black ${getDeviceStatusTextClass(issueDevice.status)}`}>
              {isOnline ? t('obs_online', 'Online') : t('obs_offline', 'Offline')}
            </div>
          </div>
          <div className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2">
            <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
              {t('obs_table_cpu', 'CPU')}
            </div>
            <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{Number(issueDevice.cpu || 0).toFixed(0)}%</div>
          </div>
          <div className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2">
            <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
              {t('obs_table_mem', 'Mem')}
            </div>
            <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{Number(issueDevice.memory || 0).toFixed(0)}%</div>
          </div>
          <div className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2">
            <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
              {t('obs_table_in', 'In')}
            </div>
            <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{formatBps(issueDevice.traffic_in_bps)}</div>
          </div>
          <div className="rounded-lg border border-gray-200 dark:border-white/10 px-3 py-2">
            <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
              {t('obs_table_out', 'Out')}
            </div>
            <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{formatBps(issueDevice.traffic_out_bps)}</div>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
          <span>{issueSiteName}</span>
          <span className="text-gray-400">&middot;</span>
          <span>{t('obs_last_seen', 'Last seen')}: {formatRelativeTime(issueDevice.last_seen) || '-'}</span>
        </div>
      </div>
    );
  };

  const issueSectionTitle = selectedDevice
    ? t('obs_related_device_alerts', 'Related Alerts for Current Device')
    : selectedSite
      ? t('obs_related_site_alerts', 'Related Alerts for Current Site')
      : t('obs_active_alerts_unread', 'Active Alerts (Unread)');

  const issueSectionDescription = selectedDevice
    ? t('obs_related_device_alerts_desc', 'Issues for the selected device are prioritized so you can investigate without losing context.')
    : selectedSite
      ? t('obs_related_site_alerts_desc', 'Unread issues for the current site stay visible here while you drill into observability and topology.')
      : t('obs_active_alerts_desc', 'Unread issues stay linked to device, topology, and observability drilldowns.');

  const northboundKpi = opsStats?.northbound_kpi || {};
  const northboundTotals = northboundKpi.totals || {};
  const northboundFailures = Array.isArray(northboundKpi.failure_causes) ? northboundKpi.failure_causes.slice(0, 3) : [];
  const northboundSuccessRate = Number(northboundKpi.success_rate_pct || 0);
  const northboundAvgAttempts = Number(northboundKpi.avg_attempts || 0);
  const northboundP95Attempts = Number(northboundKpi.p95_attempts || 0);
  const northboundStatus = String(northboundKpi.status || 'idle').toLowerCase();
  const closedLoopEngineEnabled = Boolean(closedLoopStatus?.engine_enabled);
  const closedLoopRulesEnabled = Number(closedLoopStatus?.rules_enabled || 0);
  const closedLoopRulesTotal = Number(closedLoopStatus?.rules_total || 0);
  const closedLoopConflicts = Number(closedLoopStatus?.rules_lint?.conflicts_count || 0);
  const closedLoopWarnings = Number(closedLoopStatus?.rules_lint?.warnings_count || 0);
  const closedLoopOperationalStatus = !closedLoopEngineEnabled
    ? 'disabled'
    : closedLoopConflicts > 0
      ? 'warning'
      : closedLoopWarnings > 0
        ? 'healthy'
        : 'enabled';

  const groups = Array.isArray(serviceGroups) ? serviceGroups : [];
  const issues = Array.isArray(serviceImpactIssues) ? serviceImpactIssues : [];
  const reviewStatuses = new Set(['critical', 'degraded', 'review']);
  const reviewGroups = groups.filter((group) => reviewStatuses.has(String(group?.health?.health_status || '').trim().toLowerCase()));
  const avgServiceHealth = groups.length > 0
    ? Math.round(groups.reduce((sum, group) => sum + Number(group?.health?.health_score || 0), 0) / groups.length)
    : 0;
  const topServiceGroups = [...groups]
    .sort((a, b) => {
      const issueDelta = Number(b?.health?.active_issue_count || 0) - Number(a?.health?.active_issue_count || 0);
      if (issueDelta !== 0) return issueDelta;
      const scoreDelta = Number(a?.health?.health_score || 0) - Number(b?.health?.health_score || 0);
      if (scoreDelta !== 0) return scoreDelta;
      return Number(b?.health?.offline_device_count || 0) - Number(a?.health?.offline_device_count || 0);
    })
    .slice(0, 4);
  const serviceAwareIssues = issues
    .filter((issue) => {
      if (Number(issue?.service_impact_summary?.count || 0) <= 0) return false;
      if (selectedDeviceId && String(issue?.device_id || '') !== String(selectedDeviceId)) return false;
      if (selectedSiteId && String(issue?.site_id || '') !== String(selectedSiteId)) return false;
      return true;
    })
    .sort((a, b) => {
      const severityRank = { critical: 0, warning: 1, info: 2 };
      const severityDelta =
        (severityRank[String(a?.severity || '').toLowerCase()] ?? 9) -
        (severityRank[String(b?.severity || '').toLowerCase()] ?? 9);
      if (severityDelta !== 0) return severityDelta;
      return Number(b?.service_impact_summary?.matched_member_count || 0) - Number(a?.service_impact_summary?.matched_member_count || 0);
    });
  const serviceImpactSummary = {
    totalGroups: groups.length,
    reviewGroupCount: reviewGroups.length,
    activeGroupCount: groups.filter((group) => Number(group?.health?.active_issue_count || 0) > 0).length,
    avgHealth: avgServiceHealth,
    serviceAwareIssueCount: serviceAwareIssues.length,
    criticalServiceIssueCount: serviceAwareIssues.filter((issue) => String(issue?.severity || '').trim().toLowerCase() === 'critical').length,
    topGroups: topServiceGroups,
    topIssues: serviceAwareIssues.slice(0, 4),
  };
  const topObservabilityGroup = serviceImpactSummary.topGroups[0];
  const observabilityRecommendedWorkspace = topObservabilityGroup?.health
    ? recommendServiceWorkspace({
        healthStatus: topObservabilityGroup.health.health_status,
        criticalIssueCount: topObservabilityGroup.health.critical_issue_count,
        activeIssueCount: topObservabilityGroup.health.active_issue_count,
        offlineDeviceCount: topObservabilityGroup.health.offline_device_count,
        discoveredOnlyDeviceCount: topObservabilityGroup.health.discovered_only_device_count,
        managedDeviceCount: topObservabilityGroup.health.managed_device_count,
      })
    : (filteredCounts.offline > 0 || filteredIssues.length > 0)
      ? { workspace: 'observe', reason: 'signals' }
      : { workspace: selectedSiteId ? 'discover' : 'govern', reason: selectedSiteId ? 'site_scope' : 'stable' };
  const observabilityWorkspaceLabel = getWorkspaceTitle(observabilityRecommendedWorkspace.workspace, t);

  const pageTitle = isDeepDive
    ? t('obs_deep_dive_title', 'Observability Deep Dive')
    : t('obs_overview_title', 'Observability Overview');
  const pageSubtitle = isDeepDive
    ? t(
        'obs_deep_dive_subtitle',
        'Focus on one device at a time with detailed telemetry, interface behavior, and historical drilldowns.',
      )
    : t(
        'obs_overview_subtitle',
        'Start with fleet health, active issues, and service impact before moving into deeper per-device telemetry.',
      );
  const deviceTableDescription = isDeepDive
    ? t(
        'obs_devices_deep_desc',
        'Use the device table to change focus, then inspect traffic, interface health, and detailed telemetry.',
      )
    : t(
        'obs_devices_overview_desc',
        'Use the inventory table as a lightweight entry point, then open deep dive when you need detailed telemetry.',
      );


  return (
    <div className="flex flex-col h-full min-h-0 min-w-0 gap-6 animate-fade-in text-gray-900 dark:text-white font-sans pb-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-end pb-4 border-b border-gray-200 dark:border-white/5">
        <div>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white/90">{pageTitle}</h1>
            <span className="inline-flex items-center rounded-full border border-blue-200 dark:border-blue-900/40 bg-blue-50 dark:bg-blue-950/20 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-blue-700 dark:text-blue-200">
              {isDeepDive
                ? t('obs_mode_badge_deep_dive', 'Deep Dive')
                : t('obs_mode_badge_overview', 'Overview')}
            </span>
          </div>
          <p className="text-xs text-gray-500 pl-4">{pageSubtitle}</p>
        </div>
        <div className="flex gap-3 items-center flex-wrap justify-end">
          <div className="flex gap-2 items-center">
            <select
              value={selectedSiteId}
              onChange={(e) => setSelectedSiteId(e.target.value)}
              className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 cursor-pointer transition-all hover:bg-gray-50 dark:hover:bg-black/40 hover:border-gray-400 dark:hover:border-white/20"
            >
              <option value="">{t('obs_all_sites', 'All Sites')}</option>
              {sites.map((s) => (
                <option key={s.id} value={String(s.id)}>{s.name}</option>
              ))}
            </select>
            <input
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder={t('obs_search_placeholder', 'Search tags / name / ip')}
              className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 transition-all hover:bg-gray-50 dark:hover:bg-black/40 hover:border-gray-400 dark:hover:border-white/20 w-56"
            />
          </div>
            <a
              href={urls.grafanaHome}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg text-xs font-bold text-gray-700 dark:text-gray-300 transition-colors border border-gray-200 dark:border-white/10 flex items-center gap-2"
            >
              {t('obs_grafana', 'Grafana')} <ExternalLink size={14} />
            </a>
            <a
              href={urls.grafanaAlerts}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg text-xs font-bold text-gray-700 dark:text-gray-300 transition-colors border border-gray-200 dark:border-white/10 flex items-center gap-2"
            >
              {t('obs_alert_dashboard', 'Alert Dashboard')} <ExternalLink size={14} />
            </a>
            <a
              href={urls.prometheusHome}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg text-xs font-bold text-gray-700 dark:text-gray-300 transition-colors border border-gray-200 dark:border-white/10 flex items-center gap-2"
            >
              {t('obs_prometheus', 'Prometheus')} <ExternalLink size={14} />
            </a>
            <a
              href={urls.alertmanagerHome}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg text-xs font-bold text-gray-700 dark:text-gray-300 transition-colors border border-gray-200 dark:border-white/10 flex items-center gap-2"
            >
              {t('obs_alertmanager', 'Alertmanager')} <ExternalLink size={14} />
            </a>
            {isDeepDive ? (
              <button
                type="button"
                data-testid="observability-back-overview"
                onClick={() => navigate(buildObservabilityPath('overview'))}
                className="px-3 py-2 bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg text-xs font-bold text-gray-700 dark:text-gray-300 transition-colors border border-gray-200 dark:border-white/10"
              >
                {t('obs_back_to_overview', 'Back to Overview')}
              </button>
            ) : (
              <button
                type="button"
                data-testid="observability-open-deep-dive"
                onClick={() => navigate(buildObservabilityPath('deep-dive'))}
                className="px-3 py-2 bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg text-xs font-bold text-gray-700 dark:text-gray-300 transition-colors border border-gray-200 dark:border-white/10"
              >
                {t('obs_open_deep_dive', 'Open Deep Dive')}
              </button>
            )}
            <button
              onClick={() => load(true)}
              className="p-2 bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors border border-transparent hover:border-gray-300 dark:hover:border-white/10"
            >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard title={t('obs_devices', 'Devices')} value={filteredCounts.devices} sub={t('obs_filtered_total_fmt', 'Filtered / Total {value}').replace('{value}', String(globalCounts.devices || 0))} />
        <StatCard title={t('obs_online', 'Online')} value={filteredCounts.online} sub={t('obs_filtered_total_fmt', 'Filtered / Total {value}').replace('{value}', String(globalCounts.online || 0))} />
        <StatCard title={t('obs_offline', 'Offline')} value={filteredCounts.offline} sub={t('obs_filtered_total_fmt', 'Filtered / Total {value}').replace('{value}', String(globalCounts.offline || 0))} />
      </div>

      {!isDeepDive ? (
        <div
          data-testid="obs-overview-guided-entry"
          className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5"
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                {t('obs_guided_entry_title', 'Guided Entry')}
              </div>
              <div className="mt-2 text-sm font-black text-gray-900 dark:text-white">
                {recommendedFocusLabel
                  ? t('obs_guided_entry_desc_device', 'Start with fleet and service health here, then move into deep dive for {value}.').replace('{value}', recommendedFocusLabel)
                  : t('obs_guided_entry_desc_default', 'Start with fleet and service health here, then move into deep dive when one device needs closer analysis.')}
              </div>
              <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                {t('obs_guided_entry_hint', 'Use overview for posture and priority, then open deep dive for device telemetry, interface behavior, and time-series detail.')}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="obs-overview-open-workspace"
                onClick={() => navigate(`/automation?workspace=${observabilityRecommendedWorkspace.workspace}`)}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
              >
                {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', observabilityWorkspaceLabel)}
              </button>
              <button
                type="button"
                data-testid="obs-overview-open-deep-dive-primary"
                onClick={() => navigate(recommendedDeepDivePath)}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
              >
                {recommendedFocusLabel
                  ? t('obs_guided_entry_open_device_deep_dive', 'Open Deep Dive for focus device')
                  : t('obs_open_deep_dive', 'Open Deep Dive')}
              </button>
              <button
                type="button"
                data-testid="obs-overview-open-notifications"
                onClick={() => navigate('/notifications')}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
              >
                {t('obs_open_notifications', 'Open Notifications')}
              </button>
              {selectedSiteId ? (
                <button
                  type="button"
                  data-testid="obs-overview-open-topology"
                  onClick={() => navigate(`/topology?siteId=${encodeURIComponent(String(selectedSiteId))}`)}
                  className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  {t('obs_open_topology', 'Open Topology')}
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : (
        <div
          data-testid="obs-deep-dive-focus"
          className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5"
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                {t('obs_deep_focus_title', 'Deep Dive Focus')}
              </div>
              <div className="mt-2 text-sm font-black text-gray-900 dark:text-white">
                {selectedDevice
                  ? t('obs_deep_focus_desc_device', 'Detailed telemetry is focused on {value}.').replace('{value}', selectedDevice.name || selectedDevice.ip || `#${selectedDevice.id}`)
                  : recommendedFocusLabel
                    ? t('obs_deep_focus_desc_recommended', 'No device is pinned yet. Start with {value} to inspect time-series and interfaces.').replace('{value}', recommendedFocusLabel)
                    : t('obs_deep_focus_desc_empty', 'Select a device from the table below to inspect interface behavior and detailed telemetry.')}
              </div>
              <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                {t('obs_deep_focus_hint', 'Deep dive keeps the current site and service context while narrowing analysis to one device at a time.')}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="obs-deep-dive-open-workspace"
                onClick={() => navigate(`/automation?workspace=${observabilityRecommendedWorkspace.workspace}`)}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
              >
                {t('ops_home_service_review_open_workspace', 'Open {workspace}').replace('{workspace}', observabilityWorkspaceLabel)}
              </button>
              {!selectedDevice && recommendedDeepDiveDevice ? (
                <button
                  type="button"
                  data-testid="obs-deep-dive-focus-device"
                  onClick={() => navigate(buildObservabilityPath('deep-dive', { deviceId: String(recommendedDeepDiveDevice.id) }))}
                  className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  {t('obs_deep_focus_pin_device', 'Focus recommended device')}
                </button>
              ) : null}
              {selectedDevice ? (
                <button
                  type="button"
                  data-testid="obs-deep-dive-open-device"
                  onClick={() => navigate(`/devices/${selectedDevice.id}`)}
                  className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  {t('obs_open_device', 'Open Device')}
                </button>
              ) : null}
              <button
                type="button"
                data-testid="obs-deep-dive-open-overview-secondary"
                onClick={() => navigate(buildObservabilityPath('overview'))}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
              >
                {t('obs_back_to_overview', 'Back to Overview')}
              </button>
            </div>
          </div>
        </div>
      )}

      {contextSummary.hasScopedContext ? (
        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                {t('obs_context_title', 'Active Context')}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {selectedSite ? (
                  <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/20 text-xs font-bold">
                    <MapIcon size={14} />
                    {t('obs_context_site_fmt', 'Site: {value}').replace('{value}', selectedSite.name)}
                  </span>
                ) : null}
                {selectedDevice ? (
                  <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300 border border-blue-200 dark:border-blue-500/20 text-xs font-bold">
                    <Server size={14} />
                    {t('obs_context_device_fmt', 'Device: {value}').replace('{value}', selectedDevice.name)}
                  </span>
                ) : null}
                <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300 border border-amber-200 dark:border-amber-500/20 text-xs font-bold">
                  <Bell size={14} />
                  {t('obs_context_unread_fmt', 'Unread issues: {value}').replace('{value}', String(contextSummary.unreadCount))}
                </span>
              </div>
              <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                {t('obs_context_desc', 'Observability follows the current device and site context from the main NMS flow.')}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {selectedDeviceId ? (
                <button
                  onClick={() => navigate(`/devices/${selectedDeviceId}`)}
                  className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  {t('obs_open_device', 'Open Device')}
                </button>
              ) : null}
              {selectedSiteId ? (
                <button
                  onClick={() => navigate(`/topology?siteId=${encodeURIComponent(String(selectedSiteId))}`)}
                  className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  {t('obs_open_topology', 'Open Topology')}
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {showProOperations ? (
        <div
          data-testid="obs-pro-operations-panel"
          className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5"
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                {t('ops_health_title', 'Pro Operational Delivery')}
              </div>
              <div className="mt-2 text-sm font-black text-gray-900 dark:text-white">
                {t('ops_health_desc', 'Northbound delivery and closed-loop state stay visible beside core observability so operators do not lose operational context.')}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                data-testid="obs-open-settings"
                onClick={() => navigate('/settings')}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center gap-2"
              >
                <Settings size={14} />
                {t('ops_open_settings', 'Open Settings')}
              </button>
              <button
                data-testid="obs-open-automation-hub"
                onClick={() => navigate('/automation')}
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center gap-2"
              >
                <Workflow size={14} />
                {t('ops_open_automation_hub', 'Open Operations Home')}
              </button>
              <a
                data-testid="obs-open-alert-dashboard"
                href={urls.grafanaAlerts}
                target="_blank"
                rel="noreferrer"
                className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 inline-flex items-center gap-2"
              >
                {t('obs_alert_dashboard', 'Alert Dashboard')} <ExternalLink size={14} />
              </a>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div data-testid="obs-northbound-health" className="rounded-2xl border border-gray-200 dark:border-white/10 bg-gray-50/70 dark:bg-white/[0.03] p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="inline-flex items-center gap-2 text-sm font-black text-gray-900 dark:text-white">
                  <Globe size={16} className="text-cyan-500" />
                  {t('dashboard_northbound_kpi', 'Northbound KPI')}
                </div>
                <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold uppercase ${statusBadgeClass(northboundStatus)}`}>
                  {getOperationalStatusLabel(northboundStatus)}
                </span>
              </div>
              <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                {getOperationalStatusHint(northboundStatus)}
              </div>
              <div className="mt-3 grid grid-cols-3 gap-3">
                <div className="rounded-xl border border-gray-200 dark:border-white/10 px-3 py-3">
                  <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                    {t('dashboard_delivery_success', 'Delivery Success')}
                  </div>
                  <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">{northboundSuccessRate.toFixed(2)}%</div>
                </div>
                <div className="rounded-xl border border-gray-200 dark:border-white/10 px-3 py-3">
                  <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                    {t('dashboard_attempts', 'Attempts')}
                  </div>
                  <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">{northboundAvgAttempts.toFixed(2)}</div>
                  <div className="text-[11px] text-gray-500 dark:text-gray-400">p95 {northboundP95Attempts.toFixed(0)}</div>
                </div>
                <div className="rounded-xl border border-gray-200 dark:border-white/10 px-3 py-3">
                  <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                    {t('dashboard_failures_24h', 'Failures (24h)')}
                  </div>
                  <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">{Number(northboundTotals.failed_24h || 0)}</div>
                  <div className="text-[11px] text-gray-500 dark:text-gray-400">
                    {Number(northboundTotals.success || 0)} / {Number(northboundTotals.deliveries || 0)}
                  </div>
                </div>
              </div>
              <div className="mt-3 space-y-2">
                {northboundFailures.length > 0 ? northboundFailures.map((row) => (
                  <div key={`${row.cause}-${row.count}`} className="flex items-center justify-between rounded-xl border border-gray-200 dark:border-white/10 px-3 py-2 text-xs">
                    <span className="text-gray-600 dark:text-gray-300 truncate pr-2">{row.cause}</span>
                    <span className="font-mono text-gray-500 dark:text-gray-400">{Number(row.count || 0)}</span>
                  </div>
                )) : (
                  <div className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard_no_delivery_data', 'No delivery data')}</div>
                )}
              </div>
            </div>

            <div data-testid="obs-closed-loop-health" className="rounded-2xl border border-gray-200 dark:border-white/10 bg-gray-50/70 dark:bg-white/[0.03] p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="inline-flex items-center gap-2 text-sm font-black text-gray-900 dark:text-white">
                  <Workflow size={16} className="text-violet-500" />
                  {t('dashboard_closed_loop_kpi', 'Closed-Loop KPI')}
                </div>
                <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold uppercase ${statusBadgeClass(closedLoopOperationalStatus)}`}>
                  {getOperationalStatusLabel(closedLoopOperationalStatus)}
                </span>
              </div>
              <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                {getOperationalStatusHint(closedLoopOperationalStatus)}
              </div>
              <div className="mt-3 grid grid-cols-3 gap-3">
                <div className="rounded-xl border border-gray-200 dark:border-white/10 px-3 py-3">
                  <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                    {t('ops_rules_enabled', 'Rules Enabled')}
                  </div>
                  <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">
                    {closedLoopRulesEnabled} / {closedLoopRulesTotal}
                  </div>
                </div>
                <div className="rounded-xl border border-gray-200 dark:border-white/10 px-3 py-3">
                  <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                    {t('ops_lint_conflicts', 'Lint Conflicts')}
                  </div>
                  <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">{closedLoopConflicts}</div>
                </div>
                <div className="rounded-xl border border-gray-200 dark:border-white/10 px-3 py-3">
                  <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                    {t('ops_lint_warnings', 'Lint Warnings')}
                  </div>
                  <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">{closedLoopWarnings}</div>
                </div>
              </div>
              <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                {closedLoopEngineEnabled
                  ? t('ops_closed_loop_enabled_desc', 'Closed-loop automation is enabled. Keep rules lint clean before promoting direct execution.')
                  : t('ops_closed_loop_disabled_desc', 'Closed-loop automation is currently disabled. Use Operations Home and approval flows until the engine is enabled.')}
              </div>
            </div>
          </div>

          <div
            data-testid="obs-service-impact-panel"
            className="mt-4 rounded-2xl border border-gray-200 dark:border-white/10 bg-gray-50/70 dark:bg-white/[0.03] p-4"
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="text-sm font-black text-gray-900 dark:text-white">
                  {t('obs_service_impact_title', 'Service Impact Snapshot')}
                </div>
                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 max-w-3xl">
                  {t(
                    'obs_service_impact_desc',
                    'Bring service health, impacted groups, and service-scoped issues into the same observability overview before you drill into reports or approvals.',
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  data-testid="obs-open-service-groups"
                  onClick={() => navigate('/service-groups')}
                  className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  {t('obs_open_service_groups', 'Open Service Groups')}
                </button>
                <button
                  type="button"
                  data-testid="obs-open-operations-reports"
                  onClick={() => navigate('/operations-reports')}
                  className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  {t('obs_open_operations_reports', 'Open Operations Reports')}
                </button>
                {serviceImpactSummary.serviceAwareIssueCount > 0 ? (
                  <button
                    type="button"
                    data-testid="obs-open-notifications"
                    onClick={() => navigate('/notifications')}
                    className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                  >
                    {t('obs_open_notifications', 'Open Notifications')}
                  </button>
                ) : null}
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 xl:grid-cols-4 gap-3 text-xs">
              <div className="rounded-xl border border-gray-200 dark:border-white/10 px-3 py-3">
                <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                  {t('obs_service_groups_total', 'Service Groups')}
                </div>
                <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">
                  {Number(serviceImpactSummary.totalGroups || 0)}
                </div>
              </div>
              <div className="rounded-xl border border-amber-200 dark:border-amber-800/60 bg-amber-50/70 dark:bg-amber-500/10 px-3 py-3">
                <div className="text-[10px] font-extrabold text-amber-700 dark:text-amber-300 uppercase tracking-widest">
                  {t('obs_service_groups_review', 'Needs Review')}
                </div>
                <div className="mt-1 text-lg font-black text-amber-700 dark:text-amber-300">
                  {Number(serviceImpactSummary.reviewGroupCount || 0)}
                </div>
              </div>
              <div className="rounded-xl border border-rose-200 dark:border-rose-800/60 bg-rose-50/70 dark:bg-rose-500/10 px-3 py-3">
                <div className="text-[10px] font-extrabold text-rose-700 dark:text-rose-300 uppercase tracking-widest">
                  {t('obs_service_issues_total', 'Service-scoped Issues')}
                </div>
                <div className="mt-1 text-lg font-black text-rose-700 dark:text-rose-300">
                  {Number(serviceImpactSummary.serviceAwareIssueCount || 0)}
                </div>
                <div className="text-[11px] text-rose-700/80 dark:text-rose-300/80">
                  {t('obs_service_issues_critical_fmt', 'Critical {value}').replace(
                    '{value}',
                    String(serviceImpactSummary.criticalServiceIssueCount || 0),
                  )}
                </div>
              </div>
              <div className="rounded-xl border border-emerald-200 dark:border-emerald-800/60 bg-emerald-50/70 dark:bg-emerald-500/10 px-3 py-3">
                <div className="text-[10px] font-extrabold text-emerald-700 dark:text-emerald-300 uppercase tracking-widest">
                  {t('obs_service_health_avg', 'Average Health')}
                </div>
                <div className="mt-1 text-lg font-black text-emerald-700 dark:text-emerald-300">
                  {serviceImpactSummary.avgHealth.toFixed(1)}
                </div>
                <div className="text-[11px] text-emerald-700/80 dark:text-emerald-300/80">
                  {t('obs_service_health_active_groups_fmt', 'Active impact groups {value}').replace(
                    '{value}',
                    String(serviceImpactSummary.activeGroupCount || 0),
                  )}
                </div>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/10 p-4">
                <div className="text-sm font-black text-gray-900 dark:text-white">
                  {t('obs_service_groups_hotspots', 'Service Group Hotspots')}
                </div>
                <div className="mt-3 space-y-2">
                  {serviceImpactSummary.topGroups.length > 0 ? serviceImpactSummary.topGroups.map((group) => (
                    <button
                      key={group.id}
                      type="button"
                      data-testid={`obs-service-group-${group.id}`}
                      onClick={() => navigate(`/topology?serviceOverlay=1&serviceGroupId=${encodeURIComponent(String(group.id))}`)}
                      className="w-full rounded-xl border border-gray-200 dark:border-white/10 px-3 py-3 text-left hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-gray-900 dark:text-white truncate">{group.name}</div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 truncate">
                            {t('obs_service_group_hotspot_meta_fmt', 'Issues {issues} · Offline {offline} · Health {health}')
                              .replace('{issues}', String(group.health?.active_issue_count || 0))
                              .replace('{offline}', String(group.health?.offline_device_count || 0))
                              .replace('{health}', Number(group.health?.health_score || 0).toFixed(1))}
                          </div>
                        </div>
                        <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold uppercase ${serviceHealthBadge(group.health?.health_status)}`}>
                          {String(group.health?.health_status || 'healthy')}
                        </span>
                      </div>
                    </button>
                  )) : (
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {t('obs_service_groups_hotspots_empty', 'No service groups are currently flagged for active impact.')}
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/10 p-4">
                <div className="text-sm font-black text-gray-900 dark:text-white">
                  {t('obs_service_issues_focus', 'Service-aware Issues')}
                </div>
                <div className="mt-3 space-y-2">
                  {serviceImpactSummary.topIssues.length > 0 ? serviceImpactSummary.topIssues.map((issue) => (
                    <button
                      key={issue.id}
                      type="button"
                      data-testid={`obs-service-issue-${issue.id}`}
                      onClick={() => navigate('/operations-reports')}
                      className="w-full rounded-xl border border-gray-200 dark:border-white/10 px-3 py-3 text-left hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-gray-900 dark:text-white truncate">{issue.title || issue.message || `Issue #${issue.id}`}</div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 truncate">
                            {t('obs_service_issue_meta_fmt', '{service} · matched members {members}')
                              .replace('{service}', String(issue._serviceGroupName || t('common_unknown', 'Unknown')))
                              .replace('{members}', String(issue._matchedMemberCount || 0))}
                          </div>
                        </div>
                        <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold uppercase ${severityBadge(issue.severity)}`}>
                          {String(issue.severity || 'info')}
                        </span>
                      </div>
                    </button>
                  )) : (
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {t('obs_service_issues_empty', 'No active issues are currently mapped to service impact in this scope.')}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {loadError ? (
        <div className="bg-rose-50/80 dark:bg-danger/10 border border-rose-200 dark:border-white/10 rounded-2xl p-4 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-black text-rose-800 dark:text-danger">{t('obs_load_failed', 'Failed to load observability')}</div>
            <div className="mt-1 text-xs text-rose-700 dark:text-gray-300 truncate">{loadError}</div>
          </div>
          <button
            onClick={() => load(true)}
            className="px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors"
          >
            {t('obs_retry', 'Retry')}
          </button>
        </div>
      ) : null}

      {!isDeepDive ? (
        filteredDevices.length === 0 ? (
        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
          <div className="text-sm font-black text-gray-900 dark:text-white">{t('obs_empty_title', 'No devices to display')}</div>
          <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">{t('obs_empty_desc', 'Check your site and search filters.')}</div>
        </div>
        ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider mb-4">{t('obs_top_cpu', 'Top CPU')}</div>
            <div className="space-y-2">
              {hotspots.topCpu.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDeviceId(String(d.id))}
                  className="w-full text-left flex items-center justify-between gap-3 p-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 hover:bg-gray-50 dark:hover:bg-white/5"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-black text-gray-900 dark:text-white truncate">{d.name}</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{d.ip}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-black text-gray-900 dark:text-white">{Number(d.cpu || 0).toFixed(0)}%</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400">{formatRelativeTime(d.last_seen) || '-'}</div>
                  </div>
                </button>
              ))}
              {hotspots.topCpu.length === 0 ? <div className="text-sm text-gray-500 dark:text-gray-400">-</div> : null}
            </div>
          </div>

          <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider mb-4">{t('obs_top_memory', 'Top Memory')}</div>
            <div className="space-y-2">
              {hotspots.topMem.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDeviceId(String(d.id))}
                  className="w-full text-left flex items-center justify-between gap-3 p-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 hover:bg-gray-50 dark:hover:bg-white/5"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-black text-gray-900 dark:text-white truncate">{d.name}</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{d.ip}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-black text-gray-900 dark:text-white">{Number(d.memory || 0).toFixed(0)}%</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400">{formatRelativeTime(d.last_seen) || '-'}</div>
                  </div>
                </button>
              ))}
              {hotspots.topMem.length === 0 ? <div className="text-sm text-gray-500 dark:text-gray-400">-</div> : null}
            </div>
          </div>

          <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider mb-4">{t('obs_offline_longest', 'Offline Longest')}</div>
            <div className="space-y-2">
              {hotspots.offlineLongest.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDeviceId(String(d.id))}
                  className="w-full text-left flex items-center justify-between gap-3 p-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 hover:bg-gray-50 dark:hover:bg-white/5"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-black text-gray-900 dark:text-white truncate">{d.name}</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{d.ip}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-black text-rose-700 dark:text-danger">{t('obs_offline', 'Offline')}</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400">{formatRelativeTime(d.last_seen) || '-'}</div>
                  </div>
                </button>
              ))}
              {hotspots.offlineLongest.length === 0 ? <div className="text-sm text-gray-500 dark:text-gray-400">-</div> : null}
            </div>
          </div>
        </div>
        )
      ) : null}

      {!isDeepDive ? (
      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{t('obs_recent_status_changes', 'Recent Status Changes')}</div>
          <div className="flex items-center gap-2">
            <div className="text-xs font-bold text-gray-600 dark:text-gray-300">
              {t('obs_events_flappers_fmt', '{events} events / 1h - {flappers} flappers / 30m').replace('{events}', String(eventStats.recent.length)).replace('{flappers}', String(eventStats.flappers.length))}
            </div>
            <button
              onClick={() => {
                setStatusEvents([]);
                try { sessionStorage.removeItem('observability.statusEvents.v1'); } catch (e) { console.error(e); }
              }}
              className="px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors"
            >
              {t('obs_clear', 'Clear')}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="overflow-auto rounded-xl border border-gray-200 dark:border-white/10">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 dark:bg-black/20 text-xs text-gray-600 dark:text-gray-300">
                <tr>
                  <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_time', 'Time')}</th>
                  <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_device', 'Device')}</th>
                  <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_change', 'Change')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-white/10 bg-white dark:bg-transparent">
                {eventStats.recent.map((e) => (
                  <tr
                    key={e.id || `${e.ts}-${e.device_id}`}
                    className="cursor-pointer hover:bg-gray-50 dark:hover:bg-white/5"
                    onClick={() => setSelectedDeviceId(String(e.device_id))}
                  >
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300 whitespace-nowrap">{formatRelativeTime(e.ts) || '-'}</td>
                    <td className="px-3 py-2 min-w-0">
                      <div className="text-sm font-semibold text-gray-900 dark:text-white truncate">{e.name || `#${e.device_id}`}</div>
                      <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{e.ip || '-'}</div>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold ${String(e.from) === 'online' ? 'bg-emerald-50 text-emerald-700 dark:bg-success/10 dark:text-success' : 'bg-rose-50 text-rose-700 dark:bg-danger/10 dark:text-danger'}`}>
                        {String(e.from || '').toLowerCase() === 'online' ? t('obs_online', 'Online') : t('obs_offline', 'Offline')}
                      </span>
                      <span className="mx-2 text-gray-400">-&gt;</span>
                      <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold ${String(e.to) === 'online' ? 'bg-emerald-50 text-emerald-700 dark:bg-success/10 dark:text-success' : 'bg-rose-50 text-rose-700 dark:bg-danger/10 dark:text-danger'}`}>
                        {String(e.to || '').toLowerCase() === 'online' ? t('obs_online', 'Online') : t('obs_offline', 'Offline')}
                      </span>
                    </td>
                  </tr>
                ))}
                {eventStats.recent.length === 0 ? (
                  <tr>
                    <td className="px-3 py-6 text-sm text-gray-500 dark:text-gray-400" colSpan={3}>
                      {t('obs_no_status_events', 'No status-change events yet. Keep this page open to collect transitions.')}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="space-y-2">
            {eventStats.flappers.map((f) => (
              <button
                key={f.deviceId}
                onClick={() => setSelectedDeviceId(String(f.deviceId))}
                className="w-full text-left flex items-center justify-between gap-3 p-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 hover:bg-gray-50 dark:hover:bg-white/5"
              >
                <div className="min-w-0">
                  <div className="text-sm font-black text-gray-900 dark:text-white truncate">{f.name || `#${f.deviceId}`}</div>
                  <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                    {f.ip || '-'} - {(sitesById.get(String(f.site_id || ''))?.name) || t('obs_no_site', 'No Site')}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-black text-gray-900 dark:text-white">{f.count}</div>
                  <div className="text-[11px] text-gray-500 dark:text-gray-400">{t('obs_changes_30m', 'changes / 30m')}</div>
                </div>
              </button>
            ))}
            {eventStats.flappers.length === 0 ? (
              <div className="text-sm text-gray-500 dark:text-gray-400">{t('obs_no_flap_30m', 'No flap detected in the last 30 minutes.')}</div>
            ) : null}
          </div>
        </div>
      </div>
      ) : null}

      {!isDeepDive ? (
      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex flex-col gap-3 mb-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{issueSectionTitle}</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{issueSectionDescription}</div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {selectedDevice ? (
              <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300 border border-blue-200 dark:border-blue-500/20 text-xs font-bold">
                <Server size={14} />
                {selectedDevice.name}
              </span>
            ) : null}
            {selectedSite ? (
              <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/20 text-xs font-bold">
                <MapIcon size={14} />
                {selectedSite.name}
              </span>
            ) : null}
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300 border border-amber-200 dark:border-amber-500/20 text-xs font-bold">
              <Bell size={14} />
              {t('obs_context_unread_fmt', 'Unread issues: {value}').replace('{value}', String(contextIssues.length))}
            </span>
          </div>
        </div>
        <div className="space-y-3">
          {contextIssues.slice(0, 12).map((i) => (
            <div key={i.id} className="rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 p-4">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold ${severityBadge(i.severity)}`}>
                      {String(i.severity || 'info').toUpperCase()}
                    </span>
                    {i.site_name ? (
                      <span className="px-2 py-1 rounded-full text-[11px] font-extrabold bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/20">
                        {i.site_name}
                      </span>
                    ) : null}
                    <div className="text-sm font-black text-gray-900 dark:text-white break-words">{i.title}</div>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
                    <span>{i.device || t('common_unknown', 'Unknown')}</span>
                    <span className="text-gray-400">&middot;</span>
                    <span>{formatRelativeTime(i.created_at)}</span>
                  </div>
                  {i.message ? (
                    <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      {i.message}
                    </div>
                  ) : null}
                  {renderIssueSnapshot(i)}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {i.device_id ? (
                    <button
                      onClick={() => navigate(`/devices/${i.device_id}`)}
                      className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                    >
                      {t('obs_open_device', 'Open Device')}
                    </button>
                  ) : null}
                  {i.site_id ? (
                    <button
                      onClick={() => navigate(`/topology?siteId=${encodeURIComponent(String(i.site_id))}`)}
                      className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                    >
                      {t('obs_open_topology', 'Open Topology')}
                    </button>
                  ) : null}
                  <a
                    href={buildGrafanaFleetHealthUrl({ deviceId: i.device_id || undefined, siteId: i.site_id || undefined })}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 flex items-center gap-2"
                  >
                    {t('obs_grafana', 'Grafana')} <ExternalLink size={14} />
                  </a>
                  <a
                    href={buildGrafanaAlertingCenterUrl({ deviceId: i.device_id || undefined, siteId: i.site_id || undefined })}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 flex items-center gap-2"
                  >
                    {t('obs_alert_dashboard', 'Alert Dashboard')} <ExternalLink size={14} />
                  </a>
                  <button
                    onClick={() => handleMarkRead(i.id)}
                    className="px-3 py-2 rounded-lg text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors"
                  >
                    {t('obs_mark_read', 'Read')}
                  </button>
                </div>
              </div>
            </div>
          ))}
          {contextIssues.length === 0 ? (
            <div className="text-sm text-gray-500 dark:text-gray-400">{t('obs_no_unread_alerts', 'No unread alerts right now.')}</div>
          ) : null}
          {selectedDevice && relatedSiteIssues.length > 0 ? (
            <div className="rounded-xl border border-dashed border-gray-200 dark:border-white/10 bg-white/50 dark:bg-black/10 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                    {t('obs_related_site_alerts', 'Related Alerts for Current Site')}
                  </div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {t('obs_related_site_alerts_desc', 'Unread issues for the current site stay visible here while you drill into observability and topology.')}
                  </div>
                </div>
                <div className="text-xs font-bold text-gray-600 dark:text-gray-300">
                  {relatedSiteIssues.length}
                </div>
              </div>
              <div className="mt-3 space-y-2">
                {relatedSiteIssues.slice(0, 5).map((i) => (
                  <button
                    key={`related-${i.id}`}
                    onClick={() => i.device_id && setSelectedDeviceId(String(i.device_id))}
                    className="w-full text-left rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 p-3 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold ${severityBadge(i.severity)}`}>
                        {String(i.severity || 'info').toUpperCase()}
                      </span>
                      <span className="text-sm font-black text-gray-900 dark:text-white">{i.title}</span>
                    </div>
                    <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      {(i.device || t('common_unknown', 'Unknown'))} &middot; {formatRelativeTime(i.created_at)}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
      ) : null}

      {!isDeepDive ? (
      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-blue-500 dark:text-primary" />
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{t('obs_device_status_heatmap', 'Device Status Heatmap')}</div>
          </div>
          <div className="flex items-center gap-3 text-xs font-bold text-gray-600 dark:text-gray-300">
            <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-emerald-500"></span> {t('obs_online', 'Online')}</div>
            <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-rose-500"></span> {t('obs_offline', 'Offline')}</div>
          </div>
        </div>
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}>
          {filteredDevices.map((d) => {
            const isOnline = isDeviceOnline(d.status);
            const isSelected = String(d.id) === String(selectedDeviceId);
            const siteName = sitesById.get(String(d.site_id || ''))?.name;
            return (
              <button
                key={d.id}
                onClick={() => setSelectedDeviceId(String(d.id))}
                title={`${d.name} (${d.ip})\n${siteName || t('obs_no_site', 'No Site')}\n${isOnline ? t('obs_online', 'Online') : t('obs_offline', 'Offline')}\n${t('obs_last_seen', 'Last seen')}: ${d.last_seen || ''}`}
                className={`text-left rounded-xl p-3 border transition-all ${isSelected ? 'border-blue-500/60 shadow-[0_0_15px_rgba(59,130,246,0.15)]' : 'border-gray-200 dark:border-white/10'} ${isOnline ? 'bg-emerald-50/80 dark:bg-success/10' : 'bg-rose-50/80 dark:bg-danger/10'}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-black truncate text-gray-900 dark:text-white">{d.name}</div>
                  <span className={`w-2.5 h-2.5 rounded-full ${getDeviceStatusDotClass(d.status)}`}></span>
                </div>
                <div className="mt-1 text-[11px] font-bold text-gray-600 dark:text-gray-300 truncate">{d.ip}</div>
                <div className="mt-1 text-[10px] text-gray-500 dark:text-gray-400 truncate">{siteName || t('obs_no_site', 'No Site')}</div>
              </button>
            );
          })}
        </div>
      </div>
      ) : null}

      {isDeepDive ? (
      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-blue-500 dark:text-primary" />
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{t('obs_device_telemetry', 'Device Telemetry')}</div>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={selectedDeviceId}
              onChange={(e) => setSelectedDeviceId(e.target.value)}
              className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 cursor-pointer transition-all hover:bg-gray-50 dark:hover:bg-black/40 hover:border-gray-400 dark:hover:border-white/20"
            >
              {filteredDevices.map((d) => (
                <option key={d.id} value={String(d.id)}>
                  {d.name} ({d.ip})
                </option>
              ))}
            </select>
            <button
              disabled={!selectedDeviceId}
              onClick={() => selectedDeviceId && navigate(`/devices/${selectedDeviceId}`)}
              className={`px-3 py-2 rounded-lg text-xs font-extrabold transition-colors border ${
                !selectedDeviceId
                  ? 'bg-gray-100 text-gray-500 dark:bg-white/5 dark:text-gray-500 border-transparent cursor-not-allowed'
                  : 'bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 border-gray-200 dark:border-white/10'
              }`}
            >
              {t('obs_open_device', 'Open Device')}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4 min-h-[320px]">
            <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">
              {t('obs_traffic_bps', 'Traffic (bps)')}
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeseries}>
                <defs>
                  <linearGradient id="obsIn" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="obsOut" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" vertical={false} />
                <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis
                  stroke="#64748b"
                  fontSize={10}
                  tickLine={false}
                  axisLine={false}
                  width={55}
                  tickFormatter={(v) => formatBps(v)}
                />
                <Tooltip
                  formatter={(v, name) => [formatBps(v), name === 'in' ? 'in' : 'out']}
                  contentStyle={{
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    color: '#fff',
                    borderRadius: '12px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                    backdropFilter: 'blur(8px)'
                  }}
                  itemStyle={{ fontSize: '12px', fontWeight: '500' }}
                  labelStyle={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '11px', textTransform: 'uppercase' }}
                />
                <Area type="monotone" dataKey="in" stroke="#3b82f6" strokeWidth={2.5} fill="url(#obsIn)" />
                <Area type="monotone" dataKey="out" stroke="#6366f1" strokeWidth={2.5} fill="url(#obsOut)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4 min-h-[320px]">
            <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">
              {t('obs_cpu_memory_pct', 'CPU / Memory (%)')}
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeseries}>
                <defs>
                  <linearGradient id="obsCpu" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="obsMem" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" vertical={false} />
                <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} width={35} domain={[0, 100]} />
                <Tooltip
                  formatter={(v, name) => [`${Number(v || 0).toFixed(0)}%`, name === 'cpu' ? 'cpu' : 'memory']}
                  contentStyle={{
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    color: '#fff',
                    borderRadius: '12px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                    backdropFilter: 'blur(8px)'
                  }}
                  itemStyle={{ fontSize: '12px', fontWeight: '500' }}
                  labelStyle={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '11px', textTransform: 'uppercase' }}
                />
                <Area type="monotone" dataKey="cpu" stroke="#10b981" strokeWidth={2.5} fill="url(#obsCpu)" />
                <Area type="monotone" dataKey="memory" stroke="#f59e0b" strokeWidth={2.5} fill="url(#obsMem)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4">
            {selectedDevice ? (
              <>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-black text-gray-900 dark:text-white truncate">{selectedDevice.name || '-'}</div>
                    <div className="mt-1 text-xs text-gray-600 dark:text-gray-300 truncate">{selectedDevice.ip || '-'}</div>
                    <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400 truncate">
                      {(sitesById.get(String(selectedDevice.site_id || ''))?.name) || t('obs_no_site', 'No Site')} - {selectedDevice.role || t('obs_unknown', 'unknown')}
                    </div>
                  </div>
                  <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold border ${getDeviceStatusChipClass(selectedDevice.status)}`}>
                    {isDeviceOnline(selectedDevice.status) ? t('obs_online', 'Online') : t('obs_offline', 'Offline')}
                  </span>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-gray-200 dark:border-white/10 p-3">
                    <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{t('obs_table_cpu', 'CPU')}</div>
                    <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">{Number(selectedDevice.cpu || 0).toFixed(0)}%</div>
                  </div>
                  <div className="rounded-xl border border-gray-200 dark:border-white/10 p-3">
                    <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{t('obs_table_mem', 'Mem')}</div>
                    <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">{Number(selectedDevice.memory || 0).toFixed(0)}%</div>
                  </div>
                  <div className="rounded-xl border border-gray-200 dark:border-white/10 p-3">
                    <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{t('obs_table_in', 'In')}</div>
                    <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{formatBps(selectedDevice.traffic_in_bps)}</div>
                  </div>
                  <div className="rounded-xl border border-gray-200 dark:border-white/10 p-3">
                    <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{t('obs_table_out', 'Out')}</div>
                    <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{formatBps(selectedDevice.traffic_out_bps)}</div>
                  </div>
                </div>

                <div className="mt-3 text-[11px] text-gray-500 dark:text-gray-400">
                  {t('obs_last_seen', 'Last seen')}: {formatRelativeTime(selectedDevice.last_seen) || '-'}
                </div>
              </>
            ) : (
              <InlineEmpty label={t('obs_selected_device_none', 'No selected device.')} />
            )}
          </div>
        </div>
      </div>
      ) : null}

      {isDeepDive ? (
      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-blue-500 dark:text-primary" />
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{t('obs_interface_telemetry', 'Interface Telemetry')}</div>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={selectedInterface}
              onChange={(e) => setSelectedInterface(e.target.value)}
              className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 cursor-pointer transition-all hover:bg-gray-50 dark:hover:bg-black/40 hover:border-gray-400 dark:hover:border-white/20"
            >
              {sortedInterfaces.map((x) => (
                <option key={x.interface} value={x.interface}>
                  {x.interface}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4 min-h-[300px]">
              <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">
                {t('obs_interface_traffic_bps', 'Interface Traffic (bps)')}
              </div>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={interfaceTimeseries}>
                  <defs>
                    <linearGradient id="ifIn" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="ifOut" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" vertical={false} />
                  <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis
                    stroke="#64748b"
                    fontSize={10}
                    tickLine={false}
                    axisLine={false}
                    width={55}
                    tickFormatter={(v) => formatBps(v)}
                  />
                  <Tooltip
                    formatter={(v, name) => [formatBps(v), name === 'in' ? 'in' : 'out']}
                    contentStyle={{
                      backgroundColor: 'rgba(15, 23, 42, 0.9)',
                      borderColor: 'rgba(255,255,255,0.1)',
                      color: '#fff',
                      borderRadius: '12px',
                      boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                      backdropFilter: 'blur(8px)'
                    }}
                    itemStyle={{ fontSize: '12px', fontWeight: '500' }}
                    labelStyle={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '11px', textTransform: 'uppercase' }}
                  />
                  <Area type="monotone" dataKey="in" stroke="#3b82f6" strokeWidth={2.5} fill="url(#ifIn)" />
                  <Area type="monotone" dataKey="out" stroke="#6366f1" strokeWidth={2.5} fill="url(#ifOut)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4 min-h-[300px]">
              <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">
                {t('obs_interface_errors_drops', 'Interface Errors / Drops (per sec)')}
              </div>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={interfaceTimeseries}>
                  <defs>
                    <linearGradient id="ifErr" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ef4444" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="ifDrop" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" vertical={false} />
                  <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} width={45} />
                  <Tooltip
                    formatter={(v, name) => [Number(v || 0).toFixed(2), name]}
                    contentStyle={{
                      backgroundColor: 'rgba(15, 23, 42, 0.9)',
                      borderColor: 'rgba(255,255,255,0.1)',
                      color: '#fff',
                      borderRadius: '12px',
                      boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                      backdropFilter: 'blur(8px)'
                    }}
                    itemStyle={{ fontSize: '12px', fontWeight: '500' }}
                    labelStyle={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '11px', textTransform: 'uppercase' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="errors"
                    name="errors"
                    stroke="#ef4444"
                    strokeWidth={2.25}
                    fill="url(#ifErr)"
                  />
                  <Area
                    type="monotone"
                    dataKey="drops"
                    name="drops"
                    stroke="#f59e0b"
                    strokeWidth={2.25}
                    fill="url(#ifDrop)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4">
            <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">
              {t('obs_interfaces_top', 'Interfaces (top)')}
            </div>
            <div className="overflow-auto rounded-xl border border-gray-200 dark:border-white/10">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 dark:bg-black/20 text-xs text-gray-600 dark:text-gray-300">
                  <tr>
                    <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_interface_col_interface', 'Interface')}</th>
                    <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_in', 'In')}</th>
                    <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_out', 'Out')}</th>
                    <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_interface_col_err', 'Err/s')}</th>
                    <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_interface_col_drop', 'Drop/s')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-white/10 bg-white dark:bg-transparent">
                  {sortedInterfaces.slice(0, 20).map((x) => {
                    const isSelected = String(x.interface) === String(selectedInterface);
                    const err = Number(x.in_errors_per_sec || 0) + Number(x.out_errors_per_sec || 0);
                    const drop = Number(x.in_discards_per_sec || 0) + Number(x.out_discards_per_sec || 0);
                    return (
                      <tr
                        key={x.interface}
                        className={`cursor-pointer hover:bg-gray-50 dark:hover:bg-white/5 ${isSelected ? 'bg-blue-50/60 dark:bg-blue-600/10' : ''}`}
                        onClick={() => setSelectedInterface(x.interface)}
                      >
                        <td className="px-3 py-2 font-semibold text-gray-900 dark:text-white">{x.interface}</td>
                        <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{formatBps(x.traffic_in_bps)}</td>
                        <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{formatBps(x.traffic_out_bps)}</td>
                        <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{err.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{drop.toFixed(2)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
      ) : null}

      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-4">
          <div>
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">
              {t('obs_devices', 'Devices')}
            </div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{deviceTableDescription}</div>
          </div>
          {!isDeepDive ? (
            <button
              type="button"
              data-testid="observability-open-deep-dive-inline"
              onClick={() => navigate(buildObservabilityPath('deep-dive'))}
              className="px-3 py-2 rounded-lg text-xs font-bold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
            >
              {t('obs_open_deep_dive', 'Open Deep Dive')}
            </button>
          ) : null}
        </div>
        <div
          className="overflow-auto rounded-xl border border-gray-200 dark:border-white/10"
          ref={deviceTableScrollRef}
          onScroll={onDeviceTableVirtualScroll}
        >
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-black/20 text-xs text-gray-600 dark:text-gray-300">
              <tr>
                <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_name', 'Name')}</th>
                <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_ip', 'IP')}</th>
                <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_site', 'Site')}</th>
                <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_status', 'Status')}</th>
                <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_cpu', 'CPU')}</th>
                <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_mem', 'Mem')}</th>
                <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_in', 'In')}</th>
                <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_out', 'Out')}</th>
                <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">{t('obs_table_last_seen', 'Last Seen')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-white/10 bg-white dark:bg-transparent">
              {virtualDevicePaddingTop > 0 && (
                <tr aria-hidden="true">
                  <td colSpan="9" style={{ height: `${virtualDevicePaddingTop}px`, padding: 0, border: 0 }} />
                </tr>
              )}
              {visibleDeviceRows.map((d) => {
                const isOnline = String(d.status || '').toLowerCase() === 'online';
                const siteName = sitesById.get(String(d.site_id || ''))?.name;
                return (
                  <tr
                    key={d.id}
                    className="hover:bg-gray-50 dark:hover:bg-white/5 cursor-pointer"
                    onClick={() => setSelectedDeviceId(String(d.id))}
                  >
                    <td className="px-3 py-2 font-semibold text-gray-900 dark:text-white">{d.name}</td>
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{d.ip}</td>
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{siteName || '-'}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`px-2 py-1 rounded-full text-xs font-bold ${
                          isOnline
                            ? 'bg-emerald-50 text-emerald-700 dark:bg-success/10 dark:text-success'
                            : 'bg-rose-50 text-rose-700 dark:bg-danger/10 dark:text-danger'
                        }`}
                      >
                        {isOnline ? t('obs_online', 'Online') : t('obs_offline', 'Offline')}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{Number(d.cpu || 0).toFixed(0)}%</td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{Number(d.memory || 0).toFixed(0)}%</td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{formatBps(d.traffic_in_bps)}</td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{formatBps(d.traffic_out_bps)}</td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{formatRelativeTime(d.last_seen)}</td>
                  </tr>
                );
              })}
              {virtualDevicePaddingBottom > 0 && (
                <tr aria-hidden="true">
                  <td colSpan="9" style={{ height: `${virtualDevicePaddingBottom}px`, padding: 0, border: 0 }} />
                </tr>
              )}
              {filteredDevices.length > 0 && (
                <tr>
                  <td colSpan="9" className="px-3 py-2 text-center text-xs text-gray-500 dark:text-gray-400">
                    {t('obs_rendering_progress', 'Rendering {visible}/{total}')
                      .replace('{visible}', String(visibleDeviceEndIndex - visibleDeviceStartIndex))
                      .replace('{total}', String(totalDeviceRowsCount))}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ObservabilityPage;
