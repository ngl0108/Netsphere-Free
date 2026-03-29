import React from 'react';
import { Inbox, Plus, Search, ServerOff, WifiOff, ShieldOff, FileX2 } from 'lucide-react';
import { t } from '../../i18n';

/**
 * Premium Empty-State component for zero-data views.
 *
 * @param {string}  title        - Main heading (e.g. "No devices found")
 * @param {string}  description  - Sub-text guiding the user to action
 * @param {string}  variant      - 'general' | 'device' | 'search' | 'wireless' | 'policy' | 'report'
 * @param {object}  action       - { label, onClick } for the primary CTA button
 * @param {string}  className    - Additional wrapper classes
 */
const VARIANT_MAP = {
  general:  { icon: Inbox,      color: 'blue'   },
  device:   { icon: ServerOff,  color: 'indigo'  },
  search:   { icon: Search,     color: 'gray'    },
  wireless: { icon: WifiOff,    color: 'pink'    },
  policy:   { icon: ShieldOff,  color: 'amber'   },
  report:   { icon: FileX2,     color: 'emerald' },
};

const COLOR_RING = {
  blue:    'from-blue-500/20 to-cyan-500/20 dark:from-blue-500/10 dark:to-cyan-500/10',
  indigo:  'from-indigo-500/20 to-purple-500/20 dark:from-indigo-500/10 dark:to-purple-500/10',
  gray:    'from-gray-400/20 to-slate-400/20 dark:from-gray-500/10 dark:to-slate-500/10',
  pink:    'from-pink-500/20 to-rose-500/20 dark:from-pink-500/10 dark:to-rose-500/10',
  amber:   'from-amber-500/20 to-orange-500/20 dark:from-amber-500/10 dark:to-orange-500/10',
  emerald: 'from-emerald-500/20 to-teal-500/20 dark:from-emerald-500/10 dark:to-teal-500/10',
};

const ICON_COLOR = {
  blue:    'text-blue-500',
  indigo:  'text-indigo-500',
  gray:    'text-gray-400',
  pink:    'text-pink-500',
  amber:   'text-amber-500',
  emerald: 'text-emerald-500',
};

const EmptyState = ({
  title = t('dashboard_no_data', 'No data'),
  description = '',
  variant = 'general',
  action = null,
  className = '',
}) => {
  const v = VARIANT_MAP[variant] || VARIANT_MAP.general;
  const IconComp = v.icon;

  return (
    <div className={`flex flex-col items-center justify-center py-16 px-6 text-center animate-fade-in select-none ${className}`}>
      {/* Floating icon with gradient ring */}
      <div className={`relative w-24 h-24 rounded-full bg-gradient-to-br ${COLOR_RING[v.color]} flex items-center justify-center mb-6 animate-float`}>
        <div className="absolute inset-0 rounded-full bg-gradient-to-br from-white/5 to-transparent" />
        <IconComp size={36} className={`${ICON_COLOR[v.color]} relative z-10`} strokeWidth={1.5} />
      </div>

      <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-2">
        {title}
      </h3>

      {description && (
        <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md leading-relaxed">
          {description}
        </p>
      )}

      {action && (
        <button
          onClick={action.onClick}
          className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-[0.97] text-white text-sm font-bold shadow-lg shadow-blue-500/20 transition-all duration-200"
        >
          <Plus size={16} />
          {action.label}
        </button>
      )}
    </div>
  );
};

export default EmptyState;
