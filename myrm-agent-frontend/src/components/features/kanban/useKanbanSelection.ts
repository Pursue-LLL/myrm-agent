/**
 * [INPUT]
 * - ./kanban-selection::applyTaskClick, visibleColumnTasks (POS: 看板多选与泳道规则的纯逻辑)
 * - ./kanban-styles::STATUS_COLUMNS (POS: 看板列顺序，用来确定哪些卡片在屏幕上)
 * - @/services/kanban::KanbanTask, TaskStatus (POS: 看板 API 类型定义)
 *
 * [OUTPUT]
 * - useKanbanSelection: 看板卡片多选状态（点选 / Shift 区间 / Esc 清除 / 自动剔除已看不见的任务）
 *
 * [POS]
 * 看板多选的状态层。选中集合永远只含屏幕上看得见的任务：任务被删除、归档、被责任筛选藏起来，
 * 或所在泳道被收起后自动退出选择，批量操作不会作用到看不见的任务。
 */
import { useCallback, useEffect, useMemo, useState, type MouseEvent } from 'react';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { applyTaskClick, visibleColumnTasks, type TaskClickContext } from './kanban-selection';
import { STATUS_COLUMNS } from './kanban-styles';

const NO_IDS: string[] = [];

interface UseKanbanSelectionOptions extends Omit<TaskClickContext, 'tasks'> {
  boardId: string;
  tasks: readonly KanbanTask[];
}

export function useKanbanSelection({
  boardId,
  tasks,
  columnTasks,
  laneByProfile,
  agentNameMap,
  collapsedAgents,
}: UseKanbanSelectionOptions) {
  const [ownIds, setOwnIds] = useState<string[]>(NO_IDS);
  const [ownBoardId, setOwnBoardId] = useState(boardId);
  // 换看板时选择归零；在渲染中调整状态，React 会丢弃这次渲染立刻重来，不会用旧选择画出一帧。
  if (ownBoardId !== boardId) {
    setOwnBoardId(boardId);
    setOwnIds(NO_IDS);
  }

  // 以屏幕上实际画出来的卡片为准：被删除、归档、被责任筛选藏起来，或在收起的泳道里的任务都不在其中。
  const visibleTasks = useMemo(
    () =>
      STATUS_COLUMNS.flatMap((status) =>
        visibleColumnTasks(status, columnTasks[status], { laneByProfile, agentNameMap, collapsedAgents }),
      ),
    [columnTasks, laneByProfile, agentNameMap, collapsedAgents],
  );

  const selectedTaskIds = useMemo(() => {
    const visible = new Set(visibleTasks.map((task) => task.task_id));
    const kept = ownIds.filter((id) => visible.has(id));
    return kept.length === ownIds.length ? ownIds : kept;
  }, [ownIds, visibleTasks]);

  const selectedStatuses = useMemo<TaskStatus[]>(() => {
    const selected = new Set(selectedTaskIds);
    return tasks.filter((task) => selected.has(task.task_id)).map((task) => task.status);
  }, [selectedTaskIds, tasks]);

  const selectOnly = useCallback((ids: string[]) => setOwnIds(ids), []);
  const clearSelection = useCallback(() => setOwnIds(NO_IDS), []);

  const handleTaskSelect = useCallback(
    (taskId: string, event: Pick<MouseEvent, 'ctrlKey' | 'metaKey' | 'shiftKey'>) => {
      const extendRange = event.shiftKey && !event.ctrlKey && !event.metaKey;
      selectOnly(
        applyTaskClick(
          selectedTaskIds,
          { taskId, extendRange },
          { tasks, columnTasks, laneByProfile, agentNameMap, collapsedAgents },
        ),
      );
    },
    [selectOnly, selectedTaskIds, tasks, columnTasks, laneByProfile, agentNameMap, collapsedAgents],
  );

  const hasSelection = selectedTaskIds.length > 0;
  useEffect(() => {
    if (!hasSelection) {
      return;
    }
    // 菜单、对话框等浮层用 Esc 关闭自己时会 preventDefault；此时这次 Esc 已被消费，不该同时清掉选择。
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented) {
        clearSelection();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [hasSelection, clearSelection]);

  return { selectedTaskIds, selectedStatuses, handleTaskSelect, selectOnly, clearSelection };
}
