/**
 * [INPUT]
 * - types.ts: IDesktopBridge and IShellBridge
 *
 * [OUTPUT]
 * - WebFallbackDesktopBridge: Safe no-op and Web standard API implementations for pure web / cloud environments
 *
 * [POS]
 * Desktop bridge web fallback implementation. Guarantees zero exceptions and safe no-ops in browser environments.
 */

import type {
  DesktopPlatform,
  DesktopWindowControlsState,
  IDesktopBridge,
  IShellBridge,
  NativeOpenFileDialogOptions,
} from './types';

class WebFallbackShellBridge implements IShellBridge {
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

export class WebFallbackDesktopBridge implements IDesktopBridge {
  readonly isDesktop = false;
  readonly platform: DesktopPlatform = 'web';
  readonly shell: IShellBridge = new WebFallbackShellBridge();

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
