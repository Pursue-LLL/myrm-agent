'use client';

import { memo, useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Skeleton } from '@/components/primitives/skeleton';
import { Button } from '@/components/primitives/button';
import { IconGlobe, IconLoader, IconSettings } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import useConfigStore from '@/store/useConfigStore';
import { SearchServiceConfigItem } from '@/store/config/types';
import { generateSearchServiceConfigId } from '@/store/config/searchService';
import { probeAndBuildQuickSearchConfig } from '@/store/config/quickSearchSetup';
import { startLocalSearxngAndRefreshProbe } from '@/services/searxngSetup';
import { probeLocalCapabilities } from '@/services/localCapabilitiesProbe';
import SearchServiceCard from '../SearchServiceCard';
import SearchServiceEditDialog from '../SearchServiceEditDialog';
import SearxngInstallConsentDialog from '../SearxngInstallConsentDialog';
import SettingsSection from './SettingsSection';
import { useDeployMode } from '@/hooks/useDeployMode';

const SearchSection = memo(() => {
  const t = useTranslations('settings');
  const { isLocal } = useDeployMode();
  const {
    searchServiceConfigs,
    addSearchServiceConfig,
    updateSearchServiceConfig,
    removeSearchServiceConfig,
    enableSearchServiceConfig,
    validateSearchServiceConfig,
    initConfig,
  } = useConfigStore();

  const [isLoading, setIsLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<SearchServiceConfigItem | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [quickEnabling, setQuickEnabling] = useState(false);
  const [startingSearxng, setStartingSearxng] = useState(false);
  const [searxngConsentOpen, setSearxngConsentOpen] = useState(false);
  const [pendingQuickEnable, setPendingQuickEnable] = useState(false);

  // Sandbox: hide local-only SearXNG entries; paid LiteLLM providers remain visible.
  const filteredConfigs = useMemo(() => {
    const configs = isLocal
      ? searchServiceConfigs
      : searchServiceConfigs.filter((config) => config.search_service !== 'searxng');

    return [...configs].sort((a, b) => {
      if (a.role !== b.role) {
        return a.role === 'primary' ? -1 : 1;
      }
      return (a.createdAt || 0) - (b.createdAt || 0);
    });
  }, [searchServiceConfigs, isLocal]);

  useEffect(() => {
    initConfig();
    setIsLoading(false);
  }, [initConfig]);

  const handleCreate = () => {
    setEditingConfig(null);
    setIsCreating(true);
    setIsDialogOpen(true);
  };

  const handleEdit = (config: SearchServiceConfigItem) => {
    setEditingConfig(config);
    setIsCreating(false);
    setIsDialogOpen(true);
  };

  const handleStartSearxngDocker = useCallback(async (): Promise<boolean> => {
    setStartingSearxng(true);
    try {
      const { startResult } = await startLocalSearxngAndRefreshProbe();
      if (!startResult.available) {
        toast.error(t('searchService.startSearxngFailed'));
        return false;
      }
      const config = await probeAndBuildQuickSearchConfig();
      if (config) {
        addSearchServiceConfig(config);
        toast.success(t('searchService.quickEnableSuccess', { service: 'SearXNG' }));
        return true;
      }
      return false;
    } catch {
      toast.error(t('searchService.startSearxngFailed'));
      return false;
    } finally {
      setStartingSearxng(false);
    }
  }, [addSearchServiceConfig, t]);

  const handleQuickEnable = useCallback(async () => {
    setQuickEnabling(true);
    try {
      let config = await probeAndBuildQuickSearchConfig();
      if (!config && isLocal) {
        const probe = await probeLocalCapabilities(true);
        const searxngUp = probe.search?.some((s) => s.provider === 'searxng' && s.available);
        if (!searxngUp) {
          setPendingQuickEnable(true);
          setSearxngConsentOpen(true);
          return;
        }
        config = await probeAndBuildQuickSearchConfig();
      }
      if (!config) {
        toast.error(t('searchService.quickEnableFailed'));
        setEditingConfig(null);
        setIsCreating(true);
        setIsDialogOpen(true);
        return;
      }
      addSearchServiceConfig(config);
      toast.success(t('searchService.quickEnableSuccess', { service: 'SearXNG' }));
    } finally {
      setQuickEnabling(false);
    }
  }, [addSearchServiceConfig, handleStartSearxngDocker, isLocal, t]);

  const handleSave = async (config: SearchServiceConfigItem) => {
    if (isCreating) {
      const newConfig: SearchServiceConfigItem = {
        ...config,
        id: generateSearchServiceConfigId(),
        createdAt: Date.now(),
      };
      addSearchServiceConfig(newConfig);
    } else {
      updateSearchServiceConfig(config.id, config);
    }
    setIsDialogOpen(false);
    setEditingConfig(null);
  };

  const handleDelete = (id: string) => {
    removeSearchServiceConfig(id);
  };

  const handleEnableWithLatency = (id: string, latency?: number) => {
    if (latency !== undefined) {
      updateSearchServiceConfig(id, { latency });
    }
    enableSearchServiceConfig(id);
  };

  if (isLoading) {
    return (
      <div className="space-y-5">
        <div className="space-y-1.5">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-4 w-56" />
        </div>
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-10 w-2/3 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SettingsSection
        title={t('searchServiceConfig')}
        action={
          <button
            onClick={handleCreate}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-accent-warm hover:bg-accent-warm/10 rounded-lg transition-colors"
          >
            <IconSettings className="w-4 h-4" />
            {t('searchService.addConfig')}
          </button>
        }
      >
        {filteredConfigs.length === 0 ? (
          <div className="mx-auto max-w-md rounded-2xl border border-border/60 bg-card/40 px-6 py-10 text-center">
            <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 ring-1 ring-primary/15">
              <IconGlobe className="h-7 w-7 text-primary" />
            </div>
            <h3 className="text-lg font-semibold text-foreground">{t('searchService.noConfigs')}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{t('searchService.noConfigsDesc')}</p>
            {isLocal && <p className="mt-2 text-xs text-muted-foreground">{t('searchService.searchOptionalHint')}</p>}
            <div className="mt-7 flex w-full flex-col gap-2.5">
              {isLocal && (
                <Button
                  type="button"
                  onClick={() => setSearxngConsentOpen(true)}
                  disabled={startingSearxng || quickEnabling}
                  className="h-11 w-full rounded-xl bg-primary text-primary-foreground hover:bg-primary-hover shadow-[var(--shadow-brand)]"
                >
                  {startingSearxng ? (
                    <IconLoader className="h-4 w-4 animate-spin" />
                  ) : (
                    <IconGlobe className="h-4 w-4" />
                  )}
                  {startingSearxng ? t('searchService.startingSearxng') : t('searchService.startSearxngDocker')}
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                onClick={() => void handleQuickEnable()}
                disabled={quickEnabling || startingSearxng}
                className="h-11 w-full rounded-xl brand-interactive-hover"
              >
                {quickEnabling ? (
                  <IconLoader className="h-4 w-4 animate-spin" />
                ) : (
                  <IconGlobe className="h-4 w-4 text-primary" />
                )}
                {quickEnabling ? t('searchService.quickEnableSearching') : t('searchService.quickEnableFreeSearch')}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={handleCreate}
                className={cn('h-10 w-full rounded-xl text-muted-foreground hover:text-accent-warm')}
              >
                <IconSettings className="h-4 w-4" />
                {t('searchService.addFirstConfig')}
              </Button>
            </div>
          </div>
        ) : (
          <div className="grid gap-3">
            {filteredConfigs.map((config) => {
              const conflictingService = filteredConfigs.find(
                (c) => c.id !== config.id && c.enabled && c.role === config.role,
              );
              return (
                <SearchServiceCard
                  key={config.id}
                  config={config}
                  conflictingService={conflictingService}
                  onEdit={() => handleEdit(config)}
                  onDelete={() => handleDelete(config.id)}
                  onEnable={(latency) => handleEnableWithLatency(config.id, latency)}
                  onValidate={validateSearchServiceConfig}
                />
              );
            })}
          </div>
        )}
      </SettingsSection>

      <SearchServiceEditDialog
        isOpen={isDialogOpen}
        onClose={() => setIsDialogOpen(false)}
        config={editingConfig}
        isCreating={isCreating}
        onSave={handleSave}
        onValidate={validateSearchServiceConfig}
      />

      {isLocal && (
        <SearxngInstallConsentDialog
          open={searxngConsentOpen}
          onOpenChange={(open) => {
            setSearxngConsentOpen(open);
            if (!open) {
              if (pendingQuickEnable) setQuickEnabling(false);
              setPendingQuickEnable(false);
            }
          }}
          loading={startingSearxng}
          onConfirm={async () => {
            const ok = await handleStartSearxngDocker();
            if (ok) {
              setSearxngConsentOpen(false);
              setPendingQuickEnable(false);
            } else if (pendingQuickEnable) {
              setQuickEnabling(false);
            }
          }}
        />
      )}
    </div>
  );
});

SearchSection.displayName = 'SearchSection';

export default SearchSection;
