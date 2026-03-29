import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const EDGE_POSITIONS = ['top', 'right', 'bottom', 'left'];
const CORNER_POSITIONS = ['top-left', 'top-right', 'bottom-left', 'bottom-right'];

const getCursor = (position) => {
  if (position === 'top' || position === 'bottom') return 'ns-resize';
  if (position === 'left' || position === 'right') return 'ew-resize';
  if (position === 'top-left' || position === 'bottom-right') return 'nwse-resize';
  return 'nesw-resize';
};

const buildEdgeStyle = (group, position, isActive) => {
  const thickness = 18;
  const base = {
    position: 'absolute',
    zIndex: 70,
    pointerEvents: 'auto',
    touchAction: 'none',
    cursor: getCursor(position),
    background: isActive ? 'rgba(34, 211, 238, 0.12)' : 'rgba(34, 211, 238, 0.04)',
    opacity: isActive ? 1 : 0.55,
  };
  if (position === 'top') {
    return {
      ...base,
      left: group.left,
      top: group.top - thickness / 2,
      width: group.width,
      height: thickness,
      borderTop: '2px dashed rgba(34, 211, 238, 0.95)',
    };
  }
  if (position === 'bottom') {
    return {
      ...base,
      left: group.left,
      top: group.top + group.height - thickness / 2,
      width: group.width,
      height: thickness,
      borderBottom: '2px dashed rgba(34, 211, 238, 0.95)',
    };
  }
  if (position === 'left') {
    return {
      ...base,
      left: group.left - thickness / 2,
      top: group.top,
      width: thickness,
      height: group.height,
      borderLeft: '2px dashed rgba(34, 211, 238, 0.95)',
    };
  }
  return {
    ...base,
    left: group.left + group.width - thickness / 2,
    top: group.top,
    width: thickness,
    height: group.height,
    borderRight: '2px dashed rgba(34, 211, 238, 0.95)',
  };
};

const buildCornerStyle = (group, position, isActive) => {
  const size = 14;
  const base = {
    position: 'absolute',
    zIndex: 75,
    width: size,
    height: size,
    borderRadius: 999,
    border: '2px solid #cffafe',
    background: '#0891b2',
    boxShadow: isActive ? '0 0 0 3px rgba(6, 182, 212, 0.2)' : '0 0 0 2px rgba(6, 182, 212, 0.15)',
    pointerEvents: 'auto',
    touchAction: 'none',
    cursor: getCursor(position),
    opacity: isActive ? 1 : 0.85,
  };
  if (position === 'top-left') {
    return { ...base, left: group.left - size / 2, top: group.top - size / 2 };
  }
  if (position === 'top-right') {
    return { ...base, left: group.left + group.width - size / 2, top: group.top - size / 2 };
  }
  if (position === 'bottom-left') {
    return { ...base, left: group.left - size / 2, top: group.top + group.height - size / 2 };
  }
  return { ...base, left: group.left + group.width - size / 2, top: group.top + group.height - size / 2 };
};

