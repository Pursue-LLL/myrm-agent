'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { IconCheck } from './catalog-icons';
import type { CatalogConnectionState } from './catalog-connection';

interface CatalogConnectionStatusProps {
  state: Exclude<CatalogConnectionState, 'available'>;
  className?: string;
}

/** Connection status of a catalog service, shared by the catalog cards and the onboarding tool picker. */
export const CatalogConnectionStatus = memo<CatalogConnectionStatusProps>(({ state, className }) => {
  const t = useTranslations('settings.integrationCatalog');

  if (state === 'connected') {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400',
          className,
        )}
      >
        <IconCheck className="h-3.5 w-3.5" aria-hidden="true" />
        {t('connected')}
      </span>
    );
  }

  return (
    <span className={cn('text-muted-foreground inline-flex items-center gap-1.5 text-xs font-medium', className)}>
      <span className="bg-muted-foreground/50 h-1.5 w-1.5 rounded-full" aria-hidden="true" />
      {t('disabled')}
    </span>
  );
});

CatalogConnectionStatus.displayName = 'CatalogConnectionStatus';
