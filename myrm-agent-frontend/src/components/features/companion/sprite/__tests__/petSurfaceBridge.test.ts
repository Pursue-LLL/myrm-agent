import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: vi.fn(() => true),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}));

vi.mock('@tauri-apps/api/event', () => ({
  emitTo: vi.fn(),
  listen: vi.fn(),
}));

import { isTauriEnvironment } from '@/lib/tauri';
import { invoke } from '@tauri-apps/api/core';
import { emitTo } from '@tauri-apps/api/event';

import { PetState } from '../PetStateMachine';
import { emitPetSurfaceState, hidePetSurface, isTauriEnv, showPetSurface } from '../petSurfaceBridge';

describe('petSurfaceBridge', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('isTauriEnv delegates to isTauriEnvironment', () => {
    vi.mocked(isTauriEnvironment).mockReturnValue(false);
    expect(isTauriEnv()).toBe(false);
  });

  it('showPetSurface invokes show_pet_surface with bounds', async () => {
    vi.mocked(isTauriEnvironment).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue(undefined);

    await showPetSurface({ x: 10, y: 20, width: 64, height: 112 });

    expect(invoke).toHaveBeenCalledWith('show_pet_surface', {
      payload: { x: 10, y: 20, width: 64, height: 112 },
    });
  });

  it('hidePetSurface invokes hide_pet_surface', async () => {
    vi.mocked(isTauriEnvironment).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue(undefined);

    await hidePetSurface();

    expect(invoke).toHaveBeenCalledWith('hide_pet_surface', undefined);
  });

  it('emitPetSurfaceState emits to pet-surface window', async () => {
    vi.mocked(isTauriEnvironment).mockReturnValue(true);
    vi.mocked(emitTo).mockResolvedValue(undefined);

    await emitPetSurfaceState({
      sheetUrl: 'https://example.com/sheet.webp',
      sheetRows: 9,
      petSize: 64,
      petState: PetState.IDLE,
      blockedOnUser: false,
      loading: false,
      unread: false,
      activeChatId: 'chat-1',
    });

    expect(emitTo).toHaveBeenCalledWith(
      'pet-surface',
      'pet-surface-state',
      expect.objectContaining({ sheetUrl: 'https://example.com/sheet.webp' }),
    );
  });

  it('no-ops when not in Tauri', async () => {
    vi.mocked(isTauriEnvironment).mockReturnValue(false);

    await showPetSurface({ x: 0, y: 0, width: 64, height: 64 });
    await emitPetSurfaceState({
      sheetUrl: 'x',
      sheetRows: 9,
      petSize: 64,
      petState: PetState.IDLE,
      blockedOnUser: false,
      loading: false,
      unread: false,
      activeChatId: null,
    });

    expect(invoke).not.toHaveBeenCalled();
    expect(emitTo).not.toHaveBeenCalled();
  });
});
