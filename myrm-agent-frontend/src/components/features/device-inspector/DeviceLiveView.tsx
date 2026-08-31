'use client';

import React, { useCallback, useRef, useState, useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Smartphone, RefreshCw, AlertCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useDeviceInspectorStore, { selectScopedDeviceViewData } from '@/store/useDeviceInspectorStore';
import useChatStore from '@/store/useChatStore';
import type { BrowserRefInfo } from '@/store/chat/types';
import { ElementOverlay } from '@/components/features/browser-inspector';
import { useClosePanelOnChatSwitch } from '@/hooks/inspector/useClosePanelOnChatSwitch';
import DeviceInspectorToolbar from './DeviceInspectorToolbar';
import DeviceInstructionInput from './DeviceInstructionInput';

interface DeviceLiveViewProps {
  onSendInstruction: (instruction: string, refId: string | null) => void;
}

const MIN_PANEL_WIDTH = 300;
const MAX_PANEL_WIDTH = 720;
const DEFAULT_PANEL_WIDTH = 380;
const PANEL_WIDTH_KEY = 'device-inspector-panel-width';

export const DeviceLiveView: React.FC<DeviceLiveViewProps> = ({ onSendInstruction }) => {
  const t = useTranslations('chat.deviceInspector');
  const {
    isOpen,
    mode,
    viewData,
    selectedElement,
    instructionText,
    isSnapshotLoading,
    notificationRedaction,
    closePanel,
    setMode,
    setNotificationRedaction,
    selectElement,
    clearSelection,
    setInstructionText,
    fetchSnapshot,
    sendTouchRelay,
  } = useDeviceInspectorStore();

  const chatId = useChatStore((state) => state.chatId?.trim() ?? '');
  const scopedViewData = selectScopedDeviceViewData(viewData, chatId);

  useClosePanelOnChatSwitch(chatId, isOpen, closePanel);

  const [panelWidth, setPanelWidth] = useState(DEFAULT_PANEL_WIDTH);
  const [isResizing, setIsResizing] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [touchFeedback, setTouchFeedback] = useState<{ x: number; y: number } | null>(null);

  const imageContainerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelWidthRef = useRef(panelWidth);
  panelWidthRef.current = panelWidth;

  const pointerStartRef = useRef<{ x: number; y: number; time: number } | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem(PANEL_WIDTH_KEY);
    if (saved) {
      const parsed = parseInt(saved, 10);
      if (parsed >= MIN_PANEL_WIDTH && parsed <= MAX_PANEL_WIDTH) {
        setPanelWidth(parsed);
      }
    }
  }, []);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const handlePointerDownResize = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setIsResizing(true);
    const startX = e.clientX;
    const startWidth = panelWidthRef.current;

    const onPointerMove = (ev: PointerEvent) => {
      const deltaX = startX - ev.clientX;
      const newWidth = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, startWidth + deltaX));
      setPanelWidth(newWidth);
    };

    const onPointerUp = () => {
      setIsResizing(false);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      localStorage.setItem(PANEL_WIDTH_KEY, String(panelWidthRef.current));
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  }, []);

  const handleImageLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    setImageSize({ width: img.naturalWidth, height: img.naturalHeight });
  }, []);

  const handleElementSelect = useCallback(
    (refId: string, info: BrowserRefInfo) => {
      selectElement(refId, info);
    },
    [selectElement],
  );

  const handleTouchPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    pointerStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      time: Date.now(),
    };
  }, []);

  const handleTouchPointerUp = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (mode !== 'view' || !pointerStartRef.current || !imageContainerRef.current) return;
      const start = pointerStartRef.current;
      pointerStartRef.current = null;

      const rect = imageContainerRef.current.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;

      const startRelX = (start.x - rect.left) / rect.width;
      const startRelY = (start.y - rect.top) / rect.height;
      const endRelX = (e.clientX - rect.left) / rect.width;
      const endRelY = (e.clientY - rect.top) / rect.height;

      const deltaDist = Math.hypot(e.clientX - start.x, e.clientY - start.y);
      const duration = Date.now() - start.time;

      // Touch ripple feedback
      setTouchFeedback({ x: e.clientX - rect.left, y: e.clientY - rect.top });
      setTimeout(() => setTouchFeedback(null), 400);

      if (deltaDist < 10) {
        if (duration > 500) {
          void sendTouchRelay({
            action: 'hold',
            x: Math.round(startRelX * (scopedViewData?.viewportWidth || 1080)),
            y: Math.round(startRelY * (scopedViewData?.viewportHeight || 2400)),
            durationMs: duration,
          });
        } else {
          void sendTouchRelay({
            action: 'tap',
            x: Math.round(startRelX * (scopedViewData?.viewportWidth || 1080)),
            y: Math.round(startRelY * (scopedViewData?.viewportHeight || 2400)),
          });
        }
      } else {
        void sendTouchRelay({
          action: 'swipe',
          x: Math.round(startRelX * (scopedViewData?.viewportWidth || 1080)),
          y: Math.round(startRelY * (scopedViewData?.viewportHeight || 2400)),
          endX: Math.round(endRelX * (scopedViewData?.viewportWidth || 1080)),
          endY: Math.round(endRelY * (scopedViewData?.viewportHeight || 2400)),
          durationMs: Math.max(100, duration),
        });
      }
    },
    [mode, scopedViewData, sendTouchRelay],
  );

  if (!isOpen) return null;

  const isViewMode = mode === 'view';
  const hasScreenshot = Boolean(scopedViewData?.screenshotBase64);

  return (
    <div
      ref={panelRef}
      className={cn(
        'fixed top-0 right-0 h-full z-40 bg-background border-l border-border shadow-2xl flex flex-col',
        'transition-[width] duration-75 ease-out',
        isMobile && 'w-full !max-w-full',
      )}
      style={!isMobile ? { width: panelWidth } : undefined}
      data-testid="device-inspector-panel"
    >
      {!isMobile && (
        <div
          role="separator"
          tabIndex={0}
          aria-label={t('resizePanel')}
          aria-orientation="vertical"
          onPointerDown={handlePointerDownResize}
          className={cn(
            'absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-primary/50 transition-colors z-50',
            isResizing && 'bg-primary w-2',
          )}
        />
      )}

      <DeviceInspectorToolbar
        mode={mode}
        notificationRedaction={notificationRedaction}
        onModeChange={setMode}
        onToggleNotificationRedaction={setNotificationRedaction}
        onClose={closePanel}
        onRefresh={() => void fetchSnapshot(false)}
        isLoading={isSnapshotLoading}
        title={scopedViewData?.deviceName || t('title')}
        subtitle={scopedViewData?.deviceId}
      />

      {scopedViewData && !scopedViewData.connected && (
        <div className="px-3 py-2 text-xs bg-amber-500/10 text-amber-700 dark:text-amber-400 border-b border-amber-500/20 flex items-center gap-2">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="flex-1 min-w-0">{t('deviceDisconnected')}</span>
        </div>
      )}

      <div className="flex-1 overflow-auto bg-muted/40 relative flex items-center justify-center p-2">
        {hasScreenshot && scopedViewData ? (
          <div
            ref={imageContainerRef}
            className="relative inline-block max-w-full max-h-full select-none rounded-xl overflow-hidden shadow-md border border-border"
            onPointerDown={handleTouchPointerDown}
            onPointerUp={handleTouchPointerUp}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:${scopedViewData.mimeType};base64,${scopedViewData.screenshotBase64}`}
              alt={t('screenshotAlt')}
              onLoad={handleImageLoad}
              className={cn(
                'max-w-full max-h-[calc(100vh-140px)] object-contain block mx-auto',
                isViewMode && 'cursor-pointer',
              )}
              draggable={false}
            />

            {/* Notification Bar Privacy Redaction Overlay */}
            {notificationRedaction && (
              <div
                className="absolute top-0 left-0 right-0 h-6 bg-background/90 backdrop-blur-md border-b border-border/40 flex items-center justify-center pointer-events-none z-20"
                title={t('notificationRedactedHint')}
              >
                <span className="text-[10px] text-muted-foreground font-mono font-medium tracking-tight">
                  {t('notificationRedacted')}
                </span>
              </div>
            )}

            {/* Touch Click Feedback Ripple */}
            {touchFeedback && (
              <div
                className="absolute w-6 h-6 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/40 border border-primary pointer-events-none animate-ping z-30"
                style={{ left: touchFeedback.x, top: touchFeedback.y }}
              />
            )}

            {!isViewMode && imageSize.width > 0 && (
              <ElementOverlay
                refs={scopedViewData.refs}
                selectedRefId={selectedElement?.refId ?? null}
                onSelect={handleElementSelect}
                imageNaturalWidth={imageSize.width}
                imageNaturalHeight={imageSize.height}
              />
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center text-center p-6 text-muted-foreground gap-3">
            <Smartphone className="w-10 h-10 stroke-1 opacity-50 text-emerald-500" />
            <div>
              <p className="text-sm font-medium text-foreground">{t('waitingForDevice')}</p>
              <p className="text-xs text-muted-foreground mt-1">{t('waitingHint')}</p>
            </div>
            <button
              type="button"
              onClick={() => void fetchSnapshot(false)}
              disabled={isSnapshotLoading}
              className={cn(
                'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-colors',
                'bg-primary text-primary-foreground hover:bg-primary/90',
                'disabled:opacity-50',
              )}
            >
              <RefreshCw className={cn('w-3.5 h-3.5', isSnapshotLoading && 'animate-spin')} />
              {t('refresh')}
            </button>
          </div>
        )}
      </div>

      <DeviceInstructionInput
        selectedRefId={selectedElement?.refId ?? null}
        selectedInfo={selectedElement?.info ?? null}
        instructionText={instructionText}
        onInstructionChange={setInstructionText}
        onSubmit={onSendInstruction}
        onClearSelection={clearSelection}
      />
    </div>
  );
};

export default DeviceLiveView;
