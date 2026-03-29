import { useCallback, useRef } from 'react';

/**
 * useTopologyHistory — Undo/Redo for topology node positions & edges.
 *
 * Captures snapshots of node positions and manual edges
 * so the user can Ctrl+Z / Ctrl+Y freely.
 *
 * @param {number} maxHistory - Maximum number of undo states to keep (default 40)
 */
const MAX_DEFAULT = 40;

const clonePositions = (nodes) =>
  (Array.isArray(nodes) ? nodes : []).map((n) => ({
    id: String(n?.id || ''),
    x: Number(n?.position?.x ?? n?.x ?? 0),
    y: Number(n?.position?.y ?? n?.y ?? 0),
    width: n?.width ?? n?.style?.width,
    height: n?.height ?? n?.style?.height,
  }));

const useTopologyHistory = (maxHistory = MAX_DEFAULT) => {
  const undoStack = useRef([]);
  const redoStack = useRef([]);
  const lastSnapshotRef = useRef(null);

  /** Take a snapshot of current state (call BEFORE a change) */
  const pushSnapshot = useCallback((nodes, manualEdges = []) => {
    const snap = {
      positions: clonePositions(nodes),
      manualEdges: JSON.parse(JSON.stringify(manualEdges || [])),
      ts: Date.now(),
    };
    undoStack.current.push(snap);
    if (undoStack.current.length > maxHistory) {
      undoStack.current.shift();
    }
    // Once the user makes a new change, redo history is invalidated
    redoStack.current = [];
    lastSnapshotRef.current = snap;
  }, [maxHistory]);

  /** Undo: pops the last snapshot and applies it. Returns { positions, manualEdges } or null. */
  const undo = useCallback((currentNodes, currentManualEdges) => {
    if (undoStack.current.length === 0) return null;
    // Save current state to redo
    redoStack.current.push({
      positions: clonePositions(currentNodes),
      manualEdges: JSON.parse(JSON.stringify(currentManualEdges || [])),
      ts: Date.now(),
    });
    return undoStack.current.pop();
  }, []);

  /** Redo: pops from redo stack and applies it. Returns { positions, manualEdges } or null. */
  const redo = useCallback((currentNodes, currentManualEdges) => {
    if (redoStack.current.length === 0) return null;
    // Save current state to undo
    undoStack.current.push({
      positions: clonePositions(currentNodes),
      manualEdges: JSON.parse(JSON.stringify(currentManualEdges || [])),
      ts: Date.now(),
    });
    return redoStack.current.pop();
  }, []);

  /** Check if undo/redo have items */
  const canUndo = useCallback(() => undoStack.current.length > 0, []);
  const canRedo = useCallback(() => redoStack.current.length > 0, []);

  /** Reset all history */
  const clearHistory = useCallback(() => {
    undoStack.current = [];
    redoStack.current = [];
    lastSnapshotRef.current = null;
  }, []);

  return { pushSnapshot, undo, redo, canUndo, canRedo, clearHistory };
};

export default useTopologyHistory;
