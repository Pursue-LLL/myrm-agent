import { describe, it, expect, vi, beforeEach } from 'vitest';
import { desktopBridge } from '../desktopBridge';

describe('desktopBridge', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__;
  });

  it('detects desktop environment accurately', () => {
    expect(desktopBridge.isDesktop()).toBe(false);

    (window as unknown as { __TAURI__: unknown }).__TAURI__ = {};
    expect(desktopBridge.isDesktop()).toBe(true);
  });

  it('provides default app version in web mode', async () => {
    const version = await desktopBridge.getAppVersion();
    expect(version).toBeTruthy();
  });

  it('handles writeClipboard gracefully in web browser context', async () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });

    const result = await desktopBridge.writeClipboard('test text');
    expect(result).toBe(true);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('test text');
  });

  it('returns false for showItemInFolder in non-desktop environment without throwing', async () => {
    const result = await desktopBridge.showItemInFolder('/path/to/file');
    expect(result).toBe(false);
  });

  it('opens url using window.open in web environment', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    const result = await desktopBridge.openExternal('https://example.com');
    expect(result).toBe(true);
    expect(openSpy).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer');
  });
});
