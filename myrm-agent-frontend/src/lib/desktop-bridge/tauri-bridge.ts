/**
 * [INPUT]
 * - types.ts: IDesktopBridge and sub-bridge interfaces
 * - @/lib/tauri: invokeTauriCommand, isTauriEnvironment
 *
 * [OUTPUT]
 * - TauriDesktopBridge: Native IPC bridge implementation for Tauri desktop application
 *
 * [POS]
 * Desktop bridge Tauri implementation. Connects typed frontend calls to Tauri Rust IPC.
 */

import { invokeTauriCommand, isTauriEnvironment } from '@/lib/tauri';
import { detectDesktopPlatform, getDesktopWindowControlsState } from './bridge';
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

  async minimize(): Promise<void> {
    if (!isTauriEnvironment()) return;
    try {
      await invokeTauriCommand('minimize_window');
    } catch (e) {
      console.warn('Failed to minimize window:', e);
    }
  }

  async maximize(): Promise<void> {
    if (!isTauriEnvironment()) return;
    try {
      await invokeTauriCommand('maximize_window');
    } catch (e) {
      console.warn('Failed to maximize window:', e);
    }
  }

  async toggleMaximize(): Promise<void> {
    if (!isTauriEnvironment()) return;
    try {
      await invokeTauriCommand('toggle_maximize_window');
    } catch (e) {
      console.warn('Failed to toggle maximize window:', e);
    }
  }

  async close(): Promise<void> {
    if (!isTauriEnvironment()) return;
    try {
      await invokeTauriCommand('close_window');
    } catch (e) {
      console.warn('Failed to close window:', e);
    }
  }

  async isMaximized(): Promise<boolean> {
    if (!isTauriEnvironment()) return false;
    try {
      return await invokeTauriCommand<boolean>('is_window_maximized');
    } catch {
      return false;
    }
  }

  async startDragging(): Promise<void> {
    if (!isTauriEnvironment()) return;
    try {
      await invokeTauriCommand('start_dragging');
    } catch (e) {
      console.warn('Failed to start dragging:', e);
    }
  }
}

class TauriTrayBridge implements ITrayBridge {
  async updateStatus(status: TrayStatusPayload): Promise<void> {
    if (!isTauriEnvironment()) return;
    try {
      await invokeTauriCommand('update_tray_status', {
        liveness: status.liveness,
        activeTasksCount: status.activeTasksCount,
        tokens: status.usageSummary?.tokens ?? 0,
        costUsd: status.usageSummary?.costUsd ?? 0,
        tooltipText: status.tooltipText,
      });
    } catch (e) {
      console.warn('Failed to update tray status:', e);
    }
  }

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
      if (unlisten) unlisten();
    };
  }
}

class TauriShellBridge implements IShellBridge {
  async openLocalFolder(path: string): Promise<boolean> {
    if (!isTauriEnvironment() || !path) return false;
    try {
      return await invokeTauriCommand<boolean>('open_folder', { path });
    } catch (e) {
      console.warn('Failed to open folder:', e);
      return false;
    }
  }

  async showInFileManager(path: string): Promise<boolean> {
    if (!isTauriEnvironment() || !path) return false;
    try {
      return await invokeTauriCommand<boolean>('show_in_file_manager', { path });
    } catch (e) {
      console.warn('Failed to show in file manager:', e);
      return false;
    }
  }

  async openExternalUrl(url: string): Promise<boolean> {
    if (!url) return false;
    if (!isTauriEnvironment()) {
      if (typeof window !== 'undefined') {
        window.open(url, '_blank', 'noopener,noreferrer');
        return true;
      }
      return false;
    }
    try {
      return await invokeTauriCommand<boolean>('open_external_url', { url });
    } catch {
      if (typeof window !== 'undefined') {
        window.open(url, '_blank', 'noopener,noreferrer');
        return true;
      }
      return false;
    }
  }

  async openFileDialog(options?: NativeOpenFileDialogOptions): Promise<string | string[] | null> {
    if (!isTauriEnvironment()) return null;
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

class TauriPowerBridge implements IPowerBridge {
  async acquireLock(reason: string): Promise<string | null> {
    if (!isTauriEnvironment()) return null;
    try {
      const lockId = await invokeTauriCommand<string>('acquire_power_lock', { reason });
      return lockId || 'lock-acquired';
    } catch (e) {
      console.warn('Failed to acquire power lock:', e);
      return null;
    }
  }

  async releaseLock(lockId: string): Promise<boolean> {
    if (!isTauriEnvironment()) return false;
    try {
      return await invokeTauriCommand<boolean>('release_power_lock', { lockId });
    } catch (e) {
      console.warn('Failed to release power lock:', e);
      return false;
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
      if (unlisten) unlisten();
    };
  }

  async captureScreen(): Promise<{ base64: string; mimeType: string } | null> {
    if (!isTauriEnvironment()) return null;
    try {
      const base64 = await invokeTauriCommand<string>('capture_screen');
      if (!base64) return null;
      return { base64, mimeType: 'image/png' };
    } catch (e) {
      console.warn('Failed to capture screen:', e);
      return null;
    }
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
  readonly power: IPowerBridge = new TauriPowerBridge();
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
      hasNativePowerLock: true,
      hasNativeAppshot: true,
    };
  }

  getWindowControlsState(): DesktopWindowControlsState {
    return getDesktopWindowControlsState();
  }
}
