'use client';

/**
 * [INPUT] ./batchProjectModel::isTaskRetryable (POS: 任务可重试判定), ./BatchStatusBadges::BatchTaskStatusBadge (POS: 任务状态徽标), ./BatchConfirmAlert (POS: 二次确认弹窗)
 * [OUTPUT] BatchTaskTable: 详情页的任务表（标题、状态、目录、结果摘要、单任务重试）
 * [POS] 任务聚合视图；结果列按状态展示失败原因 / 产物校验结果 / 完成摘要，失败、已归档或产物缺失的任务可单独重试。
 */

import { useTranslations } from 'next-intl';
import { CheckCircle2, Loader2, RotateCcw, XCircle } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/primitives/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/primitives/table';
import type { BatchTaskItem } from '@/services/batch-directory';
import { BatchConfirmAlert } from './BatchConfirmAlert';
import { BatchTaskStatusBadge } from './BatchStatusBadges';
import { isTaskRetryable } from './batchProjectModel';

function TaskResult({ task }: { task: BatchTaskItem }) {
  const t = useTranslations('batchDirectory');

  if (task.status === 'failed') {
    return (
      <span className="text-destructive-text block max-w-72 truncate" title={task.error}>
        {task.error || t('taskFailedUnknown')}
      </span>
    );
  }
  if (task.status !== 'completed') {
    return <span className="block max-w-72 truncate">{t('taskPending')}</span>;
  }
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      {task.artifact_status === 'verified' && (
        <span className="inline-flex items-center gap-1 text-emerald-600 shrink-0">
          <CheckCircle2 className="size-3.5" />
          {t('artifactVerified')}
        </span>
      )}
      {task.artifact_status === 'missing' && (
        <span className="inline-flex items-center gap-1 text-destructive-text shrink-0">
          <XCircle className="size-3.5" />
          {t('artifactMissing')}
        </span>
      )}
      {task.result && (
        <span className="block max-w-72 truncate" title={task.result}>
          {task.result}
        </span>
      )}
      {!task.result && task.artifact_status !== 'verified' && task.artifact_status !== 'missing' && (
        <span>{t('taskCompletedNoResult')}</span>
      )}
    </div>
  );
}

interface BatchTaskRowProps {
  task: BatchTaskItem;
  retrying: boolean;
  retryLocked: boolean;
  onRetry: (taskId: string) => Promise<void>;
}

function BatchTaskRow({ task, retrying, retryLocked, onRetry }: BatchTaskRowProps) {
  const t = useTranslations('batchDirectory');

  return (
    <TableRow>
      <TableCell className="font-medium max-w-56">
        <span className="truncate block">{task.title}</span>
      </TableCell>
      <TableCell>
        <BatchTaskStatusBadge status={task.status} />
      </TableCell>
      <TableCell className="text-xs text-muted-foreground font-mono max-w-56">
        <span className="truncate block">{task.workspace_path || '—'}</span>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        <TaskResult task={task} />
      </TableCell>
      <TableCell>
        {isTaskRetryable(task) ? (
          <BatchConfirmAlert
            trigger={
              <Button variant="ghost" size="sm" disabled={retrying || retryLocked}>
                {retrying ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCcw className="size-3.5" />}
                <span className="ml-1">{t('retryTaskAction')}</span>
              </Button>
            }
            title={t('confirmRetryTaskTitle')}
            description={t('confirmRetryTaskDescription')}
            confirmLabel={t('confirmRetryTaskAction')}
            onConfirm={() => void onRetry(task.task_id)}
          />
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </TableCell>
    </TableRow>
  );
}

interface BatchTaskTableProps {
  tasks: BatchTaskItem[];
  retryingTaskId: string | null;
  /** 整体重试 / 重跑进行中时，禁用所有单任务重试按钮。 */
  retryLocked: boolean;
  onRetryTask: (taskId: string) => Promise<void>;
}

export function BatchTaskTable({ tasks, retryingTaskId, retryLocked, onRetryTask }: BatchTaskTableProps) {
  const t = useTranslations('batchDirectory');

  return (
    <Card className="mt-6" data-testid="bd-tasks-card">
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
              <TableHead className="w-24">{t('tableAction')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tasks.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-10 text-muted-foreground">
                  {t('emptyTasks')}
                </TableCell>
              </TableRow>
            )}
            {tasks.map((task) => (
              <BatchTaskRow
                key={task.task_id}
                task={task}
                retrying={retryingTaskId === task.task_id}
                retryLocked={retryLocked}
                onRetry={onRetryTask}
              />
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
