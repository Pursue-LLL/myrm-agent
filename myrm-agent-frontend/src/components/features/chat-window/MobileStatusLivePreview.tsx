'use client';

import { Globe, Monitor, ChevronDown, Maximize2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { InspectorViewSnapshot } from '@/lib/approval/visualApprovalContext';

interface MobileStatusLivePreviewProps {
  browserViewData: InspectorViewSnapshot | null;
  desktopViewData: InspectorViewSnapshot | null;
  browserLoading: boolean;
  desktopLoading: boolean;
  previewTab: 'browser' | 'desktop';
  onPreviewTabChange: (tab: 'browser' | 'desktop') => void;
  previewCollapsed: boolean;
  onToggleCollapsed: () => void;
  lightboxSrc: string | null;
  onLightboxOpen: (src: string) => void;
  onLightboxClose: () => void;
}

export function MobileStatusLivePreview({
  browserViewData,
  desktopViewData,
  browserLoading,
  desktopLoading,
  previewTab,
  onPreviewTabChange,
  previewCollapsed,
  onToggleCollapsed,
  lightboxSrc,
  onLightboxOpen,
  onLightboxClose,
}: MobileStatusLivePreviewProps) {
  const t = useTranslations('agent.mobileCommand');

  if (!browserViewData && !desktopViewData) return null;

  const hasBoth = Boolean(browserViewData) && Boolean(desktopViewData);
  const activeTab = hasBoth ? previewTab : browserViewData ? 'browser' : 'desktop';
  const activeData = activeTab === 'browser' ? browserViewData : desktopViewData;
  const isLoading = activeTab === 'browser' ? browserLoading : desktopLoading;
  const elapsed = activeData?.updatedAt ? Math.round((Date.now() - activeData.updatedAt) / 1000) : null;
  const timeLabel =
    elapsed !== null ? (elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m`) : '';

  const label =
    activeTab === 'browser'
      ? (activeData as InspectorViewSnapshot & { pageUrl?: string }).pageUrl
      : (activeData as InspectorViewSnapshot & { windowTitle?: string; appName?: string }).windowTitle ||
        (activeData as InspectorViewSnapshot & { appName?: string }).appName;

  return (
    <>
      <div className="bg-card rounded-2xl border overflow-hidden">
        <button
          type="button"
          className="w-full p-3 border-b bg-muted/20 flex items-center gap-2"
          onClick={onToggleCollapsed}
        >
          {activeTab === 'browser' ? (
            <Globe className="h-4 w-4 text-blue-500" />
          ) : (
            <Monitor className="h-4 w-4 text-green-500" />
          )}
          <h2 className="text-sm font-medium flex-1 text-left">{t('livePreview')}</h2>
          {timeLabel && (
            <span className="text-[10px] text-muted-foreground tabular-nums">{timeLabel}</span>
          )}
          <ChevronDown
            className={`h-4 w-4 text-muted-foreground transition-transform ${previewCollapsed ? '-rotate-90' : ''}`}
          />
        </button>
        {!previewCollapsed && (
          <div className="p-2 space-y-2">
            {hasBoth && (
              <div className="flex gap-1">
                <button
                  type="button"
                  className={`flex-1 text-xs py-1 rounded-lg transition-colors ${previewTab === 'browser' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground'}`}
                  onClick={() => onPreviewTabChange('browser')}
                >
                  <Globe className="inline h-3 w-3 mr-1" />
                  {t('browser')}
                </button>
                <button
                  type="button"
                  className={`flex-1 text-xs py-1 rounded-lg transition-colors ${previewTab === 'desktop' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground'}`}
                  onClick={() => onPreviewTabChange('desktop')}
                >
                  <Monitor className="inline h-3 w-3 mr-1" />
                  {t('desktop')}
                </button>
              </div>
            )}
            {isLoading && !activeData && (
              <div className="h-32 rounded-xl bg-muted/30 animate-pulse" />
            )}
            {activeData?.screenshotBase64 && (
              <button
                type="button"
                className="relative w-full rounded-xl overflow-hidden bg-muted/30 group"
                onClick={() =>
                  onLightboxOpen(`data:${activeData.mimeType};base64,${activeData.screenshotBase64}`)
                }
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`data:${activeData.mimeType};base64,${activeData.screenshotBase64}`}
                  alt={t('livePreview')}
                  className="w-full h-auto max-h-48 object-contain"
                  draggable={false}
                />
                <div className="absolute top-2 right-2 p-1 rounded-md bg-black/40 text-white opacity-0 group-hover:opacity-100 transition-opacity">
                  <Maximize2 className="h-3.5 w-3.5" />
                </div>
              </button>
            )}
            {label ? (
              <p className="text-[10px] text-muted-foreground truncate px-1">{label}</p>
            ) : null}
          </div>
        )}
      </div>

      {lightboxSrc && (
        <div
          className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center p-4"
          onClick={onLightboxClose}
          role="dialog"
          aria-modal="true"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={lightboxSrc}
            alt={t('livePreview')}
            className="max-w-full max-h-full object-contain rounded-lg"
            draggable={false}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
}
