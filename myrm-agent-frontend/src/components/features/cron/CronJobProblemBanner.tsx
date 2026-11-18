'use client';

/**
 * [INPUT]
 * ./cron-utils::pauseReasonLabelKey (POS: Cron label keys and pure helpers)
 * @/services/cron::CronJob (POS: Frontend Cron API client and CronJob type definitions)
 *
 * [OUTPUT]
 * CronJobProblemBanner: Why a job stopped or failed, in one notice.
 *
 * [POS]
 * Notice at the top of a job's run history. A job the scheduler paused by itself says why in plain words; the raw
 * last error follows it, scrolling inside a fixed height so a long one never pushes the job's controls away, except
 * after a loop-guard break, whose internal error text is not for the user.
 */

import { useTranslations } from 'next-intl';
import type { CronJob } from '@/services/cron';
import { pauseReasonLabelKey } from './cron-utils';

interface CronJobProblemBannerProps {
  job: Pick<CronJob, 'last_error' | 'paused_reason'>;
}

export default function CronJobProblemBanner({ job }: CronJobProblemBannerProps) {
  const t = useTranslations('cron');
  const { paused_reason: reason, last_error: lastError } = job;
  const showLastError = Boolean(lastError) && reason !== 'circuit_break';

  if (!reason && !showLastError) {
    return null;
  }

  return (
    <div className="space-y-1 rounded-2xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive-text">
      {reason && <p className="font-medium">{t(pauseReasonLabelKey(reason))}</p>}
      {showLastError && (
        <p className="max-h-40 overflow-y-auto break-words">
          {t('lastError')}: {lastError}
        </p>
      )}
    </div>
  );
}
