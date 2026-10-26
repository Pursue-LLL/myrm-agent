'use client';

/**
 * [INPUT]
 * @/services/wiki/ima::ImaStatus (POS: counts, phase, job state)
 * ./imaCopy::deriveImaSyncMode, imaProgress, imaSkippedCount, formatImaChars (POS: status → what the user sees)
 *
 * [OUTPUT]
 * ImaSyncPanel: progress, outcome counts, pause/resume, "build knowledge" and the entry to the item report
 *
 * [POS]
 * Third screen of the ima card, shown once a sync exists. It reports outcomes honestly (imported, skipped, failed,
 * simplified, removed upstream) instead of one reassuring number, and puts the cost-bearing step, turning the imported
 * documents into knowledge, behind an explicit button.
 */

import { useLocale, useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Progress } from '@/components/primitives/progress';
import { cn } from '@/lib/utils/classnameUtils';
import type { ImaStatus } from '@/services/wiki/ima';
import type { ImaAction } from './useImaSync';
import {
  deriveImaSyncMode,
  formatImaChars,
  imaAttentionCount,
  imaProgress,
  imaSkippedCount,
  isImaBackfilling,
} from './imaCopy';

interface ImaSyncPanelProps {
  status: ImaStatus;
  busy: ImaAction | null;
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
  return tiles;
}

const TILE_TONE: Record<StatTile['tone'], string> = {
  default: 'text-foreground',
  warning: 'text-warning',
  muted: 'text-muted-foreground',
};

export default function ImaSyncPanel({ status, busy, onPause, onResume, onCompile, onOpenReport }: ImaSyncPanelProps) {
  const t = useTranslations('settings.wiki.ima');
  const locale = useLocale();
  const mode = deriveImaSyncMode(status);
  const progress = imaProgress(status.counts);
  const showBar = isImaBackfilling(status) && status.counts.total > 0;
  const hasReport = imaAttentionCount(status.counts) + status.counts.partial + status.counts.remote_deleted > 0;
  const lastRun = status.last_run_at ? new Date(status.last_run_at).toLocaleString(locale) : null;
  const toggleBusy = busy === 'pause' || busy === 'resume';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <p className="text-sm font-medium">{t(`mode.${mode}`)}</p>
          {lastRun ? <p className="text-xs text-muted-foreground">{t('mode.lastRun', { time: lastRun })}</p> : null}
        </div>
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
      {status.notes_unavailable ? (
        <p className="text-xs text-muted-foreground">{t('notices.notesUnavailable')}</p>
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
          <Button type="button" size="sm" disabled={busy === 'compile'} onClick={onCompile}>
            {busy === 'compile' ? t('compile.running') : t('compile.action')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
