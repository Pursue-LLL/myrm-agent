'use client';

import React, { useMemo, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import type { BrowserRefInfo } from '@/store/chat/types';

interface ElementOverlayProps {
  refs: Record<string, BrowserRefInfo>;
  imageWidth: number;
  imageHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  selectedRefId: string | null;
  onElementClick: (refId: string, info: BrowserRefInfo) => void;
}

const INTERACTIVE_ROLES = new Set([
  'button',
  'link',
  'textbox',
  'checkbox',
  'radio',
  'combobox',
  'menuitem',
  'tab',
  'switch',
  'slider',
  'spinbutton',
  'searchbox',
  'option',
  'listbox',
  'clickable',
  'focusable',
]);

const ElementOverlay: React.FC<ElementOverlayProps> = ({
  refs,
  imageWidth,
  imageHeight,
  viewportWidth,
  viewportHeight,
  selectedRefId,
  onElementClick,
}) => {
  const scaleX = imageWidth / viewportWidth;
  const scaleY = imageHeight / viewportHeight;

  const interactiveRefs = useMemo(() => {
    return Object.entries(refs).filter(([, info]) => info.bbox && INTERACTIVE_ROLES.has(info.role));
  }, [refs]);

  const handleClick = useCallback(
    (e: React.MouseEvent, refId: string, info: BrowserRefInfo) => {
      e.stopPropagation();
      onElementClick(refId, info);
    },
    [onElementClick],
  );

  if (interactiveRefs.length === 0) return null;

  return (
    <div className="absolute inset-0 pointer-events-none">
      {interactiveRefs.map(([refId, info]) => {
        const bbox = info.bbox!;
        const isSelected = refId === selectedRefId;

        const left = bbox.x * scaleX;
        const top = bbox.y * scaleY;
        const width = bbox.width * scaleX;
        const height = bbox.height * scaleY;

        if (width < 2 || height < 2) return null;

        return (
          <button
            key={refId}
            type="button"
            className={cn(
              'absolute border rounded-sm pointer-events-auto cursor-pointer transition-all duration-150',
              isSelected
                ? 'border-primary bg-primary/20 ring-2 ring-primary/40 z-20'
                : 'border-primary/40 bg-primary/5 hover:bg-primary/15 hover:border-primary/70 z-10',
            )}
            style={{
              left: `${left}px`,
              top: `${top}px`,
              width: `${width}px`,
              height: `${height}px`,
            }}
            onClick={(e) => handleClick(e, refId, info)}
            title={`[${refId}] ${info.role}: ${info.name}`}
            aria-label={`Select element ${refId} (${info.role}: ${info.name})`}
          >
            {isSelected && (
              <span
                className={cn(
                  'absolute -top-5 left-0 px-1.5 py-0.5 text-[10px] font-mono',
                  'bg-primary text-primary-foreground rounded-t-sm whitespace-nowrap',
                  'shadow-sm pointer-events-none',
                )}
              >
                {refId} {info.role}
                {info.name ? `: ${info.name.slice(0, 30)}` : ''}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};

export default React.memo(ElementOverlay);
