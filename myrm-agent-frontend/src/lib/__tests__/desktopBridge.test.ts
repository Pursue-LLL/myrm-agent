/**
 * [INPUT]: @/lib/desktopBridge::desktopBridge
 * [OUTPUT]: Unit tests for desktopBridge
 * [POS]: 前端桌面桥接门面单元测试，覆盖 isDesktop, isMacOS, isWindows, openExternal, openDirectoryPicker。
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { desktopBridge } from '../desktopBridge';
import { desktopBridge as coreDesktopBridge } from '@/lib/desktop-bridge';
import * as platformModule from '@/lib/desktop-bridge/platform-detection';
import * as tauriModule from '@/lib/tauri';

describe('desktopBridge', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('delegates isDesktop to isTauriEnvironment', () => {
    const isTauriSpy = vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
    expect(desktopBridge.isDesktop()).toBe(false);

    isTauriSpy.mockReturnValue(true);
    expect(desktopBridge.isDesktop()).toBe(true);
  });

  it('reports macOS and Windows only inside the desktop runtime', () => {
    const isTauriSpy = vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
    const platformSpy = vi.spyOn(platformModule, 'detectDesktopPlatform').mockReturnValue('macos');
    expect(desktopBridge.isMacOS()).toBe(true);
    expect(desktopBridge.isWindows()).toBe(false);

    platformSpy.mockReturnValue('windows');
    expect(desktopBridge.isMacOS()).toBe(false);
    expect(desktopBridge.isWindows()).toBe(true);

    isTauriSpy.mockReturnValue(false);
    expect(desktopBridge.isMacOS()).toBe(false);
    expect(desktopBridge.isWindows()).toBe(false);
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

  describe('openDirectoryPicker', () => {
    it('returns null without opening a dialog outside the desktop runtime', async () => {
      vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
      const openFileDialog = vi.spyOn(coreDesktopBridge.shell, 'openFileDialog');

      await expect(desktopBridge.openDirectoryPicker()).resolves.toBeNull();
      expect(openFileDialog).not.toHaveBeenCalled();
    });

    it('asks the native dialog for a single directory and passes the options through', async () => {
      vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
      const openFileDialog = vi.spyOn(coreDesktopBridge.shell, 'openFileDialog').mockResolvedValue('/work/project');

      await expect(desktopBridge.openDirectoryPicker({ title: 'Pick', defaultPath: '/work' })).resolves.toBe(
        '/work/project',
      );
      expect(openFileDialog).toHaveBeenCalledExactlyOnceWith({
        directory: true,
        multiple: false,
        title: 'Pick',
        defaultPath: '/work',
      });
    });

    it.each([
      ['the first entry of a list', ['/a', '/b'], '/a'],
      ['a blank string', '   ', null],
      ['an empty list', [], null],
      ['a cancelled dialog', null, null],
    ])('normalizes %s', async (_label, selection, expected) => {
      vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
      vi.spyOn(coreDesktopBridge.shell, 'openFileDialog').mockResolvedValue(selection);

      await expect(desktopBridge.openDirectoryPicker()).resolves.toBe(expected);
    });
  });
});
