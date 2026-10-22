/**
 * [INPUT]
 * - @dnd-kit/core::MouseSensor, TouchSensor, KeyboardSensor (POS: 鼠标 / 触屏 / 键盘各自独立的拖拽传感器)
 * - @/services/kanban::TaskStatus, KanbanTask (POS: 看板 API 类型定义)
 * - ./kanban-transitions::resolveMoveIntent (POS: 看板状态流转判定)
 * - ./kanban-styles::STATUS_COLUMNS (POS: 看板列顺序，也是全部放置目标)
 * - @/hooks/ui/useDndAccessibility (POS: 屏幕阅读器的本地化说明与播报)
 *
 * [OUTPUT]
 * - useKanbanDnD: 看板卡片拖拽状态管理 hook（传感器配置、屏幕阅读器播报、拖拽事件处理、终态确认、不可达流转拦截）
 *
 * [POS]
 * 看板拖拽逻辑层。封装 @dnd-kit 多模式传感器（鼠标/触屏/键盘）、批量拖拽、终态确认弹窗等交互状态。
 * 触屏只有长按才起拖拽，从卡片上起手的滑动留给页面滚动；卡片内控件的手势隔离须覆盖这里指针类传感器的激活事件
 * （见 kanban-card-gestures）。
 * 服务端必拒的流转在落点就拦下并提示；批量拖拽只搬能直接流转的卡片，重试与归档由单卡片流程各自确认。
 * 屏幕阅读器播报念任务标题和本地化的列名，不念任务 id 与状态枚举。
 */
'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  MouseSensor,
  TouchSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragOverEvent,
  type DragEndEvent,
  type UniqueIdentifier,
} from '@dnd-kit/core';
import { useDndAccessibility } from '@/hooks/ui/useDndAccessibility';
import type { TaskStatus, KanbanTask } from '@/services/kanban';
import { STATUS_COLUMNS } from './kanban-styles';
import { resolveMoveIntent } from './kanban-transitions';

// 归档有自己的二次确认（见 KanbanTaskActionConfirm），不在此重复弹窗。
const DESTRUCTIVE_STATUSES: TaskStatus[] = ['completed', 'failed'];

export interface DropConfirmState {
  taskIds: string[];
  targetStatus: TaskStatus;
}

interface UseKanbanDnDOptions {
  tasks: KanbanTask[];
  selectedTaskIds: string[];
  onMoveTask: (taskId: string, targetStatus: TaskStatus) => void;
  onBulkMove?: (taskIds: string[], targetStatus: TaskStatus) => void;
  /** 有卡片因流转不可达没被搬动时调用，每次落点至多一次。 */
  onMoveBlocked: () => void;
}

export function useKanbanDnD({ tasks, selectedTaskIds, onMoveTask, onBulkMove, onMoveBlocked }: UseKanbanDnDOptions) {
  const t = useTranslations('kanban');
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<TaskStatus | null>(null);
  const [dropConfirmState, setDropConfirmState] = useState<DropConfirmState | null>(null);

  // 鼠标与触屏必须分开：PointerSensor 同样接管触屏指针，位移 8px 就起拖拽，卡片上的滑动滚不动看板。
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } }),
    useSensor(KeyboardSensor),
  );

  // 拖拽项是任务 id，放置目标是列的状态枚举。
  const labelOf = useCallback(
    (id: UniqueIdentifier) => {
      const task = tasks.find((tk) => tk.task_id === id);
      if (task) {
        // 放下时被选中的卡片会一起移动，播报要说出来，否则读屏用户会以为只动了这一张。
        const selectedCount = selectedTaskIds.includes(task.task_id) ? selectedTaskIds.length : 1;
        return selectedCount > 1 ? `${task.title}, ${t('bulkSelected', { count: selectedCount })}` : task.title;
      }
      const column = STATUS_COLUMNS.find((status) => status === id);
      return column ? t(`status.${column}`) : undefined;
    },
    [tasks, selectedTaskIds, t],
  );
  const accessibility = useDndAccessibility(labelOf);

  const isBulkDrag = draggedTaskId !== null && selectedTaskIds.includes(draggedTaskId) && selectedTaskIds.length > 1;

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setDraggedTaskId(String(event.active.id));
  }, []);

  const handleDragOver = useCallback((event: DragOverEvent) => {
    const overId = event.over?.id;
    if (overId && typeof overId === 'string') {
      setDragOverColumn(overId as TaskStatus);
    } else {
      setDragOverColumn(null);
    }
  }, []);

  const dispatchMove = useCallback(
    (taskIds: string[], targetStatus: TaskStatus) => {
      if (taskIds.length > 1 && onBulkMove) {
        onBulkMove(taskIds, targetStatus);
      } else {
        taskIds.forEach((id) => onMoveTask(id, targetStatus));
      }
    },
    [onMoveTask, onBulkMove],
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const taskId = String(event.active.id);
      const targetStatus = event.over?.id as TaskStatus | undefined;

      setDraggedTaskId(null);
      setDragOverColumn(null);

      if (!targetStatus) {
        return;
      }

      const task = tasks.find((tk) => tk.task_id === taskId);
      if (!task || task.status === targetStatus) {
        return;
      }

      const statusOf = (id: string) => tasks.find((tk) => tk.task_id === id)?.status;
      const dragged = selectedTaskIds.includes(taskId) && selectedTaskIds.length > 1 ? selectedTaskIds : [taskId];
      // 已经在目标列的卡片本来就不用动，不算被拦下。
      const selection = dragged.filter((id) => statusOf(id) !== targetStatus);
      // 单卡片：重试、归档交给 onMoveTask 的确认流程；批量：只搬能直接流转的卡片。
      const movingIds = selection.filter((id) => {
        const status = statusOf(id);
        const intent = status ? resolveMoveIntent(status, targetStatus) : 'blocked';
        return intent === 'move' || (selection.length === 1 && intent !== 'blocked');
      });
      if (movingIds.length < selection.length) {
        onMoveBlocked();
      }
      if (movingIds.length === 0) {
        return;
      }

      if (DESTRUCTIVE_STATUSES.includes(targetStatus)) {
        setDropConfirmState({ taskIds: movingIds, targetStatus });
        return;
      }

      dispatchMove(movingIds, targetStatus);
    },
    [tasks, selectedTaskIds, dispatchMove, onMoveBlocked],
  );

  const handleDragCancel = useCallback(() => {
    setDraggedTaskId(null);
    setDragOverColumn(null);
  }, []);

  const handleDropConfirm = useCallback(() => {
    if (!dropConfirmState) {
      return;
    }
    setDropConfirmState(null);
    dispatchMove(dropConfirmState.taskIds, dropConfirmState.targetStatus);
  }, [dropConfirmState, dispatchMove]);

  const dismissDropConfirm = useCallback(() => {
    setDropConfirmState(null);
  }, []);

  return {
    sensors,
    accessibility,
    draggedTaskId,
    dragOverColumn,
    dropConfirmState,
    isBulkDrag,
    handleDragStart,
    handleDragOver,
    handleDragEnd,
    handleDragCancel,
    handleDropConfirm,
    dismissDropConfirm,
  };
}