const TopologyGroupResizeOverlay = ({
  enabled,
  groups,
  stageRef,
  reactFlowInstanceRef,
  onResizeGroup,
  resolveResizeFrame,
  onOpenGroupEditor,
}) => {
  const [screenGroups, setScreenGroups] = useState([]);
  const [hovered, setHovered] = useState({ id: '', position: '' });
  const dragSessionRef = useRef(null);

  const captureVisualContentMinimums = useCallback((screenGroup) => {
    const stage = stageRef?.current;
    if (!stage || !screenGroup) return { contentMinWidth: 0, contentMinHeight: 0 };
    const groupElement = stage.querySelector(`[data-testid="topology-group-node-editable"][data-node-id="${String(screenGroup.id || '')}"]`);
      const groupRect = groupElement instanceof HTMLElement
      ? groupElement.getBoundingClientRect()
      : null;
    if (!groupRect || !groupRect.width || !groupRect.height) {
      return { contentMinWidth: 0, contentMinHeight: 0 };
    }
    const groupLeft = groupRect.left;
    const groupTop = groupRect.top;
    const groupRight = groupRect.right;
    const groupBottom = groupRect.bottom;
    const elements = Array.from(stage.querySelectorAll('.react-flow__node[data-id]'));
    let maxRight = 0;
    let maxBottom = 56;
    let found = false;
    for (const element of elements) {
      if (!(element instanceof HTMLElement)) continue;
      const nodeId = String(element.getAttribute('data-id') || '');
      if (!nodeId || nodeId === String(screenGroup.id || '')) continue;
      const rect = element.getBoundingClientRect();
      if (!rect.width || !rect.height) continue;
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      if (centerX < groupLeft || centerX > groupRight || centerY < groupTop || centerY > groupBottom) continue;
      maxRight = Math.max(maxRight, rect.right - groupLeft);
      maxBottom = Math.max(maxBottom, rect.bottom - groupTop);
      found = true;
    }
    if (!found) return { contentMinWidth: 0, contentMinHeight: 0 };
    return {
      contentMinWidth: Math.round(maxRight + 28),
      contentMinHeight: Math.round(maxBottom + 28),
    };
  }, [stageRef]);

  const applyPreviewResize = useCallback((groupId, nextFrame) => {
    const stage = stageRef?.current;
    if (!stage || !groupId) return;
    const editableNode = stage.querySelector(`[data-testid="topology-group-node-editable"][data-node-id="${String(groupId)}"]`);
    if (editableNode) {
      editableNode.style.minWidth = `${Math.round(Number(nextFrame?.width || 0))}px`;
      editableNode.style.minHeight = `${Math.round(Number(nextFrame?.height || 0))}px`;
    }
    const reactFlowNode = editableNode?.closest?.('.react-flow__node');
    if (reactFlowNode) {
      reactFlowNode.style.width = `${Math.round(Number(nextFrame?.width || 0))}px`;
      reactFlowNode.style.height = `${Math.round(Number(nextFrame?.height || 0))}px`;
      reactFlowNode.style.transform = `translate(${Math.round(Number(nextFrame?.x || 0))}px, ${Math.round(Number(nextFrame?.y || 0))}px)`;
    }
    setScreenGroups((current) => current.map((group) => (
      String(group?.id || '') === String(groupId)
        ? {
            ...group,
            width: Math.round(Number(nextFrame?.width || group.width || 0)),
            height: Math.round(Number(nextFrame?.height || group.height || 0)),
            left: group.left + (Math.round(Number(nextFrame?.x || 0)) - Math.round(Number(group?.sourceX || 0))),
            top: group.top + (Math.round(Number(nextFrame?.y || 0)) - Math.round(Number(group?.sourceY || 0))),
            sourceX: Math.round(Number(nextFrame?.x || 0)),
            sourceY: Math.round(Number(nextFrame?.y || 0)),
          }
        : group
    )));
  }, [stageRef]);

  const groupMap = useMemo(() => {
    const map = new Map();
    for (const group of Array.isArray(groups) ? groups : []) {
      map.set(String(group?.id || ''), group);
    }
    return map;
  }, [groups]);

  const refreshRects = useCallback(() => {
    if (!enabled) {
      setScreenGroups([]);
      return;
    }
    const stage = stageRef?.current;
    if (!stage) return;
    const stageRect = stage.getBoundingClientRect();
    const next = [];
    for (const [groupId, group] of groupMap.entries()) {
      const element = stage.querySelector(`[data-testid="topology-group-node-editable"][data-node-id="${groupId}"]`);
      if (!element) continue;
      const rect = element.getBoundingClientRect();
      if (!rect.width || !rect.height) continue;
      next.push({
        id: groupId,
        label: String(group?.data?.label || ''),
        left: rect.left - stageRect.left,
        top: rect.top - stageRect.top,
        width: rect.width,
        height: rect.height,
        sourceX: Math.round(Number(group?.position?.x || 0)),
        sourceY: Math.round(Number(group?.position?.y || 0)),
      });
    }
    setScreenGroups(next);
  }, [enabled, groupMap, stageRef]);

  useEffect(() => {
    if (!enabled) {
      setScreenGroups([]);
      return undefined;
    }
    refreshRects();
    const interval = window.setInterval(refreshRects, 250);
    window.addEventListener('resize', refreshRects);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener('resize', refreshRects);
    };
  }, [enabled, refreshRects]);

  const stopDrag = useCallback(() => {
    const session = dragSessionRef.current;
    if (!session) return;
    window.removeEventListener('mousemove', session.moveHandler);
    window.removeEventListener('mouseup', session.upHandler);
    window.removeEventListener('pointermove', session.moveHandler);
    window.removeEventListener('pointerup', session.upHandler);
    dragSessionRef.current = null;
  }, []);

  useEffect(() => stopDrag, [stopDrag]);

  const beginResize = useCallback((screenGroup, position, event) => {
    const sourceGroup = groupMap.get(String(screenGroup?.id || ''));
    if (!sourceGroup || !onResizeGroup) return;
    event.preventDefault();
    event.stopPropagation();

    const zoom = Number(reactFlowInstanceRef?.current?.getViewport?.()?.zoom || 1) || 1;
    const startWidth = Number(sourceGroup?.width || sourceGroup?.style?.width || 0) || 160;
    const startHeight = Number(sourceGroup?.height || sourceGroup?.style?.height || 0) || 96;
    const startX = Number(sourceGroup?.position?.x || 0);
    const startY = Number(sourceGroup?.position?.y || 0);
    const startClientX = Number(event.clientX || 0);
    const startClientY = Number(event.clientY || 0);
    const visualContentMinimums = captureVisualContentMinimums(screenGroup);

    setHovered({ id: String(screenGroup.id), position });

    const moveHandler = (moveEvent) => {
      const deltaX = (Number(moveEvent.clientX || 0) - startClientX) / zoom;
      const deltaY = (Number(moveEvent.clientY || 0) - startClientY) / zoom;
      let nextWidth = startWidth;
      let nextHeight = startHeight;
      let nextNodeX = startX;
      let nextNodeY = startY;

      if (position.includes('right')) {
        nextWidth = Math.max(160, startWidth + deltaX);
      }
      if (position.includes('left')) {
        nextWidth = Math.max(160, startWidth - deltaX);
        nextNodeX = startX + (startWidth - nextWidth);
      }
      if (position.includes('bottom')) {
        nextHeight = Math.max(96, startHeight + deltaY);
      }
      if (position.includes('top')) {
        nextHeight = Math.max(96, startHeight - deltaY);
        nextNodeY = startY + (startHeight - nextHeight);
      }

      const resolvedFrame = typeof resolveResizeFrame === 'function'
        ? resolveResizeFrame(String(screenGroup.id), {
          width: Math.round(nextWidth),
          height: Math.round(nextHeight),
          x: Math.round(nextNodeX),
          y: Math.round(nextNodeY),
          anchor: position,
          baseX: Math.round(startX),
          baseY: Math.round(startY),
          baseWidth: Math.round(startWidth),
          baseHeight: Math.round(startHeight),
          contentMinWidth: visualContentMinimums.contentMinWidth,
          contentMinHeight: visualContentMinimums.contentMinHeight,
        })
        : null;
      const previewFrame = resolvedFrame || {
        width: Math.round(nextWidth),
        height: Math.round(nextHeight),
        x: Math.round(nextNodeX),
        y: Math.round(nextNodeY),
      };

      onResizeGroup(String(screenGroup.id), {
        width: previewFrame.width,
        height: previewFrame.height,
        x: previewFrame.x,
        y: previewFrame.y,
      });
      applyPreviewResize(String(screenGroup.id), previewFrame);
    };

    const upHandler = () => {
      stopDrag();
      window.setTimeout(() => refreshRects(), 0);
    };

    dragSessionRef.current = { moveHandler, upHandler };
    window.addEventListener('mousemove', moveHandler);
    window.addEventListener('mouseup', upHandler);
    window.addEventListener('pointermove', moveHandler);
    window.addEventListener('pointerup', upHandler);
  }, [captureVisualContentMinimums, groupMap, onResizeGroup, reactFlowInstanceRef, resolveResizeFrame, stopDrag]);

  if (!enabled || screenGroups.length === 0) return null;

  return (
    <div className="pointer-events-none absolute inset-0 z-[65]">
      {screenGroups.map((group) => {
        const hoveredGroup = hovered.id === group.id;
        return (
          <React.Fragment key={group.id}>
            <div
              className="pointer-events-none absolute rounded-xl"
              style={{
                left: group.left,
                top: group.top,
                width: group.width,
                height: group.height,
                boxShadow: hoveredGroup ? 'inset 0 0 0 2px rgba(34, 211, 238, 0.85)' : 'none',
              }}
            />
            <button
              type="button"
              data-testid="topology-group-overlay-open-editor"
              data-group-label={group.label}
              data-node-id={group.id}
              className="pointer-events-auto absolute rounded-full border border-cyan-400/60 bg-slate-950/90 px-2.5 py-1 text-[11px] font-semibold text-cyan-100 shadow-lg hover:bg-cyan-900/70"
              style={{
                left: group.left + Math.max(10, group.width - 96),
                top: Math.max(8, group.top - 14),
                zIndex: 76,
              }}
              onMouseDown={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onOpenGroupEditor?.(String(group.id || ''));
              }}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onOpenGroupEditor?.(String(group.id || ''));
              }}
            >
              Edit
            </button>
            {EDGE_POSITIONS.map((position) => (
              <div
                key={`${group.id}-${position}`}
                data-testid={`topology-group-overlay-${position}`}
                data-group-label={group.label}
                data-node-id={group.id}
                style={buildEdgeStyle(group, position, hoveredGroup && hovered.position === position)}
                onMouseEnter={() => setHovered({ id: group.id, position })}
                onMouseLeave={() => setHovered((current) => (current.id === group.id && current.position === position ? { id: '', position: '' } : current))}
                onMouseDown={(event) => beginResize(group, position, event)}
                onPointerDown={(event) => beginResize(group, position, event)}
              />
            ))}
            {CORNER_POSITIONS.map((position) => (
              <div
                key={`${group.id}-${position}`}
                data-testid={`topology-group-overlay-${position}`}
                data-group-label={group.label}
                data-node-id={group.id}
                style={buildCornerStyle(group, position, hoveredGroup && hovered.position === position)}
                onMouseEnter={() => setHovered({ id: group.id, position })}
                onMouseLeave={() => setHovered((current) => (current.id === group.id && current.position === position ? { id: '', position: '' } : current))}
                onMouseDown={(event) => beginResize(group, position, event)}
                onPointerDown={(event) => beginResize(group, position, event)}
              />
            ))}
          </React.Fragment>
        );
      })}
    </div>
  );
};

export default TopologyGroupResizeOverlay;
