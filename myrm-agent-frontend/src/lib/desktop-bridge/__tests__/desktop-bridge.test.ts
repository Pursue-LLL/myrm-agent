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
import * as tauriModule from '@/lib/tauri';
import {
  detectDesktopPlatform,
  getDesktopWindowControlsState,
  createDesktopBridge,
  WebFallbackDesktopBridge,
  TauriDesktopBridge,
} from '../index';

const shellOpen = vi.hoisted(() => vi.fn<(url: string) => Promise<void>>());

vi.mock('@tauri-apps/plugin-shell', () => ({ open: shellOpen }));

describe('Desktop Bridge Protocol', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    shellOpen.mockReset();
  });

  describe('WebFallbackDesktopBridge', () => {
    const bridge = new WebFallbackDesktopBridge();

    it('should report web platform and non-desktop state', () => {
      expect(bridge.isDesktop).toBe(false);
      expect(bridge.platform).toBe('web');
      expect(bridge.capabilities.hasNativeDialog).toBe(false);
      expect(bridge.capabilities.hasNativeTray).toBe(false);
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

    it('should handle tray, shell, and appshot safely without throwing', async () => {
      const unsub = bridge.tray.onTrayEvent(() => {});
      expect(typeof unsub).toBe('function');
      expect(unsub()).toBeUndefined();

      await expect(bridge.shell.openFileDialog()).resolves.toBeNull();

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
      expect(bridge.capabilities.hasNativeAppshot).toBe(true);
    });

    describe('shell.openExternalUrl', () => {
      const bridge = new TauriDesktopBridge();

      it('rejects an empty url without touching the shell plugin', async () => {
        await expect(bridge.shell.openExternalUrl('')).resolves.toBe(false);
        expect(shellOpen).not.toHaveBeenCalled();
      });

      it('opens the url through the official shell plugin inside the desktop runtime', async () => {
        vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
        shellOpen.mockResolvedValue(undefined);

        await expect(bridge.shell.openExternalUrl('https://example.com/docs')).resolves.toBe(true);
        expect(shellOpen).toHaveBeenCalledWith('https://example.com/docs');
      });

      it('falls back to the browser when the shell plugin rejects the url', async () => {
        vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
        vi.spyOn(console, 'warn').mockImplementation(() => {});
        shellOpen.mockRejectedValue(new Error('url not allowed'));
        const windowOpen = vi.spyOn(window, 'open').mockImplementation(() => null);

        await expect(bridge.shell.openExternalUrl('cursor://')).resolves.toBe(true);
        expect(windowOpen).toHaveBeenCalledWith('cursor://', '_blank', 'noopener,noreferrer');
      });

      it('skips the shell plugin outside the desktop runtime', async () => {
        vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
        const windowOpen = vi.spyOn(window, 'open').mockImplementation(() => null);

        await expect(bridge.shell.openExternalUrl('https://example.com')).resolves.toBe(true);
        expect(shellOpen).not.toHaveBeenCalled();
        expect(windowOpen).toHaveBeenCalledTimes(1);
      });
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
