'use client';

import { useTranslations } from 'next-intl';
import { Cloud, Laptop, MoonStar } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useDeployMode } from '@/hooks/shared/useDeployMode';

/**
 * Deploy-mode aware notice for recurring cron creation flows.
 *
 * - local / tauri: reminds that jobs run on the user's own machine (host online,
 *   service running; sleep is auto-inhibited only while a job executes).
 * - sandbox (cloud-hosted): surfaces the 24/7 cloud execution benefit.
 *
 * Stays hidden while the mode is still loading so it never flashes a wrong hint.
 */
export default function CronDeployModeNotice() {
  const t = useTranslations('cron');
  const { isLocal, isSandbox, isLoading } = useDeployMode();

  if (isLoading) {return null;}

  const isCloud = isSandbox && !isLocal;

  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-lg border px-3 py-2 text-xs',
        isCloud
          ? 'border-sky-500/25 bg-sky-500/5 text-sky-700 dark:text-sky-300'
          : 'border-amber-500/25 bg-amber-500/5 text-amber-700 dark:text-amber-300',
      )}
    >
      {isCloud ? (
        <Cloud className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      ) : (
        <Laptop className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      )}
      <div className="min-w-0 space-y-0.5">
        {isCloud ? (
          <p>{t('deployCloudNotice')}</p>
        ) : (
          <>
            <p>{t('deployLocalNotice')}</p>
            <p className="flex items-center gap-1 text-muted-foreground">
              <MoonStar className="h-3 w-3 shrink-0" />
              {t('deployLocalSleepHint')}
            </p>
          </>
        )}
      </div>
    </div>
  );
}