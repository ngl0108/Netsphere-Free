import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useViewport } from 'reactflow';

import { t } from '../../i18n';

const BASE_RESIZE_HANDLE_STYLE = {
  width: 12,
  height: 12,
  borderRadius: 999,
  border: '2px solid #cffafe',
  background: '#0891b2',
  boxShadow: '0 0 0 2px rgba(6, 182, 212, 0.25)',
};

const getResizeCursor = (position) => {
  if (position === 'top' || position === 'bottom') return 'ns-resize';
  if (position === 'left' || position === 'right') return 'ew-resize';
  if (position === 'top-left' || position === 'bottom-right') return 'nwse-resize';
  return 'nesw-resize';
};

const buildResizeLineStyle = (position, isActive, zoomScale) => {
  const stroke = '2px dashed rgba(34, 211, 238, 0.95)';
  const thickness = Math.max(14, Math.round(18 * zoomScale));
  const sideThickness = Math.max(14, Math.round(16 * zoomScale));
  const base = {
    position: 'absolute',
    zIndex: 25,
    touchAction: 'none',
    pointerEvents: 'auto',
    background: isActive ? 'rgba(34, 211, 238, 0.08)' : 'rgba(34, 211, 238, 0.03)',
    cursor: getResizeCursor(position),
    opacity: isActive ? 0.95 : 0.22,
  };
  if (position === 'top') {
    return {
      ...base,
      width: '100%',
      height: thickness,
      left: 0,
      top: 0,
      transform: 'translate(0, -50%)',
      borderTop: stroke,
    };
  }
  if (position === 'bottom') {
    return {
      ...base,
      width: '100%',
      height: thickness,
      left: 0,
      top: '100%',
      transform: 'translate(0, -50%)',
      borderBottom: stroke,
    };
  }
  if (position === 'left') {
    return {
      ...base,
      width: sideThickness,
      height: '100%',
      top: 0,
      left: 0,
      transform: 'translate(-50%, 0)',
      borderLeft: stroke,
    };
  }
  return {
    ...base,
    width: sideThickness,
    height: '100%',
    top: 0,
    left: '100%',
    transform: 'translate(-50%, 0)',
    borderRight: stroke,
  };
};

const buildResizeHandleStyle = (position, isActive, zoomScale) => {
  const size = Math.max(12, Math.round(14 * zoomScale));
  const base = {
    ...BASE_RESIZE_HANDLE_STYLE,
    width: size,
    height: size,
    position: 'absolute',
    zIndex: 30,
    touchAction: 'none',
    pointerEvents: 'auto',
    cursor: getResizeCursor(position),
    opacity: isActive ? 1 : 0.35,
  };
  if (position === 'top-left') {
    return { ...base, left: 0, top: 0, transform: 'translate(-50%, -50%)' };
  }
  if (position === 'top-right') {
    return { ...base, left: '100%', top: 0, transform: 'translate(-50%, -50%)' };
  }
  if (position === 'bottom-left') {
    return { ...base, left: 0, top: '100%', transform: 'translate(-50%, -50%)' };
  }
  return { ...base, left: '100%', top: '100%', transform: 'translate(-50%, -50%)' };
};

const resolveResizePosition = (nodeElement, clientX, clientY) => {
  if (!nodeElement) return '';
  const rect = nodeElement.getBoundingClientRect();
  const localX = Number(clientX || 0) - rect.left;
  const localY = Number(clientY || 0) - rect.top;
  const threshold = 14;
  const nearLeft = localX <= threshold;
  const nearRight = localX >= rect.width - threshold;
  const nearTop = localY <= threshold;
  const nearBottom = localY >= rect.height - threshold;

  if (nearTop && nearLeft) return 'top-left';
  if (nearTop && nearRight) return 'top-right';
  if (nearBottom && nearLeft) return 'bottom-left';
  if (nearBottom && nearRight) return 'bottom-right';
  if (nearTop) return 'top';
  if (nearBottom) return 'bottom';
  if (nearLeft) return 'left';
  if (nearRight) return 'right';
  return '';
};

