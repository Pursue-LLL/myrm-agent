/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addComment,
  addDependency,
  listDependencies,
  listDependents,
  listEvents,
  listRuns,
  removeDependency,
  type KanbanTask,
  type TaskEvent,
  type TaskRun,
  type TaskStatus,
} from '@/services/kanban';
import { useKanbanTaskCardDetails } from '../useKanbanTaskCardDetails';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/services/kanban', () => ({
  listRuns: vi.fn(),
  listEvents: vi.fn(),
  listDependencies: vi.fn(),
  listDependents: vi.fn(),
  addComment: vi.fn(),
  addDependency: vi.fn(),
  removeDependency: vi.fn(),
  getTask: vi.fn(),
}));

function makeTask(taskId: string, status: TaskStatus = 'ready'): KanbanTask {
  return {
    task_id: taskId,
    board_id: 'board-1',
    title: `title-${taskId}`,
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

const RUN: TaskRun = {
  run_id: 'r1',
  task_id: 'self',
  worker_id: 'w1',
  started_at: '2026-01-01T00:00:00Z',
  summary: '',
  error: '',
};
const EVENT: TaskEvent = { event_id: 1, task_id: 'self', kind: 'created', created_at: '2026-01-01T00:00:00Z' };
const COMMENT: TaskEvent = { event_id: 2, task_id: 'self', kind: 'comment', created_at: '2026-01-01T00:00:01Z' };

const ALL_TASKS = [
  makeTask('self'),
  makeTask('parent-1', 'completed'),
  makeTask('parent-2'),
  makeTask('child-1', 'backlog'),
];

function setup() {
  const onRefresh = vi.fn();
  const { result } = renderHook(() => useKanbanTaskCardDetails({ task: ALL_TASKS[0], allTasks: ALL_TASKS, onRefresh }));
  return { result, onRefresh };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listRuns).mockResolvedValue({ items: [RUN], total: 1 });
  vi.mocked(listEvents).mockResolvedValue({ items: [EVENT], total: 1 });
  vi.mocked(listDependencies).mockResolvedValue({ items: ['parent-1'], total: 1 });
  vi.mocked(listDependents).mockResolvedValue({ items: ['child-1'], total: 1 });
});

describe('useKanbanTaskCardDetails loading', () => {
  it('starts collapsed and fetches nothing', () => {
    const { result } = setup();

    expect(result.current.expanded).toBe(false);
    expect(listRuns).not.toHaveBeenCalled();
  });

  it('expanding loads runs, events, parents and children', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.toggleExpand();
    });

    expect(result.current.expanded).toBe(true);
    expect(result.current.detailLoading).toBe(false);
    expect(result.current.runs).toEqual([RUN]);
    expect(result.current.events).toEqual([EVENT]);
    expect(result.current.parents).toEqual([{ task_id: 'parent-1', title: 'title-parent-1', status: 'completed' }]);
    expect(result.current.children).toEqual([{ task_id: 'child-1', title: 'title-child-1', status: 'backlog' }]);
  });

  it('collapsing fetches nothing, and every expansion fetches again', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.toggleExpand();
    });
    await act(async () => {
      await result.current.toggleExpand();
    });
    expect(result.current.expanded).toBe(false);
    expect(listRuns).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.toggleExpand();
    });
    expect(result.current.expanded).toBe(true);
    expect(listRuns).toHaveBeenCalledTimes(2);
  });

  it('a failed load tells the user, stops loading and leaves the panel empty', async () => {
    vi.mocked(listEvents).mockRejectedValue(new Error('server detail that must not reach the UI'));
    const { result } = setup();

    await act(async () => {
      await result.current.toggleExpand();
    });

    expect(toast.error).toHaveBeenCalledWith('detailsLoadError');
    expect(result.current.detailLoading).toBe(false);
    expect(result.current.expanded).toBe(true);
    expect(result.current.runs).toEqual([]);
    expect(result.current.parents).toEqual([]);
  });
});

