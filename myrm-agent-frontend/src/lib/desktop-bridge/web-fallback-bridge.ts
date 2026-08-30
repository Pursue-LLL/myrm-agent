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
  IDesktopAppshotBridge,
  IDesktopBridge,
  IDesktopPowerBridge,
  IDesktopShellBridge,
  IDesktopTrayBridge,
  IDesktopWindowBridge,
} from './types';

class WebFallbackWindowBridge implements IDesktopWindowBridge {
  async isBorderless(): Promise<boolean> {
    return false;
  }
  async getTrafficLightsOffset(): Promise<number> {
    return 0;
  }
  async minimize(): Promise<void> {
    // No-op in browser
  }
  async maximize(): Promise<void> {
    // No-op in browser
  }
  async close(): Promise<void> {
    // No-op in browser
  }
  async startDragging(): Promise<void> {
    // No-op in browser
  }
}

class WebFallbackTrayBridge implements IDesktopTrayBridge {
  async setStatus(): Promise<void> {
    // No-op in browser
  }
  async onTrayEvent(): Promise<() => void> {
    return () => {};
  }
}

class WebFallbackShellBridge implements IDesktopShellBridge {
  async openLocalFolder(): Promise<boolean> {
    return false;
  }
  async showInFileManager(): Promise<boolean> {
    return false;
  }
  async openExternalUrl(url: string): Promise<boolean> {
    if (typeof window !== 'undefined' && url) {
      window.open(url, '_blank', 'noopener,noreferrer');
      return true;
    }
    return false;
  }
}

class WebFallbackPowerBridge implements IDesktopPowerBridge {
  async acquireLock(): Promise<boolean> {
    return false;
  }
  async releaseLock(): Promise<boolean> {
    return false;
  }
}

class WebFallbackAppshotBridge implements IDesktopAppshotBridge {
  async listenAppshot(): Promise<() => void> {
    return () => {};
  }
  async captureScreen(): Promise<string | null> {
    return null;
  }
}

export class WebFallbackDesktopBridge implements IDesktopBridge {
  readonly isTauri = false;
  readonly window = new WebFallbackWindowBridge();
  readonly tray = new WebFallbackTrayBridge();
  readonly shell = new WebFallbackShellBridge();
  readonly power = new WebFallbackPowerBridge();
  readonly appshot = new WebFallbackAppshotBridge();
}
