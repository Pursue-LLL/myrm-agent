'use client';

/**
 * [INPUT]
 * - window.visualViewport API
 * - window.matchMedia('(display-mode: standalone)')
 *
 * [OUTPUT]
 * - useMobileViewportAdapter: Hook adapting mobile viewport heights, safe areas, and dynamic keyboard offsets
 *
 * [POS]
 * Mobile Shell viewport and software keyboard collision adapter for PWA standalone parity.
 */

import { useState, useEffect, useCallback } from 'react';

export interface MobileViewportMetrics {
  viewportHeight: number;
  keyboardHeight: number;
  isKeyboardOpen: boolean;
  isStandalone: boolean;
}

export function useMobileViewportAdapter(): MobileViewportMetrics {
  const [metrics, setMetrics] = useState<MobileViewportMetrics>(() => {
    if (typeof window === 'undefined') {
      return {
        viewportHeight: 0,
        keyboardHeight: 0,
        isKeyboardOpen: false,
        isStandalone: false,
      };
    }
    const isStandalone =
      (typeof window.matchMedia === 'function' && window.matchMedia('(display-mode: standalone)').matches) ||
      ('standalone' in window.navigator && Boolean((window.navigator as unknown as { standalone: boolean }).standalone));
    return {
      viewportHeight: window.innerHeight,
      keyboardHeight: 0,
      isKeyboardOpen: false,
      isStandalone,
    };
  });

  const handleViewportChange = useCallback(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const vv = window.visualViewport;
    const windowH = window.innerHeight;
    const currentH = vv ? vv.height : windowH;
    const keyboardH = Math.max(0, windowH - currentH);
    const isKeyboardOpen = keyboardH > 120; // Keyboard usually > 120px on mobile devices

    const isStandalone =
      (typeof window.matchMedia === 'function' && window.matchMedia('(display-mode: standalone)').matches) ||
      ('standalone' in window.navigator && Boolean((window.navigator as unknown as { standalone: boolean }).standalone));

    // Update CSS custom properties for global layout consumption
    document.documentElement.style.setProperty('--mobile-viewport-height', `${currentH}px`);
    document.documentElement.style.setProperty('--mobile-keyboard-height', `${keyboardH}px`);

    setMetrics({
      viewportHeight: currentH,
      keyboardHeight: keyboardH,
      isKeyboardOpen,
      isStandalone,
    });
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    handleViewportChange();

    const vv = window.visualViewport;
    if (vv) {
      vv.addEventListener('resize', handleViewportChange);
      vv.addEventListener('scroll', handleViewportChange);
    }
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('orientationchange', handleViewportChange);

    return () => {
      if (vv) {
        vv.removeEventListener('resize', handleViewportChange);
        vv.removeEventListener('scroll', handleViewportChange);
      }
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('orientationchange', handleViewportChange);
    };
  }, [handleViewportChange]);

  return metrics;
}
