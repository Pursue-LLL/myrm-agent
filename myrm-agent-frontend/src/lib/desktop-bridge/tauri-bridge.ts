/**
 * [INPUT]
 * - types.ts: IDesktopBridge and sub-bridge interfaces
 * - @/lib/tauri: isTauriEnvironment
 * - @tauri-apps/plugin-shell / plugin-dialog / plugin-notification: official plugins, dynamically imported
 * - ./platform-detection: detectDesktopPlatform, getDesktopWindowControlsState
 *
 * [OUTPUT]
 * - TauriDesktopBridge: Native bridge implementation for Tauri desktop application
 *
 * [POS]
 * Desktop bridge Tauri implementation. Connects typed frontend calls to official Tauri plugins and the global event bridge.
 */

import { isTauriEnvironment } from '@/lib/tauri';
import { detectDesktopPlatform, getDesktopWindowControlsState } from './platform-detection';
import type {
  DesktopBridgeCapabilities,
  DesktopPlatform,
  DesktopWindowControlsState,
  IAppshotBridge,
  IDesktopBridge,
  INotificationBridge,
  IShellBridge,
  ITrayBridge,
  IWindowBridge,
  NativeNotificationPayload,
  NativeOpenFileDialogOptions,
  WindowMetrics,
} from './types';

class TauriWindowBridge implements IWindowBridge {
  async getMetrics(): Promise<WindowMetrics> {
    if (!isTauriEnvironment()) {
      return {
        isBorderless: false,
        trafficLightsPadding: 0,
        titlebarHeight: 0,
        dragRegionEnabled: false,
      };
    }
    const isMac = typeof navigator !== 'undefined' && navigator.userAgent.includes('Macintosh');
    return {
      isBorderless: true,
      trafficLightsPadding: isMac ? 28 : 0,
      titlebarHeight: 36,
      dragRegionEnabled: true,
    };
  }
}

class TauriTrayBridge implements ITrayBridge {
  onTrayEvent(handler: (event: { type: string; payload?: unknown }) => void): () => void {
    if (!isTauriEnvironment() || typeof window === 'undefined' || !window.__TAURI__?.event) {
      return () => {};
    }
    let unlisten: (() => void) | null = null;
    window.__TAURI__.event
      .listen('tray_event', (e: { payload: unknown }) => {
        const payload = e.payload as { type?: string; payload?: unknown } | string;
        if (typeof payload === 'string') {
          handler({ type: payload });
        } else if (payload && typeof payload === 'object') {
          handler({ type: payload.type || 'unknown', payload: payload.payload });
        }
      })
      .then((fn: () => void) => {
        unlisten = fn;
      })
      .catch(() => {});

    return () => {
      if (unlisten) {
        unlisten();
      }
    };
  }
}

class TauriShellBridge implements IShellBridge {
  /**
   * Single channel: resolves false when the shell plugin refuses or fails to open the URL, and never retries through
   * window.open. The external link policy routes window.open back into this method, so a fallback would loop while
   * the plugin keeps refusing and would report the silently dropped window.open as a success.
   */
  async openExternalUrl(url: string): Promise<boolean> {
    if (!url || !isTauriEnvironment()) {
      return false;
    }
    try {
      const { open } = await import('@tauri-apps/plugin-shell');
      await open(url);
      return true;
    } catch (e) {
      console.warn('Failed to open external URL via shell plugin:', e);
      return false;
    }
  }

  async openFileDialog(options?: NativeOpenFileDialogOptions): Promise<string | string[] | null> {
    if (!isTauriEnvironment()) {
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
    } catch (e) {
      console.warn('Failed to open native file dialog:', e);
      return null;
    }
  }
}

class TauriAppshotBridge implements IAppshotBridge {
  listenAppshot(handler: (payload: { path: string; mimeType: string }) => void): () => void {
    if (!isTauriEnvironment() || typeof window === 'undefined' || !window.__TAURI__?.event) {
      return () => {};
    }
    let unlisten: (() => void) | null = null;
    window.__TAURI__.event
      .listen('appshot_trigger', (e: { payload: unknown }) => {
        const p = e.payload as { path?: string; mimeType?: string } | undefined;
        handler({
          path: p?.path || '',
          mimeType: p?.mimeType || 'image/png',
        });
      })
      .then((fn: () => void) => {
        unlisten = fn;
      })
      .catch(() => {});

    return () => {
      if (unlisten) {
        unlisten();
      }
    };
  }
}

class TauriNotificationBridge implements INotificationBridge {
  async show(payload: NativeNotificationPayload): Promise<boolean> {
    if (!isTauriEnvironment()) {
      if (typeof window !== 'undefined' && 'Notification' in window) {
        if (Notification.permission === 'granted') {
          new Notification(payload.title, { body: payload.body });
          return true;
        }
      }
      return false;
    }

    try {
      const { sendNotification, isPermissionGranted, requestPermission } =
        await import('@tauri-apps/plugin-notification');
      let granted = await isPermissionGranted();
      if (!granted) {
        const permission = await requestPermission();
        granted = permission === 'granted';
      }
      if (granted) {
        sendNotification({
          title: payload.title,
          body: payload.body,
        });
        return true;
      }
    } catch (e) {
      console.warn('Failed to send native notification via plugin:', e);
    }
    return false;
  }
}

export class TauriDesktopBridge implements IDesktopBridge {
  readonly isDesktop = true;
  readonly platform: DesktopPlatform;
  readonly capabilities: DesktopBridgeCapabilities;
  readonly window: IWindowBridge = new TauriWindowBridge();
  readonly tray: ITrayBridge = new TauriTrayBridge();
  readonly shell: IShellBridge = new TauriShellBridge();
  readonly appshot: IAppshotBridge = new TauriAppshotBridge();
  readonly notification: INotificationBridge = new TauriNotificationBridge();

  constructor() {
    this.platform = detectDesktopPlatform();
    this.capabilities = {
      hasNativeDialog: true,
      hasNativeTray: true,
      hasNativeNotification: true,
      hasNativeClipboard: typeof navigator !== 'undefined' && 'clipboard' in navigator,
      hasNativeGlobalShortcuts: true,
      hasNativeAppshot: true,
    };
  }

  getWindowControlsState(): DesktopWindowControlsState {
    return getDesktopWindowControlsState();
  }
}
