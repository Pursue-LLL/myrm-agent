'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldWarning } from '@phosphor-icons/react';

import { humanizeToolLine } from '@/lib/humanize';
import type { CronBlockedAction } from '@/services/cron';

interface CronRunBlockedActionsProps {
  /** Exact number of stopped actions in the run; can exceed what `actions` lists. */
  count: number;
  actions: CronBlockedAction[];
}

/** Explains what the safety rules stopped in one run, so a skipped step is never left to guesswork. */
const CronRunBlockedActions = memo<CronRunBlockedActionsProps>(({ count, actions }) => {
  const t = useTranslations('cron');
  const tHumanize = useTranslations('humanize');
  const unlisted = count - actions.reduce((sum, action) => sum + action.count, 0);

  return (
    <div className="space-y-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2.5">
      <div className="flex items-start gap-2">
        <ShieldWarning aria-hidden="true" weight="duotone" className="mt-px h-4 w-4 shrink-0 text-warning" />
        <p className="text-xs font-medium leading-snug text-foreground">{t('blockedTitle', { count })}</p>
      </div>
      {actions.length > 0 && (
        <ul className="space-y-1.5 pl-6">
          {actions.map(({ tool, reason, count: occurrences }, index) => (
            <li key={`${index}-${tool}`} className="min-w-0 text-[11px] leading-snug">
              <p className="font-medium text-foreground">
                {humanizeToolLine(tool, {}, tHumanize, 'ask')}
                {occurrences > 1 && (
                  <span className="ml-1.5 font-normal tabular-nums text-muted-foreground">×{occurrences}</span>
                )}
              </p>
              {reason && <p className="mt-0.5 break-words text-muted-foreground">{reason}</p>}
            </li>
          ))}
          {unlisted > 0 && (
            <li className="text-[11px] text-muted-foreground">{t('blockedMore', { count: unlisted })}</li>
          )}
        </ul>
      )}
      <p className="pl-6 text-[11px] leading-relaxed text-muted-foreground">{t('blockedHint')}</p>
    </div>
  );
});

CronRunBlockedActions.displayName = 'CronRunBlockedActions';
export default CronRunBlockedActions;