describe('useKanbanTaskCardDetails dependencies', () => {
  async function expanded() {
    const ctx = setup();
    await act(async () => {
      await ctx.result.current.toggleExpand();
    });
    return ctx;
  }

  it('offers every other task that is not already a parent', async () => {
    const { result } = await expanded();

    expect(result.current.availableParents.map((task) => task.task_id)).toEqual(['parent-2', 'child-1']);
  });

  it('adding a parent lists it, closes the picker, refreshes the board and confirms', async () => {
    vi.mocked(addDependency).mockResolvedValue({ parent_task_id: 'parent-2', child_task_id: 'self' });
    const { result, onRefresh } = await expanded();
    act(() => result.current.setShowAddDep(true));

    await act(async () => {
      await result.current.handleAddDep('parent-2');
    });

    expect(addDependency).toHaveBeenCalledWith('self', 'parent-2');
    expect(result.current.parents.map((parent) => parent.task_id)).toEqual(['parent-1', 'parent-2']);
    expect(result.current.showAddDep).toBe(false);
    expect(result.current.addingDep).toBe(false);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith('depAdded');
  });

  it('a rejected add leaves the parents and the picker as they were and tells the user', async () => {
    vi.mocked(addDependency).mockRejectedValue(new Error('cycle'));
    const { result, onRefresh } = await expanded();
    act(() => result.current.setShowAddDep(true));

    await act(async () => {
      await result.current.handleAddDep('parent-2');
    });

    expect(result.current.parents.map((parent) => parent.task_id)).toEqual(['parent-1']);
    expect(result.current.showAddDep).toBe(true);
    expect(result.current.addingDep).toBe(false);
    expect(onRefresh).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('depAddError');
  });

  it('removing a parent drops it, refreshes the board and confirms', async () => {
    vi.mocked(removeDependency).mockResolvedValue(undefined);
    const { result, onRefresh } = await expanded();

    await act(async () => {
      await result.current.handleRemoveDep('parent-1');
    });

    expect(removeDependency).toHaveBeenCalledWith('self', 'parent-1');
    expect(result.current.parents).toEqual([]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith('depRemoved');
  });

  it('a rejected removal keeps the parent and tells the user', async () => {
    vi.mocked(removeDependency).mockRejectedValue(new Error('boom'));
    const { result, onRefresh } = await expanded();

    await act(async () => {
      await result.current.handleRemoveDep('parent-1');
    });

    expect(result.current.parents.map((parent) => parent.task_id)).toEqual(['parent-1']);
    expect(onRefresh).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('depRemoveError');
  });
});

describe('useKanbanTaskCardDetails comments', () => {
  it('ignores a blank comment', async () => {
    const { result } = setup();
    act(() => result.current.setCommentText('   '));

    await act(async () => {
      await result.current.handleSubmitComment();
    });

    expect(addComment).not.toHaveBeenCalled();
  });

  it('a posted comment is trimmed, appended to the timeline and clears the input', async () => {
    vi.mocked(addComment).mockResolvedValue(COMMENT);
    const { result } = setup();
    act(() => result.current.setCommentText('  looks good  '));

    await act(async () => {
      await result.current.handleSubmitComment();
    });

    expect(addComment).toHaveBeenCalledWith('self', 'looks good');
    expect(result.current.events).toEqual([COMMENT]);
    expect(result.current.commentText).toBe('');
    expect(result.current.submittingComment).toBe(false);
  });

  it('a rejected comment keeps the text for another try and tells the user', async () => {
    vi.mocked(addComment).mockRejectedValue(new Error('boom'));
    const { result } = setup();
    act(() => result.current.setCommentText('looks good'));

    await act(async () => {
      await result.current.handleSubmitComment();
    });

    expect(result.current.commentText).toBe('looks good');
    expect(result.current.events).toEqual([]);
    expect(result.current.submittingComment).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('addCommentError');
  });
});
