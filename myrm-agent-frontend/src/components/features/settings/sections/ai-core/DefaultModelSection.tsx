'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { Skeleton } from '@/components/primitives/skeleton';
import { ConfigLoadError } from '@/components/features/app-shell/config-load-error';
import { useShallow } from 'zustand/react/shallow';
import useProviderStore from '@/store/useProviderStore';
import { useOrgModelPolicy } from '@/hooks/useOrgModelPolicy';
import { ModelInfoDialog } from '../../model-service/ModelInfoCard';
import RetrievalCard from '../../retrieval/RetrievalCard';
import MediaGenerationSection from '../system/MediaGenerationSection';
import BackgroundEvolutionCard from '../../default-model/BackgroundEvolutionCard';
import BaseModelCard from '../../default-model/BaseModelCard';
import LiteModelCard from '../../default-model/LiteModelCard';
import { ModelSelectEnvProvider, type ModelSelectEnv } from '../../default-model/ModelSelectRow';
import SmartRoutingCard, { useFocusRoutingDeeplink } from '../../default-model/SmartRoutingCard';
import { useClearInvalidModelSelections } from '../../default-model/useClearInvalidModelSelections';

const DefaultModelSection = memo(() => {
  const { providers, isInitialized, initError, initProviders, retryInit, getEnabledModels } = useProviderStore(
    useShallow((state) => ({
      providers: state.providers,
      isInitialized: state.isInitialized,
      initError: state.initError,
      initProviders: state.initProviders,
      retryInit: state.retryInit,
      getEnabledModels: state.getEnabledModels,
    })),
  );

  useEffect(() => {
    if (!isInitialized) {
      initProviders();
    }
  }, [isInitialized, initProviders]);

  useClearInvalidModelSelections(isInitialized);
  useFocusRoutingDeeplink();

  const { restricted: orgPolicyRestricted, isModelAllowed } = useOrgModelPolicy();
  const isModelRestricted = useCallback(
    (modelName: string) => orgPolicyRestricted && !isModelAllowed(modelName),
    [orgPolicyRestricted, isModelAllowed],
  );

  // One dialog shared by every model's configure button
  const [modelInfoOpen, setModelInfoOpen] = useState(false);
  const [modelInfoTarget, setModelInfoTarget] = useState<{
    providerId: string;
    model: string;
  } | null>(null);
  const openModelConfig = useCallback((providerId: string, model: string) => {
    setModelInfoTarget({ providerId, model });
    setModelInfoOpen(true);
  }, []);

  if (initError) {
    return <ConfigLoadError onRetry={retryInit} className="min-h-[400px]" />;
  }

  if (!isInitialized) {
    return (
      <div className="space-y-8">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="space-y-4 p-5 rounded-xl border border-border/40 bg-card/50">
            <div className="flex items-center gap-3">
              <Skeleton className="h-9 w-9 rounded-lg" />
              <Skeleton className="h-5 w-32" />
            </div>
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-10 w-full rounded-lg" />
            <Skeleton className="h-10 w-full rounded-lg" />
          </div>
        ))}
      </div>
    );
  }

  const modelSelectEnv: ModelSelectEnv = {
    enabledModels: getEnabledModels(),
    providers,
    isModelRestricted,
    openModelConfig,
  };

  return (
    <div className="space-y-8">
      <ModelSelectEnvProvider value={modelSelectEnv}>
        <BaseModelCard />
        <LiteModelCard />
        <BackgroundEvolutionCard />
        <SmartRoutingCard />
      </ModelSelectEnvProvider>

      <RetrievalCard />

      {/* 媒体生成模型配置 */}
      <MediaGenerationSection />

      {/* Model Info Dialog (shared for all model config buttons) */}
      {modelInfoTarget && (
        <ModelInfoDialog
          open={modelInfoOpen}
          onOpenChange={setModelInfoOpen}
          providerId={modelInfoTarget.providerId}
          model={modelInfoTarget.model}
        />
      )}
    </div>
  );
});

DefaultModelSection.displayName = 'DefaultModelSection';

export default DefaultModelSection;
