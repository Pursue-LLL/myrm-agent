/**
 * [INPUT]: @/hooks/ui/useTrafficLightInsets::useTrafficLightInsets
 * [OUTPUT]: Unit tests for useTrafficLightInsets hook
 * [POS]: macOS 交通灯留白自适应 Hook 单测，覆盖 Mac 桌面端和 Web 端的自适应 CSS 变量注入与返回值。
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useTrafficLightInsets } from '../useTrafficLightInsets';
import { desktopBridge } from '@/lib/desktopBridge';

describe('useTrafficLightInsets', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns zero insets when in non-desktop web environment', () => {
    vi.spyOn(desktopBridge, 'isDesktop').mockReturnValue(false);
    vi.spyOn(desktopBridge, 'isMacOS').mockReturnValue(true);

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.isImmersiveMac).toBe(false);
    expect(result.current.topInset).toBe(0);
    expect(result.current.leftInset).toBe(0);
  });

  it('returns zero insets when in Windows/Linux desktop environment', () => {
    vi.spyOn(desktopBridge, 'isDesktop').mockReturnValue(true);
    vi.spyOn(desktopBridge, 'isMacOS').mockReturnValue(false);

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.isImmersiveMac).toBe(false);
    expect(result.current.topInset).toBe(0);
    expect(result.current.leftInset).toBe(0);
  });

  it('returns positive insets and sets CSS variables in macOS desktop environment', () => {
    vi.spyOn(desktopBridge, 'isDesktop').mockReturnValue(true);
    vi.spyOn(desktopBridge, 'isMacOS').mockReturnValue(true);

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.isImmersiveMac).toBe(true);
    expect(result.current.topInset).toBe(28);
    expect(result.current.leftInset).toBe(78);
  });
});
