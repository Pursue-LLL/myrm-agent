'use client';

import { useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import useCronStore from '@/store/useCronStore';
import CronRunItem from './CronRunItem';

const STATUS_FILTERS = [
  { value: null, labelKey: 'filterAll' },
  { value: 'ok', labelKey: 'filterOk' },
  { value: 'skipped', labelKey: 'filterSkipped' },
  { value: 'error', labelKey: 'filterError' },
] as const;

export default function GlobalRunHistory() {
  const t = useTranslations('cron');
  const {
    allRuns,
    allRunsLoading,
    allRunsHasMore,
    allRunsTotal,
    allRunsStatusFilter,
    fetchAllRuns,
    setAllRunsStatusFilter,
  } = useCronStore();

  useEffect(() => {
    fetchAllRuns();
  }, [fetchAllRuns]);

  const handleFilterChange = useCallback(
    (status: string | null) => {
      setAllRunsStatusFilter(status);
      fetchAllRuns({ status: status ?? undefined });
    },
    [fetchAllRuns, setAllRunsStatusFilter],
  );

  const loadMore = useCallback(() => {
    fetchAllRuns({ append: true });
  }, [fetchAllRuns]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <Tabs value={allRunsStatusFilter ?? 'all'} onValueChange={(v) => handleFilterChange(v === 'all' ? null : v)}>
          <TabsList className="h-8">
            {STATUS_FILTERS.map((f) => (
              <TabsTrigger key={f.value ?? 'all'} value={f.value ?? 'all'} className="text-xs px-3">
                {t(f.labelKey)}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        {allRunsTotal > 0 && (
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {allRunsTotal} {t('totalRuns')}
          </span>
        )}
      </div>

      {allRunsLoading && allRuns.length === 0 ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex gap-3">
              <Skeleton className="h-3 w-3 rounded-full shrink-0" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-3 w-2/3" />
              </div>
            </div>
          ))}
        </div>
      ) : allRuns.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">{t('noRuns')}</p>
      ) : (
        <div className="space-y-0">
          {allRuns.map((run, idx) => (
            <CronRunItem key={run.id} run={run} isLast={!allRunsHasMore && idx === allRuns.length - 1} showJobName />
          ))}
        </div>
      )}

      {allRunsHasMore && (
        <div className="flex justify-center pt-2">
          <Button variant="ghost" size="sm" onClick={loadMore} disabled={allRunsLoading}>
            {allRunsLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
            {t('loadMore')}
          </Button>
        </div>
      )}
    </div>
  );
}
