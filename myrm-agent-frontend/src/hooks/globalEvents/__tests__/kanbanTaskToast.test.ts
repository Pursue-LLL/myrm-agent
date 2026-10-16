import { beforeEach, describe, expect, it, vi } from 'vitest';
import blockedReasons from '@shared/config/kanban_blocked_reasons.json';

import { showKanbanTaskToast } from '@/hooks/globalEvents/kanbanTaskToast';

const t = (key: string) => `notifications:${key}`;
const tKanban = (key: string) => `kanban:${key}`;

describe('showKanbanTaskToast', () => {
  const pushToast = { success: vi.fn(), warning: vi.fn() };
  const notifyIfLeader = vi.fn();
  const show = (data: Record<string, unknown>) => showKanbanTaskToast(data, { t, tKanban, pushToast, notifyIfLeader });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a blocked reason the server wrote in the interface language, in the toast and the notification', () => {
    show({ action: 'task_blocked', title: 'Write docs', detail: blockedReasons.parentMergeFailed });

    const description = 'kanban:blockedReason.parentMergeFailed';
    expect(pushToast.warning).toHaveBeenCalledWith('notifications:kanbanTaskBlocked: Write docs', {
      description,
      duration: 10_000,
      dismissible: true,
    });
    expect(notifyIfLeader).toHaveBeenCalledWith('notifications:kanbanTaskBlocked: Write docs', description);
  });

  it('shows a reason it does not know as written, cut to 200 characters', () => {
    show({ action: 'task_failed', title: 'Build', detail: 'x'.repeat(250) });

    expect(pushToast.warning).toHaveBeenCalledWith(
      'notifications:kanbanTaskFailed: Build',
      expect.objectContaining({ description: 'x'.repeat(200) }),
    );
  });

  it('reports a completed task as a success without a description when the server sent no detail', () => {
    show({ action: 'task_completed', title: 'Ship' });

    expect(pushToast.success).toHaveBeenCalledWith('notifications:kanbanTaskCompleted: Ship', {
      description: undefined,
      duration: 8_000,
      dismissible: true,
    });
    expect(pushToast.warning).not.toHaveBeenCalled();
  });

  it('treats a card moved to blocked like a blocked task', () => {
    show({ action: 'moved', status: 'blocked', title: 'Review' });

    expect(pushToast.warning).toHaveBeenCalledWith(
      'notifications:kanbanTaskBlocked: Review',
      expect.objectContaining({ duration: 10_000 }),
    );
  });

  it.each([
    ['a task that only started', { action: 'task_started', title: 'Run' }],
    ['a card moved to a non-terminal column', { action: 'moved', status: 'ready', title: 'Run' }],
    ['an event without a title or task id', { action: 'task_blocked' }],
  ])('stays silent for %s', (_name, data) => {
    show(data);

    expect(pushToast.success).not.toHaveBeenCalled();
    expect(pushToast.warning).not.toHaveBeenCalled();
    expect(notifyIfLeader).not.toHaveBeenCalled();
  });
});
