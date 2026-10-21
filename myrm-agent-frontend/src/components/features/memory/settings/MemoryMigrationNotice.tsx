'use client';

/**
 * [INPUT]
 * @/store/useRetrievalStore::useRetrievalStore (POS: orphan reminder and migration run state)
 * @/lib/utils/classnameUtils::cn (POS: class merging)
 * @/components/primitives/progress::Progress (POS: determinate progress bar)
 *
 * [OUTPUT]
 * MemoryMigrationNotice: reminder, progress and outcome of moving the memories of a previous embedding model to the current one
 * (renders nothing when there is nothing to migrate)
 *
 * [POS]
 * Settings → Models → Embedding and Settings → Memory. Memories left behind by an embedding model switch are not used in
 * replies, so the notice reads their count itself when it mounts instead of relying on the switch happening in this
 * session. Migration runs in the background: the notice follows it live and keeps the reminder (with the count left)
 * when some memories failed.
 */

import { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import { IconAlertCircle, IconCheckCircle, IconLoader } from '@/components/features/icons/PremiumIcons';
import { Progress } from '@/components/primitives/progress';
import { cn } from '@/lib/utils/classnameUtils';
import useRetrievalStore from '@/store/useRetrievalStore';

const NOTICE_BASE = 'flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between';
const DISMISS_BUTTON = 'px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground';

interface MemoryMigrationNoticeProps {
  className?: string;
}

export default function MemoryMigrationNotice({ className }: MemoryMigrationNoticeProps) {
  const t = useTranslations('settings.defaultModel.retrieval');
  const {
    orphanCount,
    reindexStatus,
    reindexProgress,
    reindexResult,
    checkOrphanCollections,
    executeReindex,
    dismissOrphanWarning,
  } = useRetrievalStore(
    useShallow((state) => ({
      orphanCount: state.orphanCount,
      reindexStatus: state.reindexStatus,
      reindexProgress: state.reindexProgress,
      reindexResult: state.reindexResult,
      checkOrphanCollections: state.checkOrphanCollections,
      executeReindex: state.executeReindex,
      dismissOrphanWarning: state.dismissOrphanWarning,
    })),
  );

  useEffect(() => {
    void checkOrphanCollections();
  }, [checkOrphanCollections]);

  if (reindexStatus === 'running') {
    const { done, total } = reindexProgress;
    const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
    return (
      <output className={cn('flex flex-col gap-3 rounded-lg border border-primary/30 bg-primary/5 p-4', className)}>
        <div className="flex items-center gap-2 text-sm text-foreground">
          <IconLoader className="h-4 w-4 shrink-0 animate-spin text-primary" />
          <span>{total > 0 ? t('reindexProgress', { done, total }) : t('reindexing')}</span>
        </div>
        {/* The Progress primitive keeps `value` for the bar only, so the ARIA value is passed explicitly. */}
        <Progress aria-label={t('reindexing')} aria-valuenow={percent} value={percent} className="h-1.5" />
      </output>
    );
  }

  if (orphanCount > 0) {
    let message = t('orphanWarning', { count: orphanCount });
    if (reindexStatus === 'error') {
      message = t('reindexError');
    } else if (reindexResult) {
      message = t('reindexPartial', { migrated: reindexResult.migrated, failed: reindexResult.failed });
    }
    return (
      <div className={cn(NOTICE_BASE, 'border-warning/30 bg-warning/5', className)}>
        <div className="flex items-start gap-2 text-sm text-foreground">
          <IconAlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <span>{message}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button type="button" onClick={dismissOrphanWarning} className={DISMISS_BUTTON}>
            {t('dismiss')}
          </button>
          <button
            type="button"
            onClick={() => void executeReindex()}
            className="rounded-md bg-warning/10 px-3 py-1.5 text-xs font-medium text-warning transition-colors hover:bg-warning/20"
          >
            {t('reindex')}
          </button>
        </div>
      </div>
    );
  }

  if (reindexResult) {
    return (
      <output className={cn(NOTICE_BASE, 'border-primary/30 bg-primary/5', className)}>
        <div className="flex items-start gap-2 text-sm text-foreground">
          <IconCheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <span>
            {reindexResult.migrated > 0 ? t('reindexDone', { count: reindexResult.migrated }) : t('reindexUpToDate')}
          </span>
        </div>
        <button type="button" onClick={dismissOrphanWarning} className={`${DISMISS_BUTTON} self-end sm:self-auto`}>
          {t('dismiss')}
        </button>
      </output>
    );
  }

  return null;
}
