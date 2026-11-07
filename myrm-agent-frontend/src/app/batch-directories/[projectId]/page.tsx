'use client';

/**
 * Batch directory parallel prompt runner — project detail.
 *
 * [INPUT]
 * - @/components/features/batch-directory (POS: 详情页各区块与数据 / 动作 hooks)
 *
 * [OUTPUT]
 * - BatchProjectDetailPage: 批量项目详情 + 任务聚合视图
 *
 * [POS]
 * BatchDirectory 详情页薄壳。装配头部动作栏、进度概览、范围卡片与任务表；非终态项目每 10 秒自动刷新。
 */

import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { ChevronLeft, Clock } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Skeleton } from '@/components/primitives/skeleton';
import { BatchProjectHeader } from '@/components/features/batch-directory/BatchProjectHeader';
import { BatchProjectOverview } from '@/components/features/batch-directory/BatchProjectOverview';
import { BatchProjectScope } from '@/components/features/batch-directory/BatchProjectScope';
import { BatchTaskTable } from '@/components/features/batch-directory/BatchTaskTable';
import { deriveProjectFlags } from '@/components/features/batch-directory/batchProjectModel';
import { useBatchProjectActions } from '@/components/features/batch-directory/useBatchProjectActions';
import { useBatchProjectDetail } from '@/components/features/batch-directory/useBatchProjectDetail';

export default function BatchProjectDetailPage({ params }: { params: Promise<{ projectId: string }> }) {
  const t = useTranslations('batchDirectory');
  const router = useRouter();
  const { projectId, project, loading, refresh } = useBatchProjectDetail(params);
  const actions = useBatchProjectActions({ projectId, projectName: project?.name ?? '', refresh });

  if (loading) {
    return (
      <div className="container mx-auto max-w-5xl px-4 py-8 space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="container mx-auto max-w-5xl px-4 py-8">
        <p className="text-muted-foreground">{t('notFound')}</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push('/batch-directories')}>
          <ChevronLeft className="size-4 mr-1" />
          {t('backToList')}
        </Button>
      </div>
    );
  }

  const flags = deriveProjectFlags(project);

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <BatchProjectHeader project={project} flags={flags} actions={actions} onRefresh={refresh} />

      {flags.paused && (
        <div className="mb-6 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-600">
          <Clock className="size-4 mt-0.5 shrink-0" />
          <span>{t('pausedHint', { count: project.tasks.filter((task) => task.status === 'blocked').length })}</span>
        </div>
      )}

      <BatchProjectOverview project={project} />
      <BatchProjectScope project={project} />
      <BatchTaskTable
        tasks={project.tasks}
        retryingTaskId={actions.retryingTaskId}
        retryLocked={actions.busy.retry || actions.busy.rerun}
        onRetryTask={actions.retryTask}
      />

      {!flags.terminal && <p className="text-center text-xs text-muted-foreground mt-6">{t('autoRefreshHint')}</p>}
    </div>
  );
}
