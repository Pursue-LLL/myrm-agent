/** @vitest-environment jsdom */

import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  useRotatingPlaceholder,
  DEFAULT_TASK_TEMPLATES,
} from '../useRotatingPlaceholder';

describe('useRotatingPlaceholder', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('initializes with the first default template', () => {
    const { result } = renderHook(() => useRotatingPlaceholder());

    expect(result.current.currentIndex).toBe(0);
    expect(result.current.currentEntry.id).toBe(DEFAULT_TASK_TEMPLATES[0].id);
    expect(result.current.placeholderText).toBe(DEFAULT_TASK_TEMPLATES[0].prompt);
    expect(result.current.category).toBe(DEFAULT_TASK_TEMPLATES[0].category);
  });

  it('cycles to the next template when nextPlaceholder is called', () => {
    const { result } = renderHook(() => useRotatingPlaceholder());

    act(() => {
      result.current.nextPlaceholder();
    });

    expect(result.current.currentIndex).toBe(1);
    expect(result.current.currentEntry.id).toBe(DEFAULT_TASK_TEMPLATES[1].id);
  });

  it('automatically advances after interval timer', () => {
    const { result } = renderHook(() =>
      useRotatingPlaceholder({ intervalMs: 3000 })
    );

    expect(result.current.currentIndex).toBe(0);

    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(result.current.currentIndex).toBe(1);

    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(result.current.currentIndex).toBe(2);
  });

  it('does not advance when enabled is false', () => {
    const { result } = renderHook(() =>
      useRotatingPlaceholder({ intervalMs: 3000, enabled: false })
    );

    act(() => {
      vi.advanceTimersByTime(6000);
    });

    expect(result.current.currentIndex).toBe(0);
  });
});
