'use client';

/**
 * [INPUT]
 * ./browserAnnotationTypes (POS: BrowserAnnotationPin, BrowserPreviewAnnotationOverlayProps, PinBoundingBox)
 * ./domFeatureExtractor (POS: partitionPinsBySubtree, sanitizeElementTextAndHtml)
 * ./cropImageCanvasHelper (POS: cropImageFromBase64)
 * ./BrowserAnnotationPinMarker (POS: BrowserAnnotationPinMarker)
 * @/lib/utils/classnameUtils (POS: cn helper)
 * lucide-react (POS: Pin, Send, Trash2, X, Sparkles, Layers)
 *
 * [OUTPUT]
 * BrowserPreviewAnnotationOverlay: Interactive annotation overlay with drag-selection, pin markers, and composer export.
 *
 * [POS]
 * In-app browser annotation overlay surface. Enables pinpoint UI element feedback, structured DOM context, and parallel subagent grouping.
 */

import React, { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Pin, Send, Trash2, X, Sparkles, Layers } from 'lucide-react';
import type {
  BrowserAnnotationPin,
  BrowserPreviewAnnotationOverlayProps,
  PinBoundingBox,
} from './browserAnnotationTypes';
import { partitionPinsBySubtree } from './domFeatureExtractor';
import { cropImageFromBase64 } from './cropImageCanvasHelper';
import BrowserAnnotationPinMarker from './BrowserAnnotationPinMarker';

