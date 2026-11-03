'use client';

import { useTranslations } from 'next-intl';

export function EmbedFail({ label }: { label: string }) {
  const t = useTranslations('embeds');
  return (
    <span className="flex size-full items-center justify-center rounded-lg border border-dashed border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive/70">
      {t('loadFailed', { label })}
    </span>
  );
}
