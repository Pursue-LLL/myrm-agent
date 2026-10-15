'use client';

import { memo, useState, useCallback, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { AlertCircle, Zap, ExternalLink, Copy, Check, Loader2, X, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { useCopyFeedback } from '@/hooks/shared/useCopyFeedback';
import { useXaiDeviceLogin, type XaiLoginFailure } from '@/hooks/shared/useXaiDeviceLogin';
import useProviderStore from '@/store/useProviderStore';
import { hasUsableProviderAuth } from '@/store/config/providerTypes';

const CONNECTED_CLOSE_DELAY_MS = 1500;

const FAILURE_MESSAGE_KEYS = {
  startFailed: 'subscriptionFailedStart',
  expired: 'subscriptionFailedExpired',
  denied: 'subscriptionFailedDenied',
  timeout: 'subscriptionFailedTimeout',
} as const satisfies Record<XaiLoginFailure, string>;

const NoProviderBanner = memo(() => {
  const t = useTranslations('chat');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const isInitialized = useProviderStore((s) => s.isInitialized);
  const providers = useProviderStore((s) => s.providers);

  const hasEnabledProvider = providers.some((p) => p.isEnabled && hasUsableProviderAuth(p));

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [failure, setFailure] = useState<XaiLoginFailure | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { copied, copy } = useCopyFeedback();

  const handleConnected = useCallback(() => {
    setIsConnected(true);
    closeTimerRef.current = setTimeout(() => {
      setIsModalOpen(false);
      setIsConnected(false);
    }, CONNECTED_CLOSE_DELAY_MS);
  }, []);

  const { phase, userCode, verificationUrl, start, cancel } = useXaiDeviceLogin({
    onConnected: handleConnected,
    onFailed: setFailure,
  });

  useEffect(() => {
    return () => {
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

  const closeModal = useCallback(() => {
    cancel();
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
    }
    setIsModalOpen(false);
    setIsConnected(false);
    setFailure(null);
  }, [cancel]);

  const handleStart = useCallback(() => {
    setFailure(null);
    void start();
  }, [start]);

  const handleCopyCode = useCallback(() => {
    if (userCode) {
      void copy(userCode);
    }
  }, [copy, userCode]);

  const handleOpenVerification = useCallback(() => {
    if (verificationUrl) {
      window.open(verificationUrl, '_blank', 'noopener,noreferrer');
    }
  }, [verificationUrl]);

  // The dialog outlives the strip: a successful login enables the provider, which hides the strip at once, while the
  // confirmation inside the dialog still has to be seen.
  const isStripVisible = isInitialized && !hasEnabledProvider;
  if (!isStripVisible && !isModalOpen) {
    return null;
  }

  const copyLabel = copied ? t('subscriptionCopied') : t('subscriptionCopyCode');

  return (
    <>
      {isStripVisible && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 w-full rounded-xl border border-amber-200/80 bg-amber-50/70 p-4 dark:border-amber-900/40 dark:bg-amber-950/20 backdrop-blur-sm transition-all shadow-xs">
          <div className="flex items-center gap-3">
            <AlertCircle className="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
            <span className="text-sm font-medium text-amber-900 dark:text-amber-200">{t('noProviderBanner')}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setIsModalOpen(true)}
              className="h-8 gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-800 hover:bg-emerald-500/20 dark:text-emerald-300 dark:hover:bg-emerald-500/30 font-medium text-xs rounded-lg transition-colors"
            >
              <Zap className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
              <span>{t('subscriptionQuickConnect')}</span>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => router.push('/settings/models')}
              className="h-8 text-xs font-medium"
            >
              {t('noProviderAction')}
            </Button>
          </div>
        </div>
      )}

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="relative w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl dark:border-zinc-800 dark:bg-zinc-900 transition-all">
            <button
              onClick={closeModal}
              className="absolute right-4 top-4 rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-600 dark:hover:text-zinc-200 transition-colors"
              aria-label={tCommon('close')}
            >
              <X className="h-4 w-4" />
            </button>

            <div className="flex items-center gap-2 mb-1.5">
              <ShieldCheck className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
              <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                {t('subscriptionModalTitle')}
              </h3>
            </div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-5 leading-relaxed">
              {t('subscriptionModalDesc')}
            </p>

            {phase !== 'waiting' && !isConnected ? (
              <>
                <button
                  type="button"
                  onClick={handleStart}
                  disabled={phase === 'starting'}
                  className="flex w-full items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-800 hover:border-emerald-500/50 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-all text-left group disabled:cursor-wait disabled:opacity-70"
                >
                  <div className="flex flex-col">
                    <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200 group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                      {t('subscriptionXai')}
                    </span>
                    <span className="text-xs text-zinc-400">{t('subscriptionXaiSummary')}</span>
                  </div>
                  <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400 px-2.5 py-1 rounded-md bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900">
                    {phase === 'starting' ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      t('subscriptionConnectBtn')
                    )}
                  </span>
                </button>
                {failure && (
                  <p role="alert" className="mt-2 text-xs text-rose-500 dark:text-rose-400">
                    {t(FAILURE_MESSAGE_KEYS[failure])}
                  </p>
                )}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center p-4 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/30">
                {isConnected ? (
                  <div className="flex flex-col items-center gap-2 text-emerald-600 dark:text-emerald-400 my-4 animate-in zoom-in-95">
                    <Check className="h-8 w-8" />
                    <span className="text-sm font-semibold">{t('subscriptionConnected')}</span>
                  </div>
                ) : (
                  <>
                    <span className="text-xs text-zinc-500 dark:text-zinc-400 mb-2">
                      {t('subscriptionDeviceCodeHint')}
                    </span>
                    <div className="flex items-center gap-2 mb-4 bg-white dark:bg-zinc-900 px-4 py-2 rounded-lg border border-zinc-200 dark:border-zinc-700 font-mono text-lg font-bold tracking-widest text-zinc-800 dark:text-zinc-200">
                      <span>{userCode}</span>
                      <button
                        type="button"
                        onClick={handleCopyCode}
                        className="p-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition-colors ml-1"
                        title={copyLabel}
                        aria-label={copyLabel}
                      >
                        {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
                      </button>
                    </div>

                    <div className="flex items-center gap-2 w-full mb-3">
                      <Button
                        type="button"
                        size="sm"
                        onClick={handleOpenVerification}
                        className="flex-1 gap-1.5 h-9 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 hover:bg-zinc-800 dark:hover:bg-white text-xs font-medium"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                        <span>{t('subscriptionOpenAuth')}</span>
                      </Button>
                    </div>

                    <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-500" />
                      <span>{t('subscriptionWaiting')}</span>
                    </div>
                  </>
                )}
              </div>
            )}

            <div className="mt-5 pt-3 border-t border-zinc-100 dark:border-zinc-800/80">
              <p className="text-[11px] text-zinc-400 dark:text-zinc-500 leading-normal">{t('subscriptionNotice')}</p>
            </div>
          </div>
        </div>
      )}
    </>
  );
});

NoProviderBanner.displayName = 'NoProviderBanner';

export default NoProviderBanner;
