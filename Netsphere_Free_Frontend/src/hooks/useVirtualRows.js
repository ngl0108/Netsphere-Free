import { useCallback, useEffect, useMemo, useState } from 'react';

export default function useVirtualRows(items, options = {}) {
  const {
    containerRef,
    rowHeight = 56,
    overscan = 10,
    enabled = true,
  } = options;

  const safeRowHeight = Math.max(24, Number(rowHeight || 56));
  const safeOverscan = Math.max(1, Number(overscan || 10));
  const totalCount = Array.isArray(items) ? items.length : 0;

  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);

  const onScroll = useCallback((event) => {
    if (!enabled) return;
    const el = event?.currentTarget;
    if (!el) return;
    setScrollTop(el.scrollTop || 0);
    setViewportHeight(el.clientHeight || 0);
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    const el = containerRef?.current;
    if (!el) return;

    const update = () => {
      setViewportHeight(el.clientHeight || 0);
      setScrollTop(el.scrollTop || 0);
    };
    update();

    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(update);
      ro.observe(el);
      return () => ro.disconnect();
    }

    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [containerRef, enabled]);

  useEffect(() => {
    setScrollTop(0);
  }, [totalCount]);

  const range = useMemo(() => {
    if (!enabled || totalCount === 0) {
      return { start: 0, end: totalCount };
    }

    const safeViewport = Math.max(safeRowHeight * 6, Number(viewportHeight || 0));
    const visibleCount = Math.ceil(safeViewport / safeRowHeight);
    const rawStart = Math.floor(Number(scrollTop || 0) / safeRowHeight) - safeOverscan;
    const start = Math.max(0, rawStart);
    const end = Math.min(totalCount, start + visibleCount + safeOverscan * 2);
    return { start, end };
  }, [enabled, safeOverscan, safeRowHeight, scrollTop, totalCount, viewportHeight]);

  const visibleItems = useMemo(() => {
    if (!Array.isArray(items) || items.length === 0) return [];
    return items.slice(range.start, range.end);
  }, [items, range.end, range.start]);

  const paddingTop = enabled ? range.start * safeRowHeight : 0;
  const paddingBottom = enabled ? Math.max(0, (totalCount - range.end) * safeRowHeight) : 0;

  return {
    visibleItems,
    totalCount,
    startIndex: range.start,
    endIndex: range.end,
    paddingTop,
    paddingBottom,
    onScroll,
  };
}

