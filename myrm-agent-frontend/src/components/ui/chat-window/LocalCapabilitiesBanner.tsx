'use client';

/**
 * Local capabilities onboarding: Ollama/LM Studio + SearXNG one-click setup.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils/classnameUtils';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import useChatStore from '@/store/useChatStore';
import {
  probeLocalCapabilities,
  PROBE_CACHE_TTL_MS,
  invalidateLocalCapabilitiesProbeCache,
  type ProbeLocalResponse,
} from '@/services/localCapabilitiesProbe';
import { startLocalSearxngAndRefreshProbe } from '@/services/searxngSetup';
import { isLocalMode } from '@/lib/deploy-mode';
import { buildQuickSearchConfig } from '@/store/config/quickSearchSetup';
import { getActiveSearchServiceConfig } from '@/store/config/searchService';
import type { SearchServiceType } from '@/store/config/types';
import { IconCheck, IconCpu, IconGlobe, IconLoader, IconSettings, IconGlow } from '@/components/ui/icons/PremiumIcons';
import SearxngInstallConsentDialog from '@/components/ui/settings/SearxngInstallConsentDialog';

type ProbeState = 'idle' | 'probing' | 'ready' | 'activated';

export default function LocalCapabilitiesBanner() {
  const t = useTranslations('chat.localCapabilities');
  const tModel = useTranslations('chat.localModelDetected');
  const router = useRouter();
  const [state, setState] = useState<ProbeState>('idle');
  const [probeResult, setProbeResult] = useState<ProbeLocalResponse | null>(null);
  const [activatingModel, setActivatingModel] = useState(false);
  const [activatingSearch, setActivatingSearch] = useState(false);
  const autoEnabledSearxngRef = useRef(false);
  const [startingSearxng, setStartingSearxng] = useState(false);
  const [searxngConsentOpen, setSearxngConsentOpen] = useState(false);
  const [activatedModelName, setActivatedModelName] = useState<string | null>(null);
  const [activatedSearch, setActivatedSearch] = useState<string | null>(null);

  const providers = useProviderStore((s) => s.providers);
  const updateProvider = useProviderStore((s) => s.updateProvider);
  const setBaseModel = useProviderStore((s) => s.setBaseModel);
  const setLiteModel = useProviderStore((s) => s.setLiteModel);
  const isInitialized = useProviderStore((s) => s.isInitialized);
  const sendMessage = useChatStore((s) => s.sendMessage);

  const searchServiceConfigs = useConfigStore((s) => s.searchServiceConfigs);
  const addSearchServiceConfig = useConfigStore((s) => s.addSearchServiceConfig);

  const hasEnabledProvider = providers.some(
    (p) => p.isEnabled && (p.apiKeys?.some((k) => k.isActive && k.key) || ['ollama', 'lm_studio'].includes(p.id)),
  );
  const searchConfigured = !!getActiveSearchServiceConfig(searchServiceConfigs);

  const needsCapabilities = isLocalMode() && isInitialized && (!hasEnabledProvider || !searchConfigured);

  useEffect(() => {
    if (!needsCapabilities) {
      setState('idle');
      return;
    }

    let cancelled = false;

    const runProbe = async (force: boolean) => {
      setState((prev) => (prev === 'idle' ? 'probing' : prev));
      const result = await probeLocalCapabilities(force);
      if (cancelled) return;
      setProbeResult(result);
      setState('ready');
    };

    void runProbe(false);
    const intervalId = window.setInterval(() => void runProbe(true), PROBE_CACHE_TTL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [needsCapabilities, isInitialized, hasEnabledProvider, searchConfigured]);

  const handleActivateModel = useCallback(
    async (provider: string, baseUrl: string, modelName: string) => {
      setActivatingModel(true);
      try {
        const providerId = provider === 'ollama' ? 'ollama' : 'lm_studio';
        updateProvider(providerId, {
          apiUrl: baseUrl,
          enabledModels: [modelName],
          isEnabled: true,
          apiKeys: [{ id: `local_${providerId}`, key: 'local', remark: 'Local provider', isActive: true }],
        });
        const selection = { providerId, model: modelName };
        setBaseModel(selection);
        setLiteModel(selection);
        setActivatedModelName(modelName);
        toast.success(tModel('useModel', { model: modelName.split(':')[0] }));
      } catch {
        toast.error(t('modelActivateFailed'));
      } finally {
        setActivatingModel(false);
      }
    },
    [updateProvider, setBaseModel, setLiteModel, t, tModel],
  );

  const handleEnableSearch = useCallback(
    (service: SearchServiceType, apiBase?: string) => {
      setActivatingSearch(true);
      try {
        addSearchServiceConfig(buildQuickSearchConfig(service, apiBase));
        setActivatedSearch(service);
        toast.success(t('searchEnabled', { service: 'SearXNG' }));
      } catch {
        toast.error(t('searchEnableFailed'));
      } finally {
        setActivatingSearch(false);
      }
    },
    [addSearchServiceConfig, t],
  );

  const handleTryDemo = useCallback(() => {
    sendMessage(tModel('tryDemo'));
  }, [tModel, sendMessage]);

  const handleStartSearxngDocker = useCallback(async (): Promise<boolean> => {
    setStartingSearxng(true);
    try {
      const { startResult, probe } = await startLocalSearxngAndRefreshProbe();
      setProbeResult(probe);
      invalidateLocalCapabilitiesProbeCache();
      if (!startResult.available) {
        toast.error(t('startSearxngFailed'));
        return false;
      }
      const hit = probe.search?.find((s) => s.provider === 'searxng' && s.available);
      if (hit) {
        handleEnableSearch('searxng', hit.base_url || probe.recommended_searxng_url || 'http://127.0.0.1:8081');
      }
      return true;
    } catch {
      toast.error(t('startSearxngFailed'));
      return false;
    } finally {
      setStartingSearxng(false);
    }
  }, [handleEnableSearch, t]);

  const searxngHit = probeResult?.search?.find((s) => s.provider === 'searxng' && s.available);
  const searxngBaseUrl = searxngHit?.base_url || probeResult?.recommended_searxng_url || 'http://127.0.0.1:8081';
  const showSearchSection = !searchConfigured;

  useEffect(() => {
    if (
      !isLocalMode() ||
      !needsCapabilities ||
      state !== 'ready' ||
      !showSearchSection ||
      !searxngHit ||
      searchConfigured ||
      autoEnabledSearxngRef.current
    ) {
      return;
    }
    autoEnabledSearxngRef.current = true;
    handleEnableSearch('searxng', searxngBaseUrl);
  }, [needsCapabilities, state, showSearchSection, searxngHit, searchConfigured, searxngBaseUrl, handleEnableSearch]);

  if (!isLocalMode() || state === 'idle') return null;
  if (hasEnabledProvider && searchConfigured && !activatedModelName && !activatedSearch) return null;

  const availableModel = probeResult?.results?.find((r) => r.available && r.models.length > 0);
  const recommendedModel = probeResult?.recommended_model;
  const showModelSection = !hasEnabledProvider;

  if (state === 'probing') {
    return (
      <div className="w-full rounded-xl border border-border/60 bg-secondary/30 p-4">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <IconLoader className="h-4 w-4 animate-spin" />
          <span>{t('detecting')}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full rounded-xl border border-primary/30 bg-primary/5 p-4 space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-500">
      {showModelSection && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2">
              <IconCpu className="h-4 w-4 text-primary" />
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">{availableModel ? tModel('title') : tModel('noModels')}</span>
              {availableModel && (
                <span className="text-xs text-muted-foreground">
                  {tModel('description', {
                    provider: availableModel.provider === 'ollama' ? 'Ollama' : 'LM Studio',
                    count: availableModel.models.length,
                  })}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 sm:shrink-0">
            {availableModel && recommendedModel && (
              <Button
                size="sm"
                className="h-8 text-xs"
                disabled={activatingModel}
                onClick={() => handleActivateModel(availableModel.provider, availableModel.base_url, recommendedModel)}
              >
                {activatingModel ? (
                  <IconLoader className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <IconCheck className="mr-1.5 h-3.5 w-3.5" />
                )}
                {tModel('useModel', { model: recommendedModel.split(':')[0] })}
              </Button>
            )}
            {!availableModel && (
              <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => router.push('/settings')}>
                <IconSettings className="mr-1.5 h-3.5 w-3.5" />
                {tModel('configureManually')}
              </Button>
            )}
          </div>
        </div>
      )}

      {showSearchSection && (
        <div
          className={cn(
            'flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between',
            showModelSection && 'pt-3 border-t border-primary/20',
          )}
        >
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2">
              <IconGlobe className="h-4 w-4 text-primary" />
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">{t('searchTitle')}</span>
              <span className="text-xs text-muted-foreground">{t('searchDescription')}</span>
              {!searxngHit && <span className="text-xs text-muted-foreground/90">{t('searxngDockerHint')}</span>}
            </div>
          </div>
          {(activatingSearch || !searxngHit) && (
            <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
              {searxngHit ? (
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <IconLoader className="h-3.5 w-3.5 animate-spin" />
                  {t('enablingSearxng')}
                </span>
              ) : (
                <>
                  <Button
                    size="sm"
                    className="h-8 text-xs"
                    disabled={startingSearxng || activatingSearch}
                    onClick={() => setSearxngConsentOpen(true)}
                  >
                    {startingSearxng ? (
                      <IconLoader className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <IconGlobe className="mr-1.5 h-3.5 w-3.5" />
                    )}
                    {startingSearxng ? t('startingSearxng') : t('startSearxngDocker')}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs"
                    onClick={() => router.push('/settings/search')}
                  >
                    {t('usePaidSearchSettings')}
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {(activatedModelName || activatedSearch) && (
        <div className="flex justify-end">
          <Button size="sm" className="h-8 text-xs" onClick={handleTryDemo}>
            <IconGlow className="mr-1.5 h-3.5 w-3.5" />
            {tModel('tryDemoLabel')}
          </Button>
        </div>
      )}

      <SearxngInstallConsentDialog
        open={searxngConsentOpen}
        onOpenChange={setSearxngConsentOpen}
        loading={startingSearxng}
        onConfirm={async () => {
          const ok = await handleStartSearxngDocker();
          if (ok) setSearxngConsentOpen(false);
        }}
      />
    </div>
  );
}
