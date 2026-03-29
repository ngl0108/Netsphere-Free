import React, { memo, useState } from 'react';
import { Handle, NodeResizeControl, Position, ResizeControlVariant } from 'reactflow';

const hiddenHandleStyle = {
  width: 8,
  height: 8,
  opacity: 0,
  border: 'none',
  background: 'transparent',
};

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

const buildResizeLineStyle = (position) => {
  const stroke = '2px dashed rgba(34, 211, 238, 0.95)';
  const base = {
    touchAction: 'none',
    background: 'rgba(34, 211, 238, 0.08)',
    cursor: getResizeCursor(position),
  };
  if (position === 'top') {
    return {
      ...base,
      width: '100%',
      height: 14,
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
      height: 14,
      left: 0,
      top: '100%',
      transform: 'translate(0, -50%)',
      borderBottom: stroke,
    };
  }
  if (position === 'left') {
    return {
      ...base,
      width: 14,
      height: '100%',
      top: 0,
      left: 0,
      transform: 'translate(-50%, 0)',
      borderLeft: stroke,
    };
  }
  return {
    ...base,
    width: 14,
    height: '100%',
    top: 0,
    left: '100%',
    transform: 'translate(-50%, 0)',
    borderRight: stroke,
  };
};

const buildResizeHandleStyle = (position) => ({
  ...BASE_RESIZE_HANDLE_STYLE,
  cursor: getResizeCursor(position),
});

const NetworkNode = ({ data, selected, style }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const canResize = !!data?.editorResizable;
  const minWidth = Math.max(140, Number(data?.editorMinWidth || 0) || 140);
  const minHeight = Math.max(88, Number(data?.editorMinHeight || 0) || 88);
  const showResizeHandles = canResize && (selected || isHovered || isResizing);
  const currentWidth = Math.round(Number(style?.width || 0) || minWidth);
  const currentHeight = Math.round(Number(style?.height || 0) || minHeight);

  return (
    <>
      {showResizeHandles ? (
        <>
          {['top', 'right', 'bottom', 'left'].map((position) => (
            <NodeResizeControl
              key={`line-${position}`}
              minWidth={minWidth}
              minHeight={minHeight}
              position={position}
              variant={ResizeControlVariant.Line}
              className="topology-resize-line"
              style={buildResizeLineStyle(position)}
              onResizeStart={() => setIsResizing(true)}
              onResizeEnd={() => setIsResizing(false)}
            />
          ))}
          {['top-left', 'top-right', 'bottom-left', 'bottom-right'].map((position) => (
            <NodeResizeControl
              key={`handle-${position}`}
              minWidth={minWidth}
              minHeight={minHeight}
              position={position}
              variant={ResizeControlVariant.Handle}
              className="topology-resize-handle"
              style={buildResizeHandleStyle(position)}
              onResizeStart={() => setIsResizing(true)}
              onResizeEnd={() => setIsResizing(false)}
            />
          ))}
        </>
      ) : null}
      <Handle type="target" position={Position.Top} style={hiddenHandleStyle} />
      <Handle type="source" position={Position.Bottom} style={hiddenHandleStyle} />
      <div
        data-testid={canResize ? 'topology-node-editable' : 'topology-node'}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => {
          if (!isResizing) setIsHovered(false);
        }}
        style={{ width: '100%', height: '100%', position: 'relative', cursor: canResize ? 'grab' : 'default' }}
        className="overflow-hidden rounded-[inherit]"
      >
        {showResizeHandles ? (
          <div className="pointer-events-none absolute inset-0 rounded-[inherit] ring-2 ring-cyan-400/70 ring-offset-1 ring-offset-transparent" />
        ) : null}
        <div className="h-full w-full">
          {data?.label}
        </div>
        {showResizeHandles ? (
          <div data-testid="topology-node-resize-badge" className="pointer-events-none absolute bottom-1 right-1 rounded-md bg-slate-900/75 px-1.5 py-0.5 text-[10px] font-bold text-cyan-100">
            {`${currentWidth} x ${currentHeight}`}
          </div>
        ) : null}
      </div>
    </>
  );
};

export default memo(NetworkNode);
