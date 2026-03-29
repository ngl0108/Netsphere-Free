import axios from 'axios';
import { getApiBaseUrl } from './baseUrl';

// --------------------------------------------------------------------------
// 1. Axios 인스턴스 및 기본 설정
// --------------------------------------------------------------------------
const API_BASE_URL = getApiBaseUrl();

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const authProbeClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

let authProbePromise = null;
let authRefreshPromise = null;
let unauthorizedStrike = 0;
let lastUnauthorizedAt = 0;
let unauthorizedWindowStartedAt = 0;
let authRedirectInProgress = false;
let lastAuthErrorToastAt = 0;

const UNAUTHORIZED_BURST_DEBOUNCE_MS = 2500;
const UNAUTHORIZED_WINDOW_MS = 45000;
const UNAUTHORIZED_HARD_LOGOUT_MIN_BURSTS = 3;
const UNAUTHORIZED_HARD_LOGOUT_MIN_ELAPSED_MS = 8000;
const UNAUTHORIZED_BACKGROUND_HARD_LOGOUT_MIN_BURSTS = 4;
const UNAUTHORIZED_BACKGROUND_HARD_LOGOUT_MIN_ELAPSED_MS = 20000;
const AUTH_ERROR_TOAST_COOLDOWN_MS = 15000;

const AUTH_BACKGROUND_ENDPOINT_HINTS = [
  '/sdn/issues/unread-count',
  '/sdn/issues/active',
  '/ops/kpi/readiness/history',
  '/ops/release-evidence',
  '/sdn/dashboard/change-traces',
  '/observability/summary',
  '/observability/devices',
];

const AUTH_RETRYABLE_CODES = new Set([
  'AUTH_SESSION_MISSING',
]);

const AUTH_FORCE_LOGOUT_CODES = new Set([
  'AUTH_TOKEN_INVALID',
  'AUTH_NOT_AUTHENTICATED',
  'AUTH_CREDENTIALS_INVALID',
  'AUTH_INVALID_CREDENTIALS',
  'AUTH_USER_NOT_FOUND',
  'AUTH_SESSION_EXPIRED',
  'AUTH_SESSION_IDLE_TIMEOUT',
  'AUTH_SESSION_REVOKED',
  'AUTH_SESSION_MISMATCH',
]);

const hardLogoutToLogin = () => {
  if (authRedirectInProgress) return;
  authRedirectInProgress = true;
  resetUnauthorizedState();
  sessionStorage.setItem('nm_auth_redirect_reason', '401');
  localStorage.removeItem('authToken');
  localStorage.removeItem('authUser');
  localStorage.removeItem('authLastActiveAt');
  if (!window.location.pathname.includes('/login')) {
    window.location.href = '/login';
  }
  window.setTimeout(() => {
    authRedirectInProgress = false;
  }, 2000);
};

const resetUnauthorizedState = () => {
  unauthorizedStrike = 0;
  lastUnauthorizedAt = 0;
  unauthorizedWindowStartedAt = 0;
};

const recordUnauthorizedStrike = (now) => {
  if (!unauthorizedWindowStartedAt || now - unauthorizedWindowStartedAt > UNAUTHORIZED_WINDOW_MS) {
    unauthorizedWindowStartedAt = now;
    unauthorizedStrike = 0;
  }
  if (!lastUnauthorizedAt || now - lastUnauthorizedAt >= UNAUTHORIZED_BURST_DEBOUNCE_MS) {
    unauthorizedStrike += 1;
  }
  lastUnauthorizedAt = now;
};

const isBackgroundAuthRequest = (config = {}) => {
  if (config?.__nmBackgroundPoll === true) return true;
  const method = String(config?.method || 'get').toLowerCase();
  if (method !== 'get') return false;
  const url = String(config?.url || '');
  return AUTH_BACKGROUND_ENDPOINT_HINTS.some((hint) => url.includes(hint));
};

const shouldBypassAuthRedirect = (requestUrl = '') => {
  const url = String(requestUrl || '');
  return (
    url.includes('/auth/login') ||
    url.includes('/auth/login/verify-otp') ||
    url.includes('/auth/me/email/verify') ||
    url.includes('/auth/refresh')
  );
};

const normalizeAuthBypassError = (error, requestUrl, apiError) => {
  const url = String(requestUrl || '');
  const isOtpVerify = url.includes('/auth/login/verify-otp');
  const fallbackCode = isOtpVerify ? 'AUTH_OTP_INVALID' : 'AUTH_CREDENTIALS_INVALID';
  const fallbackMessage = isOtpVerify ? 'Invalid verification code' : 'Incorrect username or password';
  const nextCode = String(apiError?.code || fallbackCode).trim() || fallbackCode;
  const nextMessage = String(apiError?.message || fallbackMessage).trim() || fallbackMessage;
  const currentData = error?.response?.data && typeof error.response.data === 'object' ? error.response.data : {};
  const nextDetail = currentData?.detail && typeof currentData.detail === 'object'
    ? { ...currentData.detail, code: nextCode, message: nextMessage }
    : { code: nextCode, message: nextMessage };
  error.message = nextMessage;
  if (error?.response) {
    error.response = {
      ...error.response,
      data: {
        ...currentData,
        detail: nextDetail,
      },
    };
  }
  return error;
};

