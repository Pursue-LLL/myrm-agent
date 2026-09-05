'use client';

import { memo, useState, useCallback, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { AlertCircle, Zap, ExternalLink, Copy, Check, Loader2, X, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import useProviderStore from '@/store/useProviderStore';
import { hasUsableProviderAuth } from '@/store/config/providerTypes';
import { startXaiOAuth, pollXaiOAuth } from '@/services/xai-oauth';
import {
  startProviderOAuth,
  pollProviderOAuth,
  fetchProviderOAuthStatus,
  type ProviderOAuthProvider,
} from '@/services/provider-oauth';

interface DeviceCodeState {
  providerId: string;
  providerName: string;
  userCode: string;
  verificationUri: string;
  verificationUriComplete?: string;
  isPolling: boolean;
  isSuccess: boolean;
  isPkce?: boolean;
  error?: string;
}

const PROVIDER_SUBSCRIPTION_DEFAULTS: Record<string, { primary: string; models: string[] }> = {
  copilot: { primary: 'gpt-4o', models: ['gpt-4o', 'claude-3-5-sonnet'] },
  openai: { primary: 'gpt-4o', models: ['gpt-4o', 'o1', 'o3-mini'] },
  xai: { primary: 'grok-2', models: ['grok-2', 'grok-2-mini', 'grok-beta'] },
  anthropic: {
    primary: 'claude-3-5-sonnet-20241022',
    models: ['claude-3-5-sonnet-20241022', 'claude-3-7-sonnet-20250219'],
  },
};

const SUBSCRIPTION_ENTRIES: Array<{
  id: ProviderOAuthProvider;
  nameKey: 'subscriptionCopilot' | 'subscriptionOpenai' | 'subscriptionXai' | 'subscriptionClaude';
  sub: string;
}> = [
  { id: 'copilot', nameKey: 'subscriptionCopilot', sub: 'GPT-4o, Claude 3.5 Sonnet' },
  { id: 'openai', nameKey: 'subscriptionOpenai', sub: 'GPT-4o, o1, o3-mini' },
  { id: 'xai', nameKey: 'subscriptionXai', sub: 'Grok-2, Grok-Vision' },
  { id: 'anthropic', nameKey: 'subscriptionClaude', sub: 'Claude 3.5 Sonnet, Claude 3.7 Sonnet' },
];

const NoProviderBanner = memo(() => {
  const t = useTranslations('chat');
  const router = useRouter();
  const isInitialized = useProviderStore((s) => s.isInitialized);
  const providers = useProviderStore((s) => s.providers);
  const updateProvider = useProviderStore((s) => s.updateProvider);
  const setBaseModel = useProviderStore((s) => s.setBaseModel);
  const defaultModelConfig = useProviderStore((s) => s.defaultModelConfig);

  const hasEnabledProvider = providers.some((p) => p.isEnabled && hasUsableProviderAuth(p));

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeFlow, setActiveFlow] = useState<DeviceCodeState | null>(null);
  const [copied, setCopied] = useState(false);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  const cleanupPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => cleanupPolling();
  }, [cleanupPolling]);

  const onAuthSuccess = useCallback(
    (providerId: string) => {
      cleanupPolling();
      const defaults = PROVIDER_SUBSCRIPTION_DEFAULTS[providerId] || {
        primary: 'gpt-4o',
        models: ['gpt-4o'],
      };
      const targetModel = defaults.primary;
      const models = defaults.models;

      // 1. 原子化启用 Provider，标记 oauthConnected，并补齐模型列表
      const existingProvider = providers.find((p) => p.id === providerId);
      const mergedAvailable = Array.from(new Set([...(existingProvider?.availableModels || []), ...models]));
      const mergedEnabled = Array.from(new Set([...(existingProvider?.enabledModels || []), targetModel]));

      updateProvider(providerId, {
        isEnabled: true,
        oauthConnected: true,
        availableModels: mergedAvailable,
        enabledModels: mergedEnabled,
      });

      // 2. 如果未绑定主模型槽位，自动绑定官方主力推荐模型
      if (!defaultModelConfig.baseModel?.primary) {
        setBaseModel({ providerId, model: targetModel });
      }
      setActiveFlow((prev) => (prev ? { ...prev, isPolling: false, isSuccess: true } : null));
      setTimeout(() => {
        setIsModalOpen(false);
        setActiveFlow(null);
      }, 1500);
    },
    [cleanupPolling, updateProvider, defaultModelConfig, setBaseModel, providers],
  );

  const handleStartOAuth = useCallback(
    async (providerType: 'xai' | ProviderOAuthProvider) => {
      cleanupPolling();
      setActiveFlow(null);
      try {
        if (providerType === 'xai') {
          const res = await startXaiOAuth();
          const flow: DeviceCodeState = {
            providerId: 'xai',
            providerName: 'xAI SuperGrok',
            userCode: res.user_code,
            verificationUri: res.verification_uri,
            verificationUriComplete: res.verification_uri_complete,
            isPolling: true,
            isSuccess: false,
          };
          setActiveFlow(flow);

          pollTimerRef.current = setInterval(
            async () => {
              try {
                const pollRes = await pollXaiOAuth(res.user_code);
                if (pollRes.status === 'success') {
                  onAuthSuccess('xai');
                } else if (pollRes.status === 'expired' || pollRes.status === 'denied') {
                  cleanupPolling();
                  setActiveFlow((prev) =>
                    prev ? { ...prev, isPolling: false, error: pollRes.error || pollRes.status } : null,
                  );
                }
              } catch {
                // 轮询静默重试
              }
            },
            (res.interval || 5) * 1000,
          );
        } else {
          const res = await startProviderOAuth(providerType);
          if (res.user_code && res.verification_uri) {
            const flow: DeviceCodeState = {
              providerId: providerType,
              providerName: providerType === 'copilot' ? 'GitHub Copilot' : 'ChatGPT Plus / Pro',
              userCode: res.user_code,
              verificationUri: res.verification_uri,
              isPolling: true,
              isSuccess: false,
            };
            setActiveFlow(flow);

            pollTimerRef.current = setInterval(
              async () => {
                try {
                  const pollRes = await pollProviderOAuth(providerType, res.user_code!);
                  if (pollRes.status === 'success') {
                    onAuthSuccess(providerType);
                  } else if (pollRes.status === 'expired' || pollRes.status === 'denied') {
                    cleanupPolling();
                    setActiveFlow((prev) =>
                      prev ? { ...prev, isPolling: false, error: pollRes.error || pollRes.status } : null,
                    );
                  }
                } catch {
                  // 轮询静默重试
                }
              },
              (res.interval || 5) * 1000,
            );
          } else if (res.authorize_url) {
            const flow: DeviceCodeState = {
              providerId: providerType,
              providerName: 'Claude Pro / Max',
              userCode: '',
              verificationUri: res.authorize_url,
              isPolling: true,
              isSuccess: false,
              isPkce: true,
            };
            setActiveFlow(flow);
            window.open(res.authorize_url, '_blank', 'noopener,noreferrer');

            pollTimerRef.current = setInterval(async () => {
              try {
                const s = await fetchProviderOAuthStatus(providerType);
                if (s.connected) {
                  onAuthSuccess(providerType);
                }
              } catch {
                // 轮询静默重试
              }
            }, 3000);
          }
        }
      } catch (err: unknown) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to start authorization';
        setActiveFlow((prev) => (prev ? { ...prev, isPolling: false, error: errorMsg } : null));
      }
    },
    [cleanupPolling, onAuthSuccess],
  );

  const handleCopyCode = useCallback(() => {
    if (activeFlow?.userCode) {
      navigator.clipboard.writeText(activeFlow.userCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [activeFlow?.userCode]);

  if (!isInitialized || hasEnabledProvider) {
    return null;
  }

  return (
    <>
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

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="relative w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl dark:border-zinc-800 dark:bg-zinc-900 transition-all">
            <button
              onClick={() => {
                cleanupPolling();
                setIsModalOpen(false);
                setActiveFlow(null);
              }}
              className="absolute right-4 top-4 rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-600 dark:hover:text-zinc-200 transition-colors"
              aria-label="Close"
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

            {!activeFlow ? (
              <div className="grid grid-cols-1 gap-2.5">
                {SUBSCRIPTION_ENTRIES.map((entry) => (
                  <button
                    key={entry.id}
                    type="button"
                    onClick={() => handleStartOAuth(entry.id)}
                    className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-800 hover:border-emerald-500/50 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-all text-left group"
                  >
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200 group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                        {t(entry.nameKey)}
                      </span>
                      <span className="text-xs text-zinc-400">{entry.sub}</span>
                    </div>
                    <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400 px-2.5 py-1 rounded-md bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900">
                      {t('subscriptionConnectBtn')}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-4 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/30">
                {activeFlow.isSuccess ? (
                  <div className="flex flex-col items-center gap-2 text-emerald-600 dark:text-emerald-400 my-4 animate-in zoom-in-95">
                    <Check className="h-8 w-8" />
                    <span className="text-sm font-semibold">{t('subscriptionConnected')}</span>
                  </div>
                ) : activeFlow.isPkce ? (
                  <>
                    <span className="text-xs text-zinc-600 dark:text-zinc-300 mb-4 text-center leading-relaxed">
                      {t('subscriptionPkceNotice', { providerName: activeFlow.providerName })}
                    </span>

                    <div className="flex items-center gap-2 w-full mb-4">
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => window.open(activeFlow.verificationUri, '_blank', 'noopener,noreferrer')}
                        className="flex-1 gap-1.5 h-9 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 hover:bg-zinc-800 dark:hover:bg-white text-xs font-medium"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                        <span>{t('subscriptionPkceReopen')}</span>
                      </Button>
                    </div>

                    <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-500" />
                      <span>{t('subscriptionWaiting')}</span>
                    </div>

                    {activeFlow.error && (
                      <span className="text-xs text-rose-500 dark:text-rose-400 mt-2">{activeFlow.error}</span>
                    )}
                  </>
                ) : (
                  <>
                    <span className="text-xs text-zinc-500 dark:text-zinc-400 mb-2">
                      {t('subscriptionDeviceCodeHint')}
                    </span>
                    <div className="flex items-center gap-2 mb-4 bg-white dark:bg-zinc-900 px-4 py-2 rounded-lg border border-zinc-200 dark:border-zinc-700 font-mono text-lg font-bold tracking-widest text-zinc-800 dark:text-zinc-200">
                      <span>{activeFlow.userCode}</span>
                      <button
                        type="button"
                        onClick={handleCopyCode}
                        className="p-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition-colors ml-1"
                        title={t('subscriptionCopyCode')}
                      >
                        {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
                      </button>
                    </div>

                    <div className="flex items-center gap-2 w-full mb-3">
                      <Button
                        type="button"
                        size="sm"
                        onClick={() =>
                          window.open(activeFlow.verificationUriComplete || activeFlow.verificationUri, '_blank')
                        }
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

                    {activeFlow.error && (
                      <span className="text-xs text-rose-500 dark:text-rose-400 mt-2">{activeFlow.error}</span>
                    )}
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
