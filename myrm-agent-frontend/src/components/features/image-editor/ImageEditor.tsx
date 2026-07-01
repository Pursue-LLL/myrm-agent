'use client';

/**
 * [INPUT]
 * - imageSrc: string (URL or base64 data URL of the image to edit)
 * - onComplete: (blob: Blob) => void (callback with annotated image)
 * - onCancel: () => void
 *
 * [OUTPUT]
 * ImageEditor: lightweight annotation editor overlay with Canvas API tools.
 *
 * [POS]
 * Inline image annotation for VQA, AI-generated image feedback, and sensitive info masking.
 */

import React, { memo, useEffect, useState, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import {
  X,
  Undo2,
  Redo2,
  RotateCw,
  Square,
  Circle,
  ArrowUpRight,
  Pencil,
  Type,
  Eraser,
  Send,
} from 'lucide-react';
import { useImageEditor } from './useImageEditor';
import type { ToolType } from './tools/types';
import { PALETTE_COLORS, LINE_WIDTHS } from './tools/types';

interface ImageEditorProps {
  imageSrc: string;
  onComplete: (blob: Blob) => void;
  onCancel: () => void;
}

const TOOLS: { type: ToolType; icon: React.FC<{ className?: string }>; labelKey: string }[] = [
  { type: 'freehand', icon: Pencil, labelKey: 'freehand' },
  { type: 'rect', icon: Square, labelKey: 'rect' },
  { type: 'ellipse', icon: Circle, labelKey: 'ellipse' },
  { type: 'arrow', icon: ArrowUpRight, labelKey: 'arrow' },
  { type: 'text', icon: Type, labelKey: 'text' },
  { type: 'blur', icon: Eraser, labelKey: 'blur' },
];

const ImageEditor: React.FC<ImageEditorProps> = ({ imageSrc, onComplete, onCancel }) => {
  const t = useTranslations('imageEditor');
  const [loading, setLoading] = useState(true);
  const textInputRef = useRef<HTMLInputElement>(null);

  const {
    canvasRef,
    tool,
    setTool,
    color,
    setColor,
    lineWidth,
    setLineWidth,
    rotate90,
    undo,
    redo,
    canUndo,
    canRedo,
    loadImage,
    exportAsBlob,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleTextSubmit,
    pendingTextPosition,
  } = useImageEditor();

  useEffect(() => {
    setLoading(true);
    loadImage(imageSrc).finally(() => setLoading(false));
  }, [imageSrc, loadImage]);

  useEffect(() => {
    if (pendingTextPosition && textInputRef.current) {
      textInputRef.current.focus();
    }
  }, [pendingTextPosition]);

  const handleSend = useCallback(async () => {
    const blob = await exportAsBlob();
    if (blob) onComplete(blob);
  }, [exportAsBlob, onComplete]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onCancel();
    if ((e.metaKey || e.ctrlKey) && e.key === 'z') {
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    }
  }, [onCancel, undo, redo]);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);

  const cursorClass = tool === 'text' ? 'cursor-text' : 'cursor-crosshair';

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/90 backdrop-blur-sm animate-in fade-in-0 duration-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-black/60">
        <button
          type="button"
          onClick={onCancel}
          className="p-2 rounded-full hover:bg-white/10 transition-colors text-white"
          aria-label={t('cancel')}
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={undo}
            disabled={!canUndo}
            className="p-2 rounded-full hover:bg-white/10 transition-colors text-white disabled:opacity-30"
            aria-label={t('undo')}
          >
            <Undo2 className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={redo}
            disabled={!canRedo}
            className="p-2 rounded-full hover:bg-white/10 transition-colors text-white disabled:opacity-30"
            aria-label={t('redo')}
          >
            <Redo2 className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={rotate90}
            className="p-2 rounded-full hover:bg-white/10 transition-colors text-white"
            aria-label={t('rotate')}
          >
            <RotateCw className="w-4 h-4" />
          </button>
        </div>

        <button
          type="button"
          onClick={handleSend}
          className={cn(
            'flex items-center gap-1.5 px-4 py-1.5 rounded-full',
            'bg-primary text-primary-foreground font-medium text-sm',
            'hover:bg-primary/90 transition-colors',
          )}
        >
          <Send className="w-4 h-4" />
          {t('send')}
        </button>
      </div>

      {/* Canvas area */}
      <div className="flex-1 flex items-center justify-center overflow-hidden p-4 relative">
        {loading ? (
          <div className="animate-spin w-8 h-8 border-2 border-white/30 border-t-white rounded-full" />
        ) : (
          <>
            <canvas
              ref={canvasRef}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerLeave={handlePointerUp}
              className={cn(
                'max-w-full max-h-full object-contain rounded-lg shadow-2xl touch-none',
                cursorClass,
              )}
              style={{ imageRendering: 'auto' }}
            />

            {/* Text input overlay */}
            {pendingTextPosition && (
              <div className="absolute bottom-20 left-1/2 -translate-x-1/2 z-10">
                <div className="flex items-center gap-2 p-2 rounded-xl bg-popover/95 border border-border shadow-xl backdrop-blur-sm">
                  <input
                    ref={textInputRef}
                    type="text"
                    placeholder={t('textPlaceholder')}
                    className="bg-transparent text-sm text-popover-foreground outline-none min-w-[200px] placeholder:text-muted-foreground/60"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleTextSubmit((e.target as HTMLInputElement).value);
                      if (e.key === 'Escape') handleTextSubmit('');
                    }}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Bottom toolbar */}
      <div className="flex flex-col items-center gap-2 px-4 py-3 bg-black/60">
        {/* Tool buttons */}
        <div className="flex items-center gap-1 flex-wrap justify-center">
          {TOOLS.map(({ type, icon: Icon, labelKey }) => (
            <button
              key={type}
              type="button"
              onClick={() => setTool(type)}
              className={cn(
                'p-2.5 rounded-lg transition-colors',
                tool === type
                  ? 'bg-white/20 text-white'
                  : 'text-white/60 hover:text-white hover:bg-white/10',
              )}
              aria-label={t(labelKey)}
              title={t(labelKey)}
            >
              <Icon className="w-4 h-4" />
            </button>
          ))}

          <div className="w-px h-6 bg-white/20 mx-1" />

          {/* Color palette */}
          {PALETTE_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setColor(c)}
              className={cn(
                'w-6 h-6 rounded-full border-2 transition-transform',
                color === c ? 'border-white scale-110' : 'border-transparent hover:scale-105',
              )}
              style={{ backgroundColor: c }}
              aria-label={c}
            />
          ))}

          <div className="w-px h-6 bg-white/20 mx-1" />

          {/* Line width */}
          {LINE_WIDTHS.map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => setLineWidth(w)}
              className={cn(
                'p-2 rounded-lg transition-colors',
                lineWidth === w
                  ? 'bg-white/20 text-white'
                  : 'text-white/60 hover:text-white hover:bg-white/10',
              )}
              aria-label={`${w}px`}
            >
              <div
                className="rounded-full bg-current"
                style={{ width: w + 4, height: w + 4 }}
              />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default memo(ImageEditor);
