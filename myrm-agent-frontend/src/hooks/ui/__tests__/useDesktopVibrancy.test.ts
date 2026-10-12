/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useDesktopVibrancy } from '../useDesktopVibrancy';

describe('useDesktopVibrancy hook', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.style.removeProperty('--desktop-vibrancy-blur');
    document.documentElement.style.removeProperty('--desktop-vibrancy-saturate');
    document.documentElement.classList.remove('vibrancy-disabled');
  });

  it('initializes with default platform and supported styles', () => {
    const { result } = renderHook(() => useDesktopVibrancy());

    expect(result.current.platform).toBeDefined();
    expect(result.current.supportedStyles.length).toBeGreaterThan(0);
    expect(result.current.isBlurActive).toBe(true);
    expect(result.current.blurIntensity).toBe(85);
  });

  it('updates style and persists to localStorage', () => {
    const { result } = renderHook(() => useDesktopVibrancy());

    act(() => {
      result.current.setStyle('acrylic');
    });

    expect(result.current.currentStyle).toBe('acrylic');
    expect(localStorage.getItem('myrm:vibrancy-style')).toBe('acrylic');
  });

  it('adjusts blur intensity and syncs CSS variables', () => {
    const { result } = renderHook(() => useDesktopVibrancy());

    act(() => {
      result.current.setBlurIntensity(50);
    });

    expect(result.current.blurIntensity).toBe(50);
    expect(localStorage.getItem('myrm:vibrancy-intensity')).toBe('50');

    // 50% of 24px = 12px
    expect(document.documentElement.style.getPropertyValue('--desktop-vibrancy-blur')).toBe('12px');
  });

  it('clamps blur intensity between 0 and 100', () => {
    const { result } = renderHook(() => useDesktopVibrancy());

    act(() => {
      result.current.setBlurIntensity(150);
    });
    expect(result.current.blurIntensity).toBe(100);

    act(() => {
      result.current.setBlurIntensity(-20);
    });
    expect(result.current.blurIntensity).toBe(0);
  });

  it('toggles vibrancy on and off', () => {
    const { result } = renderHook(() => useDesktopVibrancy());
    expect(result.current.isBlurActive).toBe(true);

    act(() => {
      result.current.toggleVibrancy();
    });

    expect(result.current.currentStyle).toBe('disabled');
    expect(result.current.isBlurActive).toBe(false);
    expect(document.documentElement.style.getPropertyValue('--desktop-vibrancy-blur')).toBe('0px');
    expect(document.documentElement.classList.contains('vibrancy-disabled')).toBe(true);

    act(() => {
      result.current.toggleVibrancy();
    });

    expect(result.current.isBlurActive).toBe(true);
    expect(document.documentElement.classList.contains('vibrancy-disabled')).toBe(false);
  });

  it('toggles vibrancy via keyboard shortcut Option+Cmd+V', () => {
    const { result } = renderHook(() => useDesktopVibrancy());
    expect(result.current.isBlurActive).toBe(true);

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent('keydown', {
          key: 'v',
          altKey: true,
          metaKey: true,
        }),
      );
    });

    expect(result.current.currentStyle).toBe('disabled');
    expect(result.current.isBlurActive).toBe(false);
  });
});
