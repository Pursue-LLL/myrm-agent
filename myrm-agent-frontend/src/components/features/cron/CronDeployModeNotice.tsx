'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Cloud, Laptop, MoonStar } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { apiRequest } from '@/lib/api';

export type DeployMode = 'local' | 'tauri' | 'sandbox';

/**
 * Deploy-mode aware notice for recurring cron creation flows.
 *
 * - local / tauri: reminds that jobs run on the user's own machine (host online,
 *   service running; sleep is auto-inhibited only while a job executes).
 * - sandbox (cloud-hosted): surfaces the 24/7 cloud execution benefit.
 *
 * The notice stays hidden until the mode is known (and on network failure) so it
 * never guesses a misleading mode.
 */
export default function CronDeployModeNotice() {
  const t = useTranslations('cron');
  const [mode, setMode] = useState<DeployMode | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiRequest<{ deploy_mode: string }>('/health/info')
      .then((info) => {
        if (!cancelled) {
          const value = info.deploy_mode as DeployMode;
          setMode(value === 'sandbox' || value === 'local' || value === 'tauri' ? value : 'local');
        }
      })
      .catch(() => {
        if (!cancelled) {setMode(null);}
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!mode) {return null;}

  const isCloud = mode === 'sandbox';

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