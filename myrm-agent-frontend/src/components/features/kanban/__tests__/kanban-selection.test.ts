import { describe, expect, it } from 'vitest';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import {
  applyTaskClick,
  groupTasksIntoLanes,
  UNASSIGNED_LANE_KEY,
  visibleColumnTasks,
  type TaskClickContext,
} from '../kanban-selection';

function task(taskId: string, status: TaskStatus, agentId: string | null = null): KanbanTask {
  return {
    task_id: taskId,
    board_id: 'board-1',
    title: taskId,
    description: '',
    status,
    priority: 'normal',
    agent_id: agentId,
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

function groupByStatus(tasks: KanbanTask[]): Record<TaskStatus, KanbanTask[]> {
  const grouped = Object.fromEntries(STATUSES.map((status) => [status, [] as KanbanTask[]])) as Record<
    TaskStatus,
    KanbanTask[]
  >;
  for (const item of tasks) {
    grouped[item.status].push(item);
  }
  return grouped;
}

function context(tasks: KanbanTask[], overrides: Partial<TaskClickContext> = {}): TaskClickContext {
  return {
    tasks,
    columnTasks: groupByStatus(tasks),
    laneByProfile: false,
    agentNameMap: new Map(),
    collapsedAgents: new Set(),
    ...overrides,
  };
}

const toggle = (selected: string[], taskId: string, ctx: TaskClickContext) =>
  applyTaskClick(selected, { taskId, extendRange: false }, ctx);
const extend = (selected: string[], taskId: string, ctx: TaskClickContext) =>
  applyTaskClick(selected, { taskId, extendRange: true }, ctx);

describe('applyTaskClick toggling', () => {
  const ctx = context([task('a', 'ready'), task('b', 'ready')]);

  it('adds an unselected task and removes a selected one', () => {
    expect(toggle([], 'a', ctx)).toEqual(['a']);
    expect(toggle(['a'], 'b', ctx)).toEqual(['a', 'b']);
    expect(toggle(['a', 'b'], 'a', ctx)).toEqual(['b']);
  });

  it('selects just the clicked task when there is no anchor to extend from', () => {
    expect(extend([], 'a', ctx)).toEqual(['a']);
  });
});

describe('applyTaskClick range selection', () => {
  // The API order interleaves columns, as it does in production.
  const TASKS = [
    task('ready-1', 'ready'),
    task('backlog-1', 'backlog'),
    task('running-1', 'running'),
    task('ready-2', 'ready'),
    task('ready-3', 'ready'),
  ];

  it('covers only the cards between the two clicks inside the anchor column', () => {
    expect(extend(['ready-1'], 'ready-3', context(TASKS))).toEqual(['ready-1', 'ready-2', 'ready-3']);
  });

  it('never picks up cards from other columns that sit between them in the API order', () => {
    const result = extend(['ready-1'], 'ready-2', context(TASKS));

    expect(result).toEqual(['ready-1', 'ready-2']);
    expect(result).not.toContain('backlog-1');
    expect(result).not.toContain('running-1');
  });

  it('follows the order shown in the column, not the API order', () => {
    const shown = [task('ready-3', 'ready'), task('ready-1', 'ready'), task('ready-2', 'ready')];
    const ctx = context(TASKS, { columnTasks: { ...groupByStatus(TASKS), ready: shown } });

    expect(extend(['ready-3'], 'ready-2', ctx)).toEqual(['ready-3', 'ready-1', 'ready-2']);
  });

  it('skips cards the column does not show (filtered out)', () => {
    const shown = [task('ready-1', 'ready'), task('ready-3', 'ready')];
    const ctx = context(TASKS, { columnTasks: { ...groupByStatus(TASKS), ready: shown } });

    expect(extend(['ready-1'], 'ready-3', ctx)).toEqual(['ready-1', 'ready-3']);
  });

  it('falls back to a single toggle when the anchor is in another column', () => {
    expect(extend(['backlog-1'], 'ready-2', context(TASKS))).toEqual(['backlog-1', 'ready-2']);
  });

  it('falls back to a single toggle when the anchor is no longer shown', () => {
    const ctx = context(TASKS, { columnTasks: { ...groupByStatus(TASKS), ready: [task('ready-2', 'ready')] } });

    expect(extend(['ready-1'], 'ready-2', ctx)).toEqual(['ready-1', 'ready-2']);
  });

  it('keeps earlier selections and does not duplicate ids', () => {
    expect(extend(['backlog-1', 'ready-1'], 'ready-3', context(TASKS))).toEqual([
      'backlog-1',
      'ready-1',
      'ready-2',
      'ready-3',
    ]);
  });
});

describe('running column lanes', () => {
  const NAMES = new Map([
    ['agent-a', 'Alpha'],
    ['agent-b', 'Bravo'],
  ]);
  const TASKS = [
    task('a1', 'running', 'agent-a'),
    task('b1', 'running', 'agent-b'),
    task('a2', 'running', 'agent-a'),
    task('u1', 'running', null),
  ];

  it('groups tasks by agent, sorted by name, with unassigned last', () => {
    const lanes = groupTasksIntoLanes(TASKS, NAMES);

    expect(lanes.map(([agentId]) => agentId)).toEqual(['agent-a', 'agent-b', null]);
    expect(lanes[0][1].map((item) => item.task_id)).toEqual(['a1', 'a2']);
  });

  it('shows the cards lane by lane when lanes are on', () => {
    const ctx = context(TASKS, { laneByProfile: true, agentNameMap: NAMES });

    expect(visibleColumnTasks('running', ctx.columnTasks.running, ctx).map((item) => item.task_id)).toEqual([
      'a1',
      'a2',
      'b1',
      'u1',
    ]);
    expect(extend(['a1'], 'b1', ctx)).toEqual(['a1', 'a2', 'b1']);
  });

  it('leaves out cards of a collapsed lane, which the user cannot see', () => {
    const ctx = context(TASKS, {
      laneByProfile: true,
      agentNameMap: NAMES,
      collapsedAgents: new Set(['agent-b', UNASSIGNED_LANE_KEY]),
    });

    expect(visibleColumnTasks('running', ctx.columnTasks.running, ctx).map((item) => item.task_id)).toEqual([
      'a1',
      'a2',
    ]);
  });

  it('keeps the plain order when there is only one lane, since no lane headers are drawn', () => {
    const single = [task('a1', 'running', 'agent-a'), task('a2', 'running', 'agent-a')];
    const ctx = context(single, { laneByProfile: true, agentNameMap: NAMES, collapsedAgents: new Set(['agent-a']) });

    expect(visibleColumnTasks('running', ctx.columnTasks.running, ctx).map((item) => item.task_id)).toEqual([
      'a1',
      'a2',
    ]);
  });

  it('does not use lanes for other columns or when lanes are off', () => {
    const ready = [task('r1', 'ready', 'agent-b'), task('r2', 'ready', 'agent-a')];
    const ctx = context([...ready, ...TASKS], { laneByProfile: true, agentNameMap: NAMES });

    expect(visibleColumnTasks('ready', ctx.columnTasks.ready, ctx).map((item) => item.task_id)).toEqual(['r1', 'r2']);
    const lanesOff = context(TASKS, { laneByProfile: false, agentNameMap: NAMES });
    expect(visibleColumnTasks('running', lanesOff.columnTasks.running, lanesOff).map((item) => item.task_id)).toEqual([
      'a1',
      'b1',
      'a2',
      'u1',
    ]);
  });
});
