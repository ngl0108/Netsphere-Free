import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { IssueService } from '../api/services';
import useVisiblePolling from '../hooks/useVisiblePolling';

const IssuePollingContext = createContext(null);

const normalizeAlerts = (value) => (Array.isArray(value) ? value : []);
const ISSUE_POLLING_CACHE_KEY = 'issuePollingCache';
const ISSUE_POLLING_CACHE_TTL_MS = 15 * 1000;

const readIssuePollingCache = () => {
  try {
    const raw = sessionStorage.getItem(ISSUE_POLLING_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const expiresAt = Number(parsed?.expiresAt || 0);
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
      sessionStorage.removeItem(ISSUE_POLLING_CACHE_KEY);
      return null;
    }
    return {
      alerts: normalizeAlerts(parsed?.alerts),
      unreadCount: Number(parsed?.unreadCount || 0),
      hasAlertSnapshot: parsed?.hasAlertSnapshot === true,
    };
  } catch (error) {
    sessionStorage.removeItem(ISSUE_POLLING_CACHE_KEY);
    return null;
  }
};

const writeIssuePollingCache = (alerts, unreadCount, hasAlertSnapshot = false) => {
  try {
    sessionStorage.setItem(
      ISSUE_POLLING_CACHE_KEY,
      JSON.stringify({
        expiresAt: Date.now() + ISSUE_POLLING_CACHE_TTL_MS,
        alerts: normalizeAlerts(alerts),
        unreadCount: Number(unreadCount || 0),
        hasAlertSnapshot: hasAlertSnapshot === true,
      }),
    );
  } catch (error) {
    void error;
  }
};

const clearIssuePollingCache = () => {
  try {
    sessionStorage.removeItem(ISSUE_POLLING_CACHE_KEY);
  } catch (error) {
    void error;
  }
};

