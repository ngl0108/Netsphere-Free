import React, { useEffect, useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, MiniMap, useEdgesState, useNodesState } from 'reactflow';
import 'reactflow/dist/style.css';
import { VisualConfigService } from '../../api/services';
import { DeviceService } from '../../api/services';
import { CheckCircle, AlertTriangle, Plus, Eye, Play, BookOpen, ClipboardCopy, Clock, RotateCcw, RefreshCw } from 'lucide-react';
import { useToast } from '../../context/ToastContext';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';
import { InlineEmpty, InlineLoading } from '../common/PageState';

const emptyGraph = { nodes: [], edges: [], viewport: null };

const defaultNodeData = (type) => {
  if (type === 'vlan') return { vlan_id: 10, name: 'Users', svi_ip: '', vrf: '', dhcp_relay: '' };
  if (type === 'interface') return { ports: 'Gi1/0/1', description: '', admin_state: 'up', mode: 'access', access_vlan: 10, native_vlan: 1, allowed_vlans: '10,20' };
  if (type === 'l2_safety') return { ports: 'Gi1/0/1', portfast: true, bpduguard: true, storm_control: '' };
  if (type === 'acl') return { name: 'WEB', entries: [{ action: 'permit', proto: 'tcp', src: 'any', dst: 'host 10.0.0.10', dport: '443' }] };
  if (type === 'ospf') return { process_id: 1, networks: [{ ip: '10.0.0.0', wildcard: '0.0.0.255', area: '0' }] };
  if (type === 'route') return { destination: '0.0.0.0', mask: '0.0.0.0', next_hop: '10.0.0.1' };
  if (type === 'global') return {
    hostname: 'Switch01', banner: '',
    snmp: { communities: [], trap_server: '' },
    ntp: { servers: [] },
    logging: { servers: [], level: 'informational' },
    aaa: { tacacs_servers: [] },
    users: []
  };
  if (type === 'target') return { target_type: 'devices', device_ids: [] };
  return {};
};

const validateGraph = (nodes, edges) => {
  const errorsById = {};

  const pushErr = (id, msg) => {
    errorsById[id] = errorsById[id] || [];
    errorsById[id].push(msg);
  };

  const byType = {};
  for (const n of nodes) {
    byType[n.type] = byType[n.type] || [];
    byType[n.type].push(n);
  }

  if (!byType.target || byType.target.length === 0) {
    errorsById.__global = [t('visual_target_required', 'Target block is required.')];
  }

  for (const n of nodes) {
    const d = n.data || {};
    if (n.type === 'vlan') {
      const vid = Number(d.vlan_id);
      if (!Number.isInteger(vid) || vid < 1 || vid > 4094) pushErr(n.id, t('visual_err_vlan_id', 'VLAN ID must be an integer between 1 and 4094.'));
      if (!String(d.name || '').trim()) pushErr(n.id, t('visual_err_vlan_name', 'VLAN name is required.'));
    }
    if (n.type === 'interface') {
      if (!String(d.ports || '').trim()) pushErr(n.id, t('visual_err_ports_required', 'Ports are required.'));
      if (!['up', 'down'].includes(String(d.admin_state || 'up'))) pushErr(n.id, t('visual_err_admin_state', 'Admin state must be up or down.'));
      if (!['access', 'trunk'].includes(String(d.mode || 'access'))) pushErr(n.id, t('visual_err_mode', 'Mode must be access or trunk.'));
      if (String(d.mode || 'access') === 'access') {
        const av = Number(d.access_vlan);
        if (!Number.isInteger(av) || av < 1 || av > 4094) pushErr(n.id, t('visual_err_access_vlan', 'Access VLAN must be an integer between 1 and 4094.'));
      }
      if (String(d.mode || 'access') === 'trunk') {
        const nv = Number(d.native_vlan);
        if (!Number.isInteger(nv) || nv < 1 || nv > 4094) pushErr(n.id, t('visual_err_native_vlan', 'Native VLAN must be an integer between 1 and 4094.'));
        if (!String(d.allowed_vlans || '').trim()) pushErr(n.id, t('visual_err_allowed_vlans', 'Allowed VLANs are required.'));
      }
    }
    if (n.type === 'l2_safety') {
      if (!String(d.ports || '').trim()) pushErr(n.id, t('visual_err_ports_required', 'Ports are required.'));
    }
    if (n.type === 'acl') {
      if (!String(d.name || '').trim()) pushErr(n.id, t('visual_err_acl_name', 'ACL name is required.'));
      if (!Array.isArray(d.entries) || d.entries.length === 0) pushErr(n.id, t('visual_err_acl_entries', 'At least one ACL entry is required.'));
    }
    if (n.type === 'target') {
      if (String(d.target_type || 'devices') !== 'devices') pushErr(n.id, t('visual_err_target_type', 'Only devices target type is supported.'));
      if (!Array.isArray(d.device_ids) || d.device_ids.length === 0) pushErr(n.id, t('visual_err_target_devices', 'Select at least one target device.'));
    }
  }

  for (const e of edges) {
    if (!e.source || !e.target) continue;
    if (e.source === e.target) {
      errorsById.__global = errorsById.__global || [];
      errorsById.__global.push(t('visual_err_self_loop', 'Self-loop edge is not allowed.'));
    }
  }

  return errorsById;
};

const NODE_COLORS = {
  vlan: { border: 'border-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/30', accent: 'text-blue-700', dot: 'bg-blue-500' },
  interface: { border: 'border-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-900/30', accent: 'text-emerald-700', dot: 'bg-emerald-500' },
  l2_safety: { border: 'border-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/30', accent: 'text-amber-700', dot: 'bg-amber-500' },
  acl: { border: 'border-red-400', bg: 'bg-red-50 dark:bg-red-900/30', accent: 'text-red-700', dot: 'bg-red-500' },
  ospf: { border: 'border-orange-400', bg: 'bg-orange-50 dark:bg-orange-900/30', accent: 'text-orange-700', dot: 'bg-orange-500' },
  route: { border: 'border-teal-400', bg: 'bg-teal-50 dark:bg-teal-900/30', accent: 'text-teal-700', dot: 'bg-teal-500' },
  global: { border: 'border-slate-400', bg: 'bg-slate-50 dark:bg-slate-800', accent: 'text-slate-700', dot: 'bg-slate-500' },
  target: { border: 'border-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/30', accent: 'text-purple-700', dot: 'bg-purple-500' },
};

