'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { type MemoryGuardianMorningDigest } from '@/services/memory';

interface MemoryGuardianDigestPanelProps {
  digest: MemoryGuardianMorningDigest;
}

function formatDigestTime(occurredAt: string | undefined, fallback: string): string {
  if (!occurredAt) return fallback;
  const ts = new Date(occurredAt);
  if (Number.isNaN(ts.getTime())) return fallback;
  return ts.toLocaleString();
}

function formatWindowRange(startAt: string | undefined, endAt: string | undefined): string | null {
  if (!startAt || !endAt) return null;
  const start = new Date(startAt);
  const end = new Date(endAt);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
  return `${start.toLocaleString()} - ${end.toLocaleString()}`;
}

function describeWindowMode(
  mode: MemoryGuardianMorningDigest['window_mode'],
  t: ReturnType<typeof useTranslations>,
): string {
  if (mode === 'quiet_window') return t('digestWindowModeQuiet');
  if (mode === 'rolling_24h') return t('digestWindowModeRolling');
  return t('digestWindowModeUnknown');
}

const MemoryGuardianDigestPanel = memo(({ digest }: MemoryGuardianDigestPanelProps) => {
  const t = useTranslations('settings.memoryGuardian');
  if (!digest.available || !digest.counts) return null;
  const windowRange = formatWindowRange(digest.window_started_at, digest.window_ended_at);
  const windowModeLabel = describeWindowMode(digest.window_mode, t);

  return (
    <div className="rounded-xl border border-border/40 bg-background/40 p-3 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold">{t('digestTitle')}</span>
        <span className="text-[11px] text-muted-foreground">{formatDigestTime(digest.occurred_at, t('never'))}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">{t('digestWindowMode', { mode: windowModeLabel })}</p>
      {windowRange && <p className="text-[11px] text-muted-foreground leading-5">{t('digestWindow', { range: windowRange })}</p>}
      {digest.summary && <p className="text-[11px] text-muted-foreground leading-5">{digest.summary}</p>}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px]">
        {typeof digest.event_count === 'number' && (
          <div className="rounded-md bg-background px-2 py-1">
            <span className="text-muted-foreground">{t('digestRuns')}</span>
            <span className="ml-1 font-semibold tabular-nums">{digest.event_count}</span>
          </div>
        )}
        {typeof digest.forced_runs === 'number' && (
          <div className="rounded-md bg-background px-2 py-1">
            <span className="text-muted-foreground">{t('digestManualRuns')}</span>
            <span className="ml-1 font-semibold tabular-nums">{digest.forced_runs}</span>
          </div>
        )}
        <div className="rounded-md bg-background px-2 py-1">
          <span className="text-muted-foreground">{t('digestMerged')}</span>
          <span className="ml-1 font-semibold tabular-nums">{digest.counts.merged}</span>
        </div>
        <div className="rounded-md bg-background px-2 py-1">
          <span className="text-muted-foreground">{t('digestCorrected')}</span>
          <span className="ml-1 font-semibold tabular-nums">{digest.counts.corrected}</span>
        </div>
        <div className="rounded-md bg-background px-2 py-1">
          <span className="text-muted-foreground">{t('digestArchived')}</span>
          <span className="ml-1 font-semibold tabular-nums">{digest.counts.archived}</span>
        </div>
        <div className="rounded-md bg-background px-2 py-1">
          <span className="text-muted-foreground">{t('digestForgotten')}</span>
          <span className="ml-1 font-semibold tabular-nums">{digest.counts.forgotten}</span>
        </div>
        {typeof digest.health_delta === 'number' && (
          <div className="rounded-md bg-background px-2 py-1">
            <span className="text-muted-foreground">{t('digestHealthDelta')}</span>
            <span
              className={cn(
                'ml-1 font-semibold tabular-nums',
                digest.health_delta >= 0 ? 'text-emerald-500' : 'text-red-500',
              )}
            >
              {digest.health_delta >= 0 ? `+${digest.health_delta}` : `${digest.health_delta}`}
            </span>
          </div>
        )}
      </div>
    </div>
  );
});

MemoryGuardianDigestPanel.displayName = 'MemoryGuardianDigestPanel';

export default MemoryGuardianDigestPanel;
