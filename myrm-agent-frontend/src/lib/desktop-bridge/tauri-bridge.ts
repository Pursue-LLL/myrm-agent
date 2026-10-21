/**
 * [INPUT]
 * - types.ts: IDesktopBridge and IShellBridge
 * - @/lib/tauri: isTauriEnvironment
 * - @tauri-apps/plugin-shell / plugin-dialog: official plugins, dynamically imported
 * - ./platform-detection: detectDesktopPlatform, getDesktopWindowControlsState
 *
 * [OUTPUT]
 * - TauriDesktopBridge: Native bridge implementation for Tauri desktop application
 *
 * [POS]
 * Desktop bridge Tauri implementation. Connects typed frontend calls to official Tauri plugins.
 */

import { isTauriEnvironment } from '@/lib/tauri';
import { detectDesktopPlatform, getDesktopWindowControlsState } from './platform-detection';
import type {
  DesktopPlatform,
  DesktopWindowControlsState,
  IDesktopBridge,
  IShellBridge,
  NativeOpenFileDialogOptions,
} from './types';

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

export class TauriDesktopBridge implements IDesktopBridge {
  readonly isDesktop = true;
  readonly platform: DesktopPlatform = detectDesktopPlatform();
  readonly shell: IShellBridge = new TauriShellBridge();

  getWindowControlsState(): DesktopWindowControlsState {
    return getDesktopWindowControlsState();
  }
}
