import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { ThemeProvider } from './context/ThemeContext';

import { IssuePollingProvider } from './context/IssuePollingContext';
import { ProductPolicyProvider, useProductPolicy } from './context/ProductPolicyContext';
import FirstRunWizard from './components/auth/FirstRunWizard';
import HaStandbyOverlay from './components/ha/HaStandbyOverlay';
import GlobalHttpErrorBridge from './components/common/GlobalHttpErrorBridge';
import { t } from './i18n';
import { useLocaleRerender } from './i18n/useLocaleRerender';
import {
  getSurfacePolicyState,
} from './context/productPolicySelectors';
import ProductPolicyBlockCard from './components/common/ProductPolicyBlockCard';

const Layout = lazy(() => import('./components/Layout'));
const DashboardPage = lazy(() => import('./components/dashboard/DashboardPage'));
const DeviceListPage = lazy(() => import('./components/devices/DeviceListPage'));
const ConfigPage = lazy(() => import('./components/config/ConfigPage'));
const LogsPage = lazy(() => import('./components/logs/LogsPage'));
const TopologyPage = lazy(() => import('./components/topology/TopologyPage'));
const DeviceDetailPage = lazy(() => import('./pages/DeviceDetailPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const ObservabilityPage = lazy(() => import('./pages/ObservabilityPage'));
const AutomationHubLinksPage = lazy(() => import('./pages/AutomationHubLinksPage'));
const DiagnosisPage = lazy(() => import('./pages/DiagnosisPage'));
const CloudAccountsPage = lazy(() => import('./pages/CloudAccountsPage'));
const CloudIntentsPage = lazy(() => import('./pages/CloudIntentsPage'));
const PreventiveChecksPage = lazy(() => import('./pages/PreventiveChecksPage'));
const MonitoringProfilesPage = lazy(() => import('./pages/MonitoringProfilesPage'));
const SourceOfTruthPage = lazy(() => import('./pages/SourceOfTruthPage'));
const StateHistoryPage = lazy(() => import('./pages/StateHistoryPage'));
const IntentTemplatesPage = lazy(() => import('./pages/IntentTemplatesPage'));
const ServiceGroupsPage = lazy(() => import('./pages/ServiceGroupsPage'));
const OperationsReportsPage = lazy(() => import('./pages/OperationsReportsPage'));
const EditionComparePage = lazy(() => import('./pages/EditionComparePage'));
const PreviewContributionPage = lazy(() => import('./pages/PreviewContributionPage'));
const ImagePage = lazy(() => import('./components/images/ImagePage'));
const PolicyPage = lazy(() => import('./components/policy/PolicyPage'));
const SettingsPage = lazy(() => import('./components/settings/SettingsPage'));
const NotificationsPage = lazy(() => import('./components/notifications/NotificationsPage'));
const AuditPage = lazy(() => import('./components/audit/AuditPage'));
const CompliancePage = lazy(() => import('./components/compliance/CompliancePage'));
const DiscoveryPage = lazy(() => import('./components/discovery/DiscoveryPage'));
const ApprovalPage = lazy(() => import('./components/approval/ApprovalPage'));
const SiteListPage = lazy(() => import('./pages/SiteListPage'));
const WirelessPage = lazy(() => import('./pages/WirelessPage'));
const ZtpPage = lazy(() => import('./components/ztp/ZtpPage'));
const FabricPage = lazy(() => import('./components/fabric/FabricPage'));
const VisualConfigPage = lazy(() => import('./components/visual-config/VisualConfigPage'));
const UserManagementPage = lazy(() => import('./components/users/UserManagementPage'));

const RouteFallback = () => (
  <div className="min-h-[100dvh] w-full flex flex-col items-center justify-center bg-slate-100 dark:bg-[#0f172a] gap-4">
    <div className="w-14 h-14 rounded-full bg-gradient-to-br from-blue-500/20 to-cyan-500/20 flex items-center justify-center animate-glow-pulse">
      <div className="w-10 h-10 rounded-full bg-white dark:bg-[#1b1d1f] flex items-center justify-center shadow-lg">
        <div className="w-5 h-5 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
      </div>
    </div>
    <div className="text-sm font-semibold text-slate-500 dark:text-slate-400 animate-pulse-slow">
      {t('common_loading', 'Loading...')}
    </div>
  </div>
);

const PolicyBlockedPage = ({ blockState }) => <ProductPolicyBlockCard blockState={blockState} fullPage />;

const NotFoundPage = () => (
  <div className="h-full w-full min-h-[calc(100dvh-9rem)] bg-[#f4f5f9] dark:bg-[#0e1012] p-6 flex items-center justify-center">
    <div className="max-w-xl w-full rounded-2xl border border-gray-300 bg-white dark:bg-[#1b1d1f] dark:border-gray-700 px-8 py-12 text-center animate-scale-in">
      {/* Floating 404 badge */}
      <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-gradient-to-br from-blue-500/20 to-indigo-500/20 dark:from-blue-500/10 dark:to-indigo-500/10 flex items-center justify-center animate-float">
        <span className="text-3xl font-black bg-gradient-to-r from-blue-500 to-indigo-500 bg-clip-text text-transparent">404</span>
      </div>
      <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">{t('app_not_found_title')}</h2>
      <p className="mt-3 text-sm text-gray-500 dark:text-gray-400 leading-relaxed">{t('app_not_found_desc')}</p>
      <a
        href="/"
        className="inline-flex mt-6 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-[0.97] text-white text-sm font-bold shadow-lg shadow-blue-500/20 transition-all duration-200"
      >
        {t('common_go_dashboard')}
      </a>
    </div>
  </div>
);

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error('Unhandled UI error:', error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="min-h-[100dvh] w-full flex items-center justify-center bg-[#f4f5f9] dark:bg-[#0e1012] p-6">
        <div className="max-w-xl w-full rounded-2xl border border-red-200 bg-red-50/80 dark:bg-red-950/20 dark:border-red-900 px-8 py-12 text-center animate-scale-in">
          <div className="w-16 h-16 mx-auto mb-5 rounded-full bg-gradient-to-br from-red-500/20 to-orange-500/20 flex items-center justify-center animate-float">
            <span className="text-2xl">⚠️</span>
          </div>
          <h2 className="text-xl font-bold text-red-900 dark:text-red-200">{t('error_500_title', 'Internal Server Error')}</h2>
          <p className="mt-3 text-sm text-red-800 dark:text-red-300">{t('error_500_server')}</p>
          <a
            href="/"
            className="inline-flex mt-6 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-[0.97] text-white text-sm font-bold shadow-lg shadow-blue-500/20 transition-all duration-200"
          >
            {t('common_go_dashboard')}
          </a>
        </div>
      </div>
    );
  }
}