const probeSession = async (token) => {
  if (!token) return false;
  if (authProbePromise) return authProbePromise;

  authProbePromise = authProbeClient
    .get('/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
      timeout: 5000,
    })
    .then(() => true)
    .catch((err) => {
      const status = Number(err?.response?.status || 0);
      if (status === 401 || status === 403) return false;
      // Network/proxy failure is inconclusive; avoid forced logout on probe transport errors.
      return null;
    })
    .finally(() => {
      authProbePromise = null;
    });

  return authProbePromise;
};

const refreshAccessToken = async (token) => {
  if (!token) return null;
  if (authRefreshPromise) return authRefreshPromise;

  authRefreshPromise = authProbeClient
    .post(
      '/auth/refresh',
      {},
      {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 7000,
      },
    )
    .then((res) => {
      const nextToken =
        res?.data?.access_token ||
        res?.data?.token ||
        res?.data?.data?.access_token ||
        res?.data?.data?.token;
      const normalized = String(nextToken || '').trim();
      if (!normalized) return null;
      localStorage.setItem('authToken', normalized);
      localStorage.setItem('authLastActiveAt', String(Date.now()));
      return normalized;
    })
    .catch(() => null)
    .finally(() => {
      authRefreshPromise = null;
    });

  return authRefreshPromise;
};

const extractApiError = (rawData) => {
  const data = rawData && typeof rawData === 'object' ? rawData : {};
  const envelope = data?.error && typeof data.error === 'object' ? data.error : {};
  const detail = data?.detail;

  const code =
    typeof envelope?.code === 'string'
      ? envelope.code
      : typeof detail?.code === 'string'
        ? detail.code
        : '';

  const message =
    typeof envelope?.message === 'string'
      ? envelope.message
      : typeof detail === 'string'
        ? detail
        : typeof detail?.message === 'string'
          ? detail.message
          : typeof data?.message === 'string'
            ? data.message
            : '';

  const details = envelope?.details ?? detail?.details ?? (typeof detail === 'object' ? detail : null);

  return { code: String(code || '').trim(), message: String(message || '').trim(), details };
};

const getResponseRequestId = (response) => {
  const headers = response?.headers || {};
  const requestId =
    headers['x-request-id'] ||
    headers['X-Request-ID'] ||
    headers['x-correlation-id'] ||
    headers['X-Correlation-ID'];
  return String(requestId || '').trim();
};

const shouldForceLogoutFor401 = ({ code, details }) => {
  if (details && typeof details === 'object' && typeof details.force_logout === 'boolean') {
    return details.force_logout;
  }
  if (!code) return false;
  if (AUTH_RETRYABLE_CODES.has(code)) return false;
  return AUTH_FORCE_LOGOUT_CODES.has(code);
};

// 요청 인터셉터 (JWT 토큰 자동 포함)
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('authToken');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 응답 인터셉터 (401 에러 발생 시 로그인 페이지로 리다이렉트)
api.interceptors.response.use(
  (response) => {
    resetUnauthorizedState();

    const payload = response?.data;
    if (payload && typeof payload === 'object' && !(payload instanceof Blob)) {
      if (Object.prototype.hasOwnProperty.call(payload, 'success') && Object.prototype.hasOwnProperty.call(payload, 'data')) {
        if (payload.success === true) {
          response.data = payload.data;
        } else {
          // [NEW] Handle success=false payloads as errors
          const errorMsg = payload.message || 'Operation failed';
          console.warn(`API responded with success=false: ${errorMsg}`);
          // You might want to throw here, but for now we keep response to handle in components
          // or construct an error object.
          // Let's modify response.data to be consistent or keep it raw?
          // For now, trust the wrapper logic in components or throw error
          // throw new Error(errorMsg); // Optional: Standardize error throwing
        }
      }
    }
    return response;
  },
  async (error) => {
    const status = error.response ? error.response.status : null;
    const data = error.response ? error.response.data : {};
    const requestId = getResponseRequestId(error?.response);
    const apiError = extractApiError(data);
    const detail = data?.detail;
    const detailMessage = apiError.message;

    // 1. HA Standby Redirect
    if (status === 503) {
      if (detail && typeof detail === 'object' && (detail.leader_url || detail.leader_id || detail.role === 'standby')) {
        try {
          window.dispatchEvent(new CustomEvent('netmanager:ha-standby', { detail }));
        } catch (e) {
          // ignore
        }
        return Promise.reject(error);
      }
    }

    if (status === 401) {
      const originalConfig = error?.config || {};
      const requestUrl = String(originalConfig?.url || '');
      const now = Date.now();
      const isBackgroundRequest = isBackgroundAuthRequest(originalConfig);
      if (shouldBypassAuthRedirect(requestUrl)) {
        return Promise.reject(normalizeAuthBypassError(error, requestUrl, apiError));
      }

      if (!isBackgroundRequest || now - lastAuthErrorToastAt >= AUTH_ERROR_TOAST_COOLDOWN_MS) {
        try {
          window.dispatchEvent(
            new CustomEvent('netmanager:http-error', {
              detail: { status, code: apiError.code, message: detailMessage, requestId },
            }),
          );
          lastAuthErrorToastAt = now;
        } catch (e) {
          void e;
        }
      }

      const token = localStorage.getItem('authToken');
      if (!token) {
        hardLogoutToLogin();
        return Promise.reject(error);
      }

      if (originalConfig.__nmRetryAfterRefresh !== true) {
        const refreshedToken = await refreshAccessToken(token);
        if (refreshedToken) {
          const retryConfig = {
            ...originalConfig,
            __nmRetryAfterRefresh: true,
            headers: {
              ...(originalConfig.headers || {}),
              Authorization: `Bearer ${refreshedToken}`,
            },
          };
          return api.request(retryConfig);
        }
      }

      if (originalConfig.__nmRetryAfterProbe !== true) {
        const currentToken = localStorage.getItem('authToken') || token;
        const sessionStillValid = await probeSession(currentToken);
        if (sessionStillValid === true) {
          const retryConfig = {
            ...originalConfig,
            __nmRetryAfterProbe: true,
            headers: {
              ...(originalConfig.headers || {}),
              Authorization: `Bearer ${currentToken}`,
            },
          };
          return api.request(retryConfig);
        }
        if (sessionStillValid === null) {
          // Inconclusive probe (network/proxy issue). Keep session and avoid forced logout.
          return Promise.reject(error);
        }
      }

      recordUnauthorizedStrike(now);
      const elapsedMs = now - unauthorizedWindowStartedAt;
      const minBursts = isBackgroundRequest
        ? UNAUTHORIZED_BACKGROUND_HARD_LOGOUT_MIN_BURSTS
        : UNAUTHORIZED_HARD_LOGOUT_MIN_BURSTS;
      const minElapsedMs = isBackgroundRequest
        ? UNAUTHORIZED_BACKGROUND_HARD_LOGOUT_MIN_ELAPSED_MS
        : UNAUTHORIZED_HARD_LOGOUT_MIN_ELAPSED_MS;

      const forceLogoutByCode = shouldForceLogoutFor401(apiError);
      const forceLogout = (forceLogoutByCode && !isBackgroundRequest) ||
        (unauthorizedStrike >= minBursts && elapsedMs >= minElapsedMs);
      if (forceLogout) {
        hardLogoutToLogin();
      }
      return Promise.reject(error);
    }

    if (status === 403 || status === 404 || status >= 500) {
      try {
        window.dispatchEvent(
          new CustomEvent('netmanager:http-error', {
            detail: { status, code: apiError.code, message: detailMessage, requestId },
          }),
        );
      } catch (e) {
        void e;
      }
      if (status >= 500) {
        console.error('Server Error:', data);
      }
      return Promise.reject(error);
    }

    if (!status) {
      try {
        window.dispatchEvent(
          new CustomEvent('netmanager:http-error', {
            detail: { status: 0, message: error?.message || '' },
          }),
        );
      } catch (e) {
        void e;
      }
    }

    return Promise.reject(error);
  }
);

