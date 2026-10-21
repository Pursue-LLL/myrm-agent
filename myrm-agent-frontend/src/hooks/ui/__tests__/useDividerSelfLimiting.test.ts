import { renderHook, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  useDividerSelfLimiting,
  MAX_MEASURE_ITERATIONS,
  SIGNIFICANT_EXPAND_THRESHOLD_PX,
} from '../useDividerSelfLimiting';

describe('useDividerSelfLimiting', () => {
  it('bounds candidate dimension within min and max constraints', () => {
    const { result } = renderHook(() =>
      useDividerSelfLimiting(280, {
        minDimension: 200,
        maxDimension: 400,
      }),
    );

    act(() => {
      const res = result.current.negotiate(150); // Below min
      expect(res.dimension).toBe(200);
      expect(res.locked).toBe(false);
    });

    act(() => {
      const res = result.current.negotiate(500); // Above max
      expect(res.dimension).toBe(400);
      expect(res.locked).toBe(false);
    });
  });

  it('marks converged when dimension variation is within sub-pixel epsilon', () => {
    const { result } = renderHook(() =>
      useDividerSelfLimiting(280, {
        minDimension: 200,
        maxDimension: 400,
      }),
    );

    act(() => {
      result.current.negotiate(320);
    });

    let res: ReturnType<typeof result.current.negotiate> | undefined;
    act(() => {
      res = result.current.negotiate(320.5); // <= 1px delta
    });
    expect(res?.converged).toBe(true);
    expect(res?.dimension).toBe(320.5);
    expect(res?.iteration).toBe(0);
    expect(result.current.iterationCount).toBe(0);
  });

  it('engages iteration lock after exceeding MAX_MEASURE_ITERATIONS to prevent layout loops', () => {
    const onLockEngaged = vi.fn();
    const { result } = renderHook(() =>
      useDividerSelfLimiting(280, {
        minDimension: 200,
        maxDimension: 400,
        maxIterations: 3,
        onLockEngaged,
      }),
    );

    // Iteration 1
    act(() => {
      result.current.negotiate(250);
    });
    expect(result.current.isLocked).toBe(false);

    // Iteration 2 (oscillating)
    act(() => {
      result.current.negotiate(350);
    });
    expect(result.current.isLocked).toBe(false);

    // Iteration 3 (reaches threshold)
    act(() => {
      const res = result.current.negotiate(260);
      expect(res.locked).toBe(true);
    });

    expect(result.current.isLocked).toBe(true);
    expect(onLockEngaged).toHaveBeenCalledWith(260, MAX_MEASURE_ITERATIONS);

    // Subsequent call should stay locked at safe clamped dimension
    act(() => {
      const res = result.current.negotiate(380);
      expect(res.locked).toBe(true);
      expect(res.dimension).toBe(260); // Locked at last clamped
    });
  });

  it('resets lock and iteration counter when viewport grows significantly', () => {
    const { result } = renderHook(() =>
      useDividerSelfLimiting(280, {
        minDimension: 200,
        maxDimension: 400,
        maxIterations: 2,
      }),
    );

    // Force lock
    act(() => {
      result.current.negotiate(250);
    });
    act(() => {
      result.current.negotiate(350);
    });
    expect(result.current.isLocked).toBe(true);

    // Minor resize does not unlock
    act(() => {
      result.current.notifyViewportResize(800);
      result.current.notifyViewportResize(805);
    });
    expect(result.current.isLocked).toBe(true);

    // Significant resize (> 16px expand) unlocks negotiation
    act(() => {
      result.current.notifyViewportResize(805 + SIGNIFICANT_EXPAND_THRESHOLD_PX + 5);
    });
    expect(result.current.isLocked).toBe(false);

    // Now negotiation can proceed normally
    act(() => {
      const res = result.current.negotiate(310);
      expect(res.locked).toBe(false);
      expect(res.dimension).toBe(310);
    });
  });

  it('supports explicit resetNegotiation with optional forced dimension', () => {
    const { result } = renderHook(() =>
      useDividerSelfLimiting(280, {
        minDimension: 200,
        maxDimension: 400,
        maxIterations: 2,
      }),
    );

    // Force lock
    act(() => {
      result.current.negotiate(220);
      result.current.negotiate(380);
    });
    expect(result.current.isLocked).toBe(true);

    act(() => {
      result.current.resetNegotiation(280);
    });
    expect(result.current.isLocked).toBe(false);
    expect(result.current.currentDimension).toBe(280);
  });
});
