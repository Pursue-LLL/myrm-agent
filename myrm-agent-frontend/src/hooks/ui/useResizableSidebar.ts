'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'myrm-sidebar-width';
const DEFAULT_WIDTH = 280;
const MIN_WIDTH = 220;
const MAX_WIDTH = 450;
const COLLAPSE_THRESHOLD = 180;

interface UseResizableSidebarOptions {
  onCollapse?: () => void;
}

interface UseResizableSidebarReturn {
  width: number;
  isDragging: boolean;
  handleMouseDown: (e: React.MouseEvent) => void;
  handleDoubleClick: () => void;
}

export function useResizableSidebar(options?: UseResizableSidebarOptions): UseResizableSidebarReturn {
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [isDragging, setIsDragging] = useState(false);
  const rafRef = useRef<number | null>(null);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);
  const onCollapseRef = useRef(options?.onCollapse);
  onCollapseRef.current = options?.onCollapse;

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = Number(stored);
      if (parsed >= MIN_WIDTH && parsed <= MAX_WIDTH) {
        setWidth(parsed);
      }
    }
  }, []);

  const persistWidth = useCallback((w: number) => {
    localStorage.setItem(STORAGE_KEY, String(w));
  }, []);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();

      startXRef.current = e.clientX;
      startWidthRef.current = width;
      setIsDragging(true);

      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';
    },
    [width],
  );

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }

      rafRef.current = requestAnimationFrame(() => {
        const delta = e.clientX - startXRef.current;
        const rawWidth = startWidthRef.current + delta;
        const clampedWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, rawWidth));
        setWidth(clampedWidth);
      });
    };

    const handleMouseUp = (e: MouseEvent) => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }

      setIsDragging(false);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';

      const delta = e.clientX - startXRef.current;
      const rawWidth = startWidthRef.current + delta;

      if (rawWidth < COLLAPSE_THRESHOLD) {
        onCollapseRef.current?.();
        setWidth(startWidthRef.current);
      } else {
        const finalWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, rawWidth));
        setWidth(finalWidth);
        persistWidth(finalWidth);
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, [isDragging, persistWidth]);

  const handleDoubleClick = useCallback(() => {
    setWidth(DEFAULT_WIDTH);
    persistWidth(DEFAULT_WIDTH);
  }, [persistWidth]);

  return { width, isDragging, handleMouseDown, handleDoubleClick };
}
