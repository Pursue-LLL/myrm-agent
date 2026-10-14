'use client';

import { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, LogIn, LogOut, ExternalLink, Copy, Check, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useCopyFeedback } from '@/hooks/shared/useCopyFeedback';
import { useXaiDeviceLogin } from '@/hooks/shared/useXaiDeviceLogin';
import { disconnectProviderOAuth, getProviderOAuthProviderByProviderId } from '@/services/provider-oauth';
import { disconnectProviderSubscription } from '@/store/config/providerSubscription';
import { toast } from 'sonner';

interface ProviderOAuthSectionProps {
  providerId: string;
  /** The provider's persisted login state; the section never asks the server for it. */
  connected: boolean;
  hasApiKey: boolean;
}

const ProviderOAuthSection = memo<ProviderOAuthSectionProps>(({ providerId, connected, hasApiKey }) => {
  const t = useTranslations('settings.modelService.oauth');
  const oauthProvider = getProviderOAuthProviderByProviderId(providerId);

  const { copied, copy } = useCopyFeedback();

  const { phase, userCode, verificationUrl, start, cancel } = useXaiDeviceLogin({
    onConnected: () => toast.success(t('toast.connected')),
    onFailed: (reason) => toast.error(t(`toast.${reason}`)),
  });

  const handleCopyCode = useCallback(() => {
    if (userCode) {
      void copy(userCode);
    }
  }, [copy, userCode]);

  const handleConnect = useCallback(async () => {
    const url = await start();
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }, [start]);

  const handleDisconnect = useCallback(async () => {
    if (!oauthProvider) {
      return;
    }
    try {
      await disconnectProviderOAuth(oauthProvider);
    } catch {
      toast.error(t('toast.disconnectFailed'));
      return;
    }
    disconnectProviderSubscription(providerId);
    toast.success(t('toast.disconnected'));
  }, [oauthProvider, providerId, t]);

  if (!oauthProvider) {
    return null;
  }

  const isStarting = phase === 'starting';

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-foreground uppercase tracking-wide">{t('title')}</h4>
        {connected && (
          <span className="flex items-center gap-1.5 text-xs text-emerald-600">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            {t('connected')}
          </span>
        )}
      </div>

      <div className="flex items-start gap-3 p-3.5 rounded-xl border border-sky-500/30 bg-sky-500/10 dark:bg-sky-500/15 text-sky-900 dark:text-sky-200">
        <ShieldAlert className="w-5 h-5 text-sky-600 dark:text-sky-400 shrink-0 mt-0.5" />
        <div className="space-y-1 text-xs leading-relaxed">
          <p className="font-semibold text-sky-950 dark:text-sky-100">{t('noticeTitle')}</p>
          <p className="text-sky-900/90 dark:text-sky-200/90">{t('noticeBody')}</p>
        </div>
      </div>

      <div className="p-4 bg-background/50 rounded-xl border border-border/50">
        {phase === 'waiting' && userCode ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t('deviceCodeHint')}</p>
            <div className="flex items-center gap-3">
              <code className="px-4 py-2 bg-muted rounded-lg text-lg font-mono font-bold tracking-widest select-all">
                {userCode}
              </code>
              <button
                onClick={handleCopyCode}
                className="p-2 rounded-lg border border-border/50 hover:bg-muted transition-colors"
                title={t('copyCode')}
                aria-label={t('copyCode')}
              >
                {copied ? (
                  <Check className="w-4 h-4 text-emerald-500" />
                ) : (
                  <Copy className="w-4 h-4 text-muted-foreground" />
                )}
              </button>
            </div>
            {verificationUrl && (
              <a
                href={verificationUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
              >
                {t('openVerificationPage')}
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              {t('waiting')}
            </div>
            <button
              onClick={cancel}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all"
            >
              {t('cancel')}
            </button>
          </div>
        ) : connected ? (
          <div className="space-y-3">
            <p className="text-sm text-foreground">{t(hasApiKey ? 'connectedWithApiKey' : 'connectedWithQuota')}</p>
            <button
              onClick={handleDisconnect}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-red-500/30 text-red-500 hover:border-red-500 hover:bg-red-500/10 transition-all"
            >
              <LogOut className="w-3.5 h-3.5" />
              {t('disconnect')}
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t('loginPrompt')}</p>
            <button
              onClick={handleConnect}
              disabled={isStarting}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-all',
                'bg-primary text-primary-foreground hover:bg-primary/90',
                isStarting && 'opacity-60 cursor-wait',
              )}
            >
              {isStarting ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
              {t('loginButton')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
});

ProviderOAuthSection.displayName = 'ProviderOAuthSection';

export default ProviderOAuthSection;
