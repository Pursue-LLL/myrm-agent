'use client';

/**
 * [INPUT]
 * - @/lib/desktopBridge::desktopBridge (POS: native folder picker on the desktop shell)
 *
 * [OUTPUT]
 * - AutoBackupLocation: where automatic backups are saved (default folder, or one the user picks)
 *
 * [POS]
 * Folder row of the automatic backup card. On the desktop app the folder is chosen with the native
 * picker; in a browser on the same machine the path is typed. Either way the server decides whether
 * the folder is usable, and the card shows its localized reason.
 */

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowCounterClockwise, FolderOpen } from '@phosphor-icons/react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { desktopBridge } from '@/lib/desktopBridge';

interface AutoBackupLocationProps {
  directory: string;
  isDefault: boolean;
  disabled: boolean;
  /** Null selects the default folder. Resolves true when the server accepted it. */
  onChange: (directory: string | null) => Promise<boolean>;
}

export const AutoBackupLocation = memo(function AutoBackupLocation({
  directory,
  isDefault,
  disabled,
  onChange,
}: AutoBackupLocationProps) {
  const t = useTranslations('instanceArchive.auto');
  const [draft, setDraft] = useState(directory);

  useEffect(() => {
    setDraft(directory);
  }, [directory]);

  const canBrowse = desktopBridge.isDesktop();
  const changed = draft.trim() !== directory;

  const browse = async () => {
    const picked = await desktopBridge.openDirectoryPicker({ title: t('browseTitle'), defaultPath: directory });
    if (picked) {
      setDraft(picked);
      await onChange(picked);
    }
  };

  return (
    <div className="space-y-2">
      <label htmlFor="auto-backup-folder" className="text-xs font-semibold text-foreground">
        {t('folder')}
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          id="auto-backup-folder"
          value={draft}
          disabled={disabled}
          spellCheck={false}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && changed && draft.trim()) {
              void onChange(draft.trim());
            }
          }}
          className="h-9 min-w-0 flex-1 text-xs"
        />
        <div className="flex shrink-0 flex-wrap gap-2">
          {canBrowse && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 rounded-xl"
              disabled={disabled}
              onClick={() => void browse()}
            >
              <FolderOpen className="h-3.5 w-3.5" weight="bold" />
              {t('browse')}
            </Button>
          )}
          {changed && (
            <Button
              size="sm"
              className="rounded-xl"
              disabled={disabled || !draft.trim()}
              onClick={() => void onChange(draft.trim())}
            >
              {t('apply')}
            </Button>
          )}
          {!isDefault && !changed && (
            <Button
              size="sm"
              variant="ghost"
              className="gap-1.5 rounded-xl text-muted-foreground"
              disabled={disabled}
              onClick={() => void onChange(null)}
            >
              <ArrowCounterClockwise className="h-3.5 w-3.5" weight="bold" />
              {t('useDefault')}
            </Button>
          )}
        </div>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        {isDefault ? t('defaultFolderHint') : t('folderHint')}
      </p>
    </div>
  );
});
