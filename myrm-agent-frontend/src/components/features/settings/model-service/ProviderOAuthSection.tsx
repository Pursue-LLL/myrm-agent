'use client';

import { memo, useState, useCallback, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, LogIn, LogOut, ExternalLink, Copy, Check, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  type ProviderOAuthProvider,
  type ProviderOAuthStatus,
  getProviderOAuthProviderByProviderId,
  startProviderOAuth,
  pollProviderOAuth,
  fetchProviderOAuthStatus,
  disconnectProviderOAuth,
} from '@/services/provider-oauth';
import { toast } from 'sonner';

interface ProviderOAuthSectionProps {
  providerId: string;
  hasApiKey: boolean;
  onOAuthStatusChange?: (connected: boolean, availableModels?: string[]) => void;
}

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 600_000;

const ProviderOAuthSection = memo<ProviderOAuthSectionProps>(({ providerId, hasApiKey, onOAuthStatusChange }) => {
  const t = useTranslations('settings.modelService.oauth');
  const oauthProvider = getProviderOAuthProviderByProviderId(providerId);

  const [status, setStatus] = useState<ProviderOAuthStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [deviceCode, setDeviceCode] = useState<string | null>(null);
  const [verificationUri, setVerificationUri] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollStartRef = useRef<number>(0);

  const cleanup = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setIsPolling(false);
    setIsLoading(false);
    setDeviceCode(null);
    setVerificationUri(null);
  }, []);

  useEffect(() => {
    if (!oauthProvider) {
      return;
    }
    let cancelled = false;
    fetchProviderOAuthStatus(oauthProvider)
      .then((s) => {
        if (!cancelled) {
          setStatus(s);
          onOAuthStatusChange?.(s.connected, s.available_models);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [oauthProvider, onOAuthStatusChange]);

  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  const handleCopyCode = useCallback(async () => {
    if (!deviceCode) {
      return;
    }
    await navigator.clipboard.writeText(deviceCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [deviceCode]);

  const startPoll = useCallback(
    (provider: ProviderOAuthProvider, userCode: string) => {
      setIsPolling(true);
      pollStartRef.current = Date.now();

      const doPoll = async () => {
        if (Date.now() - pollStartRef.current > POLL_TIMEOUT_MS) {
          cleanup();
          toast.error(t('toast.timeout'));
          return;
        }

        try {
          const result = await pollProviderOAuth(provider, userCode);
          if (result.status === 'success') {
            cleanup();
            const refreshed = await fetchProviderOAuthStatus(provider);
            setStatus(refreshed);
            onOAuthStatusChange?.(true, refreshed.available_models);
            toast.success(t('toast.connected'));
            return;
          }
          if (result.status === 'expired' || result.status === 'denied') {
            cleanup();
            toast.error(t(result.status === 'expired' ? 'toast.expired' : 'toast.denied'));
            return;
          }
          const interval = result.slow_down ? POLL_INTERVAL_MS * 2 : POLL_INTERVAL_MS;
          pollTimerRef.current = setTimeout(doPoll, interval);
        } catch {
          pollTimerRef.current = setTimeout(doPoll, POLL_INTERVAL_MS);
        }
      };

      pollTimerRef.current = setTimeout(doPoll, POLL_INTERVAL_MS);
    },
    [cleanup, t, onOAuthStatusChange],
  );

  const handleConnect = useCallback(async () => {
    if (!oauthProvider) {
      return;
    }
    setIsLoading(true);

    try {
      const result = await startProviderOAuth(oauthProvider);
      if (!result.user_code || !result.verification_uri) {
        throw new Error('Incomplete authorization response');
      }
      setDeviceCode(result.user_code);
      setVerificationUri(result.verification_uri);
      setIsLoading(false);
      window.open(result.verification_uri, '_blank', 'noopener,noreferrer');
      startPoll(oauthProvider, result.user_code);
    } catch {
      setIsLoading(false);
      toast.error(t('toast.startFailed'));
    }
  }, [oauthProvider, startPoll, t]);

  const handleDisconnect = useCallback(async () => {
    if (!oauthProvider) {
      return;
    }
    try {
      await disconnectProviderOAuth(oauthProvider);
      setStatus((prev) => (prev ? { ...prev, connected: false } : null));
      onOAuthStatusChange?.(false);
      toast.success(t('toast.disconnected'));
    } catch {
      toast.error(t('toast.disconnectFailed'));
    }
  }, [oauthProvider, t, onOAuthStatusChange]);

  if (!oauthProvider) {
    return null;
  }

  const isConnected = status?.connected ?? false;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-foreground uppercase tracking-wide">{t('title')}</h4>
        {isConnected && (
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
        {isPolling && deviceCode ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t('deviceCodeHint')}</p>
            <div className="flex items-center gap-3">
              <code className="px-4 py-2 bg-muted rounded-lg text-lg font-mono font-bold tracking-widest select-all">
                {deviceCode}
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
            {verificationUri && (
              <a
                href={verificationUri}
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
              onClick={cleanup}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all"
            >
              {t('cancel')}
            </button>
          </div>
        ) : isConnected ? (
          <div className="space-y-3">
            <p className="text-sm text-foreground">{t(hasApiKey ? 'connectedWithApiKey' : 'connectedWithQuota')}</p>
            {status?.expires_at && (
              <p className="text-xs text-muted-foreground">
                {t('tokenExpires', { time: new Date(status.expires_at * 1000).toLocaleString() })}
              </p>
            )}
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
              disabled={isLoading}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-all',
                'bg-primary text-primary-foreground hover:bg-primary/90',
                isLoading && 'opacity-60 cursor-wait',
              )}
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
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
