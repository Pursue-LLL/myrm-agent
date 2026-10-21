'use client';

/**
 * [INPUT]
 * - window.innerWidth / window.innerHeight / window.visualViewport
 * - adaptiveGridTypes: DevicePosture, AdaptiveLayoutMode, AdaptiveViewportMetrics
 *
 * [OUTPUT]
 * - useAdaptiveDevicePosture: React hook detecting foldable, tablet, landscape postures & layout modes
 *
 * [POS]
 * Responsive posture and aspect-ratio detection engine for foldables, tablets, and multi-window split views.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  AdaptiveViewportMetrics,
  DevicePosture,
  AdaptiveLayoutMode,
  ScreenOrientation,
} from './adaptiveGridTypes';

export function calculateDevicePosture(width: number, height: number): {
  posture: DevicePosture;
  layoutMode: AdaptiveLayoutMode;
  orientation: ScreenOrientation;
  aspectRatio: number;
} {
  const safeHeight = Math.max(1, height);
  const aspectRatio = Number((width / safeHeight).toFixed(3));
  const orientation: ScreenOrientation = width >= safeHeight ? 'landscape' : 'portrait';

  // 1. Foldable unfolded state: near-square or 8:7 ratio (typically 0.85 <= ratio <= 1.28)
  // with compact foldable unfolded logical width between 550px and 920px
  if (width >= 550 && width <= 920 && aspectRatio >= 0.85 && aspectRatio <= 1.28) {
    return {
      posture: 'foldable-expanded',
      layoutMode: 'dual-panel-golden',
      orientation,
      aspectRatio,
    };
  }

  // 2. Mobile ultra-wide landscape: slim height with wide ratio (e.g., 19.5:9 or 21:9)
  if (safeHeight <= 500 && aspectRatio >= 1.7) {
    return {
      posture: 'mobile-landscape',
      layoutMode: 'mobile-landscape-compact',
      orientation,
      aspectRatio,
    };
  }

  // 3. Tablet landscape: wide tablet view (e.g. iPad 1024x768 4:3 / 16:10 in landscape)
  if (width >= 768 && width < 1280 && safeHeight > 500 && aspectRatio > 1.25 && aspectRatio <= 1.75) {
    return {
      posture: 'tablet-landscape',
      layoutMode: 'dual-panel-golden',
      orientation,
      aspectRatio,
    };
  }

  // 4. Standard mobile portrait: narrow width and vertical ratio
  if (width < 600 && aspectRatio < 0.85) {
    return {
      posture: 'mobile-portrait',
      layoutMode: 'single-panel-stacked',
      orientation,
      aspectRatio,
    };
  }

  // 5. Desktop default wide screen
  return {
    posture: 'desktop',
    layoutMode: width >= 1280 ? 'desktop-tri-panel' : 'dual-panel-golden',
    orientation,
    aspectRatio,
  };
}

export function useAdaptiveDevicePosture(): AdaptiveViewportMetrics {
  const [metrics, setMetrics] = useState<AdaptiveViewportMetrics>(() => {
    if (typeof window === 'undefined') {
      return {
        width: 1024,
        height: 768,
        aspectRatio: 1.333,
        orientation: 'landscape',
        posture: 'desktop',
        layoutMode: 'dual-panel-golden',
        isFoldable: false,
        isMobileLandscape: false,
      };
    }

    const w = window.innerWidth;
    const h = window.innerHeight;
    const { posture, layoutMode, orientation, aspectRatio } = calculateDevicePosture(w, h);

    return {
      width: w,
      height: h,
      aspectRatio,
      orientation,
      posture,
      layoutMode,
      isFoldable: posture === 'foldable-expanded',
      isMobileLandscape: posture === 'mobile-landscape',
    };
  });

  const handleResize = useCallback(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const vv = window.visualViewport;
    const w = vv ? Math.round(vv.width) : window.innerWidth;
    const h = vv ? Math.round(vv.height) : window.innerHeight;
    const { posture, layoutMode, orientation, aspectRatio } = calculateDevicePosture(w, h);

    setMetrics({
      width: w,
      height: h,
      aspectRatio,
      orientation,
      posture,
      layoutMode,
      isFoldable: posture === 'foldable-expanded',
      isMobileLandscape: posture === 'mobile-landscape',
    });
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    handleResize();

    const vv = window.visualViewport;
    if (vv) {
      vv.addEventListener('resize', handleResize);
    }
    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleResize);

    return () => {
      if (vv) {
        vv.removeEventListener('resize', handleResize);
      }
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', handleResize);
    };
  }, [handleResize]);

  return metrics;
}
