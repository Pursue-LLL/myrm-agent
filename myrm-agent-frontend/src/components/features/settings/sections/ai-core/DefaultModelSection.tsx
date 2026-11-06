'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/primitives/skeleton';
import { ConfigLoadError } from '@/components/features/app-shell/config-load-error';
import { IconAlertCircle, IconDatabase, IconRefresh } from '@/components/features/icons/PremiumIcons';
import { useShallow } from 'zustand/react/shallow';
import useProviderStore from '@/store/useProviderStore';
import { useOrgModelPolicy } from '@/hooks/useOrgModelPolicy';
import { ModelInfoDialog } from '../../model-service/ModelInfoCard';
import SettingsSection from '../SettingsSection';
import ProviderModelSelector from '../../retrieval/ProviderModelSelector';
import MemoryMigrationNotice from '@/components/features/memory/settings/MemoryMigrationNotice';
import { EMBEDDING_PROVIDERS, RERANKER_PROVIDERS } from '@/lib/search/retrievalProviders';
import useRetrievalStore from '@/store/useRetrievalStore';
import { HoverCard, HoverCardTrigger, HoverCardContent } from '@/components/primitives/hover-card';
import MediaGenerationSection from '../system/MediaGenerationSection';
import BackgroundEvolutionCard from '../../default-model/BackgroundEvolutionCard';
import BaseModelCard from '../../default-model/BaseModelCard';
import LiteModelCard from '../../default-model/LiteModelCard';
import { ModelSelectEnvProvider, type ModelSelectEnv } from '../../default-model/ModelSelectRow';
import SmartRoutingCard, { useFocusRoutingDeeplink } from '../../default-model/SmartRoutingCard';
import { useClearInvalidModelSelections } from '../../default-model/useClearInvalidModelSelections';

