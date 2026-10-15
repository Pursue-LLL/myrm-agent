import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useKanbanDnD } from '../useKanbanDnD';
import { NEXT_STATUSES } from '../kanban-styles';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import type { DragEndEvent } from '@dnd-kit/core';

vi.mock('@dnd-kit/core', async () => {
  const actual = await vi.importActual<typeof import('@dnd-kit/core')>('@dnd-kit/core');
  return {
    ...actual,
    useSensor: vi.fn((sensor, options) => ({ sensor, options })),
    useSensors: vi.fn((...sensors) => sensors),
  };
});

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

function dragEnd(activeId: string, overId: string): DragEndEvent {
  return {
    active: { id: activeId, data: { current: undefined }, rect: { current: { initial: null, translated: null } } },
    over: {
      id: overId,
      data: { current: undefined },
      rect: { width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 },
      disabled: false,
    },
    activatorEvent: new Event('pointer'),
    collisions: [],
    delta: { x: 0, y: 0 },
  } as unknown as DragEndEvent;
}

const STATUSES: TaskStatus[] = [
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

describe('useKanbanDnD 不可达流转拦截', () => {
  const onMoveTask = vi.fn();
  const onBulkMove = vi.fn();
  const onMoveBlocked = vi.fn();

  const setup = (tasks: KanbanTask[], selectedTaskIds: string[] = []) =>
    renderHook(() => useKanbanDnD({ tasks, selectedTaskIds, onMoveTask, onBulkMove, onMoveBlocked }));

  const drop = (hook: ReturnType<typeof setup>, activeId: string, overId: TaskStatus) =>
    act(() => hook.result.current.handleDragEnd(dragEnd(activeId, overId)));

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each<[TaskStatus, TaskStatus]>([
    ['in_review', 'ready'],
    ['ready', 'in_review'],
    ['triage', 'running'],
    ['triage', 'failed'],
    ['completed', 'ready'],
    ['completed', 'failed'],
    ['failed', 'running'],
    ['failed', 'completed'],
  ])('%s → %s：落点就拦下，只提示一次，不发请求也不弹终态确认', (from, to) => {
    const hook = setup([makeTask('a', from)]);

    drop(hook, 'a', to);

    expect(onMoveBlocked).toHaveBeenCalledTimes(1);
    expect(onMoveTask).not.toHaveBeenCalled();
    expect(onBulkMove).not.toHaveBeenCalled();
    expect(hook.result.current.dropConfirmState).toBeNull();
  });

  it('卡片菜单提供的每一种流转，拖拽都不会被拦下', () => {
    const offered = (Object.entries(NEXT_STATUSES) as [TaskStatus, TaskStatus[]][]).flatMap(([from, targets]) =>
      targets.filter((to) => to !== 'archived').map((to) => [from, to] as const),
    );
    expect(offered.length).toBeGreaterThan(0);

    for (const [from, to] of offered) {
      const hook = setup([makeTask('a', from)]);
      drop(hook, 'a', to);
      expect(onMoveBlocked, `${from} → ${to}`).not.toHaveBeenCalled();
    }
  });

  it('失败 → 就绪放行给 onMoveTask，由看板的重试确认接管', () => {
    const hook = setup([makeTask('a', 'failed')]);

    drop(hook, 'a', 'ready');

    expect(onMoveTask).toHaveBeenCalledWith('a', 'ready');
    expect(onMoveBlocked).not.toHaveBeenCalled();
    expect(hook.result.current.dropConfirmState).toBeNull();
  });

  it('归档有自己的确认，拖拽层不重复弹终态确认', () => {
    const hook = setup([makeTask('a', 'ready')]);

    drop(hook, 'a', 'archived');

    expect(onMoveTask).toHaveBeenCalledWith('a', 'archived');
    expect(hook.result.current.dropConfirmState).toBeNull();
  });

  it('批量拖拽只搬能直接流转的卡片，被拦下的卡片合并成一次提示', () => {
    const hook = setup(
      [makeTask('a', 'ready'), makeTask('b', 'blocked'), makeTask('c', 'failed'), makeTask('d', 'completed')],
      ['a', 'b', 'c', 'd'],
    );

    drop(hook, 'a', 'running');

    expect(onBulkMove).toHaveBeenCalledWith(['a', 'b'], 'running');
    expect(onMoveBlocked).toHaveBeenCalledTimes(1);
  });

  it('批量拖拽里的失败卡片不会被当作普通流转搬进就绪', () => {
    const hook = setup([makeTask('a', 'backlog'), makeTask('b', 'failed')], ['a', 'b']);

    drop(hook, 'a', 'ready');

    expect(onMoveTask).toHaveBeenCalledWith('a', 'ready');
    expect(onMoveTask).toHaveBeenCalledTimes(1);
    expect(onBulkMove).not.toHaveBeenCalled();
    expect(onMoveBlocked).toHaveBeenCalledTimes(1);
  });

  it('批量拖拽全部不可达时什么都不搬，仍只提示一次', () => {
    const hook = setup([makeTask('a', 'completed'), makeTask('b', 'failed')], ['a', 'b']);

    drop(hook, 'a', 'running');

    expect(onMoveTask).not.toHaveBeenCalled();
    expect(onBulkMove).not.toHaveBeenCalled();
    expect(onMoveBlocked).toHaveBeenCalledTimes(1);
  });

  it('批量拖拽里本来就在目标列的卡片静默跳过，不算被拦下', () => {
    const hook = setup([makeTask('a', 'ready'), makeTask('b', 'running')], ['a', 'b']);

    drop(hook, 'a', 'running');

    expect(onMoveTask).toHaveBeenCalledWith('a', 'running');
    expect(onMoveBlocked).not.toHaveBeenCalled();
  });

  it('终态确认只带可流转的卡片，确认时不会把被拦下的卡片带回来', () => {
    const hook = setup([makeTask('a', 'ready'), makeTask('b', 'failed')], ['a', 'b']);

    drop(hook, 'a', 'completed');

    expect(onMoveBlocked).toHaveBeenCalledTimes(1);
    expect(hook.result.current.dropConfirmState).toEqual({ taskIds: ['a'], targetStatus: 'completed' });

    act(() => hook.result.current.handleDropConfirm());

    expect(onMoveTask).toHaveBeenCalledWith('a', 'completed');
    expect(onBulkMove).not.toHaveBeenCalled();
  });

  it('覆盖全部状态对：被拦下与否与服务端守卫一致，被拦下时一定没有任何请求', () => {
    const rejected = new Set<string>();
    for (const from of STATUSES) {
      for (const to of STATUSES) {
        const terminal = ['completed', 'failed', 'archived'].includes(from);
        const blocked =
          from !== to &&
          (from === 'in_review' ||
            to === 'in_review' ||
            (terminal && to !== 'archived' && !(from === 'failed' && to === 'ready')) ||
            (from === 'triage' && !['backlog', 'ready', 'archived'].includes(to)));
        if (blocked) {
          rejected.add(`${from}>${to}`);
        }
      }
    }

    for (const from of STATUSES) {
      for (const to of STATUSES.filter((s) => s !== from)) {
        onMoveBlocked.mockClear();
        onMoveTask.mockClear();
        const hook = setup([makeTask('a', from)]);
        drop(hook, 'a', to);

        const wasBlocked = onMoveBlocked.mock.calls.length === 1;
        expect(wasBlocked, `${from} → ${to}`).toBe(rejected.has(`${from}>${to}`));
        if (wasBlocked) {
          expect(onMoveTask).not.toHaveBeenCalled();
          expect(hook.result.current.dropConfirmState).toBeNull();
        }
      }
    }
  });
});
