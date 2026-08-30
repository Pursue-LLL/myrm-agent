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
import type {
  DesktopLivenessState,
  DesktopUsageSummary,
  IDesktopAppshotBridge,
  IDesktopBridge,
  IDesktopPowerBridge,
  IDesktopShellBridge,
  IDesktopTrayBridge,
  IDesktopWindowBridge,
} from './types';

class TauriWindowBridge implements IDesktopWindowBridge {
  async isBorderless(): Promise<boolean> {
    if (!isTauriEnvironment()) return false;
    try {
      return await invokeTauriCommand<boolean>('is_borderless_window');
    } catch {
      return true; // Default to true in Tauri macOS/Windows custom frame
    }
  }

  async getTrafficLightsOffset(): Promise<number> {
    if (!isTauriEnvironment()) return 0;
    if (typeof navigator !== 'undefined' && navigator.userAgent.includes('Macintosh')) {
      return 28; // Standard macOS traffic light height offset
    }
    return 0;
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

  async close(): Promise<void> {
    if (!isTauriEnvironment()) return;
    try {
      await invokeTauriCommand('close_window');
    } catch (e) {
      console.warn('Failed to close window:', e);
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

class TauriTrayBridge implements IDesktopTrayBridge {
  async setStatus(
    liveness: DesktopLivenessState,
    backgroundRunningCount: number,
    usage?: DesktopUsageSummary | null,
  ): Promise<void> {
    if (!isTauriEnvironment()) return;
    try {
      await invokeTauriCommand('update_tray_status', {
        liveness,
        backgroundRunningCount,
        tokens: usage?.tokens ?? 0,
        costUsd: usage?.costUsd ?? 0,
      });
    } catch (e) {
      console.warn('Failed to update tray status:', e);
    }
  }

  async onTrayEvent(handler: (event: string) => void): Promise<() => void> {
    if (!isTauriEnvironment() || typeof window === 'undefined' || !window.__TAURI__?.event) {
      return () => {};
    }
    try {
      return await window.__TAURI__.event.listen('tray_event', (e) => {
        handler(typeof e.payload === 'string' ? e.payload : JSON.stringify(e.payload));
      });
    } catch {
      return () => {};
    }
  }
}

class TauriShellBridge implements IDesktopShellBridge {
  async openLocalFolder(dirPath: string): Promise<boolean> {
    if (!isTauriEnvironment() || !dirPath) return false;
    try {
      return await invokeTauriCommand<boolean>('open_folder', { path: dirPath });
    } catch (e) {
      console.warn('Failed to open folder:', e);
      return false;
    }
  }

  async showInFileManager(targetPath: string): Promise<boolean> {
    if (!isTauriEnvironment() || !targetPath) return false;
    try {
      return await invokeTauriCommand<boolean>('show_in_file_manager', { path: targetPath });
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
}

class TauriPowerBridge implements IDesktopPowerBridge {
  async acquireLock(reason: string): Promise<boolean> {
    if (!isTauriEnvironment()) return false;
    try {
      return await invokeTauriCommand<boolean>('acquire_power_lock', { reason });
    } catch (e) {
      console.warn('Failed to acquire power lock:', e);
      return false;
    }
  }

  async releaseLock(reason: string): Promise<boolean> {
    if (!isTauriEnvironment()) return false;
    try {
      return await invokeTauriCommand<boolean>('release_power_lock', { reason });
    } catch (e) {
      console.warn('Failed to release power lock:', e);
      return false;
    }
  }
}

class TauriAppshotBridge implements IDesktopAppshotBridge {
  async listenAppshot(handler: (payload: unknown) => void): Promise<() => void> {
    if (!isTauriEnvironment() || typeof window === 'undefined' || !window.__TAURI__?.event) {
      return () => {};
    }
    try {
      return await window.__TAURI__.event.listen('appshot_trigger', (e) => {
        handler(e.payload);
      });
    } catch {
      return () => {};
    }
  }

  async captureScreen(): Promise<string | null> {
    if (!isTauriEnvironment()) return null;
    try {
      return await invokeTauriCommand<string>('capture_screen');
    } catch (e) {
      console.warn('Failed to capture screen:', e);
      return null;
    }
  }
}

export class TauriDesktopBridge implements IDesktopBridge {
  readonly isTauri = true;
  readonly window = new TauriWindowBridge();
  readonly tray = new TauriTrayBridge();
  readonly shell = new TauriShellBridge();
  readonly power = new TauriPowerBridge();
  readonly appshot = new TauriAppshotBridge();
}
