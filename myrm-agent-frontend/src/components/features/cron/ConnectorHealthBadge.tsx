'use client';

/**
 * [INPUT]
 * - `@/services/cron` (`getConnectorsHealth`, `ConnectorHealthItem`, `CronJob`)
 * - `./cron-utils` (`connectorCategoryLabelKey`, `formatTime`)
 * - `next-intl` (`cron.connectorHealthStatus`, `cron.connectorStatus*`, `cron.connectorCategory*`, `cron.connectorFailureStreak`, `cron.connectorLastFailedAt`)
 * - `@/components/primitives/popover` (details of a failing destination, reachable by tap as well as by mouse)
 *
 * [OUTPUT]
 * - `ConnectorHealthBadge`: health pill of the destination a job delivers to; while it is failing, a popover tells why
 *
 * [POS]
 * Header of the delivery editor in a job's settings. The status is the server's verdict over the destination's recent
 * deliveries, not the job's own run failures; nothing is shown until the destination has been delivered to.
 */

import { memo, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Activity } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { cn } from '@/lib/utils/classnameUtils';
import { getConnectorsHealth, type ConnectorHealthItem, type CronJob } from '@/services/cron';
import { connectorCategoryLabelKey, formatTime } from './cron-utils';

const PILL_CLASS = 'inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border font-medium';

const STATUS_STYLE = {
  healthy: {
    labelKey: 'connectorStatusHealthy',
    tone: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20',
  },
  degraded: {
    labelKey: 'connectorStatusDegraded',
    tone: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
  },
  down: {
    labelKey: 'connectorStatusDown',
    tone: 'bg-destructive/10 text-destructive-text border-destructive/20',
  },
} as const satisfies Record<ConnectorHealthItem['status'], { labelKey: string; tone: string }>;

type BadgeJob = Pick<CronJob, 'id' | 'delivery' | 'last_run_at'>;

/**
 * The health of the destination the job delivers to, or `null` while it is not known: not loaded yet, not an outbound
 * destination, or the request failed. A new destination or a new run can change the verdict, so either reloads it.
 */
function useDestinationHealth(job: BadgeJob): ConnectorHealthItem | null {
  const [health, setHealth] = useState<ConnectorHealthItem | null>(null);
  const channel = job.delivery?.channel;
  const target = job.delivery?.target;

  // A response for a destination the user has already left must not replace the one they are looking at.
  useEffect(() => {
    let stale = false;
    getConnectorsHealth()
      .then((res) => {
        if (!stale) {
          setHealth(res.items.find((item) => item.bound_job_ids.includes(job.id)) ?? null);
        }
      })
      .catch(() => {
        if (!stale) {
          setHealth(null);
        }
      });
    return () => {
      stale = true;
    };
  }, [job.id, channel, target, job.last_run_at]);

  return health;
}

const ConnectorHealthBadge = memo(function ConnectorHealthBadge({ job }: { job: BadgeJob }) {
  const t = useTranslations('cron');
  const locale = useLocale();
  const health = useDestinationHealth(job);

  // Without a delivery to judge there is no verdict: a destination never delivered to is not "healthy".
  if (!health || health.total_deliveries === 0) {
    return null;
  }

  const { labelKey, tone } = STATUS_STYLE[health.status];
  // Read aloud, the verdict alone is just "Healthy"; the hidden prefix says what it is the verdict of.
  const pill = (
    <>
      <Activity aria-hidden="true" className="h-2.5 w-2.5" />
      <span className="sr-only">{t('connectorHealthStatus')}: </span>
      <span data-testid="connector-health-badge">{t(labelKey)}</span>
    </>
  );

  if (health.consecutive_failures === 0) {
    return <span className={cn(PILL_CLASS, tone)}>{pill}</span>;
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className={cn(PILL_CLASS, tone, 'cursor-pointer')}>
          {pill}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 max-w-[calc(100vw-2rem)] space-y-1.5 rounded-xl p-3 text-xs">
        <p className="font-semibold">{t('connectorFailureStreak', { count: health.consecutive_failures })}</p>
        {health.last_error_category && <p>{t(connectorCategoryLabelKey(health.last_error_category))}</p>}
        {health.last_error_message && (
          <p className="line-clamp-4 break-words font-mono text-[10px] text-muted-foreground">
            {health.last_error_message}
          </p>
        )}
        {health.last_failed_at && (
          <p className="text-muted-foreground">
            {t('connectorLastFailedAt', { time: formatTime(health.last_failed_at, locale) })}
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
});

export default ConnectorHealthBadge;
