import { useCallback, useEffect, useMemo, useState } from 'react';

export default function useProgressiveList(items, options = {}) {
  const {
    initialCount = 120,
    step = 80,
    thresholdPx = 240,
    resetKey = '',
  } = options;

  const safeInitial = Math.max(1, Number(initialCount || 120));
  const safeStep = Math.max(1, Number(step || 80));
  const safeThreshold = Math.max(32, Number(thresholdPx || 240));
  const size = Array.isArray(items) ? items.length : 0;

  const [visibleCount, setVisibleCount] = useState(safeInitial);

  useEffect(() => {
    setVisibleCount(Math.min(safeInitial, size || safeInitial));
  }, [resetKey, safeInitial, size]);

  useEffect(() => {
    setVisibleCount((prev) => {
      const clamped = Math.max(safeInitial, Number(prev || safeInitial));
      return Math.min(clamped, size || clamped);
    });
  }, [size, safeInitial]);

  const onScrollLoadMore = useCallback(
    (event) => {
      if (visibleCount >= size) return;
      const el = event?.currentTarget;
      if (!el) return;
      const nearBottom = (el.scrollTop + el.clientHeight) >= (el.scrollHeight - safeThreshold);
      if (!nearBottom) return;
      setVisibleCount((prev) => Math.min(size, Number(prev || 0) + safeStep));
    },
    [safeStep, safeThreshold, size, visibleCount],
  );

  const visibleItems = useMemo(() => {
    if (!Array.isArray(items) || items.length === 0) return [];
    return items.slice(0, Math.min(visibleCount, items.length));
  }, [items, visibleCount]);

  return {
    visibleItems,
    visibleCount: Math.min(visibleCount, size),
    totalCount: size,
    hasMore: visibleCount < size,
    onScrollLoadMore,
  };
}

