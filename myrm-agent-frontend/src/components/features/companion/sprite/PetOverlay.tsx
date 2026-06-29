/**
 * [INPUT]
 * - PetStateMachine (POS: SSE event → animation row state machine)
 * - SpriteRenderer (POS: React canvas wrapper for spritesheet rendering)
 * - tauriPetBridge (POS: Tauri IPC bridge for native pet overlay window)
 * - useCompanionStore (POS: Companion state with sprite config)
 * - useChatStore (POS: Chat state for loading detection)
 *
 * [OUTPUT]
 * - PetOverlay: Draggable floating sprite overlay with context menu
 *
 * [POS]
 * Top-level pet overlay container rendered in ChatWindow. In Web/SaaS mode,
 * renders an in-browser draggable canvas overlay. In Tauri desktop mode,
 * delegates to the native transparent always-on-top window via tauriPetBridge.
 * Integrates PetStateMachine for SSE-driven animation state transitions.
 */
'use client';

import { useCallback, useEffect, useRef, useState, memo } from 'react';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import useCompanionStore from '@/store/useCompanionStore';

import { AnimRow, PetStateMachine, stepKeyToPetEvent } from './PetStateMachine';
import { resolveAnimRow } from './petStateMapping';
import SpriteRenderer from './SpriteRenderer';
import { isTauriEnv, showPetOverlay, hidePetOverlay, setPetOverlayRow } from './tauriPetBridge';

import type { SpriteLoadState } from './SpriteEngine';

const PET_SIZES = [48, 64, 80, 96, 128] as const;
type PetSize = (typeof PET_SIZES)[number];

interface PetPosition {
  x: number;
  y: number;
}

function getStoredPosition(): PetPosition {
  try {
    const raw = localStorage.getItem('myrm-pet-position');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (typeof parsed.x === 'number' && typeof parsed.y === 'number') {
        return parsed;
      }
    }
  } catch {}
  return { x: -1, y: -1 }; // sentinel for "not set"
}

function storePosition(pos: PetPosition) {
  try {
    localStorage.setItem('myrm-pet-position', JSON.stringify(pos));
  } catch {}
}

function getStoredSize(): PetSize {
  try {
    const raw = localStorage.getItem('myrm-pet-size');
    if (raw) {
      const n = Number(raw);
      if (PET_SIZES.includes(n as PetSize)) return n as PetSize;
    }
  } catch {}
  return 64;
}

function storeSize(size: PetSize) {
  try {
    localStorage.setItem('myrm-pet-size', String(size));
  } catch {}
}

function clampPosition(pos: PetPosition, size: number): PetPosition {
  const maxX = Math.max(0, window.innerWidth - size);
  const maxY = Math.max(0, window.innerHeight - size);
  return {
    x: Math.max(0, Math.min(pos.x, maxX)),
    y: Math.max(0, Math.min(pos.y, maxY)),
  };
}

