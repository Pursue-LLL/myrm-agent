import { describe, expect, it } from 'vitest';

import type { TaskStatus } from '@/services/kanban';
import moveGuard from '@shared/config/kanban_move_guard.json';
import { NEXT_STATUSES } from '../kanban-styles';
import { isServerMoveAllowed, moveLabelKey, resolveMoveIntent } from '../kanban-transitions';

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

/** 前后端共用的 move 守卫表；服务端契约测试用真实 move 接口逐对核对它，这里只验证界面按它做判定。 */
const GUARD = moveGuard as Record<TaskStatus, TaskStatus[]>;

const PAIRS = ALL_STATUSES.flatMap((from) => ALL_STATUSES.filter((to) => to !== from).map((to) => [from, to] as const));

describe('shared move guard table', () => {
  it('lists every status as a source and only known statuses as targets', () => {
    expect(Object.keys(GUARD).sort()).toEqual([...ALL_STATUSES].sort());
    for (const [from, targets] of Object.entries(GUARD)) {
      expect(new Set(targets).size, `${from} lists a target twice`).toBe(targets.length);
      for (const to of targets) {
        expect(ALL_STATUSES, `${from} -> ${to}`).toContain(to);
      }
    }
  });
});

describe('resolveMoveIntent', () => {
  it.each(PAIRS)('%s -> %s follows the move guard table', (from, to) => {
    const intent = resolveMoveIntent(from, to);

    if (from === 'failed' && to === 'ready') {
      // 服务端不接受手动 move 出终态；界面把它当作「重试」，由重试接口承接。
      expect(intent).toBe('retry');
    } else if (!GUARD[from].includes(to)) {
      expect(intent).toBe('blocked');
    } else {
      expect(intent).toBe(to === 'archived' ? 'archive' : 'move');
    }
  });

  it('treats a no-op move as blocked', () => {
    expect(resolveMoveIntent('ready', 'ready')).toBe('blocked');
  });

  it('never offers a menu transition the server would reject', () => {
    for (const [from, targets] of Object.entries(NEXT_STATUSES) as [TaskStatus, TaskStatus[]][]) {
      for (const to of targets) {
        expect(resolveMoveIntent(from, to), `${from} -> ${to}`).not.toBe('blocked');
      }
    }
  });
});

describe('isServerMoveAllowed', () => {
  it.each<[TaskStatus, TaskStatus, boolean]>([
    ['ready', 'running', true],
    ['blocked', 'ready', true],
    ['triage', 'running', false],
    ['triage', 'backlog', true],
    ['completed', 'ready', false],
    ['completed', 'archived', true],
    ['running', 'in_review', false],
    ['in_review', 'completed', false],
  ])('%s -> %s is allowed: %s', (from, to, allowed) => {
    expect(isServerMoveAllowed(from, to)).toBe(allowed);
  });

  /** 守卫不特判「原地不动」：只有终态、草稿池、审核态任务移到自己当前的状态也被拒；归档到归档放行。 */
  it.each<[TaskStatus, boolean]>([
    ['completed', false],
    ['failed', false],
    ['in_review', false],
    ['triage', false],
    ['ready', true],
    ['blocked', true],
    ['archived', true],
  ])('a %s task moved to its own status is allowed: %s', (status, allowed) => {
    expect(isServerMoveAllowed(status, status)).toBe(allowed);
  });
});

describe('moveLabelKey', () => {
  it('labels failed -> ready as a retry', () => {
    expect(moveLabelKey('failed', 'ready')).toBe('retryAction');
  });

  it('keeps the move label for every other transition', () => {
    expect(moveLabelKey('ready', 'running')).toBe('moveTo.running');
    expect(moveLabelKey('failed', 'archived')).toBe('moveTo.archived');
  });
});