const DefaultModelSection = memo(() => {
  const t = useTranslations('settings.defaultModel');
  const tRetrieval = useTranslations('settings.retrieval');

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

  // Retrieval Service 配置
  const {
    embeddingConfig,
    embeddingApplied,
    embeddingApplyStatus,
    embeddingApplyMessage,
    rerankerConfig,
    rerankerApplied,
    rerankerApplyStatus,
    rerankerApplyMessage,
    setEmbeddingConfig,
    setRerankerConfig,
    applyEmbedding,
    applyReranker,
  } = useRetrievalStore(
    useShallow((state) => ({
      embeddingConfig: state.embeddingConfig,
      embeddingApplied: state.embeddingApplied,
      embeddingApplyStatus: state.embeddingApplyStatus,
      embeddingApplyMessage: state.embeddingApplyMessage,
      rerankerConfig: state.rerankerConfig,
      rerankerApplied: state.rerankerApplied,
      rerankerApplyStatus: state.rerankerApplyStatus,
      rerankerApplyMessage: state.rerankerApplyMessage,
      setEmbeddingConfig: state.setEmbeddingConfig,
      setRerankerConfig: state.setRerankerConfig,
      applyEmbedding: state.applyEmbedding,
      applyReranker: state.applyReranker,
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

      {/* Embedding 模型配置 */}
      <SettingsSection
        title={
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-500/10">
              <IconDatabase className="w-5 h-5 text-blue-500" />
            </div>
            <span>{t('retrieval.embeddingModel')}</span>
          </div>
        }
        description={t('retrieval.embeddingModelDescription')}
      >
        <div className="space-y-6">
          {/* Hint text - Hover to expand */}
          <HoverCard openDelay={200} closeDelay={100}>
            <HoverCardTrigger asChild>
              <div className="inline-flex items-center gap-2 rounded-lg border border-border/50 bg-muted/20 px-4 py-2.5 cursor-help transition-all hover:bg-muted/40 hover:border-border">
                <IconAlertCircle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <p className="text-sm text-foreground/80">{tRetrieval('hint.title')}</p>
              </div>
            </HoverCardTrigger>
            <HoverCardContent className="w-96" align="start">
              <div className="space-y-3">
                {/* Options */}
                <p className="text-sm leading-relaxed text-foreground">{tRetrieval('hint.options')}</p>

                {/* Recommendation */}
                <p className="text-sm leading-relaxed text-muted-foreground">{tRetrieval('hint.recommendation')}</p>

                {/* Deploy tip */}
                <div className="flex items-start gap-2 pt-1 border-t border-border/50 mt-3 pt-3">
                  <span className="text-sm text-muted-foreground/80">
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 16v-4" />
                      <path d="M12 8h.01" />
                    </svg>
                  </span>
                  <div className="text-sm text-muted-foreground/80">
                    <span>{tRetrieval('hint.deployTip')}</span>
                    <span className="mx-1">:</span>
                    <span className="font-mono text-xs bg-muted/50 px-2 py-0.5 rounded">
                      {tRetrieval('hint.deployQuestion')}
                    </span>
                  </div>
                </div>
              </div>
            </HoverCardContent>
          </HoverCard>

          <div className="p-6 rounded-xl border border-border bg-muted/30">
            <ProviderModelSelector
              value={embeddingConfig}
              onChange={setEmbeddingConfig}
              providers={EMBEDDING_PROVIDERS}
              serviceType="embedding"
              applyStatus={embeddingApplyStatus}
              applyMessage={embeddingApplyMessage}
              isApplied={embeddingApplied}
              onApply={applyEmbedding}
            />
          </div>

          <MemoryMigrationNotice />
        </div>
      </SettingsSection>

      {/* Reranker 模型配置 */}
      <SettingsSection
        title={
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-500/10">
              <IconRefresh className="w-5 h-5 text-purple-500" />
            </div>
            <span>{t('retrieval.rerankerModel')}</span>
          </div>
        }
        description={t('retrieval.rerankerModelDescription')}
      >
        <div className="space-y-6">
          {/* Hint text - Hover to expand */}
          <HoverCard openDelay={200} closeDelay={100}>
            <HoverCardTrigger asChild>
              <div className="inline-flex items-center gap-2 rounded-lg border border-border/50 bg-muted/20 px-4 py-2.5 cursor-help transition-all hover:bg-muted/40 hover:border-border">
                <IconAlertCircle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <p className="text-sm text-foreground/80">{tRetrieval('hint.title')}</p>
              </div>
            </HoverCardTrigger>
            <HoverCardContent className="w-96" align="start">
              <div className="space-y-3">
                {/* Options */}
                <p className="text-sm leading-relaxed text-foreground">{tRetrieval('hint.options')}</p>

                {/* Recommendation */}
                <p className="text-sm leading-relaxed text-muted-foreground">{tRetrieval('hint.recommendation')}</p>

                {/* Deploy tip */}
                <div className="flex items-start gap-2 pt-1 border-t border-border/50 mt-3 pt-3">
                  <span className="text-sm text-muted-foreground/80">
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 16v-4" />
                      <path d="M12 8h.01" />
                    </svg>
                  </span>
                  <div className="text-sm text-muted-foreground/80">
                    <span>{tRetrieval('hint.deployTip')}</span>
                    <span className="mx-1">:</span>
                    <span className="font-mono text-xs bg-muted/50 px-2 py-0.5 rounded">
                      {tRetrieval('hint.deployQuestion')}
                    </span>
                  </div>
                </div>
              </div>
            </HoverCardContent>
          </HoverCard>

          <div className="p-6 rounded-xl border border-border bg-muted/30">
            <ProviderModelSelector
              value={rerankerConfig}
              onChange={setRerankerConfig}
              providers={RERANKER_PROVIDERS}
              serviceType="reranker"
              applyStatus={rerankerApplyStatus}
              applyMessage={rerankerApplyMessage}
              isApplied={rerankerApplied}
              onApply={applyReranker}
            />
          </div>
        </div>
      </SettingsSection>

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
