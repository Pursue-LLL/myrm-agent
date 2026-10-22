'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import type { GoalAction, GoalStatus } from './goalStatusTypes';
import { formatResumeTime } from './goalStatusUtils';

interface GoalUsageLimitRowProps {
  /** `wait`: the app resumes by itself; `paused`: the user decides. */
  status: GoalStatus;
  resumeAt: string | undefined;
  onAction: (action: GoalAction) => Promise<unknown>;
}

export function GoalUsageLimitRow({ status, resumeAt, onAction }: GoalUsageLimitRowProps) {
  const t = useTranslations('Goal');
  const locale = useLocale();
  const [isPending, setIsPending] = useState(false);

  const isWaiting = status === 'wait';
  const time = formatResumeTime(resumeAt, locale);
  const messageKey = isWaiting
    ? time
      ? 'usageLimitWaiting'
      : 'usageLimitWaitingNoTime'
    : time
      ? 'usageLimitPaused'
      : 'usageLimitPausedNoTime';

  const handleClick = async () => {
    setIsPending(true);
    try {
      await onAction(isWaiting ? 'unwait' : 'resume');
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div
      data-testid="goal-usage-limit-row"
      className="flex flex-col gap-2 border-t border-border/60 bg-muted/30 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground" aria-live="polite">
        <span
          aria-hidden="true"
          className={cn(
            'mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full',
            isWaiting ? 'animate-pulse bg-blue-500' : 'bg-yellow-500',
          )}
        />
        <span>{t(messageKey, { time: time ?? '' })}</span>
      </p>
      <Button
        data-testid="goal-usage-limit-action"
        variant="outline"
        size="sm"
        className="self-start sm:self-auto"
        disabled={isPending}
        onClick={handleClick}
      >
        {t(isWaiting ? 'usageLimitRetryNow' : 'usageLimitResume')}
      </Button>
    </div>
  );
}
