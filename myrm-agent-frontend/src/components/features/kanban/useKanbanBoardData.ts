/**
 * [INPUT]
 * - @/services/kanban::listTasks, getBoardSummary, listBoardEdges (POS: 看板 API 层)
 * - next-intl::useTranslations (POS: 国际化翻译)
 *
 * [OUTPUT]
 * - useKanbanBoardData: 看板数据层（任务 / 汇总 / 依赖边 + 30s 轮询 + 事件触发的合并刷新 + 用户写入保护）
 *
 * [POS]
 * 看板主视图的数据来源。拉取并持有任务、汇总、依赖边；用户刚拖动的任务在 5 秒内不被服务端旧数据覆盖，
 * kanban-task-updated / app_resync_required 事件合并成一次延迟刷新。
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import type { BoardSummary, KanbanTask, TaskDependency, TaskStatus } from '@/services/kanban';
import { getBoardSummary, listBoardEdges, listTasks } from '@/services/kanban';
import type { KanbanViewMode } from './KanbanViewControls';

export interface PendingUserWrite {
  targetStatus: TaskStatus;
  previousStatus: TaskStatus;
  ts: number;
}

interface UseKanbanBoardDataOptions {
  boardId: string;
  sourceChatFilter: string | undefined;
  activeStatusFilter: TaskStatus | undefined;
  viewMode: KanbanViewMode;
}

export function useKanbanBoardData({
  boardId,
  sourceChatFilter,
  activeStatusFilter,
  viewMode,
}: UseKanbanBoardDataOptions) {
  const t = useTranslations('kanban');
  const [tasks, setTasks] = useState<KanbanTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [summaryData, setSummaryData] = useState<BoardSummary | null>(null);
  const [edges, setEdges] = useState<TaskDependency[]>([]);
  const pendingUserWrites = useRef<Map<string, { targetStatus: TaskStatus; previousStatus: TaskStatus; ts: number }>>(
    new Map(),
  );

  const fetchTasks = useCallback(async () => {
    try {
      const result = await listTasks(boardId, {
        limit: 200,
        source_chat_id: sourceChatFilter,
        status: activeStatusFilter,
      });
      const pending = pendingUserWrites.current;
      if (pending.size === 0) {
        setTasks(result.items);
      } else {
        const now = Date.now();
        for (const [id, entry] of pending) {
          if (now - entry.ts > 5_000) {
            pending.delete(id);
          }
        }
        setTasks(
          result.items.map((serverTask) => {
            const guard = pending.get(serverTask.task_id);
            if (guard) {
              return { ...serverTask, status: guard.targetStatus };
            }
            return serverTask;
          }),
        );
      }
    } catch {
      toast.error(t('fetchError'));
    } finally {
      setLoading(false);
    }
  }, [boardId, sourceChatFilter, activeStatusFilter, t]);

  const fetchEdges = useCallback(async () => {
    try {
      const result = await listBoardEdges(boardId);
      setEdges(result.items);
    } catch {
      /* edges are optional for the board view */
    }
  }, [boardId]);

  const fetchSummary = useCallback(async () => {
    try {
      const data = await getBoardSummary(boardId);
      setSummaryData(data);
    } catch {
      /* silent */
    }
  }, [boardId]);

  const reloadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleReload = useCallback(() => {
    if (reloadTimerRef.current) {
      return;
    }
    reloadTimerRef.current = setTimeout(() => {
      reloadTimerRef.current = null;
      fetchTasks();
      fetchSummary();
      fetchEdges();
    }, 250);
  }, [fetchTasks, fetchSummary, fetchEdges]);

  useEffect(() => {
    fetchTasks();
    fetchSummary();
    fetchEdges();
    const interval = setInterval(() => {
      fetchTasks();
      fetchSummary();
      if (viewMode === 'graph') {
        fetchEdges();
      }
    }, 30_000);

    const onKanbanEvent = (e: Event) => {
      const detail = (e as CustomEvent).detail as { board_id?: string } | undefined;
      if (!detail?.board_id || detail.board_id === boardId) {
        scheduleReload();
      }
    };
    const onResync = () => scheduleReload();
    window.addEventListener('kanban-task-updated', onKanbanEvent);
    window.addEventListener('app_resync_required', onResync);

    return () => {
      clearInterval(interval);
      if (reloadTimerRef.current) {
        clearTimeout(reloadTimerRef.current);
      }
      window.removeEventListener('kanban-task-updated', onKanbanEvent);
      window.removeEventListener('app_resync_required', onResync);
    };
  }, [fetchTasks, fetchSummary, fetchEdges, viewMode, boardId, scheduleReload]);

  const markPendingWrite = useCallback((taskId: string, write: PendingUserWrite) => {
    pendingUserWrites.current.set(taskId, write);
  }, []);
  const clearPendingWrite = useCallback((taskId: string) => {
    pendingUserWrites.current.delete(taskId);
  }, []);

  return {
    tasks,
    setTasks,
    loading,
    summaryData,
    edges,
    markPendingWrite,
    clearPendingWrite,
    fetchTasks,
    fetchSummary,
    fetchEdges,
  };
}
