/**
 * [INPUT]
 * - types.ts: IDesktopBridge and sub-bridge interfaces
 *
 * [OUTPUT]
 * - WebFallbackDesktopBridge: Safe no-op and Web standard API implementations for pure web / cloud environments
 *
 * [POS]
 * Desktop bridge web fallback implementation. Guarantees zero exceptions and safe no-ops in browser environments.
 */

import type {
  DesktopBridgeCapabilities,
  DesktopPlatform,
  DesktopWindowControlsState,
  IAppshotBridge,
  IDesktopBridge,
  INotificationBridge,
  IPowerBridge,
  IShellBridge,
  ITrayBridge,
  IWindowBridge,
  NativeNotificationPayload,
  NativeOpenFileDialogOptions,
  TrayStatusPayload,
  WindowMetrics,
} from './types';

class WebFallbackWindowBridge implements IWindowBridge {
  async getMetrics(): Promise<WindowMetrics> {
    return {
      isBorderless: false,
      trafficLightsPadding: 0,
      titlebarHeight: 0,
      dragRegionEnabled: false,
    };
  }

  async minimize(): Promise<void> {
    // No-op in browser
  }

  async maximize(): Promise<void> {
    // No-op in browser
  }

  async toggleMaximize(): Promise<void> {
    // No-op in browser
  }

  async close(): Promise<void> {
    // No-op in browser
  }

  async isMaximized(): Promise<boolean> {
    return false;
  }

  async startDragging(): Promise<void> {
    // No-op in browser
  }
}

class WebFallbackTrayBridge implements ITrayBridge {
  async updateStatus(_status: TrayStatusPayload): Promise<void> {
    // No-op in browser
  }

  onTrayEvent(_handler: (event: { type: string; payload?: unknown }) => void): () => void {
    return () => {};
  }
}

class WebFallbackShellBridge implements IShellBridge {
  async openLocalFolder(_path: string): Promise<boolean> {
    return false;
  }

  async showInFileManager(_path: string): Promise<boolean> {
    return false;
  }

  async openExternalUrl(url: string): Promise<boolean> {
    if (typeof window !== 'undefined' && url) {
      window.open(url, '_blank', 'noopener,noreferrer');
      return true;
    }
    return false;
  }

  async openFileDialog(_options?: NativeOpenFileDialogOptions): Promise<string | string[] | null> {
    return null;
  }
}

class WebFallbackPowerBridge implements IPowerBridge {
  async acquireLock(_reason: string): Promise<string | null> {
    return null;
  }

  async releaseLock(_lockId: string): Promise<boolean> {
    return false;
  }
}

class WebFallbackAppshotBridge implements IAppshotBridge {
  listenAppshot(_handler: (payload: { path: string; mimeType: string }) => void): () => void {
    return () => {};
  }

  async captureScreen(): Promise<{ base64: string; mimeType: string } | null> {
    return null;
  }
}

class WebFallbackNotificationBridge implements INotificationBridge {
  async show(payload: NativeNotificationPayload): Promise<boolean> {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      try {
        if (Notification.permission === 'granted') {
          new Notification(payload.title, { body: payload.body });
          return true;
        }
        if (Notification.permission !== 'denied') {
          const perm = await Notification.requestPermission();
          if (perm === 'granted') {
            new Notification(payload.title, { body: payload.body });
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

export class WebFallbackDesktopBridge implements IDesktopBridge {
  readonly isDesktop = false;
  readonly platform: DesktopPlatform = 'web';
  readonly capabilities: DesktopBridgeCapabilities = {
    hasNativeDialog: false,
    hasNativeTray: false,
    hasNativeNotification: typeof window !== 'undefined' && 'Notification' in window,
    hasNativeClipboard: typeof navigator !== 'undefined' && 'clipboard' in navigator,
    hasNativeGlobalShortcuts: false,
    hasNativePowerLock: false,
    hasNativeAppshot: false,
  };

  readonly window: IWindowBridge = new WebFallbackWindowBridge();
  readonly tray: ITrayBridge = new WebFallbackTrayBridge();
  readonly shell: IShellBridge = new WebFallbackShellBridge();
  readonly power: IPowerBridge = new WebFallbackPowerBridge();
  readonly appshot: IAppshotBridge = new WebFallbackAppshotBridge();
  readonly notification: INotificationBridge = new WebFallbackNotificationBridge();

  getWindowControlsState(): DesktopWindowControlsState {
    return {
      controlsInsetTop: 0,
      controlsInsetLeft: 0,
      platform: 'web',
      isDesktop: false,
      isOverlayTitlebar: false,
    };
  }
}
