/**
 * Annotation toolbar with tool selection, color picker, and actions.
 * Responsive: top bar on desktop, bottom bar on mobile.
 */

'use client';

import { useTranslations } from 'next-intl';
import type { AnnotationTool } from './types';
import { DEFAULT_COLORS } from './types';

interface AnnotationToolbarProps {
  activeTool: AnnotationTool;
  setActiveTool: (tool: AnnotationTool) => void;
  activeColor: string;
  setActiveColor: (color: string) => void;
  strokeWidth: number;
  setStrokeWidth: (width: number) => void;
  onUndo: () => void;
  onRedo: () => void;
  onClear: () => void;
  onSave: () => void;
  onClose: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

const TOOLS: { id: AnnotationTool; labelKey: string; icon: string }[] = [
  { id: 'arrow', labelKey: 'arrow', icon: '↗' },
  { id: 'rectangle', labelKey: 'rectangle', icon: '□' },
  { id: 'ellipse', labelKey: 'ellipse', icon: '○' },
  { id: 'text', labelKey: 'text', icon: 'T' },
  { id: 'freehand', labelKey: 'freehand', icon: '✎' },
  { id: 'highlight', labelKey: 'highlight', icon: '▬' },
  { id: 'blur', labelKey: 'blur', icon: '▦' },
  { id: 'crop', labelKey: 'crop', icon: '⬚' },
];

export function AnnotationToolbar({
  activeTool,
  setActiveTool,
  activeColor,
  setActiveColor,
  strokeWidth,
  setStrokeWidth,
  onUndo,
  onRedo,
  onClear,
  onSave,
  onClose,
  canUndo,
  canRedo,
}: AnnotationToolbarProps) {
  const t = useTranslations('annotationEditor');

  return (
    <div className="flex flex-col md:flex-row items-center gap-2 md:gap-3 px-3 py-2 bg-background/95 backdrop-blur-sm border-b md:border-b border-border">
      {/* Tool buttons */}
      <div className="flex items-center gap-1">
        {TOOLS.map((tool) => (
          <button
            key={tool.id}
            onClick={() => setActiveTool(tool.id)}
            title={t(tool.labelKey)}
            className={`w-8 h-8 flex items-center justify-center rounded-md text-sm font-medium transition-colors
              ${activeTool === tool.id ? 'bg-primary text-primary-foreground' : 'hover:bg-muted text-foreground/70'}`}
          >
            {tool.icon}
          </button>
        ))}
      </div>

      {/* Separator */}
      <div className="hidden md:block w-px h-6 bg-border" />

      {/* Color picker */}
      <div className="flex items-center gap-1">
        {DEFAULT_COLORS.map((color) => (
          <button
            key={color}
            onClick={() => setActiveColor(color)}
            className={`w-5 h-5 rounded-full border-2 transition-transform
              ${activeColor === color ? 'border-primary scale-125' : 'border-transparent hover:scale-110'}`}
            style={{ backgroundColor: color }}
            title={color}
          />
        ))}
      </div>

      {/* Separator */}
      <div className="hidden md:block w-px h-6 bg-border" />

      {/* Stroke width */}
      <div className="flex items-center gap-1">
        {[2, 4, 8].map((w) => (
          <button
            key={w}
            onClick={() => setStrokeWidth(w)}
            title={`${w}px`}
            className={`w-7 h-7 flex items-center justify-center rounded-md transition-colors
              ${strokeWidth === w ? 'bg-primary/20 ring-1 ring-primary' : 'hover:bg-muted'}`}
          >
            <span
              className="rounded-full bg-foreground"
              style={{ width: `${Math.max(w, 3)}px`, height: `${Math.max(w, 3)}px` }}
            />
          </button>
        ))}
      </div>

      {/* Separator */}
      <div className="hidden md:block w-px h-6 bg-border" />

      {/* Actions */}
      <div className="flex items-center gap-1">
        <button
          onClick={onUndo}
          disabled={!canUndo}
          title={t('undo')}
          className="w-8 h-8 flex items-center justify-center rounded-md text-sm hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
        >
          ↶
        </button>
        <button
          onClick={onRedo}
          disabled={!canRedo}
          title={t('redo')}
          className="w-8 h-8 flex items-center justify-center rounded-md text-sm hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
        >
          ↷
        </button>
        <button
          onClick={onClear}
          title={t('clear')}
          className="w-8 h-8 flex items-center justify-center rounded-md text-sm hover:bg-muted text-destructive"
        >
          ✕
        </button>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Save / Close */}
      <div className="flex items-center gap-2">
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-sm rounded-md border border-border hover:bg-muted transition-colors"
        >
          {t('cancel')}
        </button>
        <button
          onClick={onSave}
          className="px-3 py-1.5 text-sm rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          {t('save')}
        </button>
      </div>
    </div>
  );
}
