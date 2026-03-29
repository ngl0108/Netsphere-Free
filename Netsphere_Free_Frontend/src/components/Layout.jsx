import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  Bell,
  CheckCircle,
  ChevronRight,
  LogOut,
  Menu,
  Moon,
  Search,
  Sun,
  X,
  XCircle,
} from 'lucide-react';
import Sidebar from './Sidebar';
import { useAuth } from '../context/AuthContext';
import { useIssuePolling } from '../context/IssuePollingContext';
import { useTheme } from '../context/ThemeContext';
import { useToast } from '../context/ToastContext';
import { OpsService, PreviewService } from '../api/services';
import { getLocale, getLocaleChangeEventName, getLocaleLabel, getSupportedLocales, setLocale, t } from '../i18n';

const Layout = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout, isAdmin } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const { toast } = useToast();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [observabilitySupported, setObservabilitySupported] = useState(false);
  const [observabilityEnabled, setObservabilityEnabled] = useState(false);
  const [observabilityBusy, setObservabilityBusy] = useState(false);
  const [previewEnabled, setPreviewEnabled] = useState(false);
  const [previewPolicyResolved, setPreviewPolicyResolved] = useState(false);

  const { unreadCount, recentAlerts, loadAlerts, markAsRead } = useIssuePolling();
  const [showDropdown, setShowDropdown] = useState(false);
  const [locale, setLocaleState] = useState(getLocale());
  const dropdownRef = useRef(null);

  useEffect(() => {
    if (!isAdmin() || !previewPolicyResolved || previewEnabled) {
      setObservabilitySupported(false);
      setObservabilityEnabled(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await OpsService.getObservability();
        if (cancelled) return;
        const enabled = !!(res?.data?.enabled ?? res?.data?.data?.enabled);
        setObservabilitySupported(true);
        setObservabilityEnabled(enabled);
      } catch (e) {
        if (cancelled) return;
        setObservabilitySupported(false);
        setObservabilityEnabled(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user?.role, isAdmin, previewEnabled, previewPolicyResolved]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await PreviewService.getPolicy();
        if (!cancelled) {
          setPreviewEnabled(res?.data?.preview_enabled === true);
        }
      } catch (e) {
        if (!cancelled) {
          setPreviewEnabled(false);
        }
      } finally {
        if (!cancelled) {
          setPreviewPolicyResolved(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  useEffect(() => {
    setSidebarOpen(false);
    setShowDropdown(false);
  }, [location.pathname]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (!sidebarOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [sidebarOpen]);

  useEffect(() => {
    const eventName = getLocaleChangeEventName();
    const handleLocaleChanged = (event) => {
      const next = event?.detail?.locale || getLocale();
      setLocaleState(next);
    };
    window.addEventListener(eventName, handleLocaleChanged);
    return () => window.removeEventListener(eventName, handleLocaleChanged);
  }, []);

  useEffect(() => {
    if (!showDropdown) return;
    void loadAlerts({ silent: true });
  }, [showDropdown, loadAlerts]);

  const handleMarkRead = async (id, e) => {
    e.stopPropagation();
    try {
      await markAsRead(id);
    } catch (err) {
      console.error('Failed to mark as read:', err);
    }
  };

  const formatTimeAgo = (dateString) => {
    if (!dateString) return '';
    const now = new Date();
    const past = new Date(new Date(dateString).getTime() + 9 * 60 * 60 * 1000);
    const diffMins = Math.floor((now - past) / 60000);
    if (diffMins < 1) return t('layout_time_just_now', 'Just now');
    if (diffMins < 60) {
      return t('layout_time_minutes_ago', '{value}m ago').replace('{value}', String(diffMins));
    }
    if (diffMins < 1440) {
      return t('layout_time_hours_ago', '{value}h ago').replace('{value}', String(Math.floor(diffMins / 60)));
    }
    return t('layout_time_days_ago', '{value}d ago').replace('{value}', String(Math.floor(diffMins / 1440)));
  };

  const getPageTitle = (path) => {
    if (path === '/') return t('layout_page_global_dashboard');
    if (path === '/topology') return t('layout_page_network_map');
    if (path === '/devices') return t('layout_page_devices');
    if (path.startsWith('/devices/')) return t('layout_page_device360');
    if (path === '/diagnosis') return t('layout_page_diagnosis');
    if (path === '/cloud/accounts') return t('layout_page_cloud_accounts', 'Cloud Accounts');
    if (path === '/cloud/intents') return t('layout_page_cloud_intents', 'Cloud Intents');
    if (path === '/preventive-checks') return t('layout_page_preventive_checks', 'Preventive Checks');
    if (path === '/monitoring-profiles') return t('layout_page_monitoring_profiles', 'Monitoring Profiles');
    if (path === '/source-of-truth') return t('layout_page_source_of_truth', 'Source of Truth');
    if (path === '/state-history') return t('layout_page_state_history', 'State History');
    if (path === '/intent-templates') return t('layout_page_intent_templates', 'Intent Templates');
    if (path === '/service-groups') return t('layout_page_service_groups', 'Service Groups');
    if (path === '/edition/compare') return t('layout_page_edition_compare', 'Free vs Pro');
    if (path === '/wireless') return t('layout_page_wireless');
    if (path === '/config') return t('layout_page_config');
    if (path === '/images') return t('layout_page_images');
    if (path === '/policy') return t('layout_page_policy');
    if (path === '/ztp') return t('layout_page_ztp');
    if (path === '/logs') return t('layout_page_logs');
    if (path === '/audit') {
      return previewEnabled
        ? t('layout_page_preview_contribution', 'Data Handling Audit')
        : t('layout_page_audit');
    }
    if (path === '/notifications') return t('layout_page_notifications');
    if (path === '/settings') return t('layout_page_settings');
    if (path === '/users') return t('layout_page_users');
    if (path === '/sites') return t('layout_page_sites');
    if (path === '/fabric') return t('layout_page_fabric');
    if (path === '/compliance') return t('layout_page_compliance');
    if (path === '/approval') return t('layout_page_approval');
    if (path === '/observability') return t('layout_page_observability');
    if (path === '/automation') return t('layout_page_automation');
    if (path === '/preview/contribute') return t('layout_page_preview_contribution', 'Data Handling Audit');
    return t('layout_page_default');
  };

  const pageTitle = getPageTitle(location.pathname);

  const handleLogout = () => {
    if (window.confirm(t('layout_confirm_logout'))) {
      logout();
      navigate('/login');
    }
  };

  const handleToggleObservability = async () => {
    if (!observabilitySupported || observabilityBusy) return;
    setObservabilityBusy(true);
    try {
      const res = await OpsService.setObservability(!observabilityEnabled);
      const enabled = !!(res?.data?.enabled ?? res?.data?.data?.enabled);
      setObservabilityEnabled(enabled);
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || t('layout_observability_toggle_failed');
      toast.error(String(msg));
    } finally {
      setObservabilityBusy(false);
    }
  };

  const handleLocaleChange = (event) => {
    const next = setLocale(event.target.value);
    setLocaleState(next);
  };

  return (
    <div className={`flex min-h-[100dvh] h-[100dvh] w-full overflow-hidden font-sans transition-colors duration-300 ${isDark ? 'text-white bg-[#0f172a]' : 'text-gray-900 bg-slate-100'}`}>
      <div className="hidden lg:block">
        <Sidebar />
      </div>

      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={() => setSidebarOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-64">
            <div className="relative h-full">
              <button
                onClick={() => setSidebarOpen(false)}
                className="absolute top-3 right-3 z-[60] h-10 w-10 flex items-center justify-center rounded-xl bg-white/80 text-gray-700 shadow-sm hover:bg-white focus:outline-none dark:bg-black/40 dark:text-gray-200 dark:hover:bg-black/60 border border-gray-200 dark:border-white/10"
                aria-label={t('layout_close_sidebar', 'Close sidebar')}
              >
                <X size={18} />
              </button>
              <Sidebar className="shadow-2xl" onNavigate={() => setSidebarOpen(false)} />
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0 relative">
        <header className="h-16 flex-shrink-0 z-20 px-3 sm:px-4 md:px-6 py-3">
          <div className="h-full bg-white/90 dark:bg-[#1b1d1f]/90 backdrop-blur-md border border-gray-200 dark:border-white/5 rounded-2xl flex items-center justify-between px-3 sm:px-4 md:px-6 shadow-sm">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden h-10 w-10 flex items-center justify-center rounded-xl hover:bg-gray-100 dark:hover:bg-white/10 text-gray-600 dark:text-gray-300 border border-transparent hover:border-gray-200 dark:hover:border-white/5"
                aria-label={t('layout_open_sidebar', 'Open sidebar')}
              >
                <Menu size={20} />
              </button>
              <h2 className="text-lg font-bold text-gray-800 dark:text-white tracking-tight flex items-center gap-2">
                <span className="w-1.5 h-6 bg-primary rounded-full shadow-sm"></span>
                {pageTitle}
                {previewEnabled && (
                  <span className="inline-flex items-center rounded-full bg-amber-500/15 border border-amber-500/20 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-amber-700 dark:text-amber-300">
                    Free
                  </span>
                )}
              </h2>
            </div>

            <div className="flex items-center gap-5">
              <div className="relative hidden md:block group">
                <Search className="absolute left-3 top-2.5 text-gray-400 group-hover:text-primary transition-colors" size={16} />
                <input
                  type="text"
                  placeholder={t('layout_search_placeholder')}
                  className="bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-white/5 text-sm rounded-xl pl-9 pr-4 py-1.5 focus:outline-none focus:border-primary/50 text-gray-800 dark:text-gray-300 w-64 transition-all focus:bg-white dark:focus:bg-black/40 focus:ring-2 focus:ring-primary/20"
                />
              </div>

              <div className="hidden sm:flex items-center gap-2 h-10 px-3 rounded-xl bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-white/5">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {t('layout_language_label', 'Language')}
                </span>
                <select
                  value={locale}
                  onChange={handleLocaleChange}
                  className="bg-transparent text-sm font-semibold text-gray-700 dark:text-gray-200 outline-none cursor-pointer min-w-[84px]"
                  aria-label={t('layout_language_label', 'Language')}
                >
                  {getSupportedLocales().map((code) => (
                    <option key={code} value={code} className="text-gray-900">
                      {getLocaleLabel(code)}
                    </option>
                  ))}
                </select>
              </div>

              <button
                onClick={toggleTheme}
                className="h-10 w-10 flex items-center justify-center rounded-xl hover:bg-gray-100 dark:hover:bg-white/10 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-all border border-transparent hover:border-gray-200 dark:hover:border-white/5"
                title={isDark ? t('layout_theme_light') : t('layout_theme_dark')}
              >
                {isDark ? <Sun size={20} /> : <Moon size={20} />}
              </button>

              {isAdmin() && previewPolicyResolved && !previewEnabled && observabilitySupported && (
                <button
                  onClick={handleToggleObservability}
                  disabled={observabilityBusy}
                  aria-label={
                    observabilityEnabled
                      ? t('layout_observability_on', 'Observability Collection: ON (click to disable)')
                      : t('layout_observability_off', 'Observability Collection: OFF (click to enable)')
                  }
                  className={`h-10 w-10 flex items-center justify-center rounded-xl transition-all border border-transparent hover:border-gray-200 dark:hover:border-white/5 ${
                    observabilityBusy ? 'opacity-60 cursor-not-allowed' : ''
                  } ${
                    observabilityEnabled
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/15'
                      : 'hover:bg-gray-100 dark:hover:bg-white/10 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                  }`}
                  title={
                    observabilityEnabled
                      ? t('layout_observability_on', 'Observability Collection: ON (click to disable)')
                      : t('layout_observability_off', 'Observability Collection: OFF (click to enable)')
                  }
                >
                  <Activity size={20} />
                </button>
              )}

              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => setShowDropdown(!showDropdown)}
                  className="relative h-10 w-10 flex items-center justify-center rounded-xl hover:bg-gray-100 dark:hover:bg-white/10 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-all group border border-transparent hover:border-gray-200 dark:hover:border-white/5"
                >
                  <Bell size={20} className="group-hover:text-yellow-500 transition-colors" />
                  {unreadCount > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center px-1 text-[10px] font-bold text-white bg-red-500 rounded-full border-2 border-white dark:border-[#1b1d1f] animate-pulse shadow-sm">
                      {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                  )}
                </button>

                {showDropdown && (
                  <div className="absolute right-0 top-12 w-[calc(100vw-1.5rem)] max-w-sm sm:max-w-md bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 rounded-2xl shadow-xl z-50 overflow-hidden animate-scale-in origin-top-right ring-1 ring-black/5">
                    <div className="flex justify-between items-center px-4 py-3 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-[#25282c]">
                      <h3 className="font-bold text-gray-800 dark:text-white text-sm flex items-center gap-2">
                        <Bell size={16} className="text-yellow-500" />
                        {t('layout_notifications')}
                        {unreadCount > 0 && (
                          <span className="px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 text-[10px]">
                            {unreadCount} {t('layout_new')}
                          </span>
                        )}
                      </h3>
                      <button
                        onClick={() => setShowDropdown(false)}
                        className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
                      >
                        <X size={14} />
                      </button>
                    </div>

                    <div className="max-h-[24rem] overflow-y-auto custom-scrollbar bg-white dark:bg-[#1b1d1f]">
                      {recentAlerts.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500">
                          <CheckCircle size={40} className="text-gray-200 dark:text-gray-700 mb-3" />
                          <p className="text-sm font-medium">{t('layout_no_unread')}</p>
                          <p className="text-xs text-gray-400 mt-1">{t('layout_all_caught_up')}</p>
                        </div>
                      ) : (
                        recentAlerts.map((alert) => (
                          <div
                            key={alert.id}
                            onClick={() => {
                              setShowDropdown(false);
                              navigate('/notifications');
                            }}
                            className={`flex items-start gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer border-b border-gray-50 dark:border-gray-800/50 transition-colors ${!alert.is_read ? 'bg-blue-50/60 dark:bg-blue-900/10' : ''}`}
                          >
                            <div className={`mt-0.5 p-1.5 rounded-lg shrink-0 ${alert.severity === 'critical' ? 'bg-red-100 text-red-600 dark:bg-red-500/20 dark:text-red-400' : 'bg-orange-100 text-orange-600 dark:bg-orange-500/20 dark:text-orange-400'}`}>
                              {alert.severity === 'critical' ? <XCircle size={14} /> : <AlertTriangle size={14} />}
                            </div>
                            <div className="flex-1 min-w-0 space-y-0.5">
                              <div className="flex justify-between items-start gap-2">
                                <p className="text-sm font-semibold truncate text-gray-900 dark:text-gray-100">{alert.title}</p>
                                <span className="text-[10px] text-gray-400 flex items-center gap-1 whitespace-nowrap pt-0.5">
                                  {formatTimeAgo(alert.created_at)}
                                </span>
                              </div>
                              <p className="text-xs text-gray-500 dark:text-gray-400 truncate pr-4">
                                {alert.device} - {alert.description || t('layout_no_description')}
                              </p>
                            </div>
                            {!alert.is_read && (
                              <button
                                onClick={(e) => handleMarkRead(alert.id, e)}
                                className="mt-1 p-1 hover:bg-green-100 dark:hover:bg-green-900/30 rounded text-green-600 dark:text-green-400 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                                title={t('layout_mark_as_read')}
                              >
                                <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div>
                              </button>
                            )}
                          </div>
                        ))
                      )}
                    </div>

                    <button
                      onClick={() => {
                        setShowDropdown(false);
                        navigate('/notifications');
                      }}
                      className="w-full flex items-center justify-center gap-2 px-4 py-3 text-xs font-bold text-gray-600 dark:text-gray-400 hover:text-primary dark:hover:text-primary hover:bg-gray-50 dark:hover:bg-[#25282c] border-t border-gray-100 dark:border-gray-800 transition-colors uppercase tracking-wide"
                    >
                      {t('layout_view_all_activity')} <ChevronRight size={14} />
                    </button>
                  </div>
                )}
              </div>

              <div className="h-6 w-px bg-gray-200 dark:bg-white/10 mx-1"></div>

              <button
                onClick={handleLogout}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-gray-500 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400 hover:border-red-200 dark:hover:border-red-900/30 border border-transparent transition-all"
                title={t('layout_logout')}
              >
                <LogOut size={18} />
                <span className="text-xs font-bold hidden md:inline">{t('layout_logout')}</span>
              </button>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-hidden relative p-3 sm:p-4 md:p-6 pt-2">
          <div key={`locale-${locale}`} className="w-full h-full overflow-y-auto custom-scrollbar rounded-2xl p-1">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

export default Layout;
