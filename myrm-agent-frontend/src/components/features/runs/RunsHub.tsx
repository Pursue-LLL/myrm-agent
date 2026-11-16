'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Clock, XCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { Skeleton } from '@/components/primitives/skeleton';
import { listUnifiedRuns, type UnifiedRun, type RunSource, type RunStatus } from '@/services/runs';
import { RunRow } from './RunRow';

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
  useEffect(() => {
    tRef.current = t;
  }, [t]);
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
    async (offset: number, append: boolean, silent = false) => {
      const requestSeq = ++requestSeqRef.current;
      if (!silent) {
        setLoading(true);
      }
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
        if (silent) {
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
        if (!silent && requestSeq === requestSeqRef.current) {
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
    // oxlint-disable-next-line react/set-state-in-effect -- changing a filter starts the list request; the loading and error flags only mirror that in-flight fetch
    void fetchRuns(0, false);
  }, [fetchRuns]);

  // Live-refresh list while any run is in progress so status/progress stay current.
  const hasRunning = runs.some((r) => r.status === 'running');
  useEffect(() => {
    if (!hasRunning) {
      return;
    }
    const interval = setInterval(() => {
      // silent keeps the current scroll/loadMore position and avoids a loading flicker.
      void fetchRuns(offsetRef.current, false, true);
    }, 30_000);
    return () => clearInterval(interval);
  }, [hasRunning, fetchRuns]);

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
