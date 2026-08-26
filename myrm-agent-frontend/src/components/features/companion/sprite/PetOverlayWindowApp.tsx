'use client';

/**
 * Popped-out pet surface window — puppet UI driven by main-window SSOT events.
 */

import { Mail, SendHorizontal } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/utils/classnameUtils';
import { applyThemePreinitFromLocalStorage, THEME_PREINIT_STORAGE_KEY } from '@/theme-engine/preinit';

import PetStatusBubble from './PetStatusBubble';
import PetVoiceOrbGlow from './PetVoiceOrbGlow';
import {
  emitPetSurfaceControl,
  focusPetSurfaceMainWindow,
  listenPetSurfaceState,
  setPetSurfaceFocusable,
  setPetSurfaceIgnoreCursor,
  togglePetSurfaceMainWindow,
} from './petSurfaceBridge';
import { PetState } from './PetStateMachine';
import { resolvePetSheetRow } from './petStateMapping';
import SpriteRenderer from './SpriteRenderer';

import type { PetSurfaceStatePayload } from './petSurfaceTypes';

const CLICK_SLOP_PX = 3;
const DOUBLE_CLICK_MS = 250;
const ALPHA_HIT_THRESHOLD = 16;

export default function PetOverlayWindowApp() {
  const t = useTranslations('companion.sprite');
  const [state, setState] = useState<PetSurfaceStatePayload | null>(null);
  const [composerOpen, setComposerOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [unread, setUnread] = useState(false);

  const dragRef = useRef<{ startX: number; startY: number; moved: boolean } | null>(null);
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const ignoreRef = useRef(true);

  const setIgnore = useCallback((ignore: boolean) => {
    if (ignoreRef.current === ignore) {
      return;
    }
    ignoreRef.current = ignore;
    void setPetSurfaceIgnoreCursor(ignore);
  }, []);

  useEffect(() => {
    void emitPetSurfaceControl({ type: 'ready' });
    let unlisten: (() => void) | undefined;
    void listenPetSurfaceState((payload) => {
      setState(payload);
      setUnread(payload.unread);
    }).then((fn) => {
      unlisten = fn;
    });
    return () => {
      unlisten?.();
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    applyThemePreinitFromLocalStorage();
    const onStorage = (event: StorageEvent) => {
      if (event.key === THEME_PREINIT_STORAGE_KEY) {
        applyThemePreinitFromLocalStorage();
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  useEffect(() => {
    void setPetSurfaceFocusable(composerOpen);
    if (composerOpen) {
      setIgnore(false);
    }
  }, [composerOpen, setIgnore]);

  const sampleCanvasAlpha = useCallback((clientX: number, clientY: number): boolean => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return true;
    }
    const rect = canvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
      return true;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return true;
    }
    const px = Math.floor((clientX - rect.left) * (canvas.width / rect.width));
    const py = Math.floor((clientY - rect.top) * (canvas.height / rect.height));
    try {
      return ctx.getImageData(px, py, 1, 1).data[3] >= ALPHA_HIT_THRESHOLD;
    } catch {
      return true;
    }
  }, []);

  useEffect(() => {
    setIgnore(true);

    const onMove = (ev: MouseEvent) => {
      if (dragRef.current || composerOpen) {
        setIgnore(false);
        return;
      }
      const target = document.elementFromPoint(ev.clientX, ev.clientY);
      const interactive =
        target instanceof HTMLButtonElement ||
        target instanceof HTMLInputElement ||
        (containerRef.current?.contains(target ?? null) && !(target instanceof HTMLCanvasElement)) ||
        sampleCanvasAlpha(ev.clientX, ev.clientY);
      setIgnore(!interactive);
    };

    window.addEventListener('mousemove', onMove);
    return () => window.removeEventListener('mousemove', onMove);
  }, [composerOpen, sampleCanvasAlpha, setIgnore]);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) {
      return;
    }
    dragRef.current = { startX: e.screenX, startY: e.screenY, moved: false };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const handlePointerMove = useCallback(async (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) {
      return;
    }
    const dx = e.screenX - drag.startX;
    const dy = e.screenY - drag.startY;
    if (!drag.moved && (Math.abs(dx) > CLICK_SLOP_PX || Math.abs(dy) > CLICK_SLOP_PX)) {
      drag.moved = true;
    }
    if (drag.moved) {
      const { getCurrentWindow, PhysicalPosition } = await import('@tauri-apps/api/window');
      const win = getCurrentWindow();
      const pos = await win.outerPosition();
      await win.setPosition(new PhysicalPosition(pos.x + dx, pos.y + dy));
      drag.startX = e.screenX;
      drag.startY = e.screenY;
    }
  }, []);

  const openComposer = useCallback(() => {
    setComposerOpen(true);
  }, []);

  const handlePointerUp = useCallback(
    async (e: React.PointerEvent) => {
      const drag = dragRef.current;
      dragRef.current = null;
      try {
        (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
      if (!drag) {
        return;
      }

      if (drag.moved) {
        const { getCurrentWindow } = await import('@tauri-apps/api/window');
        const win = getCurrentWindow();
        const pos = await win.outerPosition();
        const size = await win.outerSize();
        void emitPetSurfaceControl({
          type: 'bounds',
          bounds: {
            x: pos.x,
            y: pos.y,
            width: size.width,
            height: size.height,
          },
        });
        return;
      }

      if (e.shiftKey) {
        void emitPetSurfaceControl({ type: 'pop-in' });
        return;
      }

      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
        // 双击手势：若伴侣在说话则打断，否则尝试重播末句 TTS (F13 DoD)
        if (state?.voiceState === 'speaking') {
          void emitPetSurfaceControl({ type: 'voice-interrupt' });
        } else {
          void emitPetSurfaceControl({ type: 'voice-replay' });
        }
        return;
      }

      clickTimerRef.current = setTimeout(() => {
        clickTimerRef.current = null;
        // 单击手势：无打字时切换主窗口，长按进入 composer
        void togglePetSurfaceMainWindow();
      }, DOUBLE_CLICK_MS);
    },
    [state?.voiceState],
  );

  const handleSubmit = useCallback(() => {
    const text = draft.trim();
    if (!text) {
      return;
    }
    void emitPetSurfaceControl({ type: 'submit', text });
    setDraft('');
    setComposerOpen(false);
  }, [draft]);

  const handleMail = useCallback(() => {
    void emitPetSurfaceControl({ type: 'clear-unread' });
    setUnread(false);
    void focusPetSurfaceMainWindow();
  }, []);

  if (!state?.sheetUrl) {
    return <div className="h-screen w-screen bg-transparent" />;
  }

  const petState = state.petState as PetState;
  const row = resolvePetSheetRow(petState, state.sheetRows);

  return (
    <div className="relative flex h-screen w-screen flex-col items-center justify-end bg-transparent pb-2">
      {composerOpen && (
        <div className="mb-2 flex w-[90%] items-center gap-1 rounded-lg border bg-popover/95 p-1 shadow-lg backdrop-blur-sm">
          <input
            type="text"
            value={draft}
            onChange={(ev) => setDraft(ev.target.value)}
            onKeyDown={(ev) => {
              if (ev.key === 'Enter' && !ev.shiftKey) {
                ev.preventDefault();
                handleSubmit();
              }
              if (ev.key === 'Escape') {
                setComposerOpen(false);
                setDraft('');
              }
            }}
            placeholder={t('composerPlaceholder')}
            className="min-w-0 flex-1 bg-transparent px-2 py-1 text-xs outline-none"
            autoFocus
          />
          <button
            type="button"
            onClick={handleSubmit}
            className="rounded p-1 hover:bg-muted"
            aria-label={t('composerSend')}
          >
            <SendHorizontal className="h-4 w-4" />
          </button>
        </div>
      )}

      <div ref={containerRef} className="relative" style={{ width: state.petSize, height: state.petSize }}>
        <PetVoiceOrbGlow
          voiceState={state.voiceState}
          audioLevel={state.audioLevel}
          size={state.petSize}
        />
        <PetStatusBubble petState={petState} />
        {unread && (
          <button
            type="button"
            onClick={handleMail}
            onPointerDown={(e) => e.stopPropagation()}
            onPointerUp={(e) => e.stopPropagation()}
            className="absolute -right-1 -top-1 z-10 rounded-full border bg-popover p-1 shadow-md"
            aria-label={t('mailOpen')}
          >
            <Mail className="h-3.5 w-3.5" />
          </button>
        )}
        <div
          className={cn('select-none', composerOpen ? 'cursor-default' : 'cursor-grab')}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          <SpriteRenderer
            sheetUrl={state.sheetUrl}
            row={row}
            size={state.petSize}
            onCanvasRef={(canvas) => {
              canvasRef.current = canvas;
            }}
          />
        </div>
      </div>
    </div>
  );
}
