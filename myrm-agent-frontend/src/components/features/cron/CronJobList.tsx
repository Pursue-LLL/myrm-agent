'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { Search, Timer, RefreshCw, Plus, Sparkles } from 'lucide-react';
import { Input } from '@/components/primitives/input';
import { Button } from '@/components/primitives/button';
import { Skeleton } from '@/components/primitives/skeleton';
import { EmptyState as StandardEmptyState } from '@/components/primitives/empty-state';
import { ListSkeleton } from '@/components/primitives/skeleton-templates';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { toast } from 'sonner';
import useCronStore from '@/store/useCronStore';
import { getCronJob } from '@/services/cron';
import type { CronJob } from '@/services/cron';
import { computeStats, filterJobs, type StatusFilter } from './cron-utils';
import CronStatsBar from './CronStatsBar';
import CronJobCard from './CronJobCard';
import CronJobCreateDialog from './CronJobCreateDialog';
import BlueprintCatalog from './BlueprintCatalog';
import BlueprintFillDialog from './BlueprintFillDialog';
import SchedulerHealthBadge from './SchedulerHealthBadge';
import type { CronBlueprint } from './cron-blueprints';
import { useSearchParams } from 'next/navigation';

interface CronJobListProps {
  onSelectJob: (job: CronJob) => void;
}

function JobListSkeleton() {
  return <ListSkeleton count={3} />;
}

function EmptyState({
  t,
  onSelectBlueprint,
}: {
  t: (key: string) => string;
  onSelectBlueprint: (bp: CronBlueprint) => void;
}) {
  return (
    <StandardEmptyState
      icon={Timer}
      title={t('emptyTitle')}
      description={t('emptyDesc')}
      className="py-6"
      action={
        <div className="w-full max-w-md pt-2">
          <p className="text-xs font-medium text-muted-foreground mb-2 text-left">{t('blueprint.quickStart')}</p>
          <BlueprintCatalog onSelect={onSelectBlueprint} maxItems={4} />
        </div>
      }
    />
  );
}

export default function CronJobList({ onSelectJob }: CronJobListProps) {
  const t = useTranslations('cron');
  const searchParams = useSearchParams();
  const chatIdFilter = searchParams.get('chat_id')?.trim() || undefined;
  const jobIdFilter = searchParams.get('job')?.trim() || undefined;
  const { jobs, loading, fetchJobs, deleteJob } = useCronStore();
  const [filter, setFilter] = useState<StatusFilter>('all');
  const [query, setQuery] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<CronJob | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedBlueprint, setSelectedBlueprint] = useState<CronBlueprint | null>(null);
  const openedJobRef = useRef<string | null>(null);

  useEffect(() => {
    fetchJobs(true, chatIdFilter);
  }, [fetchJobs, chatIdFilter]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState !== 'visible') {
        return;
      }
      void fetchJobs(true, chatIdFilter);
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [fetchJobs, chatIdFilter]);

  useEffect(() => {
    openedJobRef.current = null;
  }, [jobIdFilter]);

  useEffect(() => {
    if (!jobIdFilter || loading) {
      return;
    }
    if (openedJobRef.current === jobIdFilter) {
      return;
    }
    const matched = jobs.find((entry) => entry.id === jobIdFilter);
    if (matched) {
      openedJobRef.current = jobIdFilter;
      onSelectJob(matched);
      return;
    }
    let cancelled = false;
    void getCronJob(jobIdFilter)
      .then((job) => {
        if (!cancelled) {
          openedJobRef.current = jobIdFilter;
          onSelectJob(job);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [jobIdFilter, jobs, loading, onSelectJob]);

  const stats = useMemo(() => computeStats(jobs), [jobs]);
  const filtered = useMemo(() => filterJobs(jobs, filter, query), [jobs, filter, query]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetchJobs(true, chatIdFilter);
    } finally {
      setRefreshing(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    try {
      await deleteJob(deleteTarget.id);
      toast.success(t('deleteSuccess', { name: deleteTarget.name }));
    } catch {
      toast.error(t('actionFail'));
    }
    setDeleteTarget(null);
  };

  if (loading) {
    return <JobListSkeleton />;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <CronStatsBar stats={stats} activeFilter={filter} onFilterChange={setFilter} />
        <div className="flex items-center gap-2 shrink-0">
          <Link
            href="/settings/evolutionPending?growthType=cron_suggestion"
            className="inline-flex items-center gap-1 rounded-md border border-border/70 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground hover:border-primary/30"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {t('suggestionsLink')}
          </Link>
          <SchedulerHealthBadge />
        </div>
      </div>

      {chatIdFilter ? (
        <p className="text-xs text-muted-foreground">{t('filteredByChat', { chatId: chatIdFilter.slice(0, 8) })}</p>
      ) : null}

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
          <EmptyState t={t} onSelectBlueprint={setSelectedBlueprint} />
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
          if (!open) {
            setDeleteTarget(null);
          }
        }}
        title={t('deleteConfirmTitle')}
        description={(() => {
          const base = t('deleteConfirm', { name: deleteTarget?.name ?? '' });
          if (!deleteTarget) {
            return base;
          }
          const dependents = jobs.filter((j) => j.context_from?.includes(deleteTarget.id));
          if (dependents.length === 0) {
            return base;
          }
          const names = dependents.map((j) => j.name).join(', ');
          return `${base}\n\n${t('deleteContextFromWarning', { names })}`;
        })()}
        confirmText={t('delete')}
        cancelText={t('cancel')}
        variant="destructive"
        onConfirm={handleDelete}
      />

      <CronJobCreateDialog open={createOpen} onOpenChange={setCreateOpen} presetChatId={chatIdFilter ?? null} />

      <BlueprintFillDialog
        blueprint={selectedBlueprint}
        open={!!selectedBlueprint}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedBlueprint(null);
          }
        }}
      />
    </div>
  );
}
