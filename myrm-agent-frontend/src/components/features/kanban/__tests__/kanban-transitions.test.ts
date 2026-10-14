import { describe, expect, it } from 'vitest';

import type { TaskStatus } from '@/services/kanban';
import { NEXT_STATUSES } from '../kanban-styles';
import { moveLabelKey, resolveMoveIntent } from '../kanban-transitions';

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

/**
 * 服务端 move 守卫（move_orchestrator.move_task）对每个 (起点 → 终点) 的拒绝结果。
 * 数据来自对真实守卫逐对求值（9 × 8 = 72 对）；守卫规则变化时需同步更新这张表。
 */
const SERVER_REJECTED: Record<TaskStatus, TaskStatus[]> = {
  triage: ['running', 'blocked', 'in_review', 'completed', 'failed'],
  backlog: ['in_review'],
  ready: ['in_review'],
  running: ['in_review'],
  blocked: ['in_review'],
  in_review: ['triage', 'backlog', 'ready', 'running', 'blocked', 'completed', 'failed', 'archived'],
  completed: ['triage', 'backlog', 'ready', 'running', 'blocked', 'in_review', 'failed'],
  failed: ['triage', 'backlog', 'ready', 'running', 'blocked', 'in_review', 'completed'],
  archived: ['triage', 'backlog', 'ready', 'running', 'blocked', 'in_review', 'completed', 'failed'],
};

const PAIRS = ALL_STATUSES.flatMap((from) => ALL_STATUSES.filter((to) => to !== from).map((to) => [from, to] as const));

describe('resolveMoveIntent', () => {
  it.each(PAIRS)('%s -> %s agrees with the server move guard', (from, to) => {
    const rejectedByServer = SERVER_REJECTED[from].includes(to);
    const intent = resolveMoveIntent(from, to);

    if (from === 'failed' && to === 'ready') {
      // 服务端不接受手动 move 出终态；界面把它当作「重试」，由重试接口承接。
      expect(intent).toBe('retry');
    } else if (rejectedByServer) {
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

describe('moveLabelKey', () => {
  it('labels failed -> ready as a retry', () => {
    expect(moveLabelKey('failed', 'ready')).toBe('retryAction');
  });

  it('keeps the move label for every other transition', () => {
    expect(moveLabelKey('ready', 'running')).toBe('moveTo.running');
    expect(moveLabelKey('failed', 'archived')).toBe('moveTo.archived');
  });
});
