/**
 * [INPUT]
 * - @/lib/desktop-bridge
 *
 * [OUTPUT]
 * - Comprehensive unit tests for DesktopBridge protocol (Tauri vs WebFallback)
 *
 * [POS]
 * Tests interface compliance, the single-channel external open, zero-exception fallbacks, and platform detection.
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
    });

    it('should report empty window controls without throwing', () => {
      const controlsState = bridge.getWindowControlsState();
      expect(controlsState.controlsInsetTop).toBe(0);
      expect(controlsState.controlsInsetLeft).toBe(0);
      expect(controlsState.isDesktop).toBe(false);
      expect(controlsState.isOverlayTitlebar).toBe(false);
    });

    it('should open no file dialog without throwing', async () => {
      await expect(bridge.shell.openFileDialog()).resolves.toBeNull();
    });
  });

  describe('TauriDesktopBridge', () => {
    it('should instantiate with desktop flag true and the detected platform', () => {
      const bridge = new TauriDesktopBridge();
      expect(bridge.isDesktop).toBe(true);
      expect(bridge.platform).toBe(detectDesktopPlatform());
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

      it('reports a refused open as false without retrying through window.open', async () => {
        vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
        const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
        const refusal = new Error('url not allowed');
        shellOpen.mockRejectedValue(refusal);
        const windowOpen = vi.spyOn(window, 'open').mockImplementation(() => null);

        await expect(bridge.shell.openExternalUrl('ftp://example.com/readme')).resolves.toBe(false);
        expect(shellOpen).toHaveBeenCalledTimes(1);
        expect(windowOpen).not.toHaveBeenCalled();
        expect(warn).toHaveBeenCalledWith('Failed to open external URL via shell plugin:', refusal);
      });

      it('does nothing outside the desktop runtime', async () => {
        vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
        const windowOpen = vi.spyOn(window, 'open').mockImplementation(() => null);

        await expect(bridge.shell.openExternalUrl('https://example.com')).resolves.toBe(false);
        expect(shellOpen).not.toHaveBeenCalled();
        expect(windowOpen).not.toHaveBeenCalled();
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
