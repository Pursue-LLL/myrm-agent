'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { apiRequest } from '@/lib/api';
import { cn } from '@/lib/utils/classnameUtils';

interface SchedulerHealth {
  status: 'green' | 'yellow' | 'red';
  running: boolean;
  last_tick_at: string | null;
  tick_errors: number;
  last_tick_age_seconds: number | null;
  has_timer: boolean;
}

const STATUS_CONFIG = {
  green: { dot: 'bg-emerald-500', label: 'running', pulse: true },
  yellow: { dot: 'bg-amber-500', label: 'degraded', pulse: false },
  red: { dot: 'bg-red-500', label: 'stopped', pulse: false },
} as const;

const POLL_INTERVAL_MS = 30_000;

const SchedulerHealthBadge = memo(function SchedulerHealthBadge() {
  const t = useTranslations('cron');
  const [health, setHealth] = useState<SchedulerHealth | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    try {
      const res = await apiRequest<SchedulerHealth>('/cron/scheduler/health');
      if (res) setHealth(res);
    } catch {
      // Treat API failure as red
      setHealth({ status: 'red', running: false, last_tick_at: null, tick_errors: 0, last_tick_age_seconds: null, has_timer: false });
    }
  }, []);

  useEffect(() => {
    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [poll]);

  if (!health) return null;

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
            {t('schedulerStatus.lastTick')}: {new Date(health.last_tick_at).toLocaleTimeString()}
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
