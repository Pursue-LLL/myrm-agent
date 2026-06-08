'use client';

import { useCallback, useState, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button } from '@/components/primitives/button';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import {
  invalidateLocalCapabilitiesProbeCache,
  type ProbeLocalResponse,
} from '@/services/localCapabilitiesProbe';
import { startLocalSearxngAndRefreshProbe } from '@/services/searxngSetup';
import { buildQuickSearchConfig } from '@/store/config/quickSearchSetup';
import { getActiveSearchServiceConfig } from '@/store/config/searchService';
import type { SearchServiceType } from '@/store/config/types';
import { IconCheck, IconCpu, IconGlobe, IconLoader } from '@/components/features/icons/PremiumIcons';
import SearxngInstallConsentDialog from '@/components/features/settings/SearxngInstallConsentDialog';
import HardwareCookbook from '@/components/features/settings/model-service/HardwareCookbook';

interface LocalCapabilitiesSetupProps {
  probeResult: ProbeLocalResponse | null;
  onComplete: () => void;
}

export default function LocalCapabilitiesSetup({ probeResult: initialProbe, onComplete }: LocalCapabilitiesSetupProps) {
  const t = useTranslations('chat.localCapabilities');
  const tModel = useTranslations('chat.localModelDetected');
  
  const [probeResult, setProbeResult] = useState<ProbeLocalResponse | null>(initialProbe);
  const [activatingModel, setActivatingModel] = useState(false);
  const [activatingSearch, setActivatingSearch] = useState(false);
  const [startingSearxng, setStartingSearxng] = useState(false);
  const [searxngConsentOpen, setSearxngConsentOpen] = useState(false);
  const autoEnabledSearxngRef = useRef(false);

  const providers = useProviderStore((s) => s.providers);
  const updateProvider = useProviderStore((s) => s.updateProvider);
  const setBaseModel = useProviderStore((s) => s.setBaseModel);
  const setLiteModel = useProviderStore((s) => s.setLiteModel);

  const searchServiceConfigs = useConfigStore((s) => s.searchServiceConfigs);
  const addSearchServiceConfig = useConfigStore((s) => s.addSearchServiceConfig);

  const hasEnabledProvider = providers.some(
    (p) => p.isEnabled && (p.apiKeys?.some((k) => k.isActive && k.key) || ['ollama', 'lm_studio'].includes(p.id)),
  );
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
                  : '未检测到本地大模型，您可以稍后在设置中手动配置 API Key。'}
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
              <Button variant="outline" onClick={onComplete}>
                稍后配置
              </Button>
            )}
          </div>
        </div>
      )}

      {!hasEnabledProvider && (
        <HardwareCookbook onApplyModel={handleApplyCookbookModel} />
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
                已就绪
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
          进入工作区
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
