import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useKanbanDnD } from '../useKanbanDnD';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import type { DragStartEvent, DragOverEvent, DragEndEvent } from '@dnd-kit/core';

vi.mock('@dnd-kit/core', async () => {
  const actual = await vi.importActual<typeof import('@dnd-kit/core')>('@dnd-kit/core');
  return {
    ...actual,
    useSensor: vi.fn((sensor, options) => ({ sensor, options })),
    useSensors: vi.fn((...sensors) => sensors),
  };
});

function makeMockTask(overrides: Partial<KanbanTask> = {}): KanbanTask {
  return {
    task_id: 'task-1',
    board_id: 'board-1',
    title: 'Test Task',
    description: '',
    status: 'ready' as TaskStatus,
    priority: 'normal',
    retry_count: 0,
    max_retries: 3,
    consecutive_failures: 0,
    result: '',
    error: '',
    metadata: {},
    extra_skill_ids: [],
    attachment_ids: [],
    attachments: [],
    dep_count: 0,
    children_total: 0,
    children_done: 0,
    comment_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function makeDragStartEvent(id: string): DragStartEvent {
  return {
    active: { id, data: { current: undefined }, rect: { current: { initial: null, translated: null } } },
  } as unknown as DragStartEvent;
}

function makeDragOverEvent(overId: string | null): DragOverEvent {
  return {
    active: { id: 'task-1', data: { current: undefined }, rect: { current: { initial: null, translated: null } } },
    over: overId
      ? {
          id: overId,
          data: { current: undefined },
          rect: { width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 },
          disabled: false,
        }
      : null,
  } as unknown as DragOverEvent;
}

function makeDragEndEvent(activeId: string, overId: string | null): DragEndEvent {
  return {
    active: { id: activeId, data: { current: undefined }, rect: { current: { initial: null, translated: null } } },
    over: overId
      ? {
          id: overId,
          data: { current: undefined },
          rect: { width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 },
          disabled: false,
        }
      : null,
    activatorEvent: new Event('pointer'),
    collisions: [],
    delta: { x: 0, y: 0 },
  } as unknown as DragEndEvent;
}

describe('useKanbanDnD', () => {
  const mockOnMoveTask = vi.fn();
  const mockOnBulkMove = vi.fn();
  const defaultTasks: KanbanTask[] = [
    makeMockTask({ task_id: 'task-1', status: 'ready' }),
    makeMockTask({ task_id: 'task-2', status: 'ready' }),
    makeMockTask({ task_id: 'task-3', status: 'running' }),
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('初始状态', () => {
    it('初始化时所有拖拽状态为空', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      expect(result.current.draggedTaskId).toBeNull();
      expect(result.current.dragOverColumn).toBeNull();
      expect(result.current.dropConfirmState).toBeNull();
      expect(result.current.isBulkDrag).toBe(false);
    });

    it('返回 sensors 配置', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      expect(result.current.sensors).toBeDefined();
    });
  });

  describe('handleDragStart', () => {
    it('设置 draggedTaskId', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragStart(makeDragStartEvent('task-1'));
      });

      expect(result.current.draggedTaskId).toBe('task-1');
    });
  });

  describe('handleDragOver', () => {
    it('设置 dragOverColumn', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragOver(makeDragOverEvent('running'));
      });

      expect(result.current.dragOverColumn).toBe('running');
    });

    it('over 为 null 时清除 dragOverColumn', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragOver(makeDragOverEvent('running'));
      });
      act(() => {
        result.current.handleDragOver(makeDragOverEvent(null));
      });

      expect(result.current.dragOverColumn).toBeNull();
    });
  });

  describe('handleDragEnd - 单任务移动', () => {
    it('非破坏性状态直接调用 onMoveTask', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragStart(makeDragStartEvent('task-1'));
      });
      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('task-1', 'running'));
      });

      expect(mockOnMoveTask).toHaveBeenCalledWith('task-1', 'running');
      expect(result.current.draggedTaskId).toBeNull();
      expect(result.current.dragOverColumn).toBeNull();
    });

    it('目标为空时不调用回调', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('task-1', null));
      });

      expect(mockOnMoveTask).not.toHaveBeenCalled();
    });

    it('状态不变时不调用回调', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('task-1', 'ready'));
      });

      expect(mockOnMoveTask).not.toHaveBeenCalled();
    });

    it('任务不存在时不调用回调', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('non-existent', 'running'));
      });

      expect(mockOnMoveTask).not.toHaveBeenCalled();
    });
  });

  describe('handleDragEnd - 破坏性状态确认', () => {
    it.each(['completed', 'failed', 'archived'] as TaskStatus[])('移动到 %s 时弹出确认而不直接执行', (targetStatus) => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('task-1', targetStatus));
      });

      expect(mockOnMoveTask).not.toHaveBeenCalled();
      expect(result.current.dropConfirmState).toEqual({
        taskId: 'task-1',
        targetStatus,
      });
    });

    it('确认后执行移动', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('task-1', 'completed'));
      });
      act(() => {
        result.current.handleDropConfirm();
      });

      expect(mockOnMoveTask).toHaveBeenCalledWith('task-1', 'completed');
      expect(result.current.dropConfirmState).toBeNull();
    });

    it('取消确认清除状态', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('task-1', 'archived'));
      });
      act(() => {
        result.current.dismissDropConfirm();
      });

      expect(mockOnMoveTask).not.toHaveBeenCalled();
      expect(result.current.dropConfirmState).toBeNull();
    });
  });

  describe('多选拖拽 (Bulk Drag)', () => {
    it('选中多任务且拖拽其中之一时 isBulkDrag 为 true', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: ['task-1', 'task-2'],
          onMoveTask: mockOnMoveTask,
          onBulkMove: mockOnBulkMove,
        }),
      );

      act(() => {
        result.current.handleDragStart(makeDragStartEvent('task-1'));
      });

      expect(result.current.isBulkDrag).toBe(true);
    });

    it('选中多任务但拖拽非选中任务时 isBulkDrag 为 false', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: ['task-1', 'task-2'],
          onMoveTask: mockOnMoveTask,
          onBulkMove: mockOnBulkMove,
        }),
      );

      act(() => {
        result.current.handleDragStart(makeDragStartEvent('task-3'));
      });

      expect(result.current.isBulkDrag).toBe(false);
    });

    it('多选拖拽到非破坏性状态时调用 onBulkMove', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: ['task-1', 'task-2'],
          onMoveTask: mockOnMoveTask,
          onBulkMove: mockOnBulkMove,
        }),
      );

      act(() => {
        result.current.handleDragStart(makeDragStartEvent('task-1'));
      });
      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('task-1', 'running'));
      });

      expect(mockOnBulkMove).toHaveBeenCalledWith(['task-1', 'task-2'], 'running');
      expect(mockOnMoveTask).not.toHaveBeenCalled();
    });

    it('多选拖拽到破坏性状态时弹出确认', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: ['task-1', 'task-2'],
          onMoveTask: mockOnMoveTask,
          onBulkMove: mockOnBulkMove,
        }),
      );

      act(() => {
        result.current.handleDragStart(makeDragStartEvent('task-1'));
      });
      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('task-1', 'completed'));
      });

      expect(mockOnBulkMove).not.toHaveBeenCalled();
      expect(result.current.dropConfirmState).toEqual({
        taskId: 'task-1',
        targetStatus: 'completed',
      });
    });

    it('多选确认后调用 onBulkMove', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: ['task-1', 'task-2'],
          onMoveTask: mockOnMoveTask,
          onBulkMove: mockOnBulkMove,
        }),
      );

      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('task-1', 'archived'));
      });
      act(() => {
        result.current.handleDropConfirm();
      });

      expect(mockOnBulkMove).toHaveBeenCalledWith(['task-1', 'task-2'], 'archived');
      expect(mockOnMoveTask).not.toHaveBeenCalled();
    });

    it('未提供 onBulkMove 时多选也走 onMoveTask 逐个执行', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: ['task-1', 'task-2'],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragStart(makeDragStartEvent('task-1'));
      });
      act(() => {
        result.current.handleDragEnd(makeDragEndEvent('task-1', 'running'));
      });

      expect(mockOnMoveTask).toHaveBeenCalledWith('task-1', 'running');
    });
  });

  describe('handleDragCancel', () => {
    it('取消拖拽时清除所有拖拽状态', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDragStart(makeDragStartEvent('task-1'));
      });
      act(() => {
        result.current.handleDragOver(makeDragOverEvent('running'));
      });
      act(() => {
        result.current.handleDragCancel();
      });

      expect(result.current.draggedTaskId).toBeNull();
      expect(result.current.dragOverColumn).toBeNull();
    });
  });

  describe('handleDropConfirm 边界情况', () => {
    it('dropConfirmState 为空时调用 handleDropConfirm 无副作用', () => {
      const { result } = renderHook(() =>
        useKanbanDnD({
          tasks: defaultTasks,
          selectedTaskIds: [],
          onMoveTask: mockOnMoveTask,
        }),
      );

      act(() => {
        result.current.handleDropConfirm();
      });

      expect(mockOnMoveTask).not.toHaveBeenCalled();
    });
  });
});
