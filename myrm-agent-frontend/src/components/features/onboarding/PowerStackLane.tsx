'use client';

import { memo } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

/**
 * [POS]
 * 极客多订阅三栏 honest lane（纯展示 + 深链既有页，不碰引擎）。
 * 文案零价格数字（防与计费 catalog 漂移），价格以 /pricing 页为准。
 */

const COLUMNS = ['external', 'orchestrator', 'local'] as const;

const COLUMN_ROUTES = {
  external: '/settings/models',
  orchestrator: '/settings/agents',
  local: '/settings/models',
} as const;

const PowerStackLane = memo(() => {
  const t = useTranslations('boot.onboarding.powerStack');
  const router = useRouter();

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-sm font-bold text-foreground">{t('title')}</p>
      <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{t('description')}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {COLUMNS.map((column) => (
          <button
            key={column}
            type="button"
            onClick={() => router.push(COLUMN_ROUTES[column])}
            className="rounded-xl border border-white/10 bg-black/20 p-3 text-left hover:bg-white/5 transition-colors"
          >
            <p className="text-xs font-bold text-foreground">{t(`columns.${column}.title`)}</p>
            <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
              {t(`columns.${column}.description`)}
            </p>
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={() => router.push('/pricing')}
        className="mt-3 text-xs font-medium text-indigo-400 underline underline-offset-2 hover:no-underline"
      >
        {t('pricingLink')}
      </button>
    </div>
  );
});

PowerStackLane.displayName = 'PowerStackLane';
export default PowerStackLane;
