'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { useShallow } from 'zustand/react/shallow';
import { IconImage } from '@/components/features/icons/PremiumIcons';
import { getConfigSyncManager } from '@/services/config/ConfigSyncManager';
import { checkVisionFallbackHealth } from '@/services/llm-config';
import type { SingleModelSelection } from '@/store/config/providerTypes';
import {
  findRecommendedVisionFallbackSelection,
  shouldOfferVisionFallbackRecommendation,
} from '@/store/config/visionCapability';
import useProviderStore from '@/store/useProviderStore';
import MediaFallbackCard, { useFallbackHealthCheck, type MediaFallbackCopy } from './MediaFallbackCard';
import { useModelSlot } from './modelSlots';

interface VisionRecommendation extends SingleModelSelection {
  providerName: string;
}

type ProviderState = ReturnType<typeof useProviderStore.getState>;

/** The enabled vision-capable model to suggest while neither the base model nor a vision fallback can read images. */
function selectVisionRecommendation(state: ProviderState): VisionRecommendation | null {
  const { defaultModelConfig, getModelInfo } = state;
  if (!shouldOfferVisionFallbackRecommendation(defaultModelConfig, getModelInfo)) {
    return null;
  }
  const enabledModels = state.getEnabledModels();
  const selection = findRecommendedVisionFallbackSelection(
    enabledModels,
    getModelInfo,
    defaultModelConfig.baseModel?.primary ?? null,
  );
  if (!selection) {
    return null;
  }
  const providerName =
    enabledModels.find((entry) => entry.providerId === selection.providerId && entry.model === selection.model)
      ?.providerName ?? selection.providerId;
  return { ...selection, providerName };
}

const VisionFallbackCard = memo(() => {
  const t = useTranslations('settings.defaultModel');
  const recommendation = useProviderStore(useShallow(selectVisionRecommendation));
  const [, setVisionFallback] = useModelSlot('vision');
  const health = useFallbackHealthCheck(checkVisionFallbackHealth, t('visionHealthNetworkError'));

  const applyRecommendation = async () => {
    if (!recommendation) {
      toast.error(t('visionRecommendNone'));
      return;
    }
    setVisionFallback({ providerId: recommendation.providerId, model: recommendation.model });
    toast.success(t('visionRecommendApplied', { provider: recommendation.providerName, model: recommendation.model }));
    try {
      await getConfigSyncManager().forceSync();
    } catch {
      // Health probe reads server config; continue even if sync fails so user sees probe result.
    }
    await health.check();
  };

  const copy: MediaFallbackCopy = {
    title: t('visionFallbackModel'),
    description: t('visionFallbackModelDescription'),
    fallbackDescription: t('visionFallbackModelFallbackDescription'),
    selectFallback: t('selectVisionFallbackModel'),
    health: {
      test: t('visionHealthTest'),
      checking: t('visionHealthChecking'),
      unknown: t('visionHealthUnknown'),
      notConfigured: t('visionHealthNotConfigured'),
      okHint: t('visionHealthOkHint'),
      ok: (latency) => t('visionHealthOk', { latency }),
      failed: (error) => t('visionHealthFailed', { error }),
      failedModel: (model) => t('visionHealthFailedModel', { model }),
      failedEndpoint: (endpoint) => t('visionHealthFailedEndpoint', { endpoint }),
      resolvedModel: (configured, resolved) => t('visionHealthResolvedModel', { configured, resolved }),
    },
  };

  return (
    <MediaFallbackCard
      icon={<IconImage className="w-4 h-4 text-purple-500" />}
      copy={copy}
      primarySlot="vision"
      fallbackSlot="visionFallback"
      health={health}
    >
      {recommendation && (
        <div className="mb-4 rounded-lg border border-purple-500/20 bg-purple-500/5 px-3 py-3 dark:border-purple-400/20 dark:bg-purple-400/5">
          <p className="text-xs text-muted-foreground mb-1">{t('visionRecommendHint')}</p>
          <p className="mb-3 break-all text-xs font-medium text-foreground">
            {t('visionRecommendPreview', { provider: recommendation.providerName, model: recommendation.model })}
          </p>
          <button
            type="button"
            onClick={applyRecommendation}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-purple-500/30 bg-background/80 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent sm:w-auto"
          >
            {t('visionRecommendButton')}
          </button>
        </div>
      )}
    </MediaFallbackCard>
  );
});

VisionFallbackCard.displayName = 'VisionFallbackCard';

export default VisionFallbackCard;
