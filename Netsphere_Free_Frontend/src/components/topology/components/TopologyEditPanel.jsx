import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Box,
  Link2,
  LayoutGrid,
  PencilLine,
  PlusSquare,
  RotateCcw,
  Save,
  Trash2,
  Unlink,
  EyeOff,
} from 'lucide-react';
import { t } from '../../../i18n';

const iconRoleOptions = [
  { value: '', label: t('topology_icon_auto', 'Auto') },
  { value: 'core', label: t('topology_icon_core', 'Core') },
  { value: 'distribution', label: t('topology_icon_distribution', 'Distribution') },
  { value: 'security', label: t('topology_icon_security', 'Security') },
  { value: 'wlc', label: t('topology_icon_wlc', 'WLC') },
  { value: 'access_domestic', label: t('topology_icon_access', 'Access') },
  { value: 'access_point', label: t('topology_icon_access_point', 'Access Point') },
  { value: 'cloud', label: t('topology_icon_cloud', 'Cloud') },
];

const edgeKindOptions = [
  { value: 'manual', label: t('topology_manual_link_manual', 'Manual') },
  { value: 'l2', label: 'L2' },
  { value: 'l3', label: 'L3' },
  { value: 'hybrid', label: t('topology_manual_link_hybrid', 'Hybrid') },
];

const edgeCurveOptions = [
  { value: 'default', label: t('topology_edge_curve_default', 'Default') },
  { value: 'smoothstep', label: t('topology_edge_curve_smooth', 'Smooth') },
  { value: 'step', label: t('topology_edge_curve_step', 'Step') },
  { value: 'straight', label: t('topology_edge_curve_straight', 'Straight') },
];

const edgeLineStyleOptions = [
  { value: 'solid', label: t('topology_edge_line_solid', 'Solid') },
  { value: 'dashed', label: t('topology_edge_line_dashed', 'Dashed') },
  { value: 'dotted', label: t('topology_edge_line_dotted', 'Dotted') },
];

const sectionClass = 'rounded-2xl border border-slate-800 bg-slate-900/90 p-4';
const inputClass = 'w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-500';
const buttonClass = 'inline-flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold transition-colors';
const asColorInputValue = (value, fallback) => {
  const text = String(value || '').trim();
  return text.startsWith('#') ? text : fallback;
};

