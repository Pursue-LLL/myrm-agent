/**
 * [INPUT]
 * - useChatStore (POS: chat session id + sendMessage)
 * - petSurfaceBridge (POS: Tauri IPC + event bridge for popped-out pet window)
 * - petSurfaceStorage (POS: surface mode and bounds persistence)
 * - usePetSurfaceUnread (POS: away-completion mail unread)
 *
 * [OUTPUT]
 * - usePetSurfaceHost: popped-out lifecycle, IPC sync, pop-in/out handlers
 *
 * [POS]
 * Tauri desktop pet surface host logic extracted from PetOverlay for file-size limits.
 */

import { useCallback, useEffect, useState } from 'react';

import useChatStore from '@/store/useChatStore';

import {
  emitPetSurfaceState,
  hidePetSurface,
  listenPetSurfaceControl,
  focusPetSurfaceMainWindow,
  showPetSurface,
  togglePetSurfaceMainWindow,
} from './petSurfaceBridge';
import {
  loadPetSurfaceBounds,
  loadPetSurfaceMode,
  storePetSurfaceBounds,
  storePetSurfaceMode,
} from './petSurfaceStorage';
import { usePetSurfaceUnread } from './usePetSurfaceUnread';

import type { PetSurfaceMode, PetSurfaceStatePayload } from './petSurfaceTypes';

interface UsePetSurfaceHostArgs {
  enabled: boolean;
  isTauri: boolean;
  petSize: number;
  payloadBase: Omit<PetSurfaceStatePayload, 'unread' | 'activeChatId'>;
}

export function usePetSurfaceHost({ enabled, isTauri, petSize, payloadBase }: UsePetSurfaceHostArgs) {
  const chatId = useChatStore((s) => s.chatId);
  const [surfaceMode, setSurfaceMode] = useState<PetSurfaceMode>(() => loadPetSurfaceMode());
  const poppedOut = isTauri && surfaceMode === 'popped-out';
  const { unread, clearUnread } = usePetSurfaceUnread(poppedOut);

  const buildSurfacePayload = useCallback((): PetSurfaceStatePayload | null => {
    if (!payloadBase.sheetUrl) {
      return null;
    }
    return {
      ...payloadBase,
      unread,
      activeChatId: chatId ?? null,
    };
  }, [payloadBase, unread, chatId]);

  const pushSurfaceState = useCallback(() => {
    const payload = buildSurfacePayload();
    if (payload) {
      void emitPetSurfaceState(payload);
    }
  }, [buildSurfacePayload]);

  const handlePopOut = useCallback(() => {
    const bounds = loadPetSurfaceBounds(petSize, petSize);
    storePetSurfaceBounds(bounds);
    storePetSurfaceMode('popped-out');
    setSurfaceMode('popped-out');
  }, [petSize]);

  const handlePopIn = useCallback(() => {
    storePetSurfaceMode('embedded');
    setSurfaceMode('embedded');
  }, []);

  const toggleSurfaceMode = useCallback(() => {
    if (surfaceMode === 'popped-out') {
      handlePopIn();
    } else {
      handlePopOut();
    }
  }, [surfaceMode, handlePopIn, handlePopOut]);

  useEffect(() => {
    if (!isTauri || !enabled || !payloadBase.sheetUrl) {
      return;
    }

    if (surfaceMode !== 'popped-out') {
      void hidePetSurface();
      return;
    }

    const bounds = loadPetSurfaceBounds(petSize, petSize);
    void showPetSurface(bounds);

    return () => {
      void hidePetSurface();
    };
  }, [isTauri, enabled, payloadBase.sheetUrl, surfaceMode, petSize]);

  useEffect(() => {
    if (!poppedOut || !enabled || !payloadBase.sheetUrl) {
      return;
    }
    pushSurfaceState();
  }, [poppedOut, enabled, payloadBase.sheetUrl, pushSurfaceState]);

  useEffect(() => {
    if (!isTauri) {
      return;
    }

    let unlisten: (() => void) | undefined;
    void listenPetSurfaceControl((control) => {
      switch (control.type) {
        case 'ready':
          pushSurfaceState();
          break;
        case 'pop-in':
          handlePopIn();
          break;
        case 'submit': {
          const store = useChatStore.getState();
          if (!store.chatId?.trim()) {
            void focusPetSurfaceMainWindow();
          }
          void store.sendMessage(control.text);
          break;
        }
        case 'open-app':
          clearUnread();
          void focusPetSurfaceMainWindow();
          break;
        case 'toggle-app':
          void togglePetSurfaceMainWindow();
          break;
        case 'clear-unread':
          clearUnread();
          break;
        case 'voice-toggle': {
          window.dispatchEvent(new CustomEvent('myrm-voice-toggle'));
          break;
        }
        case 'voice-interrupt': {
          window.dispatchEvent(new CustomEvent('myrm-voice-interrupt'));
          break;
        }
        case 'voice-replay': {
          window.dispatchEvent(new CustomEvent('myrm-voice-replay'));
          break;
        }
        case 'voice-ptt-start': {
          window.dispatchEvent(new CustomEvent('voice-ptt-start'));
          break;
        }
        case 'voice-ptt-stop': {
          window.dispatchEvent(new CustomEvent('voice-ptt-stop'));
          break;
        }
        case 'bounds':
          storePetSurfaceBounds(control.bounds);
          break;
        default:
          break;
      }
    }).then((fn) => {
      unlisten = fn;
    });

    return () => {
      unlisten?.();
    };
  }, [isTauri, pushSurfaceState, handlePopIn, clearUnread]);

  return {
    poppedOut,
    surfaceMode,
    handlePopOut,
    handlePopIn,
    toggleSurfaceMode,
  };
}
