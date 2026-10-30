'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, Lock } from 'lucide-react';
import { Button } from '@/components/primitives/button';

interface OptimizeLockedNoticeProps {
  /** The lock is being changed; a second request would race the first. */
  isToggling: boolean;
  /** Clears the skill's evolution lock, which optimizing needs off. */
  onUnlock: () => void;
}

/** Why Optimize is off for a locked skill, and the one action that turns it on. */
const OptimizeLockedNotice = memo(({ isToggling, onUnlock }: OptimizeLockedNoticeProps) => {
  const t = useTranslations('settings.skills');

  return (
    <output className="flex shrink-0 flex-col items-start gap-2 border-t bg-muted/30 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
      <span className="flex min-w-0 items-start gap-2">
        <Lock size={14} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
        <span className="text-xs text-muted-foreground">{t('detail.optimizeLockedHint')}</span>
      </span>
      <Button variant="outline" size="sm" className="h-7 shrink-0 text-xs" onClick={onUnlock} disabled={isToggling}>
        {isToggling && <Loader2 className="animate-spin mr-1" size={12} />}
        {t('detail.evolutionUnlock')}
      </Button>
    </output>
  );
});

OptimizeLockedNotice.displayName = 'OptimizeLockedNotice';

export default OptimizeLockedNotice;