const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const token = localStorage.getItem('authToken');
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (loading || !user) {
    return <RouteFallback />;
  }

  return (
    <ProductPolicyProvider enabled={Boolean(user)}>
      <FirstRunWizard />
      {children}
    </ProductPolicyProvider>
  );
};

const SurfaceRouteGate = ({ surfaceKey, children }) => {
  const { manifest, loading, error } = useProductPolicy();

  if (loading && !manifest) return <RouteFallback />;

  const policyState = getSurfacePolicyState(
    manifest,
    surfaceKey,
    t,
    t('app_policy_blocked_default_reason'),
  );
  if (!policyState.access) {
    if (error) {
      return <PolicyBlockedPage blockState={getSurfacePolicyState(null, surfaceKey, t, t('policy_blocked_reason_verify_failed')).blockState} />;
    }
    return children;
  }

  if (policyState.visible && policyState.navigable) {
    return children;
  }

  return <PolicyBlockedPage blockState={policyState.blockState} />;
};

function App() {
  const locale = useLocaleRerender();

  return (
    <ThemeProvider>
      <ToastProvider>
        <GlobalHttpErrorBridge />
        <HaStandbyOverlay />
        <AuthProvider>
          <IssuePollingProvider>
            <BrowserRouter>
              <AppErrorBoundary>
                <Suspense key={`suspense-${locale}`} fallback={<RouteFallback />}>
                  <Routes>
                    <Route path="/login" element={<LoginPage />} />

                    <Route
                      path="/*"
                      element={
                        <ProtectedRoute>
                          <Layout>
                            <Routes>
                            <Route path="/" element={<SurfaceRouteGate surfaceKey="dashboard"><DashboardPage /></SurfaceRouteGate>} />
                            <Route path="/devices" element={<SurfaceRouteGate surfaceKey="devices"><DeviceListPage /></SurfaceRouteGate>} />
                            <Route path="/devices/:id" element={<SurfaceRouteGate surfaceKey="devices"><DeviceDetailPage /></SurfaceRouteGate>} />
                            <Route path="/sites" element={<SurfaceRouteGate surfaceKey="sites"><SiteListPage /></SurfaceRouteGate>} />
                            <Route path="/topology" element={<SurfaceRouteGate surfaceKey="topology"><TopologyPage /></SurfaceRouteGate>} />
                            <Route path="/config" element={<SurfaceRouteGate surfaceKey="config"><ConfigPage /></SurfaceRouteGate>} />
                            <Route path="/images" element={<SurfaceRouteGate surfaceKey="images"><ImagePage /></SurfaceRouteGate>} />
                            <Route path="/visual-config" element={<SurfaceRouteGate surfaceKey="visual_config"><VisualConfigPage /></SurfaceRouteGate>} />
                            <Route path="/policy" element={<SurfaceRouteGate surfaceKey="policy"><PolicyPage /></SurfaceRouteGate>} />
                            <Route path="/ztp" element={<SurfaceRouteGate surfaceKey="ztp"><ZtpPage /></SurfaceRouteGate>} />
                            <Route path="/fabric" element={<SurfaceRouteGate surfaceKey="fabric"><FabricPage /></SurfaceRouteGate>} />
                            <Route path="/compliance" element={<SurfaceRouteGate surfaceKey="compliance"><CompliancePage /></SurfaceRouteGate>} />
                            <Route path="/discovery" element={<SurfaceRouteGate surfaceKey="discovery"><DiscoveryPage /></SurfaceRouteGate>} />
                            <Route path="/logs" element={<SurfaceRouteGate surfaceKey="logs"><LogsPage /></SurfaceRouteGate>} />
                            <Route path="/audit" element={<SurfaceRouteGate surfaceKey="audit"><AuditPage /></SurfaceRouteGate>} />
                            <Route path="/wireless" element={<SurfaceRouteGate surfaceKey="wireless"><WirelessPage /></SurfaceRouteGate>} />
                            <Route path="/notifications" element={<SurfaceRouteGate surfaceKey="notifications"><NotificationsPage /></SurfaceRouteGate>} />
                            <Route path="/settings" element={<SurfaceRouteGate surfaceKey="settings"><SettingsPage /></SurfaceRouteGate>} />
                            <Route path="/cloud/accounts" element={<SurfaceRouteGate surfaceKey="cloud_accounts"><CloudAccountsPage /></SurfaceRouteGate>} />
                            <Route path="/cloud/intents" element={<SurfaceRouteGate surfaceKey="cloud_intents"><CloudIntentsPage /></SurfaceRouteGate>} />
                            <Route path="/preventive-checks" element={<SurfaceRouteGate surfaceKey="preventive_checks"><PreventiveChecksPage /></SurfaceRouteGate>} />
                            <Route path="/monitoring-profiles" element={<SurfaceRouteGate surfaceKey="monitoring_profiles"><MonitoringProfilesPage /></SurfaceRouteGate>} />
                            <Route path="/source-of-truth" element={<SurfaceRouteGate surfaceKey="source_of_truth"><SourceOfTruthPage /></SurfaceRouteGate>} />
                            <Route path="/state-history" element={<SurfaceRouteGate surfaceKey="state_history"><StateHistoryPage /></SurfaceRouteGate>} />
                            <Route path="/intent-templates" element={<SurfaceRouteGate surfaceKey="intent_templates"><IntentTemplatesPage /></SurfaceRouteGate>} />
                            <Route path="/service-groups" element={<SurfaceRouteGate surfaceKey="service_groups"><ServiceGroupsPage /></SurfaceRouteGate>} />
                            <Route path="/operations-reports" element={<SurfaceRouteGate surfaceKey="operations_reports"><OperationsReportsPage /></SurfaceRouteGate>} />
                            <Route path="/edition/compare" element={<SurfaceRouteGate surfaceKey="edition_compare"><EditionComparePage /></SurfaceRouteGate>} />
                            <Route path="/users" element={<SurfaceRouteGate surfaceKey="users"><UserManagementPage /></SurfaceRouteGate>} />
                            <Route path="/approval" element={<SurfaceRouteGate surfaceKey="approval"><ApprovalPage /></SurfaceRouteGate>} />
                            <Route path="/observability" element={<SurfaceRouteGate surfaceKey="observability"><ObservabilityPage mode="overview" /></SurfaceRouteGate>} />
                            <Route path="/observability/deep-dive" element={<SurfaceRouteGate surfaceKey="observability"><ObservabilityPage mode="deep-dive" /></SurfaceRouteGate>} />
                            <Route path="/automation" element={<SurfaceRouteGate surfaceKey="operations_home"><AutomationHubLinksPage /></SurfaceRouteGate>} />
                            <Route path="/diagnosis" element={<SurfaceRouteGate surfaceKey="diagnosis"><DiagnosisPage /></SurfaceRouteGate>} />
                            <Route path="/preview/contribute" element={<SurfaceRouteGate surfaceKey="preview_contribute"><PreviewContributionPage /></SurfaceRouteGate>} />
                            <Route path="*" element={<NotFoundPage />} />
                            </Routes>
                          </Layout>
                        </ProtectedRoute>
                      }
                    />
                  </Routes>
                </Suspense>
              </AppErrorBoundary>
            </BrowserRouter>
          </IssuePollingProvider>
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}

export default App;
