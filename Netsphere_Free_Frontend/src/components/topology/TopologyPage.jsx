import React, { useCallback, useEffect, useState, useRef, useMemo, Suspense, lazy } from 'react';
import ReactFlow, {
  useNodesState,
  useEdgesState,
  applyNodeChanges,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  Panel,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useLocation, useNavigate } from 'react-router-dom';
import { DeviceService, DiscoveryService, SDNService, ServiceGroupService, TopologyService, TrafficService } from '../../api/services';
import { useAuth } from '../../context/AuthContext';
import { getElkLayoutedElements } from '../../utils/elkLayout';
import { buildGrafanaFleetHealthUrl, buildObservabilityPath } from '../../utils/observabilityLinks';
import { buildCloudIntentPath } from '../../utils/cloudIntentLinks';
import { RefreshCw, Server, AlertCircle, Network, Info, Map as MapIcon, Route, Play, Pause, XCircle, Shield, Wifi, Box, Layers, Globe, Cloud, Activity, Save, LayoutTemplate, LayoutGrid, Download, Upload, Link2, CheckCircle, ChevronDown, ChevronRight, BarChart3, GitBranch, Bell, FileText } from 'lucide-react';
import GroupNode from './GroupNode';
import NetworkNode from './NetworkNode';
import TopologyEditableEdge from './components/TopologyEditableEdge';
import { useToast } from '../../context/ToastContext';
import { aggregateLinks } from './utils/topologyGraphUtils';
import { formatBps, truncateLabel, buildEvidenceParts, getIconByRole } from './utils/topologyUiUtils';
import { t } from '../../i18n';
import useVisiblePolling from '../../hooks/useVisiblePolling';
import { startAuthenticatedSse } from '../../utils/sseClient';
import { getApiBaseUrl } from '../../api/baseUrl';
import { InlineEmpty } from '../common/PageState';
import NodePanel from './components/NodePanel';
import { getCloudResourceStatusMeta, getManagedDeviceStatusMeta, isDeviceOnline } from '../../utils/deviceStatusTone';
import useTopologyHistory from './hooks/useTopologyHistory';
import useTopologyKeyboard from './hooks/useTopologyKeyboard';
import TopologyContextMenu from './components/TopologyContextMenu';
import TopologyShortcutHint from './components/TopologyShortcutHint';
import TopologyEditPanel from './components/TopologyEditPanel';
import TopologyGroupResizeOverlay from './components/TopologyGroupResizeOverlay';
import dagre from 'dagre';
const CandidatePanel = lazy(() => import('./components/CandidatePanel'));
const PathTracePanel = lazy(() => import('./components/PathTracePanel'));
const FlowInsightPanel = lazy(() => import('./components/FlowInsightPanel'));
const EdgeDetailPanel = lazy(() => import('./components/EdgeDetailPanel'));
const EndpointGroupPanel = lazy(() => import('./components/EndpointGroupPanel'));
const CloudDetailPanel = lazy(() => import('./components/CloudDetailPanel'));

const nodeTypes = { groupNode: GroupNode, topologyNode: NetworkNode };
const edgeTypes = {
  default: TopologyEditableEdge,
  smoothstep: TopologyEditableEdge,
  step: TopologyEditableEdge,
  straight: TopologyEditableEdge,
};
const OVERLAY_PROTOCOLS = new Set(['VXLAN', 'EVPN', 'NVE', 'OVERLAY']);
const CLOUD_RESOURCE_TYPE_LABELS = {
  virtual_machine: 'VM',
  instance: 'Instance',
  vm: 'VM',
  load_balancer: 'Load Balancer',
  vpn_connection: 'VPN',
  vpn_tunnel: 'VPN Tunnel',
  transit_gateway: 'Transit Gateway',
  tgw_attachment: 'TGW Attachment',
  subnet: 'Subnet',
  vpc: 'VPC',
  vnet: 'VNet',
  network: 'Network',
  route_table: 'Route Table',
  security_group: 'Security Group',
};

const clampNumber = (value, min, max, fallback) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(min, Math.min(max, numeric));
};

const computeNodeEditorMetrics = ({ role, label, fontSize, wrapMode }) => {
  const nextFontSize = clampNumber(fontSize, 10, 20, role === 'cloud' ? 11 : 12);
  const mode = String(wrapMode || 'wrap').trim().toLowerCase() === 'single' ? 'single' : 'wrap';
  const labelLength = Math.max(10, String(label || '').trim().length || 10);
  const baseWidth = role === 'cloud' ? 156 : 146;
  const baseHeight = role === 'cloud' ? 106 : 96;
  const widthFromContent = mode === 'single'
    ? Math.min(280, Math.round((labelLength * nextFontSize * 0.44) + (role === 'cloud' ? 70 : 62)))
    : Math.min(220, Math.round(baseWidth + (Math.max(0, nextFontSize - 11) * 7) + (labelLength > 22 ? 8 : 0)));
  const heightFromContent = mode === 'single'
    ? baseHeight
    : Math.round(baseHeight + (Math.max(0, nextFontSize - 11) * 6) + (labelLength > 26 ? 8 : 0));
  return {
    fontSize: nextFontSize,
    wrapMode: mode,
    minWidth: Math.max(baseWidth, widthFromContent),
    minHeight: Math.max(baseHeight, heightFromContent),
  };
};

const formatCloudResourceType = (raw) => {
  const key = String(raw || '').trim().toLowerCase();
  if (!key) return '';
  if (CLOUD_RESOURCE_TYPE_LABELS[key]) return CLOUD_RESOURCE_TYPE_LABELS[key];
  return key
    .split('_')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
};

const EMPTY_LAYOUT_ENVELOPE = {
  version: 2,
  nodes: [],
  manualEdges: [],
  hiddenEdgeKeys: [],
  nodeOverrides: {},
  edgeOverrides: {},
};

const TOPOLOGY_GRID_SIZE = 24;
const GROUP_NODE_MAX_WIDTH = 12000;
const GROUP_NODE_MAX_HEIGHT = 8000;
const REGULAR_NODE_MAX_WIDTH = 1600;
const REGULAR_NODE_MAX_HEIGHT = 1200;

const snapToTopologyGrid = (value, grid = TOPOLOGY_GRID_SIZE) => {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return 0;
  return Math.round(numeric / grid) * grid;
};

const normalizeTopologyLayoutEnvelope = (raw) => {
  if (Array.isArray(raw)) {
    return {
      ...EMPTY_LAYOUT_ENVELOPE,
      nodes: raw,
    };
  }
  if (!raw || typeof raw !== 'object') {
    return { ...EMPTY_LAYOUT_ENVELOPE };
  }
  return {
    version: Number(raw.version || 2),
    nodes: Array.isArray(raw.nodes) ? raw.nodes : [],
    manualEdges: Array.isArray(raw.manualEdges) ? raw.manualEdges : [],
    hiddenEdgeKeys: Array.isArray(raw.hiddenEdgeKeys) ? raw.hiddenEdgeKeys.map((item) => String(item)) : [],
    nodeOverrides: raw.nodeOverrides && typeof raw.nodeOverrides === 'object' ? raw.nodeOverrides : {},
    edgeOverrides: raw.edgeOverrides && typeof raw.edgeOverrides === 'object' ? raw.edgeOverrides : {},
  };
};

const serializeTopologyLayoutEnvelope = (raw) => JSON.stringify(normalizeTopologyLayoutEnvelope(raw));

const serializeTopologyLayoutNodes = (items) => {
  const list = Array.isArray(items) ? items : [];
  return list.map((node) => {
    const payload = {
      id: String(node?.id || ''),
      type: node?.type,
      position: node?.position ? { x: Number(node.position.x || 0), y: Number(node.position.y || 0) } : { x: 0, y: 0 },
      parentNode: node?.parentNode ?? null,
      extent: node?.extent ?? null,
      width: Number(node?.width || 0) || undefined,
      height: Number(node?.height || 0) || undefined,
    };
    if (node?.type === 'groupNode' && node?.style && typeof node.style === 'object') {
      payload.style = node.style;
      payload.data = node.data && typeof node.data === 'object'
          ? {
            label: node.data.label,
            orgTop: node.data.orgTop,
            orgCount: node.data.orgCount,
            manualBox: !!node.data.manualBox,
            helperText: node.data.helperText,
            labelWrapMode: node.data.labelWrapMode,
            manualSized: !!node.data.manualSized,
            editorSizePinned: !!node.data.editorSizePinned,
          }
        : undefined;
    }
    if (node?.type !== 'groupNode' && node?.data && typeof node.data === 'object' && node.data.manualSized) {
      payload.data = {
        ...(payload.data || {}),
        manualSized: true,
      };
    }
    return payload;
  }).filter((node) => !!node.id);
};

const buildAutoEdgeKey = (source, target, protocol) => {
  const pair = [String(source || ''), String(target || '')].sort().join('|');
  const proto = String(protocol || 'LINK').trim().toUpperCase() || 'LINK';
  return `auto:${pair}|${proto}`;
};

const buildEdgePairKey = (source, target) => (
  [String(source || ''), String(target || '')].sort().join('|')
);

const buildTopologyEdgeKey = (edge) => {
  if (!edge || typeof edge !== 'object') return '';
  if (edge?.data?.manual) return String(edge.id || '');
  return buildAutoEdgeKey(edge.source, edge.target, edge?.data?.protocol);
};

const inferEdgeKind = (edge) => {
  const protocol = String(edge?.data?.protocol || edge?.protocol || '').trim().toUpperCase();
  const layer = String(edge?.data?.layer || edge?.layer || '').trim().toLowerCase();
  if (
    layer === 'hybrid' ||
    protocol === 'CLOUD' ||
    edge?.data?.hybrid ||
    edge?.hybrid
  ) return 'hybrid';
  if (layer === 'l3' || protocol === 'BGP' || protocol === 'OSPF') return 'l3';
  return 'l2';
};

const buildLineDash = (lineStyle) => {
  const key = String(lineStyle || 'solid').trim().toLowerCase();
  if (key === 'dashed') return '10 6';
  if (key === 'dotted') return '3 7';
  return undefined;
};

const buildManualWarningMeta = (edge, autoMatches = []) => {
  const kind = String(edge?.kind || edge?.data?.kind || 'manual').trim().toLowerCase() || 'manual';
  if (!Array.isArray(autoMatches) || autoMatches.length === 0) {
    return {
      tone: 'warning',
      badge: 'UNVERIFIED',
      message: t(
        'topology_manual_warning_unverified',
        'No discovered topology evidence currently supports this manual link.',
      ),
    };
  }

  const discoveredKinds = new Set(autoMatches.map((item) => inferEdgeKind(item)));
  if (kind !== 'manual' && !discoveredKinds.has(kind)) {
    return {
      tone: 'critical',
      badge: 'CONFLICT',
      message: t(
        'topology_manual_warning_conflict',
        'A discovered link exists between these nodes, but its protocol or layer does not match this manual link.',
      ),
    };
  }

  return {
    tone: 'warning',
    badge: 'SCAN EXISTS',
    message: t(
      'topology_manual_warning_overlap',
      'A discovered link already exists between these nodes. Keep the manual link only if it is an intentional annotation.',
    ),
  };
};

const buildManualEdgeStyle = (kind) => {
  const key = String(kind || 'manual').trim().toLowerCase();
  if (key === 'l2') return { stroke: '#2563eb', strokeWidth: 3 };
  if (key === 'l3') return { stroke: '#7c3aed', strokeWidth: 3 };
  if (key === 'hybrid') return { stroke: '#0284c7', strokeWidth: 3, strokeDasharray: '10 6' };
  return { stroke: '#0f172a', strokeWidth: 3, strokeDasharray: '8 5' };
};

const buildManualTopologyEdge = (edge, override, warningMeta = null) => {
  const label = String(override?.label ?? edge?.label ?? edge?.data?.manualLabel ?? 'Manual link').trim() || 'Manual link';
  const kind = String(override?.kind ?? edge?.kind ?? edge?.data?.kind ?? 'manual').trim().toLowerCase() || 'manual';
  const renderCurve = String(override?.curve || edge?.curve || edge?.data?.manualCurve || 'default').trim().toLowerCase() || 'default';
  const labelPosition = clampNumber(override?.labelPosition, 10, 90, clampNumber(edge?.labelPosition, 10, 90, 50));
  const labelOffsetY = clampNumber(override?.labelOffsetY, -80, 80, clampNumber(edge?.labelOffsetY, -80, 80, 0));
  const styleOverride = {
    stroke: String(override?.color || '').trim() || undefined,
    strokeWidth: Number(override?.width || 0) || undefined,
    strokeDasharray: buildLineDash(override?.lineStyle),
  };
  const style = {
    ...buildManualEdgeStyle(kind),
    ...(styleOverride.stroke ? { stroke: styleOverride.stroke } : {}),
    ...(styleOverride.strokeWidth ? { strokeWidth: styleOverride.strokeWidth } : {}),
    ...(styleOverride.strokeDasharray ? { strokeDasharray: styleOverride.strokeDasharray } : {}),
  };
  const warningTone = String(warningMeta?.tone || '').trim().toLowerCase();
  const warningColor = warningTone === 'critical' ? '#e11d48' : '#f59e0b';
  const finalStroke = warningMeta ? warningColor : style.stroke;
  const finalLabel = warningMeta ? `[${warningMeta.badge}] ${label}` : label;
  return {
    id: String(edge?.id || ''),
    source: String(edge?.source || ''),
    target: String(edge?.target || ''),
    label: finalLabel,
    type: renderCurve,
    animated: false,
    data: {
      manual: true,
      kind,
      protocol: kind.toUpperCase(),
      status: 'manual',
      layer: kind === 'l3' ? 'l3' : (kind === 'hybrid' ? 'hybrid' : 'l2'),
      fullLabel: finalLabel,
      manualLabel: label,
      manualColor: style.stroke,
      manualWidth: Number(style.strokeWidth || 3),
      manualCurve: renderCurve,
      manualLineStyle: String(override?.lineStyle || 'solid').trim().toLowerCase() || 'solid',
      manualLabelPosition: labelPosition,
      manualLabelOffsetY: labelOffsetY,
      labelPosition,
      labelOffsetY,
      renderCurve,
      warningMeta,
      tooltipLines: [`Manual ${kind.toUpperCase()} link`, label],
      portDetails: [`Manual ${kind.toUpperCase()} link`, label],
    },
    style: {
      ...style,
      stroke: finalStroke,
      cursor: 'pointer',
    },
    labelStyle: {
      fill: finalStroke,
      fontWeight: 800,
      fontSize: 11,
    },
    labelBgPadding: [6, 4],
    labelBgBorderRadius: 999,
    labelBgStyle: warningMeta
      ? {
          fill: warningTone === 'critical' ? '#ffe4e6' : '#fef3c7',
          color: finalStroke,
          stroke: finalStroke,
        }
      : undefined,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: finalStroke,
    },
  };
};

class TopologyPanelBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error('Topology side panel render failed:', error, info);
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="absolute right-4 top-4 z-30 w-[340px] max-w-[calc(100%-2rem)] overflow-hidden rounded-2xl border border-rose-500/30 bg-[#13171c]/95 text-white shadow-2xl backdrop-blur">
        <div className="px-4 py-4">
          <div className="text-sm font-bold text-rose-200">
            {t('topology_panel_error_title', 'Node detail is temporarily unavailable')}
          </div>
          <div className="mt-2 text-xs text-slate-300">
            {t('topology_panel_error_body', 'The selected node could not be rendered in the side panel. Close the panel and try another node.')}
          </div>
          {typeof this.props.onClose === 'function' ? (
            <button
              onClick={this.props.onClose}
              className="mt-3 inline-flex rounded-xl border border-slate-700 bg-slate-800/80 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700"
            >
              {t('common_close', 'Close')}
            </button>
          ) : null}
        </div>
      </div>
    );
  }
}

class TopologyEditorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error('Topology editor render failed:', error, info);
    if (typeof this.props.onError === 'function') {
      this.props.onError(error);
    }
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="absolute inset-x-4 bottom-4 z-40 max-w-xl rounded-2xl border border-amber-500/30 bg-[#13171c]/95 text-white shadow-2xl backdrop-blur">
        <div className="px-4 py-4">
          <div className="text-sm font-bold text-amber-200">
            {t('topology_editor_error_title', 'Layout editor is temporarily unavailable')}
          </div>
          <div className="mt-2 text-xs text-slate-300">
            {t('topology_editor_error_body', 'The map is still available. Exit layout editor and try again after the page settles.')}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              onClick={() => this.props.onRecover?.()}
              className="inline-flex rounded-xl bg-cyan-600 px-3 py-2 text-xs font-semibold text-white hover:bg-cyan-500"
            >
              {t('topology_editor_error_recover', 'Exit Layout Editor')}
            </button>
            <button
              onClick={() => this.props.onReset?.()}
              className="inline-flex rounded-xl border border-slate-700 bg-slate-800/80 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700"
            >
              {t('topology_editor_error_dismiss', 'Dismiss')}
            </button>
          </div>
        </div>
      </div>
    );
  }
}

