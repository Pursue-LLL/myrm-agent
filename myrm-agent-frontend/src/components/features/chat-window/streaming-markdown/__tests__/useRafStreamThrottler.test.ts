import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRafStreamThrottler } from '../useRafStreamThrottler';

describe('useRafStreamThrottler', () => {
  let rafCallback: FrameRequestCallback | null = null;
  let rafId = 0;

  beforeEach(() => {
    rafCallback = null;
    rafId = 0;

    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback: FrameRequestCallback) => {
      rafCallback = callback;
      return ++rafId;
    });

    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {
      rafCallback = null;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('synchronously displays content when isStreaming is false', () => {
    const { result, rerender } = renderHook(
      ({ content, streaming }) => useRafStreamThrottler(content, streaming),
      { initialProps: { content: 'Initial message', streaming: false } },
    );

    expect(result.current.displayedContent).toBe('Initial message');
    expect(result.current.metrics.tokensPerSecond).toBe(0);

    // Update content while still not streaming
    rerender({ content: 'Updated message', streaming: false });
    expect(result.current.displayedContent).toBe('Updated message');
  });

  it('batches streaming chunks across animation frames', () => {
    const { result, rerender } = renderHook(
      ({ content, streaming }) =>
        useRafStreamThrottler(content, streaming, {
          targetFps: 60,
          maxBatchCharsPerFrame: 50,
        }),
      { initialProps: { content: 'Hello', streaming: true } },
    );

    expect(window.requestAnimationFrame).toHaveBeenCalled();

    // Trigger RAF frame
    act(() => {
      if (rafCallback) {
        rafCallback(100);
      }
    });

    // Content should catch up within batch size
    expect(result.current.displayedContent).toBe('Hello');

    // Simulate high frequency token appending
    rerender({
      content: 'Hello World! This is a fast stream of tokens coming from an ultra-fast flash model.',
      streaming: true,
    });

    act(() => {
      if (rafCallback) {
        rafCallback(120);
      }
    });

    // It advanced by batch limit
    expect(result.current.displayedContent.length).toBeGreaterThan(5);
  });

  it('flushes immediately when flushImmediate is called', () => {
    const fullText = 'Long text pending in buffer that needs immediate completion.';
    const { result } = renderHook(() =>
      useRafStreamThrottler(fullText, true, { maxBatchCharsPerFrame: 10 }),
    );

    act(() => {
      result.current.flushImmediate();
    });

    expect(result.current.displayedContent).toBe(fullText);
    expect(result.current.metrics.isDegradedMode).toBe(false);
  });

  it('resets buffer and metrics completely', () => {
    const { result } = renderHook(() => useRafStreamThrottler('Some text', true));

    act(() => {
      result.current.reset();
    });

    expect(result.current.displayedContent).toBe('');
    expect(result.current.metrics.tokensPerSecond).toBe(0);
    expect(result.current.metrics.isDegradedMode).toBe(false);
  });

  it('activates degraded mode under extreme throughput', () => {
    const { result, rerender } = renderHook(
      ({ content, streaming }) =>
        useRafStreamThrottler(content, streaming, {
          targetFps: 60,
          highThroughputThresholdTokensPerSec: 50,
        }),
      { initialProps: { content: 'Initial', streaming: true } },
    );

    // Simulate extreme token burst
    rerender({
      content: 'Initial' + 'A'.repeat(1000),
      streaming: true,
    });

    act(() => {
      if (rafCallback) {
        rafCallback(100);
      }
    });

    expect(result.current.metrics.isDegradedMode).toBe(true);
  });
});
