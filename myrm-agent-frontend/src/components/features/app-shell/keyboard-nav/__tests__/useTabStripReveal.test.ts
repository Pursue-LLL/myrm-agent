import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTabStripReveal } from '../useTabStripReveal';

describe('useTabStripReveal', () => {
  let mockContainer: HTMLDivElement;

  beforeEach(() => {
    mockContainer = document.createElement('div');
    Object.defineProperty(mockContainer, 'scrollWidth', { value: 800, configurable: true, writable: true });
    Object.defineProperty(mockContainer, 'clientWidth', { value: 400, configurable: true, writable: true });
    Object.defineProperty(mockContainer, 'scrollLeft', { value: 0, configurable: true, writable: true });
    mockContainer.getBoundingClientRect = vi.fn(() => ({
      left: 0,
      right: 400,
      width: 400,
      top: 0,
      bottom: 40,
      height: 40,
      x: 0,
      y: 0,
      toJSON: () => {},
    }));
    mockContainer.scrollTo = vi.fn();
  });

  it('should detect overflowing state properly on mount', () => {
    const { result } = renderHook(() => useTabStripReveal());
    act(() => {
      // 模拟绑定 ref
      result.current.containerRef.current = mockContainer;
      result.current.updateOverflow();
    });

    expect(result.current.overflowState.isOverflowing).toBe(true);
    expect(result.current.overflowState.canScrollLeft).toBe(false);
    expect(result.current.overflowState.canScrollRight).toBe(true);
    expect(result.current.overflowState.maxScrollLeft).toBe(400);
  });

  it('should reveal target tab by id and trigger scrollTo', () => {
    const tab1 = document.createElement('button');
    tab1.setAttribute('data-tab-id', 'tab-1');
    tab1.getBoundingClientRect = vi.fn(() => ({
      left: 380, // 超出容器右侧 (400) 附近
      right: 460,
      width: 80,
      top: 0,
      bottom: 40,
      height: 40,
      x: 380,
      y: 0,
      toJSON: () => {},
    }));
    mockContainer.appendChild(tab1);

    const { result } = renderHook(() => useTabStripReveal());
    act(() => {
      result.current.containerRef.current = mockContainer;
    });

    act(() => {
      result.current.revealTabById('tab-1', { safeMarginPx: 16 });
    });

    // 460 + 16 - 400 = 76 => scrollTo 应被调用为 left: 76
    expect(mockContainer.scrollTo).toHaveBeenCalledWith({
      left: 76,
      behavior: 'smooth',
    });
  });

  it('should reveal the last tab with end position alignment', () => {
    const tabLast = document.createElement('button');
    tabLast.setAttribute('data-tab-id', 'tab-last');
    tabLast.getBoundingClientRect = vi.fn(() => ({
      left: 420,
      right: 500,
      width: 80,
      top: 0,
      bottom: 40,
      height: 40,
      x: 420,
      y: 0,
      toJSON: () => {},
    }));
    mockContainer.appendChild(tabLast);

    const { result } = renderHook(() => useTabStripReveal());
    act(() => {
      result.current.containerRef.current = mockContainer;
    });

    act(() => {
      result.current.revealLastTab({ safeMarginPx: 20 });
    });

    // delta = 500 + 20 - 400 = 120
    expect(mockContainer.scrollTo).toHaveBeenCalledWith({
      left: 120,
      behavior: 'smooth',
    });
  });
});
