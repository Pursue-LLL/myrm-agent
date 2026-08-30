import { describe, it, expect, vi, beforeEach } from 'vitest';
import { desktopBridge } from '../desktopBridge';
import * as tauriModule from '../tauri';

describe('desktopBridge', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('correctly reports non-desktop environment by default in test/browser', () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
    expect(desktopBridge.isDesktop()).toBe(false);
  });

  it('correctly reports desktop environment when running inside Tauri', () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
    expect(desktopBridge.isDesktop()).toBe(true);
  });

  it('handles showItemInFolder gracefully in non-desktop environments', async () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
    const result = await desktopBridge.showItemInFolder('/test/path');
    expect(result).toBe(false);
  });

  it('handles openExternal with fallback to window.open in web mode', async () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    const success = await desktopBridge.openExternal('https://example.com');
    expect(success).toBe(true);
    expect(openSpy).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer');
  });

  it('handles empty url in openExternal safely', async () => {
    const success = await desktopBridge.openExternal('');
    expect(success).toBe(false);
  });

  it('returns default fallback version in web mode', async () => {
    vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
    const version = await desktopBridge.getAppVersion();
    expect(typeof version).toBe('string');
    expect(version.length).toBeGreaterThan(0);
  });

  it('handles writeClipboard safely via navigator.clipboard', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    const success = await desktopBridge.writeClipboard('test copy');
    expect(success).toBe(true);
    expect(writeTextMock).toHaveBeenCalledWith('test copy');
  });
});
