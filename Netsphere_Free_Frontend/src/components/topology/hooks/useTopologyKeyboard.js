import { useEffect, useCallback } from 'react';

/**
 * useTopologyKeyboard — Keyboard shortcuts for the topology editor.
 *
 * Shortcuts:
 *   Ctrl+Z       → Undo
 *   Ctrl+Y       → Redo
 *   Ctrl+Shift+Z → Redo (alternative)
 *   Delete / Backspace → Delete selected node/edge
 *   Ctrl+S       → Save layout
 *   Ctrl+A       → Select all nodes
 *   Escape       → Deselect / close panels
 *
 * @param {object} handlers
 * @param {boolean} enabled - Only active when manualEditMode is on
 */
const useTopologyKeyboard = ({
  enabled = false,
  onUndo,
  onRedo,
  onDelete,
  onSave,
  onSelectAll,
  onEscape,
}) => {
  const handleKeyDown = useCallback(
    (e) => {
      if (!enabled) return;

      // Ignore when typing in input/textarea/select
      const tag = (e.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      if (e.target?.isContentEditable) return;

      const isCtrl = e.ctrlKey || e.metaKey;

      // Ctrl+Z → Undo
      if (isCtrl && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        onUndo?.();
        return;
      }

      // Ctrl+Y or Ctrl+Shift+Z → Redo
      if ((isCtrl && e.key === 'y') || (isCtrl && e.key === 'z' && e.shiftKey)) {
        e.preventDefault();
        onRedo?.();
        return;
      }

      // Ctrl+S → Save layout
      if (isCtrl && e.key === 's') {
        e.preventDefault();
        onSave?.();
        return;
      }

      // Ctrl+A → Select all
      if (isCtrl && e.key === 'a') {
        e.preventDefault();
        onSelectAll?.();
        return;
      }

      // Delete / Backspace → Delete selected
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault();
        onDelete?.();
        return;
      }

      // Escape → Deselect
      if (e.key === 'Escape') {
        onEscape?.();
        return;
      }
    },
    [enabled, onUndo, onRedo, onDelete, onSave, onSelectAll, onEscape],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
};

export default useTopologyKeyboard;
