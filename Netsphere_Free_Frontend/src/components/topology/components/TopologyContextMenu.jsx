import React, { useEffect, useRef, useCallback } from 'react';
import {
  Trash2,
  PencilLine,
  Copy,
  EyeOff,
  Eye,
  Undo2,
  Redo2,
  Save,
  LayoutGrid,
  Link2,
  Box,
  GitBranch,
} from 'lucide-react';
import { t } from '../../../i18n';

/**
 * Right-click context menu for the topology editor.
 */
const TopologyContextMenu = ({
  position,
  targetNode,
  targetEdge,
  isMultiSelect = false,
  multiSelectCount = 0,
  actions = {},
  onClose,
}) => {
  const menuRef = useRef(null);

  useEffect(() => {
    const handleClose = () => onClose?.();
    const handleKey = (e) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('mousedown', handleClose);
    window.addEventListener('keydown', handleKey);
    window.addEventListener('scroll', handleClose, true);
    return () => {
      window.removeEventListener('mousedown', handleClose);
      window.removeEventListener('keydown', handleKey);
      window.removeEventListener('scroll', handleClose, true);
    };
  }, [onClose]);

  useEffect(() => {
    if (!menuRef.current) return;
    const rect = menuRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (rect.right > vw) {
      menuRef.current.style.left = `${Math.max(4, position.x - rect.width)}px`;
    }
    if (rect.bottom > vh) {
      menuRef.current.style.top = `${Math.max(4, position.y - rect.height)}px`;
    }
  }, [position]);

  const Item = useCallback(({
    icon: Icon,
    label,
    onClick,
    danger = false,
    disabled = false,
  }) => (
    <button
      disabled={disabled}
      onMouseDown={(e) => {
        e.stopPropagation();
        if (!disabled) {
          onClick?.();
          onClose?.();
        }
      }}
      className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-semibold rounded-lg transition-colors text-left
        ${disabled ? 'text-slate-600 cursor-not-allowed' : ''}
        ${danger && !disabled ? 'text-rose-400 hover:bg-rose-500/15' : ''}
        ${!danger && !disabled ? 'text-slate-200 hover:bg-white/10' : ''}
      `}
    >
      <Icon size={14} className="shrink-0" />
      <span className="truncate">{label}</span>
    </button>
  ), [onClose]);

  const Divider = () => <div className="h-px bg-slate-700/60 mx-2 my-1" />;

  if (!position) return null;

  const isManualGroup = targetNode?.type === 'groupNode' && !!targetNode?.data?.manualBox;
  const isManualEdge = !!targetEdge?.data?.manual;
  const isAutoEdge = !!targetEdge && !isManualEdge;
  const edgeHidden = isAutoEdge && !!targetEdge?.data?.hidden;

  return (
    <div
      ref={menuRef}
      style={{ left: position.x, top: position.y }}
      className="fixed z-[9999] min-w-[200px] max-w-[260px] rounded-xl border border-slate-700/80 bg-[#1a1e25]/98 shadow-2xl backdrop-blur-xl py-1.5 animate-scale-in"
      onContextMenu={(e) => e.preventDefault()}
    >
      {isMultiSelect && !targetEdge && (
        <>
          <div className="px-3 py-1.5 text-[10px] font-bold text-cyan-400 uppercase tracking-widest">
            {multiSelectCount} {t('topology_ctx_nodes_selected', 'nodes selected')}
          </div>
          <Item icon={LayoutGrid} label={t('topology_ctx_align_grid', 'Snap to Grid')} onClick={actions.onSnapNodesToGrid} />
          <Item icon={Box} label={t('topology_ctx_group_selected', 'Group into Box')} onClick={actions.onGroupSelected} />
          <Divider />
        </>
      )}

      {targetNode && !targetEdge && (
        <>
          <div className="px-3 py-1.5 text-[10px] font-bold text-cyan-400 uppercase tracking-widest truncate">
            {targetNode?.data?.node_label || targetNode?.data?.label || String(targetNode.id).slice(0, 24)}
          </div>
          <Item icon={PencilLine} label={t('topology_ctx_edit_node', 'Edit Node')} onClick={() => actions.onEditNode?.(targetNode)} />
          <Item icon={Link2} label={t('topology_ctx_create_link', 'Create Link From Here')} onClick={() => actions.onStartLink?.(targetNode)} />
          <Item
            icon={Copy}
            label={t('topology_ctx_copy_id', 'Copy Node ID')}
            onClick={() => {
              navigator.clipboard?.writeText?.(String(targetNode.id));
            }}
          />
          {isManualGroup ? (
            <>
              <Divider />
              <Item icon={LayoutGrid} label={t('topology_ctx_fit_children', 'Fit to Children')} onClick={() => actions.onFitGroupToChildren?.(targetNode.id)} />
              <Item icon={LayoutGrid} label={t('topology_ctx_arrange_children', 'Arrange Children')} onClick={() => actions.onArrangeGroupChildren?.(targetNode.id)} />
              <Item icon={Trash2} label={t('topology_ctx_delete_group', 'Delete Group Box')} onClick={() => actions.onDeleteManualGroup?.(targetNode.id)} danger />
            </>
          ) : null}
          <Divider />
        </>
      )}

      {targetEdge && (
        <>
          <div className="px-3 py-1.5 text-[10px] font-bold text-cyan-400 uppercase tracking-widest truncate">
            {`${targetEdge.source} -> ${targetEdge.target}`}
          </div>
          <Item icon={PencilLine} label={t('topology_ctx_edit_link', 'Edit Link')} onClick={() => actions.onEditEdge?.(targetEdge)} />
          {isManualEdge ? (
            <Item icon={Trash2} label={t('topology_ctx_delete_link', 'Delete Link')} onClick={() => actions.onDeleteManualEdge?.(targetEdge.id)} danger />
          ) : null}
          {isAutoEdge ? (
            <Item
              icon={edgeHidden ? Eye : EyeOff}
              label={edgeHidden ? t('topology_ctx_show_link', 'Show Link') : t('topology_ctx_hide_link', 'Hide Link')}
              onClick={() => (edgeHidden ? actions.onShowAutoEdge?.(targetEdge.layoutKey) : actions.onHideAutoEdge?.(targetEdge.layoutKey))}
            />
          ) : null}
          <Divider />
        </>
      )}

      <Item icon={Undo2} label={`${t('topology_ctx_undo', 'Undo')}  Ctrl+Z`} onClick={actions.onUndo} disabled={!actions.canUndo?.()} />
      <Item icon={Redo2} label={`${t('topology_ctx_redo', 'Redo')}  Ctrl+Y`} onClick={actions.onRedo} disabled={!actions.canRedo?.()} />
      <Divider />
      <Item icon={Box} label={t('topology_ctx_add_group', 'Add Group Box')} onClick={actions.onCreateManualGroup} />
      <Item icon={LayoutGrid} label={t('topology_ctx_tidy', 'Tidy Canvas')} onClick={actions.onTidyTopologyCanvas} />
      <Item icon={LayoutGrid} label={t('topology_ctx_resolve_overlaps', 'Resolve Overlaps')} onClick={actions.onResolveOverlaps} />
      <Item icon={GitBranch} label={t('topology_ctx_smart_layout', 'Smart Layout')} onClick={actions.onSmartAutoLayout} />
      <Divider />
      <Item icon={Save} label={`${t('topology_ctx_save', 'Save Layout')}  Ctrl+S`} onClick={actions.onSaveLayout} />
    </div>
  );
};

export default TopologyContextMenu;
