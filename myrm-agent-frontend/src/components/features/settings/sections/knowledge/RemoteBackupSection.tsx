'use client';

/**
 * [INPUT]
 * - ./remote-backup/useRemoteBackup::useRemoteBackup (POS: settings being edited, cloud backups listed, schedule status, actions)
 * - ./remote-backup/RemoteBackupStatus::RemoteBackupStatus (POS: last completed backup and why the schedule is failing)
 * - ./remote-backup/RemoteConnectionFields::RemoteConnectionFields (POS: provider and connection details)
 * - ./remote-backup/RemoteSchedulePanel::RemoteSchedulePanel (POS: automatic backup, frequency, copies kept, device name)
 * - ./remote-backup/RemoteFileList::RemoteFileList (POS: backups in the cloud storage with restore and delete)
 *
 * [OUTPUT]
 * - RemoteBackupSection (default): the Cloud Sync page of the Memory Center
 *
 * [POS]
 * Backs up the memories of the default agent and the shared ones to the user's own WebDAV or S3-compatible storage.
 * Off by default. The notes under the card say what the file does not protect: it is unencrypted, and it covers memories
 * only (chats, skills and settings belong to the whole-app backup).
 */

import { useTranslations } from 'next-intl';
import { CheckCircle, CircleNotch, CloudArrowUp, FloppyDisk, PlugsConnected, XCircle } from '@phosphor-icons/react';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import { RemoteBackupStatus } from './remote-backup/RemoteBackupStatus';
import { RemoteConnectionFields } from './remote-backup/RemoteConnectionFields';
import { RemoteFileList } from './remote-backup/RemoteFileList';
import { RemoteSchedulePanel } from './remote-backup/RemoteSchedulePanel';
import { useRemoteBackup } from './remote-backup/useRemoteBackup';

export default function RemoteBackupSection() {
  const t = useTranslations('settings.remoteBackup');
  const remote = useRemoteBackup();
  const { config, edit, connection, testing, backingUp } = remote;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-5 rounded-2xl border border-border/60 bg-background/60 p-5 backdrop-blur-xl dark:bg-card/40 sm:p-6">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
            <CloudArrowUp className="h-5 w-5" weight="duotone" />
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            <h3 className="text-sm font-bold text-foreground">{t('title')}</h3>
            <p className="text-xs leading-relaxed text-muted-foreground">{t('description')}</p>
          </div>
          <Switch
            checked={config.enabled}
            onCheckedChange={(enabled) => edit((previous) => ({ ...previous, enabled }))}
            aria-label={t('enabled')}
            className="mt-1 shrink-0"
          />
        </div>

        {config.enabled && (
          <div className="space-y-5">
            <RemoteBackupStatus status={remote.status} autoSync={config.autoSync} />
            <RemoteConnectionFields config={config} onEdit={edit} />
            <RemoteSchedulePanel config={config} onEdit={edit} />

            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                className="gap-1.5 rounded-xl"
                disabled={testing}
                onClick={() => void remote.testConnection()}
              >
                {testing ? (
                  <CircleNotch className="h-4 w-4 animate-spin" />
                ) : connection === 'success' ? (
                  <CheckCircle className="h-4 w-4 text-emerald-600 dark:text-emerald-400" weight="fill" />
                ) : connection === 'failed' ? (
                  <XCircle className="h-4 w-4 text-destructive" weight="fill" />
                ) : (
                  <PlugsConnected className="h-4 w-4" />
                )}
                {testing ? t('testing') : t('testConnection')}
              </Button>
              <Button className="gap-1.5 rounded-xl" onClick={remote.save}>
                <FloppyDisk className="h-4 w-4" />
                {t('save')}
              </Button>
              <Button
                variant="secondary"
                className="gap-1.5 rounded-xl"
                disabled={backingUp}
                onClick={() => void remote.backupNow()}
              >
                {backingUp ? <CircleNotch className="h-4 w-4 animate-spin" /> : <CloudArrowUp className="h-4 w-4" />}
                {backingUp ? t('backingUp') : t('triggerBackup')}
              </Button>
            </div>
          </div>
        )}

        <ul className="list-inside list-disc space-y-1 text-xs leading-relaxed text-muted-foreground">
          <li>{t('notePlain')}</li>
          <li>{t('noteScope')}</li>
        </ul>
      </div>

      {config.enabled && (
        <RemoteFileList
          files={remote.files}
          state={remote.listState}
          onRefresh={remote.reload}
          onRestore={(fileName) => void remote.restore(fileName)}
          onDelete={(fileName) => void remote.remove(fileName)}
        />
      )}
    </div>
  );
}
