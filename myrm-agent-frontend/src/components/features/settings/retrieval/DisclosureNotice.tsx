'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconShield } from '@/components/features/icons/PremiumIcons';

/** What leaves the machine for the chosen providers, and where reranking applies. */
const DisclosureNotice = memo(() => {
  const t = useTranslations('settings.retrieval');

  return (
    <div className="space-y-2 rounded-xl border border-border/50 bg-muted/20 p-4">
      <div className="flex items-center gap-2">
        <IconShield className="h-4 w-4 shrink-0 text-muted-foreground" />
        <p className="text-sm font-medium text-foreground">{t('disclosure.title')}</p>
      </div>
      <ul className="list-disc space-y-1 pl-6 text-xs leading-relaxed text-muted-foreground">
        <li>{t('disclosure.embedding')}</li>
        <li>{t('disclosure.rerank')}</li>
        <li>{t('disclosure.pageReading')}</li>
      </ul>
      <p className="pl-6 text-xs leading-relaxed text-muted-foreground">{t('disclosure.coverage')}</p>
    </div>
  );
});

DisclosureNotice.displayName = 'DisclosureNotice';

export default DisclosureNotice;
