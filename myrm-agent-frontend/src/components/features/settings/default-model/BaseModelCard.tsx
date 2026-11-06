'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconCpu } from '@/components/features/icons/PremiumIcons';
import { getProviderCategory } from '@/store/config/providerTypes';
import SettingsSection from '../sections/SettingsSection';
import { FallbackModelCard, ModelCardTitle, ModelWarning } from './ModelCardParts';
import ModelSelectRow from './ModelSelectRow';
import { useModelSlot } from './modelSlots';
import VideoFallbackCard from './VideoFallbackCard';
import VisionFallbackCard from './VisionFallbackCard';

/** The base model with its fallback, plus the vision and video fallbacks used when it cannot read that media. */
const BaseModelCard = memo(() => {
  const t = useTranslations('settings.defaultModel');
  const [basePrimary] = useModelSlot('base');
  const [baseFallback] = useModelSlot('baseFallback');

  return (
    <SettingsSection
      title={
        <ModelCardTitle
          icon={<IconCpu className="w-5 h-5 text-primary" />}
          tint="bg-primary/10"
          title={t('baseModel')}
        />
      }
      description={t('baseModelDescription')}
    >
      <div className="space-y-8">
        <ModelSelectRow slot="base" label={t('selectModel')} />

        {basePrimary && getProviderCategory(basePrimary.providerId) === 'local' && (
          <ModelWarning tone="caution" message={t('localModelWarning')} />
        )}

        {basePrimary && !baseFallback && <ModelWarning tone="missingFallback" message={t('noFallbackWarning')} />}

        <FallbackModelCard slot="baseFallback" />
        <VisionFallbackCard />
        <VideoFallbackCard />
      </div>
    </SettingsSection>
  );
});

BaseModelCard.displayName = 'BaseModelCard';

export default BaseModelCard;
