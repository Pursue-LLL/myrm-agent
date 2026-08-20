/**
 * [INPUT]
 * - PetStateMachine (POS: SSE event → animation row state machine)
 * - SpriteRenderer (POS: React canvas wrapper for spritesheet rendering)
 * - usePetSurfaceHost (POS: Tauri popped-out lifecycle + IPC sync)
 * - useCompanionStore (POS: Companion state with sprite config)
 * - deriveBlockedOnUser (POS: HITL store → blocked-on-user flag)
 *
 * [OUTPUT]
 * - PetOverlay: Draggable floating sprite overlay with context menu
 *
 * [POS]
 * Top-level pet overlay container mounted from ChatWindowSatellites when companion_mode
 * is enabled. Web renders in-browser overlay; Tauri supports embedded + popped-out OS window.
 */
'use client';

import { useCallback, useEffect, useRef, useState, memo } from 'react';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/utils/classnameUtils';
import { resolveCompanionSpritesheetUrl } from '@/services/companion/petSpritesheet';
import { openCompanionHealthCheck } from '@/services/companion/petDoctor';
import useApprovalStore from '@/store/useApprovalStore';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useChatStore from '@/store/useChatStore';
import useCompanionStore from '@/store/useCompanionStore';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import { useLivenessState } from '@/hooks/shell/useLivenessState';

import { deriveBlockedOnUser, hasPendingClarificationFromMessages } from './deriveBlockedOnUser';
import {
  clampPosition,
  defaultPosition,
  getStoredPosition,
  getStoredSize,
  PET_SIZES,
  storePosition,
  storeSize,
  type PetPosition,
  type PetSize,
} from './petOverlayLayoutStorage';
import { PetState, PetStateMachine, stepKeyToPetEvent } from './PetStateMachine';
import { resolvePetSheetRow } from './petStateMapping';
import { isTauriEnv } from './petSurfaceBridge';
import SpriteRenderer from './SpriteRenderer';
import { usePetSurfaceHost } from './usePetSurfaceHost';

import type { SpriteLoadState } from './SpriteEngine';

interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
}

