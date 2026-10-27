'use client';

/**
 * [INPUT]
 * - ./remoteBackupApi::AutoSyncStatus, errorCodeKey (POS: how the scheduled backup is doing, and its failure reasons)
 * - @/lib/instance-archive/format::formatBackupDate (POS: locale-aware date label for backup files)
 *
 * [OUTPUT]
 * - RemoteBackupStatus: the last backup that completed, and why the scheduled backup is failing when it is
 *
 * [POS]
 * Honest status line of the cloud sync card. "Last backup" is always the last one that actually completed, so a failing
 * schedule can never look healthy; a failure is reported by its localized reason, never by the server's wording. Failures
 * belong to the schedule, so they are shown only while the schedule is on.
 */

import { memo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { CheckCircle, Clock, WarningCircle } from '@phosphor-icons/react';
import { formatBackupDate } from '@/lib/instance-archive/format';
import { errorCodeKey, type AutoSyncStatus } from './remoteBackupApi';

interface RemoteBackupStatusProps {
  status: AutoSyncStatus | null;
  autoSync: boolean;
}

export const RemoteBackupStatus = memo(function RemoteBackupStatus({ status, autoSync }: RemoteBackupStatusProps) {
  const t = useTranslations('settings.remoteBackup');
  const locale = useLocale();

  if (!status) {
    return null;
  }
  const failing = autoSync && status.consecutive_failures > 0 && status.last_error_code !== null;

  return (
    <div className="space-y-2">
      {failing && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300"
        >
          <WarningCircle className="mt-0.5 h-4 w-4 shrink-0" weight="fill" />
          <div className="space-y-0.5">
            <p className="font-semibold">{t('statusFailing')}</p>
            <p className="leading-relaxed">{t(`errorCodes.${errorCodeKey(status.last_error_code)}`)}</p>
          </div>
        </div>
      )}
      {status.last_success_at ? (
        <p className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <CheckCircle className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" weight="fill" />
          {t('statusLastBackup', { date: formatBackupDate(status.last_success_at, locale) })}
        </p>
      ) : (
        autoSync && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            {t('statusNone')}
          </p>
        )
      )}
    </div>
  );
});
