import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: vi.fn(() => true),
}));

vi.mock('../petSurfaceBridge', () => ({
  emitPetSurfaceState: vi.fn(),
  hidePetSurface: vi.fn(),
  showPetSurface: vi.fn(),
  focusPetSurfaceMainWindow: vi.fn(),
  togglePetSurfaceMainWindow: vi.fn(),
  listenPetSurfaceControl: vi.fn(() => Promise.resolve(vi.fn())),
}));

vi.mock('../petSurfaceStorage', () => ({
  loadPetSurfaceBounds: vi.fn(() => ({ x: 100, y: 100, width: 64, height: 64 })),
  loadPetSurfaceMode: vi.fn(() => 'popped-out'),
  storePetSurfaceBounds: vi.fn(),
  storePetSurfaceMode: vi.fn(),
}));

vi.mock('../usePetSurfaceUnread', () => ({
  usePetSurfaceUnread: vi.fn(() => ({ unread: false, clearUnread: vi.fn() })),
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: vi.fn(() => ({ chatId: 'test-chat', sendMessage: vi.fn() })),
    // Zustand selector mock
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useChatStore: (selector: (state: any) => any) => selector({ chatId: 'test-chat' }),
  },
}));

import { emitPetSurfaceState, listenPetSurfaceControl } from '../petSurfaceBridge';
import { usePetSurfaceHost } from '../usePetSurfaceHost';
import { PetState } from '../PetStateMachine';
import type { PetSurfaceControl } from '../petSurfaceTypes';

describe('usePetSurfaceHost voice & state synchronization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('subscribes to myrm-voice-state-update and synchronizes voice payload to surface state', async () => {
    const payloadBase = {
      sheetUrl: 'https://example.com/pet.webp',
      sheetRows: 9,
      petSize: 64,
      petState: PetState.IDLE,
      blockedOnUser: false,
      loading: false,
    };

    renderHook(() =>
      usePetSurfaceHost({
        enabled: true,
        isTauri: true,
        petSize: 64,
        payloadBase,
      }),
    );

    expect(emitPetSurfaceState).toHaveBeenCalled();

    // Trigger voice state update event
    act(() => {
      window.dispatchEvent(
        new CustomEvent('myrm-voice-state-update', {
          detail: {
            voiceState: 'speaking',
            audioLevel: 0.85,
          },
        }),
      );
    });

    expect(emitPetSurfaceState).toHaveBeenCalledWith(
      expect.objectContaining({
        voiceState: 'speaking',
        audioLevel: 0.85,
      }),
    );
  });

  it('forwards voice control commands from popped-out surface to local window event bus', async () => {
    let capturedHandler: ((control: PetSurfaceControl) => void) | undefined;
    vi.mocked(listenPetSurfaceControl).mockImplementation(async (handler) => {
      capturedHandler = handler;
      return () => {};
    });

    const payloadBase = {
      sheetUrl: 'https://example.com/pet.webp',
      sheetRows: 9,
      petSize: 64,
      petState: PetState.IDLE,
      blockedOnUser: false,
      loading: false,
    };

    renderHook(() =>
      usePetSurfaceHost({
        enabled: true,
        isTauri: true,
        petSize: 64,
        payloadBase,
      }),
    );

    expect(capturedHandler).toBeDefined();

    const toggleListener = vi.fn();
    const interruptListener = vi.fn();
    const pttStartListener = vi.fn();
    const pttStopListener = vi.fn();

    window.addEventListener('myrm-voice-toggle', toggleListener);
    window.addEventListener('myrm-voice-interrupt', interruptListener);
    window.addEventListener('voice-ptt-start', pttStartListener);
    window.addEventListener('voice-ptt-stop', pttStopListener);

    act(() => {
      capturedHandler?.({ type: 'voice-toggle' });
    });
    expect(toggleListener).toHaveBeenCalledTimes(1);

    act(() => {
      capturedHandler?.({ type: 'voice-interrupt' });
    });
    expect(interruptListener).toHaveBeenCalledTimes(1);

    act(() => {
      capturedHandler?.({ type: 'voice-ptt-start' });
    });
    expect(pttStartListener).toHaveBeenCalledTimes(1);

    act(() => {
      capturedHandler?.({ type: 'voice-ptt-stop' });
    });
    expect(pttStopListener).toHaveBeenCalledTimes(1);

    window.removeEventListener('myrm-voice-toggle', toggleListener);
    window.removeEventListener('myrm-voice-interrupt', interruptListener);
    window.removeEventListener('voice-ptt-start', pttStartListener);
    window.removeEventListener('voice-ptt-stop', pttStopListener);
  });
});
