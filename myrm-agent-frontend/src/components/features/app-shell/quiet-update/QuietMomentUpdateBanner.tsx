'use client';

/**
 * 安静时刻「有更新可用」CTA 编排套件 - 悬浮横幅组件
 *
 * 在检测到纯净安静时刻时优雅浮现，支持直达升级、稍后提醒与版本跳过。
 */

import React, { useCallback } from 'react';
import { Sparkles, RefreshCw, Clock, X, ChevronRight } from 'lucide-react';
import { useQuietMomentUpdateStore } from './useQuietMomentUpdateStore';
import { formatDownloadSize } from './quietMomentUpdateEngine';

export interface QuietMomentUpdateBannerProps {
  onUpdateAction?: () => void | Promise<void>;
  onNavigateDetails?: () => void;
  className?: string;
}

export const QuietMomentUpdateBanner: React.FC<QuietMomentUpdateBannerProps> = ({
  onUpdateAction,
  onNavigateDetails,
  className = '',
}) => {
  const isOfferVisible = useQuietMomentUpdateStore((state) => state.isOfferVisible);
  const snapshot = useQuietMomentUpdateStore((state) => state.snapshot);
  const executeAction = useQuietMomentUpdateStore((state) => state.executeAction);
  const openDismissModal = useQuietMomentUpdateStore((state) => state.openDismissModal);
  const closeOffer = useQuietMomentUpdateStore((state) => state.closeOffer);

  const handleConfirmUpdate = useCallback(async () => {
    if (!onUpdateAction) {
      closeOffer();
      return;
    }
    await executeAction(onUpdateAction);
  }, [onUpdateAction, executeAction, closeOffer]);

  if (!isOfferVisible || !snapshot) {
    return null;
  }

  const formattedSize = formatDownloadSize(snapshot.downloadSizeMb);

  return (
    <output
      aria-live="polite"
      className={`fixed bottom-5 right-5 z-[9999] max-w-sm w-full bg-background/95 backdrop-blur-md border border-border shadow-xl rounded-2xl p-4 transition-all duration-300 animate-in fade-in slide-in-from-bottom-3 ${className}`}
      data-testid="quiet-moment-update-banner"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs font-semibold text-foreground tracking-tight">
                新版本可用
              </span>
              <span className="text-[11px] px-1.5 py-0.5 rounded-md bg-primary/15 text-primary font-mono font-medium">
                v{snapshot.version}
              </span>
              {snapshot.isCritical && (
                <span className="text-[10px] px-1 py-0.2 rounded bg-amber-500/15 text-amber-600 dark:text-amber-400 font-medium">
                  建议更新
                </span>
              )}
            </div>
            {snapshot.currentVersion && (
              <p className="text-[11px] text-muted-foreground mt-0.5">
                当前版本: v{snapshot.currentVersion}
                {formattedSize ? ` · ${formattedSize}` : ''}
              </p>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={closeOffer}
          className="text-muted-foreground/70 hover:text-foreground transition-colors p-1 rounded-lg hover:bg-muted/50"
          aria-label="关闭更新提示"
          data-testid="quiet-update-close-btn"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {snapshot.releaseNotes && (
        <div className="mt-2.5 text-xs text-muted-foreground line-clamp-2 leading-relaxed bg-muted/40 p-2 rounded-lg border border-border/40">
          {snapshot.releaseNotes}
        </div>
      )}

      <div className="mt-3.5 flex items-center justify-between gap-2 pt-1 border-t border-border/50">
        <div className="flex items-center gap-1.5">
          {onNavigateDetails && (
            <button
              type="button"
              onClick={onNavigateDetails}
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-0.5 px-2 py-1 rounded-md transition-colors"
              data-testid="quiet-update-details-btn"
            >
              <span>发行注记</span>
              <ChevronRight className="w-3 h-3" />
            </button>
          )}
          <button
            type="button"
            onClick={openDismissModal}
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 px-2 py-1 rounded-md transition-colors hover:bg-muted/40"
            data-testid="quiet-update-snooze-btn"
          >
            <Clock className="w-3 h-3" />
            <span>稍后</span>
          </button>
        </div>

        <button
          type="button"
          onClick={handleConfirmUpdate}
          className="text-xs font-medium px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-1.5 shadow-sm transition-all active:scale-[0.98]"
          data-testid="quiet-update-apply-btn"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>立即更新</span>
        </button>
      </div>
    </output>
  );
};
