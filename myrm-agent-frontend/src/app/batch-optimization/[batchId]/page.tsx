'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { localizeReactNode } from '@/lib/utils/localeText';
import { Loader2, ArrowLeft, Clock, CheckCircle2, XCircle, AlertCircle, Activity, FileText } from 'lucide-react';
import { apiRequest } from '@/lib/api';
import {
  cancelBatchTask,
  rollbackBatchTask,
  type BatchCancelCleanupStrategy,
} from '@/services/skill-optimization';
import { toast } from '@/hooks/useToast';
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
import {
  BatchTaskDetailItem,
  formatDateTime,
  formatDuration,
  formatDurationSeconds,
  formatTokenCount,
  getBatchProgress,
  isBatchTerminalStatus,
  normalizeBatchStatus,
} from '@/lib/batch-optimization';

const BatchDetailPage = () => {
  const locale = useLocale();
  const tBatch = useTranslations('settings.skillOptimization.batchPage');
  const isChinese = locale.startsWith('zh');
  const params = useParams();
  const router = useRouter();
  const batchId = params.batchId as string;

  const [task, setTask] = useState<BatchTaskDetailItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const hasLoadedTaskRef = useRef(false);

  const fetchTaskDetail = useCallback(
    async ({ notifyOnError = true }: { notifyOnError?: boolean } = {}) => {
      try {
        const data = await apiRequest<BatchTaskDetailItem>(`/batch-optimization/tasks/${batchId}`);
        setTask(data);
        hasLoadedTaskRef.current = true;
        setError(null);
      } catch (err) {
        if (notifyOnError || !hasLoadedTaskRef.current) {
          setError(err instanceof Error ? err.message : 'Unknown error');
        } else {
          console.error('Error refreshing batch task detail:', err);
        }
      } finally {
        setLoading(false);
      }
    },
    [batchId],
  );

  const handleRollback = useCallback(async () => {
    setIsRollingBack(true);
    try {
      const result = await rollbackBatchTask(batchId);
      if (result.success) {
        toast({ title: tBatch('rollbackSuccess', { count: result.rolled_back }) });
        await fetchTaskDetail();
      } else {
        toast({ title: tBatch('rollbackFailed'), variant: 'destructive' });
      }
    } catch {
      toast({ title: tBatch('rollbackFailed'), variant: 'destructive' });
    } finally {
      setIsRollingBack(false);
    }
  }, [batchId, fetchTaskDetail, tBatch]);

  const handleCancel = useCallback(
    async (cleanupStrategy: BatchCancelCleanupStrategy) => {
      setIsCancelling(true);
      try {
        const result = await cancelBatchTask(batchId, cleanupStrategy);
        if (cleanupStrategy === 'rollback') {
          if (result.rollback_performed) {
            toast({ title: tBatch('cancelRollbackSuccess', { count: result.rolled_back }) });
          } else if (result.rolled_back > 0) {
            toast({
              title: tBatch('cancelRollbackPartial', {
                rolled: result.rolled_back,
                failed: result.failed,
                total: result.total_skills,
              }),
              variant: 'destructive',
            });
          } else {
            toast({ title: tBatch('cancelRollbackFailed'), variant: 'destructive' });
          }
        } else {
          toast({ title: tBatch('cancelSuccess') });
        }
        await fetchTaskDetail();
      } catch {
        toast({ title: tBatch('cancelFailed'), variant: 'destructive' });
      } finally {
        setIsCancelling(false);
      }
    },
    [batchId, fetchTaskDetail, tBatch],
  );

  useEffect(() => {
    void fetchTaskDetail();
  }, [fetchTaskDetail]);

  useEffect(() => {
    if (!task || isBatchTerminalStatus(task.status)) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void fetchTaskDetail({ notifyOnError: false });
    }, 5000);

    return () => window.clearInterval(intervalId);
  }, [fetchTaskDetail, task]);

  const progressPercent = task ? getBatchProgress(task.completed_tasks, task.total_tasks) : 0;

  const getStatusBadge = (status: string) => {
    switch (normalizeBatchStatus(status)) {
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
            <Activity className="size-3 mr-1" />
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
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto h-full py-6 px-4 md:px-6">
        <Card className="border-primary/10">
          <CardContent className="flex min-h-[50vh] items-center justify-center">
            <Loader2 className="size-8 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error || !task) {
    return (
      <div className="container mx-auto h-full py-6 px-4 md:px-6">
        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-red-600">
              <XCircle className="size-5" />
              Error Loading Batch Task / 加载批量任务失败
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground mb-4">{error || 'Batch task not found'}</p>
            <Button onClick={() => router.push('/batch-optimization')}>
              <ArrowLeft className="size-4 mr-2" />
              Back to List / 返回列表
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const lastActivityLabel = formatDateTime(task.completed_at ?? task.started_at ?? task.created_at);
  const executionLabel = formatDurationSeconds(task.total_execution_time);
  const averageExecutionLabel = formatDurationSeconds(task.total_execution_time / Math.max(task.total_tasks, 1));
  const tokenLabel = formatTokenCount(task.total_token_consumption);
  const taskCountText = isChinese
    ? `${task.completed_tasks} / ${task.total_tasks} 个子任务`
    : `${task.completed_tasks} / ${task.total_tasks} tasks`;
  const averageExecutionText = isChinese ? `平均耗时 ${averageExecutionLabel}` : `Average ${averageExecutionLabel}`;
  const tokenMetricLabel = isChinese ? '令牌消耗' : 'Tokens / Token consumption';
  const terminalState = isBatchTerminalStatus(task.status);

  return localizeReactNode(
    <div className="container mx-auto h-full space-y-6 px-4 py-6 md:px-6">
      <div className="flex items-center justify-between gap-4">
        <Button variant="ghost" onClick={() => router.push('/batch-optimization')} className="px-0">
          <ArrowLeft className="size-4 mr-2" />
          Back to List / 返回列表
        </Button>
        {getStatusBadge(task.status)}
      </div>

      <Card className="overflow-hidden border-primary/10 bg-gradient-to-br from-primary/10 via-background to-background">
        <CardContent className="space-y-6 p-6 md:p-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="font-mono">
                  {batchId.substring(0, 12)}...
                </Badge>
                <Badge variant={terminalState ? 'secondary' : 'default'}>
                  {terminalState ? 'Terminal / 已结束' : 'Live / 实时'}
                </Badge>
              </div>
              <div className="space-y-2">
                <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">Batch Task Details / 批量任务详情</h1>
                <p className="max-w-3xl text-sm text-muted-foreground md:text-base">
                  Detailed information and audit logs for this batch task / 查看该批量任务的详细信息和审计日志
                </p>
              </div>
            </div>

            <div className="rounded-2xl border bg-background/80 px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Last activity / 最近活动</p>
              <p className="mt-1 text-sm font-medium">{lastActivityLabel}</p>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Card className="border-primary/10 bg-background/80">
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Status / 状态</p>
                <div className="mt-3">{getStatusBadge(task.status)}</div>
              </CardContent>
            </Card>
            <Card className="border-primary/10 bg-background/80">
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Progress / 进度</p>
                <p className="mt-2 text-2xl font-semibold">{progressPercent}%</p>
                <p className="mt-2 text-xs text-muted-foreground">{taskCountText}</p>
              </CardContent>
            </Card>
            <Card className="border-primary/10 bg-background/80">
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Performance / 性能</p>
                <p className="mt-2 text-2xl font-semibold">{executionLabel}</p>
                <p className="mt-2 text-xs text-muted-foreground">{averageExecutionText}</p>
              </CardContent>
            </Card>
            <Card className="border-primary/10 bg-background/80">
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">{tokenMetricLabel}</p>
                <p className="mt-2 text-2xl font-semibold">{tokenLabel}</p>
                <p className="mt-2 text-xs text-muted-foreground">{task.skill_ids.ids.length} skills / 技能</p>
              </CardContent>
            </Card>
          </div>
        </CardContent>
      </Card>

      <Card className="border-primary/10">
        <CardHeader>
          <CardTitle>Basic Information / 基本信息</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div>
              <dt className="text-sm font-medium text-muted-foreground">Batch ID</dt>
              <dd className="mt-1 break-all text-sm font-mono">{task.batch_id}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">Priority / 优先级</dt>
              <dd className="mt-1 text-sm">{task.priority > 0 ? task.priority : 'Default / 默认'}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">Created At / 创建时间</dt>
              <dd className="mt-1 text-sm">{formatDateTime(task.created_at)}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">Started At / 开始时间</dt>
              <dd className="mt-1 text-sm">{formatDateTime(task.started_at)}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">Completed At / 完成时间</dt>
              <dd className="mt-1 text-sm">{formatDateTime(task.completed_at)}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">Duration / 持续时间</dt>
              <dd className="mt-1 text-sm">{formatDuration(task.started_at, task.completed_at)}</dd>
            </div>
            <div className="xl:col-span-3">
              <dt className="text-sm font-medium text-muted-foreground">Skill IDs ({task.skill_ids.ids.length})</dt>
              <dd className="mt-1 break-all text-sm font-mono">{task.skill_ids.ids.join(', ')}</dd>
            </div>
            {task.error_message && (
              <div className="xl:col-span-3">
                <dt className="text-sm font-medium text-red-600">Error Message / 错误信息</dt>
                <dd className="mt-1 text-sm text-red-600">{task.error_message}</dd>
              </div>
            )}
          </dl>
        </CardContent>
      </Card>

      {!terminalState && (
        <Card className="border-destructive/20">
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>{tBatch('cancel')}</CardTitle>
              <CardDescription>{tBatch('cancelConfirmDescription')}</CardDescription>
            </div>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" disabled={isCancelling}>
                  {isCancelling ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
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
                      void handleCancel('rollback');
                    }}
                  >
                    {tBatch('cancelRollbackAction')}
                  </AlertDialogAction>
                  <AlertDialogAction
                    disabled={isCancelling}
                    className="border border-input bg-background hover:bg-accent hover:text-accent-foreground"
                    onClick={(event) => {
                      event.preventDefault();
                      void handleCancel('keep');
                    }}
                  >
                    {tBatch('cancelKeepAction')}
                  </AlertDialogAction>
                  <AlertDialogCancel>{tBatch('submitCancel')}</AlertDialogCancel>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </CardHeader>
        </Card>
      )}

      <Card className="border-primary/10">
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>{tBatch('rollback')}</CardTitle>
            <CardDescription>{tBatch('rollbackCardDescription')}</CardDescription>
          </div>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" disabled={isRollingBack || !terminalState}>
                {isRollingBack ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {tBatch('rollback')}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-md">
              <AlertDialogHeader>
                <AlertDialogTitle>{tBatch('rollbackConfirmTitle')}</AlertDialogTitle>
                <AlertDialogDescription>{tBatch('rollbackConfirmDescription')}</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-2">
                <AlertDialogCancel>{tBatch('submitCancel')}</AlertDialogCancel>
                <AlertDialogAction
                  disabled={isRollingBack}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  onClick={() => void handleRollback()}
                >
                  {tBatch('rollback')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardHeader>
      </Card>

      <Card className="border-primary/10">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="size-5" />
            Audit Logs / 审计日志
          </CardTitle>
          <CardDescription>Timeline of all operations for this batch task / 该批量任务的所有操作时间线</CardDescription>
        </CardHeader>
        <CardContent>
          {task.audit_logs.length === 0 ? (
            <p className="rounded-xl border border-dashed bg-muted/20 py-10 text-center text-muted-foreground">
              No audit logs available / 暂无审计日志
            </p>
          ) : (
            <div className="space-y-4">
              {task.audit_logs.map((log, index) => (
                <div
                  key={`${log.operation}-${log.created_at}-${index}`}
                  className="flex gap-4 rounded-xl border bg-background/70 p-4"
                >
                  <div className="flex-shrink-0 pt-1">
                    {log.status === 'success' ? (
                      <CheckCircle2 className="size-5 text-emerald-600" />
                    ) : log.status === 'failure' ? (
                      <XCircle className="size-5 text-red-600" />
                    ) : (
                      <Activity className="size-5 text-blue-600" />
                    )}
                  </div>
                  <div className="flex-1 space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium">{log.operation}</span>
                      {getStatusBadge(log.status)}
                    </div>
                    <p className="text-xs text-muted-foreground">{formatDateTime(log.created_at)}</p>
                    {Object.keys(log.details).length > 0 && (
                      <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs">
                        {JSON.stringify(log.details, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>,
    locale,
  );
};

export default BatchDetailPage;
