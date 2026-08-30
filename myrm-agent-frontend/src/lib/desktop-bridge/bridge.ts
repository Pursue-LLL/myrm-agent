/**
 * [INPUT]
 * - @/lib/tauri::isTauriEnvironment
 * - @/lib/desktop-bridge/types::IDesktopBridge, DesktopPlatform, DesktopWindowControlsState, DesktopBridgeCapabilities
 * - @/lib/desktop-bridge/tauri-bridge::TauriDesktopBridge
 * - @/lib/desktop-bridge/web-fallback-bridge::WebFallbackDesktopBridge
 *
 * [OUTPUT]
 * - detectDesktopPlatform: Detects runtime OS platform cleanly
 * - getDesktopWindowControlsState: Computes safe titlebar and traffic lights insets
 * - createDesktopBridge: Creates unified desktop bridge implementation based on environment
 * - defaultDesktopBridge / desktopBridge: Singleton instance of IDesktopBridge
 *
 * [POS]
 * Implementation of Standardized Desktop Bridge protocol. Provides runtime detection,
 * progressive feature enhancement, and unified platform APIs across Web, Desktop, and Cloud.
 */

import { isTauriEnvironment } from '@/lib/tauri';
import { TauriDesktopBridge } from './tauri-bridge';
import type { DesktopPlatform, DesktopWindowControlsState, IDesktopBridge } from './types';
import { WebFallbackDesktopBridge } from './web-fallback-bridge';

export function detectDesktopPlatform(): DesktopPlatform {
  if (!isTauriEnvironment()) {
    return 'web';
  }
  if (typeof navigator === 'undefined') {
    return 'web';
  }
  const userAgent = navigator.userAgent.toLowerCase();
  const platform = (navigator.platform || '').toLowerCase();

  if (userAgent.includes('mac') || platform.includes('mac')) {
    return 'macos';
  }
  if (userAgent.includes('win') || platform.includes('win')) {
    return 'windows';
  }
  if (userAgent.includes('linux') || platform.includes('linux')) {
    return 'linux';
  }
  return 'web';
}

export function getDesktopWindowControlsState(): DesktopWindowControlsState {
  const isDesktop = isTauriEnvironment();
  const platform = detectDesktopPlatform();

  if (!isDesktop) {
    return {
      controlsInsetTop: 0,
      controlsInsetLeft: 0,
      platform: 'web',
      isDesktop: false,
      isOverlayTitlebar: false,
    };
  }

  // In Tauri desktop, macOS has overlay traffic lights at top-left
  if (platform === 'macos') {
    return {
      controlsInsetTop: 28,
      controlsInsetLeft: 76,
      platform: 'macos',
      isDesktop: true,
      isOverlayTitlebar: true,
    };
  }

  // Windows / Linux custom titlebar
  return {
    controlsInsetTop: 0,
    controlsInsetLeft: 0,
    platform,
    isDesktop: true,
    isOverlayTitlebar: false,
  };
}

export function createDesktopBridge(): IDesktopBridge {
  if (isTauriEnvironment()) {
    return new TauriDesktopBridge();
  }
  return new WebFallbackDesktopBridge();
}

export const defaultDesktopBridge: IDesktopBridge = createDesktopBridge();
export const desktopBridge: IDesktopBridge = defaultDesktopBridge;
