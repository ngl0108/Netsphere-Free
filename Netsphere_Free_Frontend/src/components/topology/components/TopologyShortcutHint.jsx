import React, { useState } from 'react';
import { Keyboard, X, ChevronDown, ChevronUp } from 'lucide-react';
import { t } from '../../../i18n';

const TopologyShortcutHint = ({ visible = false }) => {
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const shortcuts = [
    { keys: ['Ctrl', 'Z'], label: t('topology_shortcut_undo', 'Undo') },
    { keys: ['Ctrl', 'Y'], label: t('topology_shortcut_redo', 'Redo') },
    { keys: ['Ctrl', 'S'], label: t('topology_shortcut_save_layout', 'Save Layout') },
    { keys: ['Ctrl', 'A'], label: t('topology_shortcut_select_all', 'Select All') },
    { keys: ['Delete'], label: t('topology_shortcut_delete_selected', 'Delete Selected') },
    { keys: ['Shift', 'Click'], label: t('topology_shortcut_multi_select', 'Multi-Select') },
    { keys: [t('topology_shortcut_right_click_key', 'Right Click')], label: t('topology_shortcut_context_menu', 'Context Menu') },
    { keys: ['Esc'], label: t('topology_shortcut_deselect_all', 'Deselect All') },
  ];

  if (!visible || dismissed) return null;

  return (
    <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 z-30 animate-slide-up">
      <div className="pointer-events-none rounded-2xl border border-slate-700/70 bg-[#12161c]/96 backdrop-blur-xl shadow-2xl text-white overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2.5">
          <Keyboard size={14} className="text-cyan-400" />
          <span className="text-xs font-bold text-slate-200">
            {t('topology_shortcuts_title', 'Editor Shortcuts')}
          </span>

          <button
            onClick={() => setExpanded(!expanded)}
            className="pointer-events-auto ml-auto p-1 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>

          <button
            onClick={() => setDismissed(true)}
            className="pointer-events-auto p-1 rounded-lg hover:bg-white/10 text-slate-500 hover:text-white transition-colors"
          >
            <X size={14} />
          </button>
        </div>

        {!expanded && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 pb-3 text-[11px] text-slate-400">
            <span><Kbd>Ctrl+Z</Kbd> {t('topology_shortcut_undo', 'Undo')}</span>
            <span><Kbd>Ctrl+Y</Kbd> {t('topology_shortcut_redo', 'Redo')}</span>
            <span><Kbd>Del</Kbd> {t('topology_shortcut_delete_selected_short', 'Delete')}</span>
            <span><Kbd>Shift+Click</Kbd> {t('topology_shortcut_multi_select', 'Multi-Select')}</span>
            <span><Kbd>{t('topology_shortcut_right_click_key_short', 'Right Click')}</Kbd> {t('topology_shortcut_context_menu_short', 'Menu')}</span>
          </div>
        )}

        {expanded && (
          <div className="px-4 pb-3 space-y-1.5">
            {shortcuts.map((sc, i) => (
              <div key={i} className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400">{sc.label}</span>
                <div className="flex items-center gap-1">
                  {sc.keys.map((key, j) => (
                    <Kbd key={j}>{key}</Kbd>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const Kbd = ({ children }) => (
  <kbd className="inline-flex items-center justify-center min-w-[22px] h-[20px] px-1.5 rounded-md bg-slate-800 border border-slate-600 text-[10px] font-bold text-slate-300 font-mono leading-none">
    {children}
  </kbd>
);

export default TopologyShortcutHint;
