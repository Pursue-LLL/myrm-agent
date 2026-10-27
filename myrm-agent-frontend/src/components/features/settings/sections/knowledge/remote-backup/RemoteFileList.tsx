'use client';

/**
 * [INPUT]
 * - ./useRemoteBackup::ListState (POS: whether the cloud storage has been read, is being read, or could not be read)
 * - ./remoteBackupApi::RemoteBackupFile (POS: one backup in the cloud storage)
 * - ./backupFileName::deviceOf (POS: device a backup was made on)
 * - @/lib/instance-archive/format::formatBytes, formatBackupDate (POS: size and date labels for backup files)
 *
 * [OUTPUT]
 * - RemoteFileList: the backups in the cloud storage, newest first, each with restore and delete behind a confirmation
 *
 * [POS]
 * Second card of the cloud sync page. A storage that could not be read says so and offers a retry: it is never shown as
 * having no backups. Restoring merges a backup into the current memories and removes nothing, and deleting cannot be
 * undone; each dialog says so before it asks.
 */

import { memo, type ReactNode } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { ArrowsClockwise, CircleNotch, DownloadSimple, Trash, WarningCircle } from '@phosphor-icons/react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/primitives/alert-dialog';
import { Button } from '@/components/primitives/button';
import { formatBackupDate, formatBytes } from '@/lib/instance-archive/format';
import { deviceOf } from './backupFileName';
import type { RemoteBackupFile } from './remoteBackupApi';
import type { ListState } from './useRemoteBackup';

interface RemoteFileListProps {
  files: RemoteBackupFile[];
  state: ListState;
  onRefresh: () => void;
  onRestore: (fileName: string) => void;
  onDelete: (fileName: string) => void;
}

interface ConfirmActionProps {
  trigger: ReactNode;
  title: string;
  description: string;
  fileName: string;
  confirmLabel: string;
  destructive?: boolean;
  onConfirm: () => void;
}

function ConfirmAction({
  trigger,
  title,
  description,
  fileName,
  confirmLabel,
  destructive = false,
  onConfirm,
}: ConfirmActionProps) {
  const t = useTranslations('common');

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
          <p className="break-all rounded-lg bg-muted/50 px-3 py-2 font-mono text-xs text-muted-foreground">
            {fileName}
          </p>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction
            className={destructive ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' : undefined}
            onClick={onConfirm}
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export const RemoteFileList = memo(function RemoteFileList({
  files,
  state,
  onRefresh,
  onRestore,
  onDelete,
}: RemoteFileListProps) {
  const t = useTranslations('settings.remoteBackup');
  const locale = useLocale();
  const loading = state === 'loading';

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-background/60 p-5 backdrop-blur-xl dark:bg-card/40 sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-bold text-foreground">{t('remoteFiles')}</h3>
        <Button
          variant="outline"
          size="sm"
          className="rounded-xl"
          disabled={loading}
          onClick={onRefresh}
          aria-label={t('refreshList')}
        >
          <ArrowsClockwise className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {state === 'error' && (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300 sm:flex-row sm:items-center sm:justify-between"
        >
          <span className="flex items-start gap-2">
            <WarningCircle className="mt-0.5 h-4 w-4 shrink-0" weight="fill" />
            <span className="leading-relaxed">{t('listError')}</span>
          </span>
          <Button size="sm" variant="outline" className="self-start rounded-xl sm:self-auto" onClick={onRefresh}>
            {t('retry')}
          </Button>
        </div>
      )}

      {state === 'loading' && files.length === 0 && (
        <output className="flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground">
          <CircleNotch className="h-4 w-4 animate-spin" />
          {t('loadingFiles')}
        </output>
      )}

      {(state === 'idle' || (state === 'ready' && files.length === 0)) && (
        <p className="py-6 text-center text-xs text-muted-foreground">
          {state === 'idle' ? t('listIdle') : t('noRemoteFiles')}
        </p>
      )}

      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((file) => {
            const device = deviceOf(file.file_name);
            return (
              <li
                key={file.file_name}
                title={file.file_name}
                className="flex items-center justify-between gap-3 rounded-xl border border-border/50 bg-muted/30 p-3 transition-colors hover:bg-accent/40"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">
                    {formatBackupDate(file.modified_time, locale) || file.file_name}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {[formatBytes(file.size_bytes), device].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <ConfirmAction
                    trigger={
                      <Button variant="outline" size="sm" className="rounded-xl" aria-label={t('restoreFromCloud')}>
                        <DownloadSimple className="h-4 w-4" />
                      </Button>
                    }
                    title={t('restoreFromCloud')}
                    description={t('restoreDescription')}
                    fileName={file.file_name}
                    confirmLabel={t('restoreFromCloud')}
                    onConfirm={() => onRestore(file.file_name)}
                  />
                  <ConfirmAction
                    trigger={
                      <Button variant="ghost" size="sm" className="rounded-xl" aria-label={t('deleteFromCloud')}>
                        <Trash className="h-4 w-4 text-destructive" />
                      </Button>
                    }
                    title={t('deleteFromCloud')}
                    description={t('deleteDescription')}
                    fileName={file.file_name}
                    confirmLabel={t('deleteFromCloud')}
                    destructive
                    onConfirm={() => onDelete(file.file_name)}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
});
