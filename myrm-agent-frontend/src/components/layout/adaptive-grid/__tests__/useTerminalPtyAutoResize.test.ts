/** @vitest-environment jsdom */
import React from 'react';
import { render, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  calculatePtyMatrix,
  useTerminalPtyAutoResize,
} from '../useTerminalPtyAutoResize';

describe('useTerminalPtyAutoResize & calculatePtyMatrix', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('calculates standard 80x24 terminal cols and rows based on container pixels', () => {
    // 720px width / 9px per char = 80 cols
    // 432px height / 18px per line = 24 rows
    const matrix = calculatePtyMatrix(720, 432, { charWidth: 9, charHeight: 18 });

    expect(matrix.cols).toBe(80);
    expect(matrix.rows).toBe(24);
    expect(matrix.containerWidth).toBe(720);
    expect(matrix.containerHeight).toBe(432);
  });

  it('respects minCols and minRows safeguards for narrow/squished containers', () => {
    // Very narrow container (100px x 60px)
    const matrix = calculatePtyMatrix(100, 60, { charWidth: 9, charHeight: 18 }, 40, 10);

    expect(matrix.cols).toBe(40);
    expect(matrix.rows).toBe(10);
  });

  it('adapts properly to custom font metrics', () => {
    // Custom font with charWidth 10 and charHeight 20
    // 1000px / 10 = 100 cols, 600px / 20 = 30 rows
    const matrix = calculatePtyMatrix(1000, 600, { charWidth: 10, charHeight: 20 });

    expect(matrix.cols).toBe(100);
    expect(matrix.rows).toBe(30);
  });

  it('debounces onResizePty negotiation callback on viewport changes', () => {
    const onResizePtyMock = vi.fn();

    type ResizeObserverCallback = (entries: Array<{ contentRect: { width: number; height: number } }>) => void;
    let observerCb: ResizeObserverCallback | null = null;

    class MockResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        observerCb = callback;
      }
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
    }

    vi.stubGlobal('ResizeObserver', MockResizeObserver);

    const TerminalTester: React.FC = () => {
      const { ref } = useTerminalPtyAutoResize({
        debounceMs: 50,
        onResizePty: onResizePtyMock,
      });
      return React.createElement('div', { ref, 'data-testid': 'pty-box' });
    };

    render(React.createElement(TerminalTester));

    // Trigger ResizeObserver entry
    act(() => {
      if (observerCb) {
        observerCb([{ contentRect: { width: 900, height: 450 } }]);
      }
    });

    // Before debounce timer fires
    expect(onResizePtyMock).not.toHaveBeenCalled();

    // Fast-forward debounce time
    act(() => {
      vi.advanceTimersByTime(55);
    });

    expect(onResizePtyMock).toHaveBeenCalledTimes(1);
    expect(onResizePtyMock).toHaveBeenCalledWith(
      expect.objectContaining({
        cols: 100, // 900 / 9 = 100
        rows: 25,  // 450 / 18 = 25
      }),
    );

    vi.unstubAllGlobals();
  });
});
