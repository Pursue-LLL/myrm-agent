/**
 * [INPUT]
 * - @/services/kanban::moveTask (POS: 看板 API 层)
 * - @/lib/api::ApiError (POS: API 错误类型，识别 deps_unmet)
 * - ./kanban-bulk::runBulkAction (POS: 批量请求与结果提示，批量工具栏共用)
 * - ./useKanbanBoardData::PendingUserWrite (POS: 看板数据层的用户写入保护记录)
 *
 * [OUTPUT]
 * - useKanbanMoveTask: 看板任务移动（乐观更新 + 回滚 + 依赖未满足时的强制晋升确认 + 一次请求的批量移动）
 *
 * [POS]
 * 看板主视图的移动逻辑层。先乐观改状态并登记写入保护，失败时回滚；服务端报依赖未满足时交给强制晋升确认。
 * 单卡走单任务接口；多卡走批量接口：一次请求、逐条结果，被拒的卡片回滚后交给 `onBulkSettled` 保持选中。
 * 强制晋升确认只属于单卡流程：它只有一个确认槽，容纳不了一次移动多张卡。
 */
'use client';

import { useCallback, useState, type Dispatch, type SetStateAction } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { ApiError } from '@/lib/api';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { moveTask } from '@/services/kanban';
import { runBulkAction } from './kanban-bulk';
import type { PendingUserWrite } from './useKanbanBoardData';

export interface ForcePromoteState {
  taskId: string;
  targetStatus: TaskStatus;
  parentTitles: string[];
}

interface UseKanbanMoveTaskOptions {
  boardId: string;
  tasks: KanbanTask[];
  setTasks: Dispatch<SetStateAction<KanbanTask[]>>;
  markPendingWrite: (taskId: string, write: PendingUserWrite) => void;
  clearPendingWrite: (taskId: string) => void;
  fetchTasks: () => Promise<void>;
  /** 批量移动请求结束后调用，参数为未被移动的任务 id；请求整体失败时不调用。 */
  onBulkSettled: (failedTaskIds: string[]) => void;
}

export function useKanbanMoveTask({
  boardId,
  tasks,
  setTasks,
  markPendingWrite,
  clearPendingWrite,
  fetchTasks,
  onBulkSettled,
}: UseKanbanMoveTaskOptions) {
  const t = useTranslations('kanban');
  const [forcePromoteState, setForcePromoteState] = useState<ForcePromoteState | null>(null);

  const handleMoveTask = useCallback(
    async (taskId: string, targetStatus: TaskStatus, force = false) => {
      const currentTask = tasks.find((tk) => tk.task_id === taskId);
      const previousStatus = currentTask?.status;

      if (previousStatus && previousStatus !== targetStatus) {
        markPendingWrite(taskId, { targetStatus, previousStatus, ts: Date.now() });
        setTasks((prev) => prev.map((tk) => (tk.task_id === taskId ? { ...tk, status: targetStatus } : tk)));
      }

      try {
        await moveTask(taskId, targetStatus, { force });
        clearPendingWrite(taskId);
        await fetchTasks();
      } catch (err) {
        clearPendingWrite(taskId);
        if (previousStatus) {
          setTasks((prev) => prev.map((tk) => (tk.task_id === taskId ? { ...tk, status: previousStatus } : tk)));
        }
        if (err instanceof ApiError && err.businessCode === 'deps_unmet') {
          const parents = (err.data?.unmet_parents ?? []) as Array<{ task_id: string; title: string; status: string }>;
          const parentTitles = parents.map((p) => `${p.title} (${p.status})`);
          setForcePromoteState({ taskId, targetStatus, parentTitles });
          return;
        }
        toast.error(t('moveError'));
      }
    },
    [tasks, setTasks, markPendingWrite, clearPendingWrite, fetchTasks, t],
  );

  const handleForcePromoteConfirm = useCallback(async () => {
    if (!forcePromoteState) {
      return;
    }
    const { taskId, targetStatus } = forcePromoteState;
    setForcePromoteState(null);
    await handleMoveTask(taskId, targetStatus, true);
  }, [forcePromoteState, handleMoveTask]);

  const handleBulkMove = useCallback(
    async (taskIds: string[], targetStatus: TaskStatus) => {
      const previousStatuses = new Map<string, TaskStatus>();
      for (const tk of tasks) {
        if (taskIds.includes(tk.task_id) && tk.status !== targetStatus) {
          previousStatuses.set(tk.task_id, tk.status);
        }
      }
      previousStatuses.forEach((previousStatus, taskId) =>
        markPendingWrite(taskId, { targetStatus, previousStatus, ts: Date.now() }),
      );
      setTasks((prev) => prev.map((tk) => (previousStatuses.has(tk.task_id) ? { ...tk, status: targetStatus } : tk)));

      const failedTaskIds = await runBulkAction({
        boardId,
        taskIds,
        action: 'move',
        params: { status: targetStatus },
        t,
      });
      previousStatuses.forEach((_, taskId) => clearPendingWrite(taskId));

      // 请求整体失败时没有任何卡片被确认移动，全部回滚；否则只回滚被拒的卡片。
      const rejected = failedTaskIds === null ? new Set(previousStatuses.keys()) : new Set(failedTaskIds);
      setTasks((prev) =>
        prev.map((tk) => {
          const previousStatus = rejected.has(tk.task_id) ? previousStatuses.get(tk.task_id) : undefined;
          return previousStatus ? { ...tk, status: previousStatus } : tk;
        }),
      );
      if (failedTaskIds !== null) {
        onBulkSettled(failedTaskIds);
      }
      await fetchTasks();
    },
    [boardId, tasks, setTasks, markPendingWrite, clearPendingWrite, fetchTasks, onBulkSettled, t],
  );

  return { handleMoveTask, handleBulkMove, forcePromoteState, setForcePromoteState, handleForcePromoteConfirm };
}
