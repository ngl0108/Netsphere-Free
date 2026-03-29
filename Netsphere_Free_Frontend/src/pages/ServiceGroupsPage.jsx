import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Boxes, Cloud, Network, Plus, RefreshCw, Save, Server, Trash2 } from 'lucide-react';

import { ServiceGroupService } from '../api/services';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { t } from '../i18n';
import { useLocaleRerender } from '../i18n/useLocaleRerender';

const PANEL_CLASS = 'rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] shadow-sm';

const DEFAULT_FORM = {
  name: '',
  description: '',
  criticality: 'standard',
  owner_team: '',
  color: '#0ea5e9',
  is_active: true,
};

const Input = ({ value, onChange, placeholder, type = 'text' }) => (
  <input
    type={type}
    value={value}
    onChange={(event) => onChange(event.target.value)}
    placeholder={placeholder}
    className="w-full rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
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

const Select = ({ value, onChange, children }) => (
  <select
    value={value}
    onChange={(event) => onChange(event.target.value)}
    className="w-full rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] px-4 py-3 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
  >
    {children}
  </select>
);

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

const toneForCriticality = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'high') return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-300';
  if (normalized === 'elevated') return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
  return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300';
};

const toneForHealth = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'critical') return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-300';
  if (normalized === 'degraded' || normalized === 'review') return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-300';
  return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300';
};

