'use client';

/**
 * [INPUT]
 * - adaptiveGridTypes: AdaptiveMultiPanelGridProps, DevicePosture, AdaptiveLayoutMode
 * - useAdaptiveDevicePosture: hook detecting foldable, tablet, mobile postures
 * - lucide-react icons
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - AdaptiveMultiPanelGrid: Responsive multi-panel layout adapter for foldables, tablets, and phones
 *
 * [POS]
 * Adaptive layout cockpit automatically negotiating dual-panel for foldables and compact landscape for phones.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  GripVertical,
  Columns2,
  Smartphone,
  Maximize2,
  Minimize2,
  Laptop,
} from 'lucide-react';
import { AdaptiveMultiPanelGridProps } from './adaptiveGridTypes';
import { useAdaptiveDevicePosture } from './useAdaptiveDevicePosture';

export const AdaptiveMultiPanelGrid: React.FC<AdaptiveMultiPanelGridProps> = ({
  leftPanel,
  rightPanel,
  thirdPanel,
  initialSplitRatio = 0.45,
  minLeftWidthPx = 280,
  minRightWidthPx = 320,
  overridePosture,
  className = '',
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('adaptiveLayout.grid');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback for tests
  }

  const detectedMetrics = useAdaptiveDevicePosture();
  const posture = overridePosture || detectedMetrics.posture;

  const [splitRatio, setSplitRatio] = useState<number>(initialSplitRatio);
  const [mobileActiveTab, setMobileActiveTab] = useState<'left' | 'right'>('left');
  const [isRightCollapsed, setIsRightCollapsed] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const isDraggingRef = useRef<boolean>(false);

  const handlePointerDown = useCallback(() => {
    isDraggingRef.current = true;
  }, []);

  const handlePointerMove = useCallback(
    (clientX: number) => {
      if (!isDraggingRef.current || !containerRef.current) {
        return;
      }

      const rect = containerRef.current.getBoundingClientRect();
      const containerWidth = rect.width;
      if (containerWidth <= 0) {
        return;
      }

      const relativeX = clientX - rect.left;
      const newRatio = Math.min(
        Math.max(minLeftWidthPx / containerWidth, relativeX / containerWidth),
        1 - minRightWidthPx / containerWidth,
      );
      setSplitRatio(Number(newRatio.toFixed(3)));
    },
    [minLeftWidthPx, minRightWidthPx],
  );

  useEffect(() => {
    const onWindowMouseMove = (e: globalThis.MouseEvent) => {
      if (isDraggingRef.current) {
        handlePointerMove(e.clientX);
      }
    };

    const onWindowTouchMove = (e: globalThis.TouchEvent) => {
      if (isDraggingRef.current && e.touches.length > 0) {
        handlePointerMove(e.touches[0].clientX);
      }
    };

    const onWindowPointerUp = () => {
      isDraggingRef.current = false;
    };

    window.addEventListener('mousemove', onWindowMouseMove);
    window.addEventListener('touchmove', onWindowTouchMove);
    window.addEventListener('mouseup', onWindowPointerUp);
    window.addEventListener('touchend', onWindowPointerUp);

    return () => {
      window.removeEventListener('mousemove', onWindowMouseMove);
      window.removeEventListener('touchmove', onWindowTouchMove);
      window.removeEventListener('mouseup', onWindowPointerUp);
      window.removeEventListener('touchend', onWindowPointerUp);
    };
  }, [handlePointerMove]);

  // 1. Mobile portrait mode: Single stacked panel with tabs
  if (posture === 'mobile-portrait') {
    return (
      <div
        data-testid="adaptive-grid-mobile-portrait"
        className={`flex h-full w-full flex-col overflow-hidden bg-background ${className}`}
      >
        <div className="flex h-11 shrink-0 items-center justify-around border-b border-border/80 bg-muted/30 px-2">
          <button
            type="button"
            data-testid="mobile-tab-left"
            onClick={() => {
              setMobileActiveTab('left');
            }}
            className={`flex-1 py-1.5 text-center text-xs font-semibold rounded-lg transition-all ${
              mobileActiveTab === 'left'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t('toggleLeft')}
          </button>
          <button
            type="button"
            data-testid="mobile-tab-right"
            onClick={() => {
              setMobileActiveTab('right');
            }}
            className={`flex-1 py-1.5 text-center text-xs font-semibold rounded-lg transition-all ${
              mobileActiveTab === 'right'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t('toggleRight')}
          </button>
        </div>

        <div className="flex-1 overflow-auto">
          {mobileActiveTab === 'left' ? leftPanel : rightPanel}
        </div>
      </div>
    );
  }

  // 2. Mobile landscape compact mode: Slim height dual panel
  if (posture === 'mobile-landscape') {
    return (
      <div
        data-testid="adaptive-grid-mobile-landscape"
        className={`flex h-full w-full flex-row overflow-hidden bg-background p-1 gap-1 ${className}`}
      >
        <div
          data-testid="grid-panel-left"
          className="flex h-full flex-col overflow-hidden rounded-xl border border-border/60 bg-card/60"
          style={{ width: '38%' }}
        >
          <div className="flex h-7 items-center gap-1.5 border-b border-border/40 px-2 bg-muted/20">
            <Smartphone className="h-3.5 w-3.5 text-primary rotate-90" />
            <span className="text-[10px] font-semibold text-muted-foreground">
              {t('mobileLandscape')}
            </span>
          </div>
          <div className="flex-1 overflow-auto p-1">{leftPanel}</div>
        </div>

        <div
          data-testid="grid-panel-right"
          className="flex h-full flex-1 flex-col overflow-hidden rounded-xl border border-border/60 bg-card"
        >
          <div className="flex-1 overflow-auto">{rightPanel}</div>
        </div>
      </div>
    );
  }

  // 3. Foldable expanded (8:7 / 4:3) and tablet/desktop multi-panel layout
  const isFoldable = posture === 'foldable-expanded';
  const leftWidthPercent = isRightCollapsed ? 100 : Math.round(splitRatio * 100);
  const rightWidthPercent = isRightCollapsed ? 0 : 100 - leftWidthPercent;

  return (
    <div
      ref={containerRef}
      data-testid={isFoldable ? 'adaptive-grid-foldable' : 'adaptive-grid-desktop'}
      className={`relative flex h-full w-full select-none overflow-hidden bg-background ${className}`}
    >
      {/* Left panel */}
      <div
        data-testid="grid-panel-left"
        style={{ width: `${leftWidthPercent}%` }}
        className="flex h-full flex-col overflow-hidden transition-all duration-75"
      >
        {isFoldable ? (
          <div className="flex h-8 items-center justify-between border-b border-border/50 bg-primary/5 px-3">
            <div className="flex items-center gap-1.5">
              <Columns2 className="h-4 w-4 text-primary" />
              <span className="text-xs font-semibold text-primary">
                {t('foldableGolden')} (8:7)
              </span>
            </div>
          </div>
        ) : null}
        <div className="flex-1 overflow-auto">{leftPanel}</div>
      </div>

      {/* Splitter resize handle */}
      {!isRightCollapsed ? (
        <button
          type="button"
          data-testid="grid-splitter"
          aria-label={t('dragToResize')}
          onMouseDown={handlePointerDown}
          onTouchStart={handlePointerDown}
          className="group relative flex w-2.5 cursor-col-resize items-center justify-center bg-border/40 hover:bg-primary/20 active:bg-primary/40 transition-colors z-10 border-none p-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <div className="h-8 w-1 rounded-full bg-muted-foreground/40 group-hover:bg-primary group-hover:scale-y-125 transition-all">
            <GripVertical className="h-4 w-4 -ml-1.5 opacity-0 group-hover:opacity-100 text-primary" />
          </div>
        </button>
      ) : null}

      {/* Right panel */}
      {!isRightCollapsed ? (
        <div
          data-testid="grid-panel-right"
          style={{ width: `${rightWidthPercent}%` }}
          className="relative flex h-full flex-col overflow-hidden bg-muted/10 transition-all duration-75"
        >
          <div className="absolute top-2 right-2 z-20">
            <button
              type="button"
              aria-label={t('collapsePanel')}
              onClick={() => {
                setIsRightCollapsed(true);
              }}
              className="flex h-7 w-7 items-center justify-center rounded-lg bg-background/80 border border-border/60 text-muted-foreground shadow hover:bg-muted"
            >
              <Minimize2 className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex-1 overflow-auto">{rightPanel}</div>
        </div>
      ) : (
        <button
          type="button"
          aria-label={t('expandPanel')}
          onClick={() => {
            setIsRightCollapsed(false);
          }}
          className="absolute top-2 right-2 z-20 flex h-8 items-center gap-1 rounded-xl bg-primary px-2.5 text-xs font-semibold text-primary-foreground shadow-md hover:bg-primary/90"
        >
          <Maximize2 className="h-3.5 w-3.5" />
          <span>{t('expandPanel')}</span>
        </button>
      )}

      {/* Optional third panel for wide desktop */}
      {thirdPanel && posture === 'desktop' ? (
        <div
          data-testid="grid-panel-third"
          className="hidden xl:flex h-full w-80 shrink-0 border-l border-border/80 bg-card overflow-auto"
        >
          {thirdPanel}
        </div>
      ) : null}
    </div>
  );
};
