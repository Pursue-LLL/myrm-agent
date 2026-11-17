'use client';

import dynamic from 'next/dynamic';
import { useId, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  Timer,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  Ban,
  SkipForward,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  Wrench,
  Activity,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { UnifiedRun, RunSource, RunStatus } from '@/services/runs';
import { skipReasonLabelKey } from '@/components/features/cron/cron-utils';
import { formatRelativeTime } from '@/lib/utils/relativeTime';

const ExecutionTraceTimeline = dynamic(
  () => import('@/components/features/settings/sections/system/ExecutionTraceTimeline'),
  { ssr: false },
);

// An icon is a non-text element and needs 3:1 against the row: in light mode emerald and amber use the 600 tier
// (their 500 tier stays under 3:1).
const STATUS_ICON: Record<RunStatus, React.ReactNode> = {
  running: <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500 dark:text-blue-400" />,
  ok: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />,
  error: <XCircle className="h-3.5 w-3.5 text-red-500 dark:text-red-400" />,
  skipped: <SkipForward className="h-3.5 w-3.5 text-muted-foreground" />,
  cancelled: <Ban className="h-3.5 w-3.5 text-muted-foreground" />,
  timed_out: <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />,
  circuit_break: <ShieldAlert className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400" />,
};

const SOURCE_LABEL_KEY: Record<RunSource, 'sourceCron' | 'sourceKanban' | 'sourceShell'> = {
  cron: 'sourceCron',
  kanban: 'sourceKanban',
  background: 'sourceShell',
};

const SOURCE_COLORS: Record<RunSource, string> = {
  cron: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  kanban: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
  background: 'bg-orange-500/10 text-orange-700 dark:text-orange-400',
};

function formatDuration(ms: number | null): string {
  if (ms == null) {
    return '-';
  }
  const seconds = ms / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (minutes < 60) {
    return `${minutes}m ${secs}s`;
  }
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function stopReasonLabelKey(code: string | undefined): string {
  if (!code) {
    return 'stopReasonUnknown';
  }
  if (code === 'iteration_limit_reached') {
    return 'stopReasonIterationLimit';
  }
  if (code === 'engine_limit_reached') {
    return 'stopReasonEngineLimit';
  }
  if (code === 'timed_out') {
    return 'stopReasonTimedOut';
  }
  if (code === 'agent_cancelled' || code === 'user_cancelled') {
    return 'stopReasonCancelled';
  }
  if (code === 'error') {
    return 'stopReasonError';
  }
  return 'stopReasonUnknown';
}

type Translator = ReturnType<typeof useTranslations>;

// The icon shows the state; this word is what assistive tech reads. It reuses the Hub's filter and stop-reason copy
// (`runs`) and the cron panel's run-status copy (`cron`), so both locales already carry it.
function statusLabel(status: RunStatus, t: Translator, tCron: Translator): string {
  switch (status) {
    case 'running':
      return t('filterRunning');
    case 'ok':
      return t('filterOk');
    case 'error':
      return t('filterError');
    case 'timed_out':
      return t('stopReasonTimedOut');
    case 'cancelled':
      return t('stopReasonCancelled');
    case 'skipped':
      return tCron('runSkipped');
    case 'circuit_break':
      return tCron('runCircuitBreak');
  }
}

export function RunRow({ run, t }: { run: UnifiedRun; t: ReturnType<typeof useTranslations> }) {
  const tCron = useTranslations('cron');
  const locale = useLocale();
  const detailId = useId();
  const [expanded, setExpanded] = useState(false);
  // A skipped cron run's output is the code of what skipped it; the label is what the user can read.
  const skipLabelKey =
    run.source === 'cron' && run.status === 'skipped' ? skipReasonLabelKey(run.output ?? undefined) : undefined;
  const skipLabel = skipLabelKey ? tCron(skipLabelKey) : null;
  const output = skipLabel ?? run.output;
  const summary = skipLabel ?? run.summary;
  const canShowTrace = run.source === 'kanban' && run.task_id != null;
  const hasDetail = !!(run.output || run.error || run.stop_reason || run.has_execution_steps || canShowTrace);
  const stopReasonLabel = run.stop_reason ? t(stopReasonLabelKey(run.stop_reason.code)) : null;
  const stopReasonMessage = run.stop_reason?.message?.trim() || null;
  const compactStopReason = !run.error ? stopReasonMessage : null;
  // The server mirrors the error text into the stop reason message; the error block already shows it.
  const stopReasonDetail = stopReasonMessage !== run.error?.trim() ? stopReasonMessage : null;

  // The header is the only toggle: the detail region holds its own controls (trace replay, export, selectable
  // output), so it must not sit inside the element that collapses the row. Button content is phrasing-only.
  const summaryContent = (
    <>
      <span className="mt-0.5 shrink-0">
        {STATUS_ICON[run.status]}
        <span className="sr-only">{statusLabel(run.status, t, tCron)}</span>
      </span>
      <span className="block flex-1 min-w-0 space-y-0.5">
        <span className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground truncate">{run.title}</span>
          <span className={cn('shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium', SOURCE_COLORS[run.source])}>
            {t(SOURCE_LABEL_KEY[run.source])}
          </span>
          {run.has_execution_steps && (
            <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-400">
              {t('executionStepsBadge')}
            </span>
          )}
        </span>
        {!expanded && run.error && (
          <span className="block text-[11px] text-destructive-text font-mono truncate">{run.error}</span>
        )}
        {!expanded && !run.error && compactStopReason && (
          <span className="block text-[11px] text-warning truncate">{compactStopReason}</span>
        )}
        {!expanded && !run.error && !compactStopReason && summary && (
          <span className="block text-[11px] text-muted-foreground truncate">{summary}</span>
        )}
      </span>
      <span className="shrink-0 flex flex-col items-end gap-0.5">
        <span className="text-[10px] text-muted-foreground">{formatRelativeTime(run.started_at, locale)}</span>
        {run.duration_ms != null && (
          <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
            <Timer className="h-2.5 w-2.5" />
            {formatDuration(run.duration_ms)}
          </span>
        )}
        {hasDetail &&
          (expanded ? (
            <ChevronUp className="h-3 w-3 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          ))}
      </span>
    </>
  );

  return (
    <div className="rounded-lg border border-border/20 bg-card/30">
      {hasDetail ? (
        <button
          type="button"
          className={cn(
            'flex w-full cursor-pointer items-start gap-3 px-3 py-2.5 text-left transition-colors hover:bg-card/60',
            expanded ? 'rounded-t-lg' : 'rounded-lg',
          )}
          aria-expanded={expanded}
          aria-controls={expanded ? detailId : undefined}
          onClick={() => setExpanded((open) => !open)}
        >
          {summaryContent}
        </button>
      ) : (
        <div className="flex items-start gap-3 px-3 py-2.5">{summaryContent}</div>
      )}

      {expanded && (
        <div id={detailId} className="px-3 pb-3 pt-0 space-y-2 border-t border-border/10 mt-0">
          {output && (
            <pre className="text-xs text-muted-foreground bg-muted/30 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap break-words font-mono max-h-48 overflow-y-auto">
              {output}
            </pre>
          )}
          {run.error && (
            <pre className="text-xs text-destructive-text bg-red-500/5 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap break-words max-h-32 overflow-y-auto">
              {run.error}
            </pre>
          )}
          {run.stop_reason && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2 space-y-1">
              <p className="text-[10px] font-medium text-amber-700 dark:text-amber-300 uppercase tracking-wide">
                {t('stopReasonTitle')}
              </p>
              {stopReasonLabel && <p className="text-xs text-foreground/90">{stopReasonLabel}</p>}
              {stopReasonDetail && (
                <p className="text-xs text-muted-foreground whitespace-pre-wrap break-words">{stopReasonDetail}</p>
              )}
            </div>
          )}
          {canShowTrace && (
            <div className="rounded-lg border border-border/30 bg-muted/20 p-2 space-y-2">
              <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <Activity className="h-3 w-3" />
                {t('executionTrace')}
              </p>
              <ExecutionTraceTimeline
                sessionId={run.task_id as string}
                showEvalCase={false}
                pollMs={run.status === 'running' ? 30_000 : undefined}
              />
            </div>
          )}
          {Array.isArray(run.metadata?.progressSteps) && (
            <div className="rounded-lg border border-border/30 bg-muted/20 p-2 space-y-1">
              <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <Wrench className="h-3 w-3" />
                {t('executionSteps')} ({(run.metadata.progressSteps as unknown[]).length})
              </p>
              <div className="space-y-0.5">
                {(run.metadata.progressSteps as Array<{ tool_name?: string; step_key?: string; error?: string }>).map(
                  (step, idx) => (
                    <div key={idx} className="flex items-center gap-1.5 text-[10px]">
                      <span
                        className={cn(
                          'h-1.5 w-1.5 rounded-full shrink-0',
                          step.error ? 'bg-red-400' : 'bg-emerald-400',
                        )}
                      />
                      <span className="font-mono text-foreground/80 truncate">{step.tool_name || step.step_key}</span>
                      {step.error && <span className="text-destructive-text truncate ml-1">{step.error}</span>}
                    </div>
                  ),
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
