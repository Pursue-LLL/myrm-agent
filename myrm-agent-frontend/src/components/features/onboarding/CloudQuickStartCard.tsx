'use client';

import { useTranslations } from 'next-intl';
import { IconArrowRight, IconZap } from '@/components/features/icons/PremiumIcons';

export const CLOUD_PROVIDERS = [
  { id: 'gemini', nameKey: 'cloudProviderGemini', hintKey: 'cloudProviderGeminiHint' },
  { id: 'siliconflow', nameKey: 'cloudProviderSiliconFlow', hintKey: 'cloudProviderSiliconFlowHint' },
  { id: 'openrouter', nameKey: 'cloudProviderOpenRouter', hintKey: 'cloudProviderOpenRouterHint' },
] as const;

interface CloudQuickStartCardProps {
  onSelectProvider: () => void;
}

export default function CloudQuickStartCard({ onSelectProvider }: CloudQuickStartCardProps) {
  const tBoot = useTranslations('boot');

  return (
    <div className="p-4 rounded-xl border bg-card space-y-4">
      <div className="flex items-start gap-4">
        <div className="rounded-xl bg-accent-warm/10 p-3">
          <IconZap className="h-6 w-6 text-accent-warm" />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-base font-semibold">{tBoot('onboarding.cloudQuickStart')}</span>
          <span className="text-sm text-muted-foreground">{tBoot('onboarding.cloudQuickStartHint')}</span>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {CLOUD_PROVIDERS.map(({ id, nameKey, hintKey }) => (
          <button
            key={id}
            type="button"
            onClick={onSelectProvider}
            className="flex items-center justify-between gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-accent/50"
          >
            <div className="min-w-0">
              <div className="text-sm font-medium truncate">{tBoot(`onboarding.${nameKey}`)}</div>
              <div className="text-xs text-muted-foreground truncate">{tBoot(`onboarding.${hintKey}`)}</div>
            </div>
            <IconArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          </button>
        ))}
      </div>
    </div>
  );
}
