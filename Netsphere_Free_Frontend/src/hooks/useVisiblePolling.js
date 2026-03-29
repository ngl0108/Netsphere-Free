import { useEffect, useRef } from 'react';

export default function useVisiblePolling(task, intervalMs, options = {}) {
  const {
    enabled = true,
    immediate = true,
    runOnVisible = true,
    allowHidden = false,
    minGapMs,
    pauseWhenOffline = true,
    backoffOnError = true,
    backoffMultiplier = 2,
    backoffMaxIntervalMs,
    backoffResetOnSuccess = true,
  } = options;
  const taskRef = useRef(task);

  useEffect(() => {
    taskRef.current = task;
  }, [task]);

  useEffect(() => {
    if (!enabled) return undefined;

    let isRunning = false;
    const safeInterval = Math.max(1000, Number(intervalMs || 10000));
    const safeMinGap = Number.isFinite(Number(minGapMs))
      ? Math.max(0, Number(minGapMs))
      : Math.min(1500, Math.floor(safeInterval / 2));
    const safeBackoffMultiplier = Math.max(1, Number(backoffMultiplier || 2));
    const safeBackoffMaxInterval = Number.isFinite(Number(backoffMaxIntervalMs))
      ? Math.max(safeInterval, Number(backoffMaxIntervalMs))
      : safeInterval * 4;
    let lastStartedAt = 0;
    let consecutiveFailures = 0;
    let nextAllowedAt = 0;

    const calcBackoffDelay = (failureCount) => {
      const step = Math.max(0, Number(failureCount) - 1);
      const delay = Math.round(safeInterval * Math.pow(safeBackoffMultiplier, step));
      return Math.max(safeInterval, Math.min(safeBackoffMaxInterval, delay));
    };

    const runTask = async (force = false) => {
      if (pauseWhenOffline && typeof navigator !== 'undefined' && navigator.onLine === false) return;
      const now = Date.now();
      if (!force && now < nextAllowedAt) return;
      if (isRunning) return;
      if (safeMinGap > 0 && now - lastStartedAt < safeMinGap) return;
      isRunning = true;
      lastStartedAt = now;
      try {
        const fn = taskRef.current;
        if (typeof fn === 'function') {
          await fn();
        }
        if (backoffResetOnSuccess) {
          consecutiveFailures = 0;
          nextAllowedAt = 0;
        }
      } catch (e) {
        if (backoffOnError) {
          consecutiveFailures += 1;
          nextAllowedAt = Date.now() + calcBackoffDelay(consecutiveFailures);
        }
      } finally {
        isRunning = false;
      }
    };

    const tick = () => {
      if (!allowHidden && document.visibilityState !== 'visible') return;
      void runTask();
    };

    if (immediate && (allowHidden || document.visibilityState === 'visible')) {
      void runTask();
    }

    const timer = window.setInterval(tick, safeInterval);
    const onVisibilityChange = () => {
      if (runOnVisible && document.visibilityState === 'visible') {
        void runTask(true);
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [
    enabled,
    intervalMs,
    immediate,
    runOnVisible,
    allowHidden,
    minGapMs,
    pauseWhenOffline,
    backoffOnError,
    backoffMultiplier,
    backoffMaxIntervalMs,
    backoffResetOnSuccess,
  ]);
}
