'use client';

import { memo, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { IconAlertTriangle, IconShield } from '@/components/features/icons/PremiumIcons';
import ModelSelectRow from './ModelSelectRow';
import type { ModelSlotId } from './modelSlots';

interface ModelCardTitleProps {
  icon: ReactNode;
  /** Background class of the icon chip, e.g. `bg-amber-500/10`. */
  tint: string;
  title: string;
}

export function ModelCardTitle({ icon, tint, title }: ModelCardTitleProps) {
  return (
    <div className="flex items-center gap-3">
      <div className={`p-2 rounded-lg ${tint}`}>{icon}</div>
      <span>{title}</span>
    </div>
  );
}

const WARNING_CLASS = {
  caution:
    'flex items-start gap-2.5 p-3.5 mt-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-600 dark:text-yellow-500',
  missingFallback:
    'flex items-start gap-2.5 p-3.5 mt-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-500',
} as const;

interface ModelWarningProps {
  /** `caution`: the choice may misbehave; `missingFallback`: the choice has no backup yet. */
  tone: keyof typeof WARNING_CLASS;
  message: string;
}

export const ModelWarning = memo<ModelWarningProps>(({ tone, message }) => (
  <div className={WARNING_CLASS[tone]}>
    <IconAlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
    <div className="text-xs font-medium leading-relaxed">{message}</div>
  </div>
));

ModelWarning.displayName = 'ModelWarning';

interface FallbackModelCardProps {
  slot: ModelSlotId;
}

/** The "fallback model" card shared by the base, quick and background-evolution models. */
export const FallbackModelCard = memo<FallbackModelCardProps>(({ slot }) => {
  const t = useTranslations('settings.defaultModel');
  return (
    <div className="p-5 bg-background/50 rounded-xl border border-border/50">
      <div className="flex items-center gap-2 mb-3">
        <IconShield className="w-4 h-4 text-sky-500" />
        <span className="text-sm font-medium text-foreground">{t('fallbackModel')}</span>
      </div>
      <p className="text-xs text-muted-foreground mb-4">{t('fallbackModelDescription')}</p>
      <ModelSelectRow slot={slot} label={t('selectFallbackModel')} />
    </div>
  );
});

FallbackModelCard.displayName = 'FallbackModelCard';
