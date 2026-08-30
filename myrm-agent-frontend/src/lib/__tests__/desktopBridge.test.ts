import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { desktopBridge } from '../desktopBridge';
import * as tauriLib from '../tauri';

describe('desktopBridge', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('isDesktop', () => {
    it('returns true when in Tauri environment', () => {
      vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(true);
      expect(desktopBridge.isDesktop()).toBe(true);
    });

    it('returns false when in browser environment', () => {
      vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(false);
      expect(desktopBridge.isDesktop()).toBe(false);
    });
  });

  describe('isMacOS', () => {
    it('detects macOS user agent correctly', () => {
      const originalUserAgent = navigator.userAgent;
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        configurable: true,
      });

      expect(desktopBridge.isMacOS()).toBe(true);

      Object.defineProperty(navigator, 'userAgent', {
        value: originalUserAgent,
        configurable: true,
      });
    });

    it('returns false on Windows user agent', () => {
      const originalUserAgent = navigator.userAgent;
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        configurable: true,
      });

      expect(desktopBridge.isMacOS()).toBe(false);

      Object.defineProperty(navigator, 'userAgent', {
        value: originalUserAgent,
        configurable: true,
      });
    });
  });

  describe('openExternal', () => {
    it('returns false on empty url', async () => {
      const res = await desktopBridge.openExternal('');
      expect(res).toBe(false);
    });

    it('opens window in browser fallback mode', async () => {
      vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(false);
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

      const res = await desktopBridge.openExternal('https://example.com');
      expect(res).toBe(true);
      expect(openSpy).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer');
    });
  });

  describe('getAppVersion', () => {
    it('returns default version in browser environment', async () => {
      vi.spyOn(tauriLib, 'isTauriEnvironment').mockReturnValue(false);
      const ver = await desktopBridge.getAppVersion();
      expect(ver).toBeDefined();
      expect(typeof ver).toBe('string');
    });
  });

  describe('writeClipboard', () => {
    it('writes text to navigator.clipboard if available', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: writeTextMock },
        configurable: true,
      });

      const res = await desktopBridge.writeClipboard('test text');
      expect(res).toBe(true);
      expect(writeTextMock).toHaveBeenCalledWith('test text');
    });
  });
});
