/** @vitest-environment jsdom */
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useMessageInputWidth } from '../useMessageInputWidth';

const WIDTH_VAR = '--message-input-width';
const publishedWidth = () => document.documentElement.style.getPropertyValue(WIDTH_VAR);

/** A column whose width can change between measurements, like a message list being resized; counts every read. */
function makeColumn(initialWidth: number) {
  const element = document.createElement('div');
  const measurement = { width: initialWidth, reads: 0 };
  Object.defineProperty(element, 'scrollWidth', {
    get: () => {
      measurement.reads += 1;
      return measurement.width;
    },
  });
  return { ref: { current: element }, measurement };
}

describe('useMessageInputWidth', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.documentElement.style.removeProperty(WIDTH_VAR);
  });

  it('publishes the column width 100ms after mount, not before', () => {
    const { ref } = makeColumn(812);
    renderHook(() => useMessageInputWidth(ref));

    vi.advanceTimersByTime(99);
    expect(publishedWidth()).toBe('');

    vi.advanceTimersByTime(1);
    expect(publishedWidth()).toBe('812px');
  });

  it('falls back to 740px when the column has no measurable width', () => {
    const { ref } = makeColumn(0);
    renderHook(() => useMessageInputWidth(ref));

    vi.advanceTimersByTime(100);

    expect(publishedWidth()).toBe('740px');
  });

  it('measures once, after the window stops resizing', () => {
    const { ref, measurement } = makeColumn(800);
    renderHook(() => useMessageInputWidth(ref));
    vi.advanceTimersByTime(100);
    expect(publishedWidth()).toBe('800px');
    measurement.reads = 0;

    measurement.width = 900;
    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(60);
    measurement.width = 1000;
    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(60);
    expect(publishedWidth()).toBe('800px');

    vi.advanceTimersByTime(40);
    expect(publishedWidth()).toBe('1000px');
    expect(measurement.reads).toBe(1);
  });

  it('leaves the width alone while there is no column to measure', () => {
    renderHook(() => useMessageInputWidth({ current: null }));

    vi.advanceTimersByTime(100);

    expect(publishedWidth()).toBe('');
  });

  it('measures the new column when the ref changes, and never the one it replaced', () => {
    const first = makeColumn(500);
    const second = makeColumn(900);
    const { rerender } = renderHook(({ columnRef }) => useMessageInputWidth(columnRef), {
      initialProps: { columnRef: first.ref },
    });

    rerender({ columnRef: second.ref });
    vi.advanceTimersByTime(100);

    expect(publishedWidth()).toBe('900px');
    expect(first.measurement.reads).toBe(0);
  });

  it('stops measuring once unmounted, for a pending measurement and for later resizes alike', () => {
    const { ref, measurement } = makeColumn(700);
    const { unmount } = renderHook(() => useMessageInputWidth(ref));

    unmount();
    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(500);

    expect(measurement.reads).toBe(0);
    expect(publishedWidth()).toBe('');
  });
});
