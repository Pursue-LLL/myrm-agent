'use client';

import { useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import useProviderStore from '@/store/useProviderStore';
import { IconRoute, IconZap, IconBrain, IconCpu } from '@/components/features/icons/PremiumIcons';
import type { SingleModelSelection } from '@/store/config/providerTypes';

const REASONING_MODEL_KEYWORDS = [
  'o1', 'o3', 'o4-mini', 'deepseek-r1', 'qwq', 'reasoning', 'opus',
] as const;

const LITE_MODEL_KEYWORDS = [
  'mini', 'flash', 'haiku', 'nano', 'lite', 'small',
] as const;

const LITE_SIZE_RE = /\b[1-8]b\b/i;

interface SmartRoutingStepProps {
  onComplete: () => void;
  onSkip: () => void;
}

function classifyModel(modelName: string): 'lite' | 'reasoning' | 'standard' {
  const lower = modelName.toLowerCase();
  if (REASONING_MODEL_KEYWORDS.some((p) => lower.includes(p))) return 'reasoning';
  if (LITE_MODEL_KEYWORDS.some((p) => lower.includes(p))) return 'lite';
  if (LITE_SIZE_RE.test(lower)) return 'lite';
  return 'standard';
}

export default function SmartRoutingStep({ onComplete, onSkip }: SmartRoutingStepProps) {
  const t = useTranslations('boot.onboarding.routing');

  const getEnabledModels = useProviderStore((s) => s.getEnabledModels);
  const defaultModelConfig = useProviderStore((s) => s.defaultModelConfig);

  const enabledModels = useMemo(() => getEnabledModels(), [getEnabledModels]);
  const setRoutingEnabled = useProviderStore((s) => s.setRoutingEnabled);
  const setRoutingLightModel = useProviderStore((s) => s.setRoutingLightModel);
  const setRoutingReasoningModel = useProviderStore((s) => s.setRoutingReasoningModel);

  const recommendation = useMemo(() => {
    if (enabledModels.length < 2) return null;

    const classified = enabledModels.map((m) => ({
      ...m,
      tier: classifyModel(m.model),
    }));

    const baseModel = defaultModelConfig.baseModel.primary;
    const liteCandidate = classified.find(
      (m) => m.tier === 'lite' && !(m.providerId === baseModel?.providerId && m.model === baseModel?.model),
    );
    const reasoningCandidate = classified.find(
      (m) => m.tier === 'reasoning' && !(m.providerId === baseModel?.providerId && m.model === baseModel?.model),
    );

    if (!liteCandidate && !reasoningCandidate) return null;

    return { lite: liteCandidate, reasoning: reasoningCandidate };
  }, [enabledModels, defaultModelConfig.baseModel.primary]);

  const handleEnable = useCallback(() => {
    setRoutingEnabled(true);

    if (recommendation?.lite) {
      const selection: SingleModelSelection = {
        providerId: recommendation.lite.providerId,
        model: recommendation.lite.model,
      };
      setRoutingLightModel(selection);
    }

    if (recommendation?.reasoning) {
      const selection: SingleModelSelection = {
        providerId: recommendation.reasoning.providerId,
        model: recommendation.reasoning.model,
      };
      setRoutingReasoningModel(selection);
    }

    onComplete();
  }, [recommendation, setRoutingEnabled, setRoutingLightModel, setRoutingReasoningModel, onComplete]);

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4 p-5 rounded-xl border bg-card">
        <div className="rounded-xl bg-emerald-500/10 p-3 shrink-0">
          <IconRoute className="h-7 w-7 text-emerald-500" />
        </div>
        <div className="flex flex-col gap-2 min-w-0">
          <h3 className="text-lg font-semibold text-foreground">{t('title')}</h3>
          <p className="text-sm text-muted-foreground leading-relaxed">{t('description')}</p>
          <div className="mt-1 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-sm font-medium w-fit">
            <IconZap className="h-4 w-4" />
            {t('savingsEstimate')}
          </div>
        </div>
      </div>

      {recommendation && (
        <div className="grid gap-3 sm:grid-cols-3">
          {recommendation.lite && (
            <div className="flex items-start gap-3 p-4 rounded-xl border bg-card/50">
              <IconZap className="h-5 w-5 text-emerald-500 shrink-0 mt-0.5" />
              <div className="min-w-0">
                <div className="text-sm font-medium text-foreground">{t('liteLabel')}</div>
                <div className="text-xs text-muted-foreground truncate mt-0.5">
                  {recommendation.lite.model}
                </div>
              </div>
            </div>
          )}

          <div className="flex items-start gap-3 p-4 rounded-xl border bg-card/50">
            <IconCpu className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <div className="text-sm font-medium text-foreground">{t('standardLabel')}</div>
              <div className="text-xs text-muted-foreground truncate mt-0.5">
                {defaultModelConfig.baseModel.primary?.model ?? t('currentModel')}
              </div>
            </div>
          </div>

          {recommendation.reasoning && (
            <div className="flex items-start gap-3 p-4 rounded-xl border bg-card/50">
              <IconBrain className="h-5 w-5 text-purple-500 shrink-0 mt-0.5" />
              <div className="min-w-0">
                <div className="text-sm font-medium text-foreground">{t('reasoningLabel')}</div>
                <div className="text-xs text-muted-foreground truncate mt-0.5">
                  {recommendation.reasoning.model}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="flex flex-col items-center gap-3 pt-2">
        <Button size="lg" className="w-full sm:w-auto min-w-[220px]" onClick={handleEnable}>
          <IconRoute className="mr-2 h-4 w-4" />
          {t('enableButton')}
        </Button>
        <Button variant="ghost" size="sm" onClick={onSkip}>
          {t('skipButton')}
        </Button>
      </div>
    </div>
  );
}
