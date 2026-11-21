'use client';

/**
 * [INPUT]
 * - `@/services/cron` (`getJobDeliveryHealth`, `DeliveryHealth`, `CronJob`)
 * - `./cron-utils` (`connectorCategoryLabelKey`, `connectorCategoryHintKey`, `formatTime`)
 * - `next-intl` (`cron.connectorHealthStatus`, `cron.connectorStatus*`, `cron.connectorCategory*`, `cron.connectorFailureStreak`, `cron.connectorLastFailedAt`)
 * - `@/components/primitives/popover` (why a destination is failing and what to do about it, reachable by tap as well as by mouse)
 *
 * [OUTPUT]
 * - `ConnectorHealthBadge`: health pill of the destination a job delivers to; while it is failing, a popover says why and what to do
 *
 * [POS]
 * Header of the delivery editor in a job's settings. The status is the server's verdict over the destination's recent
 * deliveries, not the job's own run failures; nothing is shown until the destination has been delivered to.
 */

import { memo, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Activity, ChevronDown } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { cn } from '@/lib/utils/classnameUtils';
import { getJobDeliveryHealth, type CronJob, type DeliveryHealth } from '@/services/cron';
import { connectorCategoryHintKey, connectorCategoryLabelKey, formatTime } from './cron-utils';

const PILL_CLASS = 'inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border font-medium';
// Only a pill that opens a popover is a control.
const PILL_BUTTON_CLASS =
  'group cursor-pointer transition-colors hover:bg-current/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

// Light text on a 10% tint has to stay readable: green-800 and the warning token are both above 4.5:1.
const STATUS_STYLE = {
  healthy: {
    labelKey: 'connectorStatusHealthy',
    tone: 'bg-green-500/10 text-green-800 dark:text-green-400 border-green-500/20',
  },
  degraded: {
    labelKey: 'connectorStatusDegraded',
    tone: 'bg-warning/10 text-warning border-warning/20',
  },
  down: {
    labelKey: 'connectorStatusDown',
    tone: 'bg-destructive/10 text-destructive-text border-destructive/20',
  },
} as const satisfies Record<DeliveryHealth['status'], { labelKey: string; tone: string }>;

type BadgeJob = Pick<CronJob, 'id' | 'delivery' | 'last_run_at'>;

/**
 * The health of the destination the job delivers to, or `null` while it is not known: not loaded yet, nothing to
 * judge, or the request failed. A new run can change the verdict, so each one reloads it.
 */
function useDestinationHealth(job: BadgeJob): DeliveryHealth | null {
  const [verdict, setVerdict] = useState<{ readFor: string; health: DeliveryHealth | null } | null>(null);
  const destination = `${job.id}\n${job.delivery?.channel ?? ''}\n${job.delivery?.target ?? ''}`;

  // An answer for a destination the user has already left must not replace the one they are looking at. A failed
  // reload leaves what is shown as it is: the request is silent, so there is nothing to tell the user either way.
  useEffect(() => {
    let stale = false;
    getJobDeliveryHealth(job.id)
      .then((health) => {
        if (!stale) {
          setVerdict({ readFor: destination, health });
        }
      })
      .catch(() => undefined);
    return () => {
      stale = true;
    };
  }, [job.id, destination, job.last_run_at]);

  // A verdict is about the destination it was read for, so it is not shown once the job delivers somewhere else; a
  // reload for the same destination keeps showing the current verdict until the new one arrives.
  return verdict?.readFor === destination ? verdict.health : null;
}

const ConnectorHealthBadge = memo(function ConnectorHealthBadge({ job }: { job: BadgeJob }) {
  const t = useTranslations('cron');
  const locale = useLocale();
  const health = useDestinationHealth(job);

  // Without a delivery to judge there is no verdict: a destination never delivered to is not "healthy".
  if (!health) {
    return null;
  }

  const { labelKey, tone } = STATUS_STYLE[health.status];
  // The pill sits apart from the label of its section, so the hidden prefix tells a screen reader what it is the verdict of.
  const verdictText = (
    <>
      <Activity aria-hidden="true" className="h-2.5 w-2.5" />
      <span className="sr-only">{t('connectorHealthStatus')}: </span>
      <span data-testid="connector-health-badge">{t(labelKey)}</span>
    </>
  );

  if (health.status === 'healthy') {
    return <span className={cn(PILL_CLASS, tone)}>{verdictText}</span>;
  }

  const category = health.last_error_category ?? 'unknown';
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className={cn(PILL_CLASS, tone, PILL_BUTTON_CLASS)}>
          {verdictText}
          <ChevronDown
            aria-hidden="true"
            className="h-2.5 w-2.5 transition-transform group-data-[state=open]:rotate-180"
          />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 max-w-[calc(100vw-2rem)] space-y-2 rounded-xl p-3 text-xs">
        <p className="font-semibold">{t(connectorCategoryLabelKey(category))}</p>
        <p className="text-muted-foreground">{t(connectorCategoryHintKey(category))}</p>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
          <span>{t('connectorFailureStreak', { count: health.failure_streak })}</span>
          {health.last_failed_at && (
            <span>{t('connectorLastFailedAt', { time: formatTime(health.last_failed_at, locale) })}</span>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
});

export default ConnectorHealthBadge;
