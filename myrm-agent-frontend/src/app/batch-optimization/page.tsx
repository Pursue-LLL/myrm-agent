'use client';

import { useCallback, useEffect, useMemo, useState, type ElementType } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { Skeleton } from '@/components/primitives/skeleton';
import { Badge } from '@/components/primitives/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/primitives/table';
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock,
  Database,
  Filter,
  Loader2,
  Play,
  Plus,
  Pause,
  RefreshCw,
  Search,
  Wifi,
  WifiOff,
  XCircle,
} from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/primitives/alert-dialog';
import { apiRequest } from '@/lib/api';
import { cancelBatchTask, type BatchCancelCleanupStrategy } from '@/services/skill-optimization';
import { localizeReactNode, selectLocalizedText } from '@/lib/utils/localeText';
import { toast } from '@/hooks/useToast';
import { useBatchWebSocket, BatchProgressUpdate } from '@/hooks/useBatchWebSocket';
import {
  BatchStatusFilter,
  BatchTaskListItem,
  buildBatchTaskStats,
  formatDateTime,
  formatDurationSeconds,
  formatTokenCount,
  getBatchProgress,
  matchesBatchStatusFilter,
  normalizeBatchStatus,
  parseSkillIds,
} from '@/lib/batch-optimization';

interface BatchTaskRowProps {
  task: BatchTaskListItem;
  cancellingBatchId: string | null;
  onUpdate: (batchId: string, update: Partial<BatchTaskListItem>) => void;
  onCancel: (batchId: string, cleanupStrategy: BatchCancelCleanupStrategy) => void;
}

