/**
 * [INPUT]
 * - `@/lib/cron/schedulerHealth` (`subscribeSchedulerHealth`)
 * - `next-intl` (`cron.schedulerBanner`, `common.close`)
 *
 * [OUTPUT]
 * - `CronSchedulerHealthBanner`: AppLayout top alert when scheduler is degraded/stopped
 * - `isCronSchedulerBannerDismissed` / `dismissCronSchedulerBanner`: session dismiss SSOT
 *
 * [POS]
 * Surfaces scheduler engine health outside the Cron settings page (Chat-only users).
 */
'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { AlertTriangle, X } from 'lucide-react';
import {
  subscribeSchedulerHealth,
  type SchedulerHealth,
} from '@/lib/cron/schedulerHealth';
import { cn } from '@/lib/utils/classnameUtils';

const DISMISS_STORAGE_KEY = 'myrm_cron_scheduler_banner_dismissed_status';

type DismissedSchedulerStatus = 'yellow' | 'red';

export function getCronSchedulerBannerDismissedStatus(): DismissedSchedulerStatus | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const value = sessionStorage.getItem(DISMISS_STORAGE_KEY);
    return value === 'yellow' || value === 'red' ? value : null;
  } catch {
    return null;
  }
}

export function dismissCronSchedulerBanner(status: DismissedSchedulerStatus): void {
  try {
    sessionStorage.setItem(DISMISS_STORAGE_KEY, status);
  } catch {
    // sessionStorage unavailable
  }
}

function shouldHideSchedulerBanner(
  health: SchedulerHealth,
  dismissedStatus: DismissedSchedulerStatus | null,
): boolean {
  if (!dismissedStatus) {
    return false;
  }
  if (health.status === 'red' && dismissedStatus === 'yellow') {
    return false;
  }
  return true;
}

interface CronSchedulerHealthBannerProps {
  className?: string;
}

export default function CronSchedulerHealthBanner({ className }: CronSchedulerHealthBannerProps) {
  const t = useTranslations('cron.schedulerBanner');
  const tCommon = useTranslations('common');
  const pathname = usePathname();
  const [health, setHealth] = useState<SchedulerHealth | null>(null);
  const [dismissedStatus, setDismissedStatus] = useState<DismissedSchedulerStatus | null>(null);

  useEffect(() => {
    setDismissedStatus(getCronSchedulerBannerDismissedStatus());
    return subscribeSchedulerHealth(setHealth);
  }, []);

  const handleDismiss = useCallback(() => {
    if (!health || health.status === 'green') {
      return;
    }
    const status: DismissedSchedulerStatus = health.status === 'red' ? 'red' : 'yellow';
    dismissCronSchedulerBanner(status);
    setDismissedStatus(status);
  }, [health]);

  if (!health || health.status === 'green') {
    return null;
  }

  if (shouldHideSchedulerBanner(health, dismissedStatus)) {
    return null;
  }

  if (pathname?.startsWith('/settings/cron')) {
    return null;
  }

  const isRed = health.status === 'red';

  return (
    <div
      data-testid="cron-scheduler-health-banner"
      role="alert"
      className={cn(
        'mb-4 flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-[13px] leading-relaxed',
        isRed
          ? 'border-destructive/30 bg-destructive/10 text-destructive/90 dark:border-destructive/40 dark:bg-destructive/15'
          : 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:border-amber-400/30 dark:bg-amber-500/15 dark:text-amber-200',
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium">{t(isRed ? 'stoppedTitle' : 'degradedTitle')}</p>
        <p className={cn(isRed ? 'text-destructive/80' : 'text-amber-700/90 dark:text-amber-200/80')}>
          {t(isRed ? 'stoppedDescription' : 'degradedDescription')}
        </p>
        <Link
          href="/settings/cron"
          className="mt-1 inline-block text-xs font-medium underline underline-offset-2 hover:no-underline"
        >
          {t('viewCron')}
        </Link>
      </div>
      <button
        type="button"
        onClick={handleDismiss}
        className={cn(
          'flex-shrink-0 rounded p-1 transition-colors',
          isRed
            ? 'text-destructive/70 hover:bg-destructive/10 hover:text-destructive'
            : 'text-amber-700/70 hover:bg-amber-500/10 hover:text-amber-800 dark:text-amber-200/70',
        )}
        aria-label={tCommon('close')}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
