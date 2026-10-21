'use client';

/**
 * [INPUT]
 * memoryLifecyclePhases (POS: lifecycle phase state types)
 *
 * [OUTPUT]
 * MemoryLifecycleTimeline: Compact write→extract→recall phase strip for MemoryInsightPanel.
 *
 * [POS]
 * Per-turn memory lifecycle UI — SSE-driven, zero prompt impact.
 */

import { useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Check, Loader2, Minus, X } from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';
import type {
  MemoryLifecyclePhaseId,
  MemoryLifecyclePhaseState,
  MemoryLifecyclePhaseStatus,
} from '@/components/features/message-box/memoryLifecyclePhases';

const PHASE_ORDER: MemoryLifecyclePhaseId[] = ['write', 'extract', 'recall'];

function statusIcon(status: MemoryLifecyclePhaseStatus) {
  switch (status) {
    case 'pending':
      return <Loader2 className="h-3 w-3 animate-spin text-amber-500" />;
    case 'success':
      return <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />;
    case 'error':
      return <X className="h-3 w-3 text-destructive" />;
    case 'skipped':
      return <Minus className="h-3 w-3 text-muted-foreground" />;
    default:
      return <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />;
  }
}

function statusLabelKey(phase: MemoryLifecyclePhaseId, status: MemoryLifecyclePhaseStatus): string {
  if (phase === 'extract' && status === 'pending') {
    return 'lifecycleExtractPending';
  }
  switch (status) {
    case 'pending':
      return 'lifecyclePending';
    case 'success':
      return 'lifecycleSuccess';
    case 'skipped':
      return 'lifecycleSkipped';
    case 'error':
      return 'lifecycleError';
    default:
      return 'lifecycleIdle';
  }
}

function phaseLabelKey(phase: MemoryLifecyclePhaseId): string {
  switch (phase) {
    case 'write':
      return 'lifecycleWrite';
    case 'extract':
      return 'lifecycleExtract';
    default:
      return 'lifecycleRecall';
  }
}

function extractSuccessStoredDetail(
  phase: MemoryLifecyclePhaseState,
  t: ReturnType<typeof useTranslations>,
): string | null {
  if (phase.status !== 'success' || phase.id !== 'extract') {
    return null;
  }
  if (phase.storedCount != null && phase.storedCount > 0) {
    return t('lifecycleStoredCount', { count: phase.storedCount });
  }
  if (phase.storedCount === 0 && phase.verbatimCount != null && phase.verbatimCount > 0) {
    return t('lifecycleVerbatimStored', { count: phase.verbatimCount });
  }
  if (phase.storedCount != null) {
    return t('lifecycleStoredCountNone');
  }
  return null;
}

export function MemoryLifecycleTimeline({
  phases,
  className,
  showRecall = true,
  onRetryExtract,
}: {
  phases: Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState>;
  className?: string;
  showRecall?: boolean;
  onRetryExtract?: () => Promise<void>;
}) {
  const t = useTranslations('memoryInsight');
  const [retrying, setRetrying] = useState(false);

  const visiblePhases = showRecall ? PHASE_ORDER : PHASE_ORDER.filter((id) => id !== 'recall');

  if (!visiblePhases.some((phaseId) => phases[phaseId].status !== 'idle')) {
    return null;
  }

  return (
    <div
      className={cn('w-full rounded-lg border border-border/50 bg-muted/20 px-3 py-2', className)}
      data-testid="memory-lifecycle-timeline"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t('lifecycleTitle')}</p>
        <Link
          href="/settings/memory?sub=explorer"
          className="shrink-0 text-[10px] font-medium text-primary/80 hover:text-primary"
        >
          {t('lifecycleCommandCenter')}
        </Link>
      </div>
      <ol className={cn('grid grid-cols-1 gap-2', showRecall ? 'sm:grid-cols-3' : 'sm:grid-cols-2')}>
        {visiblePhases.map((phaseId) => {
          const phase = phases[phaseId];
          const storedDetail = extractSuccessStoredDetail(phase, t);
          return (
            <li
              key={phaseId}
              className="flex min-w-0 flex-col gap-1 rounded-md border border-border/40 bg-background/60 px-2 py-1.5"
            >
              <div className="flex items-center gap-1.5">
                {statusIcon(phase.status)}
                <span className="truncate text-[11px] font-medium text-foreground">{t(phaseLabelKey(phaseId))}</span>
              </div>
              <span className="text-[10px] text-muted-foreground">
                {t(statusLabelKey(phaseId, phase.status))}
                {storedDetail ? ` · ${storedDetail}` : null}
                {phase.durationMs != null && phase.status === 'success' && phaseId === 'extract'
                  ? ` · ${t('lifecycleDurationMs', { ms: phase.durationMs })}`
                  : null}
              </span>
            </li>
          );
        })}
      </ol>
      {phases.extract.status === 'error' && onRetryExtract && (
        <button
          type="button"
          disabled={retrying}
          onClick={() => {
            setRetrying(true);
            void onRetryExtract().finally(() => setRetrying(false));
          }}
          className="mt-2 text-[11px] font-medium text-primary hover:underline disabled:opacity-50"
        >
          {retrying ? t('lifecycleRetrying') : t('lifecycleRetryExtract')}
        </button>
      )}
    </div>
  );
}