const NodeCard = ({ title, subtitle, status, nodeType }) => {
  const colors = NODE_COLORS[nodeType] || NODE_COLORS.vlan;
  const borderCls = status === 'error' ? 'border-red-400' : colors.border;
  const bgCls = status === 'error' ? 'bg-red-50' : colors.bg;
  return (
    <div className={`rounded-lg border-2 ${borderCls} ${bgCls} px-3 py-2 shadow-sm min-w-[160px]`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${colors.dot}`} />
          <span className={`font-bold text-sm ${colors.accent}`}>{title}</span>
        </div>
        {status === 'error' ? <AlertTriangle size={14} className="text-red-600" /> : <CheckCircle size={14} className="text-green-600" />}
      </div>
      {subtitle ? <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">{subtitle}</div> : null}
    </div>
  );
};

const VlanNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  return <NodeCard title={`VLAN ${data?.vlan_id ?? '-'}`} subtitle={String(data?.name || '')} status={status} nodeType="vlan" />;
};

const InterfaceNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  const mode = String(data?.mode || 'access');
  const sub = mode === 'access' ? `${data?.ports || '-'} / vlan ${data?.access_vlan ?? '-'}` : `${data?.ports || '-'} / trunk`;
  return <NodeCard title={t('visual_interface', 'Interface')} subtitle={sub} status={status} nodeType="interface" />;
};

const L2SafetyNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  const sub = `${data?.ports || '-'} / PF:${data?.portfast ? 'Y' : 'N'} BG:${data?.bpduguard ? 'Y' : 'N'}`;
  return <NodeCard title={t('visual_l2_safety', 'L2 Safety')} subtitle={sub} status={status} nodeType="l2_safety" />;
};

const AclNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  const sub = `${data?.name || '-'} (${Array.isArray(data?.entries) ? data.entries.length : 0} rules)`;
  return <NodeCard title={t('visual_acl', 'ACL')} subtitle={sub} status={status} nodeType="acl" />;
};

const OspfNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  const nets = Array.isArray(data?.networks) ? data.networks.length : 0;
  return <NodeCard title={`OSPF (PID ${data?.process_id ?? '-'})`} subtitle={`${nets} ${t('visual_networks', 'network(s)')}`} status={status} nodeType="ospf" />;
};

const RouteNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  return <NodeCard title={t('visual_static_route', 'Static Route')} subtitle={`${data?.destination || '0.0.0.0'} -> ${data?.next_hop || '-'}`} status={status} nodeType="route" />;
};

const GlobalConfigNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  return <NodeCard title={t('visual_global_config', 'Global Config')} subtitle={data?.hostname || t('settings_tab_general', 'System Settings')} status={status} nodeType="global" />;
};

const TargetNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  const sub = `${Array.isArray(data?.device_ids) ? data.device_ids.length : 0} ${t('visual_selected_suffix', 'selected')}`;
  return <NodeCard title={t('visual_target', 'Target')} subtitle={sub} status={status} nodeType="target" />;
};

const TabButton = ({ active, onClick, children }) => (
  <button
    onClick={onClick}
    className={`px-3 py-2 rounded-lg text-sm font-bold border ${active
      ? 'bg-blue-600 text-white border-blue-600'
      : 'bg-white dark:bg-black/20 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/30'
      }`}
  >
    {children}
  </button>
);

export default function VisualConfigPage() {
  useLocaleRerender();
  const { toast } = useToast();
  const [blueprints, setBlueprints] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedMeta, setSelectedMeta] = useState(null);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [validation, setValidation] = useState({});
  const [devices, setDevices] = useState([]);
  const [preview, setPreview] = useState(null);
  const [deploy, setDeploy] = useState(null);
  const [rightTab, setRightTab] = useState('inspector'); // inspector|preview|deploy|guide
  const [inspectorTab, setInspectorTab] = useState('general'); // general|mgmt|security
  const [historyJobs, setHistoryJobs] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const loadBlueprints = async () => {
    const res = await VisualConfigService.getBlueprints();
    setBlueprints(res.data || []);
  };

  useEffect(() => {
    loadBlueprints().catch(() => { });
    DeviceService.getDevices().then((res) => setDevices(res.data || [])).catch(() => { });
  }, []);

  const selected = useMemo(() => blueprints.find(b => b.id === selectedId) || null, [blueprints, selectedId]);

  const loadBlueprint = async (id) => {
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.getBlueprint(id);
      setSelectedId(res.data.id);
      setSelectedMeta({ name: res.data.name, description: res.data.description, current_version: res.data.current_version });
      const g = res.data.graph || emptyGraph;
      setNodes(g.nodes || []);
      setEdges(g.edges || []);
      setSelectedNodeId(null);
      setValidation({});
      setPreview(null);
      setDeploy(null);
      setRightTab('inspector');
      setHistoryJobs([]);
      setHistoryLoading(false);
      setTimeout(() => {
        loadHistory(id).catch(() => { });
      }, 0);
    } catch (e) {
      setError(t('visual_err_load_blueprint', 'Failed to load blueprint'));
    } finally {
      setBusy(false);
    }
  };

  const createBlueprint = async () => {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.createBlueprint({
        name,
        description: newDesc.trim() || null,
        graph: { nodes, edges, viewport: null },
      });
      setNewName('');
      setNewDesc('');
      await loadBlueprints();
      await loadBlueprint(res.data.id);
    } catch (e) {
      setError(t('visual_err_create_blueprint', 'Failed to create blueprint'));
    } finally {
      setBusy(false);
    }
  };

  const saveVersion = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.createVersion(selectedId, { graph: { nodes, edges, viewport: null } });
      setSelectedMeta({ name: res.data.name, description: res.data.description, current_version: res.data.current_version });
      await loadBlueprints();
      setPreview(null);
      setDeploy(null);
      setRightTab('inspector');
    } catch (e) {
      setError(t('visual_err_save_version', 'Failed to save version'));
    } finally {
      setBusy(false);
    }
  };

  const deleteBlueprint = async () => {
    if (!selectedId) return;
    const ok = window.confirm(t('visual_confirm_delete_blueprint', 'Delete this blueprint?'));
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      await VisualConfigService.deleteBlueprint(selectedId);
      setSelectedId(null);
      setSelectedMeta(null);
      setNodes([]);
      setEdges([]);
      setPreview(null);
      setDeploy(null);
      setRightTab('inspector');
      await loadBlueprints();
    } catch (e) {
      setError(t('visual_err_delete_blueprint', 'Failed to delete blueprint'));
    } finally {
      setBusy(false);
    }
  };

  const loadHistory = async (blueprintId = selectedId) => {
    if (!blueprintId) return;
    setHistoryLoading(true);
    try {
      const res = await VisualConfigService.listDeployJobsForBlueprint(blueprintId, { limit: 50, skip: 0 });
      setHistoryJobs(res.data || []);
    } catch (e) {
      setHistoryJobs([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const nodeTypes = useMemo(() => ({
    vlan: VlanNode,
    interface: InterfaceNode,
    l2_safety: L2SafetyNode,
    acl: AclNode,
    ospf: OspfNode,
    route: RouteNode,
    global: GlobalConfigNode,
    target: TargetNode,
  }), []);

  const addNode = (type) => {
    const id = `${type}-${Date.now()}`;
    const baseX = 200 + Math.round(Math.random() * 240);
    const baseY = 120 + Math.round(Math.random() * 240);
    setNodes((nds) => nds.concat([{ id, type, position: { x: baseX, y: baseY }, data: defaultNodeData(type) }]));
    setSelectedNodeId(id);
  };

  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedNodeId) || null, [nodes, selectedNodeId]);

  const updateSelectedNodeData = (patch) => {
    if (!selectedNodeId) return;
    setNodes((nds) =>
      nds.map((n) => (n.id === selectedNodeId ? { ...n, data: { ...(n.data || {}), ...patch } } : n))
    );
  };

  const runValidate = () => {
    const errs = validateGraph(nodes, edges);
    setValidation(errs);
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...(n.data || {}), __errors: errs[n.id] || [] },
      }))
    );
    if (errs.__global && errs.__global.length) {
      toast.warning(errs.__global.join('\n'));
    }
  };

  const runPreview = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.previewBlueprint(selectedId);
      setPreview(res.data);
      setRightTab('preview');
      if (Array.isArray(res.data?.errors) && res.data.errors.length > 0) {
        toast.warning(res.data.errors.join('\n'));
      }
      if (res.data?.errors_by_node_id) {
        const errs = res.data.errors_by_node_id;
        setValidation((prev) => ({ ...prev, ...errs }));
        setNodes((nds) =>
          nds.map((n) => ({
            ...n,
            data: { ...(n.data || {}), __errors: errs[n.id] || [] },
          }))
        );
      }
    } catch (e) {
      setError(t('visual_err_preview', 'Failed to preview'));
      setPreview(null);
      toast.error(t('visual_err_preview', 'Failed to preview'));
    } finally {
      setBusy(false);
    }
  };

  const runDeploy = async () => {
    if (!selectedId) return;
    const ok = window.confirm(t('visual_confirm_deploy', 'Deploy this blueprint to selected devices?'));
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.deployBlueprint(selectedId, { save_backup: true });
      setDeploy({ job_id: res.data.job_id, status: res.data.status, results: res.data.results || [], details: null });
      setRightTab('deploy');
      try {
        const det = await VisualConfigService.getDeployJob(res.data.job_id);
        setDeploy(prev => ({ ...(prev || {}), details: det.data }));
      } catch (e) {
        // ignore
      }
      loadHistory(selectedId).catch(() => { });
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail && typeof detail === 'object' && (detail.errors || detail.errors_by_node_id)) {
        if (Array.isArray(detail.errors) && detail.errors.length) toast.error(detail.errors.join('\n'));
        if (detail.errors_by_node_id) {
          const errs = detail.errors_by_node_id;
          setValidation((prev) => ({ ...prev, ...errs }));
          setNodes((nds) =>
            nds.map((n) => ({
              ...n,
              data: { ...(n.data || {}), __errors: errs[n.id] || [] },
            }))
          );
        }
      } else {
        setError(t('visual_err_deploy', 'Failed to deploy'));
        toast.error(t('visual_err_deploy', 'Failed to deploy'));
      }
      setDeploy(null);
    } finally {
      setBusy(false);
    }
  };

  const renderInspector = () => {
    if (!selectedNode) {
      return <div className="text-sm text-gray-500">{t('visual_select_node', 'Select a node to edit.')}</div>;
    }
    const nodeType = selectedNode.type;
    const d = selectedNode.data || {};
    const errs = Array.isArray(d.__errors) ? d.__errors : [];

    const header = (
      <div className="mb-3">
        <div className="font-bold text-lg">{nodeType}</div>
        <div className="text-xs text-gray-500">id: {selectedNode.id}</div>
        {errs.length > 0 ? (
          <div className="mt-2 space-y-1">
            {errs.map((e, idx) => (
              <div key={`${idx}-${e}`} className="text-xs text-red-600 flex items-center gap-1">
                <AlertTriangle size={12} /> {e}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    );

    const input = (label, value, onChange, opts = {}) => (
      <div className="space-y-1">
        <div className="text-xs font-bold text-gray-700 dark:text-gray-200">{label}</div>
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20"
          {...opts}
        />
      </div>
    );

    const select = (label, value, onChange, items) => (
      <div className="space-y-1">
        <div className="text-xs font-bold text-gray-700 dark:text-gray-200">{label}</div>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20"
        >
          {items.map((it) => (
            <option key={it.value} value={it.value}>{it.label}</option>
          ))}
        </select>
      </div>
    );

    const checkbox = (label, checked, onChange) => (
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
        <span>{label}</span>
      </label>
    );

    if (nodeType === 'vlan') {
      return (
        <div className="space-y-3">
          {header}
          {input(t('visual_label_vlan_id', 'VLAN ID'), String(d.vlan_id ?? ''), (v) => updateSelectedNodeData({ vlan_id: Number(v) }), { inputMode: 'numeric' })}
          {input(t('visual_label_name', 'Name'), String(d.name ?? ''), (v) => updateSelectedNodeData({ name: v }))}
          {input(t('visual_label_svi_ip_optional', 'SVI IP (optional)'), String(d.svi_ip ?? ''), (v) => updateSelectedNodeData({ svi_ip: v }))}
          {input(t('visual_label_vrf_optional', 'VRF (optional)'), String(d.vrf ?? ''), (v) => updateSelectedNodeData({ vrf: v }))}
          {input(t('visual_label_dhcp_relay_optional', 'DHCP Relay (optional)'), String(d.dhcp_relay ?? ''), (v) => updateSelectedNodeData({ dhcp_relay: v }))}
        </div>
      );
    }

    if (nodeType === 'interface') {
      return (
        <div className="space-y-3">
          {header}
          {input(t('visual_label_ports', 'Ports'), String(d.ports ?? ''), (v) => updateSelectedNodeData({ ports: v }))}
          {input(t('visual_label_description', 'Description'), String(d.description ?? ''), (v) => updateSelectedNodeData({ description: v }))}
          {select(t('visual_label_admin_state', 'Admin State'), String(d.admin_state || 'up'), (v) => updateSelectedNodeData({ admin_state: v }), [
            { value: 'up', label: 'up' },
            { value: 'down', label: 'down' },
          ])}
          {select(t('visual_label_mode', 'Mode'), String(d.mode || 'access'), (v) => updateSelectedNodeData({ mode: v }), [
            { value: 'access', label: 'access' },
            { value: 'trunk', label: 'trunk' },
          ])}
          {String(d.mode || 'access') === 'access' ? (
            input(t('visual_label_access_vlan', 'Access VLAN'), String(d.access_vlan ?? ''), (v) => updateSelectedNodeData({ access_vlan: Number(v) }), { inputMode: 'numeric' })
          ) : (
            <div className="space-y-3">
              {input(t('visual_label_native_vlan', 'Native VLAN'), String(d.native_vlan ?? ''), (v) => updateSelectedNodeData({ native_vlan: Number(v) }), { inputMode: 'numeric' })}
              {input(t('visual_label_allowed_vlans', 'Allowed VLANs'), String(d.allowed_vlans ?? ''), (v) => updateSelectedNodeData({ allowed_vlans: v }))}
            </div>
          )}
        </div>
      );
    }

    if (nodeType === 'l2_safety') {
      return (
        <div className="space-y-3">
          {header}
          {input(t('visual_label_ports', 'Ports'), String(d.ports ?? ''), (v) => updateSelectedNodeData({ ports: v }))}
          <div className="space-y-2">
            {checkbox('portfast', d.portfast, (v) => updateSelectedNodeData({ portfast: v }))}
            {checkbox('bpduguard', d.bpduguard, (v) => updateSelectedNodeData({ bpduguard: v }))}
          </div>
          {input(t('visual_label_storm_control_optional', 'storm-control (optional)'), String(d.storm_control ?? ''), (v) => updateSelectedNodeData({ storm_control: v }))}
        </div>
      );
    }

    if (nodeType === 'acl') {
      const entries = Array.isArray(d.entries) ? d.entries : [];
      const first = entries[0] || { action: 'permit', proto: 'tcp', src: 'any', dst: 'any', dport: '' };
      return (
        <div className="space-y-3">
          {header}
          {input(t('visual_label_name', 'Name'), String(d.name ?? ''), (v) => updateSelectedNodeData({ name: v }))}
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3 space-y-2">
            <div className="text-xs font-bold text-gray-700 dark:text-gray-200">{t('visual_acl_first_entry', 'First Entry (MVP)')}</div>
            {select(t('visual_label_action', 'Action'), String(first.action || 'permit'), (v) => updateSelectedNodeData({ entries: [{ ...first, action: v }] }), [
              { value: 'permit', label: 'permit' },
              { value: 'deny', label: 'deny' },
            ])}
            {input(t('visual_label_protocol', 'Proto'), String(first.proto || 'tcp'), (v) => updateSelectedNodeData({ entries: [{ ...first, proto: v }] }))}
            {input(t('visual_label_source', 'Src'), String(first.src || 'any'), (v) => updateSelectedNodeData({ entries: [{ ...first, src: v }] }))}
            {input(t('visual_label_destination_short', 'Dst'), String(first.dst || 'any'), (v) => updateSelectedNodeData({ entries: [{ ...first, dst: v }] }))}
            {input(t('visual_label_dest_port', 'Dst Port'), String(first.dport || ''), (v) => updateSelectedNodeData({ entries: [{ ...first, dport: v }] }))}
          </div>
        </div>
      );
    }

    if (nodeType === 'ospf') {
      const nets = Array.isArray(d.networks) ? d.networks : [];
      const first = nets[0] || { ip: '10.0.0.0', wildcard: '0.0.0.255', area: '0' };
      return (
        <div className="space-y-3">
          {header}
          {input(t('visual_label_process_id', 'Process ID'), String(d.process_id ?? ''), (v) => updateSelectedNodeData({ process_id: Number(v) }), { inputMode: 'numeric' })}
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3 space-y-2">
            <div className="text-xs font-bold text-gray-700 dark:text-gray-200">{t('visual_ospf_network_first', 'Network (first)')}</div>
            {input(t('visual_label_network_ip', 'Network IP'), String(first.ip || ''), (v) => updateSelectedNodeData({ networks: [{ ...first, ip: v }] }))}
            {input(t('visual_label_wildcard', 'Wildcard'), String(first.wildcard || ''), (v) => updateSelectedNodeData({ networks: [{ ...first, wildcard: v }] }))}
            {input(t('visual_label_area', 'Area'), String(first.area || ''), (v) => updateSelectedNodeData({ networks: [{ ...first, area: v }] }))}
          </div>
        </div>
      );
    }

    if (nodeType === 'route') {
      return (
        <div className="space-y-3">
          {header}
          {input(t('visual_label_destination', 'Destination'), String(d.destination ?? ''), (v) => updateSelectedNodeData({ destination: v }))}
          {input(t('visual_label_mask', 'Mask'), String(d.mask ?? ''), (v) => updateSelectedNodeData({ mask: v }))}
          {input(t('visual_label_next_hop', 'Next Hop'), String(d.next_hop ?? ''), (v) => updateSelectedNodeData({ next_hop: v }))}
        </div>
      );
    }

    if (nodeType === 'global') {
      const snmp = d.snmp || { communities: [], trap_server: '' };
      const ntp = d.ntp || { servers: [] };
      const logging = d.logging || { servers: [], level: 'informational' };
      const aaa = d.aaa || { tacacs_servers: [] };
      const users = d.users || []; // array of { username, privilege, secret }

      // Helper to update deeply nested
      const updateSnmp = (patch) => updateSelectedNodeData({ snmp: { ...snmp, ...patch } });
      const updateNtp = (patch) => updateSelectedNodeData({ ntp: { ...ntp, ...patch } });
      const updateLogging = (patch) => updateSelectedNodeData({ logging: { ...logging, ...patch } });
      const updateAaa = (patch) => updateSelectedNodeData({ aaa: { ...aaa, ...patch } });

      return (
        <div className="space-y-3">
          {header}
          <div className="flex border-b border-gray-200 dark:border-gray-800 mb-3">
            <button onClick={() => setInspectorTab('general')} className={`flex-1 py-1 text-xs font-bold border-b-2 ${inspectorTab === 'general' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500'}`}>{t('visual_tab_general', 'General')}</button>
            <button onClick={() => setInspectorTab('mgmt')} className={`flex-1 py-1 text-xs font-bold border-b-2 ${inspectorTab === 'mgmt' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500'}`}>{t('visual_tab_mgmt', 'Mgmt')}</button>
            <button onClick={() => setInspectorTab('security')} className={`flex-1 py-1 text-xs font-bold border-b-2 ${inspectorTab === 'security' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500'}`}>{t('visual_tab_security', 'Security')}</button>
          </div>

          {inspectorTab === 'general' && (
            <div className="space-y-3">
              {input(t('visual_label_hostname', 'Hostname'), String(d.hostname || ''), (v) => updateSelectedNodeData({ hostname: v }))}
              {input(t('visual_label_domain_name', 'Domain Name'), String(d.domain_name || ''), (v) => updateSelectedNodeData({ domain_name: v }))}
              <div className="space-y-1">
                <div className="text-xs font-bold text-gray-700 dark:text-gray-200">{t('visual_label_banner', 'Banner (MOTD/Login)')}</div>
                <textarea
                  value={d.banner || ''}
                  onChange={(e) => updateSelectedNodeData({ banner: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 text-xs h-20"
                />
              </div>
            </div>
          )}

          {inspectorTab === 'mgmt' && (
            <div className="space-y-4">
              <div className="space-y-2">
                <div className="text-xs font-bold text-blue-600">{t('visual_section_snmp', 'SNMP')}</div>
                {/* Simple 1 RO/RW for MVP */}
                {input(t('visual_label_community_ro', 'Community (RO)'), String(snmp.communities.find(c => c.mode === 'ro')?.name || ''), (v) => {
                  const others = snmp.communities.filter(c => c.mode !== 'ro');
                  updateSnmp({ communities: v ? [...others, { name: v, mode: 'ro' }] : others });
                })}
                {input(t('visual_label_community_rw', 'Community (RW)'), String(snmp.communities.find(c => c.mode === 'rw')?.name || ''), (v) => {
                  const others = snmp.communities.filter(c => c.mode !== 'rw');
                  updateSnmp({ communities: v ? [...others, { name: v, mode: 'rw' }] : others });
                })}
                {input(t('visual_label_trap_server', 'Trap Server'), String(snmp.trap_server || ''), (v) => updateSnmp({ trap_server: v }))}
              </div>
              <div className="space-y-2">
                <div className="text-xs font-bold text-blue-600">{t('visual_section_ntp', 'NTP')}</div>
                {input(t('visual_label_ntp_server_primary', 'NTP Server (Primary)'), String(ntp.servers[0] || ''), (v) => updateNtp({ servers: v ? [v] : [] }))}
              </div>
              <div className="space-y-2">
                <div className="text-xs font-bold text-blue-600">{t('visual_section_syslog', 'Syslog')}</div>
                {input(t('visual_label_syslog_server', 'Syslog Server'), String(logging.servers[0] || ''), (v) => updateLogging({ servers: v ? [v] : [] }))}
              </div>
            </div>
          )}

          {inspectorTab === 'security' && (
            <div className="space-y-4">
              <div className="space-y-2">
                <div className="text-xs font-bold text-red-600">{t('visual_section_tacacs', 'TACACS+ (AAA)')}</div>
                {/* Single Server MVP */}
                {input(t('visual_label_server_ip', 'Server IP'), String(aaa.tacacs_servers[0]?.ip || ''), (v) => {
                  const old = aaa.tacacs_servers[0] || { name: 'TACACS1', key: '' };
                  updateAaa({ tacacs_servers: v ? [{ ...old, ip: v }] : [] });
                })}
                {aaa.tacacs_servers[0]?.ip && input(t('visual_label_key', 'Key'), String(aaa.tacacs_servers[0]?.key || ''), (v) => {
                  const old = aaa.tacacs_servers[0];
                  updateAaa({ tacacs_servers: [{ ...old, key: v }] });
                }, { type: 'password' })}
              </div>
              <div className="space-y-2">
                <div className="text-xs font-bold text-red-600">{t('visual_section_local_users', 'Local Users')}</div>
                {/* Single User MVP */}
                {input(t('visual_label_username', 'Username'), String(users[0]?.username || ''), (v) => {
                  const old = users[0] || { privilege: 15, secret: '' };
                  updateSelectedNodeData({ users: v ? [{ ...old, username: v }] : [] });
                })}
                {users[0]?.username && input(t('visual_label_secret', 'Secret'), String(users[0]?.secret || ''), (v) => {
                  const old = users[0];
                  updateSelectedNodeData({ users: [{ ...old, secret: v }] });
                }, { type: 'password' })}
              </div>
            </div>
          )}
        </div>
      );
    }

    if (nodeType === 'target') {
      const ids = Array.isArray(d.device_ids) ? d.device_ids : [];
      const toggleDevice = (id) => {
        const next = ids.includes(id) ? ids.filter((x) => x !== id) : ids.concat([id]);
        updateSelectedNodeData({ device_ids: next });
      };
      return (
        <div className="space-y-3">
          {header}
          <div className="text-xs text-gray-500">{t('visual_select_target_devices', 'Select target devices')}</div>
          <div className="max-h-[420px] overflow-y-auto space-y-2">
            {devices.length === 0 ? (
              <InlineEmpty label={t('visual_no_devices', 'No devices available.')} />
            ) : devices.map((dev) => (
              <label key={dev.id} className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20">
                <div className="text-sm">
                  <div className="font-bold">{dev.name || dev.hostname || `Device ${dev.id}`}</div>
                  <div className="text-xs text-gray-500 font-mono">{dev.ip_address} ({dev.device_type || 'unknown'})</div>
                </div>
                <input type="checkbox" checked={ids.includes(dev.id)} onChange={() => toggleDevice(dev.id)} />
              </label>
            ))}
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {header}
        <div className="text-sm text-gray-500">{t('visual_unsupported_node', 'Unsupported node type.')}</div>
      </div>
    );
  };

  const copyText = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t('common_copy_success', 'Copied to clipboard.'));
    } catch (e) {
      toast.error(t('common_copy_failed', 'Copy failed.'));
    }
  };

  const renderPreviewPanel = () => {
    if (!preview) return <div className="text-sm text-gray-500">{t('visual_preview_hint', 'Run Preview to view per-device CLI output.')}</div>;
    if (!Array.isArray(preview?.devices) || preview.devices.length === 0) return <InlineEmpty label={t('visual_preview_empty', 'No target devices or preview errors exist.')} />;
    return (
      <div className="space-y-3">
        {preview.devices.map((d) => {
          const text = (d.commands || []).join('\n');
          return (
            <div key={d.device_id} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 overflow-hidden">
              <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between gap-2">
                <div>
                  <div className="font-bold text-sm">{d.name || `Device ${d.device_id}`}</div>
                  <div className="text-xs text-gray-500 font-mono">{d.ip_address} / {d.device_type}</div>
                </div>
                <button
                  onClick={() => copyText(text)}
                  className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/30 text-xs font-bold flex items-center gap-2"
                >
                  <ClipboardCopy size={14} /> {t('setup_copy_button', 'Copy')}
                </button>
              </div>
              <pre className="p-3 text-xs overflow-x-auto whitespace-pre-wrap bg-gray-50 dark:bg-black/30">{text}</pre>
            </div>
          );
        })}
      </div>
    );
  };

  const renderDeployPanel = () => {
    if (!deploy) return <div className="text-sm text-gray-500">{t('visual_deploy_hint', 'Run Deploy to see execution results.')}</div>;
    const det = deploy.details?.job;
    const summary = det?.summary || null;
    return (
      <div className="space-y-3">
        <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3">
          <div className="text-sm">
            <span className="font-bold">{t('visual_job', 'Job')}</span> #{deploy.job_id} / <span className="font-mono">{deploy.status}</span>
          </div>
          {summary ? (
            <div className="text-xs text-gray-600 dark:text-gray-400 mt-2">
              {t('visual_total', 'total')}: <span className="font-mono">{summary.total}</span> / {t('visual_success', 'success')}: <span className="font-mono">{summary.success}</span> / {t('visual_failed', 'failed')}: <span className="font-mono">{summary.failed}</span>
            </div>
          ) : null}
        </div>

        <div className="space-y-2">
          {(deploy.results || []).map((r) => (
            <div key={r.device_id} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-bold">{r.name || `Device ${r.device_id}`}</div>
                {r.success ? <CheckCircle size={16} className="text-green-600" /> : <AlertTriangle size={16} className="text-red-600" />}
              </div>
              <div className="text-xs text-gray-500 font-mono mt-1">{r.ip_address || '-'}</div>
              {!r.success && r.error ? <div className="text-xs text-red-600 mt-2">{r.error}</div> : null}
            </div>
          ))}
        </div>

        {deploy.details?.results?.length ? (
          <div className="space-y-2">
            <div className="font-bold text-sm">{t('visual_detailed_logs', 'Detailed Logs')}</div>
            {deploy.details.results.map((r) => (
              <details key={`log-${r.device_id}`} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 overflow-hidden">
                <summary className="px-3 py-2 cursor-pointer text-sm font-bold">
                  {t('devices_col_device', 'Device')} {r.device_id} {r.success ? t('visual_success_upper', 'SUCCESS') : t('visual_failed_upper', 'FAILED')}
                </summary>
                <div className="p-3 space-y-3">
                  {r.error ? <div className="text-xs text-red-600">{r.error}</div> : null}
                  <div>
                    <div className="text-xs font-bold mb-1">{t('visual_rendered_config', 'Rendered Config')}</div>
                    <pre className="text-xs whitespace-pre-wrap overflow-x-auto bg-gray-50 dark:bg-black/30 p-3 rounded-lg">{r.rendered_config || ''}</pre>
                  </div>
                  <div>
                    <div className="text-xs font-bold mb-1">{t('visual_output', 'Output')}</div>
                    <pre className="text-xs whitespace-pre-wrap overflow-x-auto bg-gray-50 dark:bg-black/30 p-3 rounded-lg">{r.output_log || ''}</pre>
                  </div>
                </div>
              </details>
            ))}
          </div>
        ) : null}
      </div>
    );
  };

  const renderGuidePanel = () => (
    <div className="space-y-3 text-sm">
      <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3">
        <div className="font-bold mb-2">{t('visual_how_to_use', 'How to Use')}</div>
        <ol className="list-decimal pl-5 space-y-1 text-gray-700 dark:text-gray-200">
          <li>{t('visual_guide_step_1', 'Create or select a blueprint')}</li>
          <li>{t('visual_guide_step_2', 'Add a Target block from Blocks and select devices')}</li>
          <li>{t('visual_guide_step_3', 'Add VLAN/Interface/L2 Safety/ACL blocks and configure values in Inspector')}</li>
          <li>{t('visual_guide_step_4', 'Run Validate to check required fields and format errors')}</li>
          <li>{t('visual_guide_step_5', 'Run Preview to inspect per-device CLI')}</li>
          <li>{t('visual_guide_step_6', 'Run Deploy and verify results/logs')}</li>
        </ol>
      </div>
      <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3">
        <div className="font-bold mb-2">{t('visual_tips', 'Tips')}</div>
        <div className="space-y-1 text-gray-700 dark:text-gray-200">
          <div>- {t('visual_tip_1', 'Click a node to edit settings in Inspector.')}</div>
          <div>- {t('visual_tip_2', 'Target is mandatory (Preview/Deploy fail without devices).')}</div>
          <div>- {t('visual_tip_3', 'Preview checks rendered output before applying changes.')}</div>
          <div>- {t('visual_tip_4', 'Deploy pushes via SSH and saves running-config backup by default.')}</div>
        </div>
      </div>
    </div>
  );

  const fmtTs = (ts) => {
    if (!ts) return '-';
    try {
      const d = new Date(ts);
      if (Number.isNaN(d.getTime())) return String(ts);
      return d.toLocaleString();
    } catch {
      return String(ts);
    }
  };

  const loadJobToDeployPanel = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const det = await VisualConfigService.getDeployJob(jobId);
      const job = det.data?.job;
      const results = (det.data?.results || []).map((r) => ({
        device_id: r.device_id,
        name: null,
        ip_address: null,
        success: !!r.success,
        error: r.error || null,
      }));
      setDeploy({ job_id: jobId, status: job?.status || 'unknown', results, details: det.data });
      setRightTab('deploy');
    } catch (e) {
      setError(t('visual_err_load_job', 'Failed to load job'));
    } finally {
      setBusy(false);
    }
  };

  const rollbackJob = async (jobId) => {
    const ok = window.confirm(t('visual_confirm_rollback', 'Rollback this job? (best-effort)'));
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.rollbackDeployJob(jobId, { save_backup: true });
      setDeploy({ job_id: res.data.job_id, status: res.data.status, results: res.data.results || [], details: null });
      setRightTab('deploy');
      try {
        const det = await VisualConfigService.getDeployJob(res.data.job_id);
        setDeploy(prev => ({ ...(prev || {}), details: det.data }));
      } catch (e) {
        // ignore
      }
      loadHistory(selectedId).catch(() => { });
    } catch (e) {
      setError(t('visual_err_rollback', 'Failed to rollback'));
    } finally {
      setBusy(false);
    }
  };

  const renderHistoryPanel = () => {
    if (!selectedId) return <div className="text-sm text-gray-500">{t('visual_select_blueprint_first', 'Select a blueprint first.')}</div>;
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-bold flex items-center gap-2"><Clock size={16} /> {t('visual_recent_jobs', 'Recent Jobs')}</div>
          <button
            disabled={historyLoading}
            onClick={() => loadHistory(selectedId)}
            className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/30 text-xs font-bold flex items-center gap-2 disabled:opacity-60"
          >
            <RefreshCw size={14} /> {t('common_refresh', 'Refresh')}
          </button>
        </div>

        {historyLoading ? (
          <InlineLoading label={t('common_loading', 'Loading...')} />
        ) : historyJobs.length === 0 ? (
          <InlineEmpty label={t('visual_no_jobs', 'No jobs yet.')} />
        ) : (
          <div className="space-y-2">
            {historyJobs.map((j) => {
              const type = j?.summary?.type || 'deploy';
              const badge = type === 'rollback' ? 'bg-purple-100 text-purple-700 border-purple-200' : 'bg-blue-100 text-blue-700 border-blue-200';
              const statusBadge = j.status === 'success'
                ? 'bg-green-100 text-green-700 border-green-200'
                : j.status === 'failed'
                  ? 'bg-red-100 text-red-700 border-red-200'
                  : 'bg-gray-100 text-gray-700 border-gray-200';
              return (
                <div key={j.id} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-bold text-sm">#{j.id}</div>
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold border ${badge}`}>{type}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold border ${statusBadge}`}>{j.status}</span>
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">{fmtTs(j.created_at)}{j.finished_at ? ` / ${fmtTs(j.finished_at)}` : ''}</div>
                  {j.summary && typeof j.summary === 'object' && j.summary.total != null ? (
                    <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                      {t('visual_total', 'total')}: <span className="font-mono">{j.summary.total}</span> / {t('visual_success', 'success')}: <span className="font-mono">{j.summary.success}</span> / {t('visual_failed', 'failed')}: <span className="font-mono">{j.summary.failed}</span>
                    </div>
                  ) : null}
                  <div className="flex gap-2 mt-3">
                    <button
                      disabled={busy}
                      onClick={() => loadJobToDeployPanel(j.id)}
                      className="flex-1 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/30 text-sm font-bold"
                    >
                      {t('common_open', 'Open')}
                    </button>
                    {type === 'deploy' ? (
                      <button
                        disabled={busy}
                        onClick={() => rollbackJob(j.id)}
                        className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-60 text-white text-sm font-bold flex items-center gap-2"
                      >
                        <RotateCcw size={16} /> {t('visual_rollback', 'Rollback')}
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full min-h-0 flex flex-col lg:flex-row">
      <div className="w-full lg:w-80 border-b lg:border-b-0 lg:border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-[#151719] p-4 overflow-y-auto max-h-[45dvh] lg:max-h-none">
        <div className="text-lg font-bold mb-1">{t('hub_item_visual_title', 'Visual Config')}</div>
        <div className="text-xs text-gray-500 mb-4">{t('visual_flow_hint', 'Assemble blocks -> Preview -> Deploy')}</div>
        <div className="space-y-2 mb-4">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t('visual_new_blueprint_name', 'New blueprint name')}
            className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20"
          />
          <input
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder={t('visual_description_optional', 'Description (optional)')}
            className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20"
          />
          <button
            disabled={busy || !newName.trim()}
            onClick={createBlueprint}
            className="w-full px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white font-bold"
          >
            {t('common_create', 'Create')}
          </button>
        </div>

        <div className="flex items-center justify-between mb-2">
          <div className="font-bold">{t('visual_blueprints', 'Blueprints')}</div>
          <button onClick={() => loadBlueprints()} className="text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200">
            {t('common_refresh', 'Refresh')}
          </button>
        </div>

        <div className="space-y-2">
          {blueprints.length === 0 ? (
            <InlineEmpty label={t('visual_no_blueprints', 'No blueprints yet.')} />
          ) : (
            blueprints.map((b) => (
              <button
                key={b.id}
                onClick={() => loadBlueprint(b.id)}
                className={`w-full text-left px-3 py-2 rounded-lg border ${selectedId === b.id
                  ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/20'
                  }`}
              >
                <div className="font-bold">{b.name}</div>
                <div className="text-xs text-gray-500">v{b.current_version}</div>
              </button>
            ))
          )}
        </div>

        {selected && (
          <div className="mt-6 space-y-2">
            <div className="font-bold">{t('visual_selected', 'Selected')}</div>
            <div className="text-sm">{selectedMeta?.name || selected.name}</div>
            <div className="text-xs text-gray-500">{t('visual_current_version', 'Current version')}: v{selectedMeta?.current_version || selected.current_version}</div>
            <div className="flex gap-2">
              <button
                disabled={busy}
                onClick={saveVersion}
                className="flex-1 px-3 py-2 rounded-lg bg-green-600 hover:bg-green-500 disabled:opacity-60 text-white font-bold"
              >
                {t('common_save', 'Save')}
              </button>
              <button
                disabled={busy}
                onClick={deleteBlueprint}
                className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/20 text-sm font-bold"
              >
                {t('common_delete', 'Delete')}
              </button>
            </div>
          </div>
        )}

        <div className="mt-6">
          <div className="font-bold mb-2">{t('visual_block_palette', 'Block Palette')}</div>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => addNode('target')} className="px-3 py-2 rounded-lg border-2 border-purple-300 bg-purple-50 dark:bg-purple-900/20 hover:bg-purple-100 dark:hover:bg-purple-900/30 text-sm font-bold flex items-center gap-2 col-span-2 text-purple-700">
              <Plus size={16} /> {t('visual_target', 'Target')}
            </button>
            <button onClick={() => addNode('vlan')} className="px-3 py-2 rounded-lg border-2 border-blue-300 bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 text-sm font-bold flex items-center gap-2 text-blue-700">
              <Plus size={16} /> VLAN
            </button>
            <button onClick={() => addNode('interface')} className="px-3 py-2 rounded-lg border-2 border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20 hover:bg-emerald-100 text-sm font-bold flex items-center gap-2 text-emerald-700">
              <Plus size={16} /> Interface
            </button>
            <button onClick={() => addNode('l2_safety')} className="px-3 py-2 rounded-lg border-2 border-amber-300 bg-amber-50 dark:bg-amber-900/20 hover:bg-amber-100 text-sm font-bold flex items-center gap-2 text-amber-700">
              <Plus size={16} /> L2 Safety
            </button>
            <button onClick={() => addNode('global')} className="px-3 py-2 rounded-lg border-2 border-slate-300 bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 text-sm font-bold flex items-center gap-2 text-slate-700">
              <Plus size={16} /> Global Config
            </button>
            <button onClick={() => addNode('acl')} className="px-3 py-2 rounded-lg border-2 border-red-300 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 text-sm font-bold flex items-center gap-2 text-red-700">
              <Plus size={16} /> ACL
            </button>
            <button onClick={() => addNode('ospf')} className="px-3 py-2 rounded-lg border-2 border-orange-300 bg-orange-50 dark:bg-orange-900/20 hover:bg-orange-100 text-sm font-bold flex items-center gap-2 text-orange-700">
              <Plus size={16} /> OSPF
            </button>
            <button onClick={() => addNode('route')} className="px-3 py-2 rounded-lg border-2 border-teal-300 bg-teal-50 dark:bg-teal-900/20 hover:bg-teal-100 text-sm font-bold flex items-center gap-2 text-teal-700">
              <Plus size={16} /> Route
            </button>
          </div>
        </div>

        <div className="mt-6">
          <div className="font-bold mb-2">{t('devices_col_actions', 'Actions')}</div>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={runValidate} className="px-3 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-bold text-sm">
              {t('visual_validate', 'Validate')}
            </button>
            <button disabled={!selectedId || busy} onClick={runPreview} className="px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white font-bold text-sm flex items-center justify-center gap-2">
              <Eye size={16} /> {t('visual_preview', 'Preview')}
            </button>
            <button disabled={!selectedId || busy} onClick={runDeploy} className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-60 text-white font-bold text-sm flex items-center justify-center gap-2 col-span-2">
              <Play size={16} /> {t('visual_deploy', 'Deploy')}
            </button>
          </div>
        </div>

        {validation?.__global?.length ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3">
            <div className="font-bold text-sm text-red-700 mb-2">{t('visual_validation', 'Validation')}</div>
            <div className="text-xs text-red-700 space-y-1">
              {validation.__global.map((m, idx) => (
                <div key={`${idx}-${m}`} className="flex items-center gap-1">
                  <AlertTriangle size={12} /> {m}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {error && <div className="mt-4 text-sm text-red-600">{error}</div>}
      </div>

      <div className="flex-1 min-h-0 bg-gray-50 dark:bg-[#0f1112] flex flex-col lg:flex-row">
        <div className="flex-1 min-h-[45dvh] lg:min-h-0">
          <div className="h-full">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              nodeTypes={nodeTypes}
              onNodeClick={(_, n) => setSelectedNodeId(n.id)}
              onPaneClick={() => setSelectedNodeId(null)}
              onConnect={(params) => setEdges((eds) => [...eds, { ...params, id: `${params.source}-${params.target}-${Date.now()}` }])}
              fitView
            >
              <Background />
              <MiniMap />
              <Controls />
            </ReactFlow>
          </div>
        </div>

        <div className="w-full lg:w-[380px] border-t lg:border-t-0 lg:border-l border-gray-200 dark:border-gray-800 bg-white dark:bg-[#151719] p-4 overflow-y-auto max-h-[45dvh] lg:max-h-none">
          <div className="flex items-center justify-between gap-2 mb-3">
            <div className="text-lg font-bold">{t('visual_details', 'Details')}</div>
            <button
              onClick={() => setRightTab('guide')}
              className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/30 text-sm font-bold flex items-center gap-2"
            >
              <BookOpen size={16} /> {t('visual_guide', 'Guide')}
            </button>
          </div>

          <div className="flex flex-wrap gap-2 mb-4">
            <TabButton active={rightTab === 'inspector'} onClick={() => setRightTab('inspector')}>{t('visual_inspector', 'Inspector')}</TabButton>
            <TabButton active={rightTab === 'preview'} onClick={() => setRightTab('preview')}>{t('visual_preview', 'Preview')}</TabButton>
            <TabButton active={rightTab === 'deploy'} onClick={() => setRightTab('deploy')}>{t('visual_deploy', 'Deploy')}</TabButton>
            <TabButton active={rightTab === 'history'} onClick={() => setRightTab('history')}>{t('visual_history', 'History')}</TabButton>
            <TabButton active={rightTab === 'guide'} onClick={() => setRightTab('guide')}>{t('visual_guide', 'Guide')}</TabButton>
          </div>

          {rightTab === 'inspector' ? renderInspector() : null}
          {rightTab === 'preview' ? renderPreviewPanel() : null}
          {rightTab === 'deploy' ? renderDeployPanel() : null}
          {rightTab === 'history' ? renderHistoryPanel() : null}
          {rightTab === 'guide' ? renderGuidePanel() : null}
        </div>
      </div>
    </div>
  );
}

