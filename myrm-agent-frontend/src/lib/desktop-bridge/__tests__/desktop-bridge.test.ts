/**
 * [INPUT]
 * - @/lib/desktop-bridge
 *
 * [OUTPUT]
 * - Comprehensive unit tests for DesktopBridge protocol (Tauri vs WebFallback)
 *
 * [POS]
 * Tests interface compliance, zero-exception fallbacks, and window controls metric calculation.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  detectDesktopPlatform,
  getDesktopWindowControlsState,
  createDesktopBridge,
  WebFallbackDesktopBridge,
  TauriDesktopBridge,
} from './index';

describe('Desktop Bridge Protocol', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('WebFallbackDesktopBridge', () => {
    const bridge = new WebFallbackDesktopBridge();

    it('should report web platform and non-desktop state', () => {
      expect(bridge.isDesktop).toBe(false);
      expect(bridge.platform).toBe('web');
      expect(bridge.capabilities.hasNativeDialog).toBe(false);
      expect(bridge.capabilities.hasNativeTray).toBe(false);
      expect(bridge.capabilities.hasNativePowerLock).toBe(false);
      expect(bridge.capabilities.hasNativeAppshot).toBe(false);
    });

    it('should return zero window metrics without throwing', async () => {
      const metrics = await bridge.window.getMetrics();
      expect(metrics.isBorderless).toBe(false);
      expect(metrics.trafficLightsPadding).toBe(0);
      expect(metrics.titlebarHeight).toBe(0);
      expect(metrics.dragRegionEnabled).toBe(false);

      const controlsState = bridge.getWindowControlsState();
      expect(controlsState.controlsInsetTop).toBe(0);
      expect(controlsState.controlsInsetLeft).toBe(0);
      expect(controlsState.isDesktop).toBe(false);
      expect(controlsState.isOverlayTitlebar).toBe(false);
    });

    it('should handle window actions safely as no-ops', async () => {
      await expect(bridge.window.minimize()).resolves.toBeUndefined();
      await expect(bridge.window.maximize()).resolves.toBeUndefined();
      await expect(bridge.window.toggleMaximize()).resolves.toBeUndefined();
      await expect(bridge.window.close()).resolves.toBeUndefined();
      await expect(bridge.window.startDragging()).resolves.toBeUndefined();
      await expect(bridge.window.isMaximized()).resolves.toBe(false);
    });

    it('should handle tray, shell, and power safely without throwing', async () => {
      await expect(
        bridge.tray.updateStatus({ liveness: 'idle', activeTasksCount: 0 }),
      ).resolves.toBeUndefined();
      const unsub = bridge.tray.onTrayEvent(() => {});
      expect(typeof unsub).toBe('function');
      expect(unsub()).toBeUndefined();

      await expect(bridge.shell.openLocalFolder('/tmp')).resolves.toBe(false);
      await expect(bridge.shell.showInFileManager('/tmp/test.txt')).resolves.toBe(false);
      await expect(bridge.shell.openFileDialog()).resolves.toBeNull();

      await expect(bridge.power.acquireLock('test')).resolves.toBeNull();
      await expect(bridge.power.releaseLock('lock-id')).resolves.toBe(false);

      await expect(bridge.appshot.captureScreen()).resolves.toBeNull();
      const unsubAppshot = bridge.appshot.listenAppshot(() => {});
      expect(typeof unsubAppshot).toBe('function');
    });
  });

  describe('TauriDesktopBridge', () => {
    it('should instantiate with desktop flag true', () => {
      const bridge = new TauriDesktopBridge();
      expect(bridge.isDesktop).toBe(true);
      expect(bridge.capabilities.hasNativeDialog).toBe(true);
      expect(bridge.capabilities.hasNativeTray).toBe(true);
      expect(bridge.capabilities.hasNativePowerLock).toBe(true);
      expect(bridge.capabilities.hasNativeAppshot).toBe(true);
    });
  });

  describe('Platform Detection and Metrics', () => {
    it('should detect web platform in standard test environment', () => {
      expect(detectDesktopPlatform()).toBe('web');
      const controls = getDesktopWindowControlsState();
      expect(controls.isDesktop).toBe(false);
      expect(controls.controlsInsetTop).toBe(0);
      expect(controls.controlsInsetLeft).toBe(0);
    });

    it('should create WebFallbackDesktopBridge by default when outside Tauri', () => {
      const bridge = createDesktopBridge();
      expect(bridge.isDesktop).toBe(false);
      expect(bridge.platform).toBe('web');
    });
  });
});
