/**
 * [INPUT]
 * localStorage (POS: Persistence for client vibrancy preferences)
 *
 * [OUTPUT]
 * - VibrancyStyleType, DesktopVibrancyState
 * - useDesktopVibrancy: Hook to manage native acrylic glassmorphism, mica, and liquid vibrancy
 *
 * [POS]
 * Desktop Vibrancy & Liquid Glassmorphism Hook (Item 17).
 * Single file < 220 lines. Zero `any` types.
 */

'use client';

import { useState, useEffect, useCallback } from 'react';

export type VibrancyStyleType =
  | 'mica'
  | 'acrylic'
  | 'vibrant_dark'
  | 'ultra_thin'
  | 'disabled';

export interface DesktopVibrancyState {
  platform: 'macos' | 'windows' | 'linux' | 'web';
  supportedStyles: VibrancyStyleType[];
  currentStyle: VibrancyStyleType;
  isBlurActive: boolean;
  blurIntensity: number; // 0 to 100
}

const STORAGE_KEY_STYLE = 'myrm:vibrancy-style';
const STORAGE_KEY_INTENSITY = 'myrm:vibrancy-intensity';

function detectPlatform(): 'macos' | 'windows' | 'linux' | 'web' {
  if (typeof window === 'undefined') {
    return 'web';
  }
  const ua = window.navigator.userAgent.toLowerCase();
  if (ua.includes('mac')) {
    return 'macos';
  }
  if (ua.includes('win')) {
    return 'windows';
  }
  if (ua.includes('linux')) {
    return 'linux';
  }
  return 'web';
}

function getPlatformSupportedStyles(platform: 'macos' | 'windows' | 'linux' | 'web'): VibrancyStyleType[] {
  if (platform === 'macos') {
    return ['vibrant_dark', 'ultra_thin', 'acrylic', 'disabled'];
  }
  if (platform === 'windows') {
    return ['mica', 'acrylic', 'vibrant_dark', 'disabled'];
  }
  return ['acrylic', 'vibrant_dark', 'disabled'];
}

function getDefaultStyle(platform: 'macos' | 'windows' | 'linux' | 'web'): VibrancyStyleType {
  if (platform === 'macos') {
    return 'vibrant_dark';
  }
  if (platform === 'windows') {
    return 'mica';
  }
  return 'acrylic';
}

export function useDesktopVibrancy() {
  const [platform, setPlatform] = useState<'macos' | 'windows' | 'linux' | 'web'>('web');
  const [currentStyle, setCurrentStyle] = useState<VibrancyStyleType>('vibrant_dark');
  const [blurIntensity, setBlurIntensityState] = useState<number>(85);
  const [isTauri, setIsTauri] = useState<boolean>(false);

  useEffect(() => {
    const detected = detectPlatform();
    setPlatform(detected);

    const isTauriEnv =
      typeof window !== 'undefined' &&
      Boolean(
        (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__,
      );
    setIsTauri(isTauriEnv);

    // Read stored preferences
    const storedStyle = localStorage.getItem(STORAGE_KEY_STYLE) as VibrancyStyleType | null;
    const storedIntensity = localStorage.getItem(STORAGE_KEY_INTENSITY);

    if (storedStyle) {
      setCurrentStyle(storedStyle);
    } else {
      setCurrentStyle(getDefaultStyle(detected));
    }

    if (storedIntensity) {
      const parsed = parseInt(storedIntensity, 10);
      if (!Number.isNaN(parsed) && parsed >= 0 && parsed <= 100) {
        setBlurIntensityState(parsed);
      }
    }
  }, []);

  // Sync CSS variables to root
  useEffect(() => {
    if (typeof document === 'undefined') {
      return;
    }
    const root = document.documentElement;
    if (currentStyle === 'disabled') {
      root.style.setProperty('--desktop-vibrancy-blur', '0px');
      root.style.setProperty('--desktop-vibrancy-saturate', '100%');
      root.classList.add('vibrancy-disabled');
    } else {
      const blurPx = Math.round((blurIntensity / 100) * 24);
      const satPct = 100 + Math.round((blurIntensity / 100) * 80);
      root.style.setProperty('--desktop-vibrancy-blur', `${blurPx}px`);
      root.style.setProperty('--desktop-vibrancy-saturate', `${satPct}%`);
      root.classList.remove('vibrancy-disabled');
    }
  }, [currentStyle, blurIntensity]);

  const setStyle = useCallback((newStyle: VibrancyStyleType) => {
    setCurrentStyle(newStyle);
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY_STYLE, newStyle);
    }
  }, []);

  const setBlurIntensity = useCallback((intensity: number) => {
    const clamped = Math.max(0, Math.min(100, intensity));
    setBlurIntensityState(clamped);
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY_INTENSITY, clamped.toString());
    }
  }, []);

  const toggleVibrancy = useCallback(() => {
    setCurrentStyle((prev) => {
      const next = prev === 'disabled' ? getDefaultStyle(platform) : 'disabled';
      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY_STYLE, next);
      }
      return next;
    });
  }, [platform]);

  // Global keyboard shortcut: Option+Cmd+V (Mac) or Alt+Ctrl+V (Win/Linux)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isAltOrOption = e.altKey;
      const isMetaOrCtrl = e.metaKey || e.ctrlKey;
      if (isAltOrOption && isMetaOrCtrl && (e.key === 'v' || e.key === 'V')) {
        e.preventDefault();
        toggleVibrancy();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleVibrancy]);

  const supportedStyles = getPlatformSupportedStyles(platform);

  return {
    platform,
    supportedStyles,
    currentStyle,
    isBlurActive: currentStyle !== 'disabled',
    blurIntensity,
    isTauri,
    setStyle,
    setBlurIntensity,
    toggleVibrancy,
  };
}
