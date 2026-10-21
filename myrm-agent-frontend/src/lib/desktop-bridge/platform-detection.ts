/**
 * [INPUT]
 * - @/lib/tauri::isTauriEnvironment (POS: Tauri 运行环境判定)
 * - ./types::DesktopPlatform, DesktopWindowControlsState (POS: 桥接契约类型 SSOT)
 *
 * [OUTPUT]
 * - detectDesktopPlatform: Detects runtime OS platform cleanly
 * - getDesktopWindowControlsState: Computes safe titlebar and traffic lights insets
 *
 * [POS]
 * 纯运行时平台探测叶子模块。零桥接实现依赖，供工厂（bridge.ts）与 Tauri 实现
 * （tauri-bridge.ts）共同引用，保持域内依赖单向无环。
 */

import { isTauriEnvironment } from '@/lib/tauri';
import type { DesktopPlatform, DesktopWindowControlsState } from './types';

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
