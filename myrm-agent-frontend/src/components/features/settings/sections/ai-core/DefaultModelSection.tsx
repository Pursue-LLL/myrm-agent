'use client';

import { memo, useEffect, useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/primitives/skeleton';
import { ConfigLoadError } from '@/components/features/app-shell/config-load-error';
import {
  IconAlertCircle,
  IconAlertTriangle,
  IconBrain,
  IconCpu,
  IconDatabase,
  IconImage,
  IconRefresh,
  IconRoute,
  IconShield,
  IconSliders,
  IconZap,
} from '@/components/features/icons/PremiumIcons';
import { useShallow } from 'zustand/react/shallow';
import useProviderStore from '@/store/useProviderStore';
import { SingleModelSelection, getProviderCategory } from '@/store/config/providerTypes';
import EnabledModelSelect from '../../default-model/EnabledModelSelect';
import { useOrgModelPolicy } from '@/hooks/useOrgModelPolicy';
import { ModelInfoDialog } from '../../model-service/ModelInfoCard';
import SettingsSection from '../SettingsSection';
import ProviderModelSelector from '../../retrieval/ProviderModelSelector';
import { EMBEDDING_PROVIDERS, RERANKER_PROVIDERS } from '@/lib/search/retrievalProviders';
import useRetrievalStore from '@/store/useRetrievalStore';
import { HoverCard, HoverCardTrigger, HoverCardContent } from '@/components/primitives/hover-card';
import MediaGenerationSection from '../system/MediaGenerationSection';

const DefaultModelSection = memo(() => {
  const t = useTranslations('settings.defaultModel');
  const tRetrieval = useTranslations('settings.retrieval');

  const {
    providers,
    defaultModelConfig,
    customModelInfo,
    isInitialized,
    initError,
    initProviders,
    retryInit,
    setBaseModel,
    setBaseModelFallback,
    setLiteModel,
    setLiteModelFallback,
    setRoutingEnabled,
    setRoutingLightModel,
    setRoutingLightModelFallback,
    setRoutingReasoningModel,
    setRoutingReasoningModelFallback,
    setVisionFallbackModel,
    getEnabledModels,
  } = useProviderStore(
    useShallow((state) => ({
      providers: state.providers,
      defaultModelConfig: state.defaultModelConfig,
      customModelInfo: state.customModelInfo,
      isInitialized: state.isInitialized,
      initError: state.initError,
      initProviders: state.initProviders,
      retryInit: state.retryInit,
      setBaseModel: state.setBaseModel,
      setBaseModelFallback: state.setBaseModelFallback,
      setLiteModel: state.setLiteModel,
      setLiteModelFallback: state.setLiteModelFallback,
      setRoutingEnabled: state.setRoutingEnabled,
      setRoutingLightModel: state.setRoutingLightModel,
      setRoutingLightModelFallback: state.setRoutingLightModelFallback,
      setRoutingReasoningModel: state.setRoutingReasoningModel,
      setRoutingReasoningModelFallback: state.setRoutingReasoningModelFallback,
      setVisionFallbackModel: state.setVisionFallbackModel,
      getEnabledModels: state.getEnabledModels,
    })),
  );

  // 用于防止重复清除无效模型选择
  const hasCleanedModelsRef = useRef(false);

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
    orphanCount,
    setEmbeddingConfig,
    setRerankerConfig,
    applyEmbedding,
    applyReranker,
    executeReindex,
    dismissOrphanWarning,
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
      orphanCount: state.orphanCount,
      setEmbeddingConfig: state.setEmbeddingConfig,
      setRerankerConfig: state.setRerankerConfig,
      applyEmbedding: state.applyEmbedding,
      applyReranker: state.applyReranker,
      executeReindex: state.executeReindex,
      dismissOrphanWarning: state.dismissOrphanWarning,
    })),
  );

  const [reindexing, setReindexing] = useState(false);
  const handleReindex = async () => {
    setReindexing(true);
    try {
      await executeReindex();
    } finally {
      setReindexing(false);
    }
  };

  useEffect(() => {
    if (!isInitialized) {
      initProviders();
    }
  }, [isInitialized, initProviders]);

  // 获取已启用的模型列表
  const enabledModels = getEnabledModels();

  const { restricted: orgPolicyRestricted, isModelAllowed } = useOrgModelPolicy();
  const isModelRestricted = useCallback(
    (modelName: string) => orgPolicyRestricted && !isModelAllowed(modelName),
    [orgPolicyRestricted, isModelAllowed],
  );

  // 检查模型选择是否有效（Provider 存在、启用、有激活的 API Key）
  const isSelectionValid = useCallback(
    (selection: SingleModelSelection | null): boolean => {
      if (!selection) return true; // null 是有效的（表示未选择）

      const provider = providers.find((p) => p.id === selection.providerId);
      if (!provider) return false; // Provider 不存在
      if (!provider.isEnabled) return false; // Provider 未启用
      if (!provider.apiKeys.some((k) => k.isActive && k.key)) return false; // 没有激活的 API Key
      if (!provider.enabledModels.includes(selection.model)) return false; // 模型未在 enabledModels 中

      return true;
    },
    [providers],
  );

  useEffect(() => {
    if (!isInitialized || hasCleanedModelsRef.current) return;

    if (!isSelectionValid(defaultModelConfig.baseModel.primary)) {
      setBaseModel(null);
    }
    if (!isSelectionValid(defaultModelConfig.baseModel.fallback)) {
      setBaseModelFallback(null);
    }
    if (!isSelectionValid(defaultModelConfig.liteModel.primary)) {
      setLiteModel(null);
    }
    if (!isSelectionValid(defaultModelConfig.liteModel.fallback)) {
      setLiteModelFallback(null);
    }
    const rc = defaultModelConfig.routingConfig;
    if (rc) {
      if (!isSelectionValid(rc.lightModel.primary)) setRoutingLightModel(null);
      if (!isSelectionValid(rc.lightModel.fallback)) setRoutingLightModelFallback(null);
      if (!isSelectionValid(rc.reasoningModel.primary)) setRoutingReasoningModel(null);
      if (!isSelectionValid(rc.reasoningModel.fallback)) setRoutingReasoningModelFallback(null);
    }
    if (!isSelectionValid(defaultModelConfig.visionFallbackModel ?? null)) {
      setVisionFallbackModel(null);
    }

    hasCleanedModelsRef.current = true;
  }, [
    isInitialized,
    isSelectionValid,
    defaultModelConfig,
    setBaseModel,
    setBaseModelFallback,
    setLiteModel,
    setLiteModelFallback,
    setRoutingLightModel,
    setRoutingLightModelFallback,
    setRoutingReasoningModel,
    setRoutingReasoningModelFallback,
  ]);

  const handleBaseModelChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setBaseModel(selection);
    },
    [setBaseModel],
  );

  const handleBaseModelFallbackChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setBaseModelFallback(selection);
    },
    [setBaseModelFallback],
  );

  const handleLiteModelChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setLiteModel(selection);
    },
    [setLiteModel],
  );

  const handleLiteModelFallbackChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setLiteModelFallback(selection);
    },
    [setLiteModelFallback],
  );

  const handleVisionFallbackModelChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setVisionFallbackModel(selection);
    },
    [setVisionFallbackModel],
  );

  const isRoutingEnabled = defaultModelConfig.routingConfig?.enabled ?? true;
  const handleRoutingToggle = useCallback(() => {
    setRoutingEnabled(!isRoutingEnabled);
  }, [setRoutingEnabled, isRoutingEnabled]);

  const handleRoutingLightModelChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setRoutingLightModel(selection);
    },
    [setRoutingLightModel],
  );

  const handleRoutingLightModelFallbackChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setRoutingLightModelFallback(selection);
    },
    [setRoutingLightModelFallback],
  );

  const handleRoutingReasoningModelChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setRoutingReasoningModel(selection);
    },
    [setRoutingReasoningModel],
  );

  const handleRoutingReasoningModelFallbackChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setRoutingReasoningModelFallback(selection);
    },
    [setRoutingReasoningModelFallback],
  );

  // Model info dialog state
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

  return (
    <div className="space-y-8">
      {/* 主模型配置 */}
      <SettingsSection
        title={
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <IconCpu className="w-5 h-5 text-primary" />
            </div>
            <span>{t('baseModel')}</span>
          </div>
        }
        description={t('baseModelDescription')}
      >
        <div className="space-y-8">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <EnabledModelSelect
                label={t('selectModel')}
                value={defaultModelConfig.baseModel.primary}
                onChange={handleBaseModelChange}
                enabledModels={enabledModels}
                providers={providers}
                isModelRestricted={isModelRestricted}
              />
            </div>
            {defaultModelConfig.baseModel.primary && (
              <button
                type="button"
                onClick={() =>
                  openModelConfig(
                    defaultModelConfig.baseModel.primary!.providerId,
                    defaultModelConfig.baseModel.primary!.model,
                  )
                }
                className="flex items-center justify-center w-10 h-10 rounded-lg border border-border bg-secondary/50 hover:bg-accent transition-colors flex-shrink-0"
                title={t('configureModel')}
              >
                <IconSliders className="w-4 h-4 text-muted-foreground" />
              </button>
            )}
          </div>

          {/* Local Model Warning */}
          {defaultModelConfig.baseModel.primary &&
            getProviderCategory(defaultModelConfig.baseModel.primary.providerId) === 'local' && (
              <div className="flex items-start gap-2.5 p-3.5 mt-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-600 dark:text-yellow-500">
                <IconAlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <div className="text-xs font-medium leading-relaxed">{t('localModelWarning')}</div>
              </div>
            )}

          {/* Fallback Model */}
          <div className="p-5 bg-background/50 rounded-xl border border-border/50">
            <div className="flex items-center gap-2 mb-3">
              <IconShield className="w-4 h-4 text-sky-500" />
              <span className="text-sm font-medium text-foreground">{t('fallbackModel')}</span>
            </div>
            <p className="text-xs text-muted-foreground mb-4">{t('fallbackModelDescription')}</p>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <EnabledModelSelect
                  label={t('selectFallbackModel')}
                  value={defaultModelConfig.baseModel.fallback}
                  onChange={handleBaseModelFallbackChange}
                  enabledModels={enabledModels}
                  providers={providers}
                  isModelRestricted={isModelRestricted}
                />
              </div>
              {defaultModelConfig.baseModel.fallback && (
                <button
                  onClick={() =>
                    openModelConfig(
                      defaultModelConfig.baseModel.fallback!.providerId,
                      defaultModelConfig.baseModel.fallback!.model,
                    )
                  }
                  className="flex items-center justify-center w-10 h-10 rounded-lg border border-border bg-secondary/50 hover:bg-accent transition-colors flex-shrink-0"
                  title={t('configureModel')}
                >
                  <IconSliders className="w-4 h-4 text-muted-foreground" />
                </button>
              )}
            </div>
          </div>

          {/* Vision Fallback Model */}
          <div className="p-5 bg-background/50 rounded-xl border border-border/50">
            <div className="flex items-center gap-2 mb-3">
              <IconImage className="w-4 h-4 text-purple-500" />
              <span className="text-sm font-medium text-foreground">{t('visionFallbackModel')}</span>
            </div>
            <p className="text-xs text-muted-foreground mb-4">{t('visionFallbackModelDescription')}</p>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <EnabledModelSelect
                  label={t('selectModel')}
                  value={defaultModelConfig.visionFallbackModel ?? null}
                  onChange={handleVisionFallbackModelChange}
                  enabledModels={enabledModels}
                  providers={providers}
                  isModelRestricted={isModelRestricted}
                />
              </div>
              {defaultModelConfig.visionFallbackModel && (
                <button
                  onClick={() =>
                    openModelConfig(
                      defaultModelConfig.visionFallbackModel!.providerId,
                      defaultModelConfig.visionFallbackModel!.model,
                    )
                  }
                  className="flex items-center justify-center w-10 h-10 rounded-lg border border-border bg-secondary/50 hover:bg-accent transition-colors flex-shrink-0"
                  title={t('configureModel')}
                >
                  <IconSliders className="w-4 h-4 text-muted-foreground" />
                </button>
              )}
            </div>
          </div>
        </div>
      </SettingsSection>

      {/* 快速模型配置 */}
      <SettingsSection
        title={
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-500/10">
              <IconZap className="w-5 h-5 text-amber-500" />
            </div>
            <span>{t('liteModel')}</span>
          </div>
        }
        description={t('liteModelDescription')}
      >
        <div className="space-y-8">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <EnabledModelSelect
                label={t('selectModel')}
                value={defaultModelConfig.liteModel.primary}
                onChange={handleLiteModelChange}
                enabledModels={enabledModels}
                providers={providers}
                isModelRestricted={isModelRestricted}
              />
            </div>
            {defaultModelConfig.liteModel.primary && (
              <button
                type="button"
                onClick={() =>
                  openModelConfig(
                    defaultModelConfig.liteModel.primary!.providerId,
                    defaultModelConfig.liteModel.primary!.model,
                  )
                }
                className="flex items-center justify-center w-10 h-10 rounded-lg border border-border bg-secondary/50 hover:bg-accent transition-colors flex-shrink-0"
                title={t('configureModel')}
              >
                <IconSliders className="w-4 h-4 text-muted-foreground" />
              </button>
            )}
          </div>

          {/* Context Window Mismatch Warning */}
          {(() => {
            const basePrimary = defaultModelConfig.baseModel.primary;
            const litePrimary = defaultModelConfig.liteModel.primary;
            if (!basePrimary || !litePrimary) return null;
            const baseWindow = customModelInfo[`${basePrimary.providerId}/${basePrimary.model}`]?.max_input_tokens;
            const liteWindow = customModelInfo[`${litePrimary.providerId}/${litePrimary.model}`]?.max_input_tokens;
            if (!baseWindow || !liteWindow || liteWindow >= baseWindow) return null;
            return (
              <div className="flex items-start gap-2.5 p-3.5 mt-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-600 dark:text-yellow-500">
                <IconAlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <div className="text-xs font-medium leading-relaxed">{t('liteModelContextWindowWarning')}</div>
              </div>
            );
          })()}

          {/* Fallback Filter Model */}
          <div className="p-5 bg-background/50 rounded-xl border border-border/50">
            <div className="flex items-center gap-2 mb-3">
              <IconShield className="w-4 h-4 text-sky-500" />
              <span className="text-sm font-medium text-foreground">{t('fallbackModel')}</span>
            </div>
            <p className="text-xs text-muted-foreground mb-4">{t('fallbackModelDescription')}</p>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <EnabledModelSelect
                  label={t('selectFallbackModel')}
                  value={defaultModelConfig.liteModel.fallback}
                  onChange={handleLiteModelFallbackChange}
                  enabledModels={enabledModels}
                  providers={providers}
                  isModelRestricted={isModelRestricted}
                />
              </div>
              {defaultModelConfig.liteModel.fallback && (
                <button
                  onClick={() =>
                    openModelConfig(
                      defaultModelConfig.liteModel.fallback!.providerId,
                      defaultModelConfig.liteModel.fallback!.model,
                    )
                  }
                  className="flex items-center justify-center w-10 h-10 rounded-lg border border-border bg-secondary/50 hover:bg-accent transition-colors flex-shrink-0"
                  title={t('configureModel')}
                >
                  <IconSliders className="w-4 h-4 text-muted-foreground" />
                </button>
              )}
            </div>
          </div>
        </div>
      </SettingsSection>

      {/* 智能路由配置 */}
      <SettingsSection
        title={
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/10">
              <IconRoute className="w-5 h-5 text-emerald-500" />
            </div>
            <span>{t('smartRouting.title')}</span>
          </div>
        }
        description={t('smartRouting.description')}
      >
        <div className="space-y-6">
          <label className="flex items-center gap-3 cursor-pointer">
            <button
              type="button"
              role="switch"
              aria-checked={isRoutingEnabled}
              onClick={handleRoutingToggle}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                isRoutingEnabled ? 'bg-emerald-500' : 'bg-muted-foreground/30'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  isRoutingEnabled ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <span className="text-sm font-medium text-foreground">{t('smartRouting.enable')}</span>
          </label>

          {isRoutingEnabled && (
            <div className="space-y-6">
              {/* Light Model */}
              <div className="p-5 bg-background/50 rounded-xl border border-border/50">
                <div className="flex items-center gap-2 mb-3">
                  <IconZap className="w-4 h-4 text-emerald-500" />
                  <span className="text-sm font-medium text-foreground">{t('smartRouting.lightModel')}</span>
                </div>
                <p className="text-xs text-muted-foreground mb-4">{t('smartRouting.lightModelDescription')}</p>
                <div className="space-y-4">
                  <div className="flex items-end gap-2">
                    <div className="flex-1">
                      <EnabledModelSelect
                        label={t('smartRouting.selectLightModel')}
                        value={defaultModelConfig.routingConfig?.lightModel?.primary ?? null}
                        onChange={handleRoutingLightModelChange}
                        enabledModels={enabledModels}
                        providers={providers}
                        isModelRestricted={isModelRestricted}
                      />
                    </div>
                    {defaultModelConfig.routingConfig?.lightModel?.primary && (
                      <button
                        onClick={() =>
                          openModelConfig(
                            defaultModelConfig.routingConfig!.lightModel.primary!.providerId,
                            defaultModelConfig.routingConfig!.lightModel.primary!.model,
                          )
                        }
                        className="flex items-center justify-center w-10 h-10 rounded-lg border border-border bg-secondary/50 hover:bg-accent transition-colors flex-shrink-0"
                        title={t('configureModel')}
                      >
                        <IconSliders className="w-4 h-4 text-muted-foreground" />
                      </button>
                    )}
                  </div>
                  <div className="pl-4 border-l-2 border-border/30">
                    <div className="flex items-center gap-2 mb-2">
                      <IconShield className="w-3.5 h-3.5 text-sky-500" />
                      <span className="text-xs font-medium text-muted-foreground">{t('fallbackModel')}</span>
                    </div>
                    <EnabledModelSelect
                      label={t('selectFallbackModel')}
                      value={defaultModelConfig.routingConfig?.lightModel?.fallback ?? null}
                      onChange={handleRoutingLightModelFallbackChange}
                      enabledModels={enabledModels}
                      providers={providers}
                      isModelRestricted={isModelRestricted}
                    />
                  </div>
                </div>
              </div>

              {/* Standard Model info */}
              <div className="p-5 bg-background/50 rounded-xl border border-border/50">
                <div className="flex items-center gap-2 mb-3">
                  <IconCpu className="w-4 h-4 text-blue-500" />
                  <span className="text-sm font-medium text-foreground">{t('smartRouting.standardModel')}</span>
                </div>
                <p className="text-xs text-muted-foreground">{t('smartRouting.standardModelDescription')}</p>
              </div>

              {/* Reasoning Model */}
              <div className="p-5 bg-background/50 rounded-xl border border-border/50">
                <div className="flex items-center gap-2 mb-3">
                  <IconBrain className="w-4 h-4 text-purple-500" />
                  <span className="text-sm font-medium text-foreground">{t('smartRouting.reasoningModel')}</span>
                </div>
                <p className="text-xs text-muted-foreground mb-4">{t('smartRouting.reasoningModelDescription')}</p>
                <div className="space-y-4">
                  <div className="flex items-end gap-2">
                    <div className="flex-1">
                      <EnabledModelSelect
                        label={t('smartRouting.selectReasoningModel')}
                        value={defaultModelConfig.routingConfig?.reasoningModel?.primary ?? null}
                        onChange={handleRoutingReasoningModelChange}
                        enabledModels={enabledModels}
                        providers={providers}
                        isModelRestricted={isModelRestricted}
                      />
                    </div>
                    {defaultModelConfig.routingConfig?.reasoningModel?.primary && (
                      <button
                        onClick={() =>
                          openModelConfig(
                            defaultModelConfig.routingConfig!.reasoningModel.primary!.providerId,
                            defaultModelConfig.routingConfig!.reasoningModel.primary!.model,
                          )
                        }
                        className="flex items-center justify-center w-10 h-10 rounded-lg border border-border bg-secondary/50 hover:bg-accent transition-colors flex-shrink-0"
                        title={t('configureModel')}
                      >
                        <IconSliders className="w-4 h-4 text-muted-foreground" />
                      </button>
                    )}
                  </div>
                  <div className="pl-4 border-l-2 border-border/30">
                    <div className="flex items-center gap-2 mb-2">
                      <IconShield className="w-3.5 h-3.5 text-sky-500" />
                      <span className="text-xs font-medium text-muted-foreground">{t('fallbackModel')}</span>
                    </div>
                    <EnabledModelSelect
                      label={t('selectFallbackModel')}
                      value={defaultModelConfig.routingConfig?.reasoningModel?.fallback ?? null}
                      onChange={handleRoutingReasoningModelFallbackChange}
                      enabledModels={enabledModels}
                      providers={providers}
                      isModelRestricted={isModelRestricted}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </SettingsSection>

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

          {orphanCount > 0 && (
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 rounded-lg border border-amber-500/30 bg-amber-500/5">
              <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
                <IconAlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{t('retrieval.orphanWarning', { count: orphanCount })}</span>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={dismissOrphanWarning}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  {t('retrieval.dismiss')}
                </button>
                <button
                  onClick={handleReindex}
                  disabled={reindexing}
                  className="text-xs font-medium px-3 py-1.5 rounded-md bg-amber-500/10 text-amber-700 dark:text-amber-400 hover:bg-amber-500/20 transition-colors disabled:opacity-50"
                >
                  {reindexing ? t('retrieval.reindexing') : t('retrieval.reindex')}
                </button>
              </div>
            </div>
          )}
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
