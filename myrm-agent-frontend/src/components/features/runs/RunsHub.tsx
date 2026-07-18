'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  Clock,
  Timer,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  Ban,
  SkipForward,
  ChevronDown,
  ChevronUp,
  Wrench,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { Skeleton } from '@/components/primitives/skeleton';
import {
  listUnifiedRuns,
  type UnifiedRun,
  type RunSource,
  type RunStatus,
} from '@/services/runs';

const STATUS_ICON: Record<RunStatus, React.ReactNode> = {
  running: <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500 dark:text-blue-400" />,
  ok: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 dark:text-emerald-400" />,
  error: <XCircle className="h-3.5 w-3.5 text-red-500 dark:text-red-400" />,
  skipped: <SkipForward className="h-3.5 w-3.5 text-muted-foreground" />,
  cancelled: <Ban className="h-3.5 w-3.5 text-muted-foreground" />,
  timed_out: <AlertTriangle className="h-3.5 w-3.5 text-amber-500 dark:text-amber-400" />,
};

const SOURCE_LABEL_KEY: Record<RunSource, 'sourceCron' | 'sourceKanban' | 'sourceShell'> = {
  cron: 'sourceCron',
  kanban: 'sourceKanban',
  background: 'sourceShell',
};

const SOURCE_COLORS: Record<RunSource, string> = {
  cron: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  kanban: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
  background: 'bg-orange-500/10 text-orange-600 dark:text-orange-400',
};

