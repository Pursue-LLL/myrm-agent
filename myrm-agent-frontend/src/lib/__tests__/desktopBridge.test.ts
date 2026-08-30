import { describe, it, expect, vi, beforeEach } from 'vitest';
import { desktopBridge } from '../desktopBridge';

describe('desktopBridge', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__;
  });

  it('detects desktop environment accurately based on __TAURI__ presence', () => {
    expect(desktopBridge.isDesktop()).toBe(false);

    (window as unknown as { __TAURI__: { invoke: () => Promise<void> } }).__TAURI__ = {
      invoke: vi.fn(),
    };

    expect(desktopBridge.isDesktop()).toBe(true);
  });

  it('detects macOS user agent safely without throwing', () => {
    const isMac = desktopBridge.isMacOS();
    expect(typeof isMac).toBe('boolean');
  });

  it('falls back to window.open when openExternal is invoked outside desktop environment', async () => {
    const windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    const result = await desktopBridge.openExternal('https://myrmagent.ai');

    expect(result).toBe(true);
    expect(windowOpenSpy).toHaveBeenCalledWith('https://myrmagent.ai', '_blank', 'noopener,noreferrer');
  });

  it('returns false for empty URL in openExternal', async () => {
    const result = await desktopBridge.openExternal('');
    expect(result).toBe(false);
  });

  it('returns fallback version outside desktop environment', async () => {
    const version = await desktopBridge.getAppVersion();
    expect(typeof version).toBe('string');
    expect(version.length).toBeGreaterThan(0);
  });

  it('returns false when showItemInFolder is called in non-desktop mode', async () => {
    const result = await desktopBridge.showItemInFolder('/path/to/file');
    expect(result).toBe(false);
  });

  it('safe window controls do not throw outside desktop environment', async () => {
    await expect(desktopBridge.minimizeWindow()).resolves.toBeUndefined();
    await expect(desktopBridge.toggleMaximizeWindow()).resolves.toBeUndefined();
    await expect(desktopBridge.closeWindow()).resolves.toBeUndefined();
  });
});