const TopologyEditPanel = ({
  enabled,
  selectedNode,
  selectedEdge,
  editableNodes,
  selectedNodeSizing,
  selectedGroupDiagnostics,
  nodeOverride,
  edgeOverride,
  edgeHidden,
  selectedEdgeWarning,
  warningCount,
  onCreateManualGroup,
  onUpdateManualGroup,
  onDeleteManualGroup,
  onResizeNode,
  onFitGroupToChildren,
  onArrangeGroupChildren,
  onResolveOverlaps,
  onSnapNodesToGrid,
  onTidyTopologyCanvas,
  snapGridEnabled,
  onToggleSnapGrid,
  onSaveNodeOverride,
  onClearNodeOverride,
  onCreateManualEdge,
  onUpdateEdge,
  onDeleteManualEdge,
  onHideAutoEdge,
  onShowAutoEdge,
  onSaveEdgeOverride,
  onClearEdgeOverride,
}) => {
  const [nodeLabel, setNodeLabel] = useState('');
  const [nodeIconRole, setNodeIconRole] = useState('');
  const [nodeFontSize, setNodeFontSize] = useState('12');
  const [nodeWrapMode, setNodeWrapMode] = useState('wrap');
  const [groupLabel, setGroupLabel] = useState('');
  const [groupFillColor, setGroupFillColor] = useState('#e0f2fe');
  const [groupBorderColor, setGroupBorderColor] = useState('#0284c7');
  const [groupFontSize, setGroupFontSize] = useState('14');
  const [groupWrapMode, setGroupWrapMode] = useState('wrap');
  const [linkTargetId, setLinkTargetId] = useState('');
  const [linkLabel, setLinkLabel] = useState('');
  const [linkKind, setLinkKind] = useState('manual');
  const [linkColor, setLinkColor] = useState('#0f172a');
  const [linkWidth, setLinkWidth] = useState('3');
  const [linkCurve, setLinkCurve] = useState('default');
  const [linkLineStyle, setLinkLineStyle] = useState('solid');
  const [linkLabelPosition, setLinkLabelPosition] = useState('50');
  const [linkLabelOffsetY, setLinkLabelOffsetY] = useState('0');
  const [edgeLabel, setEdgeLabel] = useState('');
  const [edgeKind, setEdgeKind] = useState('manual');
  const [edgeColor, setEdgeColor] = useState('#0f172a');
  const [edgeWidth, setEdgeWidth] = useState('3');
  const [edgeCurve, setEdgeCurve] = useState('default');
  const [edgeLineStyle, setEdgeLineStyle] = useState('solid');
  const [edgeLabelPosition, setEdgeLabelPosition] = useState('50');
  const [edgeLabelOffsetY, setEdgeLabelOffsetY] = useState('0');
  const [nodeWidth, setNodeWidth] = useState('');
  const [nodeHeight, setNodeHeight] = useState('');
  const [groupWidth, setGroupWidth] = useState('');
  const [groupHeight, setGroupHeight] = useState('');

  const isManualGroup = selectedNode?.type === 'groupNode' && !!selectedNode?.data?.manualBox;
  const isAutoGroup = selectedNode?.type === 'groupNode' && !selectedNode?.data?.manualBox;
  const selectedNodeMinWidth = Math.max(140, Number(selectedNodeSizing?.minWidth || 0) || 140);
  const selectedNodeMinHeight = Math.max(88, Number(selectedNodeSizing?.minHeight || 0) || 88);
  const selectedGroupMinWidth = Math.max(160, Number(selectedNodeSizing?.minWidth || 0) || 160);
  const selectedGroupMinHeight = Math.max(96, Number(selectedNodeSizing?.minHeight || 0) || 96);
  const groupDiagnosticsTone = Number(selectedGroupDiagnostics?.overflowCount || 0) > 0 ? 'warning' : (selectedGroupDiagnostics?.isTight ? 'info' : 'ok');
  const groupDiagnosticsClass = groupDiagnosticsTone === 'warning'
    ? 'border-amber-500/30 bg-amber-500/10 text-amber-100'
    : groupDiagnosticsTone === 'info'
      ? 'border-sky-500/30 bg-sky-500/10 text-sky-100'
      : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100';
  const requestedGroupWidth = Number(groupWidth || 0) || selectedGroupMinWidth;
  const requestedGroupHeight = Number(groupHeight || 0) || selectedGroupMinHeight;
  const groupWidthWillClamp = requestedGroupWidth < selectedGroupMinWidth;
  const groupHeightWillClamp = requestedGroupHeight < selectedGroupMinHeight;
  const groupHasOverflow = Number(selectedGroupDiagnostics?.overflowCount || 0) > 0;
  const groupNeedsAttention = groupHasOverflow || groupWidthWillClamp || groupHeightWillClamp;
  const groupSizeGuardClass = groupNeedsAttention
    ? 'border-amber-500/30 bg-amber-500/10 text-amber-100'
    : 'border-slate-800 bg-slate-950/70 text-slate-300';

  useEffect(() => {
    if (!selectedNode || isManualGroup) {
      setNodeLabel('');
      setNodeIconRole('');
      setNodeFontSize('12');
      setNodeWrapMode('wrap');
      setLinkTargetId('');
      setLinkLabel('');
      setLinkKind('manual');
      setLinkColor('#0f172a');
      setLinkWidth('3');
      setLinkCurve('default');
      setLinkLineStyle('solid');
      setLinkLabelPosition('50');
      setLinkLabelOffsetY('0');
      return;
    }
    setNodeLabel(nodeOverride?.label || '');
    setNodeIconRole(nodeOverride?.iconRole || '');
    setNodeFontSize(String(nodeOverride?.fontSize || selectedNode?.style?.fontSize || 12).replace('px', ''));
    setNodeWrapMode(String(nodeOverride?.wrapMode || 'wrap').trim().toLowerCase() === 'single' ? 'single' : 'wrap');
    setLinkTargetId('');
    setLinkLabel('');
    setLinkKind('manual');
    setLinkColor('#0f172a');
    setLinkWidth('3');
    setLinkCurve('default');
    setLinkLineStyle('solid');
    setLinkLabelPosition('50');
    setLinkLabelOffsetY('0');
  }, [selectedNode?.id, selectedNode?.style?.fontSize, nodeOverride?.label, nodeOverride?.iconRole, nodeOverride?.fontSize, nodeOverride?.wrapMode, isManualGroup]);

  useEffect(() => {
    if (!selectedNode || isManualGroup) {
      setNodeWidth('');
      setNodeHeight('');
      return;
    }
    setNodeWidth(String(selectedNodeSizing?.width || ''));
    setNodeHeight(String(selectedNodeSizing?.height || ''));
  }, [selectedNode?.id, isManualGroup, selectedNodeSizing?.width, selectedNodeSizing?.height]);

  useEffect(() => {
    if (!selectedNode || selectedNode?.type !== 'groupNode') {
      setGroupLabel('');
      setGroupFillColor('#e0f2fe');
      setGroupBorderColor('#0284c7');
      setGroupFontSize('14');
      setGroupWrapMode('wrap');
      return;
    }
    setGroupLabel(String(selectedNode?.data?.label || '').trim());
    setGroupFillColor(asColorInputValue(selectedNode?.style?.backgroundColor, '#e0f2fe'));
    const border = String(selectedNode?.style?.border || '').trim();
    const borderMatch = border.match(/(#[0-9a-fA-F]{3,8}|rgba?\([^)]+\))/);
    setGroupBorderColor(asColorInputValue(borderMatch?.[1], '#0284c7'));
    setGroupFontSize(String(selectedNode?.style?.fontSize || 14).replace('px', ''));
    setGroupWrapMode(String(selectedNode?.data?.labelWrapMode || 'wrap').trim().toLowerCase() === 'single' ? 'single' : 'wrap');
  }, [selectedNode?.type, selectedNode?.id, selectedNode?.data?.label, selectedNode?.data?.labelWrapMode, selectedNode?.style?.backgroundColor, selectedNode?.style?.border, selectedNode?.style?.fontSize]);

  useEffect(() => {
    if (!selectedNode || selectedNode?.type !== 'groupNode') {
      setGroupWidth('');
      setGroupHeight('');
      return;
    }
    setGroupWidth(String(selectedNodeSizing?.width || ''));
    setGroupHeight(String(selectedNodeSizing?.height || ''));
  }, [selectedNode?.type, selectedNode?.id, selectedNodeSizing?.width, selectedNodeSizing?.height]);

  useEffect(() => {
    if (!selectedEdge) {
      setEdgeLabel('');
      setEdgeKind('manual');
      setEdgeColor('#0f172a');
      setEdgeWidth('3');
      setEdgeCurve('default');
      setEdgeLineStyle('solid');
      setEdgeLabelPosition('50');
      setEdgeLabelOffsetY('0');
      return;
    }
    setEdgeLabel(edgeOverride?.label || selectedEdge?.data?.manualLabel || selectedEdge?.data?.fullLabel || selectedEdge?.label || '');
    setEdgeKind(String(selectedEdge?.data?.kind || 'manual'));
    setEdgeColor(String(edgeOverride?.color || selectedEdge?.data?.manualColor || selectedEdge?.style?.stroke || '#0f172a'));
    setEdgeWidth(String(edgeOverride?.width || selectedEdge?.data?.manualWidth || selectedEdge?.style?.strokeWidth || 3));
    setEdgeCurve(String(edgeOverride?.curve || selectedEdge?.data?.manualCurve || selectedEdge?.type || 'default'));
    setEdgeLabelPosition(String(edgeOverride?.labelPosition || selectedEdge?.data?.manualLabelPosition || selectedEdge?.data?.labelPosition || 50));
    setEdgeLabelOffsetY(String(edgeOverride?.labelOffsetY || selectedEdge?.data?.manualLabelOffsetY || selectedEdge?.data?.labelOffsetY || 0));
    if (String(edgeOverride?.lineStyle || '').trim()) {
      setEdgeLineStyle(String(edgeOverride.lineStyle));
    } else if (String(selectedEdge?.data?.manualLineStyle || '').trim()) {
      setEdgeLineStyle(String(selectedEdge.data.manualLineStyle));
    } else if (String(selectedEdge?.style?.strokeDasharray || '').trim()) {
      setEdgeLineStyle(String(selectedEdge.style.strokeDasharray).includes('3') ? 'dotted' : 'dashed');
    } else {
      setEdgeLineStyle('solid');
    }
  }, [selectedEdge?.id, edgeOverride?.label, edgeOverride?.color, edgeOverride?.width, edgeOverride?.curve, edgeOverride?.lineStyle, edgeOverride?.labelPosition, edgeOverride?.labelOffsetY, selectedEdge?.data?.kind, selectedEdge?.data?.manualLabel, selectedEdge?.data?.fullLabel, selectedEdge?.data?.manualColor, selectedEdge?.data?.manualWidth, selectedEdge?.data?.manualCurve, selectedEdge?.data?.manualLineStyle, selectedEdge?.data?.manualLabelPosition, selectedEdge?.data?.manualLabelOffsetY, selectedEdge?.data?.labelPosition, selectedEdge?.data?.labelOffsetY, selectedEdge?.label, selectedEdge?.style?.stroke, selectedEdge?.style?.strokeWidth, selectedEdge?.style?.strokeDasharray, selectedEdge?.type]);

  const linkTargets = useMemo(() => {
    const currentId = String(selectedNode?.id || '');
    return (Array.isArray(editableNodes) ? editableNodes : []).filter((item) => String(item.id) !== currentId);
  }, [editableNodes, selectedNode?.id]);

  if (!enabled) return null;

  const handleSaveNode = () => {
    if (!selectedNode) return;
    onSaveNodeOverride?.(selectedNode.id, {
      label: nodeLabel,
      iconRole: nodeIconRole,
      fontSize: Number(nodeFontSize || 12),
      wrapMode: nodeWrapMode,
    });
  };

  const handleResizeNode = () => {
    if (!selectedNode) return;
    onResizeNode?.(selectedNode.id, {
      width: Math.max(selectedNodeMinWidth, Number(nodeWidth || 0) || selectedNodeMinWidth),
      height: Math.max(selectedNodeMinHeight, Number(nodeHeight || 0) || selectedNodeMinHeight),
    });
  };

  const handleSaveGroup = () => {
    if (!selectedNode || selectedNode?.type !== 'groupNode') return;
    onUpdateManualGroup?.(selectedNode.id, {
      label: groupLabel,
      fillColor: groupFillColor,
      borderColor: groupBorderColor,
      fontSize: Number(groupFontSize || 14),
      wrapMode: groupWrapMode,
    });
  };

  const handleResizeGroup = () => {
    if (!selectedNode || selectedNode?.type !== 'groupNode') return;
    onResizeNode?.(selectedNode.id, {
      width: Math.max(selectedGroupMinWidth, Number(groupWidth || 0) || selectedGroupMinWidth),
      height: Math.max(selectedGroupMinHeight, Number(groupHeight || 0) || selectedGroupMinHeight),
    });
  };

  const clampGroupWidthInput = () => {
    setGroupWidth(String(Math.max(selectedGroupMinWidth, Number(groupWidth || 0) || selectedGroupMinWidth)));
  };

  const clampGroupHeightInput = () => {
    setGroupHeight(String(Math.max(selectedGroupMinHeight, Number(groupHeight || 0) || selectedGroupMinHeight)));
  };

  const renderGroupSizeGuard = (mode = 'manual') => (
    <div className={`rounded-xl border px-3 py-3 text-[11px] ${groupSizeGuardClass}`}>
      <div className="font-semibold">
        {groupNeedsAttention
          ? t('topology_group_size_guard_attention', 'This group box is protected from shrinking below the space required by its child nodes and header area.')
          : t('topology_group_size_guard_ok', 'This group box already has enough room for its child nodes and header area.')}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
        <span>{t('topology_group_diagnostics_minimum', 'Minimum')}: {Math.round(selectedGroupMinWidth)} 횞 {Math.round(selectedGroupMinHeight)}</span>
        <span>{t('topology_group_diagnostics_current', 'Current')}: {Math.round(Number(selectedGroupDiagnostics?.currentWidth || requestedGroupWidth))} 횞 {Math.round(Number(selectedGroupDiagnostics?.currentHeight || requestedGroupHeight))}</span>
        <span>{t('topology_group_diagnostics_overflow', 'Overflow')}: {Number(selectedGroupDiagnostics?.overflowCount || 0)}</span>
      </div>
      {groupWidthWillClamp || groupHeightWillClamp ? (
        <div className="mt-2 text-[11px]">
          {t('topology_group_size_guard_clamp', 'Values below the minimum are automatically clamped when you blur the field or apply the size.')}
        </div>
      ) : null}
      {groupHasOverflow ? (
        <div className="mt-2 text-[11px]">
          {mode === 'auto'
            ? t('topology_group_size_guard_fit_auto', 'Use Fit to Children first if you want this auto group to wrap every child cleanly before saving.')
            : t('topology_group_size_guard_fit_manual', 'Use Fit to Children first if you want this manual group to wrap every child cleanly before saving.')}
        </div>
      ) : null}
    </div>
  );

  const renderEdgePreview = ({
    label,
    color,
    width,
    lineStyle,
    labelPosition,
    labelOffsetY,
    curve,
    hidden = false,
    tone = 'edge',
  }) => {
    const previewLabel = String(label || '').trim();
    const previewWidth = Math.max(2, Math.min(8, Number(width || 3) || 3));
    const previewPosition = Math.max(10, Math.min(90, Number(labelPosition || 50) || 50));
    const previewOffsetY = Math.max(-80, Math.min(80, Number(labelOffsetY || 0) || 0));
    const previewStroke = String(color || '#0f172a').trim() || '#0f172a';
    const previewDash = lineStyle === 'dashed' ? '10 6' : lineStyle === 'dotted' ? '3 7' : '';
    const previewToneClass = tone === 'manual'
      ? 'border-emerald-500/30 bg-emerald-500/10'
      : 'border-cyan-500/30 bg-cyan-500/10';

    return (
      <div className={`rounded-xl border px-3 py-3 text-[11px] text-slate-300 ${previewToneClass}`} data-testid="topology-edge-preview-card">
        <div className="flex items-center justify-between gap-3">
          <div className="font-semibold text-slate-100">
            {t('topology_edge_preview_title', 'Link preview')}
          </div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">
            {String(curve || 'default').toUpperCase()}
          </div>
        </div>
        <div className="relative mt-3 h-16 overflow-hidden rounded-xl border border-slate-800 bg-slate-950/80">
          <div
            className="absolute left-4 right-4 top-1/2 -translate-y-1/2"
            style={{
              borderTop: `${previewWidth}px ${previewDash ? 'dashed' : 'solid'} ${previewStroke}`,
              opacity: hidden ? 0.35 : 1,
            }}
          />
          {previewLabel ? (
            <div
              className="absolute -translate-x-1/2 rounded-full border px-2.5 py-1 text-[11px] font-semibold shadow-sm"
              style={{
                left: `${previewPosition}%`,
                top: `calc(50% + ${previewOffsetY}px)`,
                transform: 'translate(-50%, -50%)',
                color: previewStroke,
                borderColor: previewStroke,
                background: 'rgba(255,255,255,0.94)',
                opacity: hidden ? 0.45 : 1,
              }}
            >
              {previewLabel}
            </div>
          ) : null}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
          <span>{t('topology_edge_preview_style_fmt', 'Style: {style}').replace('{style}', t(`topology_edge_line_${String(lineStyle || 'solid').trim().toLowerCase()}`, String(lineStyle || 'solid')))}</span>
          <span>{t('topology_edge_preview_position_fmt', 'Label {position}%').replace('{position}', String(previewPosition))}</span>
          <span>{t('topology_edge_preview_offset_fmt', 'Offset {offset}px').replace('{offset}', String(previewOffsetY))}</span>
        </div>
        {hidden ? (
          <div className="mt-2 text-[11px] text-amber-200">
            {t('topology_edge_preview_hidden_hint', 'This link is currently hidden on the map. The preview shows how it will look when you show it again.')}
          </div>
        ) : null}
      </div>
    );
  };

  const handleCreateLink = () => {
    if (!selectedNode || !linkTargetId) return;
    onCreateManualEdge?.({
      source: selectedNode.id,
      target: linkTargetId,
      label: linkLabel,
      kind: linkKind,
      color: linkColor,
      width: Number(linkWidth || 3),
      curve: linkCurve,
      lineStyle: linkLineStyle,
      labelPosition: Number(linkLabelPosition || 50),
      labelOffsetY: Number(linkLabelOffsetY || 0),
    });
  };

  const handleSaveEdge = () => {
    if (!selectedEdge) return;
    if (selectedEdge?.data?.manual) {
      onUpdateEdge?.(selectedEdge.id, {
        label: edgeLabel,
        kind: edgeKind,
        color: edgeColor,
        width: Number(edgeWidth || 3),
        curve: edgeCurve,
        lineStyle: edgeLineStyle,
        labelPosition: Number(edgeLabelPosition || 50),
        labelOffsetY: Number(edgeLabelOffsetY || 0),
      });
      return;
    }
    onSaveEdgeOverride?.(selectedEdge.layoutKey, {
      label: edgeLabel,
      color: edgeColor,
      width: Number(edgeWidth || 0),
      curve: edgeCurve,
      lineStyle: edgeLineStyle,
      labelPosition: Number(edgeLabelPosition || 50),
      labelOffsetY: Number(edgeLabelOffsetY || 0),
    });
  };

  return (
    <div className="absolute left-4 top-4 bottom-4 z-[90] w-[420px] max-w-[calc(100%-2rem)] overflow-hidden rounded-2xl border border-slate-700/80 bg-[#12161c]/96 text-white shadow-2xl backdrop-blur">
      <div className="border-b border-slate-800 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-cyan-400">
              {t('topology_manual_edit', 'Manual Edit')}
            </div>
            <div className="mt-1 text-sm font-bold text-white">
              {t('topology_manual_edit_title', 'Layout Editor Workspace')}
            </div>
            <div className="mt-1 text-xs text-slate-400">
              {t('topology_manual_edit_hint', 'Use this workspace to curate labels, icons, group boxes, and link styling without changing discovered topology facts.')}
            </div>
          </div>
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-right">
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-300">
              {t('topology_editor_warnings', 'Warnings')}
            </div>
            <div className="mt-1 text-lg font-bold text-amber-100">{Number(warningCount || 0)}</div>
          </div>
        </div>

        <div className="mt-3 flex gap-2">
          <button
            onClick={() => onCreateManualGroup?.()}
            data-testid="topology-editor-add-group"
            className={`${buttonClass} flex-1 border-violet-500/30 bg-violet-500/10 text-violet-100 hover:bg-violet-500/20`}
          >
            <PlusSquare size={14} />
            {t('topology_manual_box_add', 'Add Group Box')}
          </button>
          <button
            onClick={() => onResolveOverlaps?.()}
            data-testid="topology-editor-resolve-overlaps"
            className={`${buttonClass} border-sky-500/30 bg-sky-500/10 text-sky-100 hover:bg-sky-500/20`}
          >
            <LayoutGrid size={14} />
            {t('topology_resolve_overlaps', 'Resolve Overlaps')}
          </button>
          <button
            onClick={() => onSnapNodesToGrid?.()}
            data-testid="topology-editor-snap-nodes"
            className={`${buttonClass} border-cyan-500/30 bg-cyan-500/10 text-cyan-100 hover:bg-cyan-500/20`}
          >
            <PencilLine size={14} />
            {t('topology_snap_grid', 'Snap Nodes')}
          </button>
          <button
            onClick={() => onTidyTopologyCanvas?.()}
            data-testid="topology-editor-tidy-canvas"
            className={`${buttonClass} border-indigo-500/30 bg-indigo-500/10 text-indigo-100 hover:bg-indigo-500/20`}
          >
            <LayoutGrid size={14} />
            {t('topology_tidy_canvas', 'Tidy Canvas')}
          </button>
        </div>
        <label className="mt-3 flex items-center gap-2 text-xs font-semibold text-slate-300">
          <input
            type="checkbox"
            checked={!!snapGridEnabled}
            onChange={(e) => onToggleSnapGrid?.(e.target.checked)}
            data-testid="topology-editor-snap-grid-toggle"
            className="h-4 w-4"
          />
          {t('topology_snap_grid_toggle_hint', 'Snap dragged nodes to the editor grid')}
        </label>
      </div>

      <div className="h-[calc(100%-126px)] overflow-y-auto p-4 space-y-3">
        {isManualGroup ? (
          <div className={sectionClass} data-testid="topology-editor-manual-group-panel">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
              <Box size={15} />
              {t('topology_manual_box_title', 'Selected Group Box')}
            </div>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-400">
                  {t('topology_manual_box_label', 'Box Label')}
                </label>
                <input value={groupLabel} onChange={(e) => setGroupLabel(e.target.value)} className={inputClass} data-testid="topology-editor-manual-group-label" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_manual_box_fill', 'Fill Color')}
                  </label>
                  <input type="color" value={groupFillColor} onChange={(e) => setGroupFillColor(e.target.value)} className={`${inputClass} h-11 p-1`} />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_manual_box_border', 'Border Color')}
                  </label>
                  <input type="color" value={groupBorderColor} onChange={(e) => setGroupBorderColor(e.target.value)} className={`${inputClass} h-11 p-1`} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_font_size', 'Font Size')}
                  </label>
                  <input type="number" min="11" max="24" value={groupFontSize} onChange={(e) => setGroupFontSize(e.target.value)} className={inputClass} />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_wrap_mode', 'Wrap Mode')}
                  </label>
                  <select value={groupWrapMode} onChange={(e) => setGroupWrapMode(e.target.value)} className={inputClass}>
                    <option value="wrap">{t('topology_wrap_mode_wrap', 'Auto Wrap')}</option>
                    <option value="single">{t('topology_wrap_mode_single', 'Single Line')}</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_box_width', 'Box Width')}
                  </label>
                  <input type="number" min={selectedGroupMinWidth} value={groupWidth} onChange={(e) => setGroupWidth(e.target.value)} onBlur={clampGroupWidthInput} className={inputClass} data-testid="topology-editor-manual-group-width" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_box_height', 'Box Height')}
                  </label>
                  <input type="number" min={selectedGroupMinHeight} value={groupHeight} onChange={(e) => setGroupHeight(e.target.value)} onBlur={clampGroupHeightInput} className={inputClass} data-testid="topology-editor-manual-group-height" />
                </div>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-[11px] text-slate-400">
                {t('topology_group_minimum_size_hint', 'Current minimum size keeps the box aligned with its children. Smaller values are automatically adjusted on apply.')}
                <span className="ml-2 font-mono text-slate-200">
                  {t('topology_group_minimum_size_value', 'Min {width} × {height}')
                    .replace('{width}', String(selectedGroupMinWidth))
                    .replace('{height}', String(selectedGroupMinHeight))}
                </span>
              </div>
              {renderGroupSizeGuard('manual')}
              {selectedGroupDiagnostics ? (
                <div className={`rounded-xl border px-3 py-3 text-[11px] ${groupDiagnosticsClass}`}>
                  <div className="font-semibold">
                    {Number(selectedGroupDiagnostics.overflowCount || 0) > 0
                      ? t('topology_group_diagnostics_warning', 'Some child nodes are outside the current box bounds.')
                      : t('topology_group_diagnostics_ok', 'Current box bounds are aligned with the child nodes.')}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
                    <span>{t('topology_group_diagnostics_children', 'Children')}: {Number(selectedGroupDiagnostics.childCount || 0)}</span>
                    <span>{t('topology_group_diagnostics_overflow', 'Overflow')}: {Number(selectedGroupDiagnostics.overflowCount || 0)}</span>
                    <span>{t('topology_group_diagnostics_current', 'Current')}: {Math.round(Number(selectedGroupDiagnostics.currentWidth || 0))} × {Math.round(Number(selectedGroupDiagnostics.currentHeight || 0))}</span>
                    <span>{t('topology_group_diagnostics_minimum', 'Minimum')}: {Math.round(Number(selectedGroupDiagnostics.minWidth || 0))} × {Math.round(Number(selectedGroupDiagnostics.minHeight || 0))}</span>
                  </div>
                  {Number(selectedGroupDiagnostics.overflowCount || 0) > 0 ? (
                    <div className="mt-2 text-[11px] text-amber-200">
                      {t('topology_group_diagnostics_action_hint', 'Use Fit to Children or Arrange Children before saving if the group feels too tight.')}
                    </div>
                  ) : null}
                </div>
              ) : null}
              <div className="flex gap-2">
                <button
                  onClick={handleSaveGroup}
                  data-testid="topology-editor-manual-group-save"
                  className={`${buttonClass} flex-1 border-cyan-500/30 bg-cyan-500/10 text-cyan-100 hover:bg-cyan-500/20`}
                >
                  <Save size={14} />
                  {t('common_save', 'Save')}
                </button>
                <button
                  onClick={handleResizeGroup}
                  data-testid="topology-editor-manual-group-apply-size"
                  className={`${buttonClass} ${groupNeedsAttention ? 'border-amber-500/30 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/20'}`}
                >
                  <PencilLine size={14} />
                  {groupNeedsAttention ? t('topology_apply_size_guarded', 'Apply Guarded Size') : t('topology_apply_size', 'Apply Size')}
                </button>
                <button
                  onClick={() => onFitGroupToChildren?.(selectedNode.id)}
                  data-testid="topology-editor-manual-group-fit-children"
                  className={`${buttonClass} ${groupHasOverflow ? 'border-amber-500/30 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20' : 'border-sky-500/30 bg-sky-500/10 text-sky-100 hover:bg-sky-500/20'}`}
                >
                  <Box size={14} />
                  {t('topology_fit_children', 'Fit to Children')}
                </button>
                <button
                  onClick={() => onArrangeGroupChildren?.(selectedNode.id)}
                  data-testid="topology-editor-manual-group-arrange-children"
                  className={`${buttonClass} border-indigo-500/30 bg-indigo-500/10 text-indigo-100 hover:bg-indigo-500/20`}
                >
                  <LayoutGrid size={14} />
                  {t('topology_arrange_children', 'Arrange Children')}
                </button>
                <button
                  onClick={() => onDeleteManualGroup?.(selectedNode.id)}
                  data-testid="topology-editor-manual-group-delete"
                  className={`${buttonClass} border-rose-500/30 bg-rose-500/10 text-rose-100 hover:bg-rose-500/20`}
                >
                  <Trash2 size={14} />
                  {t('common_delete', 'Delete')}
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {isAutoGroup ? (
          <div className={sectionClass} data-testid="topology-editor-auto-group-panel">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
              <Box size={15} />
              {t('topology_auto_group_title', 'Selected Auto Group')}
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-3 text-xs text-slate-300">
              <div className="font-semibold text-white">{selectedNode?.data?.label || selectedNode?.id}</div>
              <div className="mt-2 text-slate-400">
                {t('topology_auto_group_hint', 'Resize this provider, region, or cloud container directly on the canvas. Its saved size will be preserved in the layout.')}
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-400">
                  {t('topology_font_size', 'Font Size')}
                </label>
                <input type="number" min="11" max="24" value={groupFontSize} onChange={(e) => setGroupFontSize(e.target.value)} className={inputClass} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-400">
                  {t('topology_wrap_mode', 'Wrap Mode')}
                </label>
                <select value={groupWrapMode} onChange={(e) => setGroupWrapMode(e.target.value)} className={inputClass}>
                  <option value="wrap">{t('topology_wrap_mode_wrap', 'Auto Wrap')}</option>
                  <option value="single">{t('topology_wrap_mode_single', 'Single Line')}</option>
                </select>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-400">
                  {t('topology_box_width', 'Box Width')}
                </label>
                <input type="number" min={selectedGroupMinWidth} value={groupWidth} onChange={(e) => setGroupWidth(e.target.value)} onBlur={clampGroupWidthInput} className={inputClass} data-testid="topology-editor-auto-group-width" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-400">
                  {t('topology_box_height', 'Box Height')}
                </label>
                <input type="number" min={selectedGroupMinHeight} value={groupHeight} onChange={(e) => setGroupHeight(e.target.value)} onBlur={clampGroupHeightInput} className={inputClass} data-testid="topology-editor-auto-group-height" />
              </div>
            </div>
            <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-[11px] text-slate-400">
              {t('topology_group_minimum_size_hint', 'Current minimum size keeps the box aligned with its children. Smaller values are automatically adjusted on apply.')}
              <span className="ml-2 font-mono text-slate-200">
                {t('topology_group_minimum_size_value', 'Min {width} × {height}')
                  .replace('{width}', String(selectedGroupMinWidth))
                  .replace('{height}', String(selectedGroupMinHeight))}
              </span>
            </div>
            {renderGroupSizeGuard('auto')}
            {selectedGroupDiagnostics ? (
              <div className={`mt-3 rounded-xl border px-3 py-3 text-[11px] ${groupDiagnosticsClass}`}>
                <div className="font-semibold">
                  {Number(selectedGroupDiagnostics.overflowCount || 0) > 0
                    ? t('topology_group_diagnostics_warning', 'Some child nodes are outside the current box bounds.')
                    : t('topology_group_diagnostics_ok', 'Current box bounds are aligned with the child nodes.')}
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
                  <span>{t('topology_group_diagnostics_children', 'Children')}: {Number(selectedGroupDiagnostics.childCount || 0)}</span>
                  <span>{t('topology_group_diagnostics_overflow', 'Overflow')}: {Number(selectedGroupDiagnostics.overflowCount || 0)}</span>
                  <span>{t('topology_group_diagnostics_current', 'Current')}: {Math.round(Number(selectedGroupDiagnostics.currentWidth || 0))} × {Math.round(Number(selectedGroupDiagnostics.currentHeight || 0))}</span>
                  <span>{t('topology_group_diagnostics_minimum', 'Minimum')}: {Math.round(Number(selectedGroupDiagnostics.minWidth || 0))} × {Math.round(Number(selectedGroupDiagnostics.minHeight || 0))}</span>
                </div>
                {Number(selectedGroupDiagnostics.overflowCount || 0) > 0 ? (
                  <div className="mt-2 text-[11px] text-amber-200">
                    {t('topology_group_diagnostics_action_hint', 'Use Fit to Children or Arrange Children before saving if the group feels too tight.')}
                  </div>
                ) : null}
              </div>
            ) : null}
            <button
              onClick={handleSaveGroup}
              data-testid="topology-editor-auto-group-save"
              className={`${buttonClass} mt-3 w-full border-cyan-500/30 bg-cyan-500/10 text-cyan-100 hover:bg-cyan-500/20`}
            >
              <Save size={14} />
              {t('common_save', 'Save')}
            </button>
            <button
              onClick={handleResizeGroup}
              data-testid="topology-editor-auto-group-apply-size"
              className={`${buttonClass} mt-2 w-full ${groupNeedsAttention ? 'border-amber-500/30 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/20'}`}
            >
              <PencilLine size={14} />
              {groupNeedsAttention ? t('topology_apply_size_guarded', 'Apply Guarded Size') : t('topology_apply_size', 'Apply Size')}
            </button>
            <button
              onClick={() => onFitGroupToChildren?.(selectedNode.id)}
              data-testid="topology-editor-auto-group-fit-children"
              className={`${buttonClass} mt-2 w-full ${groupHasOverflow ? 'border-amber-500/30 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20' : 'border-sky-500/30 bg-sky-500/10 text-sky-100 hover:bg-sky-500/20'}`}
            >
              <Box size={14} />
              {t('topology_fit_children', 'Fit to Children')}
            </button>
            <button
              onClick={() => onArrangeGroupChildren?.(selectedNode.id)}
              data-testid="topology-editor-auto-group-arrange-children"
              className={`${buttonClass} mt-2 w-full border-indigo-500/30 bg-indigo-500/10 text-indigo-100 hover:bg-indigo-500/20`}
            >
              <LayoutGrid size={14} />
              {t('topology_arrange_children', 'Arrange Children')}
            </button>
          </div>
        ) : null}

        {selectedNode && selectedNode?.type !== 'groupNode' ? (
          <div className={sectionClass}>
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
              <PencilLine size={15} />
              {t('topology_selected_node', 'Selected Node')}
            </div>
            <div className="mb-3 rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-300">
              <div className="font-semibold text-white">{selectedNode?.data?.node_label || selectedNode?.data?.label || selectedNode.id}</div>
              <div className="mt-1 text-slate-500">{String(selectedNode.id)}</div>
            </div>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-400">
                  {t('topology_custom_node_name', 'Custom Name')}
                </label>
                <input
                  value={nodeLabel}
                  onChange={(e) => setNodeLabel(e.target.value)}
                  placeholder={t('topology_custom_node_name_placeholder', 'Leave blank to use discovered label')}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-400">
                  {t('topology_custom_icon', 'Custom Icon')}
                </label>
                <select value={nodeIconRole} onChange={(e) => setNodeIconRole(e.target.value)} className={inputClass}>
                  {iconRoleOptions.map((item) => (
                    <option key={item.value || 'auto'} value={item.value}>{item.label}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_font_size', 'Font Size')}
                  </label>
                  <input type="number" min="11" max="22" value={nodeFontSize} onChange={(e) => setNodeFontSize(e.target.value)} className={inputClass} />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_wrap_mode', 'Wrap Mode')}
                  </label>
                  <select value={nodeWrapMode} onChange={(e) => setNodeWrapMode(e.target.value)} className={inputClass}>
                    <option value="wrap">{t('topology_wrap_mode_wrap', 'Auto Wrap')}</option>
                    <option value="single">{t('topology_wrap_mode_single', 'Single Line')}</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_node_width', 'Node Width')}
                  </label>
                  <input type="number" min={selectedNodeMinWidth} value={nodeWidth} onChange={(e) => setNodeWidth(e.target.value)} className={inputClass} />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_node_height', 'Node Height')}
                  </label>
                  <input type="number" min={selectedNodeMinHeight} value={nodeHeight} onChange={(e) => setNodeHeight(e.target.value)} className={inputClass} />
                </div>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-[11px] text-slate-400">
                {t('topology_resize_hint', 'Hover over a node or group box to reveal the dashed cyan resize guides, then drag the border or corner handles on the canvas, or set exact width and height here.')}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleSaveNode}
                  className={`${buttonClass} flex-1 border-cyan-500/30 bg-cyan-500/10 text-cyan-100 hover:bg-cyan-500/20`}
                >
                  <Save size={14} />
                  {t('common_save', 'Save')}
                </button>
                <button
                  onClick={handleResizeNode}
                  className={`${buttonClass} border-emerald-500/30 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/20`}
                >
                  <PencilLine size={14} />
                  {t('topology_apply_size', 'Apply Size')}
                </button>
                <button
                  onClick={() => onClearNodeOverride?.(selectedNode.id)}
                  className={`${buttonClass} border-slate-700 bg-slate-800/80 text-slate-200 hover:bg-slate-700`}
                >
                  <RotateCcw size={14} />
                  {t('common_reset', 'Reset')}
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {selectedNode && selectedNode?.type !== 'groupNode' ? (
          <div className={sectionClass}>
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
              <Link2 size={15} />
              {t('topology_manual_link', 'Manual Link')}
            </div>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-400">
                  {t('topology_link_target', 'Target Node')}
                </label>
                <select value={linkTargetId} onChange={(e) => setLinkTargetId(e.target.value)} className={inputClass}>
                  <option value="">{t('topology_link_target_select', 'Select target')}</option>
                  {linkTargets.map((item) => (
                    <option key={item.id} value={item.id}>{item.label}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_link_kind', 'Link Kind')}
                  </label>
                  <select value={linkKind} onChange={(e) => setLinkKind(e.target.value)} className={inputClass}>
                    {edgeKindOptions.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_link_label', 'Label')}
                  </label>
                  <input
                    value={linkLabel}
                    onChange={(e) => setLinkLabel(e.target.value)}
                    placeholder={t('topology_link_label_placeholder', 'Optional')}
                    className={inputClass}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_color', 'Edge Color')}
                  </label>
                  <input type="color" value={linkColor} onChange={(e) => setLinkColor(e.target.value)} className={`${inputClass} h-11 p-1`} />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_width', 'Thickness')}
                  </label>
                  <input type="number" min="1" max="8" value={linkWidth} onChange={(e) => setLinkWidth(e.target.value)} className={inputClass} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_curve', 'Curve')}
                  </label>
                  <select value={linkCurve} onChange={(e) => setLinkCurve(e.target.value)} className={inputClass}>
                    {edgeCurveOptions.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_line_style', 'Line Style')}
                  </label>
                  <select value={linkLineStyle} onChange={(e) => setLinkLineStyle(e.target.value)} className={inputClass}>
                    {edgeLineStyleOptions.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_label_position', 'Label Position')}
                  </label>
                  <input type="range" min="10" max="90" value={linkLabelPosition} onChange={(e) => setLinkLabelPosition(e.target.value)} className="w-full" />
                  <div className="mt-1 text-[11px] text-slate-500">{linkLabelPosition}%</div>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_label_offset', 'Label Offset')}
                  </label>
                  <input type="number" min="-80" max="80" value={linkLabelOffsetY} onChange={(e) => setLinkLabelOffsetY(e.target.value)} className={inputClass} />
                </div>
              </div>
              {renderEdgePreview({
                label: linkLabel,
                color: linkColor,
                width: linkWidth,
                lineStyle: linkLineStyle,
                labelPosition: linkLabelPosition,
                labelOffsetY: linkLabelOffsetY,
                curve: linkCurve,
                tone: 'manual',
              })}
              <button
                onClick={handleCreateLink}
                disabled={!linkTargetId}
                className={`${buttonClass} w-full border-emerald-500/30 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50`}
              >
                <Link2 size={14} />
                {t('topology_link_add', 'Add Link')}
              </button>
            </div>
          </div>
        ) : null}

        {selectedEdge ? (
          <div className={sectionClass}>
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
              <Unlink size={15} />
              {t('topology_selected_link', 'Selected Link')}
            </div>
            <div className="mb-3 rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-300">
              <div className="font-semibold text-white">{`${selectedEdge?.source || ''} -> ${selectedEdge?.target || ''}`}</div>
              <div className="mt-1 text-slate-500">
                {selectedEdge?.data?.manual ? t('topology_manual_link_manual', 'Manual') : t('topology_auto_link', 'Auto-generated')}
              </div>
            </div>

            {selectedEdgeWarning ? (
              <div className={`mb-3 rounded-2xl border px-3 py-3 text-xs ${
                selectedEdgeWarning?.tone === 'critical'
                  ? 'border-rose-500/30 bg-rose-500/10 text-rose-100'
                  : 'border-amber-500/30 bg-amber-500/10 text-amber-100'
              }`}>
                <div className="flex items-center gap-2 font-semibold">
                  <AlertTriangle size={14} />
                  {selectedEdgeWarning.badge}
                </div>
                <div className="mt-1 leading-5">{selectedEdgeWarning.message}</div>
              </div>
            ) : null}

            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-400">
                  {t('topology_link_label', 'Label')}
                </label>
                <input value={edgeLabel} onChange={(e) => setEdgeLabel(e.target.value)} className={inputClass} />
              </div>
              {selectedEdge?.data?.manual ? (
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_link_kind', 'Link Kind')}
                  </label>
                  <select value={edgeKind} onChange={(e) => setEdgeKind(e.target.value)} className={inputClass}>
                    {edgeKindOptions.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                </div>
              ) : null}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_color', 'Edge Color')}
                  </label>
                  <input type="color" value={edgeColor} onChange={(e) => setEdgeColor(e.target.value)} className={`${inputClass} h-11 p-1`} />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_width', 'Thickness')}
                  </label>
                  <input type="number" min="1" max="8" value={edgeWidth} onChange={(e) => setEdgeWidth(e.target.value)} className={inputClass} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_curve', 'Curve')}
                  </label>
                  <select value={edgeCurve} onChange={(e) => setEdgeCurve(e.target.value)} className={inputClass}>
                    {edgeCurveOptions.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_line_style', 'Line Style')}
                  </label>
                  <select value={edgeLineStyle} onChange={(e) => setEdgeLineStyle(e.target.value)} className={inputClass}>
                    {edgeLineStyleOptions.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_label_position', 'Label Position')}
                  </label>
                  <input type="range" min="10" max="90" value={edgeLabelPosition} onChange={(e) => setEdgeLabelPosition(e.target.value)} className="w-full" />
                  <div className="mt-1 text-[11px] text-slate-500">{edgeLabelPosition}%</div>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-400">
                    {t('topology_edge_label_offset', 'Label Offset')}
                  </label>
                  <input type="number" min="-80" max="80" value={edgeLabelOffsetY} onChange={(e) => setEdgeLabelOffsetY(e.target.value)} className={inputClass} />
                </div>
              </div>
              {renderEdgePreview({
                label: edgeLabel,
                color: edgeColor,
                width: edgeWidth,
                lineStyle: edgeLineStyle,
                labelPosition: edgeLabelPosition,
                labelOffsetY: edgeLabelOffsetY,
                curve: edgeCurve,
                hidden: edgeHidden,
              })}
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-[11px] text-slate-300">
                <div className="font-semibold text-slate-100">
                  {t('topology_edge_label_visibility_title', 'Label visibility guidance')}
                </div>
                <div className="mt-1 text-slate-400">
                  {edgeLabel
                    ? t('topology_edge_label_visibility_with_text', 'This label will stay visible on the link. Use position and offset to keep it clear of nearby nodes and crossings.')
                    : t('topology_edge_label_visibility_without_text', 'Leave the label blank to keep the link visually quieter. Add a label only when the circuit name or intent really needs to stay on the map.')}
                </div>
                <div className="mt-2 text-slate-500">
                  {t('topology_edge_label_visibility_preview_fmt', 'Preview: position {position}% / vertical offset {offset}px')
                    .replace('{position}', String(edgeLabelPosition))
                    .replace('{offset}', String(edgeLabelOffsetY))}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={handleSaveEdge}
                  className={`${buttonClass} flex-1 border-cyan-500/30 bg-cyan-500/10 text-cyan-100 hover:bg-cyan-500/20`}
                >
                  <Save size={14} />
                  {t('common_save', 'Save')}
                </button>
                {selectedEdge?.data?.manual ? (
                  <button
                    onClick={() => onDeleteManualEdge?.(selectedEdge.id)}
                    className={`${buttonClass} border-rose-500/30 bg-rose-500/10 text-rose-100 hover:bg-rose-500/20`}
                  >
                    <Trash2 size={14} />
                    {t('common_delete', 'Delete')}
                  </button>
                ) : (
                  <button
                    onClick={() => (edgeHidden ? onShowAutoEdge?.(selectedEdge.layoutKey) : onHideAutoEdge?.(selectedEdge.layoutKey))}
                    className={`${buttonClass} border-amber-500/30 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20`}
                  >
                    <EyeOff size={14} />
                    {edgeHidden ? t('topology_link_show', 'Show Link') : t('topology_link_hide', 'Hide Link')}
                  </button>
                )}
                {!selectedEdge?.data?.manual && (edgeOverride?.label || edgeOverride?.color || edgeOverride?.width || edgeOverride?.curve || edgeOverride?.lineStyle) ? (
                  <button
                    onClick={() => onClearEdgeOverride?.(selectedEdge.layoutKey)}
                    className={`${buttonClass} border-slate-700 bg-slate-800/80 text-slate-200 hover:bg-slate-700`}
                  >
                    <RotateCcw size={14} />
                    {t('common_reset', 'Reset')}
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        {!selectedNode && !selectedEdge ? (
          <div className={`${sectionClass} text-sm text-slate-300`}>
            {t('topology_manual_edit_empty', 'Select a node, manual box, or link to start editing. Dragging nodes updates the draft immediately, and Save Layout persists it.')}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default TopologyEditPanel;