export const BrowserPreviewAnnotationOverlay: React.FC<BrowserPreviewAnnotationOverlayProps> = ({
  isAnnotating,
  onToggleAnnotate,
  pins,
  onAddPin,
  onUpdatePinComment,
  onRemovePin,
  onClearAllPins,
  onExportToComposer,
  viewportWidth,
  viewportHeight,
  baseScreenshotBase64,
  pageUrl,
  pageTitle,
  className,
}) => {
  const containerRef = useRef<HTMLElement>(null);
  const [activePinId, setActivePinId] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [currentBox, setCurrentBox] = useState<PinBoundingBox | null>(null);

  const dragStartRef = useRef<{ x: number; y: number } | null>(null);
  const currentBoxRef = useRef<PinBoundingBox | null>(null);

  const subtreeGroups = useMemo(() => partitionPinsBySubtree(pins), [pins]);

  const scaleX = useMemo(() => {
    if (!containerRef.current || viewportWidth <= 0) {
      return 1;
    }
    return containerRef.current.clientWidth / viewportWidth;
  }, [viewportWidth]);

  const scaleY = useMemo(() => {
    if (!containerRef.current || viewportHeight <= 0) {
      return 1;
    }
    return containerRef.current.clientHeight / viewportHeight;
  }, [viewportHeight]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !isAnnotating) {
      return;
    }

    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) {
        return;
      }
      const rect = container.getBoundingClientRect();
      const clientX = e.clientX - rect.left;
      const clientY = e.clientY - rect.top;

      const normX = clientX / (scaleX || 1);
      const normY = clientY / (scaleY || 1);

      dragStartRef.current = { x: normX, y: normY };
      const initialBox: PinBoundingBox = {
        x: normX,
        y: normY,
        width: 0,
        height: 0,
        viewportWidth,
        viewportHeight,
      };
      currentBoxRef.current = initialBox;
      setCurrentBox(initialBox);
      setIsDragging(true);

      const onMouseMove = (moveEvt: MouseEvent) => {
        const start = dragStartRef.current;
        if (!start) {
          return;
        }
        const moveRect = container.getBoundingClientRect();
        const moveX = (moveEvt.clientX - moveRect.left) / (scaleX || 1);
        const moveY = (moveEvt.clientY - moveRect.top) / (scaleY || 1);

        const minX = Math.min(start.x, moveX);
        const minY = Math.min(start.y, moveY);
        const w = Math.abs(moveX - start.x);
        const h = Math.abs(moveY - start.y);

        const updatedBox: PinBoundingBox = {
          x: Math.max(0, minX),
          y: Math.max(0, minY),
          width: Math.min(viewportWidth - minX, w),
          height: Math.min(viewportHeight - minY, h),
          viewportWidth,
          viewportHeight,
        };

        currentBoxRef.current = updatedBox;
        setCurrentBox(updatedBox);
      };

      const onMouseUp = async () => {
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);

        const box = currentBoxRef.current;
        if (box) {
          const minSize = 16;
          const finalBox: PinBoundingBox = {
            ...box,
            width: Math.max(box.width, minSize),
            height: Math.max(box.height, minSize),
          };

          let croppedScreenshot: string | undefined = undefined;
          if (baseScreenshotBase64) {
            croppedScreenshot = await cropImageFromBase64(baseScreenshotBase64, finalBox);
          }

          onAddPin({
            box: finalBox,
            comment: '',
            croppedScreenshotBase64: croppedScreenshot,
          });
        }

        dragStartRef.current = null;
        currentBoxRef.current = null;
        setIsDragging(false);
        setCurrentBox(null);
      };

      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
    };

    container.addEventListener('mousedown', onMouseDown);
    return () => {
      container.removeEventListener('mousedown', onMouseDown);
    };
  }, [isAnnotating, scaleX, scaleY, viewportWidth, viewportHeight, baseScreenshotBase64, onAddPin]);

  const handleExport = useCallback(() => {
    let formattedPrompt = `## Browser In-App Annotation Feedback\n\n`;
    if (pageTitle || pageUrl) {
      formattedPrompt += `Target: ${pageTitle || 'Untitled Page'} (${pageUrl || 'current preview'})\n\n`;
    }
    formattedPrompt += `Total ${pins.length} annotation pins across ${subtreeGroups.length} DOM subtree groups.\n\n`;

    for (const group of subtreeGroups) {
      formattedPrompt += `### Group: ${group.subtreeName} (${group.subtreeKey})\n`;
      formattedPrompt += `*Recommended: Can be handled independently or by parallel subagents.*\n\n`;
      for (const pin of group.pins) {
        formattedPrompt += `- **Pin #${pin.index}**:\n`;
        if (pin.domMetadata?.cssSelector) {
          formattedPrompt += `  - Selector: \`${pin.domMetadata.cssSelector}\`\n`;
        }
        if (pin.comment) {
          formattedPrompt += `  - Feedback: "${pin.comment}"\n`;
        }
        if (pin.domMetadata?.computedStyles && Object.keys(pin.domMetadata.computedStyles).length > 0) {
          const stylesStr = Object.entries(pin.domMetadata.computedStyles)
            .map(([k, v]) => `${k}: ${v}`)
            .join('; ');
          formattedPrompt += `  - Styles: \`${stylesStr}\`\n`;
        }
        if (pin.domMetadata?.sanitizedOuterHtml) {
          formattedPrompt += `  - Markup snippet: \`${pin.domMetadata.sanitizedOuterHtml.slice(0, 100)}\`\n`;
        }
      }
      formattedPrompt += `\n`;
    }

    onExportToComposer({
      chatId: '',
      pageUrl,
      pageTitle,
      totalPins: pins.length,
      groups: subtreeGroups,
      formattedPrompt,
    });
  }, [pageTitle, pageUrl, pins, subtreeGroups, onExportToComposer]);

  return (
    <section
      ref={containerRef}
      aria-label="Browser annotation overlay"
      data-testid="browser-annotation-overlay"
      className={cn('relative w-full h-full select-none', className)}
    >
      {/* Floating Action Bar */}
      <div className="absolute top-3 left-3 right-3 z-50 flex items-center justify-between gap-2 pointer-events-none">
        <div className="flex items-center gap-2 pointer-events-auto bg-background/95 backdrop-blur-md px-3 py-1.5 rounded-full shadow-lg border border-border">
          <button
            type="button"
            data-testid="toggle-annotate-btn"
            onClick={() => onToggleAnnotate(!isAnnotating)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors',
              isAnnotating
                ? 'bg-primary text-primary-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted',
            )}
          >
            <Pin className="w-3.5 h-3.5" />
            <span>{isAnnotating ? 'Annotating Mode' : 'Annotate'}</span>
            {pins.length > 0 && (
              <span className="ml-1 px-1.5 py-0.2 bg-background/30 rounded-full text-[10px]">
                {pins.length}
              </span>
            )}
          </button>

          {isAnnotating && subtreeGroups.length > 1 && (
            <div className="hidden sm:flex items-center gap-1 text-[11px] text-muted-foreground pl-1 border-l border-border">
              <Layers className="w-3 h-3 text-primary" />
              <span>{subtreeGroups.length} subtrees</span>
              <Sparkles className="w-2.5 h-2.5 text-amber-500" />
            </div>
          )}
        </div>

        {isAnnotating && (
          <div className="flex items-center gap-1.5 pointer-events-auto bg-background/95 backdrop-blur-md px-2 py-1.5 rounded-full shadow-lg border border-border">
            {pins.length > 0 && (
              <>
                <button
                  type="button"
                  data-testid="clear-pins-btn"
                  onClick={onClearAllPins}
                  className="p-1.5 text-muted-foreground hover:text-destructive rounded-full hover:bg-muted transition-colors"
                  title="Clear all pins"
                  aria-label="Clear all pins"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  data-testid="export-composer-btn"
                  onClick={handleExport}
                  className="flex items-center gap-1.5 px-3 py-1 bg-primary text-primary-foreground rounded-full text-xs font-semibold shadow hover:bg-primary/90 transition-colors"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>
                    Add {pins.length} comment{pins.length > 1 ? 's' : ''}
                  </span>
                </button>
              </>
            )}
            <button
              type="button"
              data-testid="close-annotate-btn"
              onClick={() => onToggleAnnotate(false)}
              className="p-1.5 text-muted-foreground hover:text-foreground rounded-full hover:bg-muted transition-colors"
              title="Close annotation"
              aria-label="Close annotation"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Pins Layer */}
      {pins.map((pin) => (
        <BrowserAnnotationPinMarker
          key={pin.id}
          pin={pin}
          scaleX={scaleX}
          scaleY={scaleY}
          isActive={pin.id === activePinId}
          onSelectPin={setActivePinId}
          onUpdateComment={onUpdatePinComment}
          onDeletePin={onRemovePin}
        />
      ))}

      {/* Dragging Selection Rectangle */}
      {isDragging && currentBox && (
        <div
          data-testid="annotation-drag-rect"
          className="absolute border-2 border-dashed border-primary bg-primary/20 pointer-events-none z-40 rounded"
          style={{
            left: `${currentBox.x * scaleX}px`,
            top: `${currentBox.y * scaleY}px`,
            width: `${currentBox.width * scaleX}px`,
            height: `${currentBox.height * scaleY}px`,
          }}
        />
      )}
    </section>
  );
};

export default React.memo(BrowserPreviewAnnotationOverlay);
