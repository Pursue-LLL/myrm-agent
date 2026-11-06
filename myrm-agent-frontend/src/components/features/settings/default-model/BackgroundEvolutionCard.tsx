'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Sparkles as IconSparkles } from 'lucide-react';
import SettingsSection from '../sections/SettingsSection';
import { FallbackModelCard, ModelCardTitle } from './ModelCardParts';
import ModelSelectRow from './ModelSelectRow';

/** The model that runs background self-evolution and maintenance jobs, with its fallback. */
const BackgroundEvolutionCard = memo(() => {
  const t = useTranslations('settings.defaultModel');

  return (
    <SettingsSection
      title={
        <ModelCardTitle
          icon={<IconSparkles className="w-5 h-5 text-indigo-500" />}
          tint="bg-indigo-500/10"
          title={t('backgroundEvolutionModel')}
        />
      }
      description={t('backgroundEvolutionModelDescription')}
    >
      <div className="space-y-6">
        <ModelSelectRow slot="backgroundEvolution" label={t('selectModel')} />

        <div className="p-4 rounded-lg bg-indigo-500/5 border border-indigo-500/20 text-xs text-muted-foreground leading-relaxed">
          {t('backgroundEvolutionModelAdaptiveHint')}
        </div>

        <FallbackModelCard slot="backgroundEvolutionFallback" />
      </div>
    </SettingsSection>
  );
});

BackgroundEvolutionCard.displayName = 'BackgroundEvolutionCard';

export default BackgroundEvolutionCard;
