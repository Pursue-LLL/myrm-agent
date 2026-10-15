/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import { bulkAction, moveTask, type BulkActionResult, type KanbanTask, type TaskStatus } from '@/services/kanban';
import { useKanbanMoveTask } from '../useKanbanMoveTask';

const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));

vi.mock('@/services/kanban', () => ({
  moveTask: vi.fn(),
  bulkAction: vi.fn(),
}));

function makeTask(taskId: string, status: TaskStatus): KanbanTask {
  return {
    task_id: taskId,
    board_id: 'board-1',
    title: taskId,
    description: '',
    status,
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
  };
}

function bulkResult(failedIds: string[], ids: string[] = ['a', 'b', 'c']): BulkActionResult {
  const results = ids.map((taskId) => ({
    task_id: taskId,
    success: !failedIds.includes(taskId),
    ...(failedIds.includes(taskId) ? { error: 'server detail that must not reach the UI' } : {}),
  }));
  return { results, total: ids.length, succeeded: ids.length - failedIds.length, failed: failedIds.length };
}

function setup(initial: KanbanTask[]) {
  const markPendingWrite = vi.fn();
  const clearPendingWrite = vi.fn();
  const fetchTasks = vi.fn().mockResolvedValue(undefined);
  const onBulkSettled = vi.fn();
  const { result } = renderHook(() => {
    const [tasks, setTasks] = useState(initial);
    const move = useKanbanMoveTask({
      boardId: 'board-1',
      tasks,
      setTasks,
      markPendingWrite,
      clearPendingWrite,
      fetchTasks,
      onBulkSettled,
    });
    return { tasks, ...move };
  });
  const statusOf = (taskId: string) => result.current.tasks.find((task) => task.task_id === taskId)?.status;
  return { result, statusOf, markPendingWrite, clearPendingWrite, fetchTasks, onBulkSettled };
}

const BACKLOG_TRIO = () => [makeTask('a', 'backlog'), makeTask('b', 'backlog'), makeTask('c', 'backlog')];

describe('useKanbanMoveTask bulk move', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sends one bulk request, moves every card optimistically, and refreshes once', async () => {
    let settle: (value: BulkActionResult) => void = () => undefined;
    vi.mocked(bulkAction).mockReturnValue(new Promise((resolve) => (settle = resolve)));
    const { result, statusOf, markPendingWrite, clearPendingWrite, fetchTasks, onBulkSettled } = setup(BACKLOG_TRIO());

    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.handleBulkMove(['a', 'b', 'c'], 'ready');
    });

    // 请求在途时三张卡片已经在目标列，且各自登记了写入保护
    expect(['a', 'b', 'c'].map(statusOf)).toEqual(['ready', 'ready', 'ready']);
    expect(markPendingWrite).toHaveBeenCalledTimes(3);

    await act(async () => {
      settle(bulkResult([]));
      await pending;
    });

    expect(bulkAction).toHaveBeenCalledTimes(1);
    expect(bulkAction).toHaveBeenCalledWith('board-1', ['a', 'b', 'c'], 'move', { status: 'ready' }, false);
    expect(moveTask).not.toHaveBeenCalled();
    expect(clearPendingWrite).toHaveBeenCalledTimes(3);
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(onBulkSettled).toHaveBeenCalledWith([]);
    expect(fetchTasks).toHaveBeenCalledTimes(1);
    expect(['a', 'b', 'c'].map(statusOf)).toEqual(['ready', 'ready', 'ready']);
  });

  it('puts only the rejected cards back, reports them once and never opens the force dialog', async () => {
    vi.mocked(bulkAction).mockResolvedValue(bulkResult(['b', 'c']));
    const { result, statusOf, fetchTasks, onBulkSettled } = setup(BACKLOG_TRIO());

    await act(async () => {
      await result.current.handleBulkMove(['a', 'b', 'c'], 'ready');
    });

    expect(['a', 'b', 'c'].map(statusOf)).toEqual(['ready', 'backlog', 'backlog']);
    expect(toast.warning).toHaveBeenCalledTimes(1);
    expect(toast.warning).toHaveBeenCalledWith('bulkPartialSuccess:{"succeeded":1,"failed":2}');
    expect(toast.error).not.toHaveBeenCalled();
    expect(onBulkSettled).toHaveBeenCalledWith(['b', 'c']);
    expect(result.current.forcePromoteState).toBeNull();
    expect(fetchTasks).toHaveBeenCalledTimes(1);
  });

  it('rolls every card back and keeps the selection when the request itself fails', async () => {
    vi.mocked(bulkAction).mockRejectedValue(new Error('network down'));
    const { result, statusOf, clearPendingWrite, fetchTasks, onBulkSettled } = setup(BACKLOG_TRIO());

    await act(async () => {
      await result.current.handleBulkMove(['a', 'b', 'c'], 'ready');
    });

    expect(['a', 'b', 'c'].map(statusOf)).toEqual(['backlog', 'backlog', 'backlog']);
    expect(toast.error).toHaveBeenCalledWith('updateError');
    expect(onBulkSettled).not.toHaveBeenCalled();
    expect(clearPendingWrite).toHaveBeenCalledTimes(3);
    expect(fetchTasks).toHaveBeenCalledTimes(1);
  });

  it('does not register a write for a card that is already in the target column', async () => {
    vi.mocked(bulkAction).mockResolvedValue(bulkResult([], ['a', 'b']));
    const { result, markPendingWrite } = setup([makeTask('a', 'ready'), makeTask('b', 'backlog')]);

    await act(async () => {
      await result.current.handleBulkMove(['a', 'b'], 'ready');
    });

    expect(markPendingWrite).toHaveBeenCalledTimes(1);
    expect(markPendingWrite.mock.calls[0]?.[0]).toBe('b');
  });
});

