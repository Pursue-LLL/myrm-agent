'use client';

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

interface OpenCodeContributorNoticeProps {
  variant: 'provider' | 'model';
}

const OpenCodeContributorNotice = memo<OpenCodeContributorNoticeProps>(({ variant }) => {
  const t = useTranslations('settings.modelService.opencodeContributor');
  const [expanded, setExpanded] = useState(variant === 'provider');

  return (
    <div
      className={cn(
        'rounded-xl border border-amber-500/30 bg-amber-500/5',
        variant === 'provider' ? 'p-4' : 'px-3 py-2',
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-start justify-between gap-2 text-left"
      >
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
            {t('badge')}
          </p>
          <p className="mt-1 text-sm text-foreground">
            {variant === 'provider' ? t('providerSummary') : t('modelSummary')}
          </p>
        </div>
        <ChevronDown
          className={cn(
            'mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground transition-transform',
            expanded && 'rotate-180',
          )}
        />
      </button>
      {expanded && (
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
          <li>{t('stepEnableConsent')}</li>
          <li>{t('stepOrUseStandard')}</li>
        </ul>
      )}
    </div>
  );
});

OpenCodeContributorNotice.displayName = 'OpenCodeContributorNotice';

export default OpenCodeContributorNotice;
