'use client';

import React, { useCallback, useRef, useState, useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Globe } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import type { BrowserRefInfo } from '@/store/chat/types';
import InspectorToolbar from './InspectorToolbar';
import ElementOverlay from './ElementOverlay';
import InspectorInstructionInput from './InspectorInstructionInput';

interface BrowserLiveViewProps {
  onSendInstruction: (instruction: string, refId: string | null) => void;
}

const MIN_PANEL_WIDTH = 320;
const MAX_PANEL_WIDTH = 960;
const DEFAULT_PANEL_WIDTH = 520;
const PANEL_WIDTH_KEY = 'browser-inspector-panel-width';

const BrowserLiveView: React.FC<BrowserLiveViewProps> = ({ onSendInstruction }) => {
  const t = useTranslations('chat.browserInspector');
  const {
    isOpen,
    mode,
    viewData,
    selectedElement,
    instructionText,
    isSnapshotLoading,
    closePanel,
    setMode,
    selectElement,
    clearSelection,
    setInstructionText,
    fetchSnapshot,
  } = useBrowserInspectorStore();

  const [panelWidth, setPanelWidth] = useState(DEFAULT_PANEL_WIDTH);
  const [isResizing, setIsResizing] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const imageContainerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelWidthRef = useRef(panelWidth);
  panelWidthRef.current = panelWidth;

  useEffect(() => {
    const saved = localStorage.getItem(PANEL_WIDTH_KEY);
    if (saved) {
      const parsed = parseInt(saved, 10);
      if (parsed >= MIN_PANEL_WIDTH && parsed <= MAX_PANEL_WIDTH) {
        setPanelWidth(parsed);
      }
    }
    const checkMobile = () => setIsMobile(window.innerWidth < 640);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);

    const startX = e.clientX;
    const startWidth = panelWidthRef.current;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = startX - moveEvent.clientX;
      const newWidth = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, startWidth + delta));
      setPanelWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      localStorage.setItem(PANEL_WIDTH_KEY, String(panelWidthRef.current));
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, []);

  const handleImageLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    const container = imageContainerRef.current;
    if (!container) return;

    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;
    const scale = Math.min(containerWidth / img.naturalWidth, containerHeight / img.naturalHeight, 1);

    setImageSize({
      width: img.naturalWidth * scale,
      height: img.naturalHeight * scale,
    });
  }, []);

  const handleElementClick = useCallback(
    (refId: string, info: BrowserRefInfo) => {
      selectElement(refId, info);
    },
    [selectElement],
  );

  const handleSubmit = useCallback(
    (instruction: string, refId: string | null) => {
      onSendInstruction(instruction, refId);
      clearSelection();
    },
    [onSendInstruction, clearSelection],
  );

  if (!isOpen) return null;

  return (
    <div
      ref={panelRef}
      className={cn(
        'fixed top-0 right-0 h-full z-40 flex',
        'bg-background border-l border-border shadow-xl',
        'transition-transform duration-200 ease-out',
        isResizing && 'select-none',
      )}
      style={{ width: isMobile ? '100%' : `${panelWidth}px` }}
    >
      {/* Resize handle — hidden on mobile */}
      <div
        className={cn(
          'absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize z-50 sm:block hidden',
          'hover:bg-primary/20 active:bg-primary/30 transition-colors',
          isResizing && 'bg-primary/30',
        )}
        onMouseDown={handleResizeStart}
        role="separator"
        aria-orientation="vertical"
        aria-label={t('resizePanel')}
      />

      <div className="flex flex-col w-full ml-1.5">
        <InspectorToolbar
          mode={mode}
          onModeChange={setMode}
          onClose={closePanel}
          onRefresh={fetchSnapshot}
          pageUrl={viewData?.pageUrl}
          pageTitle={viewData?.pageTitle}
          isLoading={isSnapshotLoading}
        />

        <div
          ref={imageContainerRef}
          className="flex-1 relative overflow-hidden bg-muted/30 flex items-center justify-center"
        >
          {viewData ? (
            <div className="relative" style={{ width: imageSize.width, height: imageSize.height }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`data:${viewData.mimeType};base64,${viewData.screenshotBase64}`}
                alt={t('screenshotAlt')}
                className="w-full h-full object-contain"
                onLoad={handleImageLoad}
                draggable={false}
              />

              {mode === 'inspect' && imageSize.width > 0 && (
                <ElementOverlay
                  refs={viewData.refs}
                  imageWidth={imageSize.width}
                  imageHeight={imageSize.height}
                  viewportWidth={viewData.viewportWidth}
                  viewportHeight={viewData.viewportHeight}
                  selectedRefId={selectedElement?.refId ?? null}
                  onElementClick={handleElementClick}
                />
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 text-muted-foreground px-6 text-center">
              <div className="w-12 h-12 rounded-full border-2 border-dashed border-muted-foreground/30 flex items-center justify-center">
                <Globe className="w-6 h-6 text-muted-foreground/50" />
              </div>
              <p className="text-sm">{t('waitingForBrowser')}</p>
              <p className="text-xs text-muted-foreground/60">{t('waitingHint')}</p>
            </div>
          )}
        </div>

        {mode === 'inspect' && (
          <InspectorInstructionInput
            selectedRefId={selectedElement?.refId ?? null}
            selectedInfo={selectedElement?.info ?? null}
            instructionText={instructionText}
            onInstructionChange={setInstructionText}
            onSubmit={handleSubmit}
            onClearSelection={clearSelection}
            disabled={!viewData}
          />
        )}
      </div>
    </div>
  );
};

export default React.memo(BrowserLiveView);
