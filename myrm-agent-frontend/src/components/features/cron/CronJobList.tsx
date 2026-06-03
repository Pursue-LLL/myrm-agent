'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Search, Timer, RefreshCw, Plus } from 'lucide-react';
import { Input } from '@/components/primitives/input';
import { Button } from '@/components/primitives/button';
import { Skeleton } from '@/components/primitives/skeleton';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { toast } from 'sonner';
import useCronStore from '@/store/useCronStore';
import type { CronJob } from '@/services/cron';
import { computeStats, filterJobs, type StatusFilter } from './cron-utils';
import CronStatsBar from './CronStatsBar';
import CronJobCard from './CronJobCard';
import CronJobCreateDialog from './CronJobCreateDialog';

interface CronJobListProps {
  onSelectJob: (job: CronJob) => void;
}

function JobListSkeleton() {
  return (
    <div className="space-y-2">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex items-start gap-3 rounded-lg border px-3 py-2.5">
          <Skeleton className="h-4 w-4 mt-0.5 rounded" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-2/3" />
            <Skeleton className="h-3 w-1/4" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ t }: { t: (key: string) => string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="rounded-full bg-muted p-4 mb-4">
        <Timer className="h-8 w-8 text-muted-foreground" />
      </div>
      <h3 className="text-sm font-medium mb-1">{t('emptyTitle')}</h3>
      <p className="text-xs text-muted-foreground max-w-[240px]">{t('emptyDesc')}</p>
    </div>
  );
}

export default function CronJobList({ onSelectJob }: CronJobListProps) {
  const t = useTranslations('cron');
  const { jobs, loading, fetchJobs, deleteJob } = useCronStore();
  const [filter, setFilter] = useState<StatusFilter>('all');
  const [query, setQuery] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<CronJob | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    fetchJobs(true);
  }, [fetchJobs]);

  const stats = useMemo(() => computeStats(jobs), [jobs]);
  const filtered = useMemo(() => filterJobs(jobs, filter, query), [jobs, filter, query]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetchJobs(true);
    } finally {
      setRefreshing(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteJob(deleteTarget.id);
      toast.success(t('deleteSuccess', { name: deleteTarget.name }));
    } catch {
      toast.error(t('actionFail'));
    }
    setDeleteTarget(null);
  };

  if (loading) return <JobListSkeleton />;

  return (
    <div className="space-y-4">
      <CronStatsBar stats={stats} activeFilter={filter} onFilterChange={setFilter} />

      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder={t('searchPlaceholder')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
        </div>
        <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={handleRefresh} disabled={refreshing}>
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
        </Button>
        <Button variant="default" size="sm" className="h-8 gap-1 text-xs shrink-0" onClick={() => setCreateOpen(true)}>
          <Plus className="h-3.5 w-3.5" />
          {t('createBtn')}
        </Button>
      </div>

      {filtered.length === 0 ? (
        jobs.length === 0 ? (
          <EmptyState t={t} />
        ) : (
          <p className="text-sm text-muted-foreground text-center py-8">{t('empty')}</p>
        )
      ) : (
        <div className="space-y-2">
          {filtered.map((job) => (
            <CronJobCard key={job.id} job={job} onSelect={onSelectJob} onRequestDelete={setDeleteTarget} />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={t('deleteConfirmTitle')}
        description={(() => {
          const base = t('deleteConfirm', { name: deleteTarget?.name ?? '' });
          if (!deleteTarget) return base;
          const dependents = jobs.filter((j) => j.context_from?.includes(deleteTarget.id));
          if (dependents.length === 0) return base;
          const names = dependents.map((j) => j.name).join(', ');
          return `${base}\n\n${t('deleteContextFromWarning', { names })}`;
        })()}
        confirmText={t('delete')}
        cancelText={t('cancel')}
        variant="destructive"
        onConfirm={handleDelete}
      />

      <CronJobCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
