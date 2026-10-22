'use client';

/**
 * [INPUT]
 * - @/services/instanceAutoBackup::StoredBackup (POS: backups currently kept)
 * - @/lib/instance-archive/format::formatBytes, formatBackupDate (POS: size and date labels for backup files)
 *
 * [OUTPUT]
 * - AutoBackupList: the copies currently kept in the folder, newest first
 *
 * [POS]
 * Read-only list in the automatic backup card. Restoring is deliberately not offered here: a
 * copy is restored through the regular restore card, which checks it and shows what will change.
 */

import { memo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { FileZip } from '@phosphor-icons/react';
import { formatBackupDate, formatBytes } from '@/lib/instance-archive/format';
import type { StoredBackup } from '@/services/instanceAutoBackup';

interface AutoBackupListProps {
  backups: StoredBackup[];
}

export const AutoBackupList = memo(function AutoBackupList({ backups }: AutoBackupListProps) {
  const t = useTranslations('instanceArchive.auto');
  const locale = useLocale();

  if (backups.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-foreground">{t('savedCopies', { count: backups.length })}</p>
      <ul className="divide-y divide-border/50 overflow-hidden rounded-xl border border-border/50 bg-muted/20">
        {backups.map((backup) => (
          <li key={backup.name} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
            <span className="flex min-w-0 items-center gap-2 text-foreground">
              <FileZip className="h-4 w-4 shrink-0 text-muted-foreground" weight="duotone" />
              <span className="truncate">{formatBackupDate(backup.created_at, locale)}</span>
            </span>
            <span className="shrink-0 text-muted-foreground">{formatBytes(backup.size_bytes)}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs leading-relaxed text-muted-foreground">{t('restoreHint')}</p>
    </div>
  );
});
