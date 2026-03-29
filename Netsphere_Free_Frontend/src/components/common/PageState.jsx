import React from 'react';
import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react';
import { t } from '../../i18n';

export const SectionCard = ({ className = '', children, ...props }) => (
  <div
    {...props}
    className={`rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1b1d1f] shadow-sm dark:shadow-lg transition-shadow hover:shadow-md dark:hover:shadow-xl ${className}`}
  >
    {children}
  </div>
);

export const SectionHeader = ({ title, subtitle = '', right = null, className = '' }) => (
  <div className={`flex items-start justify-between gap-3 ${className}`}>
    <div className="min-w-0">
      <h2 className="text-base sm:text-lg font-bold text-gray-900 dark:text-white truncate">{title}</h2>
      {subtitle ? (
        <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
      ) : null}
    </div>
    {right ? <div className="shrink-0">{right}</div> : null}
  </div>
);

export const InlineLoading = ({ label = t('common_loading', 'Loading...'), className = '' }) => (
  <div className={`flex items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400 ${className}`}>
    <RefreshCw size={16} className="animate-spin" />
    <span>{label}</span>
  </div>
);

export const InlineEmpty = ({ label = t('dashboard_no_data', 'No data'), className = '' }) => (
  <div className={`flex flex-col items-center justify-center gap-3 py-10 text-sm text-gray-400 dark:text-gray-500 ${className}`}>
    <div className="w-12 h-12 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center animate-float">
      <Inbox size={20} className="text-gray-300 dark:text-gray-600" />
    </div>
    <span className="font-medium">{label}</span>
  </div>
);

export const InlineError = ({ label = t('common_error', 'Error'), className = '' }) => (
  <div className={`flex items-center justify-center gap-2 text-sm text-red-600 dark:text-red-300 ${className}`}>
    <AlertTriangle size={16} />
    <span>{label}</span>
  </div>
);

// Re-export EmptyState for easy import
export { default as EmptyState } from './EmptyState';
