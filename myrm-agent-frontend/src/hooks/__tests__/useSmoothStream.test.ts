import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSmoothStream } from '../useSmoothStream';

// Mock requestAnimationFrame
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

describe('useSmoothStream', () => {
  it('should initialize with empty state', () => {
    const { result } = renderHook(() => useSmoothStream());

    expect(result.current.displayedContent).toBe('');
    expect(result.current.isAnimating).toBe(false);
  });

  it('should add chunk and start animation', () => {
    const { result } = renderHook(() => useSmoothStream());

    act(() => {
      result.current.addChunk('Hello');
    });

    expect(result.current.isAnimating).toBe(true);
    expect(window.requestAnimationFrame).toHaveBeenCalled();
  });

  it('should display characters gradually', () => {
    const { result } = renderHook(() => useSmoothStream({ minDelay: 0 }));

    act(() => {
      result.current.addChunk('Hello');
    });

    // Simulate animation frame
    act(() => {
      if (rafCallback) {
        rafCallback(performance.now());
      }
    });

    // Should have displayed some characters
    expect(result.current.displayedContent.length).toBeGreaterThan(0);
    expect(result.current.displayedContent.length).toBeLessThanOrEqual(5);
  });

  it('should flush all remaining content', () => {
    const { result } = renderHook(() => useSmoothStream());

    act(() => {
      result.current.addChunk('Hello World');
    });

    act(() => {
      result.current.flush();
    });

    expect(result.current.displayedContent).toBe('Hello World');
    expect(result.current.isAnimating).toBe(false);
  });

  it('should reset state', () => {
    const { result } = renderHook(() => useSmoothStream());

    act(() => {
      result.current.addChunk('Hello');
      result.current.flush();
    });

    expect(result.current.displayedContent).toBe('Hello');

    act(() => {
      result.current.reset();
    });

    expect(result.current.displayedContent).toBe('');
    expect(result.current.isAnimating).toBe(false);
  });

  it('should handle multiple chunks', () => {
    const { result } = renderHook(() => useSmoothStream({ minDelay: 0 }));

    act(() => {
      result.current.addChunk('Hello ');
    });

    act(() => {
      result.current.addChunk('World');
    });

    act(() => {
      result.current.flush();
    });

    expect(result.current.displayedContent).toBe('Hello World');
  });

  it('should handle empty chunk', () => {
    const { result } = renderHook(() => useSmoothStream());

    act(() => {
      result.current.addChunk('');
    });

    expect(result.current.displayedContent).toBe('');
    expect(result.current.isAnimating).toBe(false);
  });

  it('should handle CJK characters correctly', () => {
    const { result } = renderHook(() => useSmoothStream());

    act(() => {
      result.current.addChunk('你好世界');
      result.current.flush();
    });

    expect(result.current.displayedContent).toBe('你好世界');
  });

  it('should handle emoji correctly', () => {
    const { result } = renderHook(() => useSmoothStream());

    act(() => {
      result.current.addChunk('👋🌍');
      result.current.flush();
    });

    expect(result.current.displayedContent).toBe('👋🌍');
  });

  it('should stop animation when queue is empty', () => {
    const { result } = renderHook(() => useSmoothStream({ minDelay: 0 }));

    act(() => {
      result.current.addChunk('Hi');
    });

    // Simulate multiple animation frames until queue is empty
    act(() => {
      if (rafCallback) rafCallback(performance.now());
    });
    act(() => {
      if (rafCallback) rafCallback(performance.now());
    });
    act(() => {
      if (rafCallback) rafCallback(performance.now());
    });

    // After enough frames, all content should be displayed
    expect(result.current.displayedContent).toBe('Hi');
  });
});
