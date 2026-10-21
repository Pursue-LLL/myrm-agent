'use client';

/**
 * [INPUT]
 * - InspectedElementContext, SourceLocation from @/services/selfEvolution
 * - extractInspectionFingerprint from ./domSourceLocator
 * - DesignerEyeFeedbackModal from ./DesignerEyeFeedbackModal
 * - Keyboard events (Cmd+Shift+E / Ctrl+Shift+E) and pointer hover/click events
 * - Translation strings from 'designerEye' namespace
 *
 * [OUTPUT]
 * - DesignerEyeOverlay: Viewport inspection overlay with React Fiber reverse location HUD
 *
 * [POS]
 * Interactive element inspection HUD layer for Designer's Eye UI Element Inspector & Self-Evolution Pipeline.
 * Strict typing: Zero `any`. File length < 320 lines. Accessible triggers.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconEye,
  IconSparkles,
  IconX,
} from '@/components/features/icons/PremiumIcons';
import type { InspectedElementContext } from '@/services/selfEvolution';
import { extractInspectionFingerprint } from './domSourceLocator';
import { DesignerEyeFeedbackModal } from './DesignerEyeFeedbackModal';

interface HighlightRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

function extractElementContext(el: HTMLElement): InspectedElementContext {
  const fp = extractInspectionFingerprint(el);
  const style = window.getComputedStyle(el);

  const computedStyleSummary: Record<string, string> = {
    padding: style.padding,
    margin: style.margin,
    color: style.color,
    backgroundColor: style.backgroundColor,
    fontSize: style.fontSize,
    borderRadius: style.borderRadius,
  };

  return {
    domSelector: fp.selector,
    tagName: fp.tagName,
    classes: fp.classes,
    componentHint: fp.primarySource?.componentName,
    componentHierarchy: fp.componentHierarchy,
    primarySource: fp.primarySource,
    candidates: fp.candidates,
    textSnippet: fp.textContentSnippet,
    computedStyleSummary,
  };
}

export function DesignerEyeOverlay() {
  const t = useTranslations('designerEye');

  const [isActive, setIsActive] = useState<boolean>(false);
  const [hoverRect, setHoverRect] = useState<HighlightRect | null>(null);
  const [hoveredContext, setHoveredContext] = useState<InspectedElementContext | null>(null);
  const [selectedContext, setSelectedContext] = useState<InspectedElementContext | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [isModifierHeld, setIsModifierHeld] = useState<boolean>(false);

  const overlayRef = useRef<HTMLDivElement>(null);

  // Toggle overlay on Cmd+Shift+E / Ctrl+Shift+E & track modifier keys for passthrough
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'e') {
        e.preventDefault();
        setIsActive((prev) => !prev);
      } else if (e.key === 'Escape' && isActive && !isModalOpen) {
        setIsActive(false);
        setHoverRect(null);
      }

      if (e.metaKey || e.ctrlKey) {
        setIsModifierHeld(true);
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (!e.metaKey && !e.ctrlKey) {
        setIsModifierHeld(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [isActive, isModalOpen]);

  // Pointer hover and inspect tracking
  useEffect(() => {
    if (!isActive || isModalOpen) {
      setHoverRect(null);
      setHoveredContext(null);
      return;
    }

    const getTargetElement = (e: MouseEvent | PointerEvent): HTMLElement | null => {
      if (typeof document.elementFromPoint === 'function') {
        return document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null;
      }
      return (e.target as HTMLElement | null) ?? null;
    };

    const handlePointerMove = (e: PointerEvent) => {
      if (isModifierHeld) {
        setHoverRect(null);
        setHoveredContext(null);
        return;
      }

      const target = getTargetElement(e);
      if (!target || target.closest('[data-designer-eye-ignore]')) {
        setHoverRect(null);
        setHoveredContext(null);
        return;
      }

      const rect = target.getBoundingClientRect();
      setHoverRect({
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      });
      setHoveredContext(extractElementContext(target));
    };

    const handleClick = (e: MouseEvent) => {
      // Allow passthrough when modifier key is held
      if (e.metaKey || e.ctrlKey) {
        return;
      }

      const target = getTargetElement(e);
      if (!target || target.closest('[data-designer-eye-ignore]')) {
        return;
      }

      e.preventDefault();
      e.stopPropagation();

      const ctx = extractElementContext(target);
      setSelectedContext(ctx);
      setIsModalOpen(true);
      setHoverRect(null);
    };

    window.addEventListener('pointermove', handlePointerMove, true);
    window.addEventListener('click', handleClick, true);

    return () => {
      window.removeEventListener('pointermove', handlePointerMove, true);
      window.removeEventListener('click', handleClick, true);
    };
  }, [isActive, isModalOpen, isModifierHeld]);

  const handleCloseModal = useCallback(() => {
    setIsModalOpen(false);
    setSelectedContext(null);
  }, []);

  return (
    <>
      {/* Floating HUD toggle trigger (Eliminates dead feature path) */}
      <aside
        data-designer-eye-ignore="true"
        aria-label={t('hudAriaLabel')}
        className="fixed bottom-6 right-6 z-[9990] flex items-center gap-2 select-none"
      >
        <button
          type="button"
          onClick={() => setIsActive((prev) => !prev)}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-full text-xs font-medium shadow-xl backdrop-blur-md transition-all border ${
            isActive
              ? 'bg-primary text-primary-foreground border-primary ring-2 ring-primary/40'
              : 'bg-card/90 text-foreground border-border/80 hover:bg-card hover:border-primary/50'
          }`}
          title={t('toggleHint')}
        >
          <IconEye className="w-4 h-4" />
          <span>{isActive ? t('inspectorActive') : t('inspectorTrigger')}</span>
          <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono rounded bg-background/60 border border-border/40 text-muted-foreground">
            {t('shortcutHint')}
          </kbd>
        </button>

        {isActive && (
          <button
            type="button"
            onClick={() => {
              setIsActive(false);
              setHoverRect(null);
            }}
            className="p-2 rounded-full bg-card/90 text-muted-foreground hover:text-foreground border border-border shadow-md transition-colors"
            aria-label={t('closeInspectorAriaLabel')}
          >
            <IconX className="w-4 h-4" />
          </button>
        )}
      </aside>

      {/* Active Highlighting Frame Overlay with Fiber Source Locator Tooltip */}
      {isActive && hoverRect && !isModalOpen && !isModifierHeld && (
        <div
          ref={overlayRef}
          data-designer-eye-ignore="true"
          className="pointer-events-none fixed z-[9980] transition-[top,left,width,height] duration-75 ease-out"
          style={{
            top: `${hoverRect.top}px`,
            left: `${hoverRect.left}px`,
            width: `${hoverRect.width}px`,
            height: `${hoverRect.height}px`,
          }}
        >
          {/* Glowing border */}
          <div className="absolute inset-0 rounded border-2 border-primary bg-primary/10 shadow-[0_0_14px_rgba(99,102,241,0.45)]" />

          {/* Dimension, Component & Source Badge */}
          <div className="absolute -top-7 left-0 flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-primary text-primary-foreground text-[10px] font-mono shadow-md whitespace-nowrap">
            <IconSparkles className="w-3 h-3 text-amber-300" />
            <span className="font-bold">
              {hoveredContext?.componentHint || hoveredContext?.tagName}
            </span>
            <span className="opacity-70">
              ({hoveredContext?.tagName})
            </span>
            <span className="opacity-90 bg-primary-foreground/20 px-1 py-0.2 rounded text-[9px]">
              {Math.round(hoverRect.width)} × {Math.round(hoverRect.height)}
            </span>
            {hoveredContext?.primarySource?.fileName && (
              <span className="text-[9px] text-amber-200 opacity-90 truncate max-w-[160px]">
                {hoveredContext.primarySource.fileName}
                {hoveredContext.primarySource.lineNumber ? `:${hoveredContext.primarySource.lineNumber}` : ''}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Feedback & Self-Evolution Modal */}
      <DesignerEyeFeedbackModal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        target={selectedContext}
      />
    </>
  );
}
