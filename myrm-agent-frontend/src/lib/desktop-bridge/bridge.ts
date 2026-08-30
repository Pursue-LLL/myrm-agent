/**
 * [INPUT]
 * - @/lib/tauri::isTauriEnvironment
 * - @/lib/desktop-bridge/types::DesktopBridge, DesktopPlatform, DesktopWindowControlsState, DesktopBridgeCapabilities
 *
 * [OUTPUT]
 * - detectDesktopPlatform: Detects runtime OS platform cleanly
 * - createDesktopBridge: Creates standard desktop bridge implementation
 * - defaultDesktopBridge: Singleton instance of DesktopBridge
 * - getDesktopWindowControlsState: Computes safe titlebar and traffic lights insets
 *
 * [POS]
 * Implementation of Standardized Desktop Bridge protocol. Provides runtime detection,
 * progressive feature enhancement, and unified platform APIs across Web, Desktop, and Cloud.
 */

import { isTauriEnvironment } from '@/lib/tauri';
import type {
  DesktopBridge,
  DesktopBridgeCapabilities,
  DesktopPlatform,
  DesktopWindowControlsState,
  NativeOpenFileDialogOptions,
} from './types';

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

class StandardDesktopBridge implements DesktopBridge {
  getPlatform(): DesktopPlatform {
    return detectDesktopPlatform();
  }

  isDesktop(): boolean {
    return isTauriEnvironment();
  }

  getCapabilities(): DesktopBridgeCapabilities {
    const desktop = this.isDesktop();
    return {
      hasNativeDialog: desktop,
      hasNativeTray: desktop,
      hasNativeNotification: desktop || (typeof window !== 'undefined' && 'Notification' in window),
      hasNativeClipboard: typeof navigator !== 'undefined' && 'clipboard' in navigator,
      hasNativeGlobalShortcuts: desktop,
      hasNativeProcessRegistry: desktop,
    };
  }

  getWindowControlsState(): DesktopWindowControlsState {
    return getDesktopWindowControlsState();
  }

  async openFileDialog(options?: NativeOpenFileDialogOptions): Promise<string | string[] | null> {
    if (!this.isDesktop()) {
      return null;
    }

    try {
      const { open: openDialog } = await import('@tauri-apps/plugin-dialog');
      const selected = await openDialog({
        title: options?.title,
        multiple: options?.multiple ?? false,
        directory: options?.directory ?? false,
        defaultPath: options?.defaultPath,
        filters: options?.filters,
      });
      return selected as string | string[] | null;
    } catch (err) {
      console.warn('Desktop bridge failed to open native file dialog:', err);
      return null;
    }
  }

  async sendNotification(title: string, body?: string): Promise<boolean> {
    if (this.isDesktop()) {
      try {
        const { sendNotification, isPermissionGranted, requestPermission } = await import(
          '@tauri-apps/plugin-notification'
        );
        let hasPermission = await isPermissionGranted();
        if (!hasPermission) {
          const permission = await requestPermission();
          hasPermission = permission === 'granted';
        }
        if (hasPermission) {
          sendNotification({ title, body });
          return true;
        }
      } catch (err) {
        console.warn('Native desktop notification failed, falling back to Web API:', err);
      }
    }

    // Web Notification Fallback
    if (typeof window !== 'undefined' && 'Notification' in window) {
      try {
        if (Notification.permission === 'granted') {
          new Notification(title, { body });
          return true;
        }
        if (Notification.permission !== 'denied') {
          const perm = await Notification.requestPermission();
          if (perm === 'granted') {
            new Notification(title, { body });
            return true;
          }
        }
      } catch (err) {
        console.warn('Web notification delivery failed:', err);
      }
    }

    return false;
  }
}

export const defaultDesktopBridge: DesktopBridge = new StandardDesktopBridge();
