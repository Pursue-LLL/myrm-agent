'use client';

/**
 * [INPUT]
 * @/services/wiki/ima::ImaStatus (POS: counts, phase, job state)
 * ./imaCopy::deriveImaSyncMode, imaProgress, imaSkippedCount, canImaSyncNow, imaAutoCompileKey, formatImaChars,
 *   imaUnreadableLibraries, hasImaUnreadableNotes, formatImaNames (POS: status → what the user sees)
 *
 * [OUTPUT]
 * ImaSyncPanel: progress, outcome counts, sync now / pause / resume, the compile step and the entry to the item report
 *
 * [POS]
 * Third screen of the ima card, shown once a sync exists. It reports outcomes honestly (imported, skipped, failed,
 * simplified, removed by the user, gone from ima) instead of one reassuring number, tells the user when the next automatic
 * check happens and lets them run it now, names the libraries (or the notes) ima could not be read completely, and puts
 * the cost-bearing step, compiling the imported documents, behind an explicit button while saying how later changes
 * are compiled.
 */

import { useLocale, useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Progress } from '@/components/primitives/progress';
import { cn } from '@/lib/utils/classnameUtils';
import type { ImaStatus } from '@/services/wiki/ima';
import type { ImaAction } from './useImaSync';
import {
  canImaSyncNow,
  deriveImaSyncMode,
  formatImaChars,
  formatImaNames,
  hasImaUnreadableNotes,
  imaAutoCompileKey,
  imaAttentionCount,
  imaProgress,
  imaSkippedCount,
  imaUnreadableLibraries,
  isImaBackfilling,
} from './imaCopy';

interface ImaSyncPanelProps {
  status: ImaStatus;
  busy: ImaAction | null;
  onSyncNow: () => void;
  onPause: () => void;
  onResume: () => void;
  onCompile: () => void;
  onOpenReport: () => void;
}

interface StatTile {
  key: string;
  value: number;
  tone: 'default' | 'warning' | 'muted';
}

function statTiles(status: ImaStatus): StatTile[] {
  const { counts } = status;
  const tiles: StatTile[] = [{ key: 'imported', value: counts.synced, tone: 'default' }];
  if (counts.pending > 0) {
    tiles.push({ key: 'pending', value: counts.pending, tone: 'muted' });
  }
  if (counts.failed > 0) {
    tiles.push({ key: 'failed', value: counts.failed, tone: 'warning' });
  }
  const skipped = imaSkippedCount(counts);
  if (skipped > 0) {
    tiles.push({ key: 'skipped', value: skipped, tone: 'muted' });
  }
  if (counts.partial > 0) {
    tiles.push({ key: 'partial', value: counts.partial, tone: 'warning' });
  }
  if (counts.remote_deleted > 0) {
    tiles.push({ key: 'removed', value: counts.remote_deleted, tone: 'muted' });
  }
  if (counts.dismissed > 0) {
    tiles.push({ key: 'dismissed', value: counts.dismissed, tone: 'muted' });
  }
  return tiles;
}

const TILE_TONE: Record<StatTile['tone'], string> = {
  default: 'text-foreground',
  warning: 'text-warning',
  muted: 'text-muted-foreground',
};

export default function ImaSyncPanel({
  status,
  busy,
  onSyncNow,
  onPause,
  onResume,
  onCompile,
  onOpenReport,
}: ImaSyncPanelProps) {
  const t = useTranslations('settings.wiki.ima');
  const locale = useLocale();
  const mode = deriveImaSyncMode(status);
  const progress = imaProgress(status.counts);
  const showBar = isImaBackfilling(status) && status.counts.total > 0;
  const hasReport = imaAttentionCount(status.counts) + status.counts.partial + status.counts.remote_deleted > 0;
  const lastRun = status.last_run_at ? new Date(status.last_run_at).toLocaleString(locale) : null;
  const nextCheck =
    mode === 'upToDate' && status.job.next_run_at ? new Date(status.job.next_run_at).toLocaleString(locale) : null;
  const unreadableLibraries = imaUnreadableLibraries(status);
  const toggleBusy = busy === 'pause' || busy === 'resume';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <p className="text-sm font-medium">{t(`mode.${mode}`)}</p>
          {lastRun ? <p className="text-xs text-muted-foreground">{t('mode.lastRun', { time: lastRun })}</p> : null}
          {nextCheck ? (
            <p className="text-xs text-muted-foreground">{t('mode.nextCheck', { time: nextCheck })}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canImaSyncNow(status) ? (
            <Button type="button" size="sm" variant="outline" disabled={busy === 'syncNow'} onClick={onSyncNow}>
              {busy === 'syncNow' ? t('actions.syncNowRunning') : t('actions.syncNow')}
            </Button>
          ) : null}
          {status.job.state === 'paused' ? (
            <Button type="button" size="sm" variant="outline" disabled={toggleBusy} onClick={onResume}>
              {t('actions.resume')}
            </Button>
          ) : (
            <Button type="button" size="sm" variant="outline" disabled={toggleBusy} onClick={onPause}>
              {t('actions.pause')}
            </Button>
          )}
        </div>
      </div>

      {showBar ? (
        <div className="space-y-1.5">
          <Progress value={progress.percent} aria-label={t('mode.progressLabel')} />
          <p className="text-xs text-muted-foreground">
            {t('mode.progress', { done: progress.done, total: progress.total })}
          </p>
        </div>
      ) : null}

      {status.last_error_kind === 'rate_limit' ? (
        <p className="text-xs text-warning">{t('notices.rateLimited')}</p>
      ) : null}
      {status.last_error_kind === 'transient' ? (
        <p className="text-xs text-warning">{t('notices.unreachable')}</p>
      ) : null}
      {status.last_error_kind === 'internal' ? <p className="text-xs text-warning">{t('notices.internal')}</p> : null}
      {hasImaUnreadableNotes(status) ? (
        <p className="text-xs text-muted-foreground">{t('notices.unreadableNotes')}</p>
      ) : null}
      {unreadableLibraries.length > 0 ? (
        <p className="break-words text-xs text-muted-foreground">
          {t('notices.unreadableLibraries', { names: formatImaNames(unreadableLibraries, locale) })}
        </p>
      ) : null}

      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {statTiles(status).map((tile) => (
          <li key={tile.key} className="rounded-lg border border-border/60 bg-background/40 px-3 py-2">
            <span className={cn('block text-lg font-semibold tabular-nums', TILE_TONE[tile.tone])}>{tile.value}</span>
            <span className="block text-xs text-muted-foreground">{t(`stats.${tile.key}`)}</span>
          </li>
        ))}
      </ul>

      {hasReport ? (
        <Button type="button" size="sm" variant="ghost" className="-ml-2" onClick={onOpenReport}>
          {t('actions.viewDetails')}
        </Button>
      ) : null}

      {status.counts.synced > 0 ? (
        <div className="space-y-2 rounded-lg border border-primary/30 bg-primary/5 px-3 py-3">
          <p className="text-sm font-medium">{t('compile.title')}</p>
          <p className="text-xs text-muted-foreground">
            {t('compile.body', {
              count: status.counts.synced,
              chars: formatImaChars(status.total_chars, locale),
            })}
          </p>
          <p className="text-xs text-muted-foreground">{t(imaAutoCompileKey(status))}</p>
          <Button type="button" size="sm" disabled={busy === 'compile'} onClick={onCompile}>
            {busy === 'compile' ? t('compile.running') : t('compile.action')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
