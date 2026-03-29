import React, { memo } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  getSmoothStepPath,
  getStraightPath,
} from 'reactflow';

const clamp = (value, min, max, fallback) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(min, Math.min(max, numeric));
};

const pickPath = (curve, props) => {
  const common = {
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    targetX: props.targetX,
    targetY: props.targetY,
    sourcePosition: props.sourcePosition,
    targetPosition: props.targetPosition,
  };
  if (curve === 'smoothstep') return getSmoothStepPath(common);
  if (curve === 'step') return getSmoothStepPath({ ...common, borderRadius: 0 });
  if (curve === 'straight') return getStraightPath(common);
  return getBezierPath(common);
};

const TopologyEditableEdge = (props) => {
  const {
    id,
    data,
    markerEnd,
    markerStart,
    style,
    label,
    labelStyle,
    selected,
  } = props;

  const renderCurve = String(data?.renderCurve || 'default').trim().toLowerCase() || 'default';
  const [edgePath] = pickPath(renderCurve, props);
  const labelText = String(data?.fullLabel || data?.manualLabel || label || '').trim();
  const labelPosition = clamp(data?.labelPosition, 10, 90, 50) / 100;
  const labelOffsetY = clamp(data?.labelOffsetY, -80, 80, 0);
  const labelOffsetX = clamp(data?.labelOffsetX, -120, 120, 0);
  const labelX = props.sourceX + ((props.targetX - props.sourceX) * labelPosition) + labelOffsetX;
  const labelY = props.sourceY + ((props.targetY - props.sourceY) * labelPosition) + labelOffsetY;
  const backgroundFill = data?.warningMeta
    ? (String(data.warningMeta.tone || '').trim().toLowerCase() === 'critical' ? '#ffe4e6' : '#fef3c7')
    : 'rgba(255,255,255,0.94)';
  const borderColor = style?.stroke || '#334155';

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} markerStart={markerStart} style={style} />
      {labelText ? (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan pointer-events-none absolute rounded-full border px-2.5 py-1 text-[11px] font-semibold shadow-sm backdrop-blur-sm"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              color: labelStyle?.fill || borderColor,
              background: backgroundFill,
              borderColor,
              opacity: labelStyle?.opacity ?? 1,
              boxShadow: selected ? '0 0 0 2px rgba(56, 189, 248, 0.18)' : undefined,
            }}
          >
            {labelText}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
};

export default memo(TopologyEditableEdge);
