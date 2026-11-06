'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconZap } from '@/components/features/icons/PremiumIcons';
import type { CustomModelInfo, SingleModelSelection } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';
import SettingsSection from '../sections/SettingsSection';
import { FallbackModelCard, ModelCardTitle, ModelWarning } from './ModelCardParts';
import ModelSelectRow from './ModelSelectRow';
import { useModelSlot } from './modelSlots';

/** Whether the quick model reads less context than the base model, so long inputs would not fit it. */
export function isLiteWindowBelowBase(
  base: SingleModelSelection | null,
  lite: SingleModelSelection | null,
  customModelInfo: Record<string, Pick<CustomModelInfo, 'max_input_tokens'>>,
): boolean {
  if (!base || !lite) {
    return false;
  }
  const baseWindow = customModelInfo[`${base.providerId}/${base.model}`]?.max_input_tokens;
  const liteWindow = customModelInfo[`${lite.providerId}/${lite.model}`]?.max_input_tokens;
  return Boolean(baseWindow && liteWindow && liteWindow < baseWindow);
}

/** The quick model that serves light requests, with its fallback. */
const LiteModelCard = memo(() => {
  const t = useTranslations('settings.defaultModel');
  const [basePrimary] = useModelSlot('base');
  const [litePrimary] = useModelSlot('lite');
  const [liteFallback] = useModelSlot('liteFallback');
  const customModelInfo = useProviderStore((state) => state.customModelInfo);

  return (
    <SettingsSection
      title={
        <ModelCardTitle
          icon={<IconZap className="w-5 h-5 text-amber-500" />}
          tint="bg-amber-500/10"
          title={t('liteModel')}
        />
      }
      description={t('liteModelDescription')}
    >
      <div className="space-y-8">
        <ModelSelectRow slot="lite" label={t('selectModel')} />

        {isLiteWindowBelowBase(basePrimary, litePrimary, customModelInfo) && (
          <ModelWarning tone="caution" message={t('liteModelContextWindowWarning')} />
        )}

        {litePrimary && !liteFallback && <ModelWarning tone="missingFallback" message={t('liteNoFallbackWarning')} />}

        <FallbackModelCard slot="liteFallback" />
      </div>
    </SettingsSection>
  );
});

LiteModelCard.displayName = 'LiteModelCard';

export default LiteModelCard;
