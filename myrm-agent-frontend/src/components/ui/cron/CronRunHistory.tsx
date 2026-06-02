'use client';

/**
 * [INPUT]
 * @/store/useCronStore (POS: Cron frontend state store)
 * @/services/cron (POS: Frontend Cron API client and CronJob type definitions)
 * @/components/ui/memory/SharedContextTargetBinding (POS: Shared Context runtime binding component)
 *
 * [OUTPUT]
 * CronRunHistory: Single cron job detail, editor, Shared Context binding, and run history view.
 *
 * [POS]
 * Cron task detail surface. It exposes per-job operational controls and inherited Shared Contexts.
 */

import { useCallback, useEffect, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowLeft, CheckCircle2, Clock, Activity, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils/classnameUtils';
import useCronStore from '@/store/useCronStore';
import type { CronJob } from '@/services/cron';
import { computeRunStats, formatDuration, STATUS_BADGE_STYLE, STATUS_DOT_COLOR } from './cron-utils';
import CronRunItem from './CronRunItem';
import { DeliveryEditor, FailureDeliveryEditor } from './CronDeliveryEditors';
import { IncrementalMonitorEditor } from './CronMonitorEditors';
import {
  CooldownEditor,
  MaxFiresEditor,
  ExpiresAtEditor,
  SessionTargetEditor,
  FailureAlertEditor,
  RunRetentionEditor,
  SkipIfActiveEditor,
  ContextFromEditor,
  PreConditionEditor,
} from './CronAdvancedEditors';
import { ActiveHoursEditor } from './ActiveHoursEditor';
import { CapabilityEditor } from './CapabilityEditor';
import { AllowedRootsEditor } from './AllowedRootsEditor';
import { TriggerEditor } from './CronTriggerEditor';
import { SharedContextTargetBinding } from '@/components/ui/memory/SharedContextTargetBinding';

interface CronRunHistoryProps {
  job: CronJob;
  onBack: () => void;
}

const STATUS_FILTERS = [
  { value: null, labelKey: 'filterAll' },
  { value: 'ok', labelKey: 'filterOk' },
  { value: 'skipped', labelKey: 'filterSkipped' },
  { value: 'error', labelKey: 'filterError' },
] as const;

function RunStatsSummary({
  stats,
  t,
}: {
  stats: { total: number; successRate: number; avgDuration: number };
  t: (key: string) => string;
}) {
  if (stats.total === 0) return null;

  return (
    <div className="flex items-center gap-4 rounded-lg border bg-card px-4 py-2.5 flex-wrap">
      <div className="flex items-center gap-1.5 text-xs">
        <Activity className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-muted-foreground">{t('totalRuns')}</span>
        <span className="font-medium">{stats.total}</span>
      </div>
      <div className="flex items-center gap-1.5 text-xs">
        <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
        <span className="text-muted-foreground">{t('successRate')}</span>
        <span className="font-medium">{stats.successRate}%</span>
      </div>
      <div className="flex items-center gap-1.5 text-xs">
        <Clock className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-muted-foreground">{t('avgDuration')}</span>
        <span className="font-medium">{formatDuration(stats.avgDuration)}</span>
      </div>
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-10 w-full rounded-lg" />
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
  );
}

export default function CronRunHistory({ job, onBack }: CronRunHistoryProps) {
  const t = useTranslations('cron');
  const { runs, runsLoading, runsHasMore, runsTotal, runsStatusFilter, fetchRuns, fetchJobs, setRunsStatusFilter } =
    useCronStore();

  useEffect(() => {
    fetchRuns(job.id);
  }, [job.id, fetchRuns]);

  const handleFilterChange = useCallback(
    (status: string | null) => {
      setRunsStatusFilter(status);
      fetchRuns(job.id, { status: status ?? undefined });
    },
    [job.id, fetchRuns, setRunsStatusFilter],
  );

  const loadMore = useCallback(() => {
    fetchRuns(job.id, { append: true });
  }, [job.id, fetchRuns]);

  const stats = useMemo(() => computeRunStats(runs), [runs]);

  const statusLabel: Record<string, string> = {
    active: t('statusActive'),
    paused: t('statusPaused'),
    completed: t('statusCompleted'),
  };

  const handleEditorUpdated = useCallback(() => {
    fetchRuns(job.id);
    fetchJobs(true);
  }, [job.id, fetchRuns, fetchJobs]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button size="icon" variant="ghost" className="h-7 w-7 shrink-0" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h3 className="text-sm font-medium truncate">{job.name}</h3>
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium leading-tight shrink-0',
            STATUS_BADGE_STYLE[job.status] ?? 'bg-muted text-muted-foreground border-muted',
          )}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full', STATUS_DOT_COLOR[job.status] ?? 'bg-muted-foreground/50')} />
          {statusLabel[job.status] ?? job.status}
        </span>
        <span className="text-xs text-muted-foreground ml-auto shrink-0">
          {runsTotal > 0 ? `${runsTotal} ${t('runHistory')}` : t('runHistory')}
        </span>
      </div>

      <Tabs value={runsStatusFilter ?? 'all'} onValueChange={(v) => handleFilterChange(v === 'all' ? null : v)}>
        <TabsList className="h-8">
          {STATUS_FILTERS.map((f) => (
            <TabsTrigger key={f.value ?? 'all'} value={f.value ?? 'all'} className="text-xs px-3">
              {t(f.labelKey)}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <TriggerEditor job={job} onUpdated={handleEditorUpdated} />
      <DeliveryEditor job={job} onUpdated={handleEditorUpdated} />
      <FailureDeliveryEditor job={job} onUpdated={handleEditorUpdated} />
      <FailureAlertEditor job={job} onUpdated={handleEditorUpdated} />
      <IncrementalMonitorEditor job={job} onUpdated={handleEditorUpdated} />
      <SessionTargetEditor job={job} onUpdated={handleEditorUpdated} />
      <SkipIfActiveEditor job={job} onUpdated={handleEditorUpdated} />
      <ContextFromEditor job={job} onUpdated={handleEditorUpdated} />
      <PreConditionEditor job={job} onUpdated={handleEditorUpdated} />
      <CooldownEditor job={job} onUpdated={handleEditorUpdated} />
      <MaxFiresEditor job={job} onUpdated={handleEditorUpdated} />
      <ExpiresAtEditor job={job} onUpdated={handleEditorUpdated} />
      <RunRetentionEditor job={job} onUpdated={handleEditorUpdated} />
      <ActiveHoursEditor job={job} onUpdated={handleEditorUpdated} />
      {job.job_type === 'agent' && (
        <SharedContextTargetBinding
          targetType="cron"
          targetId={job.id}
          targetLabel={t('sharedContexts.targetLabel')}
          compact
        />
      )}
      {job.job_type === 'agent' && <CapabilityEditor job={job} onUpdated={handleEditorUpdated} />}
      {job.job_type === 'agent' && <AllowedRootsEditor job={job} onUpdated={handleEditorUpdated} />}

      {job.last_error && (
        <div className="rounded-full border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {t('lastError')}: {job.last_error}
        </div>
      )}

      {runsLoading && runs.length === 0 ? (
        <HistorySkeleton />
      ) : (
        <>
          <RunStatsSummary stats={stats} t={t} />

          {runs.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">{t('noRuns')}</p>
          ) : (
            <div className="space-y-0">
              {runs.map((run, idx) => (
                <CronRunItem key={run.id} run={run} isLast={!runsHasMore && idx === runs.length - 1} />
              ))}
            </div>
          )}

          {runsHasMore && (
            <div className="flex justify-center pt-2">
              <Button variant="ghost" size="sm" onClick={loadMore} disabled={runsLoading}>
                {runsLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
                {t('loadMore')}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