const BatchTaskRow = ({ task, cancellingBatchId, onUpdate, onCancel }: BatchTaskRowProps) => {
  const locale = useLocale();
  const tBatch = useTranslations('settings.skillOptimization.batchPage');
  const isChinese = locale.startsWith('zh');
  const normalizedStatus = normalizeBatchStatus(task.status);
  const isRunning = normalizedStatus === 'running';
  const canCancel = normalizedStatus === 'running' || normalizedStatus === 'pending';
  const isCancelling = cancellingBatchId === task.batch_id;
  const progress = getBatchProgress(task.completed_tasks, task.total_tasks);
  const skillCount = task.skill_ids.ids.length;
  const maxConcurrent = task.max_concurrent ?? 3;
  const taskCountText = isChinese
    ? `${task.completed_tasks} / ${task.total_tasks} 个任务`
    : `${task.completed_tasks} / ${task.total_tasks} tasks`;
  const skillCountText = isChinese ? `${skillCount} 项技能` : `${skillCount} skills`;
  const failedText = isChinese ? `${task.failed_tasks} 次失败` : `${task.failed_tasks} failed`;
  const concurrentText = isChinese ? `${maxConcurrent} 并发` : `${maxConcurrent} concurrent`;

  const handleProgress = (update: BatchProgressUpdate) => {
    onUpdate(task.batch_id, {
      completed_tasks: update.completed,
      failed_tasks: update.failed,
      status: update.status || task.status,
    });
  };

  const handleComplete = (update: BatchProgressUpdate) => {
    onUpdate(task.batch_id, {
      completed_tasks: update.completed,
      failed_tasks: update.failed,
      status: 'completed',
    });
  };

  const { isConnected } = useBatchWebSocket({
    batchId: isRunning ? task.batch_id : '',
    onProgress: handleProgress,
    onComplete: handleComplete,
  });

  const getStatusBadge = () => {
    switch (normalizedStatus) {
      case 'pending':
        return (
          <Badge variant="secondary" className="whitespace-nowrap">
            <Clock className="size-3 mr-1" />
            {tBatch('statusPending')}
          </Badge>
        );
      case 'running':
        return (
          <Badge variant="default" className="whitespace-nowrap">
            {isConnected ? <Wifi className="size-3 mr-1" /> : <WifiOff className="size-3 mr-1" />}
            {tBatch('statusRunning')}
          </Badge>
        );
      case 'completed':
        return (
          <Badge variant="default" className="bg-emerald-600 whitespace-nowrap">
            <CheckCircle2 className="size-3 mr-1" />
            {tBatch('statusCompleted')}
          </Badge>
        );
      case 'cancelled':
        return (
          <Badge variant="destructive" className="whitespace-nowrap">
            <XCircle className="size-3 mr-1" />
            {tBatch('statusCancelled')}
          </Badge>
        );
      case 'failure':
        return (
          <Badge variant="destructive" className="whitespace-nowrap">
            <AlertCircle className="size-3 mr-1" />
            {tBatch('statusFailed')}
          </Badge>
        );
      default:
        return <Badge variant="secondary">{task.status}</Badge>;
    }
  };

  return localizeReactNode(
    <TableRow className="align-top">
      <TableCell className="space-y-2">
        <Link
          href={`/batch-optimization/${task.batch_id}`}
          className="font-mono text-sm font-medium text-primary transition-colors hover:text-primary/80 hover:underline"
        >
          {task.batch_id.substring(0, 12)}...
        </Link>
        <p className="text-xs text-muted-foreground">{formatDateTime(task.created_at)}</p>
      </TableCell>
      <TableCell className="align-top">{getStatusBadge()}</TableCell>
      <TableCell className="min-w-[240px]">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">{progress}%</span>
            <span className="text-muted-foreground">{taskCountText}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>{skillCountText}</span>
            <span>{failedText}</span>
            <span>{formatTokenCount(task.total_token_consumption)} tokens</span>
          </div>
        </div>
      </TableCell>
      <TableCell className="space-y-1 text-sm">
        <div>{concurrentText}</div>
        <div className="text-xs text-muted-foreground">
          {task.priority > 0 ? `Priority ${task.priority} / 优先级 ${task.priority}` : 'Default priority / 默认优先级'}
        </div>
      </TableCell>
      <TableCell className="space-y-1 text-sm">
        <div>{formatDurationSeconds(task.total_execution_time)}</div>
        <div className="text-xs text-muted-foreground">
          {task.status === 'running' && task.estimated_completion_time
            ? `ETA ${formatDateTime(task.estimated_completion_time)}`
            : task.completed_at
              ? `Completed ${formatDateTime(task.completed_at)}`
              : 'Waiting for completion / 等待完成'}
        </div>
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href={`/batch-optimization/${task.batch_id}`}>
              View / 详情
              <ArrowRight className="size-3" />
            </Link>
          </Button>
          {canCancel && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm" disabled={isCancelling}>
                  {isCancelling ? <Loader2 className="size-3 animate-spin" /> : <Pause className="size-3" />}
                  {tBatch('cancel')}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-md">
                <AlertDialogHeader>
                  <AlertDialogTitle>{tBatch('cancelConfirmTitle')}</AlertDialogTitle>
                  <AlertDialogDescription>{tBatch('cancelConfirmDescription')}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter className="flex-col gap-2 sm:flex-col">
                  <AlertDialogAction
                    disabled={isCancelling}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    onClick={(event) => {
                      event.preventDefault();
                      void onCancel(task.batch_id, 'rollback');
                    }}
                  >
                    {tBatch('cancelRollbackAction')}
                  </AlertDialogAction>
                  <AlertDialogAction
                    disabled={isCancelling}
                    className="border border-input bg-background hover:bg-accent hover:text-accent-foreground"
                    onClick={(event) => {
                      event.preventDefault();
                      void onCancel(task.batch_id, 'keep');
                    }}
                  >
                    {tBatch('cancelKeepAction')}
                  </AlertDialogAction>
                  <AlertDialogCancel>{tBatch('submitCancel')}</AlertDialogCancel>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </TableCell>
    </TableRow>,
    locale,
  );
};

function BatchMetricCard({
  icon: Icon,
  label,
  value,
  helper,
}: {
  icon: ElementType;
  label: string;
  value: string;
  helper: string;
}) {
  return (
    <Card className="border-primary/10 bg-background/80">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">{label}</p>
            <p className="text-2xl font-semibold tracking-tight">{value}</p>
            <p className="text-xs text-muted-foreground">{helper}</p>
          </div>
          <div className="rounded-full bg-primary/10 p-2 text-primary">
            <Icon className="size-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function BatchLoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Card key={index} className="border-primary/10">
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-3">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-8 w-20" />
                  <Skeleton className="h-3 w-32" />
                </div>
                <Skeleton className="h-10 w-10 rounded-full" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader className="space-y-3">
          <Skeleton className="h-6 w-44" />
          <Skeleton className="h-4 w-72" />
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <Skeleton className="h-10 flex-1" />
            <Skeleton className="h-10 w-64" />
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-20 w-full rounded-xl" />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function BatchEmptyState({
  title,
  description,
  actionLabel,
  onAction,
  icon: Icon,
}: {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  icon: ElementType;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed bg-muted/20 px-6 py-14 text-center">
      <div className="mb-4 rounded-full bg-primary/10 p-4 text-primary">
        <Icon className="size-8" />
      </div>
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="mt-2 max-w-xl text-sm text-muted-foreground">{description}</p>
      <Button className="mt-6" onClick={onAction}>
        {actionLabel}
      </Button>
    </div>
  );
}

const parseIntegerInput = (value: string, fallback: number, minimum: number): number => {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) {
    return fallback;
  }

  return Math.max(minimum, parsed);
};

