'use client';

import { useCallback, useState, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';

import { Button } from '@/components/primitives/button';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import { completeOnboarding } from '@/services/onboarding';
import {
  invalidateLocalCapabilitiesProbeCache,
  type ProbeLocalResponse,
} from '@/services/localCapabilitiesProbe';
import { startLocalSearxngAndRefreshProbe } from '@/services/searxngSetup';
import { buildQuickSearchConfig } from '@/store/config/quickSearchSetup';
import { getActiveSearchServiceConfig } from '@/store/config/searchService';
import type { SearchServiceType } from '@/store/config/types';
import { IconArrowRight, IconCheck, IconCpu, IconGlobe, IconLoader, IconZap } from '@/components/features/icons/PremiumIcons';
import SearxngInstallConsentDialog from '@/components/features/settings/SearxngInstallConsentDialog';
import HardwareCookbook from '@/components/features/settings/model-service/HardwareCookbook';
import { hasUsableProviderAuth, isLoopbackApiUrl } from '@/store/config/providerTypes';
import { discoverModelsFromEndpoint } from '@/services/llm-config';

interface LocalCapabilitiesSetupProps {
  probeResult: ProbeLocalResponse | null;
  onComplete: () => void;
}

const CLOUD_PROVIDERS = [
  { id: 'gemini', nameKey: 'cloudProviderGemini', hintKey: 'cloudProviderGeminiHint' },
  { id: 'siliconflow', nameKey: 'cloudProviderSiliconFlow', hintKey: 'cloudProviderSiliconFlowHint' },
  { id: 'openrouter', nameKey: 'cloudProviderOpenRouter', hintKey: 'cloudProviderOpenRouterHint' },
] as const;
const LOCAL_OPENAI_COMPAT_PROVIDER_NAME = 'Local OpenAI Compatible';
const LOCAL_OPENAI_COMPAT_PROVIDER_ID = 'local_openai_compatible';

export default function LocalCapabilitiesSetup({ probeResult: initialProbe, onComplete }: LocalCapabilitiesSetupProps) {
  const t = useTranslations('chat.localCapabilities');
  const tModel = useTranslations('chat.localModelDetected');
  const tBoot = useTranslations('boot');
  const router = useRouter();
  
  const [probeResult, setProbeResult] = useState<ProbeLocalResponse | null>(initialProbe);
  const [activatingModel, setActivatingModel] = useState(false);
  const [activatingSearch, setActivatingSearch] = useState(false);
  const [startingSearxng, setStartingSearxng] = useState(false);
  const [searxngConsentOpen, setSearxngConsentOpen] = useState(false);
  const [customApiUrl, setCustomApiUrl] = useState('');
  const [customApiKey, setCustomApiKey] = useState('');
  const [customProbeLoading, setCustomProbeLoading] = useState(false);
  const [customActivateLoading, setCustomActivateLoading] = useState(false);
  const [customProbeError, setCustomProbeError] = useState<string | null>(null);
  const [customDetectedModels, setCustomDetectedModels] = useState<string[]>([]);
  const [customSelectedModel, setCustomSelectedModel] = useState('');
  const [customNormalizedApiUrl, setCustomNormalizedApiUrl] = useState('');
  const [customNoAuthLocal, setCustomNoAuthLocal] = useState(false);
  const autoEnabledSearxngRef = useRef(false);

  const providers = useProviderStore((s) => s.providers);
  const addProvider = useProviderStore((s) => s.addProvider);
  const updateProvider = useProviderStore((s) => s.updateProvider);
  const setBaseModel = useProviderStore((s) => s.setBaseModel);
  const setLiteModel = useProviderStore((s) => s.setLiteModel);

  const searchServiceConfigs = useConfigStore((s) => s.searchServiceConfigs);
  const addSearchServiceConfig = useConfigStore((s) => s.addSearchServiceConfig);

  const hasEnabledProvider = providers.some((p) => p.isEnabled && hasUsableProviderAuth(p));
  const searchConfigured = !!getActiveSearchServiceConfig(searchServiceConfigs);

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
        toast.success(t('searchEnabled', { service: 'SearXNG' }));
      } catch {
        toast.error(t('searchEnableFailed'));
      } finally {
        setActivatingSearch(false);
      }
    },
    [addSearchServiceConfig, t],
  );

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

  useEffect(() => {
    if (
      searchConfigured ||
      !searxngHit ||
      autoEnabledSearxngRef.current
    ) {
      return;
    }
    autoEnabledSearxngRef.current = true;
    handleEnableSearch('searxng', searxngBaseUrl);
  }, [searxngHit, searchConfigured, searxngBaseUrl, handleEnableSearch]);

  const handleApplyCookbookModel = useCallback(
    (modelId: string) => {
      const pureModelName = modelId.includes('/') ? modelId.split('/')[1] : modelId;
      void handleActivateModel('ollama', 'http://localhost:11434', pureModelName);
    },
    [handleActivateModel],
  );

  const handleGoToCloudProvider = useCallback(() => {
    void completeOnboarding().catch(() => {});
    router.push('/settings/models');
  }, [router]);

  const ensureLocalOpenAICompatProvider = useCallback(() => {
    const existing = useProviderStore.getState().providers.find((p) => p.id === LOCAL_OPENAI_COMPAT_PROVIDER_ID);
    if (existing) return existing.id;
    addProvider(LOCAL_OPENAI_COMPAT_PROVIDER_NAME, 'openai-like');
    const created = useProviderStore.getState().providers.find((p) => p.id === LOCAL_OPENAI_COMPAT_PROVIDER_ID);
    if (!created) {
      throw new Error('Failed to create local OpenAI-compatible provider');
    }
    return created.id;
  }, [addProvider]);

  const handleProbeCustomEndpoint = useCallback(async () => {
    const url = customApiUrl.trim();
    if (!url) {
      setCustomProbeError('Please enter API URL');
      return;
    }

    setCustomProbeLoading(true);
    setCustomProbeError(null);
    try {
      const result = await discoverModelsFromEndpoint(url, customApiKey.trim() || undefined);
      if (!result.success) {
        setCustomDetectedModels([]);
        setCustomSelectedModel('');
        setCustomNormalizedApiUrl(result.normalized_api_url || url);
        setCustomNoAuthLocal(false);
        setCustomProbeError(result.error || 'Failed to detect models from this endpoint');
        return;
      }

      const models = (result.models ?? []).filter(Boolean);
      if (models.length === 0) {
        setCustomDetectedModels([]);
        setCustomSelectedModel('');
        setCustomNormalizedApiUrl(result.normalized_api_url || url);
        setCustomNoAuthLocal(Boolean(result.no_auth_local));
        setCustomProbeError('Endpoint is reachable but returned no models');
        return;
      }

      setCustomDetectedModels(models);
      setCustomSelectedModel((prev) => (prev && models.includes(prev) ? prev : models[0]));
      setCustomNormalizedApiUrl(result.normalized_api_url || url);
      setCustomNoAuthLocal(Boolean(result.no_auth_local));
      toast.success(`Detected ${models.length} model(s)`);
    } catch (error) {
      setCustomDetectedModels([]);
      setCustomSelectedModel('');
      setCustomNoAuthLocal(false);
      setCustomProbeError(error instanceof Error ? error.message : 'Failed to probe endpoint');
    } finally {
      setCustomProbeLoading(false);
    }
  }, [customApiKey, customApiUrl]);

  const handleActivateCustomEndpoint = useCallback(async () => {
    if (!customSelectedModel || !customNormalizedApiUrl) {
      setCustomProbeError('Please detect models first');
      return;
    }

    setCustomActivateLoading(true);
    try {
      const providerId = ensureLocalOpenAICompatProvider();
      const current = useProviderStore.getState().providers.find((p) => p.id === providerId);
      const mergedModels = Array.from(new Set([...(current?.availableModels ?? []), ...customDetectedModels]));
      const key = customApiKey.trim();
      updateProvider(providerId, {
        apiUrl: customNormalizedApiUrl,
        availableModels: mergedModels,
        enabledModels: [customSelectedModel],
        isEnabled: true,
        apiKeys: key
          ? [{ id: `${providerId}_onboarding`, key, remark: 'Onboarding endpoint key', isActive: true }]
          : [],
      });

      const selection = { providerId, model: customSelectedModel };
      setBaseModel(selection);
      setLiteModel(selection);
      toast.success(tModel('useModel', { model: customSelectedModel.split(':')[0] }));
    } catch {
      toast.error(t('modelActivateFailed'));
    } finally {
      setCustomActivateLoading(false);
    }
  }, [
    customApiKey,
    customDetectedModels,
    customNormalizedApiUrl,
    customSelectedModel,
    ensureLocalOpenAICompatProvider,
    setBaseModel,
    setLiteModel,
    t,
    tModel,
    updateProvider,
  ]);

  const availableModel = probeResult?.results?.find((r) => r.available && r.models.length > 0);
  const recommendedModel = probeResult?.recommended_model;

  return (
    <div className="space-y-8">
      {!hasEnabledProvider && (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between p-4 rounded-xl border bg-card">
          <div className="flex items-start gap-4">
            <div className="rounded-xl bg-primary/10 p-3">
              <IconCpu className="h-6 w-6 text-primary" />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-base font-semibold">{availableModel ? tModel('title') : tModel('noModels')}</span>
              <span className="text-sm text-muted-foreground">
                {availableModel 
                  ? tModel('description', {
                      provider: availableModel.provider === 'ollama' ? 'Ollama' : 'LM Studio',
                      count: availableModel.models.length,
                    })
                  : tBoot('onboarding.noLocalModel')}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:shrink-0">
            {availableModel && recommendedModel ? (
              <Button
                disabled={activatingModel}
                onClick={() => handleActivateModel(availableModel.provider, availableModel.base_url, recommendedModel)}
              >
                {activatingModel ? (
                  <IconLoader className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <IconCheck className="mr-2 h-4 w-4" />
                )}
                {tModel('useModel', { model: recommendedModel.split(':')[0] })}
              </Button>
            ) : (
              <Button variant="outline" onClick={handleGoToCloudProvider}>
                {tBoot('onboarding.configureLater')}
              </Button>
            )}
          </div>
        </div>
      )}

      {!hasEnabledProvider && (
        <HardwareCookbook onApplyModel={handleApplyCookbookModel} />
      )}

      {!hasEnabledProvider && (
        <div className="p-4 rounded-xl border bg-card space-y-4">
          <div className="space-y-1">
            <span className="text-base font-semibold">OpenAI-compatible local endpoint</span>
            <span className="block text-sm text-muted-foreground">
              Paste your local endpoint to auto-detect models and finish setup in one step.
            </span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs text-muted-foreground">API URL</span>
              <input
                value={customApiUrl}
                onChange={(e) => setCustomApiUrl(e.target.value)}
                placeholder="http://127.0.0.1:8899/v1"
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-muted-foreground">API Key (optional for localhost)</span>
              <input
                value={customApiKey}
                onChange={(e) => setCustomApiKey(e.target.value)}
                placeholder="sk-..."
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm"
              />
            </label>
          </div>
          {isLoopbackApiUrl(customApiUrl) && (
            <p className="text-xs text-muted-foreground">
              Localhost endpoints can leave API key empty; cloud or remote endpoints still require a key.
            </p>
          )}
          {customNoAuthLocal && (
            <p className="text-xs text-emerald-600 dark:text-emerald-400">
              Local no-auth mode detected. This endpoint will be used without storing an API key.
            </p>
          )}
          {customProbeError && <p className="text-xs text-destructive">{customProbeError}</p>}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={handleProbeCustomEndpoint} disabled={customProbeLoading}>
              {customProbeLoading ? <IconLoader className="mr-2 h-4 w-4 animate-spin" /> : null}
              Detect Models
            </Button>
            {customDetectedModels.length > 0 && (
              <>
                <select
                  value={customSelectedModel}
                  onChange={(e) => setCustomSelectedModel(e.target.value)}
                  className="h-10 min-w-[220px] rounded-lg border bg-background px-3 text-sm"
                >
                  {customDetectedModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
                <Button onClick={handleActivateCustomEndpoint} disabled={customActivateLoading}>
                  {customActivateLoading ? (
                    <IconLoader className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <IconCheck className="mr-2 h-4 w-4" />
                  )}
                  Use {customSelectedModel}
                </Button>
              </>
            )}
          </div>
        </div>
      )}

      {!hasEnabledProvider && !availableModel && (
        <div className="p-4 rounded-xl border bg-card space-y-4">
          <div className="flex items-start gap-4">
            <div className="rounded-xl bg-accent-warm/10 p-3">
              <IconZap className="h-6 w-6 text-accent-warm" />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-base font-semibold">{tBoot('onboarding.cloudQuickStart')}</span>
              <span className="text-sm text-muted-foreground">{tBoot('onboarding.cloudQuickStartHint')}</span>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {CLOUD_PROVIDERS.map(({ id, nameKey, hintKey }) => (
              <button
                key={id}
                type="button"
                onClick={handleGoToCloudProvider}
                className="flex items-center justify-between gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-accent/50"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{tBoot(`onboarding.${nameKey}`)}</div>
                  <div className="text-xs text-muted-foreground truncate">{tBoot(`onboarding.${hintKey}`)}</div>
                </div>
                <IconArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </button>
            ))}
          </div>
        </div>
      )}

      {!searchConfigured && (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between p-4 rounded-xl border bg-card">
          <div className="flex items-start gap-4">
            <div className="rounded-xl bg-primary/10 p-3">
              <IconGlobe className="h-6 w-6 text-primary" />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-base font-semibold">{t('searchTitle')}</span>
              <span className="text-sm text-muted-foreground">{t('searchDescription')}</span>
              {!searxngHit && <span className="text-xs text-muted-foreground/90">{t('searxngDockerHint')}</span>}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
            {searxngHit ? (
              <span className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400 font-medium">
                <IconCheck className="h-4 w-4" />
                {tBoot('onboarding.searchReady')}
              </span>
            ) : (
              <Button
                disabled={startingSearxng || activatingSearch}
                onClick={() => setSearxngConsentOpen(true)}
              >
                {startingSearxng ? (
                  <IconLoader className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <IconGlobe className="mr-2 h-4 w-4" />
                )}
                {startingSearxng ? t('startingSearxng') : t('startSearxngDocker')}
              </Button>
            )}
          </div>
        </div>
      )}

      <div className="flex justify-center pt-4">
        <Button size="lg" className="w-full sm:w-auto min-w-[200px]" onClick={onComplete}>
          {tBoot('onboarding.enterWorkspace')}
        </Button>
      </div>

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
