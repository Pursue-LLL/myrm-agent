'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { MonitorPlay, X, RefreshCw } from 'lucide-react';
import { VisualDesktop } from './VisualDesktop';
import { useFeatureEntitlements } from '@/hooks/useFeatureEntitlements';
import { isSandbox } from '@/lib/deploy-mode';
import { buildVncWebSocketUrl, fetchSandboxVncUrl, fetchUserSandbox } from '@/lib/cp-sandbox';

export const VisualDesktopToggle = () => {
  const t = useTranslations('billing.vnc');
  const [isOpen, setIsOpen] = useState(false);
  const [wsUrl, setWsUrl] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoadingUrl, setIsLoadingUrl] = useState(false);
  const { canUseVnc, isLoading: entitlementsLoading } = useFeatureEntitlements();
  const sandboxMode = isSandbox();

  const loadVnc = useCallback(
    async (isMounted: { current: boolean }) => {
      setIsLoadingUrl(true);
      setLoadError(null);
      try {
        const sandbox = await fetchUserSandbox();
        if (!sandbox) {
          throw new Error('no_sandbox');
        }
        const vnc = await fetchSandboxVncUrl(sandbox.id);
        const url = buildVncWebSocketUrl(vnc.vnc_url, vnc.token);
        if (isMounted.current) {
          setWsUrl(url);
        }
      } catch {
        if (isMounted.current) {
          setLoadError(t('loadFailed'));
          setWsUrl('');
        }
      } finally {
        if (isMounted.current) {
          setIsLoadingUrl(false);
        }
      }
    },
    [t],
  );

  const handleReconnect = useCallback(() => {
    void loadVnc({ current: true });
  }, [loadVnc]);

  useEffect(() => {
    if (!isOpen || !sandboxMode) {
      return;
    }

    const isMounted = { current: true };
    void loadVnc(isMounted);

    return () => {
      isMounted.current = false;
    };
  }, [isOpen, sandboxMode, loadVnc]);

  if (sandboxMode && !entitlementsLoading && !canUseVnc) {
    return null;
  }

  const effectiveWsUrl = sandboxMode ? wsUrl : 'ws://localhost:6080';

  return (
    <>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-24 right-6 p-3 bg-primary text-primary-foreground rounded-full shadow-lg hover:bg-primary/90 transition-colors z-50 flex items-center justify-center max-sm:bottom-20 max-sm:right-4"
        title={t('toggleTitle')}
        aria-label={t('toggleTitle')}
      >
        <MonitorPlay size={24} />
      </button>

      {isOpen && (
        <div className="fixed bottom-36 right-6 w-[min(800px,calc(100vw-2rem))] h-[min(600px,calc(100vh-8rem))] bg-background rounded-xl shadow-2xl overflow-hidden z-50 border border-border flex flex-col max-sm:bottom-32 max-sm:right-4 max-sm:left-4">
          <div className="flex justify-between items-center px-4 py-2 bg-muted border-b border-border">
            <span className="text-foreground font-medium flex items-center gap-2 text-sm sm:text-base">
              <span className="w-2 h-2 rounded-full bg-destructive animate-pulse" />
              {t('panelTitle')}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={handleReconnect}
                className="text-muted-foreground hover:text-foreground"
                aria-label={t('reconnect')}
                title={t('reconnect')}
              >
                <RefreshCw size={16} />
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="text-muted-foreground hover:text-foreground"
                aria-label={t('close')}
              >
                <X size={20} />
              </button>
            </div>
          </div>
          <div className="flex-1 relative bg-muted/30">
            {sandboxMode && isLoadingUrl ? (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
                {t('connecting')}
              </div>
            ) : null}
            {sandboxMode && loadError ? (
              <div className="absolute inset-0 flex flex-col gap-4 items-center justify-center px-6 text-center text-sm text-destructive">
                <p>{loadError}</p>
                <button
                  onClick={handleReconnect}
                  className="px-4 py-2 bg-primary text-primary-foreground font-medium rounded hover:bg-primary/90 transition-colors"
                >
                  {t('reconnect')}
                </button>
              </div>
            ) : null}
            {!loadError && effectiveWsUrl && !isLoadingUrl ? (
              <VisualDesktop wsUrl={effectiveWsUrl} className="w-full h-full" onReconnect={handleReconnect} />
            ) : null}
          </div>
        </div>
      )}
    </>
  );
};