export const IssuePollingProvider = ({ children }) => {
  const [initialCache] = useState(() => readIssuePollingCache());
  const [alerts, setAlerts] = useState(() => normalizeAlerts(initialCache?.alerts));
  const [unreadCount, setUnreadCount] = useState(() => Number(initialCache?.unreadCount || 0));
  const [alertsLoaded, setAlertsLoaded] = useState(() => initialCache?.hasAlertSnapshot === true);
  const [loading, setLoading] = useState(false);
  const alertsRef = useRef(normalizeAlerts(initialCache?.alerts));
  const unreadCountRef = useRef(Number(initialCache?.unreadCount || 0));
  const alertsLoadedRef = useRef(initialCache?.hasAlertSnapshot === true);
  const countInFlightRef = useRef(null);
  const alertsInFlightRef = useRef(null);

  useEffect(() => {
    alertsRef.current = alerts;
  }, [alerts]);

  useEffect(() => {
    unreadCountRef.current = Number(unreadCount || 0);
  }, [unreadCount]);

  useEffect(() => {
    alertsLoadedRef.current = alertsLoaded === true;
  }, [alertsLoaded]);

  const fetchUnreadCount = useCallback(() => {
    if (countInFlightRef.current) return countInFlightRef.current;
    const request = IssueService.getUnreadCount().finally(() => {
      countInFlightRef.current = null;
    });
    countInFlightRef.current = request;
    return request;
  }, []);

  const fetchAlerts = useCallback(() => {
    if (alertsInFlightRef.current) return alertsInFlightRef.current;
    const request = IssueService.getActiveIssues().finally(() => {
      alertsInFlightRef.current = null;
    });
    alertsInFlightRef.current = request;
    return request;
  }, []);

  const refresh = useCallback(async ({ silent = true, includeAlerts = false } = {}) => {
    const token = localStorage.getItem('authToken');
    if (!token) {
      setAlerts([]);
      setUnreadCount(0);
      setAlertsLoaded(false);
      setLoading(false);
      clearIssuePollingCache();
      return;
    }

    if (!silent) setLoading(true);

    try {
      const requests = [fetchUnreadCount()];
      if (includeAlerts) {
        requests.push(fetchAlerts());
      }
      const [countResult, alertsResult] = await Promise.allSettled(requests);

      let nextUnreadCount = unreadCountRef.current;
      if (countResult?.status === 'fulfilled') {
        nextUnreadCount = Number(countResult.value?.data?.unread_count || 0);
        setUnreadCount(nextUnreadCount);
      }

      let nextAlerts = alertsRef.current;
      let nextAlertsLoaded = alertsLoadedRef.current;
      if (includeAlerts && alertsResult?.status === 'fulfilled') {
        nextAlerts = normalizeAlerts(alertsResult.value?.data);
        setAlerts(nextAlerts);
        nextAlertsLoaded = true;
        setAlertsLoaded(true);
      }

      if (countResult?.status === 'fulfilled' || alertsResult?.status === 'fulfilled') {
        writeIssuePollingCache(nextAlerts, nextUnreadCount, nextAlertsLoaded);
      }
    } catch (_error) {
      // Keep previous UI state when transient poll failures happen.
    } finally {
      if (!silent) setLoading(false);
    }
  }, [fetchAlerts, fetchUnreadCount]);

  const loadAlerts = useCallback(
    async ({ silent = true } = {}) => refresh({ silent, includeAlerts: true }),
    [refresh],
  );

  useVisiblePolling(() => refresh({ silent: true }), 10000, {
    enabled: true,
    immediate: !initialCache,
    runOnVisible: true,
    minGapMs: 5000,
    backoffOnError: false,
    backoffMultiplier: 3,
    backoffMaxIntervalMs: 120000,
  });

  const markAsRead = useCallback(async (id) => {
    await IssueService.markAsRead(id);
    setAlerts((prev) => {
      const next = prev.map((item) => (item.id === id ? { ...item, is_read: true } : item));
      writeIssuePollingCache(next, Math.max(0, Number(unreadCountRef.current || 0) - 1), alertsLoadedRef.current);
      return next;
    });
    setUnreadCount((prev) => Math.max(0, Number(prev || 0) - 1));
    void refresh({ silent: true, includeAlerts: alertsLoadedRef.current });
  }, [refresh]);

  const markAllAsRead = useCallback(async () => {
    await IssueService.markAllAsRead();
    setAlerts((prev) => {
      const next = prev.map((item) => ({ ...item, is_read: true }));
      writeIssuePollingCache(next, 0, alertsLoadedRef.current);
      return next;
    });
    setUnreadCount(0);
    void refresh({ silent: true, includeAlerts: alertsLoadedRef.current });
  }, [refresh]);

  const resolveIssue = useCallback(async (id) => {
    await IssueService.resolveIssue(id);
    setAlerts((prev) => {
      const next = prev.filter((item) => item.id !== id);
      writeIssuePollingCache(next, unreadCountRef.current, alertsLoadedRef.current);
      return next;
    });
    void refresh({ silent: true, includeAlerts: alertsLoadedRef.current });
  }, [refresh]);

  const resolveAll = useCallback(async () => {
    await IssueService.resolveAll();
    setAlerts([]);
    setUnreadCount(0);
    setAlertsLoaded(true);
    writeIssuePollingCache([], 0, true);
    void refresh({ silent: true, includeAlerts: true });
  }, [refresh]);

  const recentAlerts = useMemo(
    () => alerts.filter((item) => !item?.is_read).slice(0, 5),
    [alerts],
  );

  const value = useMemo(() => ({
    alerts,
    unreadCount,
    alertsLoaded,
    recentAlerts,
    loading,
    refresh,
    loadAlerts,
    markAsRead,
    markAllAsRead,
    resolveIssue,
    resolveAll,
  }), [alerts, unreadCount, alertsLoaded, recentAlerts, loading, refresh, loadAlerts, markAsRead, markAllAsRead, resolveIssue, resolveAll]);

  return (
    <IssuePollingContext.Provider value={value}>
      {children}
    </IssuePollingContext.Provider>
  );
};

export const useIssuePolling = () => {
  const context = useContext(IssuePollingContext);
  if (!context) {
    throw new Error('useIssuePolling must be used within an IssuePollingProvider');
  }
  return context;
};
