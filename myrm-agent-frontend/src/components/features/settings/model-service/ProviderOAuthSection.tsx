'use client';

import { memo, useState, useCallback, useEffect, useRef } from 'react';
import { useLocale } from 'next-intl';
import { Loader2, LogIn, LogOut, ExternalLink, Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  type ProviderOAuthProvider,
  type ProviderOAuthStatus,
  getProviderOAuthProviderByProviderId,
  getProviderOAuthConfig,
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
  const locale = useLocale();
  const oauthProvider = getProviderOAuthProviderByProviderId(providerId);

  const [status, setStatus] = useState<ProviderOAuthStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [isPkceWaiting, setIsPkceWaiting] = useState(false);
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
    setIsPkceWaiting(false);
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
          toast.error(locale === 'zh' ? '授权超时，请重试' : 'Authorization timed out');
          return;
        }

        try {
          const result = await pollProviderOAuth(provider, userCode);
          if (result.status === 'success') {
            cleanup();
            const refreshed = await fetchProviderOAuthStatus(provider);
            setStatus(refreshed);
            onOAuthStatusChange?.(true, refreshed.available_models);
            toast.success(
              locale === 'zh'
                ? `${getProviderOAuthConfig(provider).nameZh} 连接成功`
                : `${getProviderOAuthConfig(provider).name} connected successfully`,
            );
            return;
          }
          if (result.status === 'expired' || result.status === 'denied') {
            cleanup();
            toast.error(
              locale === 'zh'
                ? `授权${result.status === 'expired' ? '过期' : '被拒绝'}，请重试`
                : `Authorization ${result.status}. Please try again.`,
            );
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
    [cleanup, locale, onOAuthStatusChange],
  );

  const handleConnect = useCallback(async () => {
    if (!oauthProvider) {
      return;
    }
    const config = getProviderOAuthConfig(oauthProvider);
    setIsLoading(true);

    try {
      const result = await startProviderOAuth(oauthProvider);

      if (config.flow === 'pkce' && result.authorize_url) {
        window.open(result.authorize_url, '_blank', 'noopener,noreferrer');
        setIsLoading(false);
        setIsPkceWaiting(true);
        pollStartRef.current = Date.now();
        const check = async () => {
          if (Date.now() - pollStartRef.current > POLL_TIMEOUT_MS) {
            cleanup();
            toast.error(locale === 'zh' ? '授权超时，请重试' : 'Authorization timed out');
            return;
          }
          try {
            const s = await fetchProviderOAuthStatus(oauthProvider);
            if (s.connected) {
              cleanup();
              setStatus(s);
              onOAuthStatusChange?.(true, s.available_models);
              toast.success(locale === 'zh' ? `${config.nameZh} 连接成功` : `${config.name} connected successfully`);
              return;
            }
          } catch {}
          pollTimerRef.current = setTimeout(check, 2000);
        };
        pollTimerRef.current = setTimeout(check, 3000);
      } else if (result.user_code && result.verification_uri) {
        setDeviceCode(result.user_code);
        setVerificationUri(result.verification_uri);
        setIsLoading(false);
        window.open(result.verification_uri, '_blank', 'noopener,noreferrer');
        startPoll(oauthProvider, result.user_code);
      }
    } catch {
      setIsLoading(false);
      toast.error(locale === 'zh' ? '启动授权失败，请重试' : 'Failed to start authorization');
    }
  }, [oauthProvider, startPoll, cleanup, locale, onOAuthStatusChange]);

  const handleDisconnect = useCallback(async () => {
    if (!oauthProvider) {
      return;
    }
    try {
      await disconnectProviderOAuth(oauthProvider);
      setStatus((prev) => (prev ? { ...prev, connected: false } : null));
      onOAuthStatusChange?.(false);
      toast.success(locale === 'zh' ? 'OAuth 已断开' : 'OAuth disconnected');
    } catch {
      toast.error(locale === 'zh' ? '断开失败' : 'Failed to disconnect');
    }
  }, [oauthProvider, locale, onOAuthStatusChange]);

  if (!oauthProvider) {
    return null;
  }

  const config = getProviderOAuthConfig(oauthProvider);
  const isConnected = status?.connected ?? false;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-foreground uppercase tracking-wide">
          {locale === 'zh' ? '订阅登录' : 'Subscription Login'}
        </h4>
        {isConnected && (
          <span className="flex items-center gap-1.5 text-xs text-emerald-600">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            {locale === 'zh' ? '已连接' : 'Connected'}
          </span>
        )}
      </div>

      <div className="p-4 bg-background/50 rounded-xl border border-border/50">
        {isPkceWaiting ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              {locale === 'zh' ? '请在浏览器中完成授权...' : 'Complete authorization in your browser...'}
            </div>
            <button
              onClick={cleanup}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all"
            >
              {locale === 'zh' ? '取消' : 'Cancel'}
            </button>
          </div>
        ) : isPolling && deviceCode ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {locale === 'zh'
                ? '请在浏览器中输入以下验证码完成授权：'
                : 'Enter this code in your browser to complete authorization:'}
            </p>
            <div className="flex items-center gap-3">
              <code className="px-4 py-2 bg-muted rounded-lg text-lg font-mono font-bold tracking-widest select-all">
                {deviceCode}
              </code>
              <button
                onClick={handleCopyCode}
                className="p-2 rounded-lg border border-border/50 hover:bg-muted transition-colors"
                title={locale === 'zh' ? '复制验证码' : 'Copy code'}
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
                {locale === 'zh' ? '打开验证页面' : 'Open verification page'}
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              {locale === 'zh' ? '等待授权完成...' : 'Waiting for authorization...'}
            </div>
            <button
              onClick={cleanup}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all"
            >
              {locale === 'zh' ? '取消' : 'Cancel'}
            </button>
          </div>
        ) : isConnected ? (
          <div className="space-y-3">
            <p className="text-sm text-foreground">
              {locale === 'zh'
                ? `已通过 ${config.nameZh} 登录。${hasApiKey ? 'API Key 优先使用，OAuth 作为备选。' : '将使用订阅额度进行 AI 调用。'}`
                : `Logged in via ${config.name}. ${hasApiKey ? 'API Key takes priority; OAuth is fallback.' : 'Your subscription quota will be used for AI calls.'}`}
            </p>
            {status?.expires_at && (
              <p className="text-xs text-muted-foreground">
                {locale === 'zh' ? '令牌过期：' : 'Token expires: '}
                {new Date(status.expires_at * 1000).toLocaleString()}
              </p>
            )}
            <button
              onClick={handleDisconnect}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-red-500/30 text-red-500 hover:border-red-500 hover:bg-red-500/10 transition-all"
            >
              <LogOut className="w-3.5 h-3.5" />
              {locale === 'zh' ? '断开连接' : 'Disconnect'}
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {locale === 'zh'
                ? `使用 ${config.nameZh} 登录，无需 API Key 即可使用 AI 模型。`
                : `Log in with your ${config.name} subscription to use AI models without an API Key.`}
            </p>
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
              {locale === 'zh' ? `使用 ${config.nameZh} 登录` : `Log in with ${config.name}`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
});

ProviderOAuthSection.displayName = 'ProviderOAuthSection';

export default ProviderOAuthSection;