const BatchOptimizationPage = () => {
  const locale = useLocale();
  const tBatch = useTranslations('settings.skillOptimization.batchPage');
  const text = useCallback((value: string) => selectLocalizedText(value, locale), [locale]);
  const isChinese = locale.startsWith('zh');
  const [tasks, setTasks] = useState<BatchTaskListItem[]>([]);
  const [cancellingBatchId, setCancellingBatchId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'tasks' | 'create'>('tasks');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<BatchStatusFilter>('all');
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [skillIds, setSkillIds] = useState('');
  const [priority, setPriority] = useState(0);
  const [maxConcurrent, setMaxConcurrent] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  const stats = useMemo(() => buildBatchTaskStats(tasks), [tasks]);

  const visibleTasks = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    return tasks.filter(
      (task) =>
        matchesBatchStatusFilter(task.status, statusFilter) &&
        (query.length === 0 ||
          task.batch_id.toLowerCase().includes(query) ||
          task.status.toLowerCase().includes(query) ||
          task.skill_ids.ids.join(' ').toLowerCase().includes(query)),
    );
  }, [searchQuery, statusFilter, tasks]);

  const fetchTasks = useCallback(
    async ({
      mode = 'refresh',
      notifyOnError = true,
    }: { mode?: 'initial' | 'refresh'; notifyOnError?: boolean } = {}) => {
      if (mode === 'initial') {
        setInitialLoading(true);
      } else {
        setRefreshing(true);
      }

      try {
        const data = await apiRequest<{ tasks: BatchTaskListItem[]; count: number }>('/batch-optimization/tasks');
        setTasks(data.tasks || []);
        setLastUpdatedAt(new Date().toLocaleTimeString());
        setLoadError(null);
      } catch (error) {
        console.error('Error fetching batch tasks:', error);
        if (mode === 'initial') {
          setLoadError(error instanceof Error ? error.message : 'Unknown error');
        }
        if (notifyOnError) {
          toast.error(text('Failed to load batch tasks / 加载批量任务失败'));
        }
      } finally {
        if (mode === 'initial') {
          setInitialLoading(false);
        } else {
          setRefreshing(false);
        }
      }
    },
    [text],
  );

  useEffect(() => {
    void fetchTasks({ mode: 'initial' });
  }, [fetchTasks]);

  useEffect(() => {
    if (activeTab !== 'tasks') {
      return;
    }

    const intervalId = window.setInterval(() => {
      void fetchTasks({ notifyOnError: false });
    }, 10000);

    return () => window.clearInterval(intervalId);
  }, [activeTab, fetchTasks]);

  const handleTaskUpdate = useCallback((batchId: string, update: Partial<BatchTaskListItem>) => {
    setTasks((prev) => prev.map((task) => (task.batch_id === batchId ? { ...task, ...update } : task)));
  }, []);

  const handleSubmitBatch = useCallback(async () => {
    const ids = parseSkillIds(skillIds);

    if (ids.length === 0) {
      toast.error(text('Please enter at least one skill ID / 请至少输入一个技能 ID'));
      return;
    }

    setSubmitting(true);
    try {
      const response = await apiRequest<{
        batch_id: string;
        status: string;
        total_tasks: number;
        estimated_seconds: number;
        estimated_completion: string;
        confidence: number;
      }>('/batch-optimization/tasks', {
        method: 'POST',
        body: JSON.stringify({
          skill_ids: ids,
          priority,
          max_concurrent: maxConcurrent,
        }),
      });

      toast.success(text(`Batch ${response.batch_id.substring(0, 12)}... submitted / 批量任务已提交`));
      setSkillIds('');
      setPriority(0);
      setMaxConcurrent(3);
      setActiveTab('tasks');
      await fetchTasks();
    } catch (error) {
      console.error('Error submitting batch:', error);
      toast.error(text('Failed to submit batch / 提交批量任务失败'));
    } finally {
      setSubmitting(false);
    }
  }, [fetchTasks, maxConcurrent, priority, skillIds, text]);

  const handleCancelBatch = useCallback(
    async (batchId: string, cleanupStrategy: BatchCancelCleanupStrategy) => {
      setCancellingBatchId(batchId);
      try {
        const result = await cancelBatchTask(batchId, cleanupStrategy);

        if (cleanupStrategy === 'rollback') {
          if (result.rollback_performed) {
            toast.success(tBatch('cancelRollbackSuccess', { count: result.rolled_back }));
          } else if (result.rolled_back > 0) {
            toast.error(
              tBatch('cancelRollbackPartial', {
                rolled: result.rolled_back,
                failed: result.failed,
                total: result.total_skills,
              }),
            );
          } else {
            toast.error(tBatch('cancelRollbackFailed'));
          }
        } else {
          toast.success(tBatch('cancelSuccess'));
        }
        await fetchTasks();
      } catch (error) {
        console.error('Error cancelling batch:', error);
        toast.error(tBatch('cancelFailed'));
      } finally {
        setCancellingBatchId(null);
      }
    },
    [fetchTasks, tBatch],
  );

  const refreshLabel = refreshing
    ? 'Refreshing / 刷新中'
    : lastUpdatedAt
      ? `Updated ${lastUpdatedAt} / 最近更新 ${lastUpdatedAt}`
      : 'Waiting for sync / 等待同步';

  const statusFilters: Array<{ value: BatchStatusFilter; label: string; count: number }> = [
    { value: 'all', label: tBatch('filterAll'), count: stats.totalBatches },
    { value: 'active', label: tBatch('filterActive'), count: stats.activeBatches },
    { value: 'pending', label: tBatch('statusPending'), count: stats.pendingBatches },
    { value: 'running', label: tBatch('filterExecuting'), count: stats.runningBatches },
    { value: 'completed', label: tBatch('statusCompleted'), count: stats.completedBatches },
    { value: 'failure', label: tBatch('statusFailed'), count: stats.failedBatches },
    { value: 'cancelled', label: tBatch('statusCancelled'), count: stats.cancelledBatches },
  ];

  const summaryCards = [
    {
      icon: BarChart3,
      label: 'Batch Count / 批次总数',
      value: `${stats.totalBatches}`,
      helper: lastUpdatedAt
        ? isChinese
          ? `最近同步 ${lastUpdatedAt}`
          : `Last synced ${lastUpdatedAt}`
        : isChinese
          ? '实时概览'
          : 'Live overview',
    },
    {
      icon: Activity,
      label: 'Active / 运行中',
      value: `${stats.activeBatches}`,
      helper: isChinese
        ? `排队 ${stats.pendingBatches} · 运行 ${stats.runningBatches}`
        : `Pending ${stats.pendingBatches} · Running ${stats.runningBatches}`,
    },
    {
      icon: CheckCircle2,
      label: 'Progress / 总进度',
      value: `${stats.overallProgress}%`,
      helper: isChinese
        ? `已完成 ${stats.completedTasks}/${stats.totalTasks} 个子任务`
        : `${stats.completedTasks}/${stats.totalTasks} subtasks complete`,
    },
    {
      icon: Database,
      label: isChinese ? '令牌消耗' : 'Tokens / Token consumption',
      value: formatTokenCount(stats.totalTokens),
      helper: isChinese
        ? `总耗时 ${formatDurationSeconds(stats.totalExecutionSeconds)}`
        : `${formatDurationSeconds(stats.totalExecutionSeconds)} total execution`,
    },
  ] as const;

  const handleSearchClear = () => {
    setSearchQuery('');
    setStatusFilter('all');
  };

  return localizeReactNode(
    <div className="container mx-auto h-full space-y-6 px-4 py-6 md:px-6">
      <Card className="overflow-hidden border-primary/10 bg-gradient-to-br from-primary/10 via-background to-background">
        <CardContent className="space-y-6 p-6 md:p-8">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={stats.activeBatches > 0 ? 'default' : 'secondary'} className="gap-1.5">
                  <IconGlow className="size-3.5" />
                  {stats.activeBatches > 0 ? 'Live tracking / 实时追踪' : 'Ready to launch / 准备就绪'}
                </Badge>
                <Badge variant="outline" className="gap-1.5">
                  <Clock className="size-3.5" />
                  Auto refresh every 10s / 每 10 秒自动刷新
                </Badge>
              </div>
              <div className="space-y-2">
                <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">Batch Optimization / 批量优化</h1>
                <p className="max-w-3xl text-sm text-muted-foreground md:text-base">
                  Manage batch skill optimization tasks with real-time progress tracking /
                  管理批量技能优化任务并实时跟踪进度
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <Button variant="outline" onClick={() => void fetchTasks()} disabled={refreshing || initialLoading}>
                <RefreshCw className={`size-4 ${refreshing ? 'animate-spin' : ''}`} />
                Refresh / 刷新
              </Button>
              <Button onClick={() => setActiveTab('create')}>
                <Play className="size-4" />
                Create Batch / 创建批量任务
              </Button>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {summaryCards.map((card) => (
              <BatchMetricCard
                key={card.label}
                icon={card.icon}
                label={card.label}
                value={card.value}
                helper={card.helper}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as 'tasks' | 'create')} className="w-full">
        <TabsList className="grid w-full grid-cols-2 h-auto bg-muted p-1 md:w-fit">
          <TabsTrigger key="tasks" value="tasks" className="gap-2 min-w-0">
            <Activity className="size-4 shrink-0" />
            <span className="truncate">Active Tasks / 运行中任务</span>
          </TabsTrigger>
          <TabsTrigger key="create" value="create" className="gap-2 min-w-0">
            <Plus className="size-4 shrink-0" />
            <span className="truncate">Create Batch / 创建批量任务</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="tasks" className="space-y-6">
          <Card className="border-primary/10">
            <CardHeader className="space-y-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-2">
                  <CardTitle className="text-xl">Batch Tasks / 批量任务</CardTitle>
                  <CardDescription>
                    Real-time status of all batch optimization tasks / 所有批量优化任务的实时状态
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2 self-start">
                  <Badge variant="secondary" className="gap-1.5 whitespace-nowrap">
                    <Clock className="size-3.5" />
                    {refreshLabel}
                  </Badge>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void fetchTasks()}
                    disabled={refreshing || initialLoading}
                  >
                    <RefreshCw className={`size-4 ${refreshing ? 'animate-spin' : ''}`} />
                    Refresh / 刷新
                  </Button>
                </div>
              </div>

              <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto]">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder="Search by batch id or skill id / 按批次ID或技能ID搜索"
                    className="pl-9"
                  />
                </div>

                <div className="flex flex-wrap gap-2">
                  {statusFilters.map((filterItem) => (
                    <Button
                      key={filterItem.value}
                      size="sm"
                      variant={statusFilter === filterItem.value ? 'default' : 'outline'}
                      onClick={() => setStatusFilter(filterItem.value)}
                      className="gap-2"
                    >
                      <Filter className="size-3.5" />
                      <span>{filterItem.label}</span>
                      <span className="rounded-full bg-background/10 px-2 py-0.5 text-[11px] font-semibold">
                        {filterItem.count}
                      </span>
                    </Button>
                  ))}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {initialLoading ? (
                <BatchLoadingSkeleton />
              ) : loadError && tasks.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-red-200 bg-red-50/40 px-6 py-12 text-center dark:border-red-900/50 dark:bg-red-950/10">
                  <div className="mb-4 rounded-full bg-red-100 p-4 text-red-600 dark:bg-red-950/40">
                    <XCircle className="size-8" />
                  </div>
                  <h3 className="text-lg font-semibold text-red-700 dark:text-red-300">
                    Failed to load tasks / 加载任务失败
                  </h3>
                  <p className="mt-2 max-w-xl text-sm text-red-600/80 dark:text-red-300/80">{loadError}</p>
                  <div className="mt-6 flex flex-wrap justify-center gap-3">
                    <Button variant="outline" onClick={() => void fetchTasks({ mode: 'initial' })}>
                      Retry / 重试
                    </Button>
                    <Button onClick={() => setActiveTab('create')}>Create Batch / 创建批量任务</Button>
                  </div>
                </div>
              ) : tasks.length === 0 ? (
                <BatchEmptyState
                  title="No batch tasks yet / 还没有批量任务"
                  description="Create a batch to start tracking live optimization progress. You can monitor status, progress, and execution metrics in one place. / 创建一个批量任务即可开始追踪实时优化进度。你可以在一个页面里查看状态、进度和执行指标。"
                  actionLabel="Create Batch / 创建批量任务"
                  onAction={() => setActiveTab('create')}
                  icon={IconGlow}
                />
              ) : visibleTasks.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed bg-muted/20 px-6 py-12 text-center">
                  <h3 className="text-lg font-semibold">No matching tasks / 没有匹配的任务</h3>
                  <p className="mt-2 max-w-xl text-sm text-muted-foreground">
                    Clear the current search or status filter to view all tasks. /
                    清除当前搜索或状态筛选即可查看全部任务。
                  </p>
                  <div className="mt-6 flex flex-wrap justify-center gap-3">
                    <Button variant="outline" onClick={handleSearchClear}>
                      Clear Filters / 清除筛选
                    </Button>
                    <Button onClick={() => setActiveTab('create')}>Create Batch / 创建批量任务</Button>
                  </div>
                </div>
              ) : (
                <div className="overflow-x-auto rounded-2xl border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Batch / 批次</TableHead>
                        <TableHead>Status / 状态</TableHead>
                        <TableHead>Progress / 进度</TableHead>
                        <TableHead>Capacity / 容量</TableHead>
                        <TableHead>Duration / 耗时</TableHead>
                        <TableHead>Actions / 操作</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {visibleTasks.map((task) => (
                        <BatchTaskRow
                          key={task.batch_id}
                          task={task}
                          cancellingBatchId={cancellingBatchId}
                          onUpdate={handleTaskUpdate}
                          onCancel={handleCancelBatch}
                        />
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="create" className="space-y-6">
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
            <Card className="border-primary/10">
              <CardHeader>
                <CardTitle>Create Batch Task / 创建批量任务</CardTitle>
                <CardDescription>
                  Submit multiple skills for optimization in a single batch / 一次性提交多个技能进行批量优化
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="space-y-2">
                  <label htmlFor="batch-skill-ids" className="text-sm font-medium">
                    Skill IDs / 技能ID
                  </label>
                  <Textarea
                    id="batch-skill-ids"
                    value={skillIds}
                    onChange={(event) => setSkillIds(event.target.value)}
                    placeholder={'skill-1, skill-2, skill-3\nskill-4\nskill-5'}
                    className="min-h-36 font-mono"
                  />
                  <p className="text-xs text-muted-foreground">
                    Supports comma, newline, semicolon and Chinese punctuation / 支持逗号、换行、分号和中文标点
                  </p>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <label htmlFor="batch-priority" className="text-sm font-medium">
                      Priority / 优先级
                    </label>
                    <Input
                      id="batch-priority"
                      type="number"
                      min="0"
                      value={priority}
                      onChange={(event) => setPriority(parseIntegerInput(event.target.value, 0, 0))}
                    />
                    <p className="text-xs text-muted-foreground">Higher priority runs sooner / 优先级越高越先执行</p>
                  </div>

                  <div className="space-y-2">
                    <label htmlFor="batch-max-concurrent" className="text-sm font-medium">
                      Max Concurrent / 最大并发数
                    </label>
                    <Input
                      id="batch-max-concurrent"
                      type="number"
                      min="1"
                      max="10"
                      value={maxConcurrent}
                      onChange={(event) => setMaxConcurrent(parseIntegerInput(event.target.value, 3, 1))}
                    />
                    <p className="text-xs text-muted-foreground">
                      Balance throughput and resource usage / 平衡吞吐与资源占用
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary">Comma / 逗号</Badge>
                  <Badge variant="secondary">New line / 换行</Badge>
                  <Badge variant="secondary">Semicolon / 分号</Badge>
                </div>

                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button disabled={submitting} className="w-full">
                      {submitting ? (
                        <>
                          <Loader2 className="size-4 animate-spin" />
                          Submitting / 提交中...
                        </>
                      ) : (
                        <>
                          <Play className="size-4" />
                          Submit Batch / 提交批量任务
                        </>
                      )}
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-md">
                    <AlertDialogHeader>
                      <AlertDialogTitle>{tBatch('submitConfirmTitle')}</AlertDialogTitle>
                      <AlertDialogDescription>{tBatch('submitConfirmDescription')}</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-2">
                      <AlertDialogCancel>{tBatch('submitCancel')}</AlertDialogCancel>
                      <AlertDialogAction disabled={submitting} onClick={() => void handleSubmitBatch()}>
                        {tBatch('submitConfirmAction')}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </CardContent>
            </Card>

            <Card className="border-primary/10 bg-muted/20">
              <CardHeader>
                <CardTitle>How it works / 使用方式</CardTitle>
                <CardDescription>
                  Keep batches easy to read and easy to monitor / 让批量任务更易读、更易追踪
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="space-y-3">
                  {[
                    {
                      title: '1. Paste skill IDs / 粘贴技能 ID',
                      description: 'Use comma, newline, or semicolon separators. / 可使用逗号、换行或分号分隔。',
                    },
                    {
                      title: '2. Tune execution settings / 调整执行参数',
                      description:
                        'Priority controls order and max concurrency controls throughput. / 优先级控制执行顺序，并发控制吞吐。',
                    },
                    {
                      title: '3. Monitor live progress / 追踪实时进度',
                      description:
                        'Switch back to Active Tasks to watch progress, ETA, and execution metrics. / 切回运行中任务即可查看进度、ETA 和执行指标。',
                    },
                  ].map((step) => (
                    <div key={step.title} className="rounded-xl border bg-background/80 p-4">
                      <p className="text-sm font-semibold">{step.title}</p>
                      <p className="mt-2 text-sm text-muted-foreground">{step.description}</p>
                    </div>
                  ))}
                </div>

                <div className="rounded-xl border bg-background/80 p-4">
                  <p className="text-sm font-semibold">Example / 示例</p>
                  <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-muted p-3 text-xs font-mono text-muted-foreground">
                    skill-alpha{'\n'}skill-beta{'\n'}skill-gamma
                  </pre>
                </div>

                <p className="text-sm text-muted-foreground">
                  After submission, the page will switch back to the live task list so you can see the new batch
                  immediately. / 提交后页面会自动切回实时任务列表，方便立即查看新批次。
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>,
    locale,
  );
};

export default BatchOptimizationPage;
