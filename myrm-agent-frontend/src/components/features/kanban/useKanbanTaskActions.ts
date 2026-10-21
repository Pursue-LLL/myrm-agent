/**
 * [INPUT]
 * - @/services/kanban::reclaimTask, deleteTask, retryTask, TaskStatus (POS: 看板 API 层)
 * - sonner::toast
 *
 * [OUTPUT]
 * - useKanbanTaskActions: 回收 / 删除 / 重试 / 归档的执行函数与结果提示，供确认对话框在用户确认后调用
 *
 * [POS]
 * 看板任务操作的执行层。确认由 KanbanTaskActionConfirm 负责；这里只调 API、刷新列表、给出本地化提示，
 * 失败一律用本地化文案，不透出服务端原文。
 */
'use client';

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { deleteTask, reclaimTask, retryTask, type TaskStatus } from '@/services/kanban';

interface UseKanbanTaskActionsOptions {
  fetchTasks: () => Promise<void>;
  moveTask: (taskId: string, targetStatus: TaskStatus) => Promise<void>;
}

export function useKanbanTaskActions({ fetchTasks, moveTask }: UseKanbanTaskActionsOptions) {
  const t = useTranslations('kanban');

  const reclaim = useCallback(
    async (taskId: string) => {
      try {
        await reclaimTask(taskId);
        await fetchTasks();
        toast.success(t('reclaimSuccess'));
      } catch {
        toast.error(t('reclaimFailed'));
      }
    },
    [fetchTasks, t],
  );

  const remove = useCallback(
    async (taskId: string) => {
      try {
        await deleteTask(taskId);
        await fetchTasks();
        toast.success(t('taskDeleted'));
      } catch {
        toast.error(t('deleteError'));
      }
    },
    [fetchTasks, t],
  );

  const retry = useCallback(
    async (taskId: string) => {
      try {
        await retryTask(taskId);
        await fetchTasks();
        toast.success(t('retrySuccess'));
      } catch {
        toast.error(t('retryError'));
      }
    },
    [fetchTasks, t],
  );

  const archive = useCallback((taskId: string) => moveTask(taskId, 'archived'), [moveTask]);

  return { reclaim, remove, retry, archive };
}
