'use client';

/**
 * [INPUT]
 * - ResizeObserver API
 * - adaptiveGridTypes: TerminalPtyDimensions, TerminalFontMetrics, UseTerminalPtyOptions
 *
 * [OUTPUT]
 * - useTerminalPtyAutoResize: React hook auto-calculating cols/rows and negotiating PTY dimensions
 *
 * [POS]
 * Terminal PTY dimension negotiator adapting monospaced character columns and rows dynamically.
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  TerminalPtyDimensions,
  TerminalFontMetrics,
  UseTerminalPtyOptions,
} from './adaptiveGridTypes';

const DEFAULT_FONT_METRICS: TerminalFontMetrics = {
  charWidth: 9,
  charHeight: 18,
};

export function calculatePtyMatrix(
  width: number,
  height: number,
  fontMetrics: TerminalFontMetrics = DEFAULT_FONT_METRICS,
  minCols = 40,
  minRows = 10,
): TerminalPtyDimensions {
  const safeWidth = Math.max(0, width);
  const safeHeight = Math.max(0, height);

  const charW = Math.max(1, fontMetrics.charWidth);
  const charH = Math.max(1, fontMetrics.charHeight);

  const rawCols = Math.floor(safeWidth / charW);
  const rawRows = Math.floor(safeHeight / charH);

  const cols = Math.max(minCols, rawCols);
  const rows = Math.max(minRows, rawRows);

  return {
    cols,
    rows,
    containerWidth: safeWidth,
    containerHeight: safeHeight,
  };
}

export function useTerminalPtyAutoResize(options: UseTerminalPtyOptions = {}) {
  const {
    fontMetrics: customFontMetrics,
    minCols = 40,
    minRows = 10,
    debounceMs = 50,
    onResizePty,
  } = options;

  const fontMetrics = useMemo<TerminalFontMetrics>(
    () => ({
      charWidth: customFontMetrics?.charWidth ?? DEFAULT_FONT_METRICS.charWidth,
      charHeight: customFontMetrics?.charHeight ?? DEFAULT_FONT_METRICS.charHeight,
    }),
    [customFontMetrics?.charWidth, customFontMetrics?.charHeight],
  );

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [dimensions, setDimensions] = useState<TerminalPtyDimensions>({
    cols: 80,
    rows: 24,
    containerWidth: 720,
    containerHeight: 432,
  });

  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const onResizePtyRef = useRef(onResizePty);

  useEffect(() => {
    onResizePtyRef.current = onResizePty;
  }, [onResizePty]);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  const updateDimensions = useCallback(
    (w: number, h: number) => {
      const calculated = calculatePtyMatrix(w, h, fontMetrics, minCols, minRows);
      setDimensions(calculated);

      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }

      timerRef.current = setTimeout(() => {
        if (onResizePtyRef.current) {
          onResizePtyRef.current(calculated);
        }
      }, debounceMs);
    },
    [fontMetrics, minCols, minRows, debounceMs],
  );

  const recalculate = useCallback(() => {
    if (!containerRef.current) {
      return;
    }
    const rect = containerRef.current.getBoundingClientRect();
    updateDimensions(rect.width, rect.height);
  }, [updateDimensions]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return;
    }

    if (typeof ResizeObserver === 'undefined') {
      const rect = element.getBoundingClientRect();
      updateDimensions(rect.width, rect.height);
      return;
    }

    const observer = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0) {
        return;
      }
      const entry = entries[0];
      const width = entry.contentRect.width;
      const height = entry.contentRect.height;
      updateDimensions(width, height);
    });

    observer.observe(element);

    return () => {
      observer.disconnect();
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [updateDimensions]);

  return {
    ref: containerRef,
    dimensions,
    recalculate,
  };
}