const captureVisualContentMinimums = (nodeElement, nodeId) => {
  if (!(nodeElement instanceof HTMLElement)) return { contentMinWidth: 0, contentMinHeight: 0 };
  const groupRect = nodeElement.getBoundingClientRect();
  if (!groupRect.width || !groupRect.height) return { contentMinWidth: 0, contentMinHeight: 0 };
  const stage = nodeElement.closest('.react-flow') || document;
  const elements = Array.from(stage.querySelectorAll('.react-flow__node[data-id]'));
  let maxRight = 0;
  let maxBottom = 56;
  let found = false;
  for (const element of elements) {
    if (!(element instanceof HTMLElement)) continue;
    const candidateId = String(element.getAttribute('data-id') || '');
    if (!candidateId || candidateId === String(nodeId || '')) continue;
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) continue;
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    if (centerX < groupRect.left || centerX > groupRect.right || centerY < groupRect.top || centerY > groupRect.bottom) continue;
    maxRight = Math.max(maxRight, rect.right - groupRect.left);
    maxBottom = Math.max(maxBottom, rect.bottom - groupRect.top);
    found = true;
  }
  if (!found) return { contentMinWidth: 0, contentMinHeight: 0 };
  return {
    contentMinWidth: Math.round(maxRight + 28),
    contentMinHeight: Math.round(maxBottom + 28),
  };
};

