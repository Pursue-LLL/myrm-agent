import { describe, it, expect } from 'vitest';
import { deriveTaskDecisionFrame, filterTasksByResponsibility } from '../kanbanDecisionFrame';
import type { KanbanTask } from '@/services/kanban';

function mockTask(partial: Partial<KanbanTask>): KanbanTask {
  return {
    task_id: 'task-1',
    board_id: 'board-1',
    title: 'Test Task',
    description: '',
    status: 'ready',
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
    created_at: '2026-08-20T00:00:00Z',
    updated_at: '2026-08-20T00:00:00Z',
    ...partial,
  };
}

describe('kanbanDecisionFrame', () => {
  it('derives correct decision frame for in_review task (needs human review)', () => {
    const task = mockTask({ status: 'in_review' });
    const frame = deriveTaskDecisionFrame(task);
    expect(frame.waitingEntity).toBe('human');
    expect(frame.safetyTier).toBe('hitl_guarded');
    expect(frame.responsibility).toBe('needs_action');
    expect(frame.hasAttention).toBe(true);
    expect(frame.recommendedActionKey).toBe('decisionFrame.actionReview');
  });

  it('derives correct decision frame for human-blocked task', () => {
    const task = mockTask({ status: 'blocked', block_kind: 'human' });
    const frame = deriveTaskDecisionFrame(task);
    expect(frame.waitingEntity).toBe('human');
    expect(frame.safetyTier).toBe('hitl_guarded');
    expect(frame.responsibility).toBe('needs_action');
    expect(frame.hasAttention).toBe(true);
  });

  it('derives correct decision frame for system-blocked task', () => {
    const task = mockTask({ status: 'blocked', block_kind: 'scheduled' });
    const frame = deriveTaskDecisionFrame(task);
    expect(frame.waitingEntity).toBe('system');
    expect(frame.safetyTier).toBe('neutral');
    expect(frame.responsibility).toBe('autonomous');
    expect(frame.hasAttention).toBe(false);
  });

  it('derives correct decision frame for failed task', () => {
    const task = mockTask({ status: 'failed', error: 'Syntax error' });
    const frame = deriveTaskDecisionFrame(task);
    expect(frame.waitingEntity).toBe('human');
    expect(frame.safetyTier).toBe('hitl_guarded');
    expect(frame.responsibility).toBe('needs_action');
    expect(frame.hasAttention).toBe(true);
  });

  it('derives correct decision frame for running task with completion intent', () => {
    const task = mockTask({
      status: 'running',
      metadata: { completion_intent: true },
    });
    const frame = deriveTaskDecisionFrame(task);
    expect(frame.waitingEntity).toBe('agent');
    expect(frame.safetyTier).toBe('safe_auto');
    expect(frame.responsibility).toBe('autonomous');
    expect(frame.hasAttention).toBe(false);
    expect(frame.recommendedActionKey).toBe('decisionFrame.actionVerifying');
  });

  it('filters tasks by responsibility correctly', () => {
    const tasks: KanbanTask[] = [
      mockTask({ task_id: '1', status: 'in_review' }),
      mockTask({ task_id: '2', status: 'running' }),
      mockTask({ task_id: '3', status: 'failed' }),
      mockTask({ task_id: '4', status: 'completed' }),
    ];

    const needsAction = filterTasksByResponsibility(tasks, 'needs_action');
    expect(needsAction.map((t) => t.task_id)).toEqual(['1', '3']);

    const autonomous = filterTasksByResponsibility(tasks, 'autonomous');
    expect(autonomous.map((t) => t.task_id)).toEqual(['2', '4']);

    const all = filterTasksByResponsibility(tasks, 'all');
    expect(all.length).toBe(4);
  });
});
