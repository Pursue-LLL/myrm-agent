/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { useKanbanSelection } from '../useKanbanSelection';

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

const ALL_STATUSES: TaskStatus[] = [
  'triage',
  'backlog',
  'ready',
  'running',
  'blocked',
  'in_review',
  'completed',
  'failed',
  'archived',
];

function columnsOf(tasks: KanbanTask[]): Record<TaskStatus, KanbanTask[]> {
  const grouped = Object.fromEntries(ALL_STATUSES.map((status) => [status, [] as KanbanTask[]])) as Record<
    TaskStatus,
    KanbanTask[]
  >;
  for (const task of tasks) {
    grouped[task.status].push(task);
  }
  return grouped;
}

const PLAIN = { ctrlKey: false, metaKey: false, shiftKey: false };
const CMD = { ...PLAIN, metaKey: true };
const SHIFT = { ...PLAIN, shiftKey: true };

const TASKS = [
  makeTask('ready-1', 'ready'),
  makeTask('backlog-1', 'backlog'),
  makeTask('ready-2', 'ready'),
  makeTask('ready-3', 'ready'),
];

function setup(initial: { boardId: string; tasks: KanbanTask[] } = { boardId: 'board-1', tasks: TASKS }) {
  return renderHook(
    (props: { boardId: string; tasks: KanbanTask[] }) =>
      useKanbanSelection({
        boardId: props.boardId,
        tasks: props.tasks,
        columnTasks: columnsOf(props.tasks),
        laneByProfile: false,
      }),
    { initialProps: initial },
  );
}

const pressEscape = (defaultPrevented = false) => {
  const event = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true });
  if (defaultPrevented) {
    event.preventDefault();
  }
  act(() => {
    window.dispatchEvent(event);
  });
};

describe('useKanbanSelection', () => {
  it('toggles cards with the modifier click and reports their statuses', () => {
    const { result } = setup();

    act(() => result.current.handleTaskSelect('ready-1', CMD));
    act(() => result.current.handleTaskSelect('backlog-1', CMD));
    expect(result.current.selectedTaskIds).toEqual(['ready-1', 'backlog-1']);
    expect(result.current.selectedStatuses).toEqual(['ready', 'backlog']);

    act(() => result.current.handleTaskSelect('ready-1', CMD));
    expect(result.current.selectedTaskIds).toEqual(['backlog-1']);
  });

  it('Shift selects the range inside the anchor column only', () => {
    const { result } = setup();

    act(() => result.current.handleTaskSelect('ready-1', CMD));
    act(() => result.current.handleTaskSelect('ready-3', SHIFT));

    expect(result.current.selectedTaskIds).toEqual(['ready-1', 'ready-2', 'ready-3']);
  });

  it('treats Ctrl/Cmd together with Shift as a plain toggle', () => {
    const { result } = setup();

    act(() => result.current.handleTaskSelect('ready-1', CMD));
    act(() => result.current.handleTaskSelect('ready-3', { ...SHIFT, metaKey: true }));

    expect(result.current.selectedTaskIds).toEqual(['ready-1', 'ready-3']);
  });

  it('drops selected tasks that no longer exist, but keeps the rest', () => {
    const { result, rerender } = setup();
    act(() => result.current.handleTaskSelect('ready-1', CMD));
    act(() => result.current.handleTaskSelect('ready-2', CMD));

    rerender({ boardId: 'board-1', tasks: TASKS.filter((task) => task.task_id !== 'ready-1') });

    expect(result.current.selectedTaskIds).toEqual(['ready-2']);
    expect(result.current.selectedStatuses).toEqual(['ready']);
  });

  it('drops selected tasks that a filter hides from the columns, so bulk actions never reach unseen cards', () => {
    const { result, rerender } = renderHook(
      (props: { visible: KanbanTask[] }) =>
        useKanbanSelection({
          boardId: 'board-1',
          tasks: TASKS,
          columnTasks: columnsOf(props.visible),
          laneByProfile: false,
        }),
      { initialProps: { visible: TASKS } },
    );
    act(() => result.current.handleTaskSelect('ready-1', CMD));
    act(() => result.current.handleTaskSelect('backlog-1', CMD));

    rerender({ visible: TASKS.filter((task) => task.task_id !== 'backlog-1') });

    expect(result.current.selectedTaskIds).toEqual(['ready-1']);
    expect(result.current.selectedStatuses).toEqual(['ready']);
  });

  it('keeps the same array between renders while nothing changes', () => {
    const { result, rerender } = setup();
    act(() => result.current.handleTaskSelect('ready-1', CMD));
    const before = result.current.selectedTaskIds;

    rerender({ boardId: 'board-1', tasks: [...TASKS] });

    expect(result.current.selectedTaskIds).toBe(before);
  });

  it('selectOnly replaces the selection, e.g. with the tasks that failed', () => {
    const { result } = setup();
    act(() => result.current.handleTaskSelect('ready-1', CMD));
    act(() => result.current.handleTaskSelect('ready-2', CMD));

    act(() => result.current.selectOnly(['ready-2']));

    expect(result.current.selectedTaskIds).toEqual(['ready-2']);
  });

  it('clears the selection when the board changes, and does not bring it back on return', () => {
    const { result, rerender } = setup();
    act(() => result.current.handleTaskSelect('ready-1', CMD));

    rerender({ boardId: 'board-2', tasks: [makeTask('other', 'ready')] });
    expect(result.current.selectedTaskIds).toEqual([]);

    rerender({ boardId: 'board-1', tasks: TASKS });
    expect(result.current.selectedTaskIds).toEqual([]);
  });

  it('Escape clears the selection', () => {
    const { result } = setup();
    act(() => result.current.handleTaskSelect('ready-1', CMD));

    pressEscape();

    expect(result.current.selectedTaskIds).toEqual([]);
  });

  it('ignores an Escape that an open menu or dialog already used to close itself', () => {
    const { result } = setup();
    act(() => result.current.handleTaskSelect('ready-1', CMD));

    pressEscape(true);

    expect(result.current.selectedTaskIds).toEqual(['ready-1']);
  });

  it('listens for Escape only while something is selected', () => {
    const add = vi.spyOn(window, 'addEventListener');
    const remove = vi.spyOn(window, 'removeEventListener');
    const keydownCalls = (spy: { mock: { calls: unknown[][] } }) =>
      spy.mock.calls.filter(([type]) => type === 'keydown').length;

    const { result } = setup();
    expect(keydownCalls(add)).toBe(0);

    act(() => result.current.handleTaskSelect('ready-1', CMD));
    expect(keydownCalls(add)).toBe(1);

    act(() => result.current.clearSelection());
    expect(keydownCalls(remove)).toBe(1);

    add.mockRestore();
    remove.mockRestore();
  });
});
