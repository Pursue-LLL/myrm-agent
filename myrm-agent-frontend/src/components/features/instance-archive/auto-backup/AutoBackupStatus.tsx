'use client';

/**
 * [INPUT]
 * - @/services/instanceAutoBackup::AutoBackup (POS: schedule + last outcome)
 * - @/lib/instance-archive/format::formatBytes, formatBackupDate (POS: size and date labels for backup files)
 * - ../ArchiveErrorNotice::ArchiveErrorNotice (POS: localized failure surface that never shows server wording)
 *
 * [OUTPUT]
 * - AutoBackupStatus: what the schedule last did (running, failing, late, completed, folder unreachable, none yet)
 *
 * [POS]
 * Honest status line of the automatic backup card. "Last backup" is always the last backup that
 * actually completed, so a failing schedule can never look healthy. A folder that cannot be reached
 * is reported as such, never as "No backup yet": its backups are unknown, not gone.
 */

import { memo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { CheckCircle, CircleNotch, Clock, WarningCircle } from '@phosphor-icons/react';
import { formatBackupDate, formatBytes } from '@/lib/instance-archive/format';
import type { AutoBackup } from '@/services/instanceAutoBackup';
import { ArchiveErrorNotice } from '../ArchiveErrorNotice';

interface AutoBackupStatusProps {
  backup: AutoBackup;
}

export const AutoBackupStatus = memo(function AutoBackupStatus({ backup }: AutoBackupStatusProps) {
  const t = useTranslations('instanceArchive.auto');
  const locale = useLocale();
  const failing = backup.consecutive_failures > 0 && backup.last_error_code !== null;

  return (
    <div className="space-y-2">
      {backup.running && (
        <output className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <CircleNotch className="h-3.5 w-3.5 animate-spin" />
          {t('running')}
        </output>
      )}
      {!backup.running && failing && backup.last_error_code && <ArchiveErrorNotice code={backup.last_error_code} />}
      {!backup.running && !failing && backup.overdue && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300"
        >
          <WarningCircle className="mt-0.5 h-4 w-4 shrink-0" weight="fill" />
          <span className="leading-relaxed">{t('overdue')}</span>
        </div>
      )}
      {backup.last_success_at ? (
        <p className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <CheckCircle className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" weight="fill" />
          {t('lastBackup', {
            date: formatBackupDate(backup.last_success_at, locale),
            size: formatBytes(backup.last_success_size ?? 0),
          })}
        </p>
      ) : !backup.folder_available ? (
        <p className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-300">
          <WarningCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" weight="fill" />
          <span className="leading-relaxed">{t('folderUnavailable')}</span>
        </p>
      ) : (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock className="h-3.5 w-3.5" />
          {t('noBackupYet')}
        </p>
      )}
    </div>
  );
});
