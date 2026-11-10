import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useMessageHeights } from '../useMessageHeights';

describe('useMessageHeights', () => {
  it('starts empty and reads back what was set', () => {
    const { result } = renderHook(() => useMessageHeights());
    expect(result.current.getHeight('m1')).toBeUndefined();

    act(() => result.current.setHeight('m1', 120));
    expect(result.current.getHeight('m1')).toBe(120);
    expect(result.current.heightCache.get('m1')).toBe(120);
  });

  it('keeps the latest height when a message is measured again', () => {
    const { result } = renderHook(() => useMessageHeights());

    act(() => result.current.setHeight('m1', 120));
    act(() => result.current.setHeight('m1', 120));
    act(() => result.current.setHeight('m1', 180));
    expect(result.current.getHeight('m1')).toBe(180);
  });

  it('clears every height at once', () => {
    const { result } = renderHook(() => useMessageHeights());
    act(() => {
      result.current.setHeight('m1', 120);
      result.current.setHeight('m2', 90);
    });

    act(() => result.current.clearCache());
    expect(result.current.getHeight('m1')).toBeUndefined();
    expect(result.current.getHeight('m2')).toBeUndefined();
    expect(result.current.heightCache.size).toBe(0);
  });

  it('keeps one cache and stable callbacks across renders', () => {
    const { result, rerender } = renderHook(() => useMessageHeights());
    const first = result.current;

    rerender();
    expect(result.current.heightCache).toBe(first.heightCache);
    expect(result.current.setHeight).toBe(first.setHeight);
    expect(result.current.getHeight).toBe(first.getHeight);
    expect(result.current.clearCache).toBe(first.clearCache);
  });
});