// --------------------------------------------------------------------------
// 2. AuthService (로그인/인증)
// --------------------------------------------------------------------------
export const AuthService = {
  login: async (username, password) => {
    // 백엔드 엔드포인트에 맞춰 수정 (보통 /auth/login 또는 /token)
    // 예시: OAuth2 Password Request
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    return api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },
  verifyOtp: async (challengeId, otp) => api.post('/auth/login/verify-otp', { challenge_id: challengeId, otp }),
  bootstrapStatus: () => api.get('/auth/bootstrap/status'),
  createInitialAdmin: (payload) => api.post('/auth/bootstrap/initial-admin', payload),
  sendMyEmailVerification: async () => api.post('/auth/me/email/send-verification'),
  verifyMyEmail: async (challengeId, otp) => api.post('/auth/me/email/verify', { challenge_id: challengeId, otp }),
  logout: () => {
    authProbePromise = null;
    authRefreshPromise = null;
    localStorage.removeItem('authToken');
    localStorage.removeItem('authUser'); // [FIX] Clear cached user data
  },
  refresh: () => api.post('/auth/refresh'),
  me: () => api.get('/auth/me'), // 현재 사용자 정보
  acceptEula: () => api.post('/auth/me/accept-eula'),
  changePasswordMe: (currentPassword, newPassword) => api.post('/auth/me/change-password', null, { params: { current_password: currentPassword, new_password: newPassword } }),
  updateMyProfile: (payload) => api.patch('/auth/me/profile', payload),
};

export const LicenseService = {
  status: () => api.get('/license/status'),
  install: (licenseJwt) => api.post('/license/install', { license_jwt: licenseJwt }),
  uninstall: () => api.delete('/license/install'),
  listRevocations: () => api.get('/license/revocations'),
  revokeInstalled: (reason = 'manual_revoke') =>
    api.post('/license/revoke', { installed_license: true, reason }),
  revokeJti: (jti, reason = 'manual_revoke') =>
    api.post('/license/revoke', { installed_license: false, jti, reason }),
  unrevokeJti: (jti) => api.delete(`/license/revoke/${encodeURIComponent(String(jti || '').trim())}`),
};

