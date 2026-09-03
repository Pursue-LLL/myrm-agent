/**
 * [INPUT]: @/hooks/ui/useTrafficLightInsets::useTrafficLightInsets
 * [OUTPUT]: Unit tests for useTrafficLightInsets hook
 * [POS]: macOS 交通灯留白自适应 Hook 单测，覆盖 Mac 桌面端和 Web 端的自适应 CSS 变量注入与返回值。
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useTrafficLightInsets } from '../useTrafficLightInsets';
import { desktopBridge } from '@/lib/desktop-bridge';

function mockControls(
  overrides: Partial<{
    platform: string;
    isDesktop: boolean;
    controlsInsetTop: number;
    controlsInsetLeft: number;
  }> = {},
) {
  vi.spyOn(desktopBridge, 'getWindowControlsState').mockReturnValue({
    platform: 'web',
    isDesktop: false,
    controlsInsetTop: 0,
    controlsInsetLeft: 0,
    ...overrides,
  });
}

describe('useTrafficLightInsets', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns zero insets when in non-desktop web environment', () => {
    mockControls({ platform: 'web', isDesktop: false });

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.isImmersiveMac).toBe(false);
    expect(result.current.topInset).toBe(0);
    expect(result.current.leftInset).toBe(0);
  });

  it('returns zero insets when in Windows/Linux desktop environment', () => {
    mockControls({ platform: 'windows', isDesktop: true });

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.isImmersiveMac).toBe(false);
    expect(result.current.topInset).toBe(0);
    expect(result.current.leftInset).toBe(0);
  });

  it('returns positive insets and sets CSS variables in macOS desktop environment', () => {
    mockControls({ platform: 'macos', isDesktop: true, controlsInsetTop: 28, controlsInsetLeft: 78 });

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.isImmersiveMac).toBe(true);
    expect(result.current.topInset).toBe(28);
    expect(result.current.leftInset).toBe(78);
  });
});
