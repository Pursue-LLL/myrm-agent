'use client';

/**
 * [INPUT]
 * - `@/lib/cron/schedulerHealth` (`subscribeSchedulerHealth`, `getCachedSchedulerHealth`)
 * - `next-intl` (`cron.schedulerStatus`)
 * - `./cron-utils` (`formatTime`)
 *
 * [OUTPUT]
 * - `SchedulerHealthBadge`: Cron list header scheduler liveness dot + tooltip
 *
 * [POS]
 * Cron settings page inline scheduler health indicator; poll shared with AppLayout banner.
 */

import { memo, useEffect, useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { getCachedSchedulerHealth, subscribeSchedulerHealth, type SchedulerHealth } from '@/lib/cron/schedulerHealth';
import { formatTime } from './cron-utils';
import { cn } from '@/lib/utils/classnameUtils';

const STATUS_CONFIG = {
  green: { dot: 'bg-emerald-500', label: 'running', pulse: true },
  yellow: { dot: 'bg-amber-500', label: 'degraded', pulse: false },
  red: { dot: 'bg-red-500', label: 'stopped', pulse: false },
} as const;

const SchedulerHealthBadge = memo(function SchedulerHealthBadge() {
  const t = useTranslations('cron');
  const locale = useLocale();
  const [health, setHealth] = useState<SchedulerHealth | null>(() => getCachedSchedulerHealth());

  useEffect(() => subscribeSchedulerHealth(setHealth), []);

  if (!health) {
    return null;
  }

  const cfg = STATUS_CONFIG[health.status];

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="inline-flex items-center gap-1.5 text-xs text-muted-foreground cursor-default">
          <span className={cn('h-2 w-2 rounded-full', cfg.dot, cfg.pulse && 'animate-pulse')} />
          <span>{t(`schedulerStatus.${cfg.label}`)}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="text-xs space-y-0.5">
        {health.last_tick_at && (
          <p>
            {t('schedulerStatus.lastTick')}: {formatTime(health.last_tick_at, locale)}
          </p>
        )}
        {health.tick_errors > 0 && (
          <p className="text-amber-500">
            {t('schedulerStatus.errors')}: {health.tick_errors}
          </p>
        )}
      </TooltipContent>
    </Tooltip>
  );
});

export default SchedulerHealthBadge;
