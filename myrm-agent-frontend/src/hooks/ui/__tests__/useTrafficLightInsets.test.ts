import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useTrafficLightInsets } from '../useTrafficLightInsets';
import { desktopBridge } from '@/lib/desktopBridge';

describe('useTrafficLightInsets', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns 0 insets in web or non-Mac environment', () => {
    vi.spyOn(desktopBridge, 'isMacOS').mockReturnValue(false);
    vi.spyOn(desktopBridge, 'isDesktop').mockReturnValue(false);

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.topInset).toBe(0);
    expect(result.current.leftInset).toBe(0);
    expect(result.current.isImmersiveMac).toBe(false);
  });

  it('calculates proper insets when in macOS desktop environment', () => {
    vi.spyOn(desktopBridge, 'isMacOS').mockReturnValue(true);
    vi.spyOn(desktopBridge, 'isDesktop').mockReturnValue(true);

    const { result } = renderHook(() => useTrafficLightInsets());

    expect(result.current.topInset).toBe(28);
    expect(result.current.leftInset).toBe(78);
    expect(result.current.isImmersiveMac).toBe(true);
  });
});
