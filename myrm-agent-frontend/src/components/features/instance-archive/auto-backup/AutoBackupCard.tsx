'use client';

/**
 * [INPUT]
 * - ./useAutoBackup::useAutoBackup (POS: schedule state machine with live progress)
 * - ./AutoBackupStatus::AutoBackupStatus (POS: honest status line, last completed backup only)
 * - ./AutoBackupLocation::AutoBackupLocation (POS: backup folder row, native picker on the desktop app)
 * - ./AutoBackupList::AutoBackupList (POS: read-only list of the copies kept)
 * - ../ArchiveErrorNotice::ArchiveErrorNotice (POS: localized failure surface that never shows server wording)
 *
 * [OUTPUT]
 * - AutoBackupCard: switch automatic whole-app backups on or off, pick how often, how many copies and where
 *
 * [POS]
 * Card of the backup panel below export and restore. Off by default; turning it on makes the first backup
 * right away, turning it off keeps showing the copies already made and the folder the user chose.
 * Not rendered where the server does not offer scheduled backups (cloud workspaces). The copy states
 * what the file does not protect: it is unencrypted, leaves out logins and keys, and a copy on this
 * computer does not survive losing it.
 */

import { memo, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { CalendarCheck, CircleNotch, Lightning } from '@phosphor-icons/react';
import { Button } from '@/components/primitives/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { ToggleGroup, ToggleGroupItem } from '@/components/primitives/toggle-group';
import type { AutoBackup, AutoBackupSettings, BackupFrequency } from '@/services/instanceAutoBackup';
import { ArchiveErrorNotice } from '../ArchiveErrorNotice';
import { AutoBackupList } from './AutoBackupList';
import { AutoBackupLocation } from './AutoBackupLocation';
import { AutoBackupStatus } from './AutoBackupStatus';
import { useAutoBackup } from './useAutoBackup';

const KEEP_CHOICES = [1, 2, 3, 5, 7, 10];
const FREQUENCIES: readonly BackupFrequency[] = ['daily', 'weekly'];
const CHOICE_CLASS =
  'h-8 gap-1.5 rounded-full border border-border bg-muted/50 px-3 text-xs data-[state=on]:border-primary/40 data-[state=on]:bg-primary/10 data-[state=on]:text-primary';

const settingsOf = (backup: AutoBackup): AutoBackupSettings => ({
  enabled: backup.enabled,
  frequency: backup.frequency,
  keep: backup.keep,
  directory: backup.default_directory ? null : backup.directory,
});

export const AutoBackupCard = memo(function AutoBackupCard() {
  const t = useTranslations('instanceArchive.auto');
  const { data, errorCode, busy, update, runNow } = useAutoBackup();

  const keepChoices = useMemo(
    () => (data ? [...new Set([...KEEP_CHOICES, data.keep])].sort((a, b) => a - b) : KEEP_CHOICES),
    [data],
  );

  if (!data?.supported) {
    return null;
  }

  const save = (changes: Partial<AutoBackupSettings>) => update({ ...settingsOf(data), ...changes });
  const locked = busy || data.running;
  // Past the bare switch once the user has a stake in it: it is on, copies were made, or a folder was chosen.
  // A chosen folder counts even when it cannot be read and so lists no copies: its row is the only way to change it.
  const showDetails = data.enabled || data.backups.length > 0 || !data.default_directory;

  return (
    <div
      id="auto-backup"
      className="flex flex-col gap-5 rounded-2xl border border-border/60 bg-background/60 p-5 backdrop-blur-xl dark:bg-card/40 sm:p-6"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
          <CalendarCheck className="h-5 w-5" weight="duotone" />
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="text-sm font-bold text-foreground">{t('title')}</h3>
          <p className="text-xs leading-relaxed text-muted-foreground">{t('description')}</p>
        </div>
        <Switch
          checked={data.enabled}
          disabled={busy}
          onCheckedChange={(enabled) => void save({ enabled })}
          aria-label={t('enable')}
          className="mt-1 shrink-0"
        />
      </div>

      {errorCode && <ArchiveErrorNotice code={errorCode} />}

      {showDetails && (
        <div className="space-y-5">
          {data.enabled && <AutoBackupStatus backup={data} />}

          {data.enabled && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <p className="text-xs font-semibold text-foreground">{t('frequency')}</p>
                <ToggleGroup
                  type="single"
                  size="sm"
                  value={data.frequency}
                  disabled={busy}
                  className="justify-start"
                  onValueChange={(value) => value && void save({ frequency: value as BackupFrequency })}
                >
                  {FREQUENCIES.map((frequency) => (
                    <ToggleGroupItem key={frequency} value={frequency} className={CHOICE_CLASS}>
                      {t(`frequencyOptions.${frequency}`)}
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
              </div>
              <div className="space-y-2">
                <p className="text-xs font-semibold text-foreground">{t('keep')}</p>
                <Select
                  value={String(data.keep)}
                  disabled={busy}
                  onValueChange={(value) => void save({ keep: Number(value) })}
                >
                  <SelectTrigger className="h-9 w-full text-xs sm:w-44" aria-label={t('keep')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {keepChoices.map((count) => (
                      <SelectItem key={count} value={String(count)}>
                        {t('keepOption', { count })}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <AutoBackupLocation
            directory={data.directory}
            isDefault={data.default_directory}
            disabled={busy}
            onChange={(directory) => save({ directory })}
          />

          <AutoBackupList backups={data.backups} />

          {data.enabled && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 rounded-xl"
              disabled={locked}
              onClick={() => void runNow()}
            >
              {data.running ? (
                <CircleNotch className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Lightning className="h-3.5 w-3.5" weight="bold" />
              )}
              {data.running ? t('running') : t('backupNow')}
            </Button>
          )}
        </div>
      )}

      <ul className="list-inside list-disc space-y-1 text-xs leading-relaxed text-muted-foreground">
        <li>{t('notePlain')}</li>
        <li>{t('noteScope')}</li>
      </ul>
    </div>
  );
});
