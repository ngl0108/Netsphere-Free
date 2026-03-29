import React, { createContext, useContext, useEffect, useState } from 'react';
import { AuthService, SettingsService } from '../api/services';
import useVisiblePolling from '../hooks/useVisiblePolling';

const AuthContext = createContext(null);

const ROLE_HIERARCHY = {
  admin: 0,
  operator: 1,
  viewer: 2,
};
const AUTH_LAST_ACTIVE_KEY = 'authLastActiveAt';
const AUTH_GENERAL_SETTINGS_CACHE_KEY = 'authGeneralSettingsCache';
const AUTH_GENERAL_SETTINGS_CACHE_TTL_MS = 5 * 60 * 1000;

const readCachedGeneralSettings = () => {
  try {
    const raw = sessionStorage.getItem(AUTH_GENERAL_SETTINGS_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const expiresAt = Number(parsed?.expiresAt || 0);
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
      sessionStorage.removeItem(AUTH_GENERAL_SETTINGS_CACHE_KEY);
      return null;
    }
    return parsed?.data && typeof parsed.data === 'object' ? parsed.data : null;
  } catch (e) {
    sessionStorage.removeItem(AUTH_GENERAL_SETTINGS_CACHE_KEY);
    return null;
  }
};

const writeCachedGeneralSettings = (data) => {
  try {
    sessionStorage.setItem(
      AUTH_GENERAL_SETTINGS_CACHE_KEY,
      JSON.stringify({
        expiresAt: Date.now() + AUTH_GENERAL_SETTINGS_CACHE_TTL_MS,
        data: data && typeof data === 'object' ? data : {},
      }),
    );
  } catch (e) {
    void e;
  }
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [idleMinutes, setIdleMinutes] = useState(30);

  const login = async (username, password) => {
    const res = await AuthService.login(username, password);
    const raw = res?.data || {};
    if (raw?.mfa_required) {
      return { mfaRequired: true, challengeId: raw.challenge_id, delivery: raw.delivery };
    }

    const token =
      res?.data?.access_token ||
      res?.data?.token ||
      res?.data?.data?.access_token ||
      res?.data?.data?.token;

    if (!token) return { success: false };

    localStorage.setItem('authToken', token);
    localStorage.setItem(AUTH_LAST_ACTIVE_KEY, String(Date.now()));

    try {
      const meRes = await AuthService.me();
      const userData = meRes?.data?.data || meRes?.data;
      setUser(userData);
      localStorage.setItem('authUser', JSON.stringify(userData));
    } catch (e) {
      const fallbackUser = { username, role: 'viewer' };
      setUser(fallbackUser);
      localStorage.setItem('authUser', JSON.stringify(fallbackUser));
    }

    return { success: true };
  };

  const verifyOtp = async (challengeId, otp) => {
    const res = await AuthService.verifyOtp(challengeId, otp);
    const token =
      res?.data?.access_token ||
      res?.data?.token ||
      res?.data?.data?.access_token ||
      res?.data?.data?.token;

    if (!token) return { success: false };

    localStorage.setItem('authToken', token);
    localStorage.setItem(AUTH_LAST_ACTIVE_KEY, String(Date.now()));

    try {
      const meRes = await AuthService.me();
      const userData = meRes?.data?.data || meRes?.data;
      setUser(userData);
      localStorage.setItem('authUser', JSON.stringify(userData));
    } catch (e) {
      const fallbackUser = { username: 'unknown', role: 'viewer' };
      setUser(fallbackUser);
      localStorage.setItem('authUser', JSON.stringify(fallbackUser));
    }

    return { success: true };
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('authToken');
    localStorage.removeItem('authUser');
    localStorage.removeItem(AUTH_LAST_ACTIVE_KEY);
  };

  const refreshUser = async () => {
    const res = await AuthService.me();
    const userData = res?.data?.data || res?.data;
    setUser(userData);
    localStorage.setItem('authUser', JSON.stringify(userData));
    localStorage.setItem(AUTH_LAST_ACTIVE_KEY, String(Date.now()));
    return userData;
  };

  useEffect(() => {
    const loadUser = async () => {
      const token = localStorage.getItem('authToken');
      if (!token) {
        setLoading(false);
        return;
      }

      const storedUser = localStorage.getItem('authUser');
      if (storedUser) {
        try {
          const parsed = JSON.parse(storedUser);
          // Legacy cache can miss newer fields; do not force logout before live /auth/me check.
          if (parsed && typeof parsed === 'object' && parsed.eula_accepted !== undefined) {
            setUser(parsed);
          } else {
            localStorage.removeItem('authUser');
          }
        } catch (e) {
          localStorage.removeItem('authUser');
        }
      }

      try {
        await refreshUser();
      } catch (e) {
        console.error('Session expired or invalid:', e);
      } finally {
        setLoading(false);
      }
    };

    loadUser();
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('authToken');
    if (!token) return undefined;

    const cached = readCachedGeneralSettings();
    const cachedTimeout = Number(cached?.session_timeout);
    if (Number.isFinite(cachedTimeout) && cachedTimeout > 0) {
      setIdleMinutes(cachedTimeout);
      return undefined;
    }

    let cancelled = false;
    (async () => {
      try {
        const res = await SettingsService.getGeneral();
        const incoming = res?.data || {};
        writeCachedGeneralSettings(incoming);
        const v = Number(incoming.session_timeout);
        if (!cancelled && Number.isFinite(v) && v > 0) {
          setIdleMinutes(v);
        }
      } catch (e) {
        void e;
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('authToken');
    if (!token) return undefined;

    let lastActive = Number(localStorage.getItem(AUTH_LAST_ACTIVE_KEY) || Date.now());
    if (!Number.isFinite(lastActive) || lastActive <= 0) {
      lastActive = Date.now();
      localStorage.setItem(AUTH_LAST_ACTIVE_KEY, String(lastActive));
    }

    const touch = () => {
      lastActive = Date.now();
      localStorage.setItem(AUTH_LAST_ACTIVE_KEY, String(lastActive));
    };

    const events = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart'];
    for (const ev of events) {
      window.addEventListener(ev, touch, { passive: true });
    }

    return () => {
      for (const ev of events) {
        window.removeEventListener(ev, touch);
      }
    };
  }, [user?.id]);

  useVisiblePolling(() => {
    const token = localStorage.getItem('authToken');
    if (!token) return;
    const t = Number(localStorage.getItem(AUTH_LAST_ACTIVE_KEY) || Date.now());
    const effective = Number.isFinite(t) && t > 0 ? t : Date.now();
    const timeoutMs = Math.max(1, Number(idleMinutes || 30)) * 60 * 1000;
    if (Date.now() - effective >= timeoutMs) {
      logout();
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
  }, 30000, {
    enabled: !!(user || localStorage.getItem('authToken')),
    immediate: false,
    runOnVisible: false,
    allowHidden: true,
    pauseWhenOffline: false,
    minGapMs: 15000,
    backoffOnError: false,
  });

  useVisiblePolling(async () => {
    const token = localStorage.getItem('authToken');
    if (!token) return;
    try {
      const res = await AuthService.refresh();
      const nextToken =
        res?.data?.access_token ||
        res?.data?.token ||
        res?.data?.data?.access_token ||
        res?.data?.data?.token;
      if (nextToken) {
        localStorage.setItem('authToken', String(nextToken));
        localStorage.setItem(AUTH_LAST_ACTIVE_KEY, String(Date.now()));
      }
    } catch (e) {
      void e;
    }
  }, 4 * 60 * 1000, {
    enabled: !!(user || localStorage.getItem('authToken')),
    immediate: false,
    runOnVisible: true,
    minGapMs: 120000,
    backoffOnError: false,
  });

  const isAtLeast = (minRole) => {
    if (!user || !user.role) return false;
    const userLevel = ROLE_HIERARCHY[user.role] ?? 999;
    const requiredLevel = ROLE_HIERARCHY[minRole] ?? 999;
    return userLevel <= requiredLevel;
  };

  const value = {
    user,
    loading,
    login,
    verifyOtp,
    logout,
    refreshUser,
    isAtLeast,
    isAdmin: () => isAtLeast('admin'),
    isOperator: () => isAtLeast('operator'),
    isViewer: () => isAtLeast('viewer'),
  };

  return <AuthContext.Provider value={value}>{!loading && children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
