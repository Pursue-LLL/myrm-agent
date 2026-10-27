'use client';

/**
 * [INPUT]
 * - ./remoteBackupConfig (POS: the offered frequencies and counts)
 * - ./TextField::TextField (POS: labelled field)
 * - @/services/config::BackupSyncConfigValue (POS: the settings being edited)
 *
 * [OUTPUT]
 * - RemoteSchedulePanel: automatic backup switch, how often, how many backups to keep, and the device name
 *
 * [POS]
 * When and how the cloud backups are made. The note under the switch says the schedule runs only while the app is open,
 * so a closed laptop is never mistaken for a broken backup. The number to keep applies to manual backups as well, so it
 * is offered whether or not the schedule is on; its hint says that older backups are deleted from the user's storage.
 */

import { memo, useId } from 'react';
import { useTranslations } from 'next-intl';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { ToggleGroup, ToggleGroupItem } from '@/components/primitives/toggle-group';
import type { BackupSyncConfigValue } from '@/services/config';
import { keepChoices, SYNC_INTERVAL_CHOICES } from './remoteBackupConfig';
import { TextField } from './TextField';

const CHOICE_CLASS =
  'h-8 rounded-full border border-border bg-muted/50 px-3 text-xs data-[state=on]:border-primary/40 data-[state=on]:bg-primary/10 data-[state=on]:text-primary';

interface RemoteSchedulePanelProps {
  config: BackupSyncConfigValue;
  onEdit: (update: (previous: BackupSyncConfigValue) => BackupSyncConfigValue) => void;
}

export const RemoteSchedulePanel = memo(function RemoteSchedulePanel({ config, onEdit }: RemoteSchedulePanelProps) {
  const t = useTranslations('settings.remoteBackup');
  const switchId = useId();
  const set = <K extends keyof BackupSyncConfigValue>(key: K, value: BackupSyncConfigValue[K]) =>
    onEdit((previous) => ({ ...previous, [key]: value }));

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 rounded-xl border border-border/50 bg-muted/30 p-4">
        <div className="min-w-0 space-y-1">
          <Label htmlFor={switchId} className="text-sm font-semibold text-foreground">
            {t('autoSync')}
          </Label>
          <p className="text-xs leading-relaxed text-muted-foreground">{t('autoSyncDescription')}</p>
        </div>
        <Switch
          id={switchId}
          checked={config.autoSync}
          onCheckedChange={(autoSync) => set('autoSync', autoSync)}
          className="mt-0.5 shrink-0"
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {config.autoSync && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-foreground">{t('syncInterval')}</p>
            <ToggleGroup
              type="single"
              size="sm"
              value={String(config.syncInterval)}
              className="flex-wrap justify-start"
              onValueChange={(minutes) => minutes && set('syncInterval', Number(minutes))}
            >
              {SYNC_INTERVAL_CHOICES.map(({ minutes, labelKey }) => (
                <ToggleGroupItem key={minutes} value={String(minutes)} className={CHOICE_CLASS}>
                  {t(`intervalOptions.${labelKey}`)}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
        )}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-foreground">{t('maxBackups')}</p>
          <Select value={String(config.maxBackups)} onValueChange={(count) => set('maxBackups', Number(count))}>
            <SelectTrigger className="w-full text-sm sm:w-44" aria-label={t('maxBackups')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {keepChoices(config.maxBackups).map((count) => (
                <SelectItem key={count} value={String(count)}>
                  {t('keepOption', { count })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs leading-relaxed text-muted-foreground">{t('keepHint')}</p>
        </div>
      </div>

      <TextField
        label={t('deviceName')}
        placeholder={t('deviceNamePlaceholder')}
        hint={t('deviceNameHint')}
        value={config.deviceName}
        onChange={(deviceName) => set('deviceName', deviceName)}
        autoComplete="off"
      />
    </div>
  );
});