function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (minutes < 60) return `${minutes}m ${secs}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function formatRelativeTime(isoDate: string, t: ReturnType<typeof useTranslations>): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return t('timeJustNow');
  if (minutes < 60) return t('timeMinutesAgo', { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t('timeHoursAgo', { count: hours });
  const days = Math.floor(hours / 24);
  return t('timeDaysAgo', { count: days });
}

const STATUS_FILTERS = [
  { value: '', labelKey: 'filterAll' },
  { value: 'running', labelKey: 'filterRunning' },
  { value: 'ok', labelKey: 'filterOk' },
  { value: 'error', labelKey: 'filterError' },
] as const;

const SOURCE_FILTERS = [
  { value: '', labelKey: 'sourceAll' },
  { value: 'cron', labelKey: 'sourceCron' },
  { value: 'kanban', labelKey: 'sourceKanban' },
  { value: 'background', labelKey: 'sourceShell' },
] as const;

export function RunsHub() {
  const t = useTranslations('runs');
  const tRef = useRef(t);
  tRef.current = t;
  const [runs, setRuns] = useState<UnifiedRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [degraded, setDegraded] = useState(false);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [statusFilter, setStatusFilter] = useState<RunStatus | ''>('');
  const [sourceFilter, setSourceFilter] = useState<RunSource | ''>('');
  const offsetRef = useRef(0);
  const requestSeqRef = useRef(0);

  const fetchRuns = useCallback(
    async (offset: number, append: boolean) => {
      const requestSeq = ++requestSeqRef.current;
      setLoading(true);
      if (!append) {
        setLoadError(false);
        setDegraded(false);
      }
      try {
        const res = await listUnifiedRuns({
          status: statusFilter || undefined,
          source: sourceFilter || undefined,
          limit: 30,
          offset,
        });
        if (requestSeq !== requestSeqRef.current) {
          return;
        }
        if (append) {
          setRuns((prev) => {
            const next = [...prev, ...res.items];
            offsetRef.current = next.length;
            return next;
          });
        } else {
          setRuns(res.items);
          offsetRef.current = res.items.length;
        }
        setTotal(res.total);
        setHasMore(res.has_more);
        setDegraded(res.degraded);
      } catch {
        if (requestSeq !== requestSeqRef.current) {
          return;
        }
        if (!append) {
          setRuns([]);
          setTotal(0);
          setHasMore(false);
          offsetRef.current = 0;
          setLoadError(true);
        } else {
          toast.error(tRef.current('loadError'));
        }
      } finally {
        if (requestSeq === requestSeqRef.current) {
          setLoading(false);
        }
      }
    },
    [statusFilter, sourceFilter],
  );

  const reload = useCallback(() => {
    void fetchRuns(0, false);
  }, [fetchRuns]);

  const loadMore = useCallback(() => {
    void fetchRuns(offsetRef.current, true);
  }, [fetchRuns]);

  useEffect(() => {
    offsetRef.current = 0;
    void fetchRuns(0, false);
  }, [fetchRuns]);

  const hasActiveFilter = statusFilter !== '' || sourceFilter !== '';

  return (
    <div className="flex h-full w-full flex-col p-4 md:p-6">
      <div className="mx-auto w-full max-w-5xl space-y-5">
        <header className="flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-lg font-semibold text-foreground">{t('title')}</h1>
            <p className="text-xs text-muted-foreground">{t('subtitle')}</p>
          </div>
          {total > 0 && (
            <span className="text-xs text-muted-foreground">
              {total} {t('totalRuns')}
            </span>
          )}
        </header>

        <div className="flex flex-wrap items-center gap-3">
          <Tabs
            value={statusFilter || 'all'}
            onValueChange={(v) => setStatusFilter(v === 'all' ? '' : (v as RunStatus))}
          >
            <TabsList className="h-8">
              {STATUS_FILTERS.map((f) => (
                <TabsTrigger key={f.value || 'all'} value={f.value || 'all'} className="text-xs px-3">
                  {t(f.labelKey)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <Tabs
            value={sourceFilter || 'all'}
            onValueChange={(v) => setSourceFilter(v === 'all' ? '' : (v as RunSource))}
          >
            <TabsList className="h-8">
              {SOURCE_FILTERS.map((f) => (
                <TabsTrigger key={f.value || 'all'} value={f.value || 'all'} className="text-xs px-3">
                  {t(f.labelKey)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        {degraded && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            {t('degradedBanner')}
          </div>
        )}

        {loading && runs.length === 0 && !loadError ? (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex gap-3 p-3 rounded-lg border border-border/30 bg-card/50">
                <Skeleton className="h-4 w-4 rounded-full shrink-0 mt-0.5" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-4 w-1/3" />
                  <Skeleton className="h-3 w-2/3" />
                </div>
              </div>
            ))}
          </div>
        ) : loadError && runs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <XCircle className="h-10 w-10 mb-3 text-red-500/70 dark:text-red-400/70" />
            <p className="text-sm text-red-600/90 dark:text-red-300/90">{t('loadError')}</p>
            <Button variant="outline" size="sm" className="mt-4" onClick={reload} disabled={loading}>
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
              {t('retry')}
            </Button>
          </div>
        ) : runs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <Clock className="h-10 w-10 mb-3 opacity-30" />
            <p className="text-sm">{t(hasActiveFilter ? 'emptyFiltered' : 'empty')}</p>
          </div>
        ) : (
          <div className={cn('space-y-1.5', loading && 'opacity-50 pointer-events-none')}>
            {runs.map((run) => (
              <RunRow key={run.id} run={run} t={t} />
            ))}
          </div>
        )}

        {hasMore && (
          <div className="flex justify-center pt-2">
            <Button variant="ghost" size="sm" onClick={loadMore} disabled={loading}>
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
              {t('loadMore')}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function RunRow({ run, t }: { run: UnifiedRun; t: ReturnType<typeof useTranslations> }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = !!(run.output || run.error || run.has_execution_steps);

  return (
    <div
      className={cn(
        'rounded-lg border border-border/20 bg-card/30 transition-colors',
        hasDetail && 'cursor-pointer hover:bg-card/60',
      )}
      onClick={hasDetail ? () => setExpanded(!expanded) : undefined}
    >
      <div className="flex items-start gap-3 px-3 py-2.5">
        <div className="mt-0.5 shrink-0">{STATUS_ICON[run.status]}</div>
        <div className="flex-1 min-w-0 space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground truncate">{run.title}</span>
            <span
              className={cn(
                'shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium',
                SOURCE_COLORS[run.source],
              )}
            >
              {t(SOURCE_LABEL_KEY[run.source])}
            </span>
            {run.has_execution_steps && (
              <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                {t('executionStepsBadge')}
              </span>
            )}
          </div>
          {!expanded && run.error && (
            <p className="text-[11px] text-red-500/80 dark:text-red-400/80 font-mono truncate">{run.error}</p>
          )}
          {!expanded && !run.error && run.summary && (
            <p className="text-[11px] text-muted-foreground truncate">{run.summary}</p>
          )}
        </div>
        <div className="shrink-0 flex flex-col items-end gap-0.5">
          <span className="text-[10px] text-muted-foreground">{formatRelativeTime(run.started_at, t)}</span>
          {run.duration_ms != null && (
            <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
              <Timer className="h-2.5 w-2.5" />
              {formatDuration(run.duration_ms)}
            </span>
          )}
          {hasDetail && (
            expanded ? <ChevronUp className="h-3 w-3 text-muted-foreground" /> : <ChevronDown className="h-3 w-3 text-muted-foreground" />
          )}
        </div>
      </div>

      {expanded && (
        <div className="px-3 pb-3 pt-0 space-y-2 border-t border-border/10 mt-0">
          {run.output && (
            <pre className="text-xs text-muted-foreground bg-muted/30 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap break-words font-mono max-h-48 overflow-y-auto">
              {run.output}
            </pre>
          )}
          {run.error && (
            <pre className="text-xs text-red-500/80 dark:text-red-400/80 bg-red-500/5 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap break-words max-h-32 overflow-y-auto">
              {run.error}
            </pre>
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
                      <span className={cn(
                        'h-1.5 w-1.5 rounded-full shrink-0',
                        step.error ? 'bg-red-400' : 'bg-emerald-400',
                      )} />
                      <span className="font-mono text-foreground/80 truncate">
                        {step.tool_name || step.step_key || `step ${idx + 1}`}
                      </span>
                      {step.error && (
                        <span className="text-red-400 truncate ml-1">{step.error}</span>
                      )}
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
