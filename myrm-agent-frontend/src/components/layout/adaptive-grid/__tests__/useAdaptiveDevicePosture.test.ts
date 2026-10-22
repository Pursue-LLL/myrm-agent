/** @vitest-environment jsdom */
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  calculateDevicePosture,
  useAdaptiveDevicePosture,
} from '../useAdaptiveDevicePosture';

describe('useAdaptiveDevicePosture & calculateDevicePosture', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('correctly identifies foldable-expanded state (8:7 ratio)', () => {
    // Example: Huawei Mate X5 / Samsung Z Fold unfolded
    const result = calculateDevicePosture(800, 700);

    expect(result.posture).toBe('foldable-expanded');
    expect(result.layoutMode).toBe('dual-panel-golden');
    expect(result.orientation).toBe('landscape');
    expect(result.aspectRatio).toBeCloseTo(1.143, 2);
  });

  it('correctly identifies mobile-landscape compact state (e.g. 19.5:9 / 21:9)', () => {
    // Example: iPhone 14 Pro horizontal (844 x 390)
    const result = calculateDevicePosture(844, 390);

    expect(result.posture).toBe('mobile-landscape');
    expect(result.layoutMode).toBe('mobile-landscape-compact');
    expect(result.orientation).toBe('landscape');
    expect(result.aspectRatio).toBeGreaterThan(1.7);
  });

  it('correctly identifies mobile-portrait state', () => {
    // Example: iPhone 14 Pro vertical (390 x 844)
    const result = calculateDevicePosture(390, 844);

    expect(result.posture).toBe('mobile-portrait');
    expect(result.layoutMode).toBe('single-panel-stacked');
    expect(result.orientation).toBe('portrait');
    expect(result.aspectRatio).toBeLessThan(0.8);
  });

  it('correctly identifies tablet-landscape state', () => {
    // Example: iPad 1024 x 768
    const result = calculateDevicePosture(1024, 768);

    expect(result.posture).toBe('tablet-landscape');
    expect(result.layoutMode).toBe('dual-panel-golden');
    expect(result.orientation).toBe('landscape');
  });

  it('correctly identifies desktop wide-screen state', () => {
    // Example: Desktop monitor 1440 x 900
    const result = calculateDevicePosture(1440, 900);

    expect(result.posture).toBe('desktop');
    expect(result.layoutMode).toBe('desktop-tri-panel');
    expect(result.orientation).toBe('landscape');
  });

  it('hook updates metrics on window resize event', () => {
    window.innerWidth = 800;
    window.innerHeight = 700;

    const { result } = renderHook(() => useAdaptiveDevicePosture());

    expect(result.current.posture).toBe('foldable-expanded');
    expect(result.current.isFoldable).toBe(true);

    act(() => {
      window.innerWidth = 390;
      window.innerHeight = 844;
      window.dispatchEvent(new Event('resize'));
    });

    expect(result.current.posture).toBe('mobile-portrait');
    expect(result.current.layoutMode).toBe('single-panel-stacked');
    expect(result.current.isFoldable).toBe(false);
  });
});
