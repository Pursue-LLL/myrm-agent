import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useTrafficLightInsets } from '../useTrafficLightInsets';
import { desktopBridge } from '@/lib/desktop-bridge';

describe('useTrafficLightInsets', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('sets zero insets in standard web browser environment', () => {
    vi.spyOn(desktopBridge, 'getWindowControlsState').mockReturnValue({
      controlsInsetTop: 0,
      controlsInsetLeft: 0,
      platform: 'web',
      isDesktop: false,
      isOverlayTitlebar: false,
    });

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.topInset).toBe(0);
    expect(result.current.leftInset).toBe(0);
    expect(result.current.isImmersiveMac).toBe(false);
  });

  it('sets non-zero insets when running in macOS desktop environment', () => {
    vi.spyOn(desktopBridge, 'getWindowControlsState').mockReturnValue({
      controlsInsetTop: 28,
      controlsInsetLeft: 76,
      platform: 'macos',
      isDesktop: true,
      isOverlayTitlebar: true,
    });

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.topInset).toBe(28);
    expect(result.current.leftInset).toBe(76);
    expect(result.current.isImmersiveMac).toBe(true);
  });
});

