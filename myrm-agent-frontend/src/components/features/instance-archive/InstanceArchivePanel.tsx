'use client';

/**
 * [INPUT]
 * - ./useArchiveStatus::useArchiveStatus (POS: single answer to what this workspace can do, shared by the backup cards and restart notices)
 * - ./ExportCard::ExportCard (POS: export half of the instance backup panel)
 * - ./ImportCard::ImportCard (POS: import half of the instance backup panel; nothing is replaced before the user confirms)
 * - ./auto-backup/AutoBackupCard::AutoBackupCard (POS: scheduled backup card; off by default, keeps showing the copies made and the folder chosen once turned off)
 * - ./RollbackStrip::RollbackStrip (POS: safety net of the instance backup panel; queues the swap)
 * - ./RestartNotice::RestartNotice (POS: shown whenever a restore, import or rollback is queued)
 *
 * [OUTPUT]
 * - InstanceArchivePanel: whole-workspace backup (manual and scheduled), restore and undo
 *
 * [POS]
 * Data-sovereignty section of the personal workbench page. Hidden when the endpoints are
 * not reachable for this identity; shows an honest note when the layout is unsupported.
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldCheck } from '@phosphor-icons/react';
import { AutoBackupCard } from './auto-backup/AutoBackupCard';
import { ExportCard } from './ExportCard';
import { ImportCard } from './ImportCard';
import { RestartNotice } from './RestartNotice';
import { RollbackStrip } from './RollbackStrip';
import { useArchiveStatus } from './useArchiveStatus';

const InstanceArchivePanel = memo(function InstanceArchivePanel() {
  const t = useTranslations('instanceArchive');
  const { status, reload } = useArchiveStatus();

  if (!status) {
    return null;
  }

  return (
    <section
      id="instance-archive"
      className="space-y-5 rounded-3xl border border-border/60 bg-gradient-to-br from-primary/5 via-background to-secondary/20 p-6 sm:p-8"
    >
      <div className="space-y-1">
        <h2 className="flex items-center gap-2 text-lg font-bold text-foreground">
          <ShieldCheck className="h-5 w-5 text-primary" weight="duotone" />
          {t('title')}
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">{t('subtitle')}</p>
      </div>

      {!status.supported ? (
        <p className="rounded-2xl border border-border/50 bg-muted/20 p-4 text-sm leading-relaxed text-muted-foreground">
          {t('unsupported')}
        </p>
      ) : (
        <>
          {status.pending_operation && <RestartNotice mode={status.restart_mode} />}
          <div className="grid gap-4 lg:grid-cols-2">
            <ExportCard canProtectSecrets={status.can_protect_secrets} />
            <ImportCard onQueued={() => void reload()} />
          </div>
          <AutoBackupCard />
          {status.rollback_available && !status.pending_operation && <RollbackStrip onQueued={() => void reload()} />}
        </>
      )}
    </section>
  );
});

export default InstanceArchivePanel;
