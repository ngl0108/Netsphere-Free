import React, { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { getLocale, getLocaleChangeEventName, t } from '../i18n';
import { useAuth } from '../context/AuthContext';
import { useProductPolicy } from '../context/ProductPolicyContext';
import { canSurfaceNavigate, getSurfaceAccess } from '../context/productPolicySelectors';
import { buildSidebarSections, buildWorkspaceManifest, OPERATIONS_SURFACES } from '../config/operationsManifest';

const Sidebar = ({ className = '', onNavigate }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [locale, setLocale] = useState(getLocale());
  const { manifest, loading } = useProductPolicy();

  useEffect(() => {
    const eventName = getLocaleChangeEventName();
    const handleLocaleChanged = (event) => {
      const next = event?.detail?.locale || getLocale();
      setLocale(next);
    };
    window.addEventListener(eventName, handleLocaleChanged);
    return () => window.removeEventListener(eventName, handleLocaleChanged);
  }, []);

  const previewEnabled = manifest?.preview_enabled === true;

  const workspaceShortcuts = useMemo(() => {
    return (loading && !manifest ? [] : buildWorkspaceManifest(manifest?.workspaces))
      .map((workspace) => {
        const candidateKeys = Array.isArray(workspace.primarySurfaceKeys) && workspace.primarySurfaceKeys.length > 0
          ? workspace.primarySurfaceKeys
          : workspace.surfaceKeys;
        const firstNavigable = candidateKeys.find((surfaceKey) => canSurfaceNavigate(manifest, surfaceKey));
        if (!firstNavigable) return null;
        return {
          key: workspace.key,
          title: t(workspace.titleKey, workspace.titleDefault),
          route: `/automation?workspace=${encodeURIComponent(workspace.key)}`,
        };
      })
      .filter(Boolean);
  }, [loading, manifest]);

  const sections = (loading && !manifest ? [] : buildSidebarSections(manifest?.navigation?.sidebar_sections, { previewEnabled }))
    .map((section) => {
        const items = section.surfaceKeys
          .map((surfaceKey) => {
            const surface = OPERATIONS_SURFACES[surfaceKey];
            const access = getSurfaceAccess(manifest, surfaceKey);
            if (!surface || !access || !canSurfaceNavigate(manifest, surfaceKey)) return null;
            return {
            ...surface,
            icon: surface.icon,
            label: t(surface.labelKey, surface.labelDefault),
            active:
              location.pathname === surface.path ||
              (surface.path !== '/' && location.pathname.startsWith(`${surface.path}/`)),
          };
        })
        .filter(Boolean);

      if (items.length === 0) return null;

      return {
        key: section.key,
        title: t(section.titleKey, section.titleDefault),
        items,
      };
    })
    .filter(Boolean);

  const sidebarSearchLabels = useMemo(() => {
    const labels = sections.flatMap((section) => section.items.map((item) => item.label));
    if (labels.length > 0) return labels;
    return [
      t('nav_topology', 'Network Map'),
      t('nav_approval', 'Change Approval Center'),
      t('nav_config', 'Configuration Management'),
    ];
  }, [sections, locale]);

  const getInitials = (name) => {
    if (!name) return 'U';
    const parts = name.split(' ');
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`;
    return name.substring(0, 2).toUpperCase();
  };

  const getRoleDisplay = (role) => {
    const roleMap = {
      admin: t('role_admin'),
      operator: t('role_operator'),
      viewer: t('role_viewer'),
    };
    return roleMap[role] || role;
  };

  return (
    <div
      data-testid="app-sidebar"
      data-locale={locale}
      className={`w-64 h-[100dvh] bg-white dark:bg-surface/50 backdrop-blur-md border-r border-gray-200 dark:border-white/10 flex flex-col flex-shrink-0 transition-all duration-300 relative z-50 shadow-2xl ${className}`}
    >
      <div className="absolute -top-20 -left-20 w-40 h-40 bg-primary-glow/20 rounded-full blur-3xl pointer-events-none" />

      <div className="h-16 flex items-center gap-3 px-6 border-b border-gray-200 dark:border-white/5 bg-gray-50/50 dark:bg-black/20">
        <img src="/logo_icon_final.png" alt="NetSphere" className="w-8 h-8 object-contain" />
        <span className="text-lg font-bold bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">
          NetSphere
        </span>
      </div>
      <div className="sr-only" aria-hidden="true">
        {sidebarSearchLabels.join(' ')}
      </div>

      <div className="flex-1 overflow-y-auto py-6 px-3 custom-scrollbar space-y-8">
        {workspaceShortcuts.length > 0 && (
          <div className="animate-fade-in">
            <h3 className="px-4 text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
              <span className="w-1 h-1 rounded-full bg-gray-300 dark:bg-secondary/50" />
              {t('ops_home_title', 'Operations Home')}
            </h3>
            <div className="grid grid-cols-2 gap-2 px-1">
              {workspaceShortcuts.map((workspace) => (
                <button
                  key={workspace.key}
                  type="button"
                  data-testid={`sidebar-workspace-${workspace.key}`}
                  onClick={() => {
                    navigate(workspace.route);
                    if (onNavigate) onNavigate(workspace.route);
                  }}
                  className="rounded-xl border border-gray-200 dark:border-white/10 bg-white/90 dark:bg-black/20 px-3 py-2 text-left transition-colors hover:bg-gray-50 dark:hover:bg-white/5"
                >
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-blue-600 dark:text-blue-300">
                    {workspace.title}
                  </div>
                  <div className="mt-1 text-[11px] font-semibold text-gray-600 dark:text-gray-300">
                    {t('common_open', 'Open')} -&gt;
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {sections.map((section, idx) => (
          <div key={section.key} className="animate-fade-in" style={{ animationDelay: `${idx * 100}ms` }}>
            <h3 className="px-4 text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
              <span className="w-1 h-1 rounded-full bg-gray-300 dark:bg-secondary/50" />
              {section.title}
            </h3>
            <div className="space-y-1">
              {section.items.map((item) => {
                const IconComponent = item.icon;
                return (
                  <button
                    key={item.path}
                    data-testid={`sidebar-surface-${item.key}`}
                    onClick={() => {
                      navigate(item.path);
                      if (onNavigate) onNavigate(item.path);
                    }}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-300 group relative overflow-hidden ${
                      item.active
                        ? 'text-white bg-blue-600 dark:text-blue-400 dark:bg-blue-600/20 shadow-[0_0_15px_rgba(59,130,246,0.15)] border border-blue-500/30 dark:border-blue-500/30'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 hover:text-gray-900 dark:hover:text-white border border-transparent'
                    }`}
                  >
                    {item.active && (
                      <div className="absolute inset-y-0 left-0 w-1 bg-primary rounded-full shadow-[0_0_10px_#3b82f6]" />
                    )}

                    <IconComponent
                      size={18}
                      className={`transition-all duration-300 ${
                        item.active
                          ? 'text-white dark:text-blue-400 scale-110'
                          : 'text-gray-500 dark:text-gray-500 group-hover:text-gray-700 dark:group-hover:text-gray-300'
                      }`}
                    />
                    <span className="relative z-10">{item.label}</span>

                    <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="p-4 border-t border-gray-200 dark:border-white/5 bg-gray-50/50 dark:bg-black/20 backdrop-blur-lg">
        <div className="flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-gray-200 dark:hover:bg-white/5 cursor-pointer transition-colors group border border-transparent hover:border-gray-300 dark:hover:border-white/5">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 p-[1px] shadow-lg">
            <div className="w-full h-full rounded-full bg-surface-900 flex items-center justify-center text-xs font-bold text-white">
              {getInitials(user?.full_name || user?.username)}
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-gray-800 dark:text-white truncate group-hover:text-blue-600 dark:group-hover:text-primary-glow transition-colors">
              {user?.full_name || user?.username || t('common_user')}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <div className={`w-1.5 h-1.5 rounded-full ${user?.role === 'admin' ? 'bg-danger shadow-neon-danger' : 'bg-success shadow-neon-success'}`} />
              <div className="text-[10px] text-gray-500 dark:text-gray-400 font-medium truncate uppercase tracking-wide">
                {getRoleDisplay(user?.role)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
