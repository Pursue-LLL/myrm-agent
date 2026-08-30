import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { desktopBridge } from '../desktopBridge';

describe('desktopBridge', () => {
  const originalNavigator = globalThis.navigator;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'navigator', {
      value: originalNavigator,
      writable: true,
      configurable: true,
    });
  });

  it('detects desktop environment correctly based on __TAURI__', () => {
    expect(desktopBridge.isDesktop()).toBe(false);

    (window as unknown as { __TAURI__: unknown }).__TAURI__ = {};
    expect(desktopBridge.isDesktop()).toBe(true);
    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__;
  });

  it('detects macOS user agent correctly', () => {
    Object.defineProperty(globalThis, 'navigator', {
      value: { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' },
      writable: true,
      configurable: true,
    });
    expect(desktopBridge.isMacOS()).toBe(true);

    Object.defineProperty(globalThis, 'navigator', {
      value: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' },
      writable: true,
      configurable: true,
    });
    expect(desktopBridge.isMacOS()).toBe(false);
  });

  it('provides safe fallback for openExternal on web', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    const result = await desktopBridge.openExternal('https://example.com');
    expect(result).toBe(true);
    expect(openSpy).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer');
  });

  it('handles empty url in openExternal gracefully', async () => {
    const result = await desktopBridge.openExternal('');
    expect(result).toBe(false);
  });

  it('handles showItemInFolder on non-desktop gracefully', async () => {
    const result = await desktopBridge.showItemInFolder('/path/to/folder');
    expect(result).toBe(false);
  });

  it('returns app version string safely', async () => {
    const version = await desktopBridge.getAppVersion();
    expect(typeof version).toBe('string');
    expect(version.length).toBeGreaterThan(0);
  });

  it('writes clipboard successfully when navigator.clipboard is available', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(globalThis, 'navigator', {
      value: { clipboard: { writeText } },
      writable: true,
      configurable: true,
    });

    const result = await desktopBridge.writeClipboard('hello world');
    expect(result).toBe(true);
    expect(writeText).toHaveBeenCalledWith('hello world');
  });
});
