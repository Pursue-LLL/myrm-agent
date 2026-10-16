'use client';

/**
 * [INPUT]
 * @/store/useRetrievalStore::useRetrievalStore (POS: orphan reminder and migration run state)
 * @/components/primitives/progress::Progress (POS: determinate progress bar)
 *
 * [OUTPUT]
 * MemoryMigrationNotice: reminder, progress and outcome of moving the memories of a previous embedding model to the current one
 *
 * [POS]
 * Settings → Models → Embedding. Shown after an embedding model switch left memories behind; migration runs in the
 * background, so the notice follows it live and keeps the reminder (with the count left) when some memories failed.
 */

import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import { IconAlertCircle, IconCheckCircle, IconLoader } from '@/components/features/icons/PremiumIcons';
import { Progress } from '@/components/primitives/progress';
import useRetrievalStore from '@/store/useRetrievalStore';

const NOTICE_BASE = 'flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between';
const DISMISS_BUTTON = 'px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground';

export default function MemoryMigrationNotice() {
  const t = useTranslations('settings.defaultModel.retrieval');
  const { orphanCount, reindexStatus, reindexProgress, reindexResult, executeReindex, dismissOrphanWarning } =
    useRetrievalStore(
      useShallow((state) => ({
        orphanCount: state.orphanCount,
        reindexStatus: state.reindexStatus,
        reindexProgress: state.reindexProgress,
        reindexResult: state.reindexResult,
        executeReindex: state.executeReindex,
        dismissOrphanWarning: state.dismissOrphanWarning,
      })),
    );

  if (reindexStatus === 'running') {
    const { done, total } = reindexProgress;
    const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
    return (
      <output className="flex flex-col gap-3 rounded-lg border border-primary/30 bg-primary/5 p-4">
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
      <div className={`${NOTICE_BASE} border-warning/30 bg-warning/5`}>
        <div className="flex items-start gap-2 text-sm text-warning">
          <IconAlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
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
      <output className={`${NOTICE_BASE} border-primary/30 bg-primary/5`}>
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
