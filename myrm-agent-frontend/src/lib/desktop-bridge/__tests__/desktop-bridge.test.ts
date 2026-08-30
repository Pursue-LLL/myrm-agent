import { describe, expect, it, vi } from 'vitest';
import {
  createDesktopBridge,
  defaultDesktopBridge,
  desktopBridge,
  detectDesktopPlatform,
  getDesktopWindowControlsState,
  TauriDesktopBridge,
  WebFallbackDesktopBridge,
} from '../index';

describe('Desktop Bridge Core Protocol', () => {
  it('detects platform correctly in browser environment', () => {
    const platform = detectDesktopPlatform();
    expect(platform).toBe('web');
  });

  it('calculates window controls state for web environment', () => {
    const state = getDesktopWindowControlsState();
    expect(state).toEqual({
      controlsInsetTop: 0,
      controlsInsetLeft: 0,
      platform: 'web',
      isDesktop: false,
      isOverlayTitlebar: false,
    });
  });

  it('creates web fallback bridge when not in Tauri environment', () => {
    const bridge = createDesktopBridge();
    expect(bridge.isDesktop).toBe(false);
    expect(bridge.platform).toBe('web');
    expect(bridge).toBeInstanceOf(WebFallbackDesktopBridge);
  });

  it('exports default singleton bridge instances', () => {
    expect(defaultDesktopBridge).toBeDefined();
    expect(desktopBridge).toBeDefined();
    expect(defaultDesktopBridge.isDesktop).toBe(false);
  });

  describe('WebFallbackDesktopBridge', () => {
    const bridge = new WebFallbackDesktopBridge();

    it('returns default zeroed metrics for window bridge', async () => {
      const metrics = await bridge.window.getMetrics();
      expect(metrics).toEqual({
        isBorderless: false,
        trafficLightsPadding: 0,
        titlebarHeight: 0,
        dragRegionEnabled: false,
      });
    });

    it('handles window operations as safe no-ops', async () => {
      await expect(bridge.window.minimize()).resolves.toBeUndefined();
      await expect(bridge.window.maximize()).resolves.toBeUndefined();
      await expect(bridge.window.toggleMaximize()).resolves.toBeUndefined();
      await expect(bridge.window.close()).resolves.toBeUndefined();
      await expect(bridge.window.startDragging()).resolves.toBeUndefined();
      expect(await bridge.window.isMaximized()).toBe(false);
    });

    it('handles tray bridge operations safely', async () => {
      await expect(
        bridge.tray.updateStatus({
          liveness: 'ready',
          activeTasksCount: 0,
        }),
      ).resolves.toBeUndefined();

      const unsubscribe = bridge.tray.onTrayEvent(() => {});
      expect(typeof unsubscribe).toBe('function');
      expect(() => unsubscribe()).not.toThrow();
    });

    it('handles shell bridge operations safely', async () => {
      expect(await bridge.shell.openLocalFolder('/tmp')).toBe(false);
      expect(await bridge.shell.showInFileManager('/tmp')).toBe(false);
      expect(await bridge.shell.openFileDialog()).toBeNull();
    });

    it('handles power and appshot bridges safely', async () => {
      expect(await bridge.power.acquireLock('task')).toBeNull();
      expect(await bridge.power.releaseLock('lock-id')).toBe(false);

      const unlisten = bridge.appshot.listenAppshot(() => {});
      expect(typeof unlisten).toBe('function');
      expect(await bridge.appshot.captureScreen()).toBeNull();
    });
  });

  describe('TauriDesktopBridge', () => {
    it('instantiates cleanly and provides capabilities', () => {
      const tauriBridge = new TauriDesktopBridge();
      expect(tauriBridge.isDesktop).toBe(true);
      expect(tauriBridge.capabilities.hasNativeDialog).toBe(true);
      expect(tauriBridge.capabilities.hasNativeTray).toBe(true);
      expect(tauriBridge.capabilities.hasNativePowerLock).toBe(true);
      expect(tauriBridge.capabilities.hasNativeAppshot).toBe(true);
    });
  });
});
