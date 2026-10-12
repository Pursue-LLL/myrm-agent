/**
 * [INPUT]: @/lib/desktopBridge::desktopBridge
 * [OUTPUT]: Unit tests for desktopBridge
 * [POS]: 前端桌面桥接门面单元测试，覆盖 isDesktop, isMacOS, openExternal, clipboard, getAppVersion 等。
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { desktopBridge } from '../desktopBridge';
import * as tauriModule from '@/lib/tauri';

describe('desktopBridge', () => {
  const originalWindow = globalThis.window;

  beforeEach(() => {
    vi.restoreAllMocks();
    if (typeof globalThis.window === 'undefined') {
      vi.stubGlobal('window', {
        open: vi.fn(() => null),
      });
    }
  });

  afterEach(() => {
    vi.restoreAllMocks();
    if (originalWindow === undefined) {
      // @ts-expect-error vitest jsdom cleanup
      delete globalThis.window;
    }
  });

  it('delegates isDesktop to isTauriEnvironment', () => {
    const isTauriSpy = vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
    expect(desktopBridge.isDesktop()).toBe(false);

    isTauriSpy.mockReturnValue(true);
    expect(desktopBridge.isDesktop()).toBe(true);
  });

  it('handles openExternal with browser fallback when not in desktop', async () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
    const windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    const result = await desktopBridge.openExternal('https://example.com');
    expect(result).toBe(true);
    expect(windowOpenSpy).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer');
  });

  it('returns false for empty url in openExternal', async () => {
    const result = await desktopBridge.openExternal('');
    expect(result).toBe(false);
  });

  it('provides default app version in web mode', async () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
    const version = await desktopBridge.getAppVersion();
    expect(typeof version).toBe('string');
    expect(version.length).toBeGreaterThan(0);
  });

  it('writes to clipboard using navigator.clipboard', async () => {
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextSpy,
      },
    });

    const success = await desktopBridge.writeClipboard('test text');
    expect(success).toBe(true);
    expect(writeTextSpy).toHaveBeenCalledWith('test text');
  });
});