describe('useKanbanMoveTask single move', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('moves optimistically, calls the single-task endpoint without force, and refreshes', async () => {
    vi.mocked(moveTask).mockResolvedValue(makeTask('a', 'ready'));
    const { result, statusOf, fetchTasks } = setup([makeTask('a', 'backlog')]);

    await act(async () => {
      await result.current.handleMoveTask('a', 'ready');
    });

    expect(moveTask).toHaveBeenCalledWith('a', 'ready', { force: false });
    expect(statusOf('a')).toBe('ready');
    expect(fetchTasks).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('rolls back and offers the force dialog when dependencies are unmet', async () => {
    const unmet = new ApiError('deps unmet', 40901, [], undefined, 'deps_unmet');
    unmet.data = { unmet_parents: [{ task_id: 'p', title: 'Parent', status: 'running' }] };
    vi.mocked(moveTask).mockRejectedValue(unmet);
    const { result, statusOf } = setup([makeTask('a', 'backlog')]);

    await act(async () => {
      await result.current.handleMoveTask('a', 'ready');
    });

    expect(statusOf('a')).toBe('backlog');
    expect(result.current.forcePromoteState).toEqual({
      taskId: 'a',
      targetStatus: 'ready',
      parentTitles: ['Parent (running)'],
    });
    expect(toast.error).not.toHaveBeenCalled();

    vi.mocked(moveTask).mockResolvedValue(makeTask('a', 'ready'));
    await act(async () => {
      await result.current.handleForcePromoteConfirm();
    });

    expect(moveTask).toHaveBeenLastCalledWith('a', 'ready', { force: true });
    await waitFor(() => expect(result.current.forcePromoteState).toBeNull());
    expect(statusOf('a')).toBe('ready');
  });

  it('rolls back and shows a localized error for any other failure', async () => {
    vi.mocked(moveTask).mockRejectedValue(new Error('server stack trace'));
    const { result, statusOf } = setup([makeTask('a', 'backlog')]);

    await act(async () => {
      await result.current.handleMoveTask('a', 'ready');
    });

    expect(statusOf('a')).toBe('backlog');
    expect(toast.error).toHaveBeenCalledWith('moveError');
    expect(result.current.forcePromoteState).toBeNull();
  });
});
