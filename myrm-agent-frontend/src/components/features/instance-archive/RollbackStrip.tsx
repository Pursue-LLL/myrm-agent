'use client';

/**
 * [INPUT]
 * - @/services/instanceArchive: instanceArchiveService.queueRollback
 *
 * [OUTPUT]
 * - RollbackStrip: undo the most recent restore (the data it replaced is kept aside)
 *
 * [POS]
 * Safety net of the instance backup panel; queues the swap, after which the panel shows
 * the restart notice.
 */

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowCounterClockwise, CircleNotch } from '@phosphor-icons/react';
import { Button } from '@/components/primitives/button';
import { archiveErrorCode, instanceArchiveService } from '@/services/instanceArchive';
import { ArchiveErrorNotice } from './ArchiveErrorNotice';

interface RollbackStripProps {
  onQueued: () => void;
}

export const RollbackStrip = memo(function RollbackStrip({ onQueued }: RollbackStripProps) {
  const t = useTranslations('instanceArchive.rollback');
  const [busy, setBusy] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const rollback = async () => {
    setBusy(true);
    setErrorCode(null);
    try {
      await instanceArchiveService.queueRollback();
      onQueued();
    } catch (error) {
      setErrorCode(archiveErrorCode(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-background/60 p-4 dark:bg-card/40 sm:flex-row sm:items-center sm:justify-between">
      <div className="space-y-0.5">
        <p className="text-sm font-semibold text-foreground">{t('title')}</p>
        <p className="text-xs leading-relaxed text-muted-foreground">{t('description')}</p>
        {errorCode && <ArchiveErrorNotice code={errorCode} />}
      </div>
      <Button
        size="sm"
        variant="outline"
        className="shrink-0 gap-1.5 rounded-xl"
        disabled={busy}
        onClick={() => void rollback()}
      >
        {busy ? (
          <CircleNotch className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <ArrowCounterClockwise className="h-3.5 w-3.5" weight="bold" />
        )}
        {t('action')}
      </Button>
    </div>
  );
});
