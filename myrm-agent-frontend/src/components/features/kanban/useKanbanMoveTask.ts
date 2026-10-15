/**
 * [INPUT]
 * - @/services/kanban::moveTask (POS: 看板 API 层)
 * - @/lib/api::ApiError (POS: API 错误类型，识别 deps_unmet)
 * - ./useKanbanBoardData::PendingUserWrite (POS: 看板数据层的用户写入保护记录)
 *
 * [OUTPUT]
 * - useKanbanMoveTask: 看板任务移动（乐观更新 + 回滚 + 依赖未满足时的强制晋升确认 + 批量顺序移动）
 *
 * [POS]
 * 看板主视图的移动逻辑层。先乐观改状态并登记写入保护，失败时回滚；服务端报依赖未满足时交给强制晋升确认。
 */
'use client';

import { useCallback, useState, type Dispatch, type SetStateAction } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { ApiError } from '@/lib/api';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { moveTask } from '@/services/kanban';
import type { PendingUserWrite } from './useKanbanBoardData';

export interface ForcePromoteState {
  taskId: string;
  targetStatus: TaskStatus;
  parentTitles: string[];
}

interface UseKanbanMoveTaskOptions {
  tasks: KanbanTask[];
  setTasks: Dispatch<SetStateAction<KanbanTask[]>>;
  markPendingWrite: (taskId: string, write: PendingUserWrite) => void;
  clearPendingWrite: (taskId: string) => void;
  fetchTasks: () => Promise<void>;
}

export function useKanbanMoveTask({
  tasks,
  setTasks,
  markPendingWrite,
  clearPendingWrite,
  fetchTasks,
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
      for (const id of taskIds) {
        await handleMoveTask(id, targetStatus);
      }
    },
    [handleMoveTask],
  );

  return { handleMoveTask, handleBulkMove, forcePromoteState, setForcePromoteState, handleForcePromoteConfirm };
}
