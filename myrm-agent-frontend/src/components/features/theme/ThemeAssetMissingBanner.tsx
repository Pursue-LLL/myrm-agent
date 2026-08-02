'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';

const ThemeAssetMissingBanner = () => {
  const t = useTranslations('settings.appearancePanel');

  return (
    <div
      role="status"
      className="fixed bottom-4 left-1/2 z-50 w-[min(92vw,28rem)] -translate-x-1/2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-foreground shadow-lg backdrop-blur-sm dark:border-amber-500/30 dark:bg-amber-500/5 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
    >
      <p className="font-medium">{t('assetMissingTitle')}</p>
      <p className="mt-1 text-xs text-muted-foreground">{t('assetMissingDesc')}</p>
      <Link
        href="/settings/preferences"
        className="mt-2 inline-block text-xs font-medium text-primary hover:underline underline-offset-4"
      >
        {t('assetMissingAction')}
      </Link>
    </div>
  );
};

export default ThemeAssetMissingBanner;