// --------------------------------------------------------------------------
// 3. 硫붿씤 而댄룷?뚰듃
// --------------------------------------------------------------------------
const TopologyPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const { isOperator } = useAuth();
  const [nodes, setNodes] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [autoRefreshTopology, setAutoRefreshTopology] = useState(true);
  const [manualEditMode, setManualEditMode] = useState(false);
  const [editorBoundaryKey, setEditorBoundaryKey] = useState(0);
  const [editorSnapEnabled, setEditorSnapEnabled] = useState(true);
  const fileInputRef = useRef(null);
  const esRef = useRef(null);
  const topoReloadTimerRef = useRef(null);
  const topoReloadCooldownRef = useRef(0);
  const candidateReloadTimerRef = useRef(null);
  const snapshotReloadTimerRef = useRef(null);
  const loadSnapshotsRef = useRef(null);
  const loadCandidatesRef = useRef(null);
  const loadCandidateSummaryRef = useRef(null);
  const topologyStageRef = useRef(null);
  const suppressPaneClickUntilRef = useRef(0);
  const showCandidatesRef = useRef(false);
  const [streamConnected, setStreamConnected] = useState(false);

  // Data Filtering
  const [sites, setSites] = useState([]);
  const [selectedSiteId, setSelectedSiteId] = useState('all');
  const [rawTopology, setRawTopology] = useState({ nodes: [], links: [] });
  const [topologySnapshots, setTopologySnapshots] = useState([]);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState('');
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const snapshotModeRef = useRef(false);
  const [selectedTopologyNode, setSelectedTopologyNode] = useState(null);
  const [selectedTopologyEdge, setSelectedTopologyEdge] = useState(null);
  const [layoutNodesSnapshot, setLayoutNodesSnapshot] = useState([]);
  const [layoutManualEdges, setLayoutManualEdges] = useState([]);
  const [layoutHiddenEdgeKeys, setLayoutHiddenEdgeKeys] = useState([]);
  const [layoutNodeOverrides, setLayoutNodeOverrides] = useState({});
  const [layoutEdgeOverrides, setLayoutEdgeOverrides] = useState({});
  const [savedLayoutDigest, setSavedLayoutDigest] = useState(() => serializeTopologyLayoutEnvelope(EMPTY_LAYOUT_ENVELOPE));
  const [layoutPersistenceMeta, setLayoutPersistenceMeta] = useState({ savedAt: '', source: 'auto' });
  const manualEdgeCounterRef = useRef(1);
  const manualGroupCounterRef = useRef(1);
  const groupResizeHandlerRef = useRef(null);
  const pendingGroupSelectionRef = useRef('');
  const topologyNodesRef = useRef([]);

  const focusTopologyGroupNode = useCallback((groupNode) => {
    if (!groupNode || groupNode?.type !== 'groupNode') return;
    suppressPaneClickUntilRef.current = Date.now() + 300;
    if (typeof window !== 'undefined') {
      window.__netmanagerTopologyDebug = {
        ...(window.__netmanagerTopologyDebug || {}),
        lastFocusedGroupId: String(groupNode?.id || ''),
        lastFocusedGroupManualBox: !!groupNode?.data?.manualBox,
        lastFocusedGroupTs: Date.now(),
      };
    }
    setCloudDetailPanel({ open: false, node: null });
    setSelectedTopologyEdge(null);
    setSelectedTopologyNode(groupNode);
  }, []);

  const handleGroupFocusById = useCallback((groupId) => {
    const key = String(groupId || '').trim();
    if (!key) return;
    const matchedNode = topologyNodesRef.current.find((node) => String(node?.id || '') === key && node?.type === 'groupNode');
    if (!matchedNode) return;
    focusTopologyGroupNode(matchedNode);
  }, [focusTopologyGroupNode]);

  const shouldIgnoreGroupFocusEvent = useCallback((target) => {
    if (!(target instanceof HTMLElement)) return true;
    if (target.closest('[data-testid^="topology-group-resize-control-"]')) return true;
    if (target.closest('[data-testid="topology-group-node-editable"][data-node-id]')) return false;
    if (target.closest('[data-testid="topology-group-focus-surface"][data-node-id]')) return false;
    if (target.closest('[data-testid="topology-group-open-editor"][data-node-id]')) return false;
    if (target.closest('[data-testid="topology-group-overlay-open-editor"][data-node-id]')) return false;
    if (
      target.closest('[data-testid^="topology-toolbar-"]') ||
      target.closest('[data-testid^="topology-editor-"]') ||
      target.closest('.react-flow__controls') ||
      target.closest('.react-flow__minimap') ||
      target.closest('.react-flow__panel') ||
      target.closest('button, input, select, textarea, a, label')
    ) {
      return true;
    }
    return false;
  }, []);

  // --- Undo/Redo & Context Menu & Multi-Select ---
  const { pushSnapshot, undo, redo, canUndo, canRedo, clearHistory } = useTopologyHistory();
  const [contextMenu, setContextMenu] = useState(null);
  const [multiSelectedNodes, setMultiSelectedNodes] = useState([]);
  const saveLayoutRef = useRef(null);

  // Tooltip
  const [tooltip, setTooltip] = useState(null);
  const [edgeDetailPanel, setEdgeDetailPanel] = useState({ open: false, edge: null, events: [], loading: false, error: '' });
  const [edgeEventStateFilter, setEdgeEventStateFilter] = useState('all');
  const [edgeEventWindowMin, setEdgeEventWindowMin] = useState(15);
  const [edgeEventDiff, setEdgeEventDiff] = useState({ loading: false, error: '', data: null, eventId: null });
  const [highlightedLink, setHighlightedLink] = useState(null);
  const edgeDetailRef = useRef({ open: false, edge: null, events: [], loading: false, error: '' });
  const [cloudDetailPanel, setCloudDetailPanel] = useState({ open: false, node: null });
  const [cloudOrgFilter, setCloudOrgFilter] = useState({ enabled: false, org: '' });
  const [cloudProviderFilter, setCloudProviderFilter] = useState('all');
  const [cloudAccountFilter, setCloudAccountFilter] = useState('all');
  const [cloudRegionFilter, setCloudRegionFilter] = useState('all');
  const [cloudIntentImpactActive, setCloudIntentImpactActive] = useState(false);
  const [focusCloudResource, setFocusCloudResource] = useState({ resourceId: '', resourceName: '' });
  const [impactCloudResourceTypes, setImpactCloudResourceTypes] = useState([]);
  const [serviceOverlayEnabled, setServiceOverlayEnabled] = useState(false);
  const [serviceGroupOptions, setServiceGroupOptions] = useState([]);
  const [selectedServiceGroupId, setSelectedServiceGroupId] = useState('');
  const [selectedServiceGroupDetail, setSelectedServiceGroupDetail] = useState(null);
  const [serviceGroupsLoading, setServiceGroupsLoading] = useState(false);
  const appliedCloudFocusRef = useRef('');
  const appliedServiceGroupRef = useRef('');

  // Path Trace State
  const [showPathTrace, setShowPathTrace] = useState(false);
  const [srcIp, setSrcIp] = useState('');
  const [dstIp, setDstIp] = useState('');
  const [pathResult, setPathResult] = useState(null);
  const [pathPlayback, setPathPlayback] = useState(false);
  const [pathActiveEdgeIndex, setPathActiveEdgeIndex] = useState(null);
  const [pathEvidenceOpen, setPathEvidenceOpen] = useState({});
  const [pathPlaybackSpeed, setPathPlaybackSpeed] = useState(1);
  const [pathBadgesEnabled, setPathBadgesEnabled] = useState(true);
  const [pathEdgeLabelMaxLen, setPathEdgeLabelMaxLen] = useState(42);
  const [pathEdgeLabelTruncateMode, setPathEdgeLabelTruncateMode] = useState('all'); // 'all' | 'path'
  const reactFlowInstanceRef = useRef(null);
  const [tracing, setTracing] = useState(false);
  const handleEditorBoundaryError = useCallback(() => {
    setManualEditMode(false);
    setContextMenu(null);
    setEditorBoundaryKey((prev) => prev + 1);
    toast.error(t('topology_editor_error_toast', 'Layout editor hit a temporary error and was turned off to keep the map available.'));
  }, [toast]);

  const recoverEditorBoundary = useCallback(() => {
    setManualEditMode(false);
    setContextMenu(null);
    setEditorBoundaryKey((prev) => prev + 1);
  }, []);
  const handleGroupResize = useCallback((nodeId, patch) => {
    if (typeof groupResizeHandlerRef.current === 'function') {
      groupResizeHandlerRef.current(nodeId, patch);
    }
  }, []);

  // Flow Insight (NetFlow)
  const [showFlowInsight, setShowFlowInsight] = useState(false);
  const [flowWindowSec, setFlowWindowSec] = useState(300);
  const [flowTalkers, setFlowTalkers] = useState([]);
  const [flowFlows, setFlowFlows] = useState([]);
  const [flowApps, setFlowApps] = useState([]);
  const [flowSelectedApp, setFlowSelectedApp] = useState('');
  const [flowSelectedAppFlows, setFlowSelectedAppFlows] = useState([]);
  const [flowLoading, setFlowLoading] = useState(false);
  const [flowAppLoading, setFlowAppLoading] = useState(false);

  // Topology protocol/layer filter state
  const [layerFilter, setLayerFilter] = useState('all'); // 'all' | 'l2' | 'l3' | 'bgp' | 'ospf' | 'overlay' | 'hybrid'

  const [showCandidates, setShowCandidates] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [candidateJobId, setCandidateJobId] = useState('');
  const [candidateSearch, setCandidateSearch] = useState('');
  const [candidateSourceDeviceId, setCandidateSourceDeviceId] = useState('');
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [candidateEdits, setCandidateEdits] = useState({});
  const [candidateStatusFilter, setCandidateStatusFilter] = useState('all');
  const [candidateOrderBy, setCandidateOrderBy] = useState('priority');
  const [candidateOrderDir, setCandidateOrderDir] = useState('desc');
  const [candidateAutoRefresh, setCandidateAutoRefresh] = useState(true);
  const [candidateRecommendations, setCandidateRecommendations] = useState({});
  const [candidateRecOpen, setCandidateRecOpen] = useState({});
  const [candidateRecLoading, setCandidateRecLoading] = useState({});
  const [candidateActionError, setCandidateActionError] = useState({});
  const [selectedCandidateIds, setSelectedCandidateIds] = useState([]);
  const [candidateSummary, setCandidateSummary] = useState(null);
  const [candidateSummaryLoading, setCandidateSummaryLoading] = useState(false);
  const [candidateTrend, setCandidateTrend] = useState(null);
  const [candidateTrendDays, setCandidateTrendDays] = useState(7);
  const [candidateSiteId, setCandidateSiteId] = useState('');
  const candidateRouteInitRef = useRef(false);
  const hasCandidatePending = useMemo(() => {
    const activeStatuses = new Set(['pending', 'queued', 'new', 'open', 'proposed', 'backlog', 'unmatched', 'low_confidence']);
    return candidates.some((item) => activeStatuses.has(String(item?.status || '').trim().toLowerCase()));
  }, [candidates]);

  useEffect(() => {
    if (candidateRouteInitRef.current) return;
    const st = location?.state;
    if (!st || typeof st !== 'object') {
      candidateRouteInitRef.current = true;
      return;
    }
    const incomingJobId = st?.candidateJobId ?? st?.jobId;
    const incomingStatus = st?.candidateStatus;
    const incomingSource = st?.candidateSourceDeviceId;
    const incomingSearch = st?.candidateSearch;
    const shouldOpen =
      Boolean(st?.showCandidates) ||
      incomingJobId !== undefined ||
      incomingStatus !== undefined ||
      incomingSource !== undefined ||
      incomingSearch !== undefined;

    if (incomingJobId !== undefined && incomingJobId !== null && String(incomingJobId).trim() !== '') {
      setCandidateJobId(String(incomingJobId));
    }
    if (incomingStatus !== undefined && incomingStatus !== null && String(incomingStatus).trim() !== '') {
      setCandidateStatusFilter(String(incomingStatus));
    }
    if (incomingSource !== undefined && incomingSource !== null && String(incomingSource).trim() !== '') {
      setCandidateSourceDeviceId(String(incomingSource));
    }
    if (incomingSearch !== undefined && incomingSearch !== null) {
      setCandidateSearch(String(incomingSearch));
    }
    if (shouldOpen) setShowCandidates(true);
    candidateRouteInitRef.current = true;
  }, [location]);

  useEffect(() => {
    const params = new URLSearchParams(location.search || '');
    const incomingSiteId = params.get('siteId');
    if (incomingSiteId && incomingSiteId !== selectedSiteId) {
      setSelectedSiteId(incomingSiteId);
    }
    const incomingCloudProvider = String(params.get('cloudProvider') || '').trim().toLowerCase();
    const incomingCloudAccountId = String(params.get('cloudAccountId') || '').trim();
    const incomingCloudRegion = String(params.get('cloudRegion') || '').trim();
    const incomingCloudIntentImpact = String(params.get('cloudIntentImpact') || '').trim() === '1';
    const incomingCloudResourceTypes = String(params.get('cloudResourceTypes') || '')
      .split(',')
      .map((row) => String(row || '').trim().toLowerCase())
      .filter(Boolean);
    const incomingResourceId = String(params.get('focusCloudResourceId') || '').trim();
    const incomingResourceName = String(params.get('focusCloudResourceName') || '').trim();

    if (incomingCloudProvider) {
      setCloudProviderFilter(incomingCloudProvider);
      if (incomingCloudAccountId) setCloudAccountFilter(incomingCloudAccountId);
      if (incomingCloudRegion) setCloudRegionFilter(incomingCloudRegion);
    }
    setCloudIntentImpactActive(incomingCloudIntentImpact);
    setImpactCloudResourceTypes(incomingCloudResourceTypes);
    if (incomingResourceId || incomingResourceName) {
      setFocusCloudResource({ resourceId: incomingResourceId, resourceName: incomingResourceName });
    } else {
      setFocusCloudResource({ resourceId: '', resourceName: '' });
      appliedCloudFocusRef.current = '';
    }
    const incomingServiceOverlay = String(params.get('serviceOverlay') || '').trim() === '1';
    const incomingServiceGroupId = String(params.get('serviceGroupId') || '').trim();
    setServiceOverlayEnabled(incomingServiceOverlay);
    if (incomingServiceGroupId) {
      setSelectedServiceGroupId(incomingServiceGroupId);
    } else if (!incomingServiceOverlay) {
      setSelectedServiceGroupId('');
    }
  }, [location.search, selectedSiteId]);

  useEffect(() => {
    let active = true;
    const loadServiceGroups = async () => {
      try {
        const res = await ServiceGroupService.list();
        if (!active) return;
        const rows = Array.isArray(res?.data) ? res.data : [];
        setServiceGroupOptions(rows);
      } catch (error) {
        if (!active) return;
        setServiceGroupOptions([]);
      }
    };
    void loadServiceGroups();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const groupId = String(selectedServiceGroupId || '').trim();
    if (!groupId) {
      setSelectedServiceGroupDetail(null);
      return () => {
        active = false;
      };
    }
    const loadServiceGroupDetail = async () => {
      setServiceGroupsLoading(true);
      try {
        const res = await ServiceGroupService.get(groupId);
        if (!active) return;
        setSelectedServiceGroupDetail(res?.data || null);
      } catch (error) {
        if (!active) return;
        setSelectedServiceGroupDetail(null);
      } finally {
        if (active) setServiceGroupsLoading(false);
      }
    };
    void loadServiceGroupDetail();
    return () => {
      active = false;
    };
  }, [selectedServiceGroupId]);

  useEffect(() => {
    const resourceId = String(focusCloudResource?.resourceId || '').trim();
    const resourceName = String(focusCloudResource?.resourceName || '').trim();
    if (!resourceId && !resourceName) return;

    const focusKey = `${resourceId}::${resourceName}`;
    if (appliedCloudFocusRef.current === focusKey) return;

    const matchedNode = nodes.find((node) => {
      if (node?.type === 'groupNode' || node?.data?.role !== 'cloud') return false;
      const cloud = node?.data?.cloud || {};
      const nodeResourceId = String(cloud?.resource_id || '').trim();
      const nodeResourceName = String(cloud?.resource_name || '').trim();
      return (resourceId && nodeResourceId === resourceId) || (resourceName && nodeResourceName === resourceName);
    });

    if (!matchedNode) return;

    appliedCloudFocusRef.current = focusKey;
    setSelectedTopologyNode(null);
    setSelectedTopologyEdge(null);
    setCloudDetailPanel({ open: true, node: matchedNode });
  }, [focusCloudResource, nodes]);

  useEffect(() => {
    topologyNodesRef.current = Array.isArray(nodes) ? nodes : [];
  }, [nodes]);

  useEffect(() => {
    const pendingGroupId = String(pendingGroupSelectionRef.current || '').trim();
    if (pendingGroupId) {
      const pendingGroup = nodes.find((node) => String(node?.id || '') === pendingGroupId);
      if (pendingGroup) {
        pendingGroupSelectionRef.current = '';
        focusTopologyGroupNode(pendingGroup);
        return;
      }
    }
    if (!selectedTopologyNode?.id) return;
    const refreshed = nodes.find((node) => String(node.id) === String(selectedTopologyNode.id));
    if (refreshed) {
      setSelectedTopologyNode(refreshed);
    } else {
      setSelectedTopologyNode(null);
    }
  }, [focusTopologyGroupNode, nodes, selectedTopologyNode?.id]);

  useEffect(() => {
    if (!selectedTopologyEdge?.id) return;
    const refreshed = edges.find((edge) => String(edge.id) === String(selectedTopologyEdge.id));
    if (refreshed) {
      setSelectedTopologyEdge({ ...refreshed, layoutKey: buildTopologyEdgeKey(refreshed) });
    } else {
      setSelectedTopologyEdge(null);
    }
  }, [edges, selectedTopologyEdge?.id]);

  const applyLayoutEnvelope = useCallback((raw) => {
    const envelope = normalizeTopologyLayoutEnvelope(raw);
    setLayoutNodesSnapshot(envelope.nodes);
    setLayoutManualEdges(envelope.manualEdges);
    setLayoutHiddenEdgeKeys(envelope.hiddenEdgeKeys);
    setLayoutNodeOverrides(envelope.nodeOverrides);
    setLayoutEdgeOverrides(envelope.edgeOverrides);
    setSavedLayoutDigest(serializeTopologyLayoutEnvelope(envelope));
    const hasSavedContent = envelope.nodes.length > 0
      || envelope.manualEdges.length > 0
      || envelope.hiddenEdgeKeys.length > 0
      || Object.keys(envelope.nodeOverrides || {}).length > 0
      || Object.keys(envelope.edgeOverrides || {}).length > 0;
    setLayoutPersistenceMeta({
      savedAt: hasSavedContent ? new Date().toISOString() : '',
      source: hasSavedContent ? 'saved' : 'auto',
    });
    const manualIds = envelope.manualEdges
      .map((item) => {
        const match = String(item?.id || '').match(/manual-(\d+)/);
        return match ? Number(match[1]) : 0;
      })
      .filter((num) => Number.isFinite(num));
    manualEdgeCounterRef.current = manualIds.length > 0 ? (Math.max(...manualIds) + 1) : 1;
    const manualGroupIds = envelope.nodes
      .map((item) => {
        const match = String(item?.id || '').match(/manual-group-(\d+)/);
        return match ? Number(match[1]) : 0;
      })
      .filter((num) => Number.isFinite(num));
    manualGroupCounterRef.current = manualGroupIds.length > 0 ? (Math.max(...manualGroupIds) + 1) : 1;
  }, []);

  useEffect(() => {
    let active = true;
    const loadLayout = async () => {
      try {
        const res = await TopologyService.getLayout();
        if (!active) return;
        applyLayoutEnvelope(res?.data?.data);
      } catch (e) {
        if (!active) return;
        applyLayoutEnvelope(null);
      }
    };
    loadLayout();
    return () => {
      active = false;
    };
  }, [applyLayoutEnvelope]);

  const buildLayoutEnvelope = useCallback((currentNodes = nodes) => ({
    version: 2,
    nodes: serializeTopologyLayoutNodes(currentNodes),
    manualEdges: Array.isArray(layoutManualEdges) ? layoutManualEdges : [],
    hiddenEdgeKeys: Array.isArray(layoutHiddenEdgeKeys) ? layoutHiddenEdgeKeys : [],
    nodeOverrides: layoutNodeOverrides && typeof layoutNodeOverrides === 'object' ? layoutNodeOverrides : {},
    edgeOverrides: layoutEdgeOverrides && typeof layoutEdgeOverrides === 'object' ? layoutEdgeOverrides : {},
  }), [nodes, layoutManualEdges, layoutHiddenEdgeKeys, layoutNodeOverrides, layoutEdgeOverrides]);

  const currentLayoutDigest = useMemo(
    () => serializeTopologyLayoutEnvelope(buildLayoutEnvelope(nodes)),
    [buildLayoutEnvelope, nodes],
  );
  const layoutHasUnsavedChanges = currentLayoutDigest !== savedLayoutDigest;
  const layoutSavedTimeLabel = useMemo(() => {
    if (!layoutPersistenceMeta?.savedAt) return '';
    const savedAt = new Date(layoutPersistenceMeta.savedAt);
    if (Number.isNaN(savedAt.getTime())) return '';
    return savedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }, [layoutPersistenceMeta?.savedAt]);

  const onNodesChange = useCallback((changes) => {
    setNodes((currentNodes) => {
      const normalizedChanges = Array.isArray(changes) ? changes : [];
      const dimensionMap = new Map();
      for (const change of normalizedChanges) {
        const key = String(change?.id || '');
        if (!key || change?.type !== 'dimensions' || !change?.dimensions) continue;
        dimensionMap.set(key, {
          width: Number(change.dimensions.width || 0) || undefined,
          height: Number(change.dimensions.height || 0) || undefined,
        });
      }
      const nextNodes = applyNodeChanges(normalizedChanges, currentNodes).map((node) => {
        const key = String(node?.id || '');
        if (!dimensionMap.has(key)) return node;
        const nextSize = dimensionMap.get(key);
        return {
          ...node,
          width: nextSize.width,
          height: nextSize.height,
          data: {
            ...(node?.data || {}),
            manualSized: true,
            editorSizePinned: true,
          },
          style: {
            ...(node?.style || {}),
            ...(nextSize.width ? { width: nextSize.width } : {}),
            ...(nextSize.height ? { height: nextSize.height } : {}),
          },
        };
      });
      setLayoutNodesSnapshot((prev) => {
        const base = Array.isArray(prev) && prev.length > 0 ? prev : serializeTopologyLayoutNodes(nextNodes);
        const map = new Map(base.map((item) => [String(item.id), { ...item }]));
        for (const change of normalizedChanges) {
          const key = String(change?.id || '');
          if (!key) continue;
          const target = map.get(key);
          if (!target) continue;
          if (change.type === 'position' && change.position) {
            target.position = {
              x: Number(change.position.x || 0),
              y: Number(change.position.y || 0),
            };
          }
          if (change.type === 'dimensions' && change.dimensions) {
            target.width = Number(change.dimensions.width || 0) || undefined;
            target.height = Number(change.dimensions.height || 0) || undefined;
            target.data = {
              ...(target.data || {}),
              manualSized: true,
              editorSizePinned: true,
            };
          }
        }
        return Array.from(map.values());
      });
      return nextNodes;
    });
  }, [handleGroupResize, manualEditMode, setNodes]);

  const [endpointGroupPanel, setEndpointGroupPanel] = useState({ open: false, loading: false, error: '', group: null, endpoints: [] });

  const cloudFilterOptions = useMemo(() => {
    let scopedNodes = Array.isArray(rawTopology?.nodes) ? rawTopology.nodes : [];
    if (selectedSiteId !== 'all') {
      const siteIdNum = Number(selectedSiteId);
      if (Number.isFinite(siteIdNum)) {
        scopedNodes = scopedNodes.filter((n) => Number(n?.site_id) === siteIdNum);
      }
    }

    const providers = new Map();
    const accounts = new Map();
    const regions = new Set();

    for (const node of scopedNodes) {
      if (node?.role !== 'cloud') continue;
      const providerRaw = String(node?.cloud?.provider || node?.evidence?.provider || 'cloud').trim().toLowerCase() || 'cloud';
      const accountRaw = node?.cloud?.account_id ?? node?.evidence?.account_id;
      const accountId = accountRaw == null ? '' : String(accountRaw).trim();
      const accountName = String(node?.cloud?.account_name || node?.evidence?.account_name || '').trim();
      const region = String(node?.cloud?.region || node?.evidence?.region || '').trim();

      providers.set(providerRaw, providerRaw.toUpperCase());

      const providerMatches = cloudProviderFilter === 'all' || providerRaw === cloudProviderFilter;
      if (providerMatches && accountId) {
        const accountLabel = accountName ? `${accountName} (#${accountId})` : `#${accountId}`;
        accounts.set(accountId, accountLabel);
      }

      const accountMatches = cloudAccountFilter === 'all' || (!!accountId && accountId === cloudAccountFilter);
      if (providerMatches && accountMatches && region) {
        regions.add(region);
      }
    }

    return {
      providers: Array.from(providers.entries())
        .map(([value, label]) => ({ value, label }))
        .sort((a, b) => a.label.localeCompare(b.label)),
      accounts: Array.from(accounts.entries())
        .map(([value, label]) => ({ value, label }))
        .sort((a, b) => a.label.localeCompare(b.label)),
      regions: Array.from(regions.values())
        .map((value) => ({ value, label: value }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    };
  }, [rawTopology?.nodes, selectedSiteId, cloudProviderFilter, cloudAccountFilter]);

  const selectedServiceGroupOption = useMemo(
    () => (serviceGroupOptions || []).find((row) => String(row?.id || '') === String(selectedServiceGroupId || '')) || null,
    [serviceGroupOptions, selectedServiceGroupId],
  );

  const serviceOverlayMemberSets = useMemo(() => {
    const members = Array.isArray(selectedServiceGroupDetail?.members) ? selectedServiceGroupDetail.members : [];
    const deviceIds = new Set();
    const cloudResourceIds = new Set();
    const cloudResourceDbIds = new Set();
    members.forEach((member) => {
      if (String(member?.member_type || '').trim().toLowerCase() === 'device') {
        const deviceId = String(member?.device_id ?? '').trim();
        if (deviceId) deviceIds.add(deviceId);
        return;
      }
      const resourceId = String(member?.resource_id || '').trim();
      const cloudResourceId = String(member?.cloud_resource_id ?? '').trim();
      if (resourceId) cloudResourceIds.add(resourceId);
      if (cloudResourceId) cloudResourceDbIds.add(cloudResourceId);
    });
    return { deviceIds, cloudResourceIds, cloudResourceDbIds };
  }, [selectedServiceGroupDetail]);

  const serviceOverlayColor = useMemo(() => {
    const candidate = String(selectedServiceGroupDetail?.color || selectedServiceGroupOption?.color || '').trim();
    return candidate || '#0ea5e9';
  }, [selectedServiceGroupDetail?.color, selectedServiceGroupOption?.color]);

  const loadCandidateSummary = async () => {
    setCandidateSummaryLoading(true);
    try {
      const params = {};
      if (candidateJobId) params.job_id = Number(candidateJobId);
      if (candidateSourceDeviceId) params.source_device_id = Number(candidateSourceDeviceId);
      if (candidateSiteId) params.site_id = Number(candidateSiteId);
      const [summaryRes, trendRes] = await Promise.all([
        TopologyService.getCandidateSummary(params),
        TopologyService.getCandidateSummaryTrend({
          days: Number(candidateTrendDays) || 7,
          limit: 5,
          site_id: candidateSiteId ? Number(candidateSiteId) : undefined,
          source_device_id: candidateSourceDeviceId ? Number(candidateSourceDeviceId) : undefined,
        }),
      ]);
      setCandidateSummary(summaryRes?.data || null);
      setCandidateTrend(trendRes?.data || null);
    } catch (e) {
      setCandidateSummary(null);
      setCandidateTrend(null);
    } finally {
      setCandidateSummaryLoading(false);
    }
  };

  const loadCandidates = async () => {
    setCandidateLoading(true);
    try {
      const params = {
        order_by: candidateOrderBy,
        order_dir: candidateOrderDir,
        limit: 500,
      };
      if (candidateJobId) params.job_id = candidateJobId;
      if (candidateStatusFilter !== 'all') params.status = candidateStatusFilter;
      if (candidateSearch) params.search = candidateSearch;
      if (candidateSourceDeviceId) params.source_device_id = Number(candidateSourceDeviceId);
      if (candidateSiteId) params.site_id = Number(candidateSiteId);
      const res = await TopologyService.getCandidates(params);
      const list = res.data || [];
      setCandidates(list);
      loadCandidateSummary();
      setSelectedCandidateIds((prev) => prev.filter((id) => list.some((c) => c.id === id)));
      setCandidateEdits((prev) => {
        const next = { ...prev };
        for (const c of list) {
          if (next[c.id] === undefined) next[c.id] = c.mgmt_ip || '';
        }
        return next;
      });
    } catch (e) {
      toast.error(t('topology_candidates_load_failed', 'Failed to load candidates'));
    } finally {
      setCandidateLoading(false);
    }
  };

  // Health View State
  const [showHealth, setShowHealth] = useState(false);
  const [healthMetric, setHealthMetric] = useState('score'); // 'score' | 'cpu' | 'memory'
  const [trafficFlowEnabled, setTrafficFlowEnabled] = useState(false);
  const [lowConfidenceOnly, setLowConfidenceOnly] = useState(false);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.7);

  // 1. Load Data
  const loadData = async () => {
    setLoading(true);
    try {
      console.log("?뱻 Fetching Topology & Sites...");
      const [topoRes, siteRes] = await Promise.all([
        SDNService.getTopology(selectedSnapshotId ? { snapshot_id: selectedSnapshotId } : {}),
        DeviceService.getSites()
      ]);

      setSites(siteRes.data);
      setRawTopology({
        nodes: topoRes.data?.nodes || [],
        links: topoRes.data?.links || []
      });

    } catch (error) {
      console.error("Error loading data:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadSnapshots = async () => {
    setSnapshotLoading(true);
    try {
      const res = await TopologyService.listSnapshots({ limit: 50 });
      setTopologySnapshots(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setTopologySnapshots([]);
    } finally {
      setSnapshotLoading(false);
    }
  };

  const handlePromoteManagedNode = async (deviceId) => {
    if (!deviceId) return;
    try {
      await DeviceService.promoteToManaged(deviceId);
      toast.success(t('devices_manage_promoted', 'This node is now actively managed.'));
      setRefreshKey((prev) => prev + 1);
    } catch (error) {
      const message =
        error?.response?.data?.detail?.message ||
        error?.response?.data?.message ||
        t('devices_manage_promote_failed', 'Unable to assign a managed slot.');
      toast.error(message);
    }
  };

  const handleReleaseManagedNode = async (deviceId) => {
    if (!deviceId) return;
    try {
      await DeviceService.releaseManagement(deviceId);
      toast.success(t('devices_manage_released', 'The managed slot was released.'));
      setRefreshKey((prev) => prev + 1);
    } catch (error) {
      const message =
        error?.response?.data?.detail?.message ||
        error?.response?.data?.message ||
        t('devices_manage_release_failed', 'Unable to release this managed slot.');
      toast.error(message);
    }
  };

  showCandidatesRef.current = showCandidates;
  loadSnapshotsRef.current = loadSnapshots;
  loadCandidatesRef.current = loadCandidates;
  loadCandidateSummaryRef.current = loadCandidateSummary;

  const loadFlowInsight = async () => {
    setFlowLoading(true);
    try {
      const [talkersRes, flowsRes, appsRes] = await Promise.all([
        TrafficService.getTopTalkers({ window_sec: flowWindowSec, limit: 10 }),
        TrafficService.getTopFlows({ window_sec: flowWindowSec, limit: 10 }),
        TrafficService.getTopApps({ window_sec: flowWindowSec, limit: 10 }),
      ]);
      setFlowTalkers(Array.isArray(talkersRes.data) ? talkersRes.data : []);
      setFlowFlows(Array.isArray(flowsRes.data) ? flowsRes.data : []);
      const apps = Array.isArray(appsRes.data) ? appsRes.data : [];
      setFlowApps(apps);
      if (!flowSelectedApp && apps.length > 0) {
        setFlowSelectedApp(String(apps[0].app || ''));
      }
    } catch (e) {
      toast.error(t('topology_flow_insight_load_failed', 'Failed to load flow insight'));
    } finally {
      setFlowLoading(false);
    }
  };

  const loadSelectedAppFlows = async (appName) => {
    const app = String(appName || '').trim();
    if (!app) return;
    setFlowAppLoading(true);
    try {
      const res = await TrafficService.getTopAppFlows({ app, window_sec: flowWindowSec, limit: 10 });
      setFlowSelectedAppFlows(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      toast.error(t('topology_app_flows_load_failed', 'Failed to load app flows'));
    } finally {
      setFlowAppLoading(false);
    }
  };

  const handleTrace = async () => {
    if (!srcIp || !dstIp) return;
    setTracing(true);
    setPathResult(null);
    setPathPlayback(false);
    setPathActiveEdgeIndex(null);
    setPathEvidenceOpen({});
    setPathPlaybackSpeed(1);
    setPathBadgesEnabled(true);
    try {
      const res = await SDNService.tracePath(srcIp, dstIp);
      setPathResult(res.data);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string'
        ? detail
        : (detail?.message || err?.message || 'unknown error');
      toast.error(`${t('topology_trace_failed', 'Trace failed')}: ${message}`);
    } finally {
      setTracing(false);
    }
  };

  const clearTrace = () => {
    setPathResult(null);
    setSrcIp('');
    setDstIp('');
    setPathPlayback(false);
    setPathActiveEdgeIndex(null);
    setPathEvidenceOpen({});
    setPathPlaybackSpeed(1);
    setPathBadgesEnabled(true);
  };

  const focusActiveHop = useCallback((edgeIdx) => {
    const inst = reactFlowInstanceRef.current;
    if (!inst) return;
    if (!pathResult?.path || pathResult.path.length < 2) return;
    if (edgeIdx == null) return;

    const maxIdx = pathResult.path.length - 2;
    const i = Math.min(Math.max(0, Number(edgeIdx)), maxIdx);
    const fromId = String(pathResult.path[i]?.id ?? '');
    const toId = String(pathResult.path[i + 1]?.id ?? '');
    if (!fromId || !toId) return;

    const nodesToFit = inst.getNodes().filter(n => String(n.id) === fromId || String(n.id) === toId);
    if (nodesToFit.length === 0) return;
    inst.fitView({ nodes: nodesToFit, padding: 0.55, duration: 450, maxZoom: 1.35 });
  }, [pathResult]);

  useEffect(() => {
    if (!pathResult?.path || pathResult.path.length < 2) return;
    setPathPlayback(false);
    setPathActiveEdgeIndex(null);
    setPathEvidenceOpen({});

    const ids = new Set(pathResult.path.map(n => String(n.id)));
    const timer = setTimeout(() => {
      const inst = reactFlowInstanceRef.current;
      if (!inst) return;
      const nodesToFit = inst.getNodes().filter(n => ids.has(String(n.id)));
      if (nodesToFit.length > 0) {
        inst.fitView({ nodes: nodesToFit, padding: 0.3, duration: 500 });
      }
    }, 50);
    return () => clearTimeout(timer);
  }, [pathResult]);

  useEffect(() => {
    if (pathActiveEdgeIndex == null) return;
    const t = setTimeout(() => {
      focusActiveHop(pathActiveEdgeIndex);
    }, 30);
    return () => clearTimeout(t);
  }, [pathActiveEdgeIndex, focusActiveHop]);

  useEffect(() => {
    if (!pathPlayback) return;
    if (!pathResult?.path || pathResult.path.length < 2) return;

    const maxIdx = pathResult.path.length - 2;
    const speed = Number(pathPlaybackSpeed || 1);
    const intervalMs = Math.max(200, Math.round(900 / (Number.isFinite(speed) && speed > 0 ? speed : 1)));
    const timer = setTimeout(() => {
      setPathActiveEdgeIndex((prev) => {
        const next = prev == null ? 0 : prev + 1;
        if (next > maxIdx) {
          setPathPlayback(false);
          return maxIdx;
        }
        return next;
      });
    }, intervalMs);
    return () => clearTimeout(timer);
  }, [pathPlayback, pathActiveEdgeIndex, pathResult, pathPlaybackSpeed]);

  useEffect(() => {
    if (!showFlowInsight) return;
    loadFlowInsight();
  }, [showFlowInsight, flowWindowSec]);

  useEffect(() => {
    if (!showFlowInsight) return;
    if (!flowSelectedApp) return;
    loadSelectedAppFlows(flowSelectedApp);
  }, [showFlowInsight, flowSelectedApp, flowWindowSec]);

  useEffect(() => {
    loadData();
  }, [refreshKey]);

  useEffect(() => {
    snapshotModeRef.current = !!selectedSnapshotId;
    if (selectedSnapshotId) {
      setAutoRefreshTopology(false);
    }
    loadData();
  }, [selectedSnapshotId]);

  useEffect(() => {
    loadSnapshots();
  }, [refreshKey]);

  useEffect(() => {
    edgeDetailRef.current = edgeDetailPanel;
  }, [edgeDetailPanel]);

  const fetchLinkEvents = useCallback(async (edge, limit = 30) => {
    const src = Number(edge?.source);
    const dst = Number(edge?.target);
    const proto = String(edge?.data?.protocol || '').toUpperCase() || undefined;
    const res = await TopologyService.listEvents({
      event_type: 'link_update',
      source_device_id: Number.isFinite(src) ? src : undefined,
      target_device_id: Number.isFinite(dst) ? dst : undefined,
      protocol: proto,
      limit,
    });
    return Array.isArray(res?.data) ? res.data : [];
  }, []);

  useEffect(() => {
    if (esRef.current) {
      try { esRef.current.close(); } catch (e) { void e; }
      esRef.current = null;
    }
    setStreamConnected(false);

    const API_BASE_URL = getApiBaseUrl();
    const url = `${API_BASE_URL}/topology/stream`;
    const authToken = localStorage.getItem('authToken');

    const norm = (s) => String(s || '').trim().toLowerCase().replace(/\s+/g, '');
    const scheduleTopologyReload = (delayMs = 700) => {
      if (topoReloadTimerRef.current) return;
      topoReloadTimerRef.current = setTimeout(() => {
        topoReloadTimerRef.current = null;
        const now = Date.now();
        if (now - topoReloadCooldownRef.current < 1500) return;
        topoReloadCooldownRef.current = now;
        setRefreshKey((k) => k + 1);
      }, Math.max(0, Number(delayMs) || 0));
    };
    const scheduleSnapshotReload = (delayMs = 250) => {
      if (snapshotReloadTimerRef.current) return;
      snapshotReloadTimerRef.current = setTimeout(() => {
        snapshotReloadTimerRef.current = null;
        const fn = loadSnapshotsRef.current;
        if (typeof fn === 'function') {
          void fn();
        }
      }, Math.max(0, Number(delayMs) || 0));
    };
    const scheduleCandidateReload = (delayMs = 250) => {
      if (!showCandidatesRef.current) return;
      if (candidateReloadTimerRef.current) return;
      candidateReloadTimerRef.current = setTimeout(() => {
        candidateReloadTimerRef.current = null;
        const loadCandidatesFn = loadCandidatesRef.current;
        const loadSummaryFn = loadCandidateSummaryRef.current;
        if (typeof loadCandidatesFn === 'function') {
          void loadCandidatesFn();
        } else if (typeof loadSummaryFn === 'function') {
          void loadSummaryFn();
        }
      }, Math.max(0, Number(delayMs) || 0));
    };

    const stream = startAuthenticatedSse({
      url,
      token: authToken,
      retryMs: 2500,
      onOpen: () => {
        setStreamConnected(true);
      },
      onClose: () => {
        setStreamConnected(false);
      },
      onEvent: ({ event, data }) => {
        try {
          if (snapshotModeRef.current) return;
          const msg = JSON.parse(data || '{}');
          if (event === 'topology_refresh') {
            scheduleTopologyReload(200);
            if (msg?.candidate_summary_changed || Number(msg?.candidates_created || 0) > 0) {
              scheduleCandidateReload(200);
            }
            return;
          }
          if (event === 'topology_snapshot_created') {
            scheduleSnapshotReload(120);
            return;
          }
          if (event === 'topology_candidate_update') {
            scheduleCandidateReload(120);
            return;
          }
          if (event !== 'link_update') return;

          const deviceId = msg.device_id != null ? String(msg.device_id) : null;
          const neighborId = msg.neighbor_device_id != null ? String(msg.neighbor_device_id) : null;
          const protocol = msg.protocol ? String(msg.protocol).toUpperCase() : null;
          const state = String(msg.state || '').toLowerCase();
          const isUp = state === 'up' || state === 'active';
          const isDegraded = state === 'degraded';
          const nextStatus = isDegraded ? 'degraded' : (isUp ? 'active' : 'down');
          const reason = msg.reason != null ? String(msg.reason) : null;
          const ifName = msg.interface ? String(msg.interface) : '';
          const ifNorm = norm(ifName);

          setRawTopology(prev => {
            const prevLinks = Array.isArray(prev?.links) ? prev.links : [];
            if (prevLinks.length === 0) return prev;
            let matched = false;
            const updated = prevLinks.map((l) => {
              const lProto = String(l?.protocol || 'LLDP').toUpperCase();
              if (protocol && lProto !== protocol) return l;

              const src = String(l?.source ?? '');
              const dst = String(l?.target ?? '');

              if (neighborId) {
                const match = (src === deviceId && dst === neighborId) || (src === neighborId && dst === deviceId);
                if (!match) return l;
                matched = true;
                if (l.status === nextStatus) return l;
                if (nextStatus === 'degraded') {
                  return { ...l, status: nextStatus, reason: reason || l.reason || null };
                }
                if (l.reason != null) {
                  const { reason: _r, ...rest } = l;
                  return { ...rest, status: nextStatus };
                }
                return { ...l, status: nextStatus };
              }

              if (!deviceId || !ifNorm) return l;
              const srcPortNorm = norm(l?.src_port);
              const dstPortNorm = norm(l?.dst_port);
              const match = (src === deviceId && srcPortNorm === ifNorm) || (dst === deviceId && dstPortNorm === ifNorm);
              if (!match) return l;
              matched = true;
              if (l.status === nextStatus) return l;
              if (nextStatus === 'degraded') {
                return { ...l, status: nextStatus, reason: reason || l.reason || null };
              }
              if (l.reason != null) {
                const { reason: _r, ...rest } = l;
                return { ...rest, status: nextStatus };
              }
              return { ...l, status: nextStatus };
            });
            if (!matched && deviceId && neighborId) {
              scheduleTopologyReload(700);
            }
            return { ...prev, links: updated };
          });

          if (msg?.structure_changed || msg?.refresh_hint === 'topology') {
            scheduleTopologyReload(220);
          }
          if (msg?.refresh_hint === 'candidates') {
            scheduleCandidateReload(180);
          }
          if (msg?.refresh_hint === 'snapshots') {
            scheduleSnapshotReload(180);
          }

          // If edge detail panel is open for this link, stream-in the latest event immediately.
          const panel = edgeDetailRef.current;
          const edge = panel?.edge;
          if (panel?.open && edge) {
            const eProto = String(edge?.data?.protocol || '').toUpperCase();
            const eSrc = String(edge?.source ?? '');
            const eDst = String(edge?.target ?? '');
            const mSrc = msg.device_id != null ? String(msg.device_id) : '';
            const mDst = msg.neighbor_device_id != null ? String(msg.neighbor_device_id) : '';
            const protoMatch = !protocol || !eProto || eProto === protocol;
            const pairMatch = mSrc && mDst && ((eSrc === mSrc && eDst === mDst) || (eSrc === mDst && eDst === mSrc));
            if (protoMatch && pairMatch) {
              const live = {
                id: `live-${Date.now()}-${mSrc}-${mDst}-${protocol || 'UNKNOWN'}`,
                event_type: 'link_update',
                created_at: new Date().toISOString(),
                payload: {
                  device_id: msg.device_id,
                  neighbor_device_id: msg.neighbor_device_id,
                  local_interface: msg.local_interface || '',
                  remote_interface: msg.remote_interface || '',
                  protocol: protocol || 'UNKNOWN',
                  state: msg.state || '',
                  reason: reason || undefined,
                  source: msg.source || 'sse',
                },
              };
              setEdgeDetailPanel((prev) => {
                if (!prev?.open || !prev?.edge) return prev;
                const pSrc = String(prev.edge.source ?? '');
                const pDst = String(prev.edge.target ?? '');
                if (!((pSrc === mSrc && pDst === mDst) || (pSrc === mDst && pDst === mSrc))) return prev;
                const next = [live, ...(Array.isArray(prev.events) ? prev.events : [])];
                return { ...prev, events: next.slice(0, 30) };
              });
            }
          }
        } catch (e) { void e; }
      },
      onError: () => {
        setStreamConnected(false);
        // Polling remains active, so stream errors degrade gracefully.
      },
    });
    esRef.current = stream;

    return () => {
      if (topoReloadTimerRef.current) {
        try { clearTimeout(topoReloadTimerRef.current); } catch (e) { void e; }
        topoReloadTimerRef.current = null;
      }
      if (candidateReloadTimerRef.current) {
        try { clearTimeout(candidateReloadTimerRef.current); } catch (e) { void e; }
        candidateReloadTimerRef.current = null;
      }
      if (snapshotReloadTimerRef.current) {
        try { clearTimeout(snapshotReloadTimerRef.current); } catch (e) { void e; }
        snapshotReloadTimerRef.current = null;
      }
      setStreamConnected(false);
      try { stream.close(); } catch (e) { void e; }
      esRef.current = null;
    };
  }, []);

  useVisiblePolling(() => {
    void loadData();
  }, streamConnected ? 30000 : 10000, {
    enabled: !!autoRefreshTopology,
    immediate: false,
    runOnVisible: true,
    minGapMs: streamConnected ? 5000 : 2500,
    backoffOnError: false,
  });

  useEffect(() => {
    const onPick = (e) => {
      const org = String(e?.detail?.org || '').trim();
      if (!org) {
        setCloudOrgFilter({ enabled: false, org: '' });
        return;
      }
      setCloudOrgFilter((prev) => {
        if (prev.enabled && prev.org === org) return { enabled: false, org: '' };
        return { enabled: true, org };
      });
    };
    window.addEventListener('netmanager:cloud-org-filter', onPick);
    return () => window.removeEventListener('netmanager:cloud-org-filter', onPick);
  }, []);

  useEffect(() => {
    if (cloudProviderFilter !== 'all' && !cloudFilterOptions.providers.some((p) => p.value === cloudProviderFilter)) {
      setCloudProviderFilter('all');
    }
  }, [cloudProviderFilter, cloudFilterOptions.providers]);

  useEffect(() => {
    if (cloudAccountFilter !== 'all' && !cloudFilterOptions.accounts.some((a) => a.value === cloudAccountFilter)) {
      setCloudAccountFilter('all');
    }
  }, [cloudAccountFilter, cloudFilterOptions.accounts]);

  useEffect(() => {
    if (cloudRegionFilter !== 'all' && !cloudFilterOptions.regions.some((r) => r.value === cloudRegionFilter)) {
      setCloudRegionFilter('all');
    }
  }, [cloudRegionFilter, cloudFilterOptions.regions]);

  useEffect(() => {
    if (!showCandidates) return;
    loadCandidates();
  }, [showCandidates, candidateJobId, candidateStatusFilter, candidateOrderBy, candidateOrderDir, candidateSourceDeviceId, candidateSiteId, refreshKey]);

  useEffect(() => {
    if (!showCandidates) return;
    const t = setTimeout(() => {
      loadCandidates();
    }, 400);
    return () => clearTimeout(t);
  }, [showCandidates, candidateSearch]);

  useVisiblePolling(() => {
    void loadCandidates();
  }, hasCandidatePending ? 8000 : 20000, {
    enabled: !!showCandidates && !!candidateAutoRefresh,
    immediate: false,
    runOnVisible: true,
    minGapMs: hasCandidatePending ? 2000 : 5000,
    backoffOnError: false,
  });

  useEffect(() => {
    if (!showCandidates) return;
    loadCandidateSummary();
  }, [showCandidates, candidateJobId, candidateSourceDeviceId, candidateTrendDays, candidateSiteId]);

  // 2. Process Nodes & Edges
  useEffect(() => {
    if (!rawTopology.nodes.length) return;

    // A. Filter Nodes
    let filteredNodes = rawTopology.nodes;
    if (selectedSiteId !== 'all') {
      filteredNodes = rawTopology.nodes.filter(n => n.site_id === parseInt(selectedSiteId));
    }

    const baseVisibleNodeIds = new Set(filteredNodes.map(n => String(n.id)));
    const scopedNodeMap = new Map(filteredNodes.map((n) => [String(n.id), n]));
    let filteredLinks = rawTopology.links.filter(l => {
      if (!baseVisibleNodeIds.has(String(l.source)) || !baseVisibleNodeIds.has(String(l.target))) return false;
      const srcNode = scopedNodeMap.get(String(l.source));
      const dstNode = scopedNodeMap.get(String(l.target));
      const proto = (l.protocol || 'LLDP').toUpperCase();
      const layerKind = String(l?.layer || '').trim().toLowerCase();
      const isOverlayProto = layerKind === 'overlay' || OVERLAY_PROTOCOLS.has(proto);
      const isL3Proto = !isOverlayProto && (layerKind === 'l3' || proto === 'OSPF' || proto === 'BGP');
      const isHybridProto =
        (l?.hybrid && typeof l.hybrid === 'object')
        || layerKind === 'hybrid'
        || proto === 'CLOUD'
        || srcNode?.role === 'cloud'
        || dstNode?.role === 'cloud';
      if (layerFilter === 'l2' && (isL3Proto || isOverlayProto)) return false;
      if (layerFilter === 'l3' && !isL3Proto) return false;
      if (layerFilter === 'bgp' && proto !== 'BGP') return false;
      if (layerFilter === 'ospf' && proto !== 'OSPF') return false;
      if (layerFilter === 'overlay' && !isOverlayProto) return false;
      if (layerFilter === 'hybrid' && !isHybridProto) return false;
      if (lowConfidenceOnly) {
        const c = Number(l?.confidence ?? l?.evidence?.confidence ?? 0);
        const confidence = Number.isFinite(c) ? c : 0;
        if (confidence >= Number(confidenceThreshold || 0.7)) return false;
      }
      return true;
    });

    const cloudFilterActive =
      cloudProviderFilter !== 'all' ||
      cloudAccountFilter !== 'all' ||
      cloudRegionFilter !== 'all';

    if (cloudFilterActive) {
      const matchedCloudNodeIds = new Set();
      for (const n of filteredNodes) {
        if (n?.role !== 'cloud') continue;
        const provider = String(n?.cloud?.provider || n?.evidence?.provider || 'cloud').trim().toLowerCase() || 'cloud';
        const accountRaw = n?.cloud?.account_id ?? n?.evidence?.account_id;
        const accountId = accountRaw == null ? '' : String(accountRaw).trim();
        const region = String(n?.cloud?.region || n?.evidence?.region || '').trim();

        const providerMatch = cloudProviderFilter === 'all' || provider === cloudProviderFilter;
        const accountMatch = cloudAccountFilter === 'all' || (!!accountId && accountId === cloudAccountFilter);
        const regionMatch = cloudRegionFilter === 'all' || (!!region && region === cloudRegionFilter);

        if (providerMatch && accountMatch && regionMatch) {
          matchedCloudNodeIds.add(String(n.id));
        }
      }

      if (matchedCloudNodeIds.size === 0) {
        filteredNodes = [];
        filteredLinks = [];
      } else {
        const relatedNodeIds = new Set(matchedCloudNodeIds);
        for (const l of filteredLinks) {
          const proto = String(l.protocol || '').toUpperCase();
          const layerKind = String(l?.layer || '').trim().toLowerCase();
          const isHybridProto =
            (l?.hybrid && typeof l.hybrid === 'object')
            || layerKind === 'hybrid'
            || proto === 'CLOUD';
          const isL3 = layerKind === 'l3' || proto === 'BGP' || proto === 'OSPF';
          if (!(isL3 || isHybridProto)) continue;
          const s = String(l.source);
          const t = String(l.target);
          if (matchedCloudNodeIds.has(s)) relatedNodeIds.add(t);
          if (matchedCloudNodeIds.has(t)) relatedNodeIds.add(s);
        }

        filteredNodes = filteredNodes.filter((n) => {
          if (n?.role === 'cloud') return matchedCloudNodeIds.has(String(n.id));
          return relatedNodeIds.has(String(n.id));
        });

        const scopedNodeIds = new Set(filteredNodes.map((n) => String(n.id)));
        filteredLinks = filteredLinks.filter((l) => scopedNodeIds.has(String(l.source)) && scopedNodeIds.has(String(l.target)));
      }
    }

    if (layerFilter === 'hybrid') {
      const hybridNodeIds = new Set();
      for (const link of filteredLinks) {
        hybridNodeIds.add(String(link.source));
        hybridNodeIds.add(String(link.target));
      }

      filteredNodes = filteredNodes.filter((node) => {
        const hybrid = node?.hybrid && typeof node.hybrid === 'object' ? node.hybrid : {};
        return node?.role === 'cloud'
          || hybridNodeIds.has(String(node.id))
          || Number(hybrid.hybrid_links || 0) > 0;
      });

      const scopedNodeIds = new Set(filteredNodes.map((n) => String(n.id)));
      filteredLinks = filteredLinks.filter((l) => scopedNodeIds.has(String(l.source)) && scopedNodeIds.has(String(l.target)));
    }

    if (layerFilter === 'bgp' || layerFilter === 'ospf' || layerFilter === 'overlay') {
      const protocolKey = layerFilter === 'bgp' ? 'bgp' : (layerFilter === 'ospf' ? 'ospf' : 'overlay');
      const protocolNodeIds = new Set();
      for (const link of filteredLinks) {
        protocolNodeIds.add(String(link.source));
        protocolNodeIds.add(String(link.target));
      }

      filteredNodes = filteredNodes.filter((node) => {
        const peerCount = protocolKey === 'overlay'
          ? Number(node?.overlay?.peer_counts?.total || 0)
          : Number(node?.l3?.peer_counts?.[protocolKey] || 0);
        return protocolNodeIds.has(String(node.id)) || peerCount > 0;
      });

      const scopedNodeIds = new Set(filteredNodes.map((n) => String(n.id)));
      filteredLinks = filteredLinks.filter((l) => scopedNodeIds.has(String(l.source)) && scopedNodeIds.has(String(l.target)));
    }

    const orgEnabled = !!(cloudOrgFilter?.enabled && String(cloudOrgFilter?.org || '').trim());
    const orgValue = orgEnabled ? String(cloudOrgFilter.org).trim() : '';
    const orgMatchedCloudIds = new Set();
    if (orgEnabled) {
      for (const n of filteredNodes) {
        if (n?.role !== 'cloud') continue;
        const text = String(n?.cloud?.org_name || n?.cloud?.as_name || n?.evidence?.org_name || n?.evidence?.as_name || '').trim();
        if (text && text === orgValue) orgMatchedCloudIds.add(String(n.id));
      }
    }
    const orgConnectedIds = new Set(orgMatchedCloudIds);
    if (orgEnabled && orgMatchedCloudIds.size > 0) {
      for (const l of filteredLinks) {
        const proto = String(l.protocol || '').toUpperCase();
        const isL3 = String(l?.layer || '').trim().toLowerCase() === 'l3' || proto === 'BGP' || proto === 'OSPF';
        if (!isL3) continue;
        const s = String(l.source);
        const t = String(l.target);
        if (orgMatchedCloudIds.has(s)) orgConnectedIds.add(t);
        else if (orgMatchedCloudIds.has(t)) orgConnectedIds.add(s);
      }
    }

    const nodeOverridesMap = layoutNodeOverrides && typeof layoutNodeOverrides === 'object' ? layoutNodeOverrides : {};
    filteredNodes = filteredNodes.map((node) => {
      const override = nodeOverridesMap[String(node?.id || '')];
      if (!override || typeof override !== 'object') return node;
      const nextLabel = String(override.label || '').trim();
      const nextIconRole = String(override.iconRole || '').trim();
      return {
        ...node,
        label: nextLabel || node.label,
        manual_icon_role: nextIconRole || node.manual_icon_role || '',
        original_label: node.original_label || node.label,
        editor_font_size: clampNumber(override.fontSize, 11, 22, null),
        editor_wrap_mode: String(override.wrapMode || '').trim().toLowerCase() === 'single' ? 'single' : 'wrap',
      };
    });

    const pathNodeIds = new Set(pathResult?.path?.map(n => String(n.id)) || []);
    const pathOrderById = new Map();
    (pathResult?.path || []).forEach((n, idx) => {
      pathOrderById.set(String(n.id), idx);
    });
    const activeFromId = (pathActiveEdgeIndex != null && pathResult?.path?.[pathActiveEdgeIndex])
      ? String(pathResult.path[pathActiveEdgeIndex].id)
      : null;
    const activeToId = (pathActiveEdgeIndex != null && pathResult?.path?.[pathActiveEdgeIndex + 1])
      ? String(pathResult.path[pathActiveEdgeIndex + 1].id)
      : null;

    // B. Transform Nodes
    const flowNodes = filteredNodes.map((d) => {
      const isPathNode = pathNodeIds.has(String(d.id));
      const isDimmed = pathResult && !isPathNode;
      const hopIndex = isPathNode ? pathOrderById.get(String(d.id)) : null;
      const isActivePathNode = isPathNode && (String(d.id) === activeFromId || String(d.id) === activeToId);
      const isCloud = d.role === 'cloud';
      const orgText = String(d?.cloud?.org_name || d?.cloud?.as_name || d?.evidence?.org_name || d?.evidence?.as_name || '').trim();
      const isOrgMatch = orgEnabled ? (isCloud && orgText && orgText === orgValue) : false;
      const isOrgConnected = orgEnabled ? (!isCloud && orgConnectedIds.has(String(d.id))) : false;
      const isOrgDimmed = orgEnabled ? (isCloud ? !isOrgMatch : !isOrgConnected) : false;

      // Metrics extraction
      const healthScore = d.metrics?.health_score ?? 100;
      const cpu = d.metrics?.cpu || 0;
      const memory = d.metrics?.memory || 0;
      const isWLC = d.role === 'wlc';
      const totalAps = d.metrics?.total_aps || 0;
      const downAps = d.metrics?.down_aps || 0;
      const clients = d.metrics?.clients || 0;
      const trafficIn = d.metrics?.traffic_in || 0;
      const trafficOut = d.metrics?.traffic_out || 0;
      const modelText = String(d.model || '').trim();
      const showModel = !!modelText && !modelText.toLowerCase().includes('unknown');
      const l3Meta = d?.l3 && typeof d.l3 === 'object' ? d.l3 : null;
      const l3PeerTotal = Number(l3Meta?.peer_counts?.total || 0);
      const l3BgpPeers = Number(l3Meta?.peer_counts?.bgp || 0);
      const l3OspfPeers = Number(l3Meta?.peer_counts?.ospf || 0);
      const l3Healthy = Number(l3Meta?.state_counts?.healthy || 0);
      const l3Degraded = Number(l3Meta?.state_counts?.degraded || 0);
      const l3LocalAsns = Array.isArray(l3Meta?.local_asns) ? l3Meta.local_asns.filter((asn) => Number.isFinite(Number(asn))) : [];
      const l3PrimaryAs = l3LocalAsns.length === 1 ? `AS${l3LocalAsns[0]}` : (l3LocalAsns.length > 1 ? `AS x${l3LocalAsns.length}` : '');
      const showL3Badges = layerFilter !== 'l2' && l3PeerTotal > 0;
      const overlayMeta = d?.overlay && typeof d.overlay === 'object' ? d.overlay : null;
      const overlayPeerTotal = Number(overlayMeta?.peer_counts?.total || 0);
      const overlayEvpnPeers = Number(overlayMeta?.peer_counts?.evpn || 0);
      const overlayHealthy = Number(overlayMeta?.state_counts?.healthy || 0);
      const overlayDegraded = Number(overlayMeta?.state_counts?.degraded || 0);
      const overlayVniTotal = Number(overlayMeta?.vni_counts?.total || 0);
      const overlayL2Vni = Number(overlayMeta?.vni_counts?.l2 || 0);
      const overlayL3Vni = Number(overlayMeta?.vni_counts?.l3 || 0);
      const overlayVteps = Array.isArray(overlayMeta?.local_vtep_ips) ? overlayMeta.local_vtep_ips.filter(Boolean) : [];
      const overlayTransports = Array.isArray(overlayMeta?.transports) ? overlayMeta.transports.filter(Boolean) : [];
      const overlayPrimaryVtep = overlayVteps.length === 1
        ? overlayVteps[0]
        : (overlayVteps.length > 1 ? `VTEP x${overlayVteps.length}` : '');
      const overlayTransportLabel = overlayTransports.length > 0 ? overlayTransports[0] : '';
      const showOverlayBadges = layerFilter !== 'l2' && overlayPeerTotal > 0;
      const hybridMeta = d?.hybrid && typeof d.hybrid === 'object' ? d.hybrid : null;
      const hybridLinkTotal = Number(hybridMeta?.hybrid_links || 0);
      const hybridPeerLinks = Number(hybridMeta?.peer_links || 0);
      const hybridInventoryLinks = Number(hybridMeta?.inventory_links || 0);
      const hybridProviders = Array.isArray(hybridMeta?.providers) ? hybridMeta.providers.filter(Boolean) : [];
      const hybridAccounts = Array.isArray(hybridMeta?.account_names) ? hybridMeta.account_names.filter(Boolean) : [];
      const hybridRegions = Array.isArray(hybridMeta?.regions) ? hybridMeta.regions.filter(Boolean) : [];
      const hybridPrimaryProvider = hybridProviders.length > 0 ? String(hybridProviders[0]).toUpperCase() : '';
      const hybridKind = String(hybridMeta?.kind || '').trim().toLowerCase();
      const hybridKindLabel = hybridKind
        ? (hybridKind === 'virtual_peer'
          ? 'Peer'
          : (hybridKind === 'inventory_resource' ? 'Inventory' : hybridKind.replace(/_/g, ' ')))
        : '';
      const showHybridBadges = layerFilter === 'hybrid' || hybridLinkTotal > 0 || d.role === 'cloud';
      const effectiveLabel = String(d.label || '').trim() || String(d.original_label || d.id || '');
      const effectiveIconRole = String(d.manual_icon_role || '').trim() || d.role;
      const nodeEditorMetrics = computeNodeEditorMetrics({
        role: d.role,
        label: effectiveLabel,
        fontSize: d.editor_font_size,
        wrapMode: d.editor_wrap_mode,
      });
      const titleFontSize = nodeEditorMetrics.fontSize + 2;
      const bodyFontSize = Math.max(11, nodeEditorMetrics.fontSize);
      const metaFontSize = Math.max(10, nodeEditorMetrics.fontSize - 1);
      const badgeFontSize = Math.max(10, nodeEditorMetrics.fontSize - 2);
      const compactWrap = nodeEditorMetrics.wrapMode === 'single';
      const cloudProvider = String(d?.cloud?.provider || '').trim();
      const cloudRegion = String(d?.cloud?.region || '').trim();
      const cloudAccountId = d?.cloud?.account_id != null ? String(d.cloud.account_id).trim() : '';
      const cloudResourceType = formatCloudResourceType(d?.cloud?.resource_type_label || d?.cloud?.resource_type);
      const cloudResourceTypeRaw = String(d?.cloud?.resource_type || d?.cloud?.resource_type_label || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
      const cloudAccountName = String(d?.cloud?.account_name || '').trim();
      const cloudResourceId = String(d?.cloud?.resource_id || '').trim();
      const cloudProviderLabel = (cloudProvider || 'cloud').toUpperCase();
      const cloudAsn = d?.cloud?.asn ? `AS${d.cloud.asn}` : '';
      const cloudOrg = String(d?.cloud?.org_name || d?.cloud?.as_name || '').trim();
      const cloudBadgeText = [cloudProviderLabel, cloudRegion, cloudResourceType].filter(Boolean).join(' · ');
      const cloudTitle = [cloudProviderLabel, cloudRegion, cloudResourceType, cloudResourceId, cloudAsn, cloudOrg].filter(Boolean).join(' · ');

      // Dynamic metric based on user selection
      let metricValue, metricLabel, isHighBad;
      if (healthMetric === 'cpu') {
        metricValue = cpu;
        metricLabel = 'CPU';
        isHighBad = true; // High CPU = bad
      } else if (healthMetric === 'memory') {
        metricValue = memory;
        metricLabel = 'Memory';
        isHighBad = true; // High Memory = bad
      } else {
        metricValue = healthScore;
        metricLabel = 'Health';
        isHighBad = false; // Low Health Score = bad
      }

      const cloudStatusMeta = d.role === 'cloud'
        ? getCloudResourceStatusMeta(d.status, d?.cloud?.resource_type)
        : null;
      const deviceStatusMeta = d.role === 'cloud'
        ? null
        : getManagedDeviceStatusMeta(d.status, d.management_state);
      const isDiscoveredOnly = d.role !== 'cloud' && String(d?.management_state || '').trim().toLowerCase() === 'discovered_only';
      const topologyDeviceId = String(d?.device_id ?? d?.id ?? '').trim();
      const topologyCloudResourceId = String(d?.cloud?.resource_id || '').trim();
      const topologyCloudDbId = String(d?.cloud?.cloud_resource_id ?? '').trim();
      const serviceOverlayActive = serviceOverlayEnabled && !!selectedServiceGroupDetail;
      const isServiceOverlayNode = serviceOverlayActive && (
        (d.role === 'cloud'
          ? (
            (topologyCloudDbId && serviceOverlayMemberSets.cloudResourceDbIds.has(topologyCloudDbId))
            || (topologyCloudResourceId && serviceOverlayMemberSets.cloudResourceIds.has(topologyCloudResourceId))
          )
          : (topologyDeviceId && serviceOverlayMemberSets.deviceIds.has(topologyDeviceId)))
      );
      const isServiceOverlayDimmed = serviceOverlayActive && !isServiceOverlayNode;
      const impactResourceTypeMatch = impactCloudResourceTypes.length === 0
        ? true
        : impactCloudResourceTypes.some((row) => row === cloudResourceTypeRaw);
      const impactProviderMatch = cloudProviderFilter === 'all' || String(cloudProvider || '').trim().toLowerCase() === String(cloudProviderFilter || '').trim().toLowerCase();
      const impactAccountMatch = cloudAccountFilter === 'all' || cloudAccountId === String(cloudAccountFilter || '').trim();
      const impactRegionMatch = cloudRegionFilter === 'all' || cloudRegion === String(cloudRegionFilter || '').trim();
      const isIntentImpactNode = cloudIntentImpactActive && d.role === 'cloud' && impactProviderMatch && impactAccountMatch && impactRegionMatch && impactResourceTypeMatch;
      const online = cloudStatusMeta ? cloudStatusMeta.active : isDeviceOnline(d.status);
      const statusMeta = cloudStatusMeta || deviceStatusMeta;
      const statusChipClass = statusMeta?.chipClass || '';
      const statusDotClass = statusMeta?.dotClass || '';
      const statusLabel = statusMeta?.label || (online ? 'ONLINE' : 'OFFLINE');
      let healthColor = 'bg-green-100 text-green-600';
      let healthBorder = '2px solid #10b981';
      let healthBg = '#fff';

      // Color logic based on metric type
      const isBad = isHighBad ? metricValue >= 80 : metricValue < 50;
      const isWarning = isHighBad ? (metricValue >= 50 && metricValue < 80) : (metricValue >= 50 && metricValue < 80);

      if (isDiscoveredOnly) {
        healthColor = 'bg-slate-100 text-slate-500';
        healthBorder = '2px dashed #94a3b8';
        healthBg = '#f8fafc';
      } else if (!online) {
        healthColor = 'bg-gray-100 text-gray-400';
        healthBorder = '2px solid #9ca3af';
      } else if (showHealth) {
        if (isBad) {
          healthColor = 'bg-red-100 text-red-600 animate-pulse';
          healthBorder = '2px solid #ef4444';
          healthBg = '#fef2f2';
        } else if (isWarning) {
          healthColor = 'bg-yellow-100 text-yellow-600';
          healthBorder = '2px solid #f59e0b';
          healthBg = '#fffbeb';
        } else {
          healthColor = 'bg-green-100 text-green-600';
          healthBorder = '2px solid #10b981';
          healthBg = '#ecfdf5';
        }
      } else {
        // Standard Role-based Border
        if (d.role === 'core') healthBorder = '2px solid #3b82f6';
        else if (d.role === 'wlc') healthBorder = '2px solid #9333ea';
        else if (d.role === 'security') healthBorder = '2px solid #ef4444';
        else if (d.role === 'distribution') healthBorder = '2px solid #06b6d4';
        else if (d.role === 'access_domestic') healthBorder = '2px solid #f59e0b';
        else if (d.role === 'cloud') healthBorder = '2px solid #0ea5e9';
        if (layerFilter === 'l3' && l3PeerTotal > 0) healthBorder = '2px solid #7c3aed';
        if (layerFilter === 'overlay' && overlayPeerTotal > 0) healthBorder = '2px solid #06b6d4';
        if (layerFilter === 'hybrid' && (d.role === 'cloud' || hybridLinkTotal > 0)) healthBorder = '2px solid #0284c7';

        // Standard Role-based BG
        if (d.role === 'core') healthBg = '#eff6ff';
        else if (d.role === 'wlc') healthBg = '#fdf4ff';
        else if (d.role === 'security') healthBg = '#fff1f2';
        else if (d.role === 'distribution') healthBg = '#ecfeff';
        else if (d.role === 'access_domestic') healthBg = '#fffbeb';
        else if (d.role === 'cloud') healthBg = '#f0f9ff';
        if (layerFilter === 'l3' && l3PeerTotal > 0) healthBg = '#faf5ff';
        if (layerFilter === 'overlay' && overlayPeerTotal > 0) healthBg = '#ecfeff';
        if (layerFilter === 'hybrid' && (d.role === 'cloud' || hybridLinkTotal > 0)) healthBg = '#eff6ff';
      }

      if (isIntentImpactNode) {
        healthBorder = '3px solid #8b5cf6';
        healthBg = '#faf5ff';
      } else if (isServiceOverlayNode) {
        healthBorder = `3px solid ${serviceOverlayColor}`;
        healthBg = `${String(serviceOverlayColor)}12`;
      }

      // Badge color based on metric
      const getBadgeClass = () => {
        if (isBad) return 'bg-red-500 text-white';
        if (isWarning) return 'bg-yellow-400 text-white';
        return 'bg-green-500 text-white';
      };

      return {
        id: String(d.id),
        site_id: d.site_id, // For ELK grouping
        site_name: d.site_name,
        tier: d.tier,
      data: {
        label: (
            <div className="flex h-full w-full min-w-0 flex-col items-center justify-center gap-1 px-2 py-1.5">
              <div className={`mb-1 rounded-full p-1.5 ${healthColor} ${isPathNode ? 'ring-2 ring-green-500 ring-offset-2' : ''}`}>
                {getIconByRole(effectiveIconRole)}
              </div>
              <div
                className="w-full text-center font-bold text-gray-800"
                style={{
                  fontSize: `${titleFontSize}px`,
                  lineHeight: 1.15,
                  display: '-webkit-box',
                  WebkitBoxOrient: 'vertical',
                  WebkitLineClamp: compactWrap ? 1 : 2,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: compactWrap ? 'nowrap' : 'normal',
                  wordBreak: 'break-word',
                }}
                title={effectiveLabel}
              >
                {effectiveLabel}
              </div>
              <div
                className="w-full truncate text-center font-mono text-gray-500"
                style={{ fontSize: `${metaFontSize}px` }}
                title={d.ip}
              >
                {d.ip}
              </div>
              <div className={`mb-1 inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 font-semibold ${statusChipClass}`} style={{ fontSize: `${badgeFontSize}px` }}>
                <span className={`h-2 w-2 rounded-full ${statusDotClass}`}></span>
                {statusLabel}
              </div>
              {d.role !== 'cloud' && (
                <div
                  className={`max-w-full rounded-full border px-2 py-0.5 text-center font-semibold truncate ${
                    isDiscoveredOnly
                      ? 'border-slate-200 bg-slate-50 text-slate-700'
                      : 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  }`}
                  style={{ fontSize: `${badgeFontSize}px` }}
                  title={isDiscoveredOnly ? t('devices_filter_discovered_only', 'Discovered Only') : t('devices_filter_managed', 'Managed')}
                >
                  {isDiscoveredOnly ? t('devices_filter_discovered_only', 'Discovered Only') : t('devices_filter_managed', 'Managed')}
                </div>
              )}
              {d.role === 'cloud' && (
                <div
                  className={`max-w-full rounded-full px-2 py-0.5 text-center font-semibold truncate ${isIntentImpactNode ? 'bg-violet-100 text-violet-700' : 'bg-sky-50 text-sky-700'}`}
                  style={{ fontSize: `${badgeFontSize}px` }}
                  title={cloudTitle}
                >
                  {cloudBadgeText}
                </div>
              )}
              {isIntentImpactNode && (
                <div
                  className="max-w-full rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-center font-semibold text-violet-700 truncate"
                  style={{ fontSize: `${badgeFontSize}px` }}
                  title={t('topology_intent_impact_title', 'Cloud Intent Impact Mode')}
                >
                  {t('topology_intent_impact_badge', 'INTENT IMPACT')}
                </div>
              )}
              {isServiceOverlayNode && (
                <div
                  className="max-w-full rounded-full border px-2 py-0.5 text-center font-semibold truncate"
                  style={{
                    fontSize: `${badgeFontSize}px`,
                    borderColor: serviceOverlayColor,
                    color: serviceOverlayColor,
                    background: `${String(serviceOverlayColor)}18`,
                  }}
                  title={selectedServiceGroupDetail?.name || t('topology_service_overlay_badge', 'SERVICE')}
                >
                  {t('topology_service_overlay_badge', 'SERVICE')}
                </div>
              )}
              {d.role === 'cloud' && cloudAccountName && (
                <div
                  className="max-w-full rounded-full border border-slate-200 bg-white px-2 py-0.5 text-center font-semibold text-slate-600 truncate"
                  style={{ fontSize: `${badgeFontSize}px` }}
                  title={cloudAccountName}
                >
                  {cloudAccountName}
                </div>
              )}
              {showModel && d.role !== 'cloud' && (
                <div className="max-w-full truncate text-center font-mono text-gray-600" style={{ fontSize: `${metaFontSize}px` }} title={modelText}>
                  {modelText}
                </div>
              )}

              {showL3Badges && (
                <div className="mt-1 flex w-full flex-wrap items-center justify-center gap-1">
                  {!!l3PrimaryAs && (
                    <div className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-violet-100 text-violet-700">
                      {l3PrimaryAs}
                    </div>
                  )}
                  <div className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${l3Degraded > 0 ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
                    L3 {l3Healthy}/{l3PeerTotal}
                  </div>
                </div>
              )}

              {showOverlayBadges && (
                <div className="mt-1 flex w-full flex-wrap items-center justify-center gap-1">
                  {!!overlayTransportLabel && (
                    <div className="text-[10px] px-2 py-0.5 rounded-full font-semibold bg-cyan-50 text-cyan-700">
                      {overlayTransportLabel}
                    </div>
                  )}
                  <div className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${overlayDegraded > 0 ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
                    VX {overlayHealthy}/{overlayPeerTotal}
                  </div>
                  {(overlayL2Vni > 0 || overlayL3Vni > 0) && (
                    <div className="text-[10px] px-2 py-0.5 rounded-full font-semibold bg-slate-100 text-slate-700">
                      {overlayL2Vni}/{overlayL3Vni}
                    </div>
                  )}
                </div>
              )}

              {showHybridBadges && (
                <div className="mt-1 flex w-full flex-wrap items-center justify-center gap-1">
                  {!!hybridKindLabel && (
                    <div className="text-[10px] px-2 py-0.5 rounded-full font-semibold bg-sky-100 text-sky-700">
                      {hybridKindLabel}
                    </div>
                  )}
                  {hybridLinkTotal > 0 && (
                    <div className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-blue-100 text-blue-700">
                      HY {hybridLinkTotal}
                    </div>
                  )}
                  {!!hybridPrimaryProvider && (
                    <div className="text-[10px] px-2 py-0.5 rounded-full font-semibold bg-slate-100 text-slate-700">
                      {hybridPrimaryProvider}
                    </div>
                  )}
                </div>
              )}

              {trafficFlowEnabled && online && (
                <div className="flex items-center gap-1 text-[10px] font-semibold text-gray-600">
                  <span className="px-2 py-0.5 rounded-full bg-sky-50 text-sky-700">IN {formatBps(trafficIn)}</span>
                  <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">OUT {formatBps(trafficOut)}</span>
                </div>
              )}

              {showHealth && online && (
                <div className="flex flex-col items-center gap-1">
                  <div className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${getBadgeClass()}`}>
                    {metricLabel}: {metricValue}%
                  </div>
                  {isWLC && totalAps > 0 && (
                    <div className={`text-[9px] px-2 py-0.5 rounded-full font-medium ${downAps > 0 ? 'bg-orange-100 text-orange-700' : 'bg-purple-100 text-purple-700'}`}>
                      AP: {totalAps - downAps}/{totalAps} · {clients} clients
                    </div>
                  )}
                </div>
              )}

              {isPathNode && (
                <div className="mt-1 flex items-center gap-1">
                  <div className={`text-[10px] text-white px-2 py-0.5 rounded-full ${isActivePathNode ? 'bg-emerald-600 animate-pulse' : 'bg-green-500'}`}>
                    Hop {Number.isFinite(Number(hopIndex)) ? (Number(hopIndex) + 1) : '?'}
                  </div>
                </div>
              )}
            </div>
          ),
          tier: d.tier,
          role: d.role,
          status: d.status,
          site_id: d.site_id,
          site_name: d.site_name,
          device_id: d.device_id,
          port: d.port,
          node_label: effectiveLabel,
          original_node_label: d.original_label || d.label,
          icon_role: effectiveIconRole,
          ip: d.ip,
          vendor: d.vendor,
          model: d.model,
          version: d.version,
          metrics: d.metrics,
          l3: l3Meta,
          overlay: overlayMeta,
          hybrid: hybridMeta,
          cloud: d.cloud,
          evidence: d.evidence,
          intentImpact: isIntentImpactNode,
          serviceOverlayMatch: isServiceOverlayNode,
          serviceGroupName: isServiceOverlayNode ? String(selectedServiceGroupDetail?.name || '') : '',
          serviceGroupId: isServiceOverlayNode ? String(selectedServiceGroupDetail?.id || '') : '',
          serviceGroupColor: isServiceOverlayNode ? serviceOverlayColor : '',
          editorResizable: manualEditMode,
          editorMinWidth: nodeEditorMetrics.minWidth,
          editorMinHeight: nodeEditorMetrics.minHeight,
        },
        type: 'topologyNode',
        position: { x: 0, y: 0 },
        style: {
          background: healthBg,
          border: isActivePathNode
            ? '4px solid #22c55e'
            : (isOrgMatch || isOrgConnected ? '4px solid #f59e0b' : (isPathNode ? '3px solid #10b981' : healthBorder)),
          borderRadius: '12px',
          padding: 5,
          boxShadow: isActivePathNode ? '0 0 22px rgba(34, 197, 94, 0.55)' : (isPathNode ? '0 0 15px rgba(16, 185, 129, 0.4)' : '0 4px 6px -1px rgba(0, 0, 0, 0.1)'),
          cursor: 'pointer',
          fontSize: `${bodyFontSize}px`,
          minWidth: nodeEditorMetrics.minWidth,
          minHeight: nodeEditorMetrics.minHeight,
          opacity: isOrgDimmed ? 0.12 : (isServiceOverlayDimmed ? 0.18 : (isDimmed ? 0.3 : 1)),
          zIndex: isActivePathNode ? 12 : (isServiceOverlayNode ? 11 : ((isOrgMatch || isOrgConnected) ? 11 : (isPathNode ? 10 : 1)))
        },
      };
    });

    const nodeTrafficById = new Map();
    for (const n of filteredNodes) {
      const id = String(n.id);
      nodeTrafficById.set(id, {
        in_bps: n.metrics?.traffic_in || 0,
        out_bps: n.metrics?.traffic_out || 0
      });
    }
    const impactNodeIds = new Set(
      flowNodes
        .filter((node) => !!node?.data?.intentImpact)
        .map((node) => String(node.id)),
    );
    const serviceOverlayNodeIds = new Set(
      flowNodes
        .filter((node) => !!node?.data?.serviceOverlayMatch)
        .map((node) => String(node.id)),
    );

    // D. Build Edges (with Path logic)
    const flowEdges = aggregateLinks(filteredLinks, pathResult, {
      trafficFlowEnabled,
      nodeTrafficById,
      pathPlayback: { activeEdgeIndex: pathActiveEdgeIndex },
      pathBadgesEnabled,
      maxEdgeLabelLen: pathEdgeLabelMaxLen,
      labelTruncateMode: pathEdgeLabelTruncateMode,
      highlightLink: highlightedLink,
      formatBps,
      truncateLabel,
    });
    const styledEdges = orgEnabled && orgMatchedCloudIds.size > 0
      ? flowEdges.map((e) => {
        const proto = String(e?.data?.protocol || '').toUpperCase();
        const isL3 = String(e?.data?.layer || '').trim().toLowerCase() === 'l3' || proto === 'BGP' || proto === 'OSPF';
        const s = String(e.source);
        const t = String(e.target);
        const hits = isL3 && (orgMatchedCloudIds.has(s) || orgMatchedCloudIds.has(t));
        if (hits) {
          return {
            ...e,
            style: { ...(e.style || {}), stroke: '#f59e0b', strokeWidth: Math.max(3, Number(e.style?.strokeWidth || 2)), opacity: 1 },
            markerEnd: { type: MarkerType.ArrowClosed, color: '#f59e0b' },
            markerStart: e.markerStart ? { ...e.markerStart, color: '#f59e0b' } : e.markerStart,
            zIndex: Math.max(Number(e.zIndex || 0), 20),
          };
        }
        const baseOpacity = Number(e.style?.opacity ?? 1);
        const nextOpacity = Math.max(0.05, Math.min(1, baseOpacity * 0.12));
        return { ...e, style: { ...(e.style || {}), opacity: nextOpacity }, labelStyle: { ...(e.labelStyle || {}), opacity: Math.max(0.05, (e.labelStyle?.opacity ?? 1) * 0.12) } };
      })
      : flowEdges;
    const impactStyledEdges = cloudIntentImpactActive && impactNodeIds.size > 0
      ? styledEdges.map((edge) => {
          const sourceHit = impactNodeIds.has(String(edge?.source || ''));
          const targetHit = impactNodeIds.has(String(edge?.target || ''));
          if (!sourceHit && !targetHit) return edge;
          const isFullImpact = sourceHit && targetHit;
          const impactStroke = isFullImpact ? '#8b5cf6' : '#a78bfa';
          return {
            ...edge,
            data: {
              ...(edge.data || {}),
              intentImpact: true,
              intentImpactStrength: isFullImpact ? 'full' : 'partial',
            },
            style: {
              ...(edge.style || {}),
              stroke: impactStroke,
              strokeWidth: Math.max(isFullImpact ? 4 : 3, Number(edge?.style?.strokeWidth || 2)),
              opacity: 1,
            },
            labelStyle: {
              ...(edge.labelStyle || {}),
              fill: impactStroke,
              opacity: 1,
              fontWeight: isFullImpact ? 800 : (edge?.labelStyle?.fontWeight || 700),
            },
            markerEnd: edge?.markerEnd ? { ...edge.markerEnd, color: impactStroke } : edge.markerEnd,
            markerStart: edge?.markerStart ? { ...edge.markerStart, color: impactStroke } : edge.markerStart,
            zIndex: Math.max(Number(edge?.zIndex || 0), isFullImpact ? 22 : 19),
          };
        })
      : styledEdges;
    const serviceOverlayStyledEdges = serviceOverlayEnabled && selectedServiceGroupDetail && serviceOverlayNodeIds.size > 0
      ? impactStyledEdges.map((edge) => {
          if (edge?.data?.intentImpact) return edge;
          const sourceHit = serviceOverlayNodeIds.has(String(edge?.source || ''));
          const targetHit = serviceOverlayNodeIds.has(String(edge?.target || ''));
          if (!sourceHit && !targetHit) {
            return {
              ...edge,
              style: {
                ...(edge.style || {}),
                opacity: Math.max(0.08, Number(edge?.style?.opacity ?? 1) * 0.18),
              },
              labelStyle: {
                ...(edge.labelStyle || {}),
                opacity: Math.max(0.08, Number(edge?.labelStyle?.opacity ?? 1) * 0.18),
              },
            };
          }
          const overlayStroke = serviceOverlayColor;
          const isFullServiceEdge = sourceHit && targetHit;
          return {
            ...edge,
            data: {
              ...(edge.data || {}),
              serviceOverlay: true,
              serviceOverlayStrength: isFullServiceEdge ? 'full' : 'boundary',
            },
            style: {
              ...(edge.style || {}),
              stroke: overlayStroke,
              strokeWidth: Math.max(isFullServiceEdge ? 4 : 3, Number(edge?.style?.strokeWidth || 2)),
              opacity: 1,
            },
            labelStyle: {
              ...(edge.labelStyle || {}),
              fill: overlayStroke,
              opacity: 1,
              fontWeight: isFullServiceEdge ? 800 : (edge?.labelStyle?.fontWeight || 700),
            },
            markerEnd: edge?.markerEnd ? { ...edge.markerEnd, color: overlayStroke } : edge.markerEnd,
            markerStart: edge?.markerStart ? { ...edge.markerStart, color: overlayStroke } : edge.markerStart,
            zIndex: Math.max(Number(edge?.zIndex || 0), isFullServiceEdge ? 18 : 16),
          };
        })
      : impactStyledEdges;

    const hiddenEdgeKeys = new Set(Array.isArray(layoutHiddenEdgeKeys) ? layoutHiddenEdgeKeys : []);
    const edgeOverrideMap = layoutEdgeOverrides && typeof layoutEdgeOverrides === 'object' ? layoutEdgeOverrides : {};
    const autoEdgePairMap = new Map();
    for (const edge of serviceOverlayStyledEdges) {
      const pairKey = buildEdgePairKey(edge?.source, edge?.target);
      if (!autoEdgePairMap.has(pairKey)) autoEdgePairMap.set(pairKey, []);
      autoEdgePairMap.get(pairKey).push(edge);
    }
    let finalEdges = serviceOverlayStyledEdges
      .filter((edge) => !hiddenEdgeKeys.has(buildTopologyEdgeKey(edge)))
      .map((edge) => {
        const edgeKey = buildTopologyEdgeKey(edge);
        const override = edgeOverrideMap[edgeKey];
        if (!override || typeof override !== 'object') return edge;
        const nextLabel = String(override.label || '').trim() || edge.label;
        const nextStroke = String(override.color || '').trim() || edge?.style?.stroke;
        const nextStrokeWidth = Number(override.width || 0) || edge?.style?.strokeWidth;
        const nextDash = buildLineDash(override.lineStyle) || edge?.style?.strokeDasharray;
        const nextCurve = String(override.curve || edge.type || edge?.data?.renderCurve || 'default').trim().toLowerCase() || 'default';
        const nextLabelPosition = clampNumber(override.labelPosition, 10, 90, clampNumber(edge?.data?.labelPosition, 10, 90, 50));
        const nextLabelOffsetY = clampNumber(override.labelOffsetY, -80, 80, clampNumber(edge?.data?.labelOffsetY, -80, 80, 0));
        return {
          ...edge,
          label: nextLabel || edge.label,
          type: nextCurve,
          data: {
            ...(edge.data || {}),
            fullLabel: nextLabel || edge?.data?.fullLabel || edge.label,
            renderCurve: nextCurve,
            labelPosition: nextLabelPosition,
            labelOffsetY: nextLabelOffsetY,
          },
          style: {
            ...(edge.style || {}),
            ...(nextStroke ? { stroke: nextStroke } : {}),
            ...(nextStrokeWidth ? { strokeWidth: nextStrokeWidth } : {}),
            ...(nextDash ? { strokeDasharray: nextDash } : {}),
          },
          labelStyle: {
            ...(edge.labelStyle || {}),
            ...(nextStroke ? { fill: nextStroke } : {}),
          },
          markerEnd: edge?.markerEnd
            ? {
                ...edge.markerEnd,
                ...(nextStroke ? { color: nextStroke } : {}),
              }
            : edge.markerEnd,
        };
      });

    if (Array.isArray(layoutManualEdges) && layoutManualEdges.length > 0) {
      const visibleNodeIds = new Set(flowNodes.map((node) => String(node.id)));
      const renderedManualEdges = layoutManualEdges
        .filter((edge) => visibleNodeIds.has(String(edge?.source || '')) && visibleNodeIds.has(String(edge?.target || '')))
        .map((edge) => {
          const pairKey = buildEdgePairKey(edge?.source, edge?.target);
          const warningMeta = buildManualWarningMeta(edge, autoEdgePairMap.get(pairKey) || []);
          return buildManualTopologyEdge(edge, edgeOverrideMap[String(edge?.id || '')], warningMeta);
        });
      finalEdges = [...finalEdges, ...renderedManualEdges];
    }

    finalEdges = finalEdges.map((edge) => {
      const renderCurve = String(edge?.data?.renderCurve || edge?.type || 'default').trim().toLowerCase() || 'default';
      return {
        ...edge,
        data: {
          ...(edge.data || {}),
          renderCurve,
          labelPosition: clampNumber(edge?.data?.labelPosition, 10, 90, 50),
          labelOffsetY: clampNumber(edge?.data?.labelOffsetY, -80, 80, 0),
        },
      };
    });

    // E. Apply Layout
    // E. Apply Layout (Async ELK)
    const runLayout = async () => {
      if (flowNodes.length === 0) {
        setNodes([]);
        setEdges([]);
        return;
      }

      const savedNodes = Array.isArray(layoutNodesSnapshot) ? layoutNodesSnapshot : [];
      if (savedNodes.length > 0) {
        const liveDataMap = new Map(flowNodes.map((n) => [String(n.id), n]));
        const savedNodeIds = new Set(
          savedNodes
            .map((n) => String(n?.id || ''))
            .filter((id) => !!id),
        );

        const mergedNodes = savedNodes.map((savedNode) => {
          const liveNode = liveDataMap.get(String(savedNode?.id || ''));
          const manualSized = !!savedNode?.data?.manualSized;
          const editorSizePinned = !!savedNode?.data?.editorSizePinned || !!liveNode?.data?.editorSizePinned;
          if (liveNode) {
            const mergedNode = {
              ...savedNode,
              type: savedNode?.type === 'groupNode' ? 'groupNode' : (liveNode.type || savedNode?.type),
              draggable: typeof liveNode?.draggable === 'boolean' ? liveNode.draggable : (typeof savedNode?.draggable === 'boolean' ? savedNode.draggable : true),
              selectable: typeof liveNode?.selectable === 'boolean' ? liveNode.selectable : (typeof savedNode?.selectable === 'boolean' ? savedNode.selectable : true),
              data: {
                ...(savedNode?.data || {}),
                ...(liveNode.data || {}),
                manualSized,
                editorSizePinned,
                onResizeNode: handleGroupResize,
              },
              style: {
                ...(savedNode?.style || {}),
                ...(savedNode?.type === 'groupNode' ? {} : liveNode.style),
              },
            };
            if (!manualSized) {
              delete mergedNode.width;
              delete mergedNode.height;
              if (mergedNode.style && typeof mergedNode.style === 'object') {
                delete mergedNode.style.width;
                delete mergedNode.style.height;
              }
            }
            return mergedNode;
          }
          if (savedNode?.type === 'groupNode') {
            const orphanGroupNode = {
              ...savedNode,
              draggable: true,
              selectable: true,
              data: {
                ...(savedNode?.data || {}),
                editorResizable: manualEditMode,
                editorSizePinned: !!savedNode?.data?.editorSizePinned,
                onResizeNode: handleGroupResize,
              },
            };
            if (!manualSized) {
              delete orphanGroupNode.width;
              delete orphanGroupNode.height;
              if (orphanGroupNode.style && typeof orphanGroupNode.style === 'object') {
                delete orphanGroupNode.style.width;
                delete orphanGroupNode.style.height;
              }
            }
            return orphanGroupNode;
          }
          return null;
        }).filter(Boolean);

        const missingLiveNodes = flowNodes.filter((liveNode) => !savedNodeIds.has(String(liveNode.id)));
        if (missingLiveNodes.length > 0) {
          const baseX = 120;
          const baseY = 120;
          const colSize = 260;
          const rowSize = 170;
          const cols = 4;
          missingLiveNodes.forEach((liveNode, idx) => {
            const x = baseX + (idx % cols) * colSize;
            const y = baseY + Math.floor(idx / cols) * rowSize;
            mergedNodes.push({
              ...liveNode,
              position: { x, y },
            });
          });
        }

        setNodes(mergedNodes);
        setEdges(finalEdges);
        return;
      }

      // 1. Create Group Nodes for Sites
      const siteGroups = new Map();
      const cloudProviderGroups = new Map();
      const cloudProviderStats = new Map();
      const cloudRegionGroups = new Map();
      const cloudRegionStats = new Map();
      const cloudProviderTheme = {
        aws: { bg: 'rgba(245, 158, 11, 0.10)', border: 'rgba(245, 158, 11, 0.70)', text: '#b45309' },
        azure: { bg: 'rgba(59, 130, 246, 0.10)', border: 'rgba(59, 130, 246, 0.70)', text: '#2563eb' },
        gcp: { bg: 'rgba(34, 197, 94, 0.10)', border: 'rgba(34, 197, 94, 0.70)', text: '#16a34a' },
        naver: { bg: 'rgba(132, 204, 22, 0.10)', border: 'rgba(132, 204, 22, 0.70)', text: '#4d7c0f' },
        inferred: { bg: 'rgba(148, 163, 184, 0.12)', border: 'rgba(148, 163, 184, 0.70)', text: '#94a3b8' },
        cloud: { bg: 'rgba(14, 165, 233, 0.08)', border: 'rgba(56, 189, 248, 0.65)', text: '#0ea5e9' },
      };

      // Clone nodes to avoid mutating state directly (good practice)
      const deviceNodes = flowNodes.map(node => ({ ...node }));

      deviceNodes.forEach(node => {
        const siteId = node.site_id || (node?.data?.role === 'cloud' ? 'cloud' : 'default_site');
        const groupId = `group-${siteId}`;

        if (!siteGroups.has(groupId)) {
          siteGroups.set(groupId, {
            id: groupId,
            type: 'groupNode', // Use custom Resizable Group Node
            data: {
              label: node.site_name || (siteId === 'cloud' ? 'Cloud' : siteId),
              labelWrapMode: 'wrap',
              editorResizable: manualEditMode,
              manualSized: false,
              editorSizePinned: false,
              onResizeNode: handleGroupResize,
            },
            position: { x: 0, y: 0 },
            style: {
              backgroundColor: 'rgba(240, 244, 255, 0.2)', // Very transparent
              border: '2px dashed rgba(148, 163, 184, 0.7)', // Slightly darker border for visibility
              borderRadius: '12px',
              padding: 20,
              width: 10,
              height: 10,
              zIndex: manualEditMode ? 40 : -100,
              pointerEvents: 'all',

              // Helper to position label at top
              display: 'flex',
              alignItems: 'flex-start', // Top alignment
              justifyContent: 'center',
              fontWeight: 'bold',
              color: '#475569', // Slate-600 (darker)
              fontSize: '16px', // Larger font
            },
            draggable: true,
            selectable: true, // Allow selection for resizing
          });
        }

        if (node?.data?.role === 'cloud') {
          const providerRaw = String(node?.data?.cloud?.provider || node?.data?.evidence?.provider || 'cloud').trim();
          const provider = providerRaw ? providerRaw.toLowerCase() : 'cloud';
          const providerGroupId = `group-cloud-${provider}`;
          const asnRaw = node?.data?.cloud?.asn || node?.data?.evidence?.asn || null;
          const asn = asnRaw != null && String(asnRaw).trim() ? String(asnRaw).trim() : null;
          const regionRaw = String(node?.data?.cloud?.region || node?.data?.evidence?.region || '').trim();
          const region = regionRaw ? regionRaw : 'global';
          const regionGroupId = `group-cloud-${provider}-${region}`;
          const orgRaw = String(node?.data?.cloud?.org_name || node?.data?.cloud?.as_name || node?.data?.evidence?.org_name || node?.data?.evidence?.as_name || '').trim();
          const org = orgRaw || null;
          const stat = cloudProviderStats.get(providerGroupId) || { provider, count: 0, asnCounts: new Map(), orgCounts: new Map() };
          stat.count += 1;
          if (asn) stat.asnCounts.set(asn, (stat.asnCounts.get(asn) || 0) + 1);
          if (org) stat.orgCounts.set(org, (stat.orgCounts.get(org) || 0) + 1);
          cloudProviderStats.set(providerGroupId, stat);

          if (!cloudProviderGroups.has(providerGroupId)) {
            const theme = cloudProviderTheme[provider] || cloudProviderTheme.cloud;
            cloudProviderGroups.set(providerGroupId, {
              id: providerGroupId,
              type: 'groupNode',
              data: {
                label: provider.toUpperCase(),
                labelWrapMode: 'wrap',
                editorResizable: manualEditMode,
                manualSized: false,
                editorSizePinned: false,
                onResizeNode: handleGroupResize,
              },
              position: { x: 0, y: 0 },
              style: {
                backgroundColor: theme.bg,
                border: `2px dashed ${theme.border}`,
                borderRadius: '12px',
                padding: 16,
                width: 10,
                height: 10,
                zIndex: manualEditMode ? 40 : -90,
                pointerEvents: 'all',
                display: 'flex',
                alignItems: 'flex-start',
                justifyContent: 'center',
                fontWeight: 'bold',
                color: theme.text,
                fontSize: '14px',
              },
              draggable: true,
              selectable: true,
              parentNode: groupId,
              extent: 'parent',
            });
          }

          const rstat = cloudRegionStats.get(regionGroupId) || { provider, region, count: 0, asnCounts: new Map(), orgCounts: new Map() };
          rstat.count += 1;
          if (asn) rstat.asnCounts.set(asn, (rstat.asnCounts.get(asn) || 0) + 1);
          if (org) rstat.orgCounts.set(org, (rstat.orgCounts.get(org) || 0) + 1);
          cloudRegionStats.set(regionGroupId, rstat);

          if (!cloudRegionGroups.has(regionGroupId)) {
            const theme = cloudProviderTheme[provider] || cloudProviderTheme.cloud;
            cloudRegionGroups.set(regionGroupId, {
              id: regionGroupId,
              type: 'groupNode',
              data: {
                label: region,
                labelWrapMode: 'wrap',
                editorResizable: manualEditMode,
                manualSized: false,
                editorSizePinned: false,
                onResizeNode: handleGroupResize,
              },
              position: { x: 0, y: 0 },
              style: {
                backgroundColor: theme.bg,
                border: `1px dashed ${theme.border}`,
                borderRadius: '12px',
                padding: 14,
                width: 10,
                height: 10,
                zIndex: manualEditMode ? 40 : -80,
                pointerEvents: 'all',
                display: 'flex',
                alignItems: 'flex-start',
                justifyContent: 'center',
                fontWeight: 'bold',
                color: theme.text,
                fontSize: '12px',
                opacity: 0.95,
              },
              draggable: true,
              selectable: true,
              parentNode: providerGroupId,
              extent: 'parent',
            });
          }

          node.parentNode = regionGroupId;
          node.extent = 'parent';
        } else {
          // Link device node to site group
          node.parentNode = groupId;
          node.extent = 'parent'; // Keep child inside parent
        }
      });

      for (const [providerGroupId, stat] of cloudProviderStats.entries()) {
        const g = cloudProviderGroups.get(providerGroupId);
        if (!g) continue;
        const providerLabel = String(stat.provider || 'cloud').toUpperCase();
        const asnKeys = Array.from(stat.asnCounts.keys());
        const uniqueAsn = asnKeys.length === 1 ? asnKeys[0] : null;
        const orgCounts = stat.orgCounts || new Map();
        const orgKeys = Array.from(orgCounts.keys());
        const sortedOrgs = Array.from(orgCounts.entries()).sort((a, b) => (b[1] || 0) - (a[1] || 0));
        const orgTop = sortedOrgs.slice(0, 5).map(([org, count]) => ({ org, count }));
        let orgPart = '';
        if (orgKeys.length === 1) {
          orgPart = ` · ${truncateLabel(orgKeys[0], 26)}`;
        } else if (orgKeys.length > 1) {
          const topOrg = sortedOrgs[0]?.[0];
          if (topOrg) orgPart = ` · ${truncateLabel(topOrg, 22)} +${orgKeys.length - 1}`;
        }
        const label = `${providerLabel} (${stat.count})${uniqueAsn ? ` · AS${uniqueAsn}` : ''}${orgPart}`;
        g.data = { ...(g.data || {}), label, orgTop, orgCount: orgKeys.length };
      }

      for (const [regionGroupId, stat] of cloudRegionStats.entries()) {
        const g = cloudRegionGroups.get(regionGroupId);
        if (!g) continue;
        const regionLabel = String(stat.region || 'global');
        const asnKeys = Array.from(stat.asnCounts.keys());
        const uniqueAsn = asnKeys.length === 1 ? asnKeys[0] : null;
        const orgCounts = stat.orgCounts || new Map();
        const orgKeys = Array.from(orgCounts.keys());
        const sortedOrgs = Array.from(orgCounts.entries()).sort((a, b) => (b[1] || 0) - (a[1] || 0));
        const orgTop = sortedOrgs.slice(0, 5).map(([org, count]) => ({ org, count }));
        let orgPart = '';
        if (orgKeys.length === 1) {
          orgPart = ` · ${truncateLabel(orgKeys[0], 26)}`;
        } else if (orgKeys.length > 1) {
          const topOrg = sortedOrgs[0]?.[0];
          if (topOrg) orgPart = ` · ${truncateLabel(topOrg, 22)} +${orgKeys.length - 1}`;
        }
        const label = `${regionLabel} (${stat.count})${uniqueAsn ? ` · AS${uniqueAsn}` : ''}${orgPart}`;
        g.data = { ...(g.data || {}), label, orgTop, orgCount: orgKeys.length };
      }

      // 2. Combine all nodes
      const allNodes = [
        ...Array.from(siteGroups.values()),
        ...Array.from(cloudProviderGroups.values()),
        ...Array.from(cloudRegionGroups.values()),
        ...deviceNodes
      ];

      // 3. Calculate Layout
      try {
        const { nodes: layoutedNodes, edges: layoutedEdges } = await getElkLayoutedElements(
          allNodes,
          finalEdges
        );
        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
      } catch (err) {
        console.error("ELK Layout Failed:", err);
      }
    };

    runLayout();

  }, [
    rawTopology,
    selectedSiteId,
    pathResult,
    showHealth,
    healthMetric,
    layerFilter,
    trafficFlowEnabled,
    lowConfidenceOnly,
    confidenceThreshold,
    highlightedLink,
    cloudProviderFilter,
    cloudAccountFilter,
    cloudRegionFilter,
    cloudOrgFilter?.enabled,
    cloudOrgFilter?.org,
    manualEditMode,
    layoutNodesSnapshot,
    layoutManualEdges,
    layoutHiddenEdgeKeys,
    layoutNodeOverrides,
    layoutEdgeOverrides,
    setNodes,
    setEdges,
  ]); // Include cloud filter deps so dropdown changes re-render immediately


  // Events
  const onNodeClick = useCallback(async (event, node) => {
    if (node.type === 'groupNode') {
      if (manualEditMode) {
        focusTopologyGroupNode(node);
      }
      return;
    }
    if (String(node.id || '').startsWith('ep-') || node?.data?.role === 'endpoint') return;

    if (node?.data?.role === 'endpoint_group') {
      const deviceId = node?.data?.device_id;
      const port = node?.data?.port;
      if (!deviceId || !port) return;

      setEndpointGroupPanel({ open: true, loading: true, error: '', group: { device_id: deviceId, port, label: node?.data?.node_label || null }, endpoints: [] });
      try {
        const res = await DeviceService.getEndpointGroupDetails(deviceId, port, { hours: 24 });
        setEndpointGroupPanel(prev => ({ ...prev, loading: false, endpoints: res.data?.endpoints || [], group: { ...prev.group, count: res.data?.count } }));
      } catch (e) {
        setEndpointGroupPanel(prev => ({ ...prev, loading: false, error: e.response?.data?.detail || e.message || 'Failed to load endpoint group' }));
      }
      return;
    }

    if (node?.data?.role === 'cloud') {
      setSelectedTopologyEdge(null);
      if (manualEditMode) {
        setCloudDetailPanel({ open: false, node: null });
        setSelectedTopologyNode(node);
        return;
      }
      setSelectedTopologyNode(null);
      setSelectedTopologyEdge(null);
      setCloudDetailPanel({ open: true, node });
      return;
    }

    setSelectedTopologyEdge(null);
    setSelectedTopologyNode(node);
  }, [focusTopologyGroupNode, manualEditMode]);

  const onNodeDoubleClick = useCallback((event, node) => {
    if (!node || node.type === 'groupNode') return;
    if (String(node.id || '').startsWith('ep-') || node?.data?.role === 'endpoint') return;
    if (node?.data?.role === 'cloud') {
      setSelectedTopologyNode(null);
      setCloudDetailPanel({ open: true, node });
      return;
    }
    const deviceId = node?.data?.device_id ?? node.id;
    if (!deviceId) return;
    navigate(`/devices/${deviceId}`);
  }, [navigate]);

  const onPaneClick = useCallback(() => {
    if (Date.now() < suppressPaneClickUntilRef.current) return;
    setSelectedTopologyNode(null);
    setSelectedTopologyEdge(null);
    setTooltip(null);
    setContextMenu(null);
    setMultiSelectedNodes([]);
  }, []);

  // --- Context Menu handlers ---
  const onNodeContextMenu = useCallback((event, node) => {
    if (!manualEditMode) return;
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY, node, edge: null });
  }, [manualEditMode]);

  const onEdgeContextMenu = useCallback((event, edge) => {
    if (!manualEditMode) return;
    event.preventDefault();
    const layoutKey = buildTopologyEdgeKey(edge);
    setContextMenu({ x: event.clientX, y: event.clientY, node: null, edge: { ...edge, layoutKey } });
  }, [manualEditMode]);

  const onPaneContextMenu = useCallback((event) => {
    if (!manualEditMode) return;
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY, node: null, edge: null });
  }, [manualEditMode]);

  // --- Selection change (multi-select) ---
  const onSelectionChange = useCallback(({ nodes: selectedNodes }) => {
    setMultiSelectedNodes(selectedNodes || []);
  }, []);

  // --- Undo snapshot on drag start ---
  const onNodeDragStart = useCallback(() => {
    if (!manualEditMode) return;
    pushSnapshot(nodes, layoutManualEdges);
  }, [manualEditMode, nodes, layoutManualEdges, pushSnapshot]);

  const onNodeDragStop = useCallback((event, node) => {
    if (!manualEditMode || !editorSnapEnabled || !node?.id) return;
    const snappedPosition = {
      x: snapToTopologyGrid(node?.position?.x || 0),
      y: snapToTopologyGrid(node?.position?.y || 0),
    };
    setNodes((currentNodes) => {
      let changed = false;
      const nextNodes = currentNodes.map((item) => {
        if (String(item?.id || '') !== String(node.id)) return item;
        const currentX = Number(item?.position?.x || 0);
        const currentY = Number(item?.position?.y || 0);
        if (currentX === snappedPosition.x && currentY === snappedPosition.y) return item;
        changed = true;
        return {
          ...item,
          position: snappedPosition,
        };
      });
      if (!changed) return currentNodes;
      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      return nextNodes;
    });
  }, [editorSnapEnabled, manualEditMode, setNodes]);

  const onEdgeMouseEnter = useCallback((event, edge) => {
    if (edge.data && (edge.data.tooltipLines || edge.data.portDetails)) {
      setTooltip({
        x: event.clientX,
        y: event.clientY,
        content: edge.data.tooltipLines || edge.data.portDetails,
        label: edge.data?.fullLabel || edge.label
      });
    }
  }, []);

  const onEdgeMouseLeave = useCallback(() => {
    setTooltip(null);
  }, []);

  const onEdgeMouseMove = useCallback((event) => {
    setTooltip((prev) => prev ? { ...prev, x: event.clientX, y: event.clientY } : null);
  }, []);

  const filterEdgeEventsByWindow = useCallback((events, windowMin) => {
    const list = Array.isArray(events) ? events : [];
    const mins = Number(windowMin || 0);
    if (!Number.isFinite(mins) || mins <= 0) return list;
    const cutoff = Date.now() - (mins * 60 * 1000);
    return list.filter((ev) => {
      const ts = Date.parse(String(ev?.created_at || ''));
      return Number.isFinite(ts) && ts >= cutoff;
    });
  }, []);

  const autoDiffForEvent = useCallback(async (ev) => {
    const eventTs = Date.parse(String(ev?.created_at || ''));
    if (!Number.isFinite(eventTs)) {
      setEdgeEventDiff({ loading: false, error: 'Invalid event timestamp', data: null, eventId: ev?.id ?? null });
      return;
    }

    let snaps = Array.isArray(topologySnapshots) ? topologySnapshots.slice() : [];
    if (snaps.length < 2) {
      try {
        const res = await TopologyService.listSnapshots({ limit: 50 });
        snaps = Array.isArray(res?.data) ? res.data.slice() : [];
      } catch (e) {
        setEdgeEventDiff({ loading: false, error: e?.response?.data?.detail || e?.message || 'Failed to load snapshots', data: null, eventId: ev?.id ?? null });
        return;
      }
    }
    if (snaps.length < 2) {
      setEdgeEventDiff({ loading: false, error: 'Need at least 2 snapshots', data: null, eventId: ev?.id ?? null });
      return;
    }

    snaps.sort((a, b) => {
      const ta = Date.parse(String(a?.created_at || ''));
      const tb = Date.parse(String(b?.created_at || ''));
      return (Number.isFinite(ta) ? ta : 0) - (Number.isFinite(tb) ? tb : 0);
    });

    let before = null;
    let after = null;
    for (const s of snaps) {
      const ts = Date.parse(String(s?.created_at || ''));
      if (!Number.isFinite(ts)) continue;
      if (ts <= eventTs) before = s;
      if (ts > eventTs) {
        after = s;
        break;
      }
    }

    let a = null;
    let b = null;
    if (before && after && before.id !== after.id) {
      a = before;
      b = after;
    } else if (before) {
      const idx = snaps.findIndex((x) => x.id === before.id);
      if (idx > 0) {
        a = snaps[idx - 1];
        b = before;
      }
    } else if (after) {
      const idx = snaps.findIndex((x) => x.id === after.id);
      if (idx >= 0 && idx < snaps.length - 1) {
        a = after;
        b = snaps[idx + 1];
      }
    }
    if (!a || !b || a.id === b.id) {
      a = snaps[Math.max(0, snaps.length - 2)];
      b = snaps[snaps.length - 1];
    }

    try {
      const res = await TopologyService.diffSnapshots(a.id, b.id);
      setEdgeEventDiff({
        loading: false,
        error: '',
        data: res?.data || null,
        eventId: ev?.id ?? null,
      });
    } catch (e) {
      setEdgeEventDiff({ loading: false, error: e?.response?.data?.detail || e?.message || 'Failed to load snapshot diff', data: null, eventId: ev?.id ?? null });
    }
  }, [topologySnapshots]);

  const onEdgeClick = useCallback(async (event, edge) => {
    const layoutKey = buildTopologyEdgeKey(edge);
    if (manualEditMode) {
      setSelectedTopologyNode(null);
      setSelectedTopologyEdge({ ...edge, layoutKey });
      return;
    }
    setEdgeEventStateFilter('all');
    setEdgeEventWindowMin(15);
    setEdgeEventDiff({ loading: false, error: '', data: null, eventId: null });
    setSelectedTopologyNode(null);
    setSelectedTopologyEdge({ ...edge, layoutKey });
    setEdgeDetailPanel({ open: true, edge, events: [], loading: true, error: '' });
    try {
      const events = await fetchLinkEvents(edge, 30);
      setEdgeDetailPanel({ open: true, edge, events, loading: false, error: '' });
    } catch (e) {
      setEdgeDetailPanel({
        open: true,
        edge,
        events: [],
        loading: false,
        error: e?.response?.data?.detail || e?.message || 'Failed to load link events',
      });
    }
  }, [fetchLinkEvents, manualEditMode]);

  const saveNodeOverride = useCallback((nodeId, override) => {
    const key = String(nodeId || '');
    if (!key) return;
    setLayoutNodeOverrides((prev) => {
      const next = { ...(prev || {}) };
      const normalized = {
        label: String(override?.label || '').trim(),
        iconRole: String(override?.iconRole || '').trim(),
        fontSize: clampNumber(override?.fontSize, 11, 22, ''),
        wrapMode: String(override?.wrapMode || '').trim().toLowerCase() === 'single' ? 'single' : (String(override?.wrapMode || '').trim() ? 'wrap' : ''),
      };
      if (!normalized.label && !normalized.iconRole && !normalized.fontSize && !normalized.wrapMode) {
        delete next[key];
      } else {
        next[key] = normalized;
      }
      return next;
    });
  }, []);

  const createManualGroup = useCallback(() => {
    const currentManualIds = nodes
      .map((node) => String(node?.id || '').trim())
      .filter((id) => id.startsWith('manual-group-'));
    const maxExistingCounter = currentManualIds.reduce((current, id) => {
      const match = id.match(/^manual-group-(\d+)$/);
      if (!match) return current;
      return Math.max(current, Number(match[1] || 0));
    }, 0);
    const nextCounter = Math.max(manualGroupCounterRef.current, maxExistingCounter + 1);
    manualGroupCounterRef.current = nextCounter + 1;
    const nextId = `manual-group-${nextCounter}`;
    const inst = reactFlowInstanceRef.current;
    const viewportCenter = inst?.screenToFlowPosition
      ? inst.screenToFlowPosition({
          x: Math.max(240, Math.round(window.innerWidth / 2)),
          y: Math.max(180, Math.round(window.innerHeight / 2)),
        })
      : { x: 220, y: 180 };

    const groupNode = {
      id: nextId,
      type: 'groupNode',
      position: viewportCenter,
      data: {
        label: t('topology_manual_box_default', 'New Zone'),
        manualBox: true,
        helperText: t('topology_manual_box_hint', 'Manual grouping box'),
        labelWrapMode: 'wrap',
        editorResizable: manualEditMode,
        manualSized: true,
        editorSizePinned: true,
        onResizeNode: handleGroupResize,
        onFocusNode: handleGroupFocusById,
      },
      style: {
        backgroundColor: 'rgba(14, 165, 233, 0.08)',
        border: '2px dashed rgba(14, 165, 233, 0.65)',
        borderRadius: '14px',
        padding: 20,
        width: 340,
        height: 220,
        zIndex: manualEditMode ? 40 : -60,
        pointerEvents: 'all',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        fontWeight: 'bold',
        color: '#0f172a',
        fontSize: '14px',
      },
      draggable: true,
      selectable: true,
    };

    setNodes((currentNodes) => {
      const nextNodes = [...currentNodes, groupNode];
      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      return nextNodes;
    });
    pendingGroupSelectionRef.current = nextId;
    suppressPaneClickUntilRef.current = Date.now() + 600;
    if (typeof window !== 'undefined') {
      window.setTimeout(() => {
        window.dispatchEvent(new CustomEvent('netmanager:topology-group-focus', {
          detail: { id: nextId },
        }));
      }, 0);
      window.requestAnimationFrame(() => {
        window.dispatchEvent(new CustomEvent('netmanager:topology-group-focus', {
          detail: { id: nextId },
        }));
      });
    }
  }, [handleGroupFocusById, manualEditMode, nodes, setNodes]);

  const updateManualGroup = useCallback((nodeId, patch) => {
    const key = String(nodeId || '').trim();
    if (!key) return;
    setNodes((currentNodes) => {
      const nextNodes = currentNodes.map((node) => {
        if (String(node?.id || '') !== key || node?.type !== 'groupNode') return node;
        const nextLabel = String(patch?.label || node?.data?.label || '').trim() || t('topology_manual_box_default', 'New Zone');
        const fillColor = String(patch?.fillColor || '').trim() || 'rgba(14, 165, 233, 0.08)';
        const borderColor = String(patch?.borderColor || '').trim() || 'rgba(14, 165, 233, 0.65)';
        const nextFontSize = clampNumber(patch?.fontSize, 11, 24, Number(String(node?.style?.fontSize || 14).replace('px', '')) || 14);
        const nextWrapMode = String(patch?.wrapMode || node?.data?.labelWrapMode || 'wrap').trim().toLowerCase() === 'single' ? 'single' : 'wrap';
        const borderPrefix = String(node?.style?.border || '').includes('1px') ? '1px dashed' : '2px dashed';
        return {
          ...node,
          data: {
            ...(node.data || {}),
            label: nextLabel,
            manualBox: !!node?.data?.manualBox,
            labelWrapMode: nextWrapMode,
            editorResizable: manualEditMode,
            manualSized: true,
            editorSizePinned: !!node?.data?.editorSizePinned,
            onResizeNode: handleGroupResize,
            onFocusNode: handleGroupFocusById,
          },
          style: {
            ...(node.style || {}),
            backgroundColor: fillColor,
            border: `${borderPrefix} ${borderColor}`,
            fontSize: `${nextFontSize}px`,
          },
        };
      });
      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      return nextNodes;
    });
  }, [handleGroupFocusById, handleGroupResize, manualEditMode, setNodes]);

  const deleteManualGroup = useCallback((nodeId) => {
    const key = String(nodeId || '').trim();
    if (!key) return;
    setNodes((currentNodes) => {
      const nextNodes = currentNodes.filter((node) => String(node?.id || '') !== key);
      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      return nextNodes;
    });
    setSelectedTopologyNode((prev) => (String(prev?.id || '') === key ? null : prev));
  }, [setNodes]);

  const clearNodeOverride = useCallback((nodeId) => {
    const key = String(nodeId || '');
    if (!key) return;
    setLayoutNodeOverrides((prev) => {
      const next = { ...(prev || {}) };
      delete next[key];
      return next;
    });
  }, []);

  const measureGroupChildBounds = useCallback((groupId, childNodes) => {
    const key = String(groupId || '').trim();
    if (!key) return null;
    const stage = topologyStageRef?.current;
    if (!stage) return null;
    const groupElement = stage.querySelector(`.react-flow__node[data-id="${key}"]`);
    if (!(groupElement instanceof HTMLElement)) return null;
    const groupRect = groupElement.getBoundingClientRect();
    if (!groupRect.width || !groupRect.height) return null;

    let maxRight = 0;
    let maxBottom = 0;
    let measured = false;
    for (const child of Array.isArray(childNodes) ? childNodes : []) {
      const childId = String(child?.id || '').trim();
      if (!childId) continue;
      const childElement = stage.querySelector(`.react-flow__node[data-id="${childId}"]`);
      if (!(childElement instanceof HTMLElement)) continue;
      const childRect = childElement.getBoundingClientRect();
      if (!childRect.width || !childRect.height) continue;
      maxRight = Math.max(maxRight, childRect.right - groupRect.left);
      maxBottom = Math.max(maxBottom, childRect.bottom - groupRect.top);
      measured = true;
    }

    if (!measured) return null;
    return { maxRight, maxBottom };
  }, [topologyStageRef]);

  const getNodeResizeMinimums = useCallback((node, sourceNodes) => {
    const isGroupNode = node?.type === 'groupNode';
    const baseMinWidth = Math.max(
      isGroupNode ? 160 : 140,
      Number(node?.data?.editorMinWidth || 0) || (isGroupNode ? 160 : 140),
    );
    const baseMinHeight = Math.max(
      isGroupNode ? 96 : 88,
      Number(node?.data?.editorMinHeight || 0) || (isGroupNode ? 96 : 88),
    );
    if (!isGroupNode) {
      return { minWidth: baseMinWidth, minHeight: baseMinHeight };
    }

    const key = String(node?.id || '').trim();
    if (!key) {
      return { minWidth: baseMinWidth, minHeight: baseMinHeight };
    }

    const rows = Array.isArray(sourceNodes) ? sourceNodes : [];
    const childNodes = rows.filter((candidate) => String(candidate?.parentNode || '') === key);
    if (childNodes.length === 0) {
      return { minWidth: baseMinWidth, minHeight: baseMinHeight };
    }

    const descendantNodes = [];
    const pendingParentIds = childNodes.map((candidate) => String(candidate?.id || '')).filter(Boolean);
    const visited = new Set(pendingParentIds);
    while (pendingParentIds.length > 0) {
      const parentId = pendingParentIds.shift();
      const nestedChildren = rows.filter((candidate) => String(candidate?.parentNode || '') === String(parentId || ''));
      for (const candidate of nestedChildren) {
        const candidateId = String(candidate?.id || '');
        descendantNodes.push(candidate);
        if (candidateId && !visited.has(candidateId)) {
          visited.add(candidateId);
          pendingParentIds.push(candidateId);
        }
      }
    }

    const rightPadding = 28;
    const bottomPadding = 28;
    const minHeaderBottom = 56;
    let maxRight = rightPadding;
    let maxBottom = minHeaderBottom;

    for (const child of childNodes) {
      const width = Number(child?.width || child?.style?.width || child?.data?.editorMinWidth || 140) || 140;
      const height = Number(child?.height || child?.style?.height || child?.data?.editorMinHeight || 88) || 88;
      const childX = Number(child?.position?.x || 0);
      const childY = Number(child?.position?.y || 0);
      maxRight = Math.max(maxRight, childX + width);
      maxBottom = Math.max(maxBottom, childY + height);
    }

    const measuredBounds = measureGroupChildBounds(key, [...childNodes, ...descendantNodes]);
    if (measuredBounds) {
      maxRight = Math.max(maxRight, Number(measuredBounds.maxRight || 0));
      maxBottom = Math.max(maxBottom, Number(measuredBounds.maxBottom || 0), minHeaderBottom);
    }

    return {
      minWidth: Math.max(baseMinWidth, Math.round(maxRight + rightPadding)),
      minHeight: Math.max(baseMinHeight, Math.round(maxBottom + bottomPadding)),
    };
  }, [measureGroupChildBounds]);

  const resolveResizeFrame = useCallback((nodeId, patch, sourceNodes) => {
    const key = String(nodeId || '').trim();
    if (!key) return null;
    const rows = Array.isArray(sourceNodes) ? sourceNodes : [];
    const node = rows.find((candidate) => String(candidate?.id || '') === key);
    if (!node) return null;

    const isGroupNode = node?.type === 'groupNode';
    const maxWidth = isGroupNode ? GROUP_NODE_MAX_WIDTH : REGULAR_NODE_MAX_WIDTH;
    const maxHeight = isGroupNode ? GROUP_NODE_MAX_HEIGHT : REGULAR_NODE_MAX_HEIGHT;
    let { minWidth, minHeight } = getNodeResizeMinimums(node, rows);
    const visualContentMinWidth = Number(patch?.contentMinWidth || 0);
    const visualContentMinHeight = Number(patch?.contentMinHeight || 0);
    if (Number.isFinite(visualContentMinWidth) && visualContentMinWidth > 0) {
      minWidth = Math.max(minWidth, Math.round(visualContentMinWidth));
    }
    if (Number.isFinite(visualContentMinHeight) && visualContentMinHeight > 0) {
      minHeight = Math.max(minHeight, Math.round(visualContentMinHeight));
    }
    const nextWidth = clampNumber(
      patch?.width,
      minWidth,
      maxWidth,
      Number(node?.width || node?.style?.width || minWidth) || minWidth,
    );
    const nextHeight = clampNumber(
      patch?.height,
      minHeight,
      maxHeight,
      Number(node?.height || node?.style?.height || minHeight) || minHeight,
    );
    let nextX = Number.isFinite(Number(patch?.x)) ? Number(patch.x) : Number(node?.position?.x || 0);
    let nextY = Number.isFinite(Number(patch?.y)) ? Number(patch.y) : Number(node?.position?.y || 0);
    const anchor = String(patch?.anchor || '').trim().toLowerCase();
    const baseX = Number.isFinite(Number(patch?.baseX)) ? Number(patch.baseX) : Number(node?.position?.x || 0);
    const baseY = Number.isFinite(Number(patch?.baseY)) ? Number(patch.baseY) : Number(node?.position?.y || 0);
    const baseWidth = Number.isFinite(Number(patch?.baseWidth))
      ? Number(patch.baseWidth)
      : (Number(node?.width || node?.style?.width || nextWidth) || nextWidth);
    const baseHeight = Number.isFinite(Number(patch?.baseHeight))
      ? Number(patch.baseHeight)
      : (Number(node?.height || node?.style?.height || nextHeight) || nextHeight);
    if (anchor.includes('left')) {
      nextX = Math.round(baseX + (baseWidth - nextWidth));
    }
    if (anchor.includes('top')) {
      nextY = Math.round(baseY + (baseHeight - nextHeight));
    }
    return {
      width: nextWidth,
      height: nextHeight,
      x: nextX,
      y: nextY,
      minWidth,
      minHeight,
    };
  }, [getNodeResizeMinimums]);

  const resizeNodeFrame = useCallback((nodeId, patch) => {
    const key = String(nodeId || '').trim();
    if (!key) return;
    setNodes((currentNodes) => {
      const nextNodes = currentNodes.map((node) => {
        if (String(node?.id || '') !== key) return node;
        const resolved = resolveResizeFrame(key, patch, currentNodes);
        const nextWidth = Number(resolved?.width || node?.width || node?.style?.width || 0);
        const nextHeight = Number(resolved?.height || node?.height || node?.style?.height || 0);
        const nextX = Number.isFinite(Number(resolved?.x)) ? Number(resolved.x) : Number(node?.position?.x || 0);
        const nextY = Number.isFinite(Number(resolved?.y)) ? Number(resolved.y) : Number(node?.position?.y || 0);
        return {
          ...node,
          width: nextWidth,
          height: nextHeight,
          position: {
            ...(node?.position || {}),
            x: nextX,
            y: nextY,
          },
          data: {
            ...(node?.data || {}),
            manualSized: true,
            editorSizePinned: true,
          },
          style: {
            ...(node?.style || {}),
            width: nextWidth,
            height: nextHeight,
          },
        };
      });
      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      return nextNodes;
    });
  }, [resolveResizeFrame, setNodes]);

  useEffect(() => {
    groupResizeHandlerRef.current = resizeNodeFrame;
    return () => {
      if (groupResizeHandlerRef.current === resizeNodeFrame) {
        groupResizeHandlerRef.current = null;
      }
    };
  }, [resizeNodeFrame]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handleDirectResize = (event) => {
      if (!manualEditMode) return;
      const detail = event?.detail && typeof event.detail === 'object' ? event.detail : {};
      if (!detail?.id) return;
      resizeNodeFrame(detail.id, {
        width: detail.width,
        height: detail.height,
        x: detail.x,
        y: detail.y,
      });
    };
    window.addEventListener('netmanager:topology-direct-resize', handleDirectResize);
    return () => {
      window.removeEventListener('netmanager:topology-direct-resize', handleDirectResize);
    };
  }, [manualEditMode, resizeNodeFrame]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handleGroupFocus = (event) => {
      if (!manualEditMode) return;
      const detail = event?.detail && typeof event.detail === 'object' ? event.detail : {};
      const key = String(detail?.id || '').trim();
      if (!key) return;
      const matchedNode = nodes.find((node) => String(node?.id || '') === key);
      if (!matchedNode || matchedNode?.type !== 'groupNode') return;
      focusTopologyGroupNode(matchedNode);
    };
    window.addEventListener('netmanager:topology-group-focus', handleGroupFocus);
    return () => {
      window.removeEventListener('netmanager:topology-group-focus', handleGroupFocus);
    };
  }, [focusTopologyGroupNode, manualEditMode, nodes]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handleOpenEditor = (event) => {
      if (!manualEditMode) return;
      const detail = event?.detail && typeof event.detail === 'object' ? event.detail : {};
      const key = String(detail?.id || '').trim();
      if (!key) return;
      if (typeof window !== 'undefined') {
        window.__netmanagerTopologyDebug = {
          ...(window.__netmanagerTopologyDebug || {}),
          lastOpenEditorHandledId: key,
          lastOpenEditorHandledTs: Date.now(),
        };
      }
      const matchedNode = nodes.find((node) => String(node?.id || '') === key);
      if (!matchedNode || matchedNode?.type !== 'groupNode') return;
      focusTopologyGroupNode(matchedNode);
    };
    window.addEventListener('netmanager:topology-group-open-editor', handleOpenEditor);
    return () => {
      window.removeEventListener('netmanager:topology-group-open-editor', handleOpenEditor);
    };
  }, [focusTopologyGroupNode, manualEditMode, nodes]);

  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const handleQuickEditIntent = (event) => {
      if (!manualEditMode) return;
      const target = event?.target instanceof HTMLElement ? event.target : null;
      if (!target) return;
      const pointCandidates = Number.isFinite(Number(event?.clientX)) && Number.isFinite(Number(event?.clientY))
        ? document.elementsFromPoint(Number(event.clientX), Number(event.clientY))
        : [];
      const quickEdit = target.closest('[data-testid="topology-group-open-editor"][data-node-id], [data-testid="topology-group-overlay-open-editor"][data-node-id]')
        || pointCandidates.find((candidate) => (
          candidate instanceof HTMLElement &&
          candidate.matches?.('[data-testid="topology-group-open-editor"][data-node-id], [data-testid="topology-group-overlay-open-editor"][data-node-id]')
        ));
      if (!(quickEdit instanceof HTMLElement)) return;
      const key = String(quickEdit.getAttribute('data-node-id') || '').trim();
      if (!key) return;
      const matchedNode = nodes.find((node) => String(node?.id || '') === key);
      if (!matchedNode || matchedNode?.type !== 'groupNode') return;
      suppressPaneClickUntilRef.current = Date.now() + 600;
      if (typeof window !== 'undefined') {
        window.__netmanagerTopologyDebug = {
          ...(window.__netmanagerTopologyDebug || {}),
          lastQuickEditIntentId: key,
          lastQuickEditIntentTs: Date.now(),
          lastQuickEditIntentTarget: quickEdit.getAttribute('data-testid') || '',
        };
      }
      event.preventDefault?.();
      event.stopPropagation?.();
      focusTopologyGroupNode(matchedNode);
    };
    document.addEventListener('pointerdown', handleQuickEditIntent, true);
    document.addEventListener('click', handleQuickEditIntent, true);
    return () => {
      document.removeEventListener('pointerdown', handleQuickEditIntent, true);
      document.removeEventListener('click', handleQuickEditIntent, true);
    };
  }, [focusTopologyGroupNode, manualEditMode, nodes]);

  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const resolveGroupNodeFromEvent = (event) => {
      if (!manualEditMode) return null;
      const target = event?.target instanceof HTMLElement ? event.target : null;
      if (!target) return null;
      if (shouldIgnoreGroupFocusEvent(target)) return null;

      const directGroup = target.closest('[data-testid="topology-group-node-editable"][data-node-id]');
      const focusSurface = target.closest('[data-testid="topology-group-focus-surface"][data-node-id]');
      const quickEdit = target.closest('[data-testid="topology-group-open-editor"][data-node-id]');
      const wrapper = target.closest('.react-flow__node[data-id]');
      const fallbackElement = Number.isFinite(Number(event?.clientX)) && Number.isFinite(Number(event?.clientY))
        ? document.elementsFromPoint(Number(event.clientX), Number(event.clientY)).find((candidate) => (
          candidate instanceof HTMLElement &&
          (
            candidate.matches?.('[data-testid="topology-group-node-editable"][data-node-id]') ||
            candidate.matches?.('[data-testid="topology-group-focus-surface"][data-node-id]') ||
            candidate.matches?.('.react-flow__node[data-id]')
          )
        ))
        : null;

      const key = String(
        (directGroup instanceof HTMLElement
          ? directGroup.getAttribute('data-node-id')
          : focusSurface instanceof HTMLElement
            ? focusSurface.getAttribute('data-node-id')
            : quickEdit instanceof HTMLElement
              ? quickEdit.getAttribute('data-node-id')
              : wrapper instanceof HTMLElement
                ? wrapper.getAttribute('data-id')
                : fallbackElement instanceof HTMLElement
                  ? (fallbackElement.getAttribute('data-node-id') || fallbackElement.getAttribute('data-id'))
                  : '') || '',
      ).trim();
      if (!key) return null;
      return nodes.find((node) => String(node?.id || '') === key && node?.type === 'groupNode') || null;
    };

    const handleDocumentPointerDown = (event) => {
      const matchedNode = resolveGroupNodeFromEvent(event);
      if (!matchedNode) return;
      focusTopologyGroupNode(matchedNode);
    };

    document.addEventListener('pointerdown', handleDocumentPointerDown, true);
    document.addEventListener('mousedown', handleDocumentPointerDown, true);
    return () => {
      document.removeEventListener('pointerdown', handleDocumentPointerDown, true);
      document.removeEventListener('mousedown', handleDocumentPointerDown, true);
    };
  }, [focusTopologyGroupNode, manualEditMode, nodes, shouldIgnoreGroupFocusEvent]);

  useEffect(() => {
    if (!manualEditMode || typeof document === 'undefined') return undefined;

    const wrappers = Array.from(document.querySelectorAll('.react-flow__node[data-id]'));
    const cleanups = [];

    const handleWrapperPointerDown = (event) => {
      const wrapper = event?.currentTarget instanceof HTMLElement ? event.currentTarget : null;
      const target = event?.target instanceof HTMLElement ? event.target : null;
      if (!wrapper) return;
      if (target?.closest('[data-testid^="topology-group-resize-control-"]')) return;
      const key = String(wrapper.getAttribute('data-id') || '').trim();
      if (!key) return;
      const matchedNode = nodes.find((node) => String(node?.id || '') === key && node?.type === 'groupNode');
      if (!matchedNode) return;
      focusTopologyGroupNode(matchedNode);
    };

    for (const wrapper of wrappers) {
      if (!(wrapper instanceof HTMLElement)) continue;
      const key = String(wrapper.getAttribute('data-id') || '').trim();
      if (!key) continue;
      const matchedNode = nodes.find((node) => String(node?.id || '') === key && node?.type === 'groupNode');
      if (!matchedNode) continue;
      wrapper.addEventListener('pointerdown', handleWrapperPointerDown, true);
      wrapper.addEventListener('mousedown', handleWrapperPointerDown, true);
      cleanups.push(() => {
        wrapper.removeEventListener('pointerdown', handleWrapperPointerDown, true);
        wrapper.removeEventListener('mousedown', handleWrapperPointerDown, true);
      });
    }

    return () => {
      cleanups.forEach((cleanup) => cleanup());
    };
  }, [focusTopologyGroupNode, manualEditMode, nodes]);

  useEffect(() => {
    const stage = topologyStageRef?.current;
    if (!stage || typeof stage.addEventListener !== 'function') return undefined;
    const handleStageClick = (event) => {
      if (!manualEditMode) return;
      const target = event?.target instanceof HTMLElement ? event.target : null;
      if (!target) return;
      if (shouldIgnoreGroupFocusEvent(target)) return;
      const pointCandidates = typeof document !== 'undefined' && Number.isFinite(Number(event?.clientX)) && Number.isFinite(Number(event?.clientY))
        ? document.elementsFromPoint(Number(event.clientX), Number(event.clientY))
        : [];
      const pointElement = pointCandidates.find((candidate) => (
        candidate instanceof HTMLElement &&
        (
          candidate.matches?.('[data-testid="topology-group-focus-surface"][data-node-id]') ||
          candidate.matches?.('[data-testid="topology-group-node-editable"][data-node-id]') ||
          candidate.matches?.('.react-flow__node[data-id]')
        )
      ));
      const focusSurface = target.closest('[data-testid="topology-group-focus-surface"][data-node-id]');
      const groupElement = target.closest('[data-testid="topology-group-node-editable"][data-node-id]');
      const groupWrapper = target.closest('.react-flow__node[data-id]');
      const key = String(
        (focusSurface instanceof HTMLElement
          ? focusSurface.getAttribute('data-node-id')
          : groupElement instanceof HTMLElement
          ? groupElement.getAttribute('data-node-id')
          : groupWrapper instanceof HTMLElement
            ? groupWrapper.getAttribute('data-id')
            : pointElement instanceof HTMLElement
              ? (pointElement.getAttribute('data-node-id') || pointElement.getAttribute('data-id'))
            : '') || '',
      ).trim();
      if (!key) return;
      const matchedNode = nodes.find((node) => String(node?.id || '') === key);
      if (!matchedNode || matchedNode?.type !== 'groupNode') return;
      focusTopologyGroupNode(matchedNode);
    };
    stage.addEventListener('click', handleStageClick, true);
    return () => {
      stage.removeEventListener('click', handleStageClick, true);
    };
  }, [focusTopologyGroupNode, manualEditMode, nodes, shouldIgnoreGroupFocusEvent]);

  useEffect(() => {
    setNodes((currentNodes) => currentNodes.map((node) => {
      if (node?.type !== 'groupNode') return node;
      const baseZIndex = Number(
        node?.data?.editorBaseZIndex ?? node?.style?.zIndex ?? (node?.data?.manualBox ? -60 : -100),
      );
      const manualEditZIndex = node?.data?.manualBox ? 60 : 40;
      return {
        ...node,
        data: {
          ...(node?.data || {}),
          editorResizable: manualEditMode,
          editorBaseZIndex: baseZIndex,
          onFocusNode: handleGroupFocusById,
        },
        style: {
          ...(node?.style || {}),
          zIndex: manualEditMode ? manualEditZIndex : baseZIndex,
          pointerEvents: 'all',
        },
      };
    }));
  }, [handleGroupFocusById, manualEditMode, setNodes]);

  const fitGroupToChildren = useCallback((nodeId) => {
    const key = String(nodeId || '').trim();
    if (!key) return;
    setNodes((currentNodes) => {
      const groupNode = currentNodes.find((node) => String(node?.id || '') === key && node?.type === 'groupNode');
      if (!groupNode) return currentNodes;
      const childNodes = currentNodes.filter((node) => String(node?.parentNode || '') === key);
      if (childNodes.length === 0) {
        toast.warning(t('topology_fit_children_empty', 'There are no child nodes inside this box yet.'));
        return currentNodes;
      }

      const { minWidth, minHeight } = getNodeResizeMinimums(groupNode, currentNodes);
      const horizontalPadding = 28;
      const bottomPadding = 28;
      const headerPadding = 56;
      const minChildX = Math.min(...childNodes.map((node) => Number(node?.position?.x || 0)));
      const minChildY = Math.min(...childNodes.map((node) => Number(node?.position?.y || 0)));
      const offsetX = minChildX < horizontalPadding ? horizontalPadding - minChildX : 0;
      const offsetY = minChildY < headerPadding ? headerPadding - minChildY : 0;

      let maxX = horizontalPadding;
      let maxY = headerPadding;
      const nextNodes = currentNodes.map((node) => {
        if (String(node?.parentNode || '') !== key) return node;
        const width = Number(node?.width || node?.style?.width || node?.data?.editorMinWidth || 140) || 140;
        const height = Number(node?.height || node?.style?.height || node?.data?.editorMinHeight || 88) || 88;
        const nextPosition = {
          x: Number(node?.position?.x || 0) + offsetX,
          y: Number(node?.position?.y || 0) + offsetY,
        };
        maxX = Math.max(maxX, nextPosition.x + width);
        maxY = Math.max(maxY, nextPosition.y + height);
        return {
          ...node,
          position: nextPosition,
        };
      }).map((node) => {
        if (String(node?.id || '') !== key) return node;
        const nextWidth = Math.max(minWidth, Math.round(maxX + horizontalPadding));
        const nextHeight = Math.max(minHeight, Math.round(maxY + bottomPadding));
        return {
          ...node,
          width: nextWidth,
          height: nextHeight,
          data: {
            ...(node?.data || {}),
            manualSized: true,
            editorSizePinned: true,
          },
          style: {
            ...(node?.style || {}),
            width: nextWidth,
            height: nextHeight,
          },
        };
      });

      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      toast.success(t('topology_fit_children_done', 'Group box resized to fit its child nodes.'));
      return nextNodes;
    });
  }, [setNodes, toast]);

  const arrangeGroupChildren = useCallback((nodeId) => {
    const key = String(nodeId || '').trim();
    if (!key) return;
    setNodes((currentNodes) => {
      const groupNode = currentNodes.find((node) => String(node?.id || '') === key && node?.type === 'groupNode');
      if (!groupNode) return currentNodes;
      const childNodes = currentNodes.filter((node) => String(node?.parentNode || '') === key);
      if (childNodes.length === 0) {
        toast.warning(t('topology_arrange_children_empty', 'There are no child nodes inside this box yet.'));
        return currentNodes;
      }

      const { minWidth, minHeight } = getNodeResizeMinimums(groupNode, currentNodes);
      const currentWidth = Math.max(minWidth, Number(groupNode?.width || groupNode?.style?.width || minWidth) || minWidth);
      const horizontalPadding = 28;
      const topPadding = 56;
      const bottomPadding = 28;
      const colGap = 24;
      const rowGap = 24;
      const availableWidth = Math.max(180, currentWidth - horizontalPadding * 2);
      const sortedChildren = [...childNodes].sort((a, b) => {
        const ay = Number(a?.position?.y || 0);
        const by = Number(b?.position?.y || 0);
        if (Math.abs(ay - by) > 4) return ay - by;
        return Number(a?.position?.x || 0) - Number(b?.position?.x || 0);
      });

      let cursorX = horizontalPadding;
      let cursorY = topPadding;
      let rowHeight = 0;
      let maxRight = horizontalPadding;
      let maxBottom = topPadding;
      const arrangedMap = new Map();

      for (const node of sortedChildren) {
        const width = Number(node?.width || node?.style?.width || node?.data?.editorMinWidth || 140) || 140;
        const height = Number(node?.height || node?.style?.height || node?.data?.editorMinHeight || 88) || 88;
        const neededWidth = width + (cursorX > horizontalPadding ? colGap : 0);
        if (cursorX > horizontalPadding && (cursorX - horizontalPadding + neededWidth) > availableWidth) {
          cursorX = horizontalPadding;
          cursorY += rowHeight + rowGap;
          rowHeight = 0;
        }
        arrangedMap.set(String(node.id), {
          x: cursorX,
          y: cursorY,
        });
        cursorX += width + colGap;
        rowHeight = Math.max(rowHeight, height);
        maxRight = Math.max(maxRight, cursorX - colGap);
        maxBottom = Math.max(maxBottom, cursorY + height);
      }

      const nextHeight = Math.max(minHeight, Math.round(maxBottom + bottomPadding));
      const nextNodes = currentNodes.map((node) => {
        if (String(node?.parentNode || '') === key) {
          const nextPosition = arrangedMap.get(String(node?.id || ''));
          if (!nextPosition) return node;
          return {
            ...node,
            position: nextPosition,
          };
        }
        if (String(node?.id || '') === key) {
          return {
            ...node,
            width: currentWidth,
            height: nextHeight,
            data: {
              ...(node?.data || {}),
              manualSized: true,
              editorSizePinned: !!node?.data?.editorSizePinned,
            },
            style: {
              ...(node?.style || {}),
              width: currentWidth,
              height: nextHeight,
            },
          };
        }
        return node;
      });

      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      toast.success(t('topology_arrange_children_done', 'Child nodes were arranged inside the selected box.'));
      return nextNodes;
    });
  }, [setNodes, toast]);

  const resolveTopologyOverlaps = useCallback(() => {
    setNodes((currentNodes) => {
      const nextNodes = [...currentNodes];
      const groups = new Map();
      for (const node of nextNodes) {
        if (node?.type === 'groupNode') continue;
        const parentKey = String(node?.parentNode || '__root__');
        if (!groups.has(parentKey)) groups.set(parentKey, []);
        groups.get(parentKey).push(node);
      }

      let changed = false;
      const padding = 20;
      const iterations = 8;
      for (const items of groups.values()) {
        for (let iter = 0; iter < iterations; iter += 1) {
          let movedInIteration = false;
          for (let i = 0; i < items.length; i += 1) {
            for (let j = i + 1; j < items.length; j += 1) {
              const a = items[i];
              const b = items[j];
              const ax = Number(a?.position?.x || 0);
              const ay = Number(a?.position?.y || 0);
              const bx = Number(b?.position?.x || 0);
              const by = Number(b?.position?.y || 0);
              const aw = Number(a?.width || a?.style?.width || a?.data?.editorMinWidth || 140) || 140;
              const ah = Number(a?.height || a?.style?.height || a?.data?.editorMinHeight || 88) || 88;
              const bw = Number(b?.width || b?.style?.width || b?.data?.editorMinWidth || 140) || 140;
              const bh = Number(b?.height || b?.style?.height || b?.data?.editorMinHeight || 88) || 88;

              const overlapX = Math.min(ax + aw + padding, bx + bw + padding) - Math.max(ax - padding, bx - padding);
              const overlapY = Math.min(ay + ah + padding, by + bh + padding) - Math.max(ay - padding, by - padding);
              if (overlapX <= 0 || overlapY <= 0) continue;

              changed = true;
              movedInIteration = true;
              if (overlapX <= overlapY) {
                const shift = Math.ceil(overlapX / 2) + 8;
                a.position = { ...(a.position || {}), x: ax - shift };
                b.position = { ...(b.position || {}), x: bx + shift };
              } else {
                const shift = Math.ceil(overlapY / 2) + 8;
                a.position = { ...(a.position || {}), y: ay - shift };
                b.position = { ...(b.position || {}), y: by + shift };
              }
            }
          }
          if (!movedInIteration) break;
        }
      }

      if (!changed) {
        toast.info(t('topology_resolve_overlaps_none', 'No major overlaps were detected.'));
        return currentNodes;
      }

      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      toast.success(t('topology_resolve_overlaps_done', 'Overlapping nodes were nudged apart.'));
      return nextNodes;
    });
  }, [setNodes, toast]);

  const snapNodesToGrid = useCallback(() => {
    setNodes((currentNodes) => {
      let changed = false;
      const nextNodes = currentNodes.map((node) => {
        const currentX = Number(node?.position?.x || 0);
        const currentY = Number(node?.position?.y || 0);
        const nextX = snapToTopologyGrid(currentX);
        const nextY = snapToTopologyGrid(currentY);
        if (currentX === nextX && currentY === nextY) return node;
        changed = true;
        return {
          ...node,
          position: { x: nextX, y: nextY },
        };
      });
      if (!changed) {
        toast.info(t('topology_snap_grid_none', 'Nodes are already aligned to the editor grid.'));
        return currentNodes;
      }
      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      toast.success(t('topology_snap_grid_done', 'Nodes were aligned to the editor grid.'));
      return nextNodes;
    });
  }, [setNodes, toast]);

  const tidyTopologyCanvas = useCallback(() => {
    setNodes((currentNodes) => {
      const nextNodes = [...currentNodes];
      let changed = false;

      for (const node of nextNodes) {
        const currentX = Number(node?.position?.x || 0);
        const currentY = Number(node?.position?.y || 0);
        const nextX = snapToTopologyGrid(currentX);
        const nextY = snapToTopologyGrid(currentY);
        if (currentX !== nextX || currentY !== nextY) {
          node.position = { ...(node.position || {}), x: nextX, y: nextY };
          changed = true;
        }
      }

      const groups = nextNodes.filter((node) => node?.type === 'groupNode');
      for (const groupNode of groups) {
        const key = String(groupNode?.id || '');
        if (!key) continue;
        const childNodes = nextNodes.filter((node) => String(node?.parentNode || '') === key);
        if (childNodes.length === 0) continue;
        const sizePinned = !!groupNode?.data?.editorSizePinned;

        const { minWidth, minHeight } = getNodeResizeMinimums(groupNode, nextNodes);
        const currentWidth = Math.max(minWidth, Number(groupNode?.width || groupNode?.style?.width || minWidth) || minWidth);
        const horizontalPadding = 28;
        const topPadding = 56;
        const bottomPadding = 28;
        const colGap = 24;
        const rowGap = 24;
        const availableWidth = Math.max(180, currentWidth - horizontalPadding * 2);
        const sortedChildren = [...childNodes].sort((a, b) => {
          const ay = Number(a?.position?.y || 0);
          const by = Number(b?.position?.y || 0);
          if (Math.abs(ay - by) > 4) return ay - by;
          return Number(a?.position?.x || 0) - Number(b?.position?.x || 0);
        });

        let cursorX = horizontalPadding;
        let cursorY = topPadding;
        let rowHeight = 0;
        let maxRight = horizontalPadding;
        let maxBottom = topPadding;

        for (const child of sortedChildren) {
          const width = Number(child?.width || child?.style?.width || child?.data?.editorMinWidth || 140) || 140;
          const height = Number(child?.height || child?.style?.height || child?.data?.editorMinHeight || 88) || 88;
          const neededWidth = width + (cursorX > horizontalPadding ? colGap : 0);
          if (cursorX > horizontalPadding && (cursorX - horizontalPadding + neededWidth) > availableWidth) {
            cursorX = horizontalPadding;
            cursorY += rowHeight + rowGap;
            rowHeight = 0;
          }
          const nextX = snapToTopologyGrid(cursorX);
          const nextY = snapToTopologyGrid(cursorY);
          if (Number(child?.position?.x || 0) !== nextX || Number(child?.position?.y || 0) !== nextY) {
            child.position = { x: nextX, y: nextY };
            changed = true;
          }
          cursorX = nextX + width + colGap;
          rowHeight = Math.max(rowHeight, height);
          maxRight = Math.max(maxRight, nextX + width);
          maxBottom = Math.max(maxBottom, nextY + height);
        }

        const nextWidth = Math.max(minWidth, snapToTopologyGrid(maxRight + horizontalPadding));
        const nextHeight = Math.max(minHeight, snapToTopologyGrid(maxBottom + bottomPadding));
        const currentHeight = Math.max(minHeight, Number(groupNode?.height || groupNode?.style?.height || minHeight) || minHeight);
        const enforcedWidth = sizePinned ? Math.max(currentWidth, nextWidth) : nextWidth;
        const enforcedHeight = sizePinned ? Math.max(currentHeight, nextHeight) : nextHeight;
        if (
          Number(groupNode?.width || groupNode?.style?.width || 0) !== enforcedWidth ||
          Number(groupNode?.height || groupNode?.style?.height || 0) !== enforcedHeight
        ) {
          groupNode.width = enforcedWidth;
          groupNode.height = enforcedHeight;
          groupNode.data = {
            ...(groupNode?.data || {}),
            manualSized: true,
          };
          groupNode.style = {
            ...(groupNode?.style || {}),
            width: enforcedWidth,
            height: enforcedHeight,
          };
          changed = true;
        }
      }

      const groupsByParent = new Map();
      for (const node of nextNodes) {
        if (node?.type === 'groupNode') continue;
        const parentKey = String(node?.parentNode || '__root__');
        if (!groupsByParent.has(parentKey)) groupsByParent.set(parentKey, []);
        groupsByParent.get(parentKey).push(node);
      }
      const padding = 20;
      const iterations = 8;
      for (const items of groupsByParent.values()) {
        for (let iter = 0; iter < iterations; iter += 1) {
          let movedInIteration = false;
          for (let i = 0; i < items.length; i += 1) {
            for (let j = i + 1; j < items.length; j += 1) {
              const a = items[i];
              const b = items[j];
              const ax = Number(a?.position?.x || 0);
              const ay = Number(a?.position?.y || 0);
              const bx = Number(b?.position?.x || 0);
              const by = Number(b?.position?.y || 0);
              const aw = Number(a?.width || a?.style?.width || a?.data?.editorMinWidth || 140) || 140;
              const ah = Number(a?.height || a?.style?.height || a?.data?.editorMinHeight || 88) || 88;
              const bw = Number(b?.width || b?.style?.width || b?.data?.editorMinWidth || 140) || 140;
              const bh = Number(b?.height || b?.style?.height || b?.data?.editorMinHeight || 88) || 88;
              const overlapX = Math.min(ax + aw + padding, bx + bw + padding) - Math.max(ax - padding, bx - padding);
              const overlapY = Math.min(ay + ah + padding, by + bh + padding) - Math.max(ay - padding, by - padding);
              if (overlapX <= 0 || overlapY <= 0) continue;
              movedInIteration = true;
              changed = true;
              if (overlapX <= overlapY) {
                const shift = Math.max(8, Math.ceil(overlapX / 2) + 8);
                a.position = { ...(a.position || {}), x: snapToTopologyGrid(ax - shift, 8) };
                b.position = { ...(b.position || {}), x: snapToTopologyGrid(bx + shift, 8) };
              } else {
                const shift = Math.max(8, Math.ceil(overlapY / 2) + 8);
                a.position = { ...(a.position || {}), y: snapToTopologyGrid(ay - shift, 8) };
                b.position = { ...(b.position || {}), y: snapToTopologyGrid(by + shift, 8) };
              }
            }
          }
          if (!movedInIteration) break;
        }
      }

      if (!changed) {
        toast.info(t('topology_tidy_canvas_none', 'The canvas is already tidy.'));
        return currentNodes;
      }

      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      toast.success(t('topology_tidy_canvas_done', 'The topology canvas was tidied for easier editing.'));
      return nextNodes;
    });
  }, [setNodes, toast]);

  // ── Smart Auto-Layout (Dagre hierarchical) ──
  const smartAutoLayout = useCallback((direction = 'TB') => {
    setNodes((currentNodes) => {
      if (!dagre || !dagre.graphlib) {
        toast.error('Dagre library not available');
        return currentNodes;
      }

      // Separate groups from regular nodes
      const groupNodes = currentNodes.filter(n => n?.type === 'groupNode');
      const regularNodes = currentNodes.filter(n => n?.type !== 'groupNode' && !n?.parentNode);
      const childNodes = currentNodes.filter(n => n?.type !== 'groupNode' && !!n?.parentNode);

      if (regularNodes.length === 0) {
        toast.info(t('topology_auto_layout_empty', 'No nodes to arrange.'));
        return currentNodes;
      }

      // Role-based rank assignment for hierarchical ordering
      const roleRank = (node) => {
        const role = String(node?.data?.iconRole || node?.data?.role || node?.device_type || '').toLowerCase();
        if (role.includes('core') || role.includes('router')) return 0;
        if (role.includes('dist') || role.includes('distribution')) return 1;
        if (role.includes('wlc') || role.includes('controller')) return 2;
        if (role.includes('access') || role.includes('switch')) return 3;
        if (role.includes('ap') || role.includes('wireless')) return 4;
        if (role.includes('cloud') || role.includes('server')) return 5;
        return 3; // default to access-level
      };

      const g = new dagre.graphlib.Graph();
      g.setGraph({
        rankdir: direction,
        nodesep: 80,
        ranksep: 120,
        edgesep: 40,
        marginx: 60,
        marginy: 60,
      });
      g.setDefaultEdgeLabel(() => ({}));

      // Add nodes with role-based rank hints
      for (const node of regularNodes) {
        const w = Number(node?.width || node?.style?.width || 160) || 160;
        const h = Number(node?.height || node?.style?.height || 88) || 88;
        g.setNode(String(node.id), { width: w, height: h, rank: roleRank(node) });
      }

      // Add edges from current ReactFlow edges
      const edgeSet = new Set();
      for (const edge of (reactFlowInstanceRef.current?.getEdges?.() || [])) {
        const src = String(edge?.source || '');
        const tgt = String(edge?.target || '');
        if (!src || !tgt || src === tgt) continue;
        if (!g.hasNode(src) || !g.hasNode(tgt)) continue;
        const key = [src, tgt].sort().join('|');
        if (edgeSet.has(key)) continue;
        edgeSet.add(key);
        g.setEdge(src, tgt);
      }

      dagre.layout(g);

      const nextNodes = currentNodes.map(node => {
        if (node?.type === 'groupNode' || node?.parentNode) return node;
        const pos = g.node(String(node.id));
        if (!pos) return node;
        const w = Number(node?.width || node?.style?.width || 160) || 160;
        const h = Number(node?.height || node?.style?.height || 88) || 88;
        return {
          ...node,
          position: {
            x: snapToTopologyGrid(pos.x - w / 2),
            y: snapToTopologyGrid(pos.y - h / 2),
          },
        };
      });

      setLayoutNodesSnapshot(serializeTopologyLayoutNodes(nextNodes));
      toast.success(t('topology_auto_layout_done', 'Nodes arranged in hierarchical layout.'));
      return nextNodes;
    });
  }, [setNodes, toast]);

  const createManualEdge = useCallback((payload) => {
    const source = String(payload?.source || '').trim();
    const target = String(payload?.target || '').trim();
    if (!source || !target || source === target) return;
    const id = `manual-${manualEdgeCounterRef.current}`;
    manualEdgeCounterRef.current += 1;
    setLayoutManualEdges((prev) => [
      ...(Array.isArray(prev) ? prev : []),
      {
        id,
        source,
        target,
        label: String(payload?.label || '').trim(),
        kind: String(payload?.kind || 'manual').trim().toLowerCase() || 'manual',
        color: String(payload?.color || '').trim() || '',
        width: Number(payload?.width || 0) || 3,
        curve: String(payload?.curve || 'default').trim().toLowerCase() || 'default',
        lineStyle: String(payload?.lineStyle || 'solid').trim().toLowerCase() || 'solid',
        labelPosition: clampNumber(payload?.labelPosition, 10, 90, 50),
        labelOffsetY: clampNumber(payload?.labelOffsetY, -80, 80, 0),
      },
    ]);
  }, []);

  const updateManualEdge = useCallback((edgeId, patch) => {
    const key = String(edgeId || '');
    if (!key) return;
    setLayoutManualEdges((prev) => (Array.isArray(prev) ? prev : []).map((edge) => (
      String(edge?.id || '') === key
        ? {
            ...edge,
            label: String(patch?.label || '').trim(),
            kind: String(patch?.kind || edge?.kind || 'manual').trim().toLowerCase() || 'manual',
            color: String(patch?.color || edge?.color || '').trim(),
            width: Number(patch?.width || edge?.width || 0) || 3,
            curve: String(patch?.curve || edge?.curve || 'default').trim().toLowerCase() || 'default',
            lineStyle: String(patch?.lineStyle || edge?.lineStyle || 'solid').trim().toLowerCase() || 'solid',
            labelPosition: clampNumber(patch?.labelPosition, 10, 90, Number(edge?.labelPosition || 50) || 50),
            labelOffsetY: clampNumber(patch?.labelOffsetY, -80, 80, Number(edge?.labelOffsetY || 0) || 0),
          }
        : edge
    )));
  }, []);

  const deleteManualEdge = useCallback((edgeId) => {
    const key = String(edgeId || '');
    if (!key) return;
    setLayoutManualEdges((prev) => (Array.isArray(prev) ? prev : []).filter((edge) => String(edge?.id || '') !== key));
    setSelectedTopologyEdge((prev) => (String(prev?.id || '') === key ? null : prev));
  }, []);

  const hideAutoEdge = useCallback((edgeKey) => {
    const key = String(edgeKey || '').trim();
    if (!key) return;
    setLayoutHiddenEdgeKeys((prev) => {
      const set = new Set(Array.isArray(prev) ? prev : []);
      set.add(key);
      return Array.from(set);
    });
  }, []);

  const showAutoEdge = useCallback((edgeKey) => {
    const key = String(edgeKey || '').trim();
    if (!key) return;
    setLayoutHiddenEdgeKeys((prev) => (Array.isArray(prev) ? prev : []).filter((item) => String(item) !== key));
  }, []);

  const saveEdgeOverride = useCallback((edgeKey, override) => {
    const key = String(edgeKey || '').trim();
    if (!key) return;
    setLayoutEdgeOverrides((prev) => {
      const next = { ...(prev || {}) };
      const normalized = {
        label: String(override?.label || '').trim(),
        color: String(override?.color || '').trim(),
        width: Number(override?.width || 0) || '',
        curve: String(override?.curve || '').trim().toLowerCase(),
        lineStyle: String(override?.lineStyle || '').trim().toLowerCase(),
        labelPosition: clampNumber(override?.labelPosition, 10, 90, 50),
        labelOffsetY: clampNumber(override?.labelOffsetY, -80, 80, 0),
      };
      if (normalized.labelPosition === 50) normalized.labelPosition = '';
      if (normalized.labelOffsetY === 0) normalized.labelOffsetY = '';
      if (!normalized.label && !normalized.color && !normalized.width && !normalized.curve && !normalized.lineStyle && normalized.labelPosition === '' && normalized.labelOffsetY === '') {
        delete next[key];
      } else {
        next[key] = normalized;
      }
      return next;
    });
  }, []);

  const clearEdgeOverride = useCallback((edgeKey) => {
    const key = String(edgeKey || '').trim();
    if (!key) return;
    setLayoutEdgeOverrides((prev) => {
      const next = { ...(prev || {}) };
      delete next[key];
      return next;
    });
  }, []);

  // --- Undo/Redo execution ---
  const performUndo = useCallback(() => {
    const snap = undo(nodes, layoutManualEdges);
    if (!snap) return;
    setNodes((prev) => {
      const posMap = new Map(snap.positions.map((p) => [p.id, p]));
      return prev.map((n) => {
        const saved = posMap.get(String(n.id));
        if (!saved) return n;
        return { ...n, position: { x: saved.x, y: saved.y } };
      });
    });
    setLayoutManualEdges(snap.manualEdges);
    toast.info(t('topology_undo_done', 'Undo'));
  }, [nodes, layoutManualEdges, undo, setNodes, toast]);

  const performRedo = useCallback(() => {
    const snap = redo(nodes, layoutManualEdges);
    if (!snap) return;
    setNodes((prev) => {
      const posMap = new Map(snap.positions.map((p) => [p.id, p]));
      return prev.map((n) => {
        const saved = posMap.get(String(n.id));
        if (!saved) return n;
        return { ...n, position: { x: saved.x, y: saved.y } };
      });
    });
    setLayoutManualEdges(snap.manualEdges);
    toast.info(t('topology_redo_done', 'Redo'));
  }, [nodes, layoutManualEdges, redo, setNodes, toast]);

  // --- Save layout (also used by Ctrl+S) ---
  const handleSaveLayout = useCallback(async () => {
    try {
      const envelope = buildLayoutEnvelope(nodes);
      await TopologyService.saveLayout({ name: 'User Layout', data: envelope });
      setLayoutNodesSnapshot(envelope.nodes);
      setSavedLayoutDigest(serializeTopologyLayoutEnvelope(envelope));
      setLayoutPersistenceMeta({ savedAt: new Date().toISOString(), source: 'saved' });
      toast.success(t('topology_layout_saved', 'Layout saved successfully!'));
    } catch (err) {
      console.error('Failed to save layout:', err);
      toast.error(t('topology_layout_save_failed', 'Failed to save layout.'));
    }
  }, [buildLayoutEnvelope, nodes, toast]);

  useEffect(() => {
    saveLayoutRef.current = handleSaveLayout;
  }, [handleSaveLayout]);

  // --- Delete selected handler (for Delete key) ---
  const handleDeleteSelected = useCallback(() => {
    if (selectedTopologyEdge?.data?.manual) {
      pushSnapshot(nodes, layoutManualEdges);
      deleteManualEdge(selectedTopologyEdge.id);
      setSelectedTopologyEdge(null);
      return;
    }
    const selNode = selectedTopologyNode;
    if (selNode?.type === 'groupNode' && selNode?.data?.manualBox) {
      pushSnapshot(nodes, layoutManualEdges);
      deleteManualGroup(selNode.id);
      setSelectedTopologyNode(null);
    }
  }, [selectedTopologyEdge, selectedTopologyNode, nodes, layoutManualEdges, pushSnapshot, deleteManualEdge, deleteManualGroup]);

  // --- Select all handler ---
  const handleSelectAll = useCallback(() => {
    const inst = reactFlowInstanceRef.current;
    if (!inst) return;
    const allNodes = inst.getNodes();
    allNodes.forEach((n) => { n.selected = true; });
    setNodes([...allNodes]);
    setMultiSelectedNodes(allNodes);
  }, [setNodes]);

  // --- Escape handler ---
  const handleEscape = useCallback(() => {
    setSelectedTopologyNode(null);
    setSelectedTopologyEdge(null);
    setContextMenu(null);
    setMultiSelectedNodes([]);
    const inst = reactFlowInstanceRef.current;
    if (inst) {
      const allNodes = inst.getNodes();
      allNodes.forEach((n) => { n.selected = false; });
      setNodes([...allNodes]);
    }
  }, [setNodes]);

  // --- Group selected nodes into a box ---
  const handleGroupSelected = useCallback(() => {
    if (multiSelectedNodes.length < 2) return;
    pushSnapshot(nodes, layoutManualEdges);
    createManualGroup();
  }, [multiSelectedNodes, nodes, layoutManualEdges, pushSnapshot, createManualGroup]);

  // --- Keyboard shortcuts ---
  useTopologyKeyboard({
    enabled: manualEditMode,
    onUndo: performUndo,
    onRedo: performRedo,
    onDelete: handleDeleteSelected,
    onSave: () => saveLayoutRef.current?.(),
    onSelectAll: handleSelectAll,
    onEscape: handleEscape,
  });

  const focusEventLink = useCallback((ev) => {
    const inst = reactFlowInstanceRef.current;
    if (!inst) return;
    const payload = ev?.payload || {};
    const src = payload?.device_id != null ? String(payload.device_id) : '';
    const dst = payload?.neighbor_device_id != null ? String(payload.neighbor_device_id) : '';
    if (!src || !dst) return;
    const nodesToFit = inst.getNodes().filter((n) => {
      const id = String(n.id || '');
      return id === src || id === dst;
    });
    if (nodesToFit.length > 0) {
      inst.fitView({ nodes: nodesToFit, padding: 0.55, duration: 450, maxZoom: 1.35 });
    }
  }, []);

  const onEdgeEventClick = useCallback(async (ev) => {
    focusEventLink(ev);
    setEdgeEventDiff({ loading: true, error: '', data: null, eventId: ev?.id ?? null });
    await autoDiffForEvent(ev);
  }, [focusEventLink, autoDiffForEvent]);

  const focusLinkPair = useCallback((sourceId, targetId, protocol) => {
    const src = String(sourceId || '');
    const dst = String(targetId || '');
    if (!src || !dst) return;
    const inst = reactFlowInstanceRef.current;
    if (inst) {
      const nodesToFit = inst.getNodes().filter((n) => {
        const id = String(n.id || '');
        return id === src || id === dst;
      });
      if (nodesToFit.length > 0) {
        inst.fitView({ nodes: nodesToFit, padding: 0.55, duration: 450, maxZoom: 1.35 });
      }
    }
    setHighlightedLink({ source: src, target: dst, protocol: String(protocol || '').toUpperCase() });
  }, []);

  const focusTopologyNodeForImpact = useCallback((nodeId) => {
    const targetId = String(nodeId || '').trim();
    if (!targetId) return;
    const matchedNode = Array.isArray(nodes)
      ? nodes.find((node) => String(node?.id || '') === targetId)
      : null;
    if (!matchedNode) return;

    const inst = reactFlowInstanceRef.current;
    if (inst) {
      const nodesToFit = inst.getNodes().filter((node) => String(node?.id || '') === targetId);
      if (nodesToFit.length > 0) {
        inst.fitView({ nodes: nodesToFit, padding: 0.75, duration: 350, maxZoom: 1.45 });
      }
    }

    setSelectedTopologyEdge(null);
    setTooltip(null);
    if (matchedNode?.data?.role === 'cloud') {
      setSelectedTopologyNode(null);
      setCloudDetailPanel({ open: true, node: matchedNode });
      return;
    }
    setCloudDetailPanel({ open: false, node: null });
    setSelectedTopologyNode(matchedNode);
  }, [nodes]);

  const onRelatedDiffClick = useCallback((entry) => {
    const l = (entry?.after || entry?.before || entry || {});
    const src = l?.source;
    const dst = l?.target;
    const proto = l?.protocol;
    focusLinkPair(src, dst, proto);
  }, [focusLinkPair]);

  const filteredEdgeEvents = useMemo(() => {
    const base = filterEdgeEventsByWindow(edgeDetailPanel?.events || [], edgeEventWindowMin);
    return base.filter((ev) => {
      if (edgeEventStateFilter === 'all') return true;
      const st = String(ev?.payload?.state || '').toLowerCase();
      if (edgeEventStateFilter === 'down') return st === 'down' || st === 'inactive';
      return st === edgeEventStateFilter;
    });
  }, [edgeDetailPanel?.events, edgeEventWindowMin, edgeEventStateFilter, filterEdgeEventsByWindow]);

  useEffect(() => {
    if (!highlightedLink) return;
    const t = setTimeout(() => setHighlightedLink(null), 4500);
    return () => clearTimeout(t);
  }, [highlightedLink]);

  const relatedSnapshotDiff = useMemo(() => {
    const diff = edgeEventDiff?.data;
    const edge = edgeDetailPanel?.edge;
    if (!diff || !edge) return { added: [], removed: [], changed: [] };

    const edgeSrc = String(edge.source || '');
    const edgeDst = String(edge.target || '');
    const edgeProto = String(edge?.data?.protocol || '').toUpperCase();

    const matchLink = (l) => {
      if (!l || typeof l !== 'object') return false;
      const src = String(l.source || '');
      const dst = String(l.target || '');
      const proto = String(l.protocol || '').toUpperCase();
      const pair = (src === edgeSrc && dst === edgeDst) || (src === edgeDst && dst === edgeSrc);
      if (!pair) return false;
      if (edgeProto && proto && edgeProto !== proto) return false;
      return true;
    };

    const added = (Array.isArray(diff.added) ? diff.added : []).filter(matchLink);
    const removed = (Array.isArray(diff.removed) ? diff.removed : []).filter(matchLink);
    const changed = (Array.isArray(diff.changed) ? diff.changed : []).filter((c) => matchLink(c?.after || c?.before));
    return { added, removed, changed };
  }, [edgeEventDiff?.data, edgeDetailPanel?.edge]);

  const bgpViewSummary = useMemo(() => {
    const sessionEdges = (edges || []).filter((edge) => String(edge?.data?.protocol || '').toUpperCase() === 'BGP');
    const seenNodeIds = new Set();
    const asnSet = new Set();
    let established = 0;
    let degraded = 0;
    let ibgp = 0;
    let ebgp = 0;
    let unknown = 0;

    for (const edge of sessionEdges) {
      seenNodeIds.add(String(edge?.source || ''));
      seenNodeIds.add(String(edge?.target || ''));
      const l3 = edge?.data?.l3 && typeof edge.data.l3 === 'object' ? edge.data.l3 : {};
      const relationship = String(l3.relationship || '').trim().toLowerCase();
      const state = String(l3.state || '').trim().toLowerCase();

      if (relationship === 'ibgp') ibgp += 1;
      else if (relationship === 'ebgp') ebgp += 1;
      else unknown += 1;

      if (state === 'established' || state === 'up') established += 1;
      else degraded += 1;

      for (const asn of [l3?.source?.local_as, l3?.target?.local_as]) {
        const value = Number(asn);
        if (Number.isFinite(value)) asnSet.add(value);
      }
    }

    const bgpNodes = (nodes || []).filter((node) => {
      const peerCount = Number(node?.data?.l3?.peer_counts?.bgp || 0);
      return peerCount > 0 || seenNodeIds.has(String(node?.id || ''));
    });

    for (const node of bgpNodes) {
      const localAsns = Array.isArray(node?.data?.l3?.local_asns) ? node.data.l3.local_asns : [];
      for (const asn of localAsns) {
        const value = Number(asn);
        if (Number.isFinite(value)) asnSet.add(value);
      }
    }

    const sortedAsns = Array.from(asnSet.values()).sort((a, b) => a - b);
    return {
      totalSessions: sessionEdges.length,
      established,
      degraded,
      ibgp,
      ebgp,
      unknown,
      nodes: bgpNodes.length,
      asns: sortedAsns.slice(0, 8),
      moreAsnCount: Math.max(0, sortedAsns.length - 8),
    };
  }, [edges, nodes]);

  const overlayViewSummary = useMemo(() => {
    const overlayEdges = (edges || []).filter((edge) => {
      const protocol = String(edge?.data?.protocol || '').toUpperCase();
      const layer = String(edge?.data?.layer || '').trim().toLowerCase();
      return layer === 'overlay' || OVERLAY_PROTOCOLS.has(protocol);
    });
    const seenNodeIds = new Set();
    const vniMap = new Map();
    const transportSet = new Set();
    let active = 0;
    let degraded = 0;
    let evpn = 0;

    for (const edge of overlayEdges) {
      seenNodeIds.add(String(edge?.source || ''));
      seenNodeIds.add(String(edge?.target || ''));
      const overlay = edge?.data?.overlay && typeof edge.data.overlay === 'object' ? edge.data.overlay : {};
      const state = String(overlay.state || '').trim().toLowerCase();
      const transport = String(overlay.transport || '').trim().toUpperCase();
      if (transport) {
        transportSet.add(transport);
        if (transport.includes('EVPN')) evpn += 1;
      }
      if (state === 'up' || state === 'established' || state === 'active' || state === 'full') active += 1;
      else degraded += 1;

      const vnis = Array.isArray(overlay.vnis) ? overlay.vnis : [];
      for (const row of vnis) {
        const value = Number(row?.vni);
        if (!Number.isFinite(value)) continue;
        const type = String(row?.type || '').trim().toLowerCase() === 'l3' ? 'l3' : 'l2';
        vniMap.set(value, type);
      }
    }

    const overlayNodes = (nodes || []).filter((node) => {
      const peerCount = Number(node?.data?.overlay?.peer_counts?.total || 0);
      return peerCount > 0 || seenNodeIds.has(String(node?.id || ''));
    });
    const vtepSet = new Set();
    for (const node of overlayNodes) {
      const vteps = Array.isArray(node?.data?.overlay?.local_vtep_ips) ? node.data.overlay.local_vtep_ips : [];
      for (const vtep of vteps) {
        const value = String(vtep || '').trim();
        if (value) vtepSet.add(value);
      }
    }

    let l2 = 0;
    let l3 = 0;
    for (const type of vniMap.values()) {
      if (type === 'l3') l3 += 1;
      else l2 += 1;
    }

    return {
      totalTunnels: overlayEdges.length,
      active,
      degraded,
      nodes: overlayNodes.length,
      vteps: vtepSet.size,
      vnis: vniMap.size,
      l2vni: l2,
      l3vni: l3,
      evpn,
      transports: Array.from(transportSet.values()).slice(0, 4),
    };
  }, [edges, nodes]);

  const hybridViewSummary = useMemo(() => {
    const hybridEdges = (edges || []).filter((edge) => {
      const hybrid = edge?.data?.hybrid && typeof edge.data.hybrid === 'object' ? edge.data.hybrid : null;
      const protocol = String(edge?.data?.protocol || '').toUpperCase();
      const layer = String(edge?.data?.layer || '').trim().toLowerCase();
      return !!hybrid || protocol === 'CLOUD' || layer === 'hybrid';
    });
    const hybridNodeIds = new Set();
    const providerSet = new Set();
    const accountSet = new Set();
    const regionSet = new Set();
    let peerLinks = 0;
    let inventoryLinks = 0;
    let degraded = 0;

    for (const edge of hybridEdges) {
      hybridNodeIds.add(String(edge?.source || ''));
      hybridNodeIds.add(String(edge?.target || ''));
      const hybrid = edge?.data?.hybrid && typeof edge.data.hybrid === 'object' ? edge.data.hybrid : {};
      const kind = String(hybrid.kind || '').trim().toLowerCase();
      const status = String(edge?.data?.status || edge?.status || '').trim().toLowerCase();
      if (kind === 'inventory' || String(edge?.data?.protocol || '').toUpperCase() === 'CLOUD') inventoryLinks += 1;
      else peerLinks += 1;
      if (status && status !== 'active' && status !== 'up') degraded += 1;

      const provider = String(hybrid.provider || '').trim().toLowerCase();
      const accountId = hybrid.account_id != null ? String(hybrid.account_id).trim() : '';
      const region = String(hybrid.region || '').trim();
      if (provider) providerSet.add(provider);
      if (accountId) accountSet.add(accountId);
      if (region) regionSet.add(region);
    }

    const cloudNodes = (nodes || []).filter((node) => {
      const role = String(node?.data?.role || '').trim().toLowerCase();
      return role === 'cloud' || hybridNodeIds.has(String(node?.id || ''));
    });
    const onPremNodes = cloudNodes.filter((node) => String(node?.data?.role || '').trim().toLowerCase() !== 'cloud');
    const cloudOnlyNodes = cloudNodes.filter((node) => String(node?.data?.role || '').trim().toLowerCase() === 'cloud');

    for (const node of cloudOnlyNodes) {
      const hybrid = node?.data?.hybrid && typeof node.data.hybrid === 'object' ? node.data.hybrid : {};
      const cloud = node?.data?.cloud && typeof node.data.cloud === 'object' ? node.data.cloud : {};
      const providerValues = Array.isArray(hybrid.providers) ? hybrid.providers : [cloud.provider];
      const regionValues = Array.isArray(hybrid.regions) ? hybrid.regions : [cloud.region];
      const accountValues = Array.isArray(hybrid.accounts) ? hybrid.accounts : [cloud.account_id];
      for (const provider of providerValues) {
        const value = String(provider || '').trim().toLowerCase();
        if (value) providerSet.add(value);
      }
      for (const region of regionValues) {
        const value = String(region || '').trim();
        if (value) regionSet.add(value);
      }
      for (const account of accountValues) {
        const value = String(account || '').trim();
        if (value) accountSet.add(value);
      }
    }

    return {
      totalLinks: hybridEdges.length,
      peerLinks,
      inventoryLinks,
      degraded,
      cloudNodes: cloudOnlyNodes.length,
      onPremNodes: onPremNodes.length,
      providers: Array.from(providerSet.values()).sort(),
      accounts: accountSet.size,
      regions: regionSet.size,
    };
  }, [edges, nodes]);

  const protocolFilterOptions = [
    { value: 'all', label: 'All', activeClass: 'bg-gray-700 text-white' },
    { value: 'l2', label: 'L2', activeClass: 'bg-blue-500 text-white' },
    { value: 'l3', label: 'L3', activeClass: 'bg-purple-500 text-white' },
    { value: 'bgp', label: 'BGP', activeClass: 'bg-fuchsia-600 text-white' },
    { value: 'ospf', label: 'OSPF', activeClass: 'bg-orange-500 text-white' },
    { value: 'overlay', label: 'VXLAN', activeClass: 'bg-cyan-600 text-white' },
    { value: 'hybrid', label: 'Hybrid', activeClass: 'bg-sky-600 text-white' },
  ];
  const showBgpSummary = layerFilter === 'bgp' || (layerFilter === 'l3' && bgpViewSummary.totalSessions > 0);
  const showOverlaySummary = layerFilter === 'overlay' && overlayViewSummary.totalTunnels > 0;
  const showHybridSummary = layerFilter === 'hybrid' && hybridViewSummary.totalLinks > 0;
  const editableNodeOptions = useMemo(() => (
    (nodes || [])
      .filter((node) => node && node.type !== 'groupNode' && !String(node.id || '').startsWith('ep-') && node?.data?.role !== 'endpoint' && node?.data?.role !== 'endpoint_group')
      .map((node) => ({
        id: String(node.id),
        label: String(node?.data?.node_label || node?.data?.label || node.id),
      }))
  ), [nodes]);
  const groupNodesForOverlay = useMemo(
    () => (nodes || []).filter((node) => node?.type === 'groupNode'),
    [nodes],
  );
  const selectedEdgeOverride = useMemo(() => {
    if (!selectedTopologyEdge?.layoutKey) return null;
    return layoutEdgeOverrides?.[selectedTopologyEdge.layoutKey] || null;
  }, [layoutEdgeOverrides, selectedTopologyEdge?.layoutKey]);
  const selectedNodeOverride = useMemo(() => {
    if (!selectedTopologyNode?.id) return null;
    return layoutNodeOverrides?.[String(selectedTopologyNode.id)] || null;
  }, [layoutNodeOverrides, selectedTopologyNode?.id]);
  const selectedNodeSizing = useMemo(() => {
    if (!selectedTopologyNode) return null;
    const fallbackMinWidth = selectedTopologyNode?.type === 'groupNode' ? 160 : 140;
    const fallbackMinHeight = selectedTopologyNode?.type === 'groupNode' ? 96 : 88;
    const effectiveMinimums = getNodeResizeMinimums(selectedTopologyNode, nodes);
    return {
      width: Number(selectedTopologyNode?.width || selectedTopologyNode?.style?.width || 0) || '',
      height: Number(selectedTopologyNode?.height || selectedTopologyNode?.style?.height || 0) || '',
      minWidth: Math.max(fallbackMinWidth, Number(effectiveMinimums?.minWidth || 0) || fallbackMinWidth),
      minHeight: Math.max(fallbackMinHeight, Number(effectiveMinimums?.minHeight || 0) || fallbackMinHeight),
    };
  }, [getNodeResizeMinimums, nodes, selectedTopologyNode]);
  const selectedGroupDiagnostics = useMemo(() => {
    if (!selectedTopologyNode || selectedTopologyNode?.type !== 'groupNode') return null;
    const groupId = String(selectedTopologyNode?.id || '').trim();
    if (!groupId) return null;
    const currentWidth = Number(selectedTopologyNode?.width || selectedTopologyNode?.style?.width || selectedNodeSizing?.width || 0) || 0;
    const currentHeight = Number(selectedTopologyNode?.height || selectedTopologyNode?.style?.height || selectedNodeSizing?.height || 0) || 0;
    const minWidth = Math.max(160, Number(selectedNodeSizing?.minWidth || 0) || 160);
    const minHeight = Math.max(96, Number(selectedNodeSizing?.minHeight || 0) || 96);
    const horizontalPadding = 28;
    const topPadding = 56;
    const bottomPadding = 28;
    const childNodes = (Array.isArray(nodes) ? nodes : []).filter((node) => String(node?.parentNode || '') === groupId);
    const overflowChildren = childNodes.filter((node) => {
      const x = Number(node?.position?.x || 0);
      const y = Number(node?.position?.y || 0);
      const width = Number(node?.width || node?.style?.width || node?.data?.editorMinWidth || 140) || 140;
      const height = Number(node?.height || node?.style?.height || node?.data?.editorMinHeight || 88) || 88;
      if (x < horizontalPadding || y < topPadding) return true;
      if ((x + width + horizontalPadding) > currentWidth) return true;
      if ((y + height + bottomPadding) > currentHeight) return true;
      return false;
    });
    return {
      childCount: childNodes.length,
      overflowCount: overflowChildren.length,
      currentWidth,
      currentHeight,
      minWidth,
      minHeight,
      isTight: currentWidth <= minWidth || currentHeight <= minHeight,
    };
  }, [nodes, selectedNodeSizing?.height, selectedNodeSizing?.minHeight, selectedNodeSizing?.minWidth, selectedNodeSizing?.width, selectedTopologyNode]);
  const selectedEdgeHidden = useMemo(() => {
    if (!selectedTopologyEdge?.layoutKey) return false;
    return (Array.isArray(layoutHiddenEdgeKeys) ? layoutHiddenEdgeKeys : []).includes(selectedTopologyEdge.layoutKey);
  }, [layoutHiddenEdgeKeys, selectedTopologyEdge?.layoutKey]);
  const selectedEdgeWarning = useMemo(() => (
    selectedTopologyEdge?.data?.warningMeta || null
  ), [selectedTopologyEdge?.data?.warningMeta]);
  const manualWarningCount = useMemo(() => (
    (edges || []).filter((edge) => edge?.data?.manual && edge?.data?.warningMeta).length
  ), [edges]);

  const toolbarButtonBase =
    'h-11 px-3 inline-flex items-center gap-2 rounded-xl border shadow-sm text-sm font-semibold transition-colors whitespace-nowrap';
  const toolbarButtonNeutral =
    'bg-white dark:bg-[#25282c] text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700';
  const toolbarSelectBase =
    'h-11 px-3 rounded-xl border shadow-sm text-sm font-medium bg-white dark:bg-[#25282c] text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-700 outline-none';
  const toolbarControlCard =
    'h-11 px-3 inline-flex items-center gap-2 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#25282c] shadow-sm min-w-0';
  const toolbarIconButton =
    'h-11 w-11 inline-flex items-center justify-center rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#25282c] text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm';
  const observabilityHref = selectedSiteId !== 'all'
    ? buildObservabilityPath({ siteId: selectedSiteId })
    : buildObservabilityPath();
  const grafanaFleetHref = selectedSiteId !== 'all'
    ? buildGrafanaFleetHealthUrl({ siteId: selectedSiteId })
    : buildGrafanaFleetHealthUrl();
  const cloudIntentImpactSummary = useMemo(() => {
    if (!cloudIntentImpactActive) return null;
    const provider = cloudProviderFilter !== 'all' ? String(cloudProviderFilter || '').trim() : '';
    const accountId = cloudAccountFilter !== 'all' ? String(cloudAccountFilter || '').trim() : '';
    const accountLabel = accountId
      ? (cloudFilterOptions.accounts.find((row) => String(row.value) === accountId)?.label || `#${accountId}`)
      : '';
    const region = cloudRegionFilter !== 'all' ? String(cloudRegionFilter || '').trim() : '';
    const resourceName = String(focusCloudResource?.resourceName || focusCloudResource?.resourceId || '').trim();
    const resourceId = String(focusCloudResource?.resourceId || '').trim();
    const impactedNodes = Array.isArray(nodes)
      ? nodes.filter((node) => node?.type !== 'groupNode' && node?.data?.intentImpact)
      : [];
    const impactedEdges = Array.isArray(edges)
      ? edges.filter((edge) => edge?.data?.intentImpact)
      : [];
    const fullImpactLinkCount = impactedEdges.filter((edge) => String(edge?.data?.intentImpactStrength || '').trim().toLowerCase() === 'full').length;
    const partialImpactLinkCount = Math.max(0, impactedEdges.length - fullImpactLinkCount);
    const highlightedNodeLabels = impactedNodes
      .map((node) => String(
        node?.data?.node_label
          || node?.data?.original_node_label
          || node?.data?.hostname
          || node?.data?.ip
          || node?.id
          || '',
      ).trim())
      .filter(Boolean)
      .slice(0, 4);
    const impactedNodeEntries = impactedNodes
      .map((node) => {
        const label = String(
          node?.data?.node_label
            || node?.data?.original_node_label
            || node?.data?.hostname
            || node?.data?.ip
            || node?.id
            || '',
        ).trim();
        if (!label) return null;
        return {
          id: String(node?.id || '').trim(),
          label,
          role: String(node?.data?.role || '').trim().toLowerCase(),
          resourceType: String(node?.data?.cloud?.resource_type_label || node?.data?.cloud?.resource_type || '').trim(),
          provider: String(node?.data?.cloud?.provider || '').trim().toUpperCase(),
        };
      })
      .filter(Boolean)
      .sort((a, b) => {
        const aCloud = a?.role === 'cloud' ? 0 : 1;
        const bCloud = b?.role === 'cloud' ? 0 : 1;
        if (aCloud !== bCloud) return aCloud - bCloud;
        return String(a?.label || '').localeCompare(String(b?.label || ''));
      });
    const cloudIntentPath = buildCloudIntentPath({
      provider,
      accountId,
      region,
      resourceTypes: Array.isArray(impactCloudResourceTypes) ? impactCloudResourceTypes.filter(Boolean) : [],
      resourceName,
      resourceId,
      source: 'topology-impact',
    });
    const nextAction = impactedEdges.length > 0
      ? t('topology_intent_impact_next_action_links', 'Review the highlighted links first, then decide whether this scope is safe to approve.')
      : t('topology_intent_impact_next_action_scope', 'No discovered links matched this scope yet. Review the cloud node details and approval guardrails before you proceed.');
    return {
      provider,
      accountId,
      accountLabel,
      region,
      resourceName,
      resourceTypes: Array.isArray(impactCloudResourceTypes) ? impactCloudResourceTypes.filter(Boolean) : [],
      impactedNodeCount: impactedNodes.length,
      impactedLinkCount: impactedEdges.length,
      fullImpactLinkCount,
      partialImpactLinkCount,
      highlightedNodeLabels,
      impactedNodeEntries: impactedNodeEntries.slice(0, 6),
      remainingImpactedNodeCount: Math.max(0, impactedNodeEntries.length - 6),
      cloudIntentPath,
      cloudAccountsPath: accountId ? `/cloud/accounts?focusAccountId=${encodeURIComponent(accountId)}` : '/cloud/accounts',
      nextAction,
    };
  }, [
    cloudIntentImpactActive,
    cloudProviderFilter,
    cloudAccountFilter,
    cloudRegionFilter,
    cloudFilterOptions.accounts,
    focusCloudResource,
    impactCloudResourceTypes,
    nodes,
    edges,
  ]);

  const serviceOverlaySummary = useMemo(() => {
    if (!serviceOverlayEnabled || !selectedServiceGroupDetail) return null;
    const matchedNodes = Array.isArray(nodes)
      ? nodes.filter((node) => node?.type !== 'groupNode' && node?.data?.serviceOverlayMatch)
      : [];
    const highlightedEdges = Array.isArray(edges)
      ? edges.filter((edge) => edge?.data?.serviceOverlay)
      : [];
    const fullEdges = highlightedEdges.filter((edge) => String(edge?.data?.serviceOverlayStrength || '').trim().toLowerCase() === 'full').length;
    const boundaryEdges = Math.max(0, highlightedEdges.length - fullEdges);
    const matchedEntries = matchedNodes
      .map((node) => ({
        id: String(node?.id || ''),
        label: String(
          node?.data?.node_label
            || node?.data?.original_node_label
            || node?.data?.hostname
            || node?.data?.ip
            || node?.id
            || '',
        ).trim(),
        role: String(node?.data?.role || '').trim().toLowerCase(),
        provider: String(node?.data?.cloud?.provider || '').trim().toUpperCase(),
        resourceType: String(node?.data?.cloud?.resource_type_label || node?.data?.cloud?.resource_type || '').trim(),
      }))
      .filter((entry) => !!entry.label)
      .sort((a, b) => String(a.label).localeCompare(String(b.label)));
    return {
      id: String(selectedServiceGroupDetail?.id || ''),
      name: String(selectedServiceGroupDetail?.name || '').trim(),
      criticality: String(selectedServiceGroupDetail?.criticality || '').trim(),
      ownerTeam: String(selectedServiceGroupDetail?.owner_team || '').trim(),
      healthScore: Number(selectedServiceGroupDetail?.health?.health_score || 0),
      healthStatus: String(selectedServiceGroupDetail?.health?.health_status || '').trim().toLowerCase(),
      activeIssueCount: Number(selectedServiceGroupDetail?.health?.active_issue_count || 0),
      offlineDeviceCount: Number(selectedServiceGroupDetail?.health?.offline_device_count || 0),
      color: serviceOverlayColor,
      impactedNodeCount: matchedNodes.length,
      impactedEdgeCount: highlightedEdges.length,
      fullEdgeCount: fullEdges,
      boundaryEdgeCount: boundaryEdges,
      memberEntries: matchedEntries.slice(0, 8),
      remainingMemberCount: Math.max(0, matchedEntries.length - 8),
      serviceGroupsPath: `/service-groups?focusGroupId=${encodeURIComponent(String(selectedServiceGroupDetail?.id || ''))}`,
      operationsReportsPath: `/operations-reports?focusGroupId=${encodeURIComponent(String(selectedServiceGroupDetail?.id || selectedServiceGroupId || ''))}&focusGroupName=${encodeURIComponent(String(selectedServiceGroupDetail?.name || '').trim())}`,
      notificationsPath: `/notifications?serviceImpact=1&openServiceImpact=1&focusGroupId=${encodeURIComponent(String(selectedServiceGroupDetail?.id || selectedServiceGroupId || ''))}&focusGroupName=${encodeURIComponent(String(selectedServiceGroupDetail?.name || '').trim())}`,
    };
  }, [serviceOverlayEnabled, selectedServiceGroupDetail, selectedServiceGroupId, serviceOverlayColor, nodes, edges]);


  return (
    <div className="h-full min-h-0 w-full bg-[#f4f5f9] dark:bg-[#0e1012] flex flex-col animate-fade-in relative">

      {/* Header */}
      <div className="px-3 sm:px-4 md:px-6 py-3 flex flex-col gap-3 bg-white dark:bg-[#1b1d1f] border-b border-gray-200 dark:border-gray-800 shadow-sm z-10">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Network className="text-indigo-500" /> {t('topology_title_network_map', 'Network Map')}
          </h1>
        </div>

        <div className="w-full pb-1 lg:pb-0">
          <div className="flex flex-col gap-2.5">
            <div className="flex flex-wrap items-center gap-2 lg:gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => setShowHealth(!showHealth)}
                  className={`${toolbarButtonBase} ${showHealth ? 'bg-red-500 text-white border-red-600' : toolbarButtonNeutral}`}
                >
                  <Activity size={14} /> {t('topology_health', 'Health')}
                </button>
                {showHealth && (
                  <select
                    value={healthMetric}
                    onChange={(e) => setHealthMetric(e.target.value)}
                    className={`${toolbarSelectBase} w-[120px]`}
                  >
                    <option value="score">{t('topology_metric_score', 'Score')}</option>
                    <option value="cpu">{t('topology_metric_cpu', 'CPU')}</option>
                    <option value="memory">{t('topology_metric_memory', 'Memory')}</option>
                  </select>
                )}
              </div>

                <button
                  onClick={() => setTrafficFlowEnabled(!trafficFlowEnabled)}
                  className={`${toolbarButtonBase} ${trafficFlowEnabled ? 'bg-sky-600 text-white border-sky-700' : toolbarButtonNeutral}`}
                >
                  <Link2 size={14} /> {t('topology_traffic_flow', 'Traffic Flow')}
                </button>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => setLowConfidenceOnly((v) => !v)}
                    className={`${toolbarButtonBase} ${lowConfidenceOnly ? 'bg-amber-500 text-white border-amber-600' : toolbarButtonNeutral}`}
                    title={t('topology_low_confidence_title', 'Show only low-confidence links')}
                  >
                    <AlertCircle size={14} /> {t('topology_low_confidence', 'Low Confidence')}
                  </button>
                  {lowConfidenceOnly && (
                    <select
                      value={String(confidenceThreshold)}
                      onChange={(e) => setConfidenceThreshold(Number(e.target.value || 0.7))}
                      className={`${toolbarSelectBase} w-[108px]`}
                    >
                      <option value="0.6">&lt; 0.60</option>
                      <option value="0.7">&lt; 0.70</option>
                      <option value="0.8">&lt; 0.80</option>
                      <option value="0.9">&lt; 0.90</option>
                    </select>
                  )}
                </div>

                <button
                  onClick={() => setShowFlowInsight(!showFlowInsight)}
                  className={`${toolbarButtonBase} ${showFlowInsight ? 'bg-emerald-600 text-white border-emerald-700' : toolbarButtonNeutral}`}
                >
                  <Activity size={14} /> {t('topology_flow_insight', 'Flow Insight')}
                </button>

                <button
                  data-testid="topology-path-trace-toggle"
                  onClick={() => setShowPathTrace(!showPathTrace)}
                  className={`${toolbarButtonBase} ${showPathTrace ? 'bg-indigo-500 text-white border-indigo-600' : toolbarButtonNeutral}`}
                >
                  <Route size={14} /> {t('topology_path_trace', 'Path Trace')}
                </button>

                <div className="h-11 inline-flex max-w-full items-center rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#25282c] overflow-x-auto shadow-sm">
                  {protocolFilterOptions.map((lf) => (
                    <button
                      key={lf.value}
                      data-testid={`topology-layer-filter-${lf.value}`}
                      onClick={() => setLayerFilter(lf.value)}
                      className={`h-full px-3 text-xs font-semibold transition-colors ${layerFilter === lf.value
                        ? lf.activeClass
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                        }`}
                    >
                      {lf.label}
                    </button>
                  ))}
                </div>

                <button
                  data-testid="topology-candidates-toggle"
                  onClick={() => setShowCandidates(!showCandidates)}
                  className={`${toolbarButtonBase} ${showCandidates ? 'bg-amber-500 text-white border-amber-600' : toolbarButtonNeutral}`}
                >
                  <Link2 size={14} /> {t('topology_candidates', 'Candidates')}
                </button>
              </div>

            <div className="flex flex-wrap items-center gap-2 lg:gap-3">
              <div className={`${toolbarControlCard} min-w-[220px] flex-1 sm:flex-none sm:w-[260px] lg:w-[300px]`}>
                <MapIcon size={14} className="text-gray-500 shrink-0" />
                <select
                  value={selectedSiteId}
                  onChange={(e) => setSelectedSiteId(e.target.value)}
                  className="text-sm bg-transparent outline-none text-gray-700 dark:text-gray-300 cursor-pointer flex-1 min-w-0"
                >
                  <option value="all">{t('topology_global_view_all_sites', 'Global View (All Sites)')}</option>
                  {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>

              <div className={`${toolbarControlCard} min-w-[168px] flex-1 sm:flex-none sm:w-[180px]`}>
                <Cloud size={14} className="text-gray-500 shrink-0" />
                <select
                  value={cloudProviderFilter}
                  onChange={(e) => {
                    const v = String(e.target.value || 'all');
                    setCloudProviderFilter(v);
                    setCloudAccountFilter('all');
                    setCloudRegionFilter('all');
                  }}
                  className="text-sm bg-transparent outline-none text-gray-700 dark:text-gray-300 cursor-pointer flex-1 min-w-0"
                  title={t('topology_cloud_provider_filter', 'Cloud provider filter')}
                >
                  <option value="all">{t('topology_cloud_provider_all', 'Provider: All')}</option>
                  {cloudFilterOptions.providers.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>

              <div className={`${toolbarControlCard} min-w-[168px] flex-1 sm:flex-none sm:w-[180px]`}>
                <Server size={14} className="text-gray-500 shrink-0" />
                <select
                  value={cloudAccountFilter}
                  onChange={(e) => {
                    const v = String(e.target.value || 'all');
                    setCloudAccountFilter(v);
                    setCloudRegionFilter('all');
                  }}
                  className="text-sm bg-transparent outline-none text-gray-700 dark:text-gray-300 cursor-pointer flex-1 min-w-0"
                  title={t('topology_cloud_account_filter', 'Cloud account filter')}
                >
                  <option value="all">{t('topology_cloud_account_all', 'Account: All')}</option>
                  {cloudFilterOptions.accounts.map((a) => (
                    <option key={a.value} value={a.value}>{a.label}</option>
                  ))}
                </select>
              </div>

              <div className={`${toolbarControlCard} min-w-[168px] flex-1 sm:flex-none sm:w-[180px]`}>
                <Globe size={14} className="text-gray-500 shrink-0" />
                <select
                  value={cloudRegionFilter}
                  onChange={(e) => setCloudRegionFilter(String(e.target.value || 'all'))}
                  className="text-sm bg-transparent outline-none text-gray-700 dark:text-gray-300 cursor-pointer flex-1 min-w-0"
                  title={t('topology_cloud_region_filter', 'Cloud region filter')}
                >
                  <option value="all">{t('topology_cloud_region_all', 'Region: All')}</option>
                  {cloudFilterOptions.regions.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>

              {(cloudProviderFilter !== 'all' || cloudAccountFilter !== 'all' || cloudRegionFilter !== 'all' || cloudOrgFilter?.enabled) && (
                <button
                  onClick={() => {
                    setCloudProviderFilter('all');
                    setCloudAccountFilter('all');
                    setCloudRegionFilter('all');
                    setCloudOrgFilter({ enabled: false, org: '' });
                  }}
                  className={`${toolbarButtonBase} ${toolbarButtonNeutral}`}
                >
                  <XCircle size={14} />
                  {t('topology_cloud_filter_clear', 'Clear Cloud Filter')}
                </button>
              )}

              <button
                data-testid="topology-service-overlay-toggle"
                onClick={() => {
                  const next = !serviceOverlayEnabled;
                  setServiceOverlayEnabled(next);
                  if (!next) {
                    setSelectedServiceGroupDetail(null);
                  } else if (!selectedServiceGroupId && serviceGroupOptions.length > 0) {
                    setSelectedServiceGroupId(String(serviceGroupOptions[0]?.id || ''));
                  }
                }}
                className={`${toolbarButtonBase} ${serviceOverlayEnabled ? 'text-white border-cyan-700' : toolbarButtonNeutral}`}
                style={serviceOverlayEnabled ? { backgroundColor: serviceOverlayColor, borderColor: serviceOverlayColor } : undefined}
                title={t('topology_service_overlay_title', 'Service map overlay')}
              >
                <Layers size={14} />
                {t('topology_service_overlay_title', 'Service Map')}
              </button>

              <div className={`${toolbarControlCard} min-w-[220px] flex-1 sm:flex-none sm:w-[250px] ${serviceOverlayEnabled ? '' : 'opacity-70'}`}>
                <Box size={14} className="text-gray-500 shrink-0" />
                <select
                  data-testid="topology-service-overlay-select"
                  value={selectedServiceGroupId}
                  onChange={(e) => {
                    const value = String(e.target.value || '');
                    setSelectedServiceGroupId(value);
                    if (!serviceOverlayEnabled && value) setServiceOverlayEnabled(true);
                  }}
                  className="text-sm bg-transparent outline-none text-gray-700 dark:text-gray-300 cursor-pointer flex-1 min-w-0"
                  disabled={serviceGroupsLoading || serviceGroupOptions.length === 0}
                  title={t('topology_service_overlay_group_filter', 'Service group overlay')}
                >
                  <option value="">
                    {serviceGroupsLoading
                      ? t('common_loading', 'Loading...')
                      : t('topology_service_overlay_group_none', 'Service Group: Select')}
                  </option>
                  {serviceGroupOptions.map((group) => (
                    <option key={group.id} value={String(group.id)}>
                      {group.name}
                    </option>
                  ))}
                </select>
              </div>

              {(serviceOverlayEnabled || selectedServiceGroupId) && (
                <button
                  onClick={() => {
                    setServiceOverlayEnabled(false);
                    setSelectedServiceGroupId('');
                    setSelectedServiceGroupDetail(null);
                    appliedServiceGroupRef.current = '';
                  }}
                  className={`${toolbarButtonBase} ${toolbarButtonNeutral}`}
                >
                  <XCircle size={14} />
                  {t('topology_service_overlay_clear', 'Clear Service Map')}
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 lg:gap-3">
              <div className={`${toolbarControlCard} min-w-[280px] flex-1 lg:max-w-[460px]`}>
                <span className="text-xs font-bold text-gray-500 whitespace-nowrap">{t('topology_snapshot', 'Snapshot')}</span>
                <select
                  data-testid="topology-snapshot-select"
                  value={selectedSnapshotId}
                  onChange={(e) => setSelectedSnapshotId(e.target.value)}
                  className="text-sm bg-transparent outline-none text-gray-700 dark:text-gray-300 cursor-pointer flex-1 min-w-0"
                >
                  <option value="">{t('topology_live', 'Live')}</option>
                  {topologySnapshots.map((s) => (
                    <option key={s.id} value={String(s.id)}>
                      {s.label ? `${s.label} (#${s.id})` : `#${s.id}`} {s.created_at ? `· ${new Date(s.created_at).toLocaleString()}` : ''}
                    </option>
                  ))}
                </select>
                <button
                  onClick={async () => {
                    try {
                      const siteId = selectedSiteId !== 'all' ? Number(selectedSiteId) : null;
                      await TopologyService.createSnapshot({
                        site_id: siteId,
                        label: `manual ${new Date().toISOString().slice(0, 19).replace('T', ' ')}`,
                        metadata: { trigger: 'ui' }
                      });
                      await loadSnapshots();
                      toast.success(t('topology_snapshot_created', 'Snapshot created'));
                    } catch (e) {
                      toast.error(t('topology_snapshot_create_failed', 'Failed to create snapshot'));
                    }
                  }}
                  disabled={snapshotLoading}
                  className="h-8 px-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md text-xs font-bold disabled:opacity-50 shrink-0"
                  title={t('topology_snapshot_create', 'Create snapshot')}
                >
                  {snapshotLoading ? '...' : 'Save'}
                </button>
              </div>

              {/* Hidden File Input for Import */}
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                accept=".json"
                onChange={async (e) => {
                  const file = e.target.files[0];
                  if (!file) return;

                  try {
                    const text = await file.text();
                    const json = JSON.parse(text);

                    if (Array.isArray(json) || (json && typeof json === 'object')) {
                      if (
                        window.confirm(
                          t('topology_import_layout_confirm_fmt', 'Import layout from "{file}"? This will overwrite your current layout.')
                            .replace('{file}', String(file.name || '')),
                        )
                      ) {
                        const envelope = normalizeTopologyLayoutEnvelope(json);
                        applyLayoutEnvelope(envelope);
                        try {
                          await TopologyService.saveLayout({ name: 'Imported Layout', data: envelope });
                          setSavedLayoutDigest(serializeTopologyLayoutEnvelope(envelope));
                          setLayoutPersistenceMeta({ savedAt: new Date().toISOString(), source: 'saved' });
                          toast.success(t('topology_layout_import_saved', 'Layout imported and saved successfully!'));
                        } catch (err) {
                          console.error("Failed to save layout:", err);
                          toast.warning(t('topology_layout_import_only', 'Layout imported, but failed to save to DB.'));
                        }
                      }
                    } else {
                      toast.warning(t('topology_layout_invalid_file', 'Invalid topology file format.'));
                    }
                  } catch (err) {
                    console.error("File read error:", err);
                    toast.error(t('topology_layout_read_failed', 'Failed to read file.'));
                  }
                  e.target.value = '';
                }}
              />

              <div className="flex flex-wrap items-center gap-2">
                <div
                  data-testid="topology-toolbar-layout-status"
                  className={`${toolbarButtonBase} pointer-events-none ${
                    layoutHasUnsavedChanges
                      ? 'border-amber-500/30 bg-amber-500/10 text-amber-100'
                      : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
                  }`}
                >
                  {layoutHasUnsavedChanges
                    ? t('topology_layout_status_dirty', 'Draft changes')
                    : layoutPersistenceMeta?.source === 'saved'
                      ? t('topology_layout_status_saved_at', 'Saved {time}').replace('{time}', layoutSavedTimeLabel || '--:--')
                      : t('topology_layout_status_auto', 'Auto layout active')}
                </div>

                <button
                  onClick={async () => {
                    try {
                      const envelope = buildLayoutEnvelope(nodes);
                      await TopologyService.saveLayout({ name: "User Layout", data: envelope });
                      setLayoutNodesSnapshot(envelope.nodes);
                      setSavedLayoutDigest(serializeTopologyLayoutEnvelope(envelope));
                      setLayoutPersistenceMeta({ savedAt: new Date().toISOString(), source: 'saved' });
                      toast.success(t('topology_layout_saved', 'Layout saved successfully!'));
                    } catch (err) {
                      console.error("Failed to save layout:", err);
                      toast.error(t('topology_layout_save_failed', 'Failed to save layout.'));
                    }
                  }}
                  title={t('topology_save_layout_title', 'Save current layout to DB')}
                  data-testid="topology-toolbar-save-layout"
                  className={toolbarIconButton}
                >
                  <Save size={14} />
                </button>

                <button
                  onClick={async () => {
                    if (window.confirm(t('topology_layout_reset_confirm', 'Are you sure you want to reset the layout to auto-generated?'))) {
                      try {
                        await TopologyService.resetLayout();
                        applyLayoutEnvelope(null);
                        setSavedLayoutDigest(serializeTopologyLayoutEnvelope(EMPTY_LAYOUT_ENVELOPE));
                        setLayoutPersistenceMeta({ savedAt: '', source: 'auto' });
                        setSelectedTopologyEdge(null);
                        setSelectedTopologyNode(null);
                      } catch (err) {
                        console.error("Failed to reset layout:", err);
                      }
                    }
                  }}
                  title={t('topology_reset_layout_title', 'Reset to auto layout')}
                  data-testid="topology-toolbar-reset-layout"
                  className={toolbarIconButton}
                >
                  <LayoutTemplate size={14} />
                </button>

                <button
                  onClick={() => {
                    const jsonString = JSON.stringify(buildLayoutEnvelope(nodes), null, 2);
                    const blob = new Blob([jsonString], { type: "application/json" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `topology-layout-${new Date().toISOString().slice(0, 10)}.json`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                  }}
                  title={t('topology_export_layout_title', 'Export Layout (JSON)')}
                  data-testid="topology-toolbar-export-layout"
                  className={toolbarIconButton}
                >
                  <Download size={14} />
                </button>

                <button
                  onClick={() => fileInputRef.current?.click()}
                  title={t('topology_import_layout_title', 'Import Layout (JSON)')}
                  data-testid="topology-toolbar-import-layout"
                  className={toolbarIconButton}
                >
                  <Upload size={14} />
                </button>

                <button
                  onClick={() => setManualEditMode((prev) => !prev)}
                  title={t('topology_manual_edit_toggle', 'Toggle manual edit mode')}
                  data-testid="topology-toolbar-layout-editor-toggle"
                  disabled={loading}
                  className={`${toolbarButtonBase} ${manualEditMode ? 'bg-cyan-600 text-white border-cyan-700' : toolbarButtonNeutral}`}
                >
                  <Link2 size={14} />
                  {manualEditMode ? t('topology_manual_edit_on', 'Layout Editor On') : t('topology_manual_edit_off', 'Layout Editor')}
                </button>

                {manualEditMode ? (
                  <button
                    onClick={createManualGroup}
                    title={t('topology_manual_box_add', 'Add manual grouping box')}
                    data-testid="topology-toolbar-add-group"
                    className={`${toolbarButtonBase} bg-violet-600 text-white border-violet-700 hover:bg-violet-500`}
                  >
                    <Box size={14} />
                    {t('topology_manual_box_add_short', 'New Box')}
                  </button>
                ) : null}

                {manualEditMode ? (
                  <label className={`${toolbarButtonBase} ${toolbarButtonNeutral} cursor-pointer select-none`}>
                    <input
                      type="checkbox"
                      checked={editorSnapEnabled}
                      onChange={(e) => setEditorSnapEnabled(e.target.checked)}
                      data-testid="topology-toolbar-snap-grid-toggle"
                      className="h-4 w-4"
                    />
                    {t('topology_snap_grid_toggle', 'Snap Grid')}
                  </label>
                ) : null}

                {manualEditMode ? (
                  <button
                    onClick={tidyTopologyCanvas}
                    title={t('topology_tidy_canvas', 'Tidy Canvas')}
                    data-testid="topology-toolbar-tidy-canvas"
                    className={`${toolbarButtonBase} bg-sky-600 text-white border-sky-700 hover:bg-sky-500`}
                  >
                    <LayoutGrid size={14} />
                    {t('topology_tidy_canvas', 'Tidy Canvas')}
                  </button>
                ) : null}

                {manualEditMode ? (
                  <button
                    onClick={() => { pushSnapshot(nodes, layoutManualEdges); smartAutoLayout('TB'); }}
                    title={t('topology_smart_layout', 'Smart Layout (Hierarchical)')}
                    data-testid="topology-toolbar-smart-layout"
                    className={`${toolbarButtonBase} bg-indigo-600 text-white border-indigo-700 hover:bg-indigo-500`}
                  >
                    <GitBranch size={14} />
                    {t('topology_smart_layout_short', 'Smart Layout')}
                  </button>
                ) : null}
              </div>

              <div className="flex flex-wrap items-center gap-2 md:ml-auto">
                <button
                  onClick={() => navigate(observabilityHref)}
                  className={`${toolbarButtonBase} ${toolbarButtonNeutral}`}
                >
                  <BarChart3 size={14} />
                  {t('common_open_observability', 'Open Observability')}
                </button>

                <a
                  href={grafanaFleetHref}
                  target="_blank"
                  rel="noreferrer"
                  className={`${toolbarButtonBase} ${toolbarButtonNeutral}`}
                >
                  <Activity size={14} />
                  {t('obs_grafana', 'Grafana')}
                </a>

                <button
                  onClick={() => setRefreshKey((k) => k + 1)}
                  className={`${toolbarButtonBase} ${toolbarButtonNeutral}`}
                >
                  <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
                  {t('topology_refresh', 'Refresh')}
                </button>

                <label className={`${toolbarButtonBase} ${toolbarButtonNeutral} cursor-pointer select-none`}>
                  <input
                    type="checkbox"
                    checked={autoRefreshTopology}
                    onChange={(e) => setAutoRefreshTopology(e.target.checked)}
                    className="h-4 w-4"
                  />
                  {t('topology_auto', 'Auto')}
                </label>
              </div>
            </div>

            {serviceOverlaySummary && (
              <div
                data-testid="topology-service-overlay-banner"
                className="rounded-2xl border px-4 py-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"
                style={{
                  borderColor: `${serviceOverlaySummary.color}55`,
                  background: `${serviceOverlaySummary.color}12`,
                }}
              >
                <div className="min-w-0">
                  <div
                    data-testid="topology-service-overlay-group-name"
                    className="text-sm font-bold"
                    style={{ color: serviceOverlaySummary.color }}
                  >
                    {t('topology_service_overlay_title', 'Service Map')} · {serviceOverlaySummary.name}
                  </div>
                  <div className="mt-1 text-xs text-gray-700 dark:text-gray-200">
                    {t('topology_service_overlay_desc', 'This view highlights the devices and cloud resources that belong to the selected service group so operations can review business impact in one place.')}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                    <span className="inline-flex items-center rounded-full border bg-white/80 px-2 py-1 font-bold text-gray-700 dark:bg-slate-950/30 dark:text-slate-100" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                      {t('service_groups_criticality_label', 'Criticality')}: {serviceOverlaySummary.criticality || '--'}
                    </span>
                    {serviceOverlaySummary.ownerTeam ? (
                      <span className="inline-flex items-center rounded-full border bg-white/80 px-2 py-1 font-bold text-gray-700 dark:bg-slate-950/30 dark:text-slate-100" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                        {t('service_groups_owner_team_label', 'Owner Team')}: {serviceOverlaySummary.ownerTeam}
                      </span>
                    ) : null}
                    <span className="inline-flex items-center rounded-full border bg-white/80 px-2 py-1 font-bold text-gray-700 dark:bg-slate-950/30 dark:text-slate-100" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                      {t('topology_intent_impact_nodes', 'Impacted Nodes')}: {serviceOverlaySummary.impactedNodeCount}
                    </span>
                    <span className="inline-flex items-center rounded-full border bg-white/80 px-2 py-1 font-bold text-gray-700 dark:bg-slate-950/30 dark:text-slate-100" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                      {t('topology_intent_impact_links', 'Highlighted Links')}: {serviceOverlaySummary.impactedEdgeCount}
                    </span>
                    <span className="inline-flex items-center rounded-full border bg-white/80 px-2 py-1 font-bold text-gray-700 dark:bg-slate-950/30 dark:text-slate-100" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                      {t('service_groups_health_score', 'Health Score')}: {serviceOverlaySummary.healthScore} {t(`service_groups_health_status_${serviceOverlaySummary.healthStatus || 'review'}`, serviceOverlaySummary.healthStatus || 'review')}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-4">
                    <div className="rounded-xl border bg-white/80 px-3 py-2 dark:bg-slate-950/20" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                      <div className="text-[11px] uppercase tracking-[0.18em] font-bold" style={{ color: serviceOverlaySummary.color }}>
                        {t('topology_intent_impact_nodes', 'Impacted Nodes')}
                      </div>
                      <div className="mt-1 text-lg font-black text-gray-900 dark:text-slate-100">
                        {serviceOverlaySummary.impactedNodeCount}
                      </div>
                    </div>
                    <div className="rounded-xl border bg-white/80 px-3 py-2 dark:bg-slate-950/20" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                      <div className="text-[11px] uppercase tracking-[0.18em] font-bold" style={{ color: serviceOverlaySummary.color }}>
                        {t('topology_intent_impact_confirmed_links', 'Confirmed Links')}
                      </div>
                      <div className="mt-1 text-lg font-black text-gray-900 dark:text-slate-100">
                        {serviceOverlaySummary.fullEdgeCount}
                      </div>
                    </div>
                    <div className="rounded-xl border bg-white/80 px-3 py-2 dark:bg-slate-950/20" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                      <div className="text-[11px] uppercase tracking-[0.18em] font-bold" style={{ color: serviceOverlaySummary.color }}>
                        {t('topology_intent_impact_boundary_links', 'Boundary Links')}
                      </div>
                      <div className="mt-1 text-lg font-black text-gray-900 dark:text-slate-100">
                        {serviceOverlaySummary.boundaryEdgeCount}
                      </div>
                    </div>
                    <div className="rounded-xl border bg-white/80 px-3 py-2 dark:bg-slate-950/20" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                      <div className="text-[11px] uppercase tracking-[0.18em] font-bold" style={{ color: serviceOverlaySummary.color }}>
                        {t('service_groups_health_active_issues', 'Active issues')}
                      </div>
                      <div className="mt-1 text-lg font-black text-gray-900 dark:text-slate-100">
                        {serviceOverlaySummary.activeIssueCount}
                      </div>
                      <div className="mt-1 text-[11px] text-gray-500 dark:text-slate-400">
                        {t('service_groups_health_offline_devices', 'Offline devices')}: {serviceOverlaySummary.offlineDeviceCount}
                      </div>
                    </div>
                  </div>
                  {serviceOverlaySummary.memberEntries.length > 0 ? (
                    <div className="mt-3 rounded-xl border bg-white/80 px-3 py-3 dark:bg-slate-950/20" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                      <div className="text-[11px] uppercase tracking-[0.18em] font-bold" style={{ color: serviceOverlaySummary.color }}>
                        {t('topology_service_overlay_review_nodes', 'Review service members')}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {serviceOverlaySummary.memberEntries.map((entry) => (
                          <button
                            key={`service-node-${entry.id}`}
                            type="button"
                            onClick={() => focusTopologyNodeForImpact(entry.id)}
                            className="inline-flex items-center gap-1 rounded-full border bg-white px-3 py-1.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
                            style={{ borderColor: `${serviceOverlaySummary.color}55` }}
                          >
                            <span>{entry.label}</span>
                            {entry.provider ? <span className="text-[10px] uppercase text-gray-400 dark:text-slate-400">{entry.provider}</span> : null}
                            {entry.resourceType ? <span className="text-[10px] text-gray-400 dark:text-slate-400">{entry.resourceType}</span> : null}
                          </button>
                        ))}
                        {serviceOverlaySummary.remainingMemberCount > 0 ? (
                          <span className="inline-flex items-center rounded-full border px-3 py-1.5 text-[11px] font-semibold text-gray-600 dark:border-slate-700 dark:text-slate-300" style={{ borderColor: `${serviceOverlaySummary.color}55` }}>
                            {t('topology_intent_impact_more_nodes', '+{count} more').replace('{count}', String(serviceOverlaySummary.remainingMemberCount))}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => navigate(serviceOverlaySummary.serviceGroupsPath)}
                    className="inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold text-white shadow-sm"
                    style={{ backgroundColor: serviceOverlaySummary.color, borderColor: serviceOverlaySummary.color }}
                  >
                    <GitBranch size={14} />
                    {t('topology_service_overlay_open_groups', 'Open Service Groups')}
                  </button>
                  <button
                    type="button"
                    data-testid="topology-service-overlay-open-notifications"
                    onClick={() => navigate(serviceOverlaySummary.notificationsPath)}
                    className="inline-flex items-center gap-2 rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs font-semibold text-cyan-700 shadow-sm hover:bg-cyan-100 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-200 dark:hover:bg-cyan-950/30"
                  >
                    <Bell size={14} />
                    {t('topology_service_overlay_open_notifications', 'Open service-aware alerts')}
                  </button>
                  <button
                    type="button"
                    data-testid="topology-service-overlay-open-review"
                    onClick={() => navigate(serviceOverlaySummary.operationsReportsPath)}
                    className="inline-flex items-center gap-2 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-xs font-semibold text-violet-700 shadow-sm hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-200 dark:hover:bg-violet-950/30"
                  >
                    <FileText size={14} />
                    {t('topology_service_overlay_open_review', 'Open service review')}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setServiceOverlayEnabled(false);
                      setSelectedServiceGroupId('');
                      setSelectedServiceGroupDetail(null);
                      appliedServiceGroupRef.current = '';
                    }}
                    className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-3 py-2 text-xs font-semibold text-gray-700 shadow-sm hover:bg-gray-50 dark:border-slate-700 dark:bg-[#25282c] dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    <XCircle size={14} />
                    {t('topology_service_overlay_clear', 'Clear Service Map')}
                  </button>
                </div>
              </div>
            )}

            {cloudIntentImpactSummary && (
              <div
                data-testid="topology-intent-impact-banner"
                className="rounded-2xl border border-violet-200 dark:border-violet-900/40 bg-violet-50 dark:bg-violet-950/20 px-4 py-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"
              >
                <div className="min-w-0">
                  <div className="text-sm font-bold text-violet-800 dark:text-violet-200">
                    {t('topology_intent_impact_title', 'Cloud Intent Impact Mode')}
                  </div>
                  <div className="mt-1 text-xs text-violet-700 dark:text-violet-300">
                    {t('topology_intent_impact_desc', 'This view is filtered to the cloud scope referenced by the selected intent or alert. Impacted nodes and links stay highlighted until you clear this mode.')}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                    {cloudIntentImpactSummary.provider ? (
                      <span className="inline-flex items-center px-2 py-1 rounded-full border border-violet-200 dark:border-violet-800 bg-white/80 dark:bg-violet-950/30 font-bold text-violet-700 dark:text-violet-200">
                        {t('cloud_accounts_provider', 'Provider')}: {String(cloudIntentImpactSummary.provider).toUpperCase()}
                      </span>
                    ) : null}
                    {cloudIntentImpactSummary.accountLabel ? (
                      <span className="inline-flex items-center px-2 py-1 rounded-full border border-violet-200 dark:border-violet-800 bg-white/80 dark:bg-violet-950/30 font-bold text-violet-700 dark:text-violet-200">
                        {t('cloud_detail_account', 'Account')}: {cloudIntentImpactSummary.accountLabel}
                      </span>
                    ) : null}
                    {cloudIntentImpactSummary.region ? (
                      <span className="inline-flex items-center px-2 py-1 rounded-full border border-violet-200 dark:border-violet-800 bg-white/80 dark:bg-violet-950/30 font-bold text-violet-700 dark:text-violet-200">
                        {t('cloud_detail_region', 'Region')}: {cloudIntentImpactSummary.region}
                      </span>
                    ) : null}
                    {cloudIntentImpactSummary.resourceName ? (
                      <span className="inline-flex items-center px-2 py-1 rounded-full border border-violet-200 dark:border-violet-800 bg-white/80 dark:bg-violet-950/30 font-bold text-violet-700 dark:text-violet-200">
                        {t('cloud_detail_resource_name', 'Resource')}: {cloudIntentImpactSummary.resourceName}
                      </span>
                    ) : null}
                    {cloudIntentImpactSummary.resourceTypes.length > 0 ? (
                      <span className="inline-flex items-center px-2 py-1 rounded-full border border-violet-200 dark:border-violet-800 bg-white/80 dark:bg-violet-950/30 font-bold text-violet-700 dark:text-violet-200">
                        {t('cloud_intents_resource_types', 'Resource Types')}: {cloudIntentImpactSummary.resourceTypes.join(', ')}
                      </span>
                    ) : null}
                    <span className="inline-flex items-center px-2 py-1 rounded-full border border-violet-200 dark:border-violet-800 bg-white/80 dark:bg-violet-950/30 font-bold text-violet-700 dark:text-violet-200">
                      {t('topology_intent_impact_nodes', 'Impacted Nodes')}: {cloudIntentImpactSummary.impactedNodeCount}
                    </span>
                    <span className="inline-flex items-center px-2 py-1 rounded-full border border-violet-200 dark:border-violet-800 bg-white/80 dark:bg-violet-950/30 font-bold text-violet-700 dark:text-violet-200">
                      {t('topology_intent_impact_links', 'Highlighted Links')}: {cloudIntentImpactSummary.impactedLinkCount}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-3">
                    <div className="rounded-xl border border-violet-200 dark:border-violet-900/40 bg-white/80 dark:bg-violet-950/20 px-3 py-2">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-violet-600 dark:text-violet-300 font-bold">
                        {t('topology_intent_impact_nodes', 'Impacted Nodes')}
                      </div>
                      <div className="mt-1 text-lg font-black text-violet-900 dark:text-violet-100">
                        {cloudIntentImpactSummary.impactedNodeCount}
                      </div>
                    </div>
                    <div className="rounded-xl border border-violet-200 dark:border-violet-900/40 bg-white/80 dark:bg-violet-950/20 px-3 py-2">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-violet-600 dark:text-violet-300 font-bold">
                        {t('topology_intent_impact_confirmed_links', 'Confirmed Links')}
                      </div>
                      <div className="mt-1 text-lg font-black text-violet-900 dark:text-violet-100">
                        {cloudIntentImpactSummary.fullImpactLinkCount}
                      </div>
                    </div>
                    <div className="rounded-xl border border-violet-200 dark:border-violet-900/40 bg-white/80 dark:bg-violet-950/20 px-3 py-2">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-violet-600 dark:text-violet-300 font-bold">
                        {t('topology_intent_impact_boundary_links', 'Boundary Links')}
                      </div>
                      <div className="mt-1 text-lg font-black text-violet-900 dark:text-violet-100">
                        {cloudIntentImpactSummary.partialImpactLinkCount}
                      </div>
                    </div>
                  </div>
                  {cloudIntentImpactSummary.highlightedNodeLabels.length > 0 ? (
                    <div className="mt-3 text-xs text-violet-700 dark:text-violet-300">
                      <span className="font-bold">{t('topology_intent_impact_highlighted_nodes', 'Highlighted Nodes')}:</span>{' '}
                      {cloudIntentImpactSummary.highlightedNodeLabels.join(', ')}
                    </div>
                  ) : null}
                  {cloudIntentImpactSummary.impactedNodeEntries.length > 0 ? (
                    <div className="mt-3 rounded-xl border border-violet-200 dark:border-violet-900/40 bg-white/80 dark:bg-violet-950/20 px-3 py-3">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-violet-600 dark:text-violet-300 font-bold">
                        {t('topology_intent_impact_review_nodes', 'Review impacted nodes')}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {cloudIntentImpactSummary.impactedNodeEntries.map((entry) => (
                          <button
                            key={`impact-node-${entry.id}`}
                            type="button"
                            onClick={() => focusTopologyNodeForImpact(entry.id)}
                            className="inline-flex items-center gap-2 rounded-full border border-violet-200 dark:border-violet-800 bg-violet-100/70 dark:bg-violet-900/30 px-3 py-1.5 text-xs font-semibold text-violet-800 dark:text-violet-100 hover:bg-violet-200/80 dark:hover:bg-violet-900/50"
                          >
                            <span>{entry.label}</span>
                            {entry.provider ? (
                              <span className="rounded-full bg-white/80 dark:bg-black/20 px-2 py-0.5 text-[10px] font-black tracking-wide">
                                {entry.provider}
                              </span>
                            ) : null}
                            {entry.resourceType ? (
                              <span className="text-[10px] text-violet-700/80 dark:text-violet-200/80">
                                {entry.resourceType}
                              </span>
                            ) : null}
                          </button>
                        ))}
                        {cloudIntentImpactSummary.remainingImpactedNodeCount > 0 ? (
                          <span className="inline-flex items-center rounded-full border border-violet-200 dark:border-violet-800 bg-transparent px-3 py-1.5 text-xs font-semibold text-violet-700 dark:text-violet-200">
                            {t('topology_intent_impact_more_nodes', '+{count} more').replace('{count}', String(cloudIntentImpactSummary.remainingImpactedNodeCount))}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                  <div className="mt-2 text-xs text-violet-700 dark:text-violet-300">
                    {cloudIntentImpactSummary.nextAction}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => navigate(cloudIntentImpactSummary.cloudIntentPath)}
                    className={`${toolbarButtonBase} bg-sky-600 text-white border-sky-700 hover:bg-sky-500`}
                  >
                    <GitBranch size={14} /> {t('topology_intent_impact_open_intent', 'Open Cloud Intents')}
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate('/approval')}
                    className={`${toolbarButtonBase} bg-violet-600 text-white border-violet-700 hover:bg-violet-500`}
                  >
                    <Shield size={14} /> {t('topology_intent_impact_open_approval', 'Open Approval Center')}
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate(cloudIntentImpactSummary.cloudAccountsPath)}
                    className={`${toolbarButtonBase} ${toolbarButtonNeutral}`}
                  >
                    <Cloud size={14} /> {t('cloud_detail_open_accounts', 'Open Cloud Accounts')}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setCloudIntentImpactActive(false);
                      setImpactCloudResourceTypes([]);
                      setFocusCloudResource({ resourceId: '', resourceName: '' });
                    }}
                    className={`${toolbarButtonBase} ${toolbarButtonNeutral}`}
                  >
                    <XCircle size={14} /> {t('topology_intent_impact_clear', 'Clear Impact Mode')}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Map Area */}
      <div ref={topologyStageRef} data-testid="topology-map-stage" className="flex-1 w-full h-full relative">
        {!loading && nodes.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400 z-10">
            <InlineEmpty label={t('topology_no_data', 'No topology data available for this view.')} />
          </div>
        )}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onNodeDoubleClick={onNodeDoubleClick}
          onNodeDragStart={onNodeDragStart}
          onNodeDragStop={onNodeDragStop}
          onNodeContextMenu={onNodeContextMenu}
          onPaneClick={onPaneClick}
          onPaneContextMenu={onPaneContextMenu}
          onEdgeClick={onEdgeClick}
          onEdgeContextMenu={onEdgeContextMenu}
          onEdgeMouseEnter={onEdgeMouseEnter}
          onEdgeMouseLeave={onEdgeMouseLeave}
          onEdgeMouseMove={onEdgeMouseMove}
          onSelectionChange={onSelectionChange}
          selectionKeyCode={manualEditMode ? 'Shift' : null}
          multiSelectionKeyCode={manualEditMode ? 'Shift' : null}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onInit={(inst) => { reactFlowInstanceRef.current = inst; }}
          fitView
          snapToGrid={manualEditMode && editorSnapEnabled}
          snapGrid={[TOPOLOGY_GRID_SIZE, TOPOLOGY_GRID_SIZE]}
          className="bg-gray-50 dark:bg-[#0e1012]"
          minZoom={0.1}
        >
          <MiniMap nodeColor="#aaa" maskColor="rgba(0, 0, 0, 0.1)" />
          <Controls />
          <Background color="#ccc" gap={20} size={1} />

          {showOverlaySummary && (
            <Panel position="top-right" className="m-4">
              <div
                data-testid="overlay-topology-summary"
                className="w-[292px] rounded-2xl border border-cyan-200 bg-white/95 p-4 shadow-xl backdrop-blur dark:border-cyan-900/70 dark:bg-[#0d1820]/95"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-cyan-500">
                      {t('topology_overlay_focus', 'Overlay Focus')}
                    </div>
                    <div className="mt-1 text-sm font-bold text-gray-900 dark:text-white">
                      {t('topology_overlay_summary', 'VXLAN / EVPN Summary')}
                    </div>
                  </div>
                  <div
                    data-testid="overlay-summary-total"
                    className="rounded-xl bg-cyan-100 px-2.5 py-1 text-[11px] font-bold text-cyan-700 dark:bg-cyan-950/60 dark:text-cyan-200"
                  >
                    {overlayViewSummary.totalTunnels} {t('topology_overlay_tunnels', 'tunnels')}
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 dark:border-emerald-900/70 dark:bg-emerald-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-emerald-600 dark:text-emerald-300">
                      {t('topology_overlay_up', 'Up')}
                    </div>
                    <div data-testid="overlay-summary-up" className="mt-1 text-lg font-bold text-emerald-700 dark:text-emerald-200">{overlayViewSummary.active}</div>
                  </div>
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900/70 dark:bg-amber-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-amber-600 dark:text-amber-300">
                      {t('topology_overlay_degraded', 'Degraded')}
                    </div>
                    <div data-testid="overlay-summary-degraded" className="mt-1 text-lg font-bold text-amber-700 dark:text-amber-200">{overlayViewSummary.degraded}</div>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/60">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-300">
                      {t('topology_overlay_nodes', 'Nodes')}
                    </div>
                    <div data-testid="overlay-summary-nodes" className="mt-1 text-lg font-bold text-slate-700 dark:text-slate-100">{overlayViewSummary.nodes}</div>
                  </div>
                  <div className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 dark:border-sky-900/70 dark:bg-sky-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-sky-600 dark:text-sky-300">
                      {t('topology_overlay_vnis', 'VNIs')}
                    </div>
                    <div data-testid="overlay-summary-vnis" className="mt-1 text-lg font-bold text-sky-700 dark:text-sky-200">{overlayViewSummary.vnis}</div>
                  </div>
                  <div className="rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-2 dark:border-cyan-900/70 dark:bg-cyan-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-cyan-600 dark:text-cyan-300">
                      {t('topology_overlay_l2vni', 'L2 VNI')}
                    </div>
                    <div data-testid="overlay-summary-l2vni" className="mt-1 text-lg font-bold text-cyan-700 dark:text-cyan-200">{overlayViewSummary.l2vni}</div>
                  </div>
                  <div className="rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 dark:border-violet-900/70 dark:bg-violet-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-violet-600 dark:text-violet-300">
                      {t('topology_overlay_l3vni', 'L3 VNI')}
                    </div>
                    <div data-testid="overlay-summary-l3vni" className="mt-1 text-lg font-bold text-violet-700 dark:text-violet-200">{overlayViewSummary.l3vni}</div>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1 text-[11px] font-bold text-gray-700 dark:border-gray-700 dark:bg-[#25282c] dark:text-gray-200">
                    VTEP {overlayViewSummary.vteps}
                  </span>
                  <span className="rounded-full border border-teal-200 bg-teal-50 px-2 py-1 text-[11px] font-bold text-teal-700 dark:border-teal-900/70 dark:bg-teal-950/30 dark:text-teal-200">
                    EVPN {overlayViewSummary.evpn}
                  </span>
                  {overlayViewSummary.transports.length > 0 ? overlayViewSummary.transports.map((transport) => (
                    <span
                      key={transport}
                      className="rounded-full border border-cyan-200 bg-cyan-50 px-2 py-1 text-[11px] font-bold text-cyan-700 dark:border-cyan-900/70 dark:bg-cyan-950/30 dark:text-cyan-200"
                    >
                      {transport}
                    </span>
                  )) : (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {t('topology_overlay_transport_none', 'No transport metadata')}
                    </span>
                  )}
                </div>
              </div>
            </Panel>
          )}

          {showHybridSummary && (
            <Panel position="top-right" className="m-4">
              <div
                data-testid="hybrid-topology-summary"
                className="w-[304px] rounded-2xl border border-sky-200 bg-white/95 p-4 shadow-xl backdrop-blur dark:border-sky-900/70 dark:bg-[#0c1623]/95"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-sky-500">
                      {t('topology_hybrid_focus', 'Hybrid Focus')}
                    </div>
                    <div className="mt-1 text-sm font-bold text-gray-900 dark:text-white">
                      {t('topology_hybrid_summary', 'Cloud / Hybrid Summary')}
                    </div>
                  </div>
                  <div
                    data-testid="hybrid-summary-total-links"
                    className="rounded-xl bg-sky-100 px-2.5 py-1 text-[11px] font-bold text-sky-700 dark:bg-sky-950/60 dark:text-sky-200"
                  >
                    {hybridViewSummary.totalLinks} {t('topology_hybrid_links', 'links')}
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 dark:border-indigo-900/70 dark:bg-indigo-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-indigo-600 dark:text-indigo-300">
                      {t('topology_hybrid_peer_links', 'Peer')}
                    </div>
                    <div data-testid="hybrid-summary-peer-links" className="mt-1 text-lg font-bold text-indigo-700 dark:text-indigo-200">{hybridViewSummary.peerLinks}</div>
                  </div>
                  <div className="rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-2 dark:border-cyan-900/70 dark:bg-cyan-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-cyan-600 dark:text-cyan-300">
                      {t('topology_hybrid_inventory_links', 'Inventory')}
                    </div>
                    <div data-testid="hybrid-summary-inventory-links" className="mt-1 text-lg font-bold text-cyan-700 dark:text-cyan-200">{hybridViewSummary.inventoryLinks}</div>
                  </div>
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900/70 dark:bg-amber-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-amber-600 dark:text-amber-300">
                      {t('topology_hybrid_degraded', 'Degraded')}
                    </div>
                    <div data-testid="hybrid-summary-degraded" className="mt-1 text-lg font-bold text-amber-700 dark:text-amber-200">{hybridViewSummary.degraded}</div>
                  </div>
                  <div className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 dark:border-sky-900/70 dark:bg-sky-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-sky-600 dark:text-sky-300">
                      {t('topology_hybrid_cloud_nodes', 'Cloud')}
                    </div>
                    <div data-testid="hybrid-summary-cloud-nodes" className="mt-1 text-lg font-bold text-sky-700 dark:text-sky-200">{hybridViewSummary.cloudNodes}</div>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/60">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-300">
                      {t('topology_hybrid_onprem_nodes', 'On-Prem')}
                    </div>
                    <div data-testid="hybrid-summary-onprem-nodes" className="mt-1 text-lg font-bold text-slate-700 dark:text-slate-100">{hybridViewSummary.onPremNodes}</div>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/60">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-300">
                      {t('topology_hybrid_accounts', 'Accounts')}
                    </div>
                    <div data-testid="hybrid-summary-accounts" className="mt-1 text-lg font-bold text-slate-700 dark:text-slate-100">{hybridViewSummary.accounts}</div>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  <span className="rounded-full border border-sky-200 bg-sky-50 px-2 py-1 text-[11px] font-bold text-sky-700 dark:border-sky-900/70 dark:bg-sky-950/30 dark:text-sky-200">
                    {t('topology_hybrid_regions', 'Regions')} {hybridViewSummary.regions}
                  </span>
                  {hybridViewSummary.providers.length > 0 ? hybridViewSummary.providers.map((provider) => (
                    <span
                      key={provider}
                      className="rounded-full border border-blue-200 bg-blue-50 px-2 py-1 text-[11px] font-bold text-blue-700 dark:border-blue-900/70 dark:bg-blue-950/30 dark:text-blue-200"
                    >
                      {String(provider).toUpperCase()}
                    </span>
                  )) : (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {t('topology_hybrid_no_provider', 'No provider metadata')}
                    </span>
                  )}
                </div>
              </div>
            </Panel>
          )}

          {showBgpSummary && (
            <Panel position="top-right" className="m-4">
              <div
                data-testid="bgp-topology-summary"
                className="w-[280px] rounded-2xl border border-fuchsia-200 bg-white/95 p-4 shadow-xl backdrop-blur dark:border-fuchsia-900/70 dark:bg-[#17111d]/95"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-fuchsia-500">
                      {t('topology_bgp_focus', 'BGP Focus')}
                    </div>
                    <div className="mt-1 text-sm font-bold text-gray-900 dark:text-white">
                      {t('topology_bgp_sessions', 'Routing Session Summary')}
                    </div>
                  </div>
                  <div
                    data-testid="bgp-summary-total-sessions"
                    className="rounded-xl bg-fuchsia-100 px-2.5 py-1 text-[11px] font-bold text-fuchsia-700 dark:bg-fuchsia-950/60 dark:text-fuchsia-200"
                  >
                    {bgpViewSummary.totalSessions} {t('topology_bgp_session_count', 'sessions')}
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 dark:border-emerald-900/70 dark:bg-emerald-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-emerald-600 dark:text-emerald-300">
                      {t('topology_bgp_up', 'Up')}
                    </div>
                    <div data-testid="bgp-summary-up" className="mt-1 text-lg font-bold text-emerald-700 dark:text-emerald-200">{bgpViewSummary.established}</div>
                  </div>
                  <div className="rounded-xl border border-fuchsia-200 bg-fuchsia-50 px-3 py-2 dark:border-fuchsia-900/70 dark:bg-fuchsia-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-fuchsia-600 dark:text-fuchsia-300">
                      {t('topology_bgp_ebgp', 'eBGP')}
                    </div>
                    <div data-testid="bgp-summary-ebgp" className="mt-1 text-lg font-bold text-fuchsia-700 dark:text-fuchsia-200">{bgpViewSummary.ebgp}</div>
                  </div>
                  <div className="rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 dark:border-violet-900/70 dark:bg-violet-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-violet-600 dark:text-violet-300">
                      {t('topology_bgp_ibgp', 'iBGP')}
                    </div>
                    <div data-testid="bgp-summary-ibgp" className="mt-1 text-lg font-bold text-violet-700 dark:text-violet-200">{bgpViewSummary.ibgp}</div>
                  </div>
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900/70 dark:bg-amber-950/30">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-amber-600 dark:text-amber-300">
                      {t('topology_bgp_degraded', 'Degraded')}
                    </div>
                    <div data-testid="bgp-summary-degraded" className="mt-1 text-lg font-bold text-amber-700 dark:text-amber-200">{bgpViewSummary.degraded}</div>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/60">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-300">
                      {t('topology_bgp_nodes', 'Nodes')}
                    </div>
                    <div data-testid="bgp-summary-nodes" className="mt-1 text-lg font-bold text-slate-700 dark:text-slate-100">{bgpViewSummary.nodes}</div>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/60">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-300">
                      {t('topology_bgp_unknown', 'Unknown')}
                    </div>
                    <div data-testid="bgp-summary-unknown" className="mt-1 text-lg font-bold text-slate-700 dark:text-slate-100">{bgpViewSummary.unknown}</div>
                  </div>
                </div>

                <div className="mt-3">
                  <div className="text-[11px] font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    {t('topology_bgp_asn_scope', 'Observed ASNs')}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {bgpViewSummary.asns.length > 0 ? bgpViewSummary.asns.map((asn) => (
                      <span
                        key={asn}
                        className="rounded-full border border-fuchsia-200 bg-fuchsia-50 px-2 py-1 text-[11px] font-bold text-fuchsia-700 dark:border-fuchsia-900/70 dark:bg-fuchsia-950/30 dark:text-fuchsia-200"
                      >
                        AS{asn}
                      </span>
                    )) : (
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {t('topology_bgp_no_asn', 'No ASN metadata')}
                      </span>
                    )}
                    {bgpViewSummary.moreAsnCount > 0 && (
                      <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1 text-[11px] font-bold text-gray-600 dark:border-gray-700 dark:bg-[#25282c] dark:text-gray-300">
                        +{bgpViewSummary.moreAsnCount}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </Panel>
          )}

          <Panel position="bottom-left" className="pointer-events-none bg-white/90 p-2 rounded shadow text-xs text-gray-500">
            <div>{t('topology_hover_links', 'Hover over links to see details.')}</div>
          </Panel>

          {/* Legend Panel */}
          <Panel position="bottom-right" className="pointer-events-none bg-white/90 dark:bg-[#1b1d1f]/90 p-3 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 text-xs text-gray-600 dark:text-gray-300 backdrop-blur-sm m-4 z-50">
            <h4 className="font-bold mb-2 flex items-center gap-1.5 border-b pb-1 dark:border-gray-700 text-gray-800 dark:text-gray-200">
              <Info size={14} /> {t('topology_legend', 'Legend')}
            </h4>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-blue-50 text-blue-600 border border-blue-200">
                  <Globe size={14} />
                </div>
                <span>{t('topology_legend_core', 'Core')}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-cyan-50 text-cyan-600 border border-cyan-200">
                  <Layers size={14} />
                </div>
                <span>{t('topology_legend_dist', 'Dist')}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-[#fdf4ff] text-[#9333ea] border border-[#9333ea]">
                  <Wifi size={14} />
                </div>
                <span>{t('topology_legend_wlc', 'WLC')}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-red-50 text-red-500 border border-red-200">
                  <Shield size={14} />
                </div>
                <span>{t('topology_legend_security', 'Security')}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-amber-50 text-amber-500 border border-amber-200">
                  <Box size={14} />
                </div>
                <span>{t('topology_legend_domestic', 'Domestic')}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-white text-gray-500 border border-gray-300">
                  <Box size={14} />
                </div>
                <span>{t('topology_legend_access', 'Access')}</span>
              </div>
            </div>
            <div className="mt-3 border-t border-gray-200 pt-2 dark:border-gray-700">
              <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                {t('topology_management_scope', 'Management Scope')}
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <div className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
                    {t('devices_filter_managed', 'Managed')}
                  </div>
                  <span>{t('topology_managed_node_desc', 'This node currently uses one NetSphere Free managed slot for active monitoring, alerts, and diagnosis.')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-bold text-slate-700">
                    {t('devices_filter_discovered_only', 'Discovered Only')}
                  </div>
                  <span>{t('topology_discovered_only_legend', 'Visible in inventory and topology, but active monitoring is disabled until a managed slot is assigned.')}</span>
                </div>
              </div>
            </div>
            <div className="mt-3 border-t border-gray-200 pt-2 dark:border-gray-700">
              <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                {t('topology_service_overlay_title', 'Service Map')}
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <div className="rounded-full border px-2 py-0.5 text-[10px] font-bold" style={{ borderColor: serviceOverlayColor, color: serviceOverlayColor, background: `${String(serviceOverlayColor)}18` }}>
                    {t('topology_service_overlay_badge', 'SERVICE')}
                  </div>
                  <span>{t('topology_service_overlay_desc', 'This view highlights the devices and cloud resources that belong to the selected service group so operations can review business impact in one place.')}</span>
                </div>
              </div>
            </div>
            <div className="mt-3 border-t border-gray-200 pt-2 dark:border-gray-700">
              <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                {t('topology_legend_routing_links', 'Routing Links')}
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <div className="h-0 w-8 border-t-[3px] border-fuchsia-500 rounded-full" />
                  <span>{t('topology_legend_bgp_ebgp', 'BGP eBGP')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-0 w-8 border-t-[3px] border-violet-500 rounded-full" style={{ borderTopStyle: 'dashed' }} />
                  <span>{t('topology_legend_bgp_ibgp', 'BGP iBGP')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-0 w-8 border-t-[3px] border-amber-500 rounded-full" style={{ borderTopStyle: 'dashed' }} />
                  <span>{t('topology_legend_ospf', 'OSPF')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-0 w-8 border-t-[3px] border-cyan-500 rounded-full" style={{ borderTopStyle: 'dashed' }} />
                  <span>{t('topology_legend_overlay', 'VXLAN / EVPN')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-0 w-8 border-t-[3px] border-sky-500 rounded-full" style={{ borderTopStyle: 'dashed' }} />
                  <span>{t('topology_hybrid_summary', 'Cloud / Hybrid Summary')}</span>
                </div>
              </div>
            </div>
          </Panel>

          {/* Path Trace Panel Overlay */}
          {showPathTrace && (
            <Suspense fallback={null}>
              <PathTracePanel
                setShowPathTrace={setShowPathTrace}
                srcIp={srcIp}
                setSrcIp={setSrcIp}
                dstIp={dstIp}
                setDstIp={setDstIp}
                handleTrace={handleTrace}
                tracing={tracing}
                pathResult={pathResult}
                clearTrace={clearTrace}
                pathPlayback={pathPlayback}
                setPathPlayback={setPathPlayback}
                setPathActiveEdgeIndex={setPathActiveEdgeIndex}
                pathPlaybackSpeed={pathPlaybackSpeed}
                setPathPlaybackSpeed={setPathPlaybackSpeed}
                pathBadgesEnabled={pathBadgesEnabled}
                setPathBadgesEnabled={setPathBadgesEnabled}
                pathEdgeLabelMaxLen={pathEdgeLabelMaxLen}
                setPathEdgeLabelMaxLen={setPathEdgeLabelMaxLen}
                pathEdgeLabelTruncateMode={pathEdgeLabelTruncateMode}
                setPathEdgeLabelTruncateMode={setPathEdgeLabelTruncateMode}
                pathEvidenceOpen={pathEvidenceOpen}
                setPathEvidenceOpen={setPathEvidenceOpen}
                buildEvidenceParts={buildEvidenceParts}
                pathActiveEdgeIndex={pathActiveEdgeIndex}
              />
            </Suspense>
          )}
          {showFlowInsight && (
            <Suspense fallback={null}>
              <FlowInsightPanel
                showPathTrace={showPathTrace}
                setShowFlowInsight={setShowFlowInsight}
                flowWindowSec={flowWindowSec}
                setFlowWindowSec={setFlowWindowSec}
                loadFlowInsight={loadFlowInsight}
                flowLoading={flowLoading}
                flowTalkers={flowTalkers}
                flowApps={flowApps}
                flowSelectedApp={flowSelectedApp}
                setFlowSelectedApp={setFlowSelectedApp}
                flowFlows={flowFlows}
                flowAppLoading={flowAppLoading}
                flowSelectedAppFlows={flowSelectedAppFlows}
                formatBps={formatBps}
              />
            </Suspense>
          )}
          {cloudOrgFilter.enabled && cloudOrgFilter.org && (
            <Panel position="top-left" className="m-4">
              <div className="bg-white/90 border border-amber-200 rounded-xl shadow px-3 py-2 text-sm text-gray-800 flex items-center gap-2">
                <div className="font-bold text-amber-700">ORG</div>
                <div className="max-w-[360px] truncate" title={cloudOrgFilter.org}>{cloudOrgFilter.org}</div>
                <button
                  onClick={() => setCloudOrgFilter({ enabled: false, org: '' })}
                  className="ml-1 px-2 py-0.5 rounded bg-amber-100 hover:bg-amber-200 text-amber-800 text-xs font-bold"
                >
                  Clear
                </button>
              </div>
            </Panel>
          )}

          <Suspense fallback={null}>
            <EndpointGroupPanel
              endpointGroupPanel={endpointGroupPanel}
              setEndpointGroupPanel={setEndpointGroupPanel}
              showPathTrace={showPathTrace}
            />
          </Suspense>

          {showCandidates && (
            <Suspense fallback={null}>
              <CandidatePanel
                setShowCandidates={setShowCandidates}
                candidateJobId={candidateJobId}
                setCandidateJobId={setCandidateJobId}
                candidateSearch={candidateSearch}
                setCandidateSearch={setCandidateSearch}
                candidateStatusFilter={candidateStatusFilter}
                setCandidateStatusFilter={setCandidateStatusFilter}
                candidateSiteId={candidateSiteId}
                setCandidateSiteId={setCandidateSiteId}
                candidateTrendDays={candidateTrendDays}
                setCandidateTrendDays={setCandidateTrendDays}
                candidateOrderBy={candidateOrderBy}
                setCandidateOrderBy={setCandidateOrderBy}
                candidateOrderDir={candidateOrderDir}
                setCandidateOrderDir={setCandidateOrderDir}
                loadCandidates={loadCandidates}
                candidateLoading={candidateLoading}
                candidateSourceDeviceId={candidateSourceDeviceId}
                setCandidateSourceDeviceId={setCandidateSourceDeviceId}
                candidateAutoRefresh={candidateAutoRefresh}
                setCandidateAutoRefresh={setCandidateAutoRefresh}
                selectedCandidateIds={selectedCandidateIds}
                setSelectedCandidateIds={setSelectedCandidateIds}
                candidates={candidates}
                setCandidates={setCandidates}
                candidateEdits={candidateEdits}
                setCandidateEdits={setCandidateEdits}
                candidateRecommendations={candidateRecommendations}
                setCandidateRecommendations={setCandidateRecommendations}
                candidateRecOpen={candidateRecOpen}
                setCandidateRecOpen={setCandidateRecOpen}
                candidateRecLoading={candidateRecLoading}
                setCandidateRecLoading={setCandidateRecLoading}
                candidateActionError={candidateActionError}
                setCandidateActionError={setCandidateActionError}
                candidateSummaryLoading={candidateSummaryLoading}
                candidateSummary={candidateSummary}
                candidateTrend={candidateTrend}
                sites={sites}
                toast={toast}
                navigate={navigate}
              />
            </Suspense>
          )}
        </ReactFlow>

        <TopologyEditorBoundary
          resetKey={`${editorBoundaryKey}:${manualEditMode ? 'on' : 'off'}`}
          onError={handleEditorBoundaryError}
          onRecover={recoverEditorBoundary}
          onReset={() => setEditorBoundaryKey((prev) => prev + 1)}
        >
          <Suspense fallback={null}>
            <TopologyGroupResizeOverlay
              enabled={manualEditMode}
              groups={groupNodesForOverlay}
              stageRef={topologyStageRef}
              reactFlowInstanceRef={reactFlowInstanceRef}
              onResizeGroup={resizeNodeFrame}
              resolveResizeFrame={(nodeId, patch) => resolveResizeFrame(nodeId, patch, nodes)}
              onOpenGroupEditor={handleGroupFocusById}
            />
          </Suspense>

          {contextMenu && manualEditMode && (
            <TopologyContextMenu
              position={{ x: contextMenu.x, y: contextMenu.y }}
              targetNode={contextMenu.node}
              targetEdge={contextMenu.edge}
              isMultiSelect={multiSelectedNodes.length > 1}
              multiSelectCount={multiSelectedNodes.length}
              actions={{
                onUndo: performUndo,
                onRedo: performRedo,
                canUndo,
                canRedo,
                onEditNode: (node) => { setSelectedTopologyNode(node); setContextMenu(null); },
                onEditEdge: (edge) => { setSelectedTopologyEdge(edge); setContextMenu(null); },
                onStartLink: (node) => { setSelectedTopologyNode(node); setContextMenu(null); },
                onDeleteManualGroup: (id) => { pushSnapshot(nodes, layoutManualEdges); deleteManualGroup(id); },
                onDeleteManualEdge: (id) => { pushSnapshot(nodes, layoutManualEdges); deleteManualEdge(id); },
                onHideAutoEdge: hideAutoEdge,
                onShowAutoEdge: showAutoEdge,
                onFitGroupToChildren: fitGroupToChildren,
                onArrangeGroupChildren: arrangeGroupChildren,
                onCreateManualGroup: () => { pushSnapshot(nodes, layoutManualEdges); createManualGroup(); },
                onSnapNodesToGrid: () => { pushSnapshot(nodes, layoutManualEdges); snapNodesToGrid(); },
                onTidyTopologyCanvas: () => { pushSnapshot(nodes, layoutManualEdges); tidyTopologyCanvas(); },
                onResolveOverlaps: () => { pushSnapshot(nodes, layoutManualEdges); resolveTopologyOverlaps(); },
                onSmartAutoLayout: () => { pushSnapshot(nodes, layoutManualEdges); smartAutoLayout('TB'); },
                onGroupSelected: handleGroupSelected,
                onSaveLayout: () => saveLayoutRef.current?.(),
              }}
              onClose={() => setContextMenu(null)}
            />
          )}

          <TopologyShortcutHint visible={manualEditMode} />

          <Suspense fallback={null}>
            <TopologyEditPanel
              enabled={manualEditMode}
              selectedNode={selectedTopologyNode}
              selectedEdge={selectedTopologyEdge}
              editableNodes={editableNodeOptions}
              selectedNodeSizing={selectedNodeSizing}
              selectedGroupDiagnostics={selectedGroupDiagnostics}
              nodeOverride={selectedNodeOverride}
              edgeOverride={selectedEdgeOverride}
              edgeHidden={selectedEdgeHidden}
              selectedEdgeWarning={selectedEdgeWarning}
              warningCount={manualWarningCount}
              onCreateManualGroup={createManualGroup}
              onUpdateManualGroup={updateManualGroup}
              onDeleteManualGroup={deleteManualGroup}
              onResizeNode={resizeNodeFrame}
              onFitGroupToChildren={fitGroupToChildren}
              onArrangeGroupChildren={arrangeGroupChildren}
              onResolveOverlaps={resolveTopologyOverlaps}
              onSnapNodesToGrid={snapNodesToGrid}
              onTidyTopologyCanvas={tidyTopologyCanvas}
              snapGridEnabled={editorSnapEnabled}
              onToggleSnapGrid={setEditorSnapEnabled}
              onSaveNodeOverride={saveNodeOverride}
              onClearNodeOverride={clearNodeOverride}
              onCreateManualEdge={createManualEdge}
              onUpdateEdge={updateManualEdge}
              onDeleteManualEdge={deleteManualEdge}
              onHideAutoEdge={hideAutoEdge}
              onShowAutoEdge={showAutoEdge}
              onSaveEdgeOverride={saveEdgeOverride}
              onClearEdgeOverride={clearEdgeOverride}
            />
          </Suspense>
        </TopologyEditorBoundary>

        <TopologyPanelBoundary
          resetKey={`node:${manualEditMode ? 'off' : (selectedTopologyNode?.id || 'none')}`}
          onClose={() => setSelectedTopologyNode(null)}
        >
          <NodePanel
            node={manualEditMode ? null : selectedTopologyNode}
            onClose={() => setSelectedTopologyNode(null)}
            canManageNodes={isOperator()}
            activeServiceGroup={serviceOverlaySummary}
            onOpenServiceGroups={() => navigate('/service-groups')}
            onOpenDevice={(deviceId) => {
              if (!deviceId) return;
              navigate(`/devices/${deviceId}`);
            }}
            onOpenObservability={(deviceId, siteId) => {
              navigate(buildObservabilityPath({ deviceId, siteId }));
            }}
            onOpenGrafana={(deviceId, siteId) => {
              window.open(buildGrafanaFleetHealthUrl({ deviceId, siteId }), '_blank', 'noopener,noreferrer');
            }}
            onPromoteManaged={handlePromoteManagedNode}
            onReleaseManaged={handleReleaseManagedNode}
            onOpenEditionCompare={() => navigate('/edition/compare')}
          />
        </TopologyPanelBoundary>

        {/* Tooltip */}
        {tooltip && (
          <div
            className="fixed z-50 bg-black/80 text-white text-xs p-3 rounded-lg shadow-xl backdrop-blur-sm pointer-events-none transform -translate-x-1/2 -translate-y-full mt-[-10px]"
            style={{ left: tooltip.x, top: tooltip.y }}
          >
            <div className="font-bold mb-1 border-b border-gray-600 pb-1 text-yellow-400">
              {tooltip.label}
            </div>
            <ul className="space-y-0.5">
              {tooltip.content.map((port, idx) => (
                <li key={idx} className="whitespace-nowrap flex items-center gap-2">
                  <span className="w-1 h-1 bg-green-400 rounded-full inline-block"></span>
                  {port}
                </li>
              ))}
            </ul>
          </div>
        )}

        <TopologyPanelBoundary
          resetKey={`cloud:${cloudDetailPanel?.open ? (cloudDetailPanel?.node?.id || 'open') : 'closed'}`}
          onClose={() => setCloudDetailPanel({ open: false, node: null })}
        >
          <Suspense fallback={null}>
            <CloudDetailPanel
              cloudDetailPanel={cloudDetailPanel}
              setCloudDetailPanel={setCloudDetailPanel}
            />
          </Suspense>
        </TopologyPanelBoundary>

        <Suspense fallback={null}>
          <EdgeDetailPanel
            edgeDetailPanel={edgeDetailPanel}
            setEdgeDetailPanel={setEdgeDetailPanel}
            setEdgeEventDiff={setEdgeEventDiff}
            setShowCandidates={setShowCandidates}
            setCandidateStatusFilter={setCandidateStatusFilter}
            setCandidateSourceDeviceId={setCandidateSourceDeviceId}
            setCandidateSearch={setCandidateSearch}
            edgeEventWindowMin={edgeEventWindowMin}
            setEdgeEventWindowMin={setEdgeEventWindowMin}
            edgeEventStateFilter={edgeEventStateFilter}
            setEdgeEventStateFilter={setEdgeEventStateFilter}
            fetchLinkEvents={fetchLinkEvents}
            filteredEdgeEvents={filteredEdgeEvents}
            onEdgeEventClick={onEdgeEventClick}
            edgeEventDiff={edgeEventDiff}
            relatedSnapshotDiff={relatedSnapshotDiff}
            onRelatedDiffClick={onRelatedDiffClick}
          />
        </Suspense>

      </div>
    </div>
  );
};

export default TopologyPage;