function defaultPosition(size: number): PetPosition {
  return {
    x: window.innerWidth - size - 24,
    y: window.innerHeight - size - 120,
  };
}

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
  const loading = useChatStore((s) => s.loading);

  const [petSize, setPetSize] = useState<PetSize>(getStoredSize);
  const [position, setPosition] = useState<PetPosition>(() => {
    const stored = getStoredPosition();
    return stored.x < 0 ? defaultPosition(getStoredSize()) : stored;
  });
  const [animRow, setAnimRow] = useState(AnimRow.IDLE);
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

  // Init state machine
  useEffect(() => {
    const sm = new PetStateMachine({
      onChange: (row) => setAnimRow(row),
    });
    stateMachineRef.current = sm;
    return () => {
      sm.destroy();
      stateMachineRef.current = null;
    };
  }, []);

  // React to loading state
  useEffect(() => {
    stateMachineRef.current?.setLoading(loading);
  }, [loading]);

  // Listen for SSE status events (via CustomEvent from statusStreamEvents)
  useEffect(() => {
    const handleStatusEvent = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (!detail?.step_key) return;

      const petEvent = stepKeyToPetEvent(detail.step_key);
      if (petEvent) {
        stateMachineRef.current?.ingest(petEvent);
      }
      stateMachineRef.current?.heartbeat();
    };

    window.addEventListener('pet-status-event', handleStatusEvent);
    return () => window.removeEventListener('pet-status-event', handleStatusEvent);
  }, []);

  // Drag handlers
  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
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

      const el = e.currentTarget as HTMLElement;
      el.setPointerCapture(e.pointerId);
    },
    [position],
  );

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;

    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;

    if (!drag.moved && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
      drag.moved = true;
    }

    if (drag.moved) {
      const newPos = clampPosition({ x: drag.posX + dx, y: drag.posY + dy }, petSize);
      setPosition(newPos);
    }
  }, [petSize]);

  const handlePointerUp = useCallback(
    (e: React.PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;

      const el = e.currentTarget as HTMLElement;
      try {
        el.releasePointerCapture(e.pointerId);
      } catch {}

      if (drag.moved) {
        storePosition(position);
      }

      dragRef.current = null;
      setIsDragging(false);
    },
    [position],
  );

  // Context menu
  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const menuW = 160;
    const menuH = 180;
    const x = Math.min(e.clientX, window.innerWidth - menuW);
    const y = Math.min(e.clientY, window.innerHeight - menuH);
    setContextMenu({ visible: true, x: Math.max(0, x), y: Math.max(0, y) });
  }, []);

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu.visible) return;

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

  const resolvedRow = resolveAnimRow(animRow, sheetRows);

  const handleSheetRowsDetected = useCallback((rows: number) => {
    setSheetRows(rows);
  }, []);

  const handleSpriteLoadState = useCallback((state: SpriteLoadState) => {
    if (state === 'error') {
      setAnimRow(AnimRow.IDLE);
    }
  }, []);

  // Clamp position on window resize
  useEffect(() => {
    const handleResize = () => {
      setPosition((prev) => clampPosition(prev, petSize));
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [petSize]);

  const isTauri = isTauriEnv();

  // Tauri: manage native overlay window lifecycle
  useEffect(() => {
    if (!isTauri || !spriteEnabled || !spriteConfig?.sheetUrl) return;

    showPetOverlay(spriteConfig.sheetUrl, petSize, resolvedRow);
    return () => { hidePetOverlay(); };
  }, [isTauri, spriteEnabled, spriteConfig?.sheetUrl, petSize]); // eslint-disable-line react-hooks/exhaustive-deps

  // Tauri: sync animation row changes to native overlay
  useEffect(() => {
    if (!isTauri || !spriteEnabled) return;
    setPetOverlayRow(resolvedRow);
  }, [isTauri, spriteEnabled, resolvedRow]);

  if (!spriteEnabled || !spriteConfig?.sheetUrl) return null;

  // In Tauri mode, the native overlay handles rendering; skip in-browser overlay
  if (isTauri) return null;

  return (
    <>
      <div
        ref={containerRef}
        className={cn(
          'fixed z-[60] select-none',
          isDragging ? 'cursor-grabbing' : 'cursor-grab',
        )}
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
          sheetUrl={spriteConfig.sheetUrl}
          row={resolvedRow}
          size={petSize}
          meta={spriteConfig.meta}
          onLoadStateChange={handleSpriteLoadState}
          onSheetRowsDetected={handleSheetRowsDetected}
        />
      </div>

      {/* Context menu */}
      {contextMenu.visible && (
        <div
          className="fixed z-[70] min-w-[140px] rounded-lg border bg-popover p-1 shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
            {t('sprite.contextTitle')}
          </div>

          <div className="px-2 py-1 text-xs text-muted-foreground">
            {t('sprite.size')}
          </div>
          <div className="flex gap-1 px-2 pb-1">
            {PET_SIZES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => handleSizeChange(s)}
                className={cn(
                  'rounded px-1.5 py-0.5 text-xs transition-colors',
                  s === petSize
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted text-foreground',
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
