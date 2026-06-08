'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { cn } from '@/lib/utils/classnameUtils';

import { SpriteEngine, CODEX_STANDARD } from './SpriteEngine';

import type { SpriteLoadState, SpritesheetMeta } from './SpriteEngine';

interface SpriteRendererProps {
  /** URL of the spritesheet image (webp/png). */
  sheetUrl: string | null;
  /** Current animation row (0-indexed). */
  row: number;
  /** Display size in CSS pixels. Defaults to 64. */
  size?: number;
  /** Optional spritesheet layout override. Defaults to Codex standard 8×9. */
  meta?: Partial<SpritesheetMeta>;
  /** Additional CSS classes on the wrapper. */
  className?: string;
  /** Called when load state changes. */
  onLoadStateChange?: (state: SpriteLoadState) => void;
}

/**
 * SpriteRenderer — React wrapper around SpriteEngine.
 *
 * Handles:
 * - Canvas lifecycle (create/destroy on mount/unmount)
 * - Sheet loading with fallback (shows a pulsing placeholder on error)
 * - Row changes via prop
 * - Pixel-art upscaling (image-rendering: pixelated)
 */
export default function SpriteRenderer({
  sheetUrl,
  row,
  size = 64,
  meta,
  className,
  onLoadStateChange,
}: SpriteRendererProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<SpriteEngine | null>(null);
  const [loadState, setLoadState] = useState<SpriteLoadState>('idle');

  const handleLoadStateChange = useCallback(
    (state: SpriteLoadState) => {
      setLoadState(state);
      onLoadStateChange?.(state);
    },
    [onLoadStateChange],
  );

  // Init engine on mount
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const engine = new SpriteEngine({
      canvas,
      meta: { ...CODEX_STANDARD, ...meta },
      onLoadStateChange: handleLoadStateChange,
    });
    engineRef.current = engine;

    return () => {
      engine.destroy();
      engineRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on mount
  }, []);

  // Load sheet when URL changes
  useEffect(() => {
    const engine = engineRef.current;
    if (!engine || !sheetUrl) return;

    engine.loadSheet(sheetUrl).then(() => engine.play()).catch(() => {
      // error state already set by engine
    });
  }, [sheetUrl]);

  // Update row when prop changes
  useEffect(() => {
    engineRef.current?.setRow(row);
  }, [row]);

  // Update meta when prop changes
  useEffect(() => {
    if (meta) {
      engineRef.current?.setMeta(meta);
    }
  }, [meta]);

  const cellW = meta?.cellWidth ?? CODEX_STANDARD.cellWidth;
  const cellH = meta?.cellHeight ?? CODEX_STANDARD.cellHeight;

  return (
    <div
      className={cn('relative inline-flex items-center justify-center', className)}
      style={{ width: size, height: size }}
    >
      <canvas
        ref={canvasRef}
        width={cellW}
        height={cellH}
        className={cn(
          'w-full h-full',
          loadState !== 'ready' && 'hidden',
        )}
        style={{ imageRendering: 'pixelated' }}
      />

      {/* Fallback: pulsing circle when loading or error */}
      {loadState !== 'ready' && (
        <div
          className={cn(
            'w-full h-full rounded-full flex items-center justify-center',
            loadState === 'loading' && 'bg-muted animate-pulse',
            loadState === 'error' && 'bg-destructive/10',
            loadState === 'idle' && 'bg-muted/50',
          )}
        >
          {loadState === 'error' && (
            <span className="text-xs text-destructive">!</span>
          )}
        </div>
      )}
    </div>
  );
}
