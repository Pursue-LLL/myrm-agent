import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTrafficLightInsets } from '../useTrafficLightInsets';
import { desktopBridge } from '@/lib/desktopBridge';

describe('useTrafficLightInsets', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('returns 0 insets in Web or non-Mac environment', () => {
    vi.spyOn(desktopBridge, 'isMacOS').mockReturnValue(false);
    vi.spyOn(desktopBridge, 'isDesktop').mockReturnValue(false);

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.isImmersiveMac).toBe(false);
    expect(result.current.topInset).toBe(0);
    expect(result.current.leftInset).toBe(0);
  });

  it('returns active insets and sets CSS variables in macOS Tauri desktop environment', () => {
    vi.spyOn(desktopBridge, 'isMacOS').mockReturnValue(true);
    vi.spyOn(desktopBridge, 'isDesktop').mockReturnValue(true);

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.isImmersiveMac).toBe(true);
    expect(result.current.topInset).toBe(28);
    expect(result.current.leftInset).toBe(78);
  });
});
