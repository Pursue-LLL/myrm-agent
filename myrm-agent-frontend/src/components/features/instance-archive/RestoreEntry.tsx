'use client';

/**
 * [INPUT]
 * - ./useArchiveStatus: whether this workspace can restore, and a swap waiting for a restart
 * - ./ImportCard: the restore wizard
 * - ./RestartNotice: restart prompt once a restore is queued
 *
 * [OUTPUT]
 * - RestoreEntry: a quiet "restore from a backup" prompt for first-run screens; expands the restore wizard in place
 *
 * [POS]
 * Lets someone who arrives with a backup restore it before setting anything up, instead of
 * configuring what the restore would replace. Renders nothing where backups are unsupported, so
 * the prompt never leads nowhere. The wizard expands inline and stays mounted while collapsed:
 * the onboarding overlay owns the top layer and an upload in progress must survive a toggle.
 */

import { memo, useCallback, useId, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { ImportCard } from './ImportCard';
import { RestartNotice } from './RestartNotice';
import { useArchiveStatus } from './useArchiveStatus';

export const RestoreEntry = memo(function RestoreEntry() {
  const t = useTranslations('instanceArchive.entry');
  const { status, reload } = useArchiveStatus();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const handleQueued = useCallback(() => void reload(), [reload]);

  if (!status?.supported) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col items-center justify-center gap-0.5 text-center sm:flex-row sm:gap-2">
        <span className="text-sm text-muted-foreground">{t('prompt')}</span>
        <Button
          variant="link"
          size="sm"
          className="h-auto px-1 py-0.5"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((current) => !current)}
        >
          {open ? t('close') : t('open')}
        </Button>
      </div>
      {status.pending_operation && <RestartNotice mode={status.restart_mode} />}
      <div id={panelId} hidden={!open}>
        <ImportCard onQueued={handleQueued} />
      </div>
    </div>
  );
});