const GroupNode = ({ id, data, selected, style, xPos, yPos }) => {
  const { zoom = 1 } = useViewport();
  const [open, setOpen] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [resizeHoverPosition, setResizeHoverPosition] = useState('');
  const wrapperRef = useRef(null);
  const resizeSessionRef = useRef(null);
  const orgTop = useMemo(() => (Array.isArray(data?.orgTop) ? data.orgTop : []), [data]);
  const orgCount = Number.isFinite(Number(data?.orgCount)) ? Number(data.orgCount) : orgTop.length;
  const fontSize = Math.max(12, Number(String(style?.fontSize || data?.fontSize || 14).replace('px', '')) || 14);
  const wrapMode = String(data?.labelWrapMode || 'wrap').trim().toLowerCase() === 'single' ? 'single' : 'wrap';
  const labelLength = String(data?.label || '').trim().length || 12;
  const canResize = !!data?.editorResizable;
  const canFocusGroup = canResize || typeof data?.onFocusNode === 'function';
  const minWidth = Math.max(160, Math.min(320, Math.round((wrapMode === 'single' ? labelLength * fontSize * 0.42 : 160) + 36)));
  const minHeight = Math.max(96, fontSize >= 18 ? 112 : 96);
  const resizeUiActive = selected || isHovered || isResizing || !!resizeHoverPosition;
  const showResizeHandles = canResize;
  const currentWidth = Math.round(Number(style?.width || 0) || minWidth);
  const currentHeight = Math.round(Number(style?.height || 0) || minHeight);
  const groupLabel = String(data?.label || '');
  const zoomScale = useMemo(() => {
    const nextZoom = Number(zoom);
    if (!Number.isFinite(nextZoom) || nextZoom <= 0) return 1;
    return Math.min(12, Math.max(1, 1 / nextZoom));
  }, [zoom]);

  const dispatchDirectResize = useCallback((payload) => {
    if (typeof window === 'undefined') return;
    window.dispatchEvent(new CustomEvent('netmanager:topology-direct-resize', {
      detail: {
        id,
        width: payload.width,
        height: payload.height,
        x: payload.x,
        y: payload.y,
        anchor: payload.anchor,
        baseX: payload.baseX,
        baseY: payload.baseY,
        baseWidth: payload.baseWidth,
        baseHeight: payload.baseHeight,
        contentMinWidth: payload.contentMinWidth,
        contentMinHeight: payload.contentMinHeight,
      },
    }));
  }, [id]);

  const dispatchFocusNode = useCallback(() => {
    if (typeof data?.onFocusNode === 'function') {
      data.onFocusNode(id);
      return;
    }
    if (typeof window === 'undefined') return;
    window.dispatchEvent(new CustomEvent('netmanager:topology-group-focus', {
      detail: {
        id,
      },
    }));
  }, [data?.onFocusNode, id]);

  const dispatchOpenEditor = useCallback(() => {
    if (typeof window === 'undefined') {
      dispatchFocusNode();
      return;
    }
    window.__netmanagerTopologyDebug = {
      ...(window.__netmanagerTopologyDebug || {}),
      lastOpenEditorRequestId: id,
      lastOpenEditorRequestTs: Date.now(),
    };
    window.dispatchEvent(new CustomEvent('netmanager:topology-group-open-editor', {
      detail: {
        id,
      },
    }));
  }, [dispatchFocusNode, id]);

  const activateGroupEditor = useCallback(() => {
    if (!canFocusGroup || isResizing) return;
    if (canResize) {
      dispatchOpenEditor();
      return;
    }
    dispatchFocusNode();
  }, [canFocusGroup, canResize, dispatchFocusNode, dispatchOpenEditor, isResizing]);

  const stopDirectResize = useCallback(() => {
    const session = resizeSessionRef.current;
    if (session?.moveHandler) {
      window.removeEventListener('pointermove', session.moveHandler);
      window.removeEventListener('mousemove', session.moveHandler);
    }
    if (session?.upHandler) {
      window.removeEventListener('pointerup', session.upHandler);
      window.removeEventListener('pointercancel', session.upHandler);
      window.removeEventListener('mouseup', session.upHandler);
    }
    resizeSessionRef.current = null;
    setIsResizing(false);
  }, []);

  useEffect(() => stopDirectResize, [stopDirectResize]);

  useEffect(() => {
    if (!canFocusGroup) return undefined;
    const nodeElement = wrapperRef.current;
    if (!(nodeElement instanceof HTMLElement)) return undefined;
    const handleNativeFocusCapture = (event) => {
      if (isResizing) return;
      const target = event?.target instanceof HTMLElement ? event.target : null;
      if (!target) return;
      if (target.closest('[data-testid^="topology-group-resize-control-"]')) return;
      dispatchFocusNode();
    };
    nodeElement.addEventListener('pointerdown', handleNativeFocusCapture, true);
    nodeElement.addEventListener('mousedown', handleNativeFocusCapture, true);
    return () => {
      nodeElement.removeEventListener('pointerdown', handleNativeFocusCapture, true);
      nodeElement.removeEventListener('mousedown', handleNativeFocusCapture, true);
    };
  }, [canFocusGroup, dispatchFocusNode, isResizing]);

  const updateResizeHoverPosition = useCallback((event) => {
    if (!canResize || isResizing) return;
    setResizeHoverPosition(resolveResizePosition(wrapperRef.current, event.clientX, event.clientY));
  }, [canResize, isResizing]);

  const beginDirectResize = useCallback((position, event) => {
    if (!canResize) return;
    const nodeElement = wrapperRef.current;
    if (!nodeElement || !position) return;
    event.preventDefault();
    event.stopPropagation();

    const startWidth = Number(style?.width || nodeElement.getBoundingClientRect().width || minWidth) || minWidth;
    const startHeight = Number(style?.height || nodeElement.getBoundingClientRect().height || minHeight) || minHeight;
    const startX = Number.isFinite(Number(xPos)) ? Number(xPos) : 0;
    const startY = Number.isFinite(Number(yPos)) ? Number(yPos) : 0;
    const visualContentMinimums = captureVisualContentMinimums(nodeElement, id);

    setIsResizing(true);
    setIsHovered(true);
    setResizeHoverPosition(position);

    const moveHandler = (moveEvent) => {
      const deltaX = Number(moveEvent.clientX || 0) - Number(event.clientX || 0);
      const deltaY = Number(moveEvent.clientY || 0) - Number(event.clientY || 0);
      let nextWidth = startWidth;
      let nextHeight = startHeight;
      let nextNodeX = startX;
      let nextNodeY = startY;

      if (position.includes('right')) {
        nextWidth = Math.max(minWidth, startWidth + deltaX);
      }
      if (position.includes('left')) {
        nextWidth = Math.max(minWidth, startWidth - deltaX);
        nextNodeX = startX + (startWidth - nextWidth);
      }
      if (position.includes('bottom')) {
        nextHeight = Math.max(minHeight, startHeight + deltaY);
      }
      if (position.includes('top')) {
        nextHeight = Math.max(minHeight, startHeight - deltaY);
        nextNodeY = startY + (startHeight - nextHeight);
      }

      dispatchDirectResize({
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
      });
    };

    const upHandler = () => stopDirectResize();

    resizeSessionRef.current = { moveHandler, upHandler };
    window.addEventListener('pointermove', moveHandler);
    window.addEventListener('mousemove', moveHandler);
    window.addEventListener('pointerup', upHandler);
    window.addEventListener('pointercancel', upHandler);
    window.addEventListener('mouseup', upHandler);
  }, [canResize, dispatchDirectResize, minHeight, minWidth, stopDirectResize, style?.height, style?.width, xPos, yPos]);

  const bindResizeTarget = useCallback((position) => ({
    onMouseEnter: () => {
      setIsHovered(true);
      setResizeHoverPosition(position);
    },
    onMouseLeave: () => {
      if (!isResizing) {
        setIsHovered(false);
        setResizeHoverPosition('');
      }
    },
    onMouseDown: (event) => beginDirectResize(position, event),
    onPointerDown: (event) => beginDirectResize(position, event),
  }), [beginDirectResize, isResizing]);

  return (
    <div
      ref={wrapperRef}
      data-testid={canResize ? 'topology-group-node-editable' : 'topology-group-node'}
      data-node-id={String(id || '')}
      data-group-label={groupLabel}
      data-resize-hover-position={resizeHoverPosition}
      data-resizing={isResizing ? 'true' : 'false'}
      style={{
        width: '100%',
        height: '100%',
        minWidth: `${Math.max(minWidth, currentWidth)}px`,
        minHeight: `${Math.max(minHeight, currentHeight)}px`,
        position: 'relative',
        pointerEvents: 'auto',
        cursor: canFocusGroup ? (isResizing ? 'grabbing' : (resizeHoverPosition ? getResizeCursor(resizeHoverPosition) : 'grab')) : 'default',
      }}
      className="overflow-hidden rounded-[inherit]"
      onPointerDownCapture={(event) => {
        if (!canFocusGroup || isResizing) return;
        const target = event?.target instanceof HTMLElement ? event.target : null;
        if (target?.closest('[data-testid^="topology-group-resize-control-"]')) return;
        dispatchFocusNode();
      }}
      onMouseDownCapture={(event) => {
        if (!canFocusGroup || isResizing) return;
        const target = event?.target instanceof HTMLElement ? event.target : null;
        if (target?.closest('[data-testid^="topology-group-resize-control-"]')) return;
        dispatchFocusNode();
      }}
      onClick={() => {
        activateGroupEditor();
      }}
    >
      {showResizeHandles ? (
        <>
          {['top', 'right', 'bottom', 'left'].map((position) => (
            <div
              key={`line-${position}`}
              data-testid={`topology-group-resize-control-${position}`}
              data-group-label={groupLabel}
              className="nodrag nopan topology-group-resize-line"
              style={buildResizeLineStyle(position, resizeUiActive, zoomScale)}
              {...bindResizeTarget(position)}
            />
          ))}
          {['top-left', 'top-right', 'bottom-left', 'bottom-right'].map((position) => (
            <div
              key={`handle-${position}`}
              data-testid={`topology-group-resize-control-${position}`}
              data-group-label={groupLabel}
              className="nodrag nopan topology-group-resize-handle"
              style={buildResizeHandleStyle(position, resizeUiActive, zoomScale)}
              {...bindResizeTarget(position)}
            />
          ))}
        </>
      ) : null}

      <div
        style={{
          width: '100%',
          height: '100%',
        }}
        className="overflow-hidden rounded-[inherit]"
      >
        {resizeUiActive ? (
          <div
            style={{
              pointerEvents: 'none',
              position: 'absolute',
              inset: 0,
              borderRadius: 'inherit',
              boxShadow: 'inset 0 0 0 2px rgba(34, 211, 238, 0.75)',
            }}
          />
        ) : null}

        {canResize && !isResizing ? (
          <button
            type="button"
            data-testid="topology-group-open-editor"
            data-node-id={String(id || '')}
            data-group-label={groupLabel}
            onPointerDown={(event) => {
              event.preventDefault();
              event.stopPropagation();
              dispatchOpenEditor();
            }}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              dispatchOpenEditor();
            }}
            className="nodrag nopan"
            style={{
              position: 'absolute',
              top: 10,
              right: 12,
              zIndex: 22,
              borderRadius: 999,
              border: '1px solid rgba(103, 232, 249, 0.5)',
              background: 'rgba(8, 145, 178, 0.16)',
              color: '#cffafe',
              fontSize: 11,
              fontWeight: 700,
              lineHeight: 1,
              padding: '6px 10px',
              cursor: 'pointer',
              boxShadow: '0 8px 20px rgba(8, 145, 178, 0.18)',
              opacity: selected || isHovered ? 1 : 0.72,
            }}
          >
            {t('topology_group_open_editor', 'Edit')}
          </button>
        ) : null}

        {canFocusGroup ? (
          <button
            type="button"
            aria-label={t('topology_group_focus_surface', 'Select group box')}
            data-testid="topology-group-focus-surface"
            data-node-id={String(id || '')}
            data-group-label={groupLabel}
            onPointerDown={() => {
              activateGroupEditor();
            }}
            onMouseDown={() => {
              activateGroupEditor();
            }}
            onClick={() => {
              activateGroupEditor();
            }}
            onKeyDown={(event) => {
              if (event.key !== 'Enter' && event.key !== ' ') return;
              event.preventDefault();
              activateGroupEditor();
            }}
            className="nodrag nopan"
            style={{
              position: 'absolute',
              inset: 0,
              zIndex: 5,
              background: 'transparent',
              cursor: isResizing ? 'grabbing' : (resizeHoverPosition ? getResizeCursor(resizeHoverPosition) : 'grab'),
              pointerEvents: 'auto',
              outline: 'none',
              border: 'none',
              padding: 0,
              margin: 0,
              appearance: 'none',
            }}
          />
        ) : null}

        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 12,
            right: 12,
            display: 'flex',
            justifyContent: 'center',
            paddingTop: '10px',
            fontWeight: 'bold',
            color: '#64748b',
            fontSize: `${fontSize}px`,
            lineHeight: 1.2,
            textAlign: 'center',
            whiteSpace: wrapMode === 'single' ? 'nowrap' : 'normal',
            overflow: 'hidden',
            textOverflow: wrapMode === 'single' ? 'ellipsis' : 'clip',
            wordBreak: 'break-word',
            pointerEvents: 'none',
            cursor: 'default',
          }}
        >
          {groupLabel}
        </div>

        {selected && orgTop.length > 0 ? (
          <div
            style={{
              position: 'absolute',
              top: 10,
              right: 10,
              pointerEvents: 'auto',
              zIndex: 10,
            }}
          >
            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              style={{
                fontSize: 11,
                fontWeight: 700,
                padding: '4px 8px',
                borderRadius: 999,
                border: '1px solid rgba(148, 163, 184, 0.6)',
                background: 'rgba(15, 23, 42, 0.05)',
                color: '#334155',
                cursor: 'pointer',
              }}
            >
              ORG {orgCount > 0 ? `(${orgCount})` : ''}
            </button>
            {open ? (
              <div
                style={{
                  marginTop: 6,
                  minWidth: 220,
                  maxWidth: 320,
                  background: 'rgba(255,255,255,0.95)',
                  border: '1px solid rgba(148, 163, 184, 0.6)',
                  borderRadius: 10,
                  padding: 10,
                  boxShadow: '0 10px 24px rgba(0,0,0,0.12)',
                  color: '#0f172a',
                  fontSize: 11,
                }}
              >
                {orgTop.slice(0, 5).map((x, idx) => (
                  <div
                    key={idx}
                    onClick={() => {
                      try {
                        window.dispatchEvent(new CustomEvent('netmanager:cloud-org-filter', { detail: { org: String(x.org || '') } }));
                      } catch (e) {
                        void e;
                      }
                    }}
                    style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '2px 0', cursor: 'pointer' }}
                    title={t('topology_org_filter_title', 'Click to filter by ORG')}
                  >
                    <div style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={String(x.org || '')}>
                      {String(x.org || '')}
                    </div>
                    <div style={{ fontFamily: 'monospace', color: '#475569' }}>{Number(x.count || 0)}</div>
                  </div>
                ))}
                {orgCount > orgTop.length ? (
                  <div style={{ marginTop: 6, color: '#64748b' }}>
                    {t('common_more_fmt', '+{value} more').replace('{value}', String(orgCount - orgTop.length))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {resizeUiActive ? (
          <div
            data-testid="topology-group-resize-badge"
            style={{
              pointerEvents: 'none',
              position: 'absolute',
              right: 8,
              bottom: 8,
              borderRadius: 8,
              background: 'rgba(15, 23, 42, 0.78)',
              color: '#cffafe',
              fontSize: 10,
              fontWeight: 800,
              padding: '3px 6px',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            {`${currentWidth} x ${currentHeight}`}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default memo(GroupNode);