const ServiceGroupsPage = () => {
  useLocaleRerender();
  const { isAtLeast } = useAuth();
  const { toast } = useToast();
  const canOperate = isAtLeast('operator');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const editorRef = useRef(null);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [addingDevice, setAddingDevice] = useState(false);
  const [addingCloud, setAddingCloud] = useState(false);
  const [groups, setGroups] = useState([]);
  const [catalog, setCatalog] = useState({ devices: [], cloud_resources: [] });
  const [selectedGroupId, setSelectedGroupId] = useState(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [selectedCloudId, setSelectedCloudId] = useState('');
  const [form, setForm] = useState(DEFAULT_FORM);

  const selectedGroup = useMemo(
    () => groups.find((item) => Number(item.id) === Number(selectedGroupId)) || null,
    [groups, selectedGroupId],
  );

  const summary = useMemo(() => {
    const rows = Array.isArray(groups) ? groups : [];
    const deviceCount = rows.reduce((sum, item) => sum + Number(item.device_count || 0), 0);
    const cloudCount = rows.reduce((sum, item) => sum + Number(item.cloud_resource_count || 0), 0);
    const avgHealth = rows.length > 0
      ? Math.round(rows.reduce((sum, item) => sum + Number(item?.health?.health_score || 0), 0) / rows.length)
      : 0;
    const reviewGroups = rows.filter((item) => ['critical', 'degraded', 'review'].includes(String(item?.health?.health_status || '').trim().toLowerCase())).length;
    return {
      totalGroups: rows.length,
      deviceCount,
      cloudCount,
      avgHealth,
      reviewGroups,
    };
  }, [groups]);

  const reviewQueue = useMemo(() => {
    const statusRank = {
      critical: 0,
      degraded: 1,
      review: 1,
      healthy: 2,
    };
    const criticalityRank = {
      high: 0,
      elevated: 1,
      standard: 2,
    };

    return (Array.isArray(groups) ? groups : [])
      .map((group) => {
        const health = group?.health || {};
        const healthStatus = String(health.health_status || 'healthy').trim().toLowerCase() || 'healthy';
        const activeIssueCount = Number(health.active_issue_count || 0);
        const criticalIssueCount = Number(health.critical_issue_count || 0);
        const offlineDeviceCount = Number(health.offline_device_count || 0);
        const managedDeviceCount = Number(health.managed_device_count || 0);
        const discoveredOnlyDeviceCount = Number(health.discovered_only_device_count || 0);
        const healthScore = Number(health.health_score || 0);
        const criticality = String(group?.criticality || 'standard').trim().toLowerCase() || 'standard';
        const reviewNeeded = ['critical', 'degraded', 'review'].includes(healthStatus) || activeIssueCount > 0 || offlineDeviceCount > 0;
        let nextAction = t('service_groups_review_next_action_stable', '서비스 맵과 토폴로지 기준선을 유지하세요.');
        if (healthStatus === 'critical' || criticalIssueCount > 0) {
          nextAction = t('service_groups_review_next_action_critical', '영향 이슈와 토폴로지를 먼저 열어 즉시 원인을 검토하세요.');
        } else if (offlineDeviceCount > 0) {
          nextAction = t('service_groups_review_next_action_offline', '오프라인 장비와 연결된 경로를 열어 운영 상태를 점검하세요.');
        } else if (discoveredOnlyDeviceCount > managedDeviceCount) {
          nextAction = t('service_groups_review_next_action_discovered_only', '발견 전용 장비 비중이 높습니다. 관리 대상으로 승격할 장비를 검토하세요.');
        } else if (activeIssueCount > 0) {
          nextAction = t('service_groups_review_next_action_issues', '알림 흐름과 운영 보고서에서 후속 조치를 정리하세요.');
        }
        return {
          ...group,
          reviewNeeded,
          healthStatus,
          healthScore,
          activeIssueCount,
          criticalIssueCount,
          offlineDeviceCount,
          managedDeviceCount,
          discoveredOnlyDeviceCount,
          nextAction,
          sortKey: [
            statusRank[healthStatus] ?? 3,
            criticalityRank[criticality] ?? 3,
            -criticalIssueCount,
            -activeIssueCount,
            -offlineDeviceCount,
            healthScore,
          ],
        };
      })
      .filter((group) => group.reviewNeeded)
      .sort((a, b) => {
        for (let index = 0; index < Math.max(a.sortKey.length, b.sortKey.length); index += 1) {
          const left = a.sortKey[index] ?? 0;
          const right = b.sortKey[index] ?? 0;
          if (left !== right) return left - right;
        }
        return String(a.name || '').localeCompare(String(b.name || ''));
      })
      .slice(0, 4);
  }, [groups]);

  const loadAll = async (preferredGroupId = null) => {
    setLoading(true);
    try {
      const [groupsRes, catalogRes] = await Promise.all([
        ServiceGroupService.list(),
        ServiceGroupService.getCatalog(),
      ]);
      const nextGroups = Array.isArray(groupsRes.data) ? groupsRes.data : [];
      const nextCatalog = catalogRes.data || { devices: [], cloud_resources: [] };
      setCatalog({
        devices: Array.isArray(nextCatalog.devices) ? nextCatalog.devices : [],
        cloud_resources: Array.isArray(nextCatalog.cloud_resources) ? nextCatalog.cloud_resources : [],
      });
      let focusId = preferredGroupId;
      if (focusId == null && nextGroups.length > 0) {
        const selectedStillExists = nextGroups.some((item) => Number(item.id) === Number(selectedGroupId));
        focusId = selectedStillExists ? selectedGroupId : nextGroups[0].id;
      }
      if (focusId != null) {
        try {
          const detailRes = await ServiceGroupService.get(focusId);
          const detail = detailRes.data || null;
          const merged = nextGroups.map((item) => (Number(item.id) === Number(detail?.id) ? detail : item));
          setGroups(merged);
          setSelectedGroupId(detail?.id ?? null);
          setForm(
            detail
              ? {
                  name: detail.name || '',
                  description: detail.description || '',
                  criticality: detail.criticality || 'standard',
                  owner_team: detail.owner_team || '',
                  color: detail.color || '#0ea5e9',
                  is_active: detail.is_active !== false,
                }
              : DEFAULT_FORM,
          );
        } catch (error) {
          setGroups(nextGroups);
          setSelectedGroupId(nextGroups[0]?.id ?? null);
          setForm(DEFAULT_FORM);
        }
      } else {
        setGroups(nextGroups);
        setSelectedGroupId(null);
        setForm(DEFAULT_FORM);
      }
    } catch (error) {
      toast.error(`${t('service_groups_load_failed', '서비스 그룹을 불러오지 못했습니다')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const focusGroupId = Number(searchParams.get('focusGroupId') || 0);
    void loadAll(focusGroupId > 0 ? focusGroupId : null);
  }, [searchParams]);

  const handleNew = () => {
    setSelectedGroupId(null);
    setForm(DEFAULT_FORM);
    setSelectedDeviceId('');
    setSelectedCloudId('');
  };

  const handleSelectGroup = async (groupId) => {
    setLoading(true);
    try {
      const res = await ServiceGroupService.get(groupId);
      const detail = res.data || null;
      setGroups((prev) => prev.map((item) => (Number(item.id) === Number(groupId) ? detail : item)));
      setSelectedGroupId(detail?.id ?? null);
      setForm(
        detail
          ? {
              name: detail.name || '',
              description: detail.description || '',
              criticality: detail.criticality || 'standard',
              owner_team: detail.owner_team || '',
              color: detail.color || '#0ea5e9',
              is_active: detail.is_active !== false,
            }
          : DEFAULT_FORM,
      );
    } catch (error) {
      toast.error(`${t('service_groups_load_failed', '서비스 그룹을 불러오지 못했습니다')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const focusGroupReview = async (groupId) => {
    await handleSelectGroup(groupId);
    window.requestAnimationFrame(() => {
      editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  const handleSave = async () => {
    if (!String(form.name || '').trim()) {
      toast.error(t('service_groups_name_required', '서비스 그룹 이름을 입력하세요.'));
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: String(form.name || '').trim(),
        description: String(form.description || '').trim() || null,
        criticality: String(form.criticality || 'standard'),
        owner_team: String(form.owner_team || '').trim() || null,
        color: String(form.color || '#0ea5e9'),
        is_active: Boolean(form.is_active),
      };
      const res = selectedGroupId
        ? await ServiceGroupService.update(selectedGroupId, payload)
        : await ServiceGroupService.create(payload);
      const detail = res.data || null;
      toast.success(
        selectedGroupId
          ? t('service_groups_saved', '서비스 그룹을 저장했습니다.')
          : t('service_groups_created', '서비스 그룹을 생성했습니다.'),
      );
      await loadAll(detail?.id ?? null);
    } catch (error) {
      toast.error(`${t('service_groups_save_failed', '서비스 그룹 저장에 실패했습니다')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedGroupId) return;
    if (!window.confirm(t('service_groups_delete_confirm', '이 서비스 그룹을 삭제할까요?'))) return;
    try {
      await ServiceGroupService.delete(selectedGroupId);
      toast.success(t('service_groups_deleted', '서비스 그룹을 삭제했습니다.'));
      await loadAll(null);
    } catch (error) {
      toast.error(`${t('service_groups_delete_failed', '서비스 그룹 삭제에 실패했습니다')}: ${error?.response?.data?.detail || error.message}`);
    }
  };

  const handleAddDevice = async () => {
    if (!selectedGroupId || !selectedDeviceId) return;
    setAddingDevice(true);
    try {
      await ServiceGroupService.addDevice(selectedGroupId, selectedDeviceId);
      toast.success(t('service_groups_device_added', '장비를 서비스 그룹에 추가했습니다.'));
      setSelectedDeviceId('');
      await loadAll(selectedGroupId);
    } catch (error) {
      toast.error(`${t('service_groups_add_member_failed', '구성원 추가에 실패했습니다')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setAddingDevice(false);
    }
  };

  const handleAddCloud = async () => {
    if (!selectedGroupId || !selectedCloudId) return;
    setAddingCloud(true);
    try {
      await ServiceGroupService.addCloudResource(selectedGroupId, selectedCloudId);
      toast.success(t('service_groups_cloud_added', '클라우드 자산을 서비스 그룹에 추가했습니다.'));
      setSelectedCloudId('');
      await loadAll(selectedGroupId);
    } catch (error) {
      toast.error(`${t('service_groups_add_member_failed', '구성원 추가에 실패했습니다')}: ${error?.response?.data?.detail || error.message}`);
    } finally {
      setAddingCloud(false);
    }
  };

  const handleRemoveMember = async (memberId) => {
    if (!selectedGroupId) return;
    try {
      await ServiceGroupService.removeMember(selectedGroupId, memberId);
      toast.success(t('service_groups_member_removed', '서비스 그룹 구성원을 제거했습니다.'));
      await loadAll(selectedGroupId);
    } catch (error) {
      toast.error(`${t('service_groups_remove_member_failed', '구성원 제거에 실패했습니다')}: ${error?.response?.data?.detail || error.message}`);
    }
  };

  const availableDevices = useMemo(() => {
    const used = new Set((selectedGroup?.members || []).filter((row) => row.member_type === 'device').map((row) => Number(row.device_id)));
    return (catalog.devices || []).filter((row) => !used.has(Number(row.id)));
  }, [catalog.devices, selectedGroup]);

  const availableCloudResources = useMemo(() => {
    const used = new Set((selectedGroup?.members || []).filter((row) => row.member_type === 'cloud_resource').map((row) => Number(row.cloud_resource_id)));
    return (catalog.cloud_resources || []).filter((row) => !used.has(Number(row.id)));
  }, [catalog.cloud_resources, selectedGroup]);

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-[#f4f5f9] dark:bg-[#0e1012] h-full min-h-0 flex flex-col overflow-y-auto animate-fade-in text-gray-900 dark:text-white">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between mb-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-blue-700 dark:border-blue-900/50 dark:bg-blue-500/10 dark:text-blue-300">
            <Boxes size={14} />
            {t('service_groups_badge', 'Service Groups')}
          </div>
          <h1 className="mt-3 text-2xl font-black tracking-tight">{t('service_groups_title', '서비스 그룹')}</h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-600 dark:text-gray-300">
            {t(
              'service_groups_desc',
              '장비와 클라우드 자산을 업무 서비스 단위로 묶어 두면, 이후 서비스 영향도와 운영 보고서를 더 자연스럽게 연결할 수 있습니다.',
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => loadAll(selectedGroupId)}
            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#171a1d] px-4 py-2 text-sm font-bold text-gray-700 dark:text-gray-100"
          >
            <RefreshCw size={16} />
            {t('common_refresh', 'Refresh')}
          </button>
          <button
            onClick={handleNew}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 dark:bg-white px-4 py-2 text-sm font-bold text-white dark:text-slate-900"
          >
            <Plus size={16} />
            {t('service_groups_new', '새 서비스 그룹')}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4 mb-6">
        <MetricCard icon={Boxes} title={t('service_groups_metric_total', 'Groups')} value={summary.totalGroups} hint={t('service_groups_metric_total_hint', '업무 서비스 분류 수')} />
        <MetricCard icon={Server} title={t('service_groups_metric_devices', 'Mapped Devices')} value={summary.deviceCount} hint={t('service_groups_metric_devices_hint', '서비스에 연결된 장비 수')} />
        <MetricCard icon={Cloud} title={t('service_groups_metric_cloud', 'Mapped Cloud Resources')} value={summary.cloudCount} hint={t('service_groups_metric_cloud_hint', '서비스에 연결된 클라우드 자산 수')} />
        <MetricCard icon={Network} title={t('service_groups_metric_health', 'Average Health')} value={summary.avgHealth} hint={t('service_groups_metric_health_hint', 'Average service posture score across all groups')} />
        <MetricCard icon={RefreshCw} title={t('service_groups_metric_review', 'Needs Review')} value={summary.reviewGroups} hint={t('service_groups_metric_review_hint', 'Groups with degraded, critical, or incomplete posture')} />
      </div>

      <section className={`${PANEL_CLASS} mb-6 p-5`} data-testid="service-groups-review-queue">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">
              {t('service_groups_review_queue_label', 'Service Review Queue')}
            </div>
            <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              {t('service_groups_review_queue_desc', '검토가 필요한 서비스 그룹을 먼저 보고, 토폴로지·알림·운영 보고서로 바로 이어집니다.')}
            </div>
          </div>
          <div className="inline-flex rounded-full border border-gray-200 dark:border-gray-800 px-3 py-1 text-[11px] font-semibold text-gray-600 dark:text-gray-300">
            {t('service_groups_review_queue_count_fmt', '검토 큐 {value}').replace('{value}', String(reviewQueue.length))}
          </div>
        </div>

        {reviewQueue.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
            {t('service_groups_review_queue_empty', '지금 즉시 검토가 필요한 서비스 그룹이 없습니다. 서비스 헬스 기준선이 안정적입니다.')}
          </div>
        ) : (
          <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
            {reviewQueue.map((group) => (
              <div
                key={group.id}
                data-testid={`service-groups-review-card-${group.id}`}
                className="rounded-2xl border border-amber-200/80 bg-amber-50/50 p-4 dark:border-amber-900/40 dark:bg-amber-950/10"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-black text-gray-900 dark:text-gray-100">{group.name}</span>
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${toneForCriticality(group.criticality)}`}>
                        {group.criticality || 'standard'}
                      </span>
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${toneForHealth(group.healthStatus)}`}>
                        {t(`service_groups_health_status_${group.healthStatus}`, group.healthStatus)} {group.healthScore}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {group.owner_team || t('service_groups_owner_team_unassigned', '담당 팀 미지정')} · {group.member_count || 0} {t('service_groups_members_short', 'members')}
                    </div>
                  </div>
                  <div className="text-right text-[11px] text-gray-500 dark:text-gray-400">
                    <div>{t('service_groups_health_active_issues', 'Active issues')}: {group.activeIssueCount}</div>
                    <div>{t('service_groups_health_offline_devices', 'Offline devices')}: {group.offlineDeviceCount}</div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                  <span>{t('service_groups_health_critical_issues', 'Critical issues')}: {group.criticalIssueCount}</span>
                  <span>{t('service_groups_health_managed_devices', 'Managed devices')}: {group.managedDeviceCount}</span>
                  <span>{t('service_groups_health_discovered_only', 'Discovered only')}: {group.discoveredOnlyDeviceCount}</span>
                </div>
                <div className="mt-3 rounded-xl border border-white/70 bg-white/80 px-3 py-2 text-xs text-gray-600 dark:border-white/5 dark:bg-black/20 dark:text-gray-300">
                  {group.nextAction}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    data-testid={`service-groups-review-open-${group.id}`}
                    onClick={() => { void focusGroupReview(group.id); }}
                    className="rounded-full border border-gray-200 px-3 py-1 text-[11px] font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-white/10 dark:text-gray-200 dark:hover:bg-white/10"
                  >
                    {t('service_groups_review_open', '리뷰 열기')}
                  </button>
                  <button
                    type="button"
                    data-testid={`service-groups-review-topology-${group.id}`}
                    onClick={() => navigate(`/topology?serviceOverlay=1&serviceGroupId=${encodeURIComponent(String(group.id))}&focusGroupName=${encodeURIComponent(String(group.name || '').trim())}`)}
                    className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-semibold text-cyan-700 transition-colors hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
                  >
                    {t('service_groups_open_topology', 'Open Topology')}
                  </button>
                  <button
                    type="button"
                    data-testid={`service-groups-review-notifications-${group.id}`}
                    onClick={() => navigate(`/notifications?serviceImpact=1&openServiceImpact=1&focusGroupId=${encodeURIComponent(String(group.id))}&focusGroupName=${encodeURIComponent(String(group.name || '').trim())}`)}
                    className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[11px] font-semibold text-amber-700 transition-colors hover:bg-amber-100 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200 dark:hover:bg-amber-950/30"
                  >
                    {t('service_groups_review_open_notifications', '서비스 영향 알림 열기')}
                  </button>
                  <button
                    type="button"
                    data-testid={`service-groups-review-reports-${group.id}`}
                    onClick={() => navigate(`/operations-reports?focusGroupId=${encodeURIComponent(String(group.id))}&focusGroupName=${encodeURIComponent(String(group.name || '').trim())}`)}
                    className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-200 dark:hover:bg-emerald-950/30"
                  >
                    {t('service_groups_review_open_reports', '운영 보고서 열기')}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_420px] gap-4">
        <section className={`${PANEL_CLASS} p-4`}>
          <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">
            {t('service_groups_list_label', 'Service Group List')}
          </div>
          <div className="mt-4 space-y-2">
            {(groups || []).length === 0 ? (
              <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                {t('service_groups_empty', '아직 서비스 그룹이 없습니다.')}
              </div>
            ) : (
              groups.map((group) => {
                const active = Number(group.id) === Number(selectedGroupId);
                return (
                  <button
                    key={group.id}
                    onClick={() => handleSelectGroup(group.id)}
                    className={`w-full rounded-xl border px-4 py-3 text-left transition-colors ${
                      active
                        ? 'border-blue-500 bg-blue-50/90 dark:border-blue-500 dark:bg-blue-500/10'
                        : 'border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111315] hover:border-blue-300 dark:hover:border-blue-800'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-bold text-sm">{group.name}</div>
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${toneForCriticality(group.criticality)}`}>
                          {group.criticality || 'standard'}
                        </span>
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${toneForHealth(group?.health?.health_status)}`}>
                          {t(`service_groups_health_status_${String(group?.health?.health_status || 'healthy').toLowerCase()}`, String(group?.health?.health_status || 'healthy'))} {Number(group?.health?.health_score || 0)}
                        </span>
                      </div>
                    </div>
                    <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      {group.member_count || 0} {t('service_groups_members_short', 'members')} · {group.device_count || 0} {t('service_groups_devices_short', 'devices')} · {group.cloud_resource_count || 0} {t('service_groups_cloud_short', 'cloud')}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                      <span>{t('service_groups_health_active_issues', 'Active issues')}: {Number(group?.health?.active_issue_count || 0)}</span>
                      <span>{t('service_groups_health_offline_devices', 'Offline devices')}: {Number(group?.health?.offline_device_count || 0)}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section ref={editorRef} className={`${PANEL_CLASS} p-5`}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">
                {t('service_groups_editor_label', 'Service Group Editor')}
              </div>
              <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                {selectedGroup
                  ? t('service_groups_editor_existing', '서비스 그룹 이름, 중요도, 소유 팀을 정리하고 자산 멤버를 관리합니다.')
                  : t('service_groups_editor_new', '새 서비스 그룹을 만들어 장비와 클라우드 자산을 함께 묶습니다.')}
              </div>
            </div>
            {selectedGroup ? (
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => navigate(`/topology?serviceOverlay=1&serviceGroupId=${encodeURIComponent(String(selectedGroup.id))}`)}
                  className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-bold text-sky-700 dark:border-sky-900/40 dark:bg-sky-500/10 dark:text-sky-300"
                >
                  <Network size={16} />
                  {t('service_groups_open_topology', 'Open Topology')}
                </button>
                <button
                  onClick={handleDelete}
                  disabled={!canOperate}
                  className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-bold text-rose-700 disabled:opacity-60 dark:border-rose-900/40 dark:bg-rose-500/10 dark:text-rose-300"
                >
                  <Trash2 size={16} />
                  {t('common_remove', 'Remove')}
                </button>
              </div>
            ) : null}
          </div>

          <div className="mt-5 grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold mb-2">{t('service_groups_name_label', '이름')}</div>
              <Input value={form.name} onChange={(value) => setForm((prev) => ({ ...prev, name: value }))} placeholder={t('service_groups_name_placeholder', '민원 서비스')} />
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold mb-2">{t('service_groups_owner_team_label', '소유 팀')}</div>
              <Input value={form.owner_team} onChange={(value) => setForm((prev) => ({ ...prev, owner_team: value }))} placeholder={t('service_groups_owner_team_placeholder', 'InfraOps')} />
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold mb-2">{t('service_groups_criticality_label', '중요도')}</div>
              <Select value={form.criticality} onChange={(value) => setForm((prev) => ({ ...prev, criticality: value }))}>
                <option value="standard">{t('service_groups_criticality_standard', '표준')}</option>
                <option value="elevated">{t('service_groups_criticality_elevated', '상향')}</option>
                <option value="high">{t('service_groups_criticality_high', '높음')}</option>
              </Select>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold mb-2">{t('service_groups_color_label', '색상')}</div>
              <Input type="color" value={form.color} onChange={(value) => setForm((prev) => ({ ...prev, color: value }))} />
            </div>
          </div>

          <div className="mt-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold mb-2">{t('service_groups_description_label', '설명')}</div>
            <TextArea value={form.description} onChange={(value) => setForm((prev) => ({ ...prev, description: value }))} placeholder={t('service_groups_description_placeholder', '서비스 범위와 포함 자산의 목적을 적어두세요.')} />
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              onClick={handleSave}
              disabled={!canOperate || saving}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
            >
              <Save size={16} />
              {saving ? t('service_groups_saving', '저장 중...') : t('service_groups_save', '저장')}
            </button>
            {selectedGroup ? (
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {t('service_groups_member_summary', '현재 구성원')} {selectedGroup.member_count || 0} · {t('service_groups_devices_short', '장비')} {selectedGroup.device_count || 0} · {t('service_groups_cloud_short', '클라우드')} {selectedGroup.cloud_resource_count || 0}
              </div>
            ) : null}
          </div>

          {selectedGroup?.health ? (
            <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
              <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-[#111315] px-4 py-3">
                <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">{t('service_groups_health_score', 'Health Score')}</div>
                <div className="mt-2 flex items-center gap-2">
                  <div className="text-2xl font-black text-gray-900 dark:text-gray-100">{Number(selectedGroup.health.health_score || 0)}</div>
                  <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${toneForHealth(selectedGroup.health.health_status)}`}>
                    {t(`service_groups_health_status_${String(selectedGroup.health.health_status || 'healthy').toLowerCase()}`, String(selectedGroup.health.health_status || 'healthy'))}
                  </span>
                </div>
              </div>
              <MetricCard icon={RefreshCw} title={t('service_groups_health_active_issues', 'Active issues')} value={Number(selectedGroup.health.active_issue_count || 0)} hint={`${t('service_groups_health_critical_issues', 'Critical issues')}: ${Number(selectedGroup.health.critical_issue_count || 0)}`} />
              <MetricCard icon={Server} title={t('service_groups_health_offline_devices', 'Offline devices')} value={Number(selectedGroup.health.offline_device_count || 0)} hint={`${t('service_groups_health_managed_devices', 'Managed devices')}: ${Number(selectedGroup.health.managed_device_count || 0)}`} />
              <MetricCard icon={Boxes} title={t('service_groups_health_discovered_only', 'Discovered only')} value={Number(selectedGroup.health.discovered_only_device_count || 0)} hint={`${t('service_groups_health_member_devices', 'Mapped devices')}: ${Number(selectedGroup.health.member_device_count || 0)}`} />
              <MetricCard icon={Cloud} title={t('service_groups_health_member_cloud', 'Mapped cloud')} value={Number(selectedGroup.health.member_cloud_count || 0)} hint={`${t('service_groups_members_short', 'members')}: ${Number(selectedGroup.member_count || 0)}`} />
            </div>
          ) : null}
        </section>

        <section className={`${PANEL_CLASS} p-5`}>
          <div className="text-[11px] uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400 font-bold">
            {t('service_groups_members_label', 'Service Members')}
          </div>
          {!selectedGroup ? (
            <div className="mt-4 rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
              {t('service_groups_select_first', '먼저 서비스 그룹을 선택하거나 새로 저장하세요.')}
            </div>
          ) : (
            <>
              <div className="mt-4 space-y-4">
                <div>
                  <div className="text-xs font-bold text-gray-500 dark:text-gray-400 mb-2">{t('service_groups_add_device', '장비 추가')}</div>
                  <div className="flex gap-2">
                    <Select value={selectedDeviceId} onChange={setSelectedDeviceId}>
                      <option value="">{t('service_groups_select_device', '장비 선택')}</option>
                      {availableDevices.map((device) => (
                        <option key={device.id} value={device.id}>
                          {device.name} ({device.ip_address})
                        </option>
                      ))}
                    </Select>
                    <button
                      onClick={handleAddDevice}
                      disabled={!selectedDeviceId || addingDevice}
                      className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2 text-sm font-bold disabled:opacity-60"
                    >
                      <Plus size={16} />
                      {t('common_add', '추가')}
                    </button>
                  </div>
                </div>
                <div>
                  <div className="text-xs font-bold text-gray-500 dark:text-gray-400 mb-2">{t('service_groups_add_cloud', '클라우드 자산 추가')}</div>
                  <div className="flex gap-2">
                    <Select value={selectedCloudId} onChange={setSelectedCloudId}>
                      <option value="">{t('service_groups_select_cloud', '클라우드 자산 선택')}</option>
                      {availableCloudResources.map((resource) => (
                        <option key={resource.id} value={resource.id}>
                          [{String(resource.provider || '').toUpperCase()}] {resource.name || resource.resource_id} ({resource.resource_type})
                        </option>
                      ))}
                    </Select>
                    <button
                      onClick={handleAddCloud}
                      disabled={!selectedCloudId || addingCloud}
                      className="inline-flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2 text-sm font-bold disabled:opacity-60"
                    >
                      <Plus size={16} />
                      {t('common_add', '추가')}
                    </button>
                  </div>
                </div>
              </div>

              <div className="mt-5 space-y-2">
                {(selectedGroup.members || []).length === 0 ? (
                  <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                    {t('service_groups_no_members', '아직 연결된 자산이 없습니다.')}
                  </div>
                ) : (
                  selectedGroup.members.map((member) => (
                    <div key={member.id} className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#111315] px-4 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            {member.member_type === 'device' ? <Server size={16} className="text-blue-500" /> : <Cloud size={16} className="text-cyan-500" />}
                            <div className="font-bold text-sm text-gray-900 dark:text-gray-100">{member.display_name}</div>
                          </div>
                          {member.subtitle ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{member.subtitle}</div> : null}
                        </div>
                        <button
                          onClick={() => handleRemoveMember(member.id)}
                          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 dark:border-gray-700 px-2.5 py-1.5 text-xs font-bold text-gray-600 dark:text-gray-200"
                        >
                          <Trash2 size={14} />
                          {t('common_remove', 'Remove')}
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </section>
      </div>

      {loading ? (
        <div className="mt-6 text-sm text-gray-500 dark:text-gray-400">{t('common_loading', 'Loading...')}</div>
      ) : null}
    </div>
  );
};

export default ServiceGroupsPage;