export const SupportService = {
  bundle: (params = {}) => api.get('/support/bundle', { params, responseType: 'blob' }),
  restore: (file, options = {}) => {
    const form = new FormData();
    form.append('bundle', file);
    form.append('apply', String(options.apply !== false));
    form.append('restore_settings', String(options.restoreSettings !== false));
    return api.post('/support/restore', form, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
};

export const ObservabilityService = {
  summary: () => api.get('/observability/summary'),
  devices: () => api.get('/observability/devices'),
  deviceTimeseries: (deviceId, minutes = 360, limit = 720) =>
    api.get(`/observability/devices/${deviceId}/timeseries`, { params: { minutes, limit } }),
  deviceInterfaces: (deviceId) => api.get(`/observability/devices/${deviceId}/interfaces`),
  interfaceTimeseries: (deviceId, name, minutes = 360, limit = 720) =>
    api.get(`/observability/devices/${deviceId}/interfaces/timeseries`, { params: { name, minutes, limit } }),
};

// --------------------------------------------------------------------------
// 3. DeviceService (장비 관리 및 SDN 핵심 기능 통합)
// --------------------------------------------------------------------------
export const DeviceService = {
  // --- [Basic] 기존 장비 CRUD ---
  getAll: () => api.get('/devices/'),
  getDevices: () => api.get('/devices/'),
  getDetail: (id) => api.get(`/devices/${id}`),
  getManagedSummary: () => api.get('/devices/managed-summary'),
  promoteToManaged: (id) => api.post(`/devices/${id}/manage`),
  releaseManagement: (id) => api.post(`/devices/${id}/release-management`),
  create: (data) => api.post('/devices/', data),
  update: (id, data) => api.put(`/devices/${id}`, data),
  delete: (id) => api.delete(`/devices/${id}`),
  syncDevice: (id) => api.post(`/devices/${id}/sync`),
  getInventory: (id) => api.get(`/devices/${id}/inventory`),
  exportInventory: (id, format = 'xlsx') =>
    api.get(`/devices/${id}/inventory/export`, { params: { format }, responseType: 'blob' }),

  // --- [Dashboard] 통계 ---
  getDashboardStats: (siteId) => api.get('/sdn/dashboard/stats', { params: { site_id: siteId } }),
  getDashboardChangeTraces: (params = {}) => api.get('/sdn/dashboard/change-traces', { params }),
  getAnalytics: (range) => api.get(`/devices/analytics?range=${range}`),
  // getTopology: Moved to SDNService for consistency with PathTrace
  getTopology: (params = {}) => api.get('/devices/topology/links', { params }),
  getEndpointGroupDetails: (deviceId, port, params = {}) => api.get('/devices/topology/endpoint-group', { params: { device_id: deviceId, port, ...params } }),

  // --- [Feature 1] 사이트 관리 (Site Ops) ---
  getSites: () => api.get('/sites/'),
  createSite: (data) => api.post('/sites/', data),
  updateSite: (id, data) => api.put(`/sites/${id}`, data),
  deleteSite: (id) => api.delete(`/sites/${id}`),
  getSiteDevices: (siteId) => api.get(`/sites/${siteId}/devices`),
  assignDevicesToSite: (siteId, deviceIds) => api.post(`/sites/${siteId}/devices`, { device_ids: deviceIds }),

  // --- [Feature 2] 사이트 정책 설계 (Site Policies) ---
  getSiteVlans: (siteId) => api.get(`/sites/${siteId}/vlans`),
  createSiteVlan: (siteId, data) => api.post(`/sites/${siteId}/vlans`, data),

  // --- [Step 1] 스마트 템플릿 (Templates) ---
  getTemplates: () => api.get('/templates/'),
  createTemplate: (data) => api.post('/templates/', data),
  updateTemplate: (id, data) => api.put(`/templates/${id}`, data),
  deleteTemplate: (id) => api.delete(`/templates/${id}`),
  previewTemplate: (data) => api.post('/templates/preview', data),

  // [추가] 템플릿 배포 함수 (ConfigPage에서 사용)
  deployTemplate: (templateId, payloadOrDeviceIds) => {
    const payload = Array.isArray(payloadOrDeviceIds)
      ? { device_ids: payloadOrDeviceIds }
      : { ...(payloadOrDeviceIds || {}) };
    return api.post(`/templates/${templateId}/deploy`, payload);
  },
  dryRunTemplate: (templateId, deviceIds, options = {}) =>
    api.post(`/templates/${templateId}/dry-run`, {
      device_ids: deviceIds,
      variables: options.variables || {},
      include_rendered: !!options.includeRendered,
      rollback_on_failure: options.rollbackOnFailure !== false,
      post_check_enabled: options.postCheckEnabled !== false,
      post_check_commands: Array.isArray(options.postCheckCommands) ? options.postCheckCommands : [],
      canary_count: Number.isFinite(Number(options.canaryCount)) ? Math.max(0, Math.trunc(Number(options.canaryCount))) : 0,
      wave_size: Number.isFinite(Number(options.waveSize)) ? Math.max(0, Math.trunc(Number(options.waveSize))) : 0,
      stop_on_wave_failure: options.stopOnWaveFailure !== false,
      inter_wave_delay_seconds: Number.isFinite(Number(options.interWaveDelaySeconds)) ? Math.max(0, Number(options.interWaveDelaySeconds)) : 0,
    }),

  // --- [Step 2] 변수 관리 (Variables) ---
  updateVariables: (targetType, targetId, variables) =>
    api.put(`/vars/${targetType}/${targetId}`, { variables }),

  // --- [Feature 3] 무선 관리 (Wireless Ops) ---
  getWirelessOverview: () => api.get('/devices/wireless/overview'),
};

// --------------------------------------------------------------------------
// 4. LogService & IssueService & SDNService
// --------------------------------------------------------------------------
export const LogService = {
  getRecentLogs: (days) => api.get('/logs/recent', { params: { days } }),
};

const ISSUE_QUERY_CACHE_TTL_MS = 1500;
const issueQueryCache = new Map();

const toStableQueryKey = (params = {}) => {
  const entries = Object.entries(params || {})
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .sort(([a], [b]) => String(a).localeCompare(String(b)));
  return entries.map(([k, v]) => `${String(k)}=${Array.isArray(v) ? v.join(',') : String(v)}`).join('&');
};

const withIssueQueryCache = (cacheKey, fetcher) => {
  const now = Date.now();
  const key = String(cacheKey || '');
  const hit = issueQueryCache.get(key);
  if (hit && now < Number(hit.expiresAt || 0)) {
    return hit.promise;
  }
  const promise = Promise.resolve()
    .then(fetcher)
    .catch((error) => {
      issueQueryCache.delete(key);
      throw error;
    });
  issueQueryCache.set(key, { promise, expiresAt: now + ISSUE_QUERY_CACHE_TTL_MS });
  return promise;
};

const clearIssueQueryCache = () => {
  issueQueryCache.clear();
};

export const IssueService = {
  getActiveIssues: (params = {}) => withIssueQueryCache(
    `active:${toStableQueryKey(params)}`,
    () => api.get('/sdn/issues/active', { params, __nmBackgroundPoll: true }),
  ),
  getUnreadCount: () => withIssueQueryCache(
    'unread',
    () => api.get('/sdn/issues/unread-count', { __nmBackgroundPoll: true }),
  ),
  getAutomationPreview: (id) => api.get(`/sdn/issues/${id}/automation`),
  runAutomation: async (id) => {
    const res = await api.post(`/sdn/issues/${id}/automation/run`);
    clearIssueQueryCache();
    return res;
  },
  markAsRead: async (id) => {
    const res = await api.put(`/sdn/issues/${id}/read`);
    clearIssueQueryCache();
    return res;
  },
  markAllAsRead: async () => {
    const res = await api.put('/sdn/issues/read-all');
    clearIssueQueryCache();
    return res;
  },
  resolveIssue: async (id) => {
    const res = await api.put(`/sdn/issues/${id}/resolve`);
    clearIssueQueryCache();
    return res;
  },
  resolveAll: async () => {
    const res = await api.post('/sdn/issues/resolve-all');
    clearIssueQueryCache();
    return res;
  },
  listActions: (issueId) => api.get(`/sdn/issues/${issueId}/actions`),
  createAction: async (issueId, payload = {}) => {
    const res = await api.post(`/sdn/issues/${issueId}/actions`, payload);
    clearIssueQueryCache();
    return res;
  },
  updateAction: async (actionId, payload = {}) => {
    const res = await api.put(`/sdn/actions/${actionId}`, payload);
    clearIssueQueryCache();
    return res;
  },
  getApprovalContext: (issueId) => api.get(`/sdn/issues/${issueId}/approval-context`),
  getServiceImpact: (issueId) => api.get(`/sdn/issues/${issueId}/service-impact`),
  getSop: (issueId) => api.get(`/sdn/issues/${issueId}/sop`),
  listKnowledge: (issueId) => api.get(`/sdn/issues/${issueId}/knowledge`),
  createKnowledge: async (issueId, payload = {}) => {
    const res = await api.post(`/sdn/issues/${issueId}/knowledge`, payload);
    clearIssueQueryCache();
    return res;
  },
};

export const SDNService = {
  getDevices: () => api.get('/devices'), // [FIX] 장비 목록 조회 추가
  getImages: () => api.get('/sdn/images'),
  uploadImage: (formData) => api.post('/sdn/images', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  deleteImage: (id) => api.delete(`/sdn/images/${id}`),

  // [SWIM] Deployment
  deployImage: (imageId, deviceIds) => api.post(`/sdn/images/${imageId}/deploy`, { device_ids: deviceIds }),
  getUpgradeJobs: () => api.get('/sdn/images/jobs'),

  getPolicies: () => api.get('/sdn/policies'),
  createPolicy: (data) => api.post('/sdn/policies', data),
  updatePolicy: (id, data) => api.put(`/sdn/policies/${id}`, data),
  deletePolicy: (id) => api.delete(`/sdn/policies/${id}`),
  previewPolicy: (id) => api.get(`/sdn/policies/${id}/preview`),
  deployPolicy: (id, deviceIds) => api.post(`/sdn/policies/${id}/deploy`, { device_ids: deviceIds }), // List[int] wrapped in object

  // [PathTrace] Topology
  getTopology: (params = {}) => api.get('/devices/topology/links', { params }),
  tracePath: (srcIp, dstIp) => api.post('/topology/path-trace', { src_ip: srcIp, dst_ip: dstIp }),

  // [Fabric] Automation
  generateFabric: (payload) => api.post('/fabric/generate', payload),
  deployFabric: (payload) => api.post('/fabric/deploy', payload),

  getAuditLogs: (params) => api.get('/audit', { params }), // [NEW] Audit Logs


  getUsers: () => api.get('/auth/users'), // 사용자 목록
  createUser: (data) => api.post('/auth/users', data),
  updateUser: (id, data) => api.put(`/auth/users/${id}`, data),
  deleteUser: (id) => api.delete(`/auth/users/${id}`),
};

export const DiagnosisService = {
  oneClick: (srcIp, dstIp, includeShowCommands = true) =>
    api.post('/diagnosis/one-click', { src_ip: srcIp, dst_ip: dstIp, include_show_commands: includeShowCommands }),
};

export const VisualConfigService = {
  getBlueprints: () => api.get('/visual/blueprints'),
  createBlueprint: (payload) => api.post('/visual/blueprints', payload),
  getBlueprint: (id) => api.get(`/visual/blueprints/${id}`),
  updateBlueprint: (id, payload) => api.put(`/visual/blueprints/${id}`, payload),
  deleteBlueprint: (id) => api.delete(`/visual/blueprints/${id}`),
  createVersion: (id, payload) => api.post(`/visual/blueprints/${id}/versions`, payload),
  previewBlueprint: (id) => api.post(`/visual/blueprints/${id}/preview`),
  deployBlueprint: (id, payload) => api.post(`/visual/blueprints/${id}/deploy`, payload),
  getDeployJob: (jobId) => api.get(`/visual/deploy-jobs/${jobId}`),
  listDeployJobsForBlueprint: (id, params) => api.get(`/visual/blueprints/${id}/deploy-jobs`, { params }),
  rollbackDeployJob: (jobId, payload) => api.post(`/visual/deploy-jobs/${jobId}/rollback`, payload),
};

export const TrafficService = {
  getTopTalkers: (params = {}) => api.get('/traffic/top-talkers', { params }),
  getTopFlows: (params = {}) => api.get('/traffic/top-flows', { params }),
  getTopApps: (params = {}) => api.get('/traffic/top-apps', { params }),
  getTopAppFlows: (params = {}) => api.get('/traffic/top-app-flows', { params }),
};

export const ComplianceService = {
  getStandards: () => api.get('/compliance/standards'),
  createStandard: (data) => api.post('/compliance/standards', data),
  deleteStandard: (id) => api.delete(`/compliance/standards/${id}`),

  addRule: (stdId, data) => api.post(`/compliance/standards/${stdId}/rules`, data),
  deleteRule: (ruleId) => api.delete(`/compliance/rules/${ruleId}`),

  runScan: (payload) => api.post('/compliance/scan', payload), // { device_ids: [], standard_id: opt }
  getReports: (deviceId) => api.get('/compliance/reports', { params: { device_id: deviceId } }),
  exportReports: (params = {}) => api.get('/compliance/reports/export', { params, responseType: 'blob' }),

  // [NEW] Config Drift
  getBackups: (deviceId) => api.get(`/compliance/drift/backups/${deviceId}`),
  setGolden: (backupId) => api.post(`/compliance/drift/golden/${backupId}`),
  checkDrift: (deviceId) => api.get(`/compliance/drift/check/${deviceId}`),
  remediateDrift: (deviceId, payload = {}) => api.post(`/compliance/drift/remediate/${deviceId}`, payload),
  remediateDriftBatch: (payload = {}) => api.post('/compliance/drift/remediate-batch', payload),
  getDriftKpiSummary: (params = {}) => api.get('/compliance/drift/kpi/summary', { params }),
};

export const JobService = {
  getStatus: (taskId) => api.get(`/jobs/${taskId}`),
};

export const DiscoveryService = {
  startScan: (data) => api.post('/discovery/scan', data),
  startNeighborCrawl: (data) => api.post('/discovery/crawl', data),
  getJobStatus: (id) => api.get(`/discovery/jobs/${id}`),
  getJobResults: (id) => api.get(`/discovery/jobs/${id}/results`),
  getJobKpi: (id) => api.get(`/discovery/jobs/${id}/kpi`),
  getKpiSummary: (params = {}) => api.get('/discovery/kpi/summary', { params }),
  getKpiAlerts: (params = {}) => api.get('/discovery/kpi/alerts', { params }),
  approveDevice: (id) => api.post(`/discovery/approve/${id}`),
  ignoreDevice: (id) => api.post(`/discovery/ignore/${id}`),
  approveAll: (jobId, options = {}) => api.post(
    `/discovery/jobs/${jobId}/approve-all`,
    null,
    { params: { policy: options.policy === true } }
  ),
};

export const DiscoveryHintService = {
  getSummary: (params = {}) => api.get('/discovery/hints/summary', { params }),
  getTelemetrySummary: (params = {}) => api.get('/discovery/hints/telemetry/summary', { params }),
  applyScoreAdjustments: (payload = {}) => api.post('/discovery/hints/rules/score-adjustments/apply', payload),
  applyAliasCandidates: (payload = {}) => api.post('/discovery/hints/rules/alias-candidates/apply', payload),
  applySeedRuleDrafts: (payload = {}) => api.post('/discovery/hints/rules/seed-rule-drafts/apply', payload),
};


// [추가] 설정 관리 서비스
export const SettingsService = {
  getGeneral: () => api.get('/settings/general'),
  updateGeneral: (data) => api.put('/settings/general', data),
  getCapabilityProfile: () => api.get('/settings/capability-profile'),
  getEffectiveCapabilityProfile: (params = {}) => api.get('/settings/capability-profile/effective', { params }),
  sendTestEmail: (toEmail) => api.post('/settings/test-email', { to_email: toEmail }),
  sendTestWebhook: (payload = {}) => api.post('/settings/test-webhook', payload),
  sendTestWebhookConnector: (payload = {}) => api.post('/settings/test-webhook-connector', payload),
  listWebhookDeliveries: (params = {}) => api.get('/settings/webhook-deliveries', { params }),
  retryWebhookDelivery: (deliveryId, payload = {}) => api.post(`/settings/webhook-deliveries/${deliveryId}/retry`, payload),
};

export const PreviewService = {
  getPolicy: () => api.get('/preview/policy'),
  updateContributionConsent: (payload) => api.post('/preview/consent/contribution', payload),
  sanitizeEntries: (payload) => api.post('/preview/sanitize', payload),
  captureFromDevice: (deviceId, payload = {}) => api.post(`/preview/devices/${deviceId}/capture`, payload),
  uploadContribution: (payload) => api.post('/preview/contributions', payload),
  listRecent: (params = {}) => api.get('/preview/contributions/recent', { params }),
  getContributionRecord: (id) => api.get(`/preview/contributions/${id}`),
};

export const CloudService = {
  listAccounts: () => api.get('/cloud/accounts'),
  getOperationsLedger: (params = {}) => api.get('/cloud/accounts/operations-ledger', { params }),
  getKpiSummary: (params = {}) => api.get('/cloud/kpi/summary', { params }),
  listProviderPresets: () => api.get('/cloud/providers/presets'),
  getProviderPreset: (provider) => api.get(`/cloud/providers/${provider}/preset`),
  preflight: (payload) => api.post('/cloud/preflight', payload),
  runPipeline: (payload = {}) => api.post('/cloud/pipeline/run', payload),
  runBootstrap: (payload = {}) => api.post('/cloud/bootstrap/run', payload),
  createAccount: (payload) => api.post('/cloud/accounts', payload),
  updateAccount: (id, payload) => api.put(`/cloud/accounts/${id}`, payload),
  deleteAccount: (id) => api.delete(`/cloud/accounts/${id}`),
  preflightAccount: (id) => api.post(`/cloud/accounts/${id}/preflight`),
  runAccountPipeline: (id, payload = {}) => api.post(`/cloud/accounts/${id}/pipeline/run`, payload),
  runAccountBootstrap: (id, payload = {}) => api.post(`/cloud/accounts/${id}/bootstrap/run`, payload),
  scanAccount: (id) => api.post(`/cloud/accounts/${id}/scan`),
  listResources: (params = {}) => api.get('/cloud/resources', { params }),
  listNormalizedResources: (params = {}) => api.get('/cloud/resources/normalized', { params }),
  getMaskedCredentials: (id) => api.get(`/cloud/accounts/${id}/credentials`),
  buildHybrid: () => api.post('/cloud/hybrid/build'),
  inferHybrid: (params = {}) => api.post('/cloud/hybrid/infer', null, { params }),
};

export const OpsService = {
  getPolicyManifest: () => api.get('/ops/policy-manifest'),
  getObservability: () => api.get('/ops/observability'),
  setObservability: (enabled) => api.post('/ops/observability', { enabled: !!enabled }),
  getSelfHealth: () => api.get('/ops/self-health'),
  getKpiReadiness: (params = {}) => api.get('/ops/kpi/readiness', { params }),
  createKpiReadinessSnapshot: (params = {}) => api.post('/ops/kpi/readiness/snapshot', null, { params }),
  getKpiReadinessHistory: (params = {}) => api.get('/ops/kpi/readiness/history', { params }),
  getReleaseEvidence: (params = {}) => api.get('/ops/release-evidence', { params }),
  refreshReleaseEvidence: (params = {}) => api.post('/ops/release-evidence/refresh', null, { params }),
  downloadReleaseEvidenceBundle: (params = {}) => api.get('/ops/release-evidence/bundle', { params, responseType: 'blob' }),
  downloadProOperatorPackage: (params = {}) => api.get('/ops/pro/operator-package', { params, responseType: 'blob' }),
  downloadOperationsReviewBundle: (params = {}) => api.get('/ops/operations-review-bundle', { params, responseType: 'blob' }),
};

export const PreventiveCheckService = {
  getSummary: () => api.get('/ops/preventive-checks/summary'),
  listTemplates: () => api.get('/ops/preventive-checks/templates'),
  createTemplate: (payload = {}) => api.post('/ops/preventive-checks/templates', payload),
  updateTemplate: (id, payload = {}) => api.put(`/ops/preventive-checks/templates/${id}`, payload),
  deleteTemplate: (id) => api.delete(`/ops/preventive-checks/templates/${id}`),
  listRuns: (params = {}) => api.get('/ops/preventive-checks/runs', { params }),
  getRun: (id) => api.get(`/ops/preventive-checks/runs/${id}`),
  runTemplate: (id) => api.post(`/ops/preventive-checks/templates/${id}/run`),
  exportRun: (id, params = {}) => api.get(`/ops/preventive-checks/runs/${id}/export`, { params, responseType: 'blob' }),
};

export const ServiceGroupService = {
  list: () => api.get('/service-groups/'),
  get: (id) => api.get(`/service-groups/${id}`),
  create: (payload = {}) => api.post('/service-groups/', payload),
  update: (id, payload = {}) => api.put(`/service-groups/${id}`, payload),
  delete: (id) => api.delete(`/service-groups/${id}`),
  getCatalog: () => api.get('/service-groups/catalog'),
  addDevice: (groupId, deviceId) => api.post(`/service-groups/${groupId}/members/device/${deviceId}`),
  addCloudResource: (groupId, cloudResourceId) => api.post(`/service-groups/${groupId}/members/cloud/${cloudResourceId}`),
  removeMember: (groupId, memberId) => api.delete(`/service-groups/${groupId}/members/${memberId}`),
};

export const MonitoringProfileService = {
  list: () => api.get('/monitoring-profiles/'),
  getCatalog: () => api.get('/monitoring-profiles/catalog'),
  create: (payload = {}) => api.post('/monitoring-profiles/', payload),
  update: (id, payload = {}) => api.put(`/monitoring-profiles/${id}`, payload),
  delete: (id) => api.delete(`/monitoring-profiles/${id}`),
  getRecommendation: (deviceId) => api.get(`/monitoring-profiles/devices/${deviceId}/recommendation`),
  assignToDevice: (deviceId, profileId) =>
    api.post(`/monitoring-profiles/devices/${deviceId}/assign`, { profile_id: profileId }),
  recomputeForDevice: (deviceId) => api.post(`/monitoring-profiles/devices/${deviceId}/recompute`),
};

export const SourceOfTruthService = {
  getSummary: () => api.get('/automation-hub/source-of-truth/summary'),
};

export const StateHistoryService = {
  getCurrent: () => api.get('/automation-hub/state-history/current'),
  listSnapshots: (params = {}) => api.get('/automation-hub/state-history/snapshots', { params }),
  createSnapshot: (payload = {}) => api.post('/automation-hub/state-history/snapshots', payload),
  compareSnapshot: (snapshotId) => api.get(`/automation-hub/state-history/compare/${snapshotId}`),
};

export const IntentTemplateService = {
  getCatalog: () => api.get('/intent/templates/catalog'),
  getTemplate: (key) => api.get(`/intent/templates/${key}`),
};

export const IntentService = {
  getStatus: () => api.get('/intent/status'),
  validateIntent: (payload = {}) => api.post('/intent/validate', payload),
  simulateIntent: (payload = {}) => api.post('/intent/simulate', payload),
  applyIntent: (payload = {}) => api.post('/intent/apply', payload),
  getClosedLoopStatus: () => api.get('/intent/closed-loop/status'),
  getClosedLoopRules: () => api.get('/intent/closed-loop/rules'),
  saveClosedLoopRules: (rules = []) => api.put('/intent/closed-loop/rules', { rules }),
  getClosedLoopRulesLint: () => api.get('/intent/closed-loop/rules/lint'),
  lintClosedLoopRules: (rules = []) => api.post('/intent/closed-loop/rules/lint', { rules }),
};

// --------------------------------------------------------------------------
// 5. ZtpService (Zero Touch Provisioning)
// --------------------------------------------------------------------------
export const ZtpService = {
  // 대기열 조회
  getQueue: (status = null) => api.get('/ztp/queue', { params: status ? { status } : {} }),
  getStats: () => api.get('/ztp/stats'),

  // 장비 승인
  approveDevice: (itemId, payload) => api.post(`/ztp/queue/${itemId}/approve`, payload),

  // 미리 등록 (RMA)
  stageDevice: (payload) => api.post('/ztp/queue/stage', payload),

  // 삭제
  deleteItem: (itemId) => api.delete(`/ztp/queue/${itemId}`),

  // 재시도
  retryItem: (itemId) => api.post(`/ztp/queue/${itemId}/retry`),
};

// --------------------------------------------------------------------------
// 6. Firmware Image Service (SDN)
// --------------------------------------------------------------------------
export const ImageService = {
  getImages: () => api.get('/sdn/images'),
  uploadImage: (formData) => api.post('/sdn/images', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  deleteImage: (id) => api.delete(`/sdn/images/${id}`),
};

// --------------------------------------------------------------------------
// 7. Topology Service
// --------------------------------------------------------------------------
export const TopologyService = {
  getLayout: () => api.get('/topology/layout'),
  saveLayout: (layoutData) => api.post('/topology/layout', layoutData),
  resetLayout: () => api.delete('/topology/layout'),
  listSnapshots: (params = {}) => api.get('/topology/snapshots', { params }),
  createSnapshot: (payload) => api.post('/topology/snapshots', payload),
  getSnapshot: (id) => api.get(`/topology/snapshots/${id}`),
  diffSnapshots: (snapshotA, snapshotB) => api.get('/topology/diff', { params: { snapshot_a: snapshotA, snapshot_b: snapshotB } }),
  getCandidates: (params = {}) => api.get('/topology/candidates', { params }),
  getCandidateSummary: (params = {}) => api.get('/topology/candidates/summary', { params }),
  getCandidateSummaryTrend: (params = {}) => api.get('/topology/candidates/summary/trend', { params }),
  getCandidateRecommendations: (candidateId, params = {}) => api.get(`/topology/candidates/${candidateId}/recommendations`, { params }),
  promoteCandidate: (candidateId, payload) => api.post(`/topology/candidates/${candidateId}/promote`, payload),
  ignoreCandidate: (candidateId) => api.post(`/topology/candidates/${candidateId}/ignore`),
  bulkIgnoreCandidates: (candidateIds) => api.post('/topology/candidates/bulk-ignore', { candidate_ids: candidateIds }),
  bulkPromoteCandidates: (jobId, items) => api.post('/topology/candidates/bulk-promote', { job_id: jobId, items }),
  listEvents: (params = {}) => api.get('/topology/events', { params }),
};

// --------------------------------------------------------------------------
// 8. Approval Service (Change Management)
// --------------------------------------------------------------------------
export const ApprovalService = {
  create: (data) => api.post('/approval/', data),
  getRequests: (params) => api.get('/approval/', { params }),
  getRequest: (id) => api.get(`/approval/${id}`),
  getServiceImpact: (id) => api.get(`/approval/${id}/service-impact`),
  approve: (id, comment) => api.post(`/approval/${id}/approve`, { approver_comment: comment }),
  reject: (id, comment) => api.post(`/approval/${id}/reject`, { approver_comment: comment }),
  downloadEvidencePackage: (id) => api.get(`/approval/${id}/evidence-package`, { responseType: 'blob' }),
};

export default api;
