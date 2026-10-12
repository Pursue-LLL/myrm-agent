'use client';

/**
 * [INPUT]
 * - navigator.onLine & online/offline events
 * - Connection status props (isConnecting, hasError, onRetry, hostName, isStandalone)
 *
 * [OUTPUT]
 * - MobileShellStatusBar: Native shell status perception bar with offline/reconnect HUD & retry trigger
 *
 * [POS]
 * Mobile PWA native shell connectivity perception layer at the top safe-area boundary.
 */

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconActivity,
  IconAlertTriangle,
  IconCheck,
  IconLoader,
  IconShieldCheck,
  IconZap,
} from '@/components/features/icons/PremiumIcons';

export interface MobileShellStatusBarProps {
  isConnecting?: boolean;
  hasError?: boolean;
  onRetry?: () => void;
  hostName?: string;
  isStandalone?: boolean;
}

export function MobileShellStatusBar({
  isConnecting = false,
  hasError = false,
  onRetry,
  hostName,
  isStandalone = false,
}: MobileShellStatusBarProps) {
  const t = useTranslations('mobileShell');
  const [isOnline, setIsOnline] = useState<boolean>(() =>
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );
  const [detailsExpanded, setDetailsExpanded] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const isDisconnected = !isOnline || hasError;

  return (
    <header
      role="banner"
      aria-label={t('statusBanner')}
      className="fixed inset-x-0 top-0 z-50 pt-[env(safe-area-inset-top,0px)] transition-all duration-300"
    >
      {isDisconnected ? (
        <div className="flex items-center justify-between border-b border-rose-500/30 bg-rose-950/90 px-4 py-2 text-xs text-rose-200 backdrop-blur-md shadow-sm">
          <div className="flex items-center gap-2">
            <IconAlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
            <span className="font-medium">
              {!isOnline ? t('offlineNotice') : t('connectionErrorNotice')}
            </span>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="flex items-center gap-1 rounded-md bg-rose-600/40 px-2 py-1 text-[11px] font-semibold text-rose-100 hover:bg-rose-600/60 transition-colors"
            >
              <IconZap className="h-3 w-3" />
              <span>{t('retryButton')}</span>
            </button>
          )}
        </div>
      ) : isConnecting ? (
        <div className="flex items-center justify-center gap-2 border-b border-amber-500/30 bg-amber-950/80 px-4 py-1.5 text-xs text-amber-200 backdrop-blur-md">
          <IconLoader className="h-3.5 w-3.5 animate-spin text-amber-400" />
          <span>{t('connectingNotice')}</span>
        </div>
      ) : (
        <div className="mx-auto flex max-w-lg items-center justify-between px-4 py-1">
          <button
            type="button"
            onClick={() => setDetailsExpanded((prev) => !prev)}
            className="flex items-center gap-1.5 rounded-full border border-border/40 bg-background/80 px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground backdrop-blur-md shadow-xs hover:text-foreground transition-all"
            aria-expanded={detailsExpanded}
            aria-label={t('networkDetailsToggle')}
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            <span>{hostName ? `${t('connectedTo')} ${hostName}` : t('connectedReady')}</span>
            {isStandalone && (
              <span className="ml-1 rounded bg-primary/10 px-1 py-0.2 text-[9px] font-semibold text-primary">
                PWA
              </span>
            )}
          </button>
        </div>
      )}

      {detailsExpanded && !isDisconnected && !isConnecting && (
        <div className="mx-auto mt-1 max-w-lg rounded-xl border border-border/60 bg-background/95 p-3 text-xs shadow-lg backdrop-blur-md">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <div className="flex items-center gap-1.5 font-semibold text-foreground">
              <IconShieldCheck className="h-4 w-4 text-emerald-500" />
              <span>{t('thinClientSecurity')}</span>
            </div>
            <button
              type="button"
              onClick={() => setDetailsExpanded(false)}
              className="text-[11px] text-muted-foreground hover:text-foreground"
            >
              {t('close')}
            </button>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
            <div>
              <span className="block font-medium text-foreground">{t('modeLabel')}</span>
              <span>{isStandalone ? t('standaloneApp') : t('browserShell')}</span>
            </div>
            <div>
              <span className="block font-medium text-foreground">{t('loadProfile')}</span>
              <span>{t('zeroLocalExecution')}</span>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
