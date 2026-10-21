/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useMobileViewportAdapter } from '../useMobileViewportAdapter';

describe('useMobileViewportAdapter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'innerHeight', {
      writable: true,
      configurable: true,
      value: 800,
    });
  });

  it('initializes with default window metrics and sets CSS variables', () => {
    const { result } = renderHook(() => useMobileViewportAdapter());

    expect(result.current.viewportHeight).toBe(800);
    expect(result.current.keyboardHeight).toBe(0);
    expect(result.current.isKeyboardOpen).toBe(false);
    expect(document.documentElement.style.getPropertyValue('--mobile-viewport-height')).toBe('800px');
  });

  it('detects standalone mode when matchMedia matches', () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('standalone'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const { result } = renderHook(() => useMobileViewportAdapter());
    expect(result.current.isStandalone).toBe(true);

    window.matchMedia = originalMatchMedia;
  });

  it('updates metrics when visualViewport resizes due to software keyboard', () => {
    const listeners: Record<string, () => void> = {};
    const mockVisualViewport = {
      height: 500, // Reduced from 800 -> 300px keyboard
      width: 400,
      addEventListener: vi.fn((event: string, cb: () => void) => {
        listeners[event] = cb;
      }),
      removeEventListener: vi.fn(),
    };

    Object.defineProperty(window, 'visualViewport', {
      writable: true,
      configurable: true,
      value: mockVisualViewport,
    });

    const { result } = renderHook(() => useMobileViewportAdapter());

    // Initially when hooked, visualViewport height is 500
    expect(result.current.viewportHeight).toBe(500);
    expect(result.current.keyboardHeight).toBe(300);
    expect(result.current.isKeyboardOpen).toBe(true);
    expect(document.documentElement.style.getPropertyValue('--mobile-keyboard-height')).toBe('300px');

    // Simulate keyboard dismissal: visualViewport restored to 800
    mockVisualViewport.height = 800;
    act(() => {
      listeners['resize']?.();
    });

    expect(result.current.viewportHeight).toBe(800);
    expect(result.current.keyboardHeight).toBe(0);
    expect(result.current.isKeyboardOpen).toBe(false);
  });
});
