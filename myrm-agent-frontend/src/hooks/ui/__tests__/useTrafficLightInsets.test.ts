import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useTrafficLightInsets } from '../useTrafficLightInsets';
import { desktopBridge } from '@/lib/desktopBridge';

describe('useTrafficLightInsets', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('returns zero insets when in non-mac web environment', () => {
    vi.spyOn(desktopBridge, 'isDesktop').mockReturnValue(false);
    vi.spyOn(desktopBridge, 'isMacOS').mockReturnValue(false);

    const { result } = renderHook(() => useTrafficLightInsets());
    expect(result.current.topInset).toBe(0);
    expect(result.current.leftInset).toBe(0);
    expect(result.current.isImmersiveMac).toBe(false);
  });

  it('returns positive insets and sets CSS vars when in macOS desktop environment', () => {
    vi.spyOn(desktopBridge, 'isDesktop').mockReturnValue(true);
    vi.spyOn(desktopBridge, 'isMacOS').mockReturnValue(true);

    const { result } = renderHook(() => useTrafficLightInsets());
    expect(result.current.topInset).toBeGreaterThan(0);
    expect(result.current.leftInset).toBeGreaterThan(0);
    expect(result.current.isImmersiveMac).toBe(true);
  });
});
