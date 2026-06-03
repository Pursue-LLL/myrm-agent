/**
 * [INPUT]
 * - @dnd-kit/core::PointerSensor, TouchSensor, KeyboardSensor (POS: 跨平台拖拽传感器)
 * - @/services/kanban::TaskStatus, KanbanTask (POS: 看板 API 类型定义)
 *
 * [OUTPUT]
 * - useKanbanDnD: 看板卡片拖拽状态管理 hook（传感器配置、拖拽事件处理、破坏性操作确认）
 *
 * [POS]
 * 看板拖拽逻辑层。封装 @dnd-kit 多模式传感器（鼠标/触屏/键盘）、批量拖拽、终态确认弹窗等交互状态。
 */
'use client';

import { useCallback, useState } from 'react';
import {
  PointerSensor,
  TouchSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragOverEvent,
  type DragEndEvent,
} from '@dnd-kit/core';
import type { TaskStatus, KanbanTask } from '@/services/kanban';

const DESTRUCTIVE_STATUSES: TaskStatus[] = ['completed', 'failed', 'archived'];

interface DropConfirmState {
  taskId: string;
  targetStatus: TaskStatus;
}

interface UseKanbanDnDOptions {
  tasks: KanbanTask[];
  selectedTaskIds: string[];
  onMoveTask: (taskId: string, targetStatus: TaskStatus) => void;
  onBulkMove?: (taskIds: string[], targetStatus: TaskStatus) => void;
}

export function useKanbanDnD({ tasks, selectedTaskIds, onMoveTask, onBulkMove }: UseKanbanDnDOptions) {
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<TaskStatus | null>(null);
  const [dropConfirmState, setDropConfirmState] = useState<DropConfirmState | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } }),
    useSensor(KeyboardSensor),
  );

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

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const taskId = String(event.active.id);
      const targetStatus = event.over?.id as TaskStatus | undefined;

      setDraggedTaskId(null);
      setDragOverColumn(null);

      if (!targetStatus) return;

      const task = tasks.find((tk) => tk.task_id === taskId);
      if (!task || task.status === targetStatus) return;

      const movingIds = selectedTaskIds.includes(taskId) && selectedTaskIds.length > 1 ? selectedTaskIds : [taskId];

      if (DESTRUCTIVE_STATUSES.includes(targetStatus)) {
        setDropConfirmState({ taskId: movingIds[0], targetStatus });
        return;
      }

      if (movingIds.length > 1 && onBulkMove) {
        onBulkMove(movingIds, targetStatus);
      } else {
        onMoveTask(taskId, targetStatus);
      }
    },
    [tasks, selectedTaskIds, onMoveTask, onBulkMove],
  );

  const handleDragCancel = useCallback(() => {
    setDraggedTaskId(null);
    setDragOverColumn(null);
  }, []);

  const handleDropConfirm = useCallback(() => {
    if (!dropConfirmState) return;
    const { taskId, targetStatus } = dropConfirmState;
    setDropConfirmState(null);

    const movingIds = selectedTaskIds.includes(taskId) && selectedTaskIds.length > 1 ? selectedTaskIds : [taskId];

    if (movingIds.length > 1 && onBulkMove) {
      onBulkMove(movingIds, targetStatus);
    } else {
      onMoveTask(taskId, targetStatus);
    }
  }, [dropConfirmState, selectedTaskIds, onMoveTask, onBulkMove]);

  const dismissDropConfirm = useCallback(() => {
    setDropConfirmState(null);
  }, []);

  return {
    sensors,
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