const PetOverlay = memo(function PetOverlay() {
  const t = useTranslations('companion');
  const spriteConfig = useCompanionStore((s) => s.spriteConfig);
  const spriteEnabled = useCompanionStore((s) => s.spriteEnabled);
  const setSpriteEnabled = useCompanionStore((s) => s.setSpriteEnabled);
  const sheetUrl = resolveCompanionSpritesheetUrl(spriteConfig);
  const liveness = useLivenessState();
  const loading = liveness.state === 'busy' || liveness.state === 'draining';
  const toolApprovalQueueLength = useToolApprovalStore((s) => s.queue.length);
  const approvalQueueLength = useApprovalStore((s) => s.queue.length);
  const hasPendingClarification = useChatStore((s) => hasPendingClarificationFromMessages(s.messages));
  const desktopControlPending = useDesktopControlApprovalStore((s) => s.pending);
  const browserTakeoverPending = useBrowserTakeoverStore((s) => s.pending);

  const blockedOnUser = deriveBlockedOnUser({
    toolApprovalQueueLength,
    approvalQueueLength,
    hasPendingClarification,
    desktopControlPending,
    browserTakeoverPending,
  });

  const isTauri = isTauriEnv();
  const [petState, setPetState] = useState(PetState.IDLE);
  const [petSize, setPetSize] = useState<PetSize>(getStoredSize);
  const [position, setPosition] = useState<PetPosition>(() => {
    const stored = getStoredPosition();
    return stored.x < 0 ? defaultPosition(getStoredSize()) : stored;
  });
  const [sheetRows, setSheetRows] = useState(9);
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    x: 0,
    y: 0,
  });
  const [isDragging, setIsDragging] = useState(false);

  const stateMachineRef = useRef<PetStateMachine | null>(null);
  const dragRef = useRef<{ startX: number; startY: number; posX: number; posY: number; moved: boolean } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const { poppedOut, handlePopOut, toggleSurfaceMode } = usePetSurfaceHost({
    enabled: spriteEnabled && Boolean(sheetUrl),
    isTauri,
    petSize,
    payloadBase: {
      sheetUrl: sheetUrl ?? '',
      sheetRows,
      petSize,
      petState,
      blockedOnUser,
      loading,
    },
  });

  useEffect(() => {
    const sm = new PetStateMachine({
      onChange: (state) => setPetState(state),
    });
    stateMachineRef.current = sm;
    return () => {
      sm.destroy();
      stateMachineRef.current = null;
    };
  }, []);

  useEffect(() => {
    stateMachineRef.current?.setLoading(loading);
  }, [loading]);

  useEffect(() => {
    stateMachineRef.current?.setBlockedOnUser(blockedOnUser);
  }, [blockedOnUser]);

  useEffect(() => {
    const handleStatusEvent = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (!detail?.step_key) {
        return;
      }

      const petEvent = stepKeyToPetEvent(detail.step_key);
      if (petEvent) {
        stateMachineRef.current?.ingest(petEvent);
      }
      stateMachineRef.current?.heartbeat();
    };

    window.addEventListener('pet-status-event', handleStatusEvent);
    return () => window.removeEventListener('pet-status-event', handleStatusEvent);
  }, []);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) {
        return;
      }
      e.preventDefault();
      e.stopPropagation();

      dragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        posX: position.x,
        posY: position.y,
        moved: false,
      };
      setIsDragging(true);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    },
    [position],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) {
        return;
      }

      const dx = e.clientX - drag.startX;
      const dy = e.clientY - drag.startY;

      if (!drag.moved && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
        drag.moved = true;
      }

      if (drag.moved) {
        setPosition(clampPosition({ x: drag.posX + dx, y: drag.posY + dy }, petSize));
      }
    },
    [petSize],
  );

  const handlePointerUp = useCallback(
    (e: React.PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) {
        return;
      }

      try {
        (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {}

      if (drag.moved) {
        storePosition(position);
      } else if (isTauri && e.shiftKey) {
        toggleSurfaceMode();
      }

      dragRef.current = null;
      setIsDragging(false);
    },
    [position, isTauri, toggleSurfaceMode],
  );

  const handleContextMenu = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const menuW = 160;
      const menuH = isTauri ? 220 : 180;
      setContextMenu({
        visible: true,
        x: Math.max(0, Math.min(e.clientX, window.innerWidth - menuW)),
        y: Math.max(0, Math.min(e.clientY, window.innerHeight - menuH)),
      });
    },
    [isTauri],
  );

  useEffect(() => {
    if (!contextMenu.visible) {
      return;
    }
    const close = () => setContextMenu((prev) => ({ ...prev, visible: false }));
    const timer = setTimeout(() => window.addEventListener('click', close, { once: true }), 0);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('click', close);
    };
  }, [contextMenu.visible]);

  const handleSizeChange = useCallback((size: PetSize) => {
    setPetSize(size);
    storeSize(size);
    setContextMenu((prev) => ({ ...prev, visible: false }));
  }, []);

  const handleHide = useCallback(() => {
    setSpriteEnabled(false);
    setContextMenu((prev) => ({ ...prev, visible: false }));
  }, [setSpriteEnabled]);

  const handleResetPosition = useCallback(() => {
    const pos = defaultPosition(petSize);
    setPosition(pos);
    storePosition(pos);
    setContextMenu((prev) => ({ ...prev, visible: false }));
  }, [petSize]);

  const handlePopOutFromMenu = useCallback(() => {
    handlePopOut();
    setContextMenu((prev) => ({ ...prev, visible: false }));
  }, [handlePopOut]);

  const handleSheetRowsDetected = useCallback((rows: number) => {
    setSheetRows(rows);
  }, []);

  const handleSpriteLoadState = useCallback((state: SpriteLoadState) => {
    if (state === 'error') {
      stateMachineRef.current?.reset();
      setPetState(PetState.IDLE);
    }
  }, []);

  useEffect(() => {
    const handleResize = () => {
      setPosition((prev) => clampPosition(prev, petSize));
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [petSize]);

  if (!spriteEnabled || !sheetUrl) {
    return null;
  }
  if (poppedOut) {
    return null;
  }

  const resolvedRow = resolvePetSheetRow(petState, sheetRows);

  return (
    <>
      <div
        ref={containerRef}
        className={cn('fixed z-[60] select-none', isDragging ? 'cursor-grabbing' : 'cursor-grab')}
        style={{
          left: position.x,
          top: position.y,
          width: petSize,
          height: petSize,
          touchAction: 'none',
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onContextMenu={handleContextMenu}
      >
        <SpriteRenderer
          sheetUrl={sheetUrl}
          row={resolvedRow}
          size={petSize}
          onLoadStateChange={handleSpriteLoadState}
          onSheetRowsDetected={handleSheetRowsDetected}
          onHealthCheckRequest={openCompanionHealthCheck}
        />
      </div>

      {contextMenu.visible && (
        <div
          className="fixed z-[70] min-w-[140px] rounded-lg border bg-popover p-1 shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">{t('sprite.contextTitle')}</div>

          {isTauri && (
            <button
              type="button"
              onClick={handlePopOutFromMenu}
              className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-muted transition-colors"
            >
              {t('sprite.popOut')}
            </button>
          )}

          <div className="px-2 py-1 text-xs text-muted-foreground">{t('sprite.size')}</div>
          <div className="flex gap-1 px-2 pb-1">
            {PET_SIZES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => handleSizeChange(s)}
                className={cn(
                  'rounded px-1.5 py-0.5 text-xs transition-colors',
                  s === petSize ? 'bg-primary text-primary-foreground' : 'hover:bg-muted text-foreground',
                )}
              >
                {s}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={handleResetPosition}
            className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-muted transition-colors"
          >
            {t('sprite.resetPosition')}
          </button>

          <button
            type="button"
            onClick={handleHide}
            className="w-full rounded px-2 py-1.5 text-left text-xs text-destructive hover:bg-destructive/10 transition-colors"
          >
            {t('sprite.hide')}
          </button>
        </div>
      )}
    </>
  );
});

export default PetOverlay;
