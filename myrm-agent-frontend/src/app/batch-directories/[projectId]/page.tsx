'use client';

/**
 * Batch directory parallel prompt runner — project detail.
 *
 * [INPUT]
 * - @/services/batch-directory::* (POS: 批量目录 API 服务层)
 *
 * [OUTPUT]
 * - BatchProjectDetailPage: 批量项目详情 + 任务聚合视图
 *
 * [POS]
 * BatchDirectory 详情页。展示项目进度、目录清单、任务状态聚合与失败详情。
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import Link from 'next/link';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Progress } from '@/components/primitives/progress';
import { Skeleton } from '@/components/primitives/skeleton';
import { Badge } from '@/components/primitives/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/primitives/table';
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
  CheckCircle2,
  ChevronLeft,
  Clock,
  FolderOpen,
  Loader2,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { toast } from '@/hooks/shared/useToast';
import { cn } from '@/lib/utils/classnameUtils';
import {
  cancelBatchProject,
  deleteBatchProject,
  getBatchProject,
  isBatchTerminalStatus,
  type BatchProjectDetail,
} from '@/services/batch-directory';

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

export default function BatchProjectDetailPage({ params }: { params: Promise<{ projectId: string }> }) {
  const t = useTranslations('batchDirectory');
  const locale = useLocale();
  const router = useRouter();
  const isChinese = locale.startsWith('zh');

  const [projectId, setProjectId] = useState<string | null>(null);
  const [project, setProject] = useState<BatchProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    let active = true;
    void params.then((p) => {
      if (active) setProjectId(p.projectId);
    });
    return () => {
      active = false;
    };
  }, [params]);

  const fetchDetail = useCallback(
    async (id: string) => {
      try {
        const detail = await getBatchProject(id);
        setProject(detail);
      } catch {
        toast.error(t('detailLoadError'));
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (projectId) void fetchDetail(projectId);
  }, [projectId, fetchDetail]);

  // 运行中每 10s 自动刷新进度
  useEffect(() => {
    if (!projectId || !project || isBatchTerminalStatus(project.status)) return;
    const timer = window.setInterval(() => {
      void fetchDetail(projectId);
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [projectId, project, fetchDetail]);

  const handleCancel = useCallback(async () => {
    if (!projectId) return;
    setCancelling(true);
    try {
      await cancelBatchProject(projectId);
      toast.success(t('cancelSuccess', { name: project?.name ?? '' }));
      setConfirmCancel(false);
      await fetchDetail(projectId);
    } catch {
      toast.error(t('cancelError'));
    } finally {
      setCancelling(false);
    }
  }, [projectId, project?.name, fetchDetail, t]);

  const handleDelete = useCallback(async () => {
    if (!projectId) return;
    try {
      await deleteBatchProject(projectId);
      toast.success(t('deleteSuccess', { name: project?.name ?? '' }));
      router.push('/batch-directories');
    } catch {
      toast.error(t('deleteError'));
    }
  }, [projectId, project?.name, router, t]);

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

  const total = project.total_tasks || 0;
  const done = project.completed_tasks + project.failed_tasks;
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);
  const running = project.status === 'running';

  const statusLabel = (status: string) => {
    switch (status) {
      case 'running':
        return <Badge className="border-muted bg-muted/50 text-foreground">{t('statusRunning')}</Badge>;
      case 'completed':
        return <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600">{t('statusCompleted')}</Badge>;
      case 'failed':
        return <Badge className="border-destructive/30 bg-destructive/10 text-destructive">{t('statusFailed')}</Badge>;
      case 'cancelled':
        return <Badge className="border-muted bg-muted/50 text-muted-foreground">{t('statusCancelled')}</Badge>;
      default:
        return <Badge className="border-muted bg-muted/50 text-muted-foreground">{t('statusDraft')}</Badge>;
    }
  };

  const taskStatusMeta = (status: string) => {
    switch (status) {
      case 'completed':
        return {
          icon: <CheckCircle2 className="size-3.5 text-emerald-500" />,
          className: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600',
        };
      case 'failed':
        return {
          icon: <XCircle className="size-3.5 text-destructive" />,
          className: 'border-destructive/30 bg-destructive/10 text-destructive',
        };
      case 'running':
        return {
          icon: <Loader2 className="size-3.5 animate-spin" />,
          className: 'border-muted bg-muted/50 text-foreground',
        };
      default:
        return {
          icon: <Clock className="size-3.5" />,
          className: 'border-muted bg-muted/50 text-muted-foreground',
        };
    }
  };

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push('/batch-directories')} aria-label={t('backToList')}>
            <ChevronLeft className="size-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
            <p className="text-sm text-muted-foreground mt-1 flex items-center gap-2">
              {statusLabel(project.status)}
              <span className="text-xs">{t('projectIdLabel', { id: project.project_id })}</span>
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => fetchDetail(project.project_id)}>
            <RefreshCw className="size-4 mr-1" />
            {t('refresh')}
          </Button>
          {running && (
            <AlertDialog open={confirmCancel} onOpenChange={setConfirmCancel}>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" disabled={cancelling}>
                  {cancelling ? <Loader2 className="size-4 mr-1 animate-spin" /> : null}
                  {t('cancelAction')}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t('confirmCancelTitle', { name: project.name })}</AlertDialogTitle>
                  <AlertDialogDescription>{t('confirmCancelDescription')}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t('cancelButton')}</AlertDialogCancel>
                  <AlertDialogAction onClick={() => void handleCancel()}>{t('confirmCancelAction')}</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
          {!running && (
            <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="sm" className="text-destructive">
                  <XCircle className="size-4 mr-1" />
                  {t('deleteAction')}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t('confirmDeleteTitle', { name: project.name })}</AlertDialogTitle>
                  <AlertDialogDescription>{t('confirmDeleteDescription')}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t('cancelButton')}</AlertDialogCancel>
                  <AlertDialogAction onClick={() => void handleDelete()} className="bg-destructive text-destructive-foreground">
                    {t('confirmDeleteAction')}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('overviewTitle')}</CardTitle>
            <CardDescription>{t('overviewDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{t('statProgress')}</span>
              <span className="font-medium">
                {done}/{total} ({percent}%)
              </span>
            </div>
            <Progress value={percent} />
            <div className="grid grid-cols-3 gap-2 pt-1">
              <div className="rounded-md border p-3 text-center">
                <p className="text-xl font-semibold">{total}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{t('statTotalTasks')}</p>
              </div>
              <div className="rounded-md border p-3 text-center">
                <p className="text-xl font-semibold text-emerald-500">{project.completed_tasks}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{t('statCompleted')}</p>
              </div>
              <div className="rounded-md border p-3 text-center">
                <p className="text-xl font-semibold text-destructive">{project.failed_tasks}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{t('statFailed')}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('configTitle')}</CardTitle>
            <CardDescription>{t('configDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground shrink-0">{t('configBoard')}</span>
              <span className="truncate font-mono text-xs">
                {project.board_id ? (
                  <Link href={`/work`} className="hover:underline">
                    {project.board_id}
                  </Link>
                ) : (
                  '—'
                )}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground shrink-0">{t('configConcurrency')}</span>
              <span className="font-mono">{project.concurrency}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground shrink-0">{t('configAgent')}</span>
              <span className="truncate font-mono text-xs">{project.agent_id || '—'}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground shrink-0">{t('configNotify')}</span>
              <span>{project.notify_enabled ? t('configEnabled') : t('configDisabled')}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground shrink-0">{t('configCreated')}</span>
              <span className="text-xs">{formatDateTime(project.created_at)}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground shrink-0">{t('configFinished')}</span>
              <span className="text-xs">{formatDateTime(project.finished_at)}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {project.prompt && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">{t('promptTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap text-muted-foreground">{project.prompt}</p>
          </CardContent>
        </Card>
      )}

      {project.artifact_patterns.length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">{t('artifactsTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {project.artifact_patterns.map((pattern) => (
                <Badge key={pattern} variant="outline" className="font-mono">
                  {pattern}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('directoriesTitle')}</CardTitle>
          <CardDescription>
            {isChinese
              ? `共 ${project.directories.length} 个目标目录`
              : `${project.directories.length} target director${project.directories.length > 1 ? 'ies' : 'y'}`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {project.directories.map((dir) => {
              const failed = project.failed_directories?.includes(dir);
              return (
                <span
                  key={dir}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-mono',
                    failed
                      ? 'border-destructive/30 bg-destructive/10 text-destructive'
                      : 'border-muted bg-muted/40 text-foreground',
                  )}
                >
                  {failed ? <XCircle className="size-3" /> : <FolderOpen className="size-3" />}
                  <span className="max-w-64 truncate">{dir}</span>
                </span>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">{t('tasksTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('tableName')}</TableHead>
                <TableHead>{t('tableStatus')}</TableHead>
                <TableHead>{t('tableDirectory')}</TableHead>
                <TableHead>{t('tableResult')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {project.tasks.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center py-10 text-muted-foreground">
                    {t('emptyTasks')}
                  </TableCell>
                </TableRow>
              )}
              {project.tasks.map((task) => {
                const meta = taskStatusMeta(task.status);
                const isFailed = task.status === 'failed';
                return (
                  <TableRow key={task.task_id}>
                    <TableCell className="font-medium max-w-56">
                      <span className="truncate block">{task.title}</span>
                    </TableCell>
                    <TableCell>
                      <Badge className={meta.className}>
                        {meta.icon}
                        {task.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground font-mono max-w-56">
                      <span className="truncate block">{task.workspace_path || '—'}</span>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {isFailed ? (
                        <span className="text-destructive block max-w-72 truncate" title={task.error}>
                          {task.error || t('taskFailedUnknown')}
                        </span>
                      ) : task.status === 'completed' ? (
                        <span className="block max-w-72 truncate" title={task.result}>
                          {task.result || t('taskCompletedNoResult')}
                        </span>
                      ) : (
                        <span className="block max-w-72 truncate">{t('taskPending')}</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {!isBatchTerminalStatus(project.status) && (
        <p className="text-center text-xs text-muted-foreground mt-6">{t('autoRefreshHint')}</p>
      )}
    </div>
  );
}
