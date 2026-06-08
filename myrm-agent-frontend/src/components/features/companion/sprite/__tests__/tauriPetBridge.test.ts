import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { hidePetOverlay, isTauriEnv, setPetOverlayRow, showPetOverlay } from '../tauriPetBridge';

describe('tauriPetBridge', () => {
  const originalWindow = globalThis.window;

  afterEach(() => {
    if (originalWindow) {
      delete (window as any).__TAURI__;
    }
  });

  describe('isTauriEnv', () => {
    it('returns false when __TAURI__ is not defined', () => {
      delete (window as any).__TAURI__;
      expect(isTauriEnv()).toBe(false);
    });

    it('returns true when __TAURI__ is defined', () => {
      (window as any).__TAURI__ = { core: { invoke: vi.fn() } };
      expect(isTauriEnv()).toBe(true);
    });
  });

  describe('showPetOverlay', () => {
    it('returns null when not in Tauri env', async () => {
      delete (window as any).__TAURI__;
      const result = await showPetOverlay('https://example.com/sheet.webp');
      expect(result).toBeNull();
    });

    it('invokes show_pet_overlay when in Tauri env', async () => {
      const mockInvoke = vi.fn().mockResolvedValue(undefined);
      (window as any).__TAURI__ = { core: { invoke: mockInvoke } };

      await showPetOverlay('https://example.com/sheet.webp', 64, 2);

      expect(mockInvoke).toHaveBeenCalledWith('show_pet_overlay', {
        payload: { sheetUrl: 'https://example.com/sheet.webp', size: 64, initialRow: 2 },
      });
    });

    it('uses default size and row when not provided', async () => {
      const mockInvoke = vi.fn().mockResolvedValue(undefined);
      (window as any).__TAURI__ = { core: { invoke: mockInvoke } };

      await showPetOverlay('https://example.com/sheet.webp');

      expect(mockInvoke).toHaveBeenCalledWith('show_pet_overlay', {
        payload: { sheetUrl: 'https://example.com/sheet.webp', size: 128, initialRow: 0 },
      });
    });

    it('catches and returns null on invoke failure', async () => {
      const mockInvoke = vi.fn().mockRejectedValue(new Error('IPC failed'));
      (window as any).__TAURI__ = { core: { invoke: mockInvoke } };
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      const result = await showPetOverlay('url');
      expect(result).toBeNull();
      expect(consoleSpy).toHaveBeenCalled();

      consoleSpy.mockRestore();
    });
  });

  describe('hidePetOverlay', () => {
    it('returns null when not in Tauri env', async () => {
      delete (window as any).__TAURI__;
      const result = await hidePetOverlay();
      expect(result).toBeNull();
    });

    it('invokes hide_pet_overlay when in Tauri env', async () => {
      const mockInvoke = vi.fn().mockResolvedValue(undefined);
      (window as any).__TAURI__ = { core: { invoke: mockInvoke } };

      await hidePetOverlay();
      expect(mockInvoke).toHaveBeenCalledWith('hide_pet_overlay', undefined);
    });
  });

  describe('setPetOverlayRow', () => {
    it('returns null when not in Tauri env', async () => {
      delete (window as any).__TAURI__;
      const result = await setPetOverlayRow(3);
      expect(result).toBeNull();
    });

    it('invokes pet_overlay_set_row with correct args', async () => {
      const mockInvoke = vi.fn().mockResolvedValue(undefined);
      (window as any).__TAURI__ = { core: { invoke: mockInvoke } };

      await setPetOverlayRow(5);
      expect(mockInvoke).toHaveBeenCalledWith('pet_overlay_set_row', { row: 5 });
    });
  });
});
