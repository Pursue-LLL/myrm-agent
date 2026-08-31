import { describe, it, expect, vi, beforeEach } from 'vitest';
import { desktopBridge } from '../desktopBridge';
import * as tauriLib from '../tauri';

describe('desktopBridge', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('correctly reports non-desktop environment by default', () => {
    vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(false);
    expect(desktopBridge.isDesktop()).toBe(false);
  });

  it('correctly reports desktop environment when in Tauri', () => {
    vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(true);
    expect(desktopBridge.isDesktop()).toBe(true);
  });

  it('falls back gracefully on non-desktop for showItemInFolder', async () => {
    vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(false);
    const result = await desktopBridge.showItemInFolder('/test/path');
    expect(result).toBe(false);
  });

  it('falls back to window.open for openExternal on web', async () => {
    vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(false);
    const windowOpenSpy = vi.fn();
    window.open = windowOpenSpy;

    const result = await desktopBridge.openExternal('https://example.com');
    expect(result).toBe(true);
    expect(windowOpenSpy).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer');
  });

  it('returns default version string when not in desktop', async () => {
    vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(false);
    const version = await desktopBridge.getAppVersion();
    expect(typeof version).toBe('string');
    expect(version.length).toBeGreaterThan(0);
  });

  it('safely handles window minimization on web without throwing', async () => {
    vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(false);
    await expect(desktopBridge.minimizeWindow()).resolves.toBeUndefined();
  });

  it('safely handles window close on web without throwing', async () => {
    vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(false);
    await expect(desktopBridge.closeWindow()).resolves.toBeUndefined();
  });
});
