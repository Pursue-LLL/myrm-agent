import { beforeEach, describe, expect, it, vi } from 'vitest';
import blockedReasons from '@shared/config/kanban_blocked_reasons.json';

import { showKanbanTaskToast } from '@/hooks/globalEvents/kanbanTaskToast';

const t = (key: string) => `notifications:${key}`;
const tKanban = (key: string) => `kanban:${key}`;

describe('showKanbanTaskToast', () => {
  const pushToast = { success: vi.fn(), warning: vi.fn() };
  const notifyIfLeader = vi.fn();
  const router = { push: vi.fn() };
  const show = (data: Record<string, unknown>) =>
    showKanbanTaskToast(data, { t, tKanban, router, pushToast, notifyIfLeader });
  const boardAction = { label: 'notifications:viewKanbanBoard', onClick: expect.any(Function) };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a blocked reason the server wrote in the interface language, in the toast and the notification', () => {
    show({ action: 'task_blocked', title: 'Write docs', board_id: 'b1', detail: blockedReasons.parentMergeFailed });

    const description = 'kanban:blockedReason.parentMergeFailed';
    expect(pushToast.warning).toHaveBeenCalledWith('notifications:kanbanTaskBlocked: Write docs', {
      description,
      duration: 10_000,
      dismissible: true,
      action: boardAction,
    });
    expect(notifyIfLeader).toHaveBeenCalledWith(
      'notifications:kanbanTaskBlocked: Write docs',
      description,
      expect.any(Function),
    );
  });

  it('shows a reason it does not know as written, cut to 200 characters with an ellipsis', () => {
    show({ action: 'task_blocked', title: 'Build', detail: 'x'.repeat(250) });

    expect(pushToast.warning).toHaveBeenCalledWith(
      'notifications:kanbanTaskBlocked: Build',
      expect.objectContaining({ description: `${'x'.repeat(199)}…` }),
    );
  });

  it('does not cut a reason of exactly 200 characters', () => {
    show({ action: 'task_completed', title: 'Build', detail: 'x'.repeat(200) });

    expect(pushToast.success).toHaveBeenCalledWith(
      'notifications:kanbanTaskCompleted: Build',
      expect.objectContaining({ description: 'x'.repeat(200) }),
    );
  });

  it('reports a failed task without a description, as the server sends none', () => {
    show({ action: 'task_failed', title: 'Build', board_id: 'b1' });

    expect(pushToast.warning).toHaveBeenCalledWith('notifications:kanbanTaskFailed: Build', {
      description: undefined,
      duration: 10_000,
      dismissible: true,
      action: boardAction,
    });
    expect(notifyIfLeader).toHaveBeenCalledWith(
      'notifications:kanbanTaskFailed: Build',
      undefined,
      expect.any(Function),
    );
  });

  it('reports a completed task as a success without a description when the server sent no detail', () => {
    show({ action: 'task_completed', title: 'Ship', board_id: 'b1' });

    expect(pushToast.success).toHaveBeenCalledWith('notifications:kanbanTaskCompleted: Ship', {
      description: undefined,
      duration: 8_000,
      dismissible: true,
      action: boardAction,
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
    ['a block that waits for the user', { action: 'task_blocked', block_kind: 'human' }],
    ['a block that waits for an external event', { action: 'task_blocked', block_kind: 'external' }],
    ['a card moved to blocked that waits for the user', { action: 'moved', status: 'blocked', block_kind: 'human' }],
  ])('still interrupts for %s', (_name, extra) => {
    show({ ...extra, title: 'Review', detail: 'Need a decision' });

    expect(pushToast.warning).toHaveBeenCalledWith(
      'notifications:kanbanTaskBlocked: Review',
      expect.objectContaining({ description: 'Need a decision' }),
    );
    expect(notifyIfLeader).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['a completed task', { action: 'task_completed' }, 'success', 'completed'],
    ['a blocked task', { action: 'task_blocked' }, 'warning', 'blocked'],
    ['a failed task', { action: 'task_failed' }, 'warning', 'failed'],
    ['a card moved to failed', { action: 'moved', status: 'failed' }, 'warning', 'failed'],
  ] as const)(
    'opens the board on the column of %s from the toast action and from the notification click',
    (_name, extra, kind, status) => {
      show({ ...extra, title: 'Ship', board_id: 'board-7' });

      const options = pushToast[kind].mock.calls[0][1] as { action: { onClick: () => void } };
      options.action.onClick();
      expect(router.push).toHaveBeenLastCalledWith(`/settings/kanban?board_id=board-7&status=${status}`);

      (notifyIfLeader.mock.calls[0][2] as () => void)();
      expect(router.push).toHaveBeenCalledTimes(2);
      expect(router.push).toHaveBeenLastCalledWith(`/settings/kanban?board_id=board-7&status=${status}`);
    },
  );

  it('offers no action when the event names no board', () => {
    show({ action: 'task_failed', title: 'Build' });

    expect(pushToast.warning).toHaveBeenCalledWith(
      'notifications:kanbanTaskFailed: Build',
      expect.objectContaining({ action: undefined }),
    );
    expect(notifyIfLeader).toHaveBeenCalledWith('notifications:kanbanTaskFailed: Build', undefined, undefined);
  });

  it.each([
    ['a task that only started', { action: 'task_started', title: 'Run' }],
    ['a card moved to a non-terminal column', { action: 'moved', status: 'ready', title: 'Run' }],
    ['an event without a title or task id', { action: 'task_blocked' }],
    ['a scheduled block that resumes by itself', { action: 'task_blocked', title: 'Nightly', block_kind: 'scheduled' }],
    [
      'a card moved to a scheduled block',
      { action: 'moved', status: 'blocked', title: 'Nightly', block_kind: 'scheduled' },
    ],
  ])('stays silent for %s', (_name, data) => {
    show(data);

    expect(pushToast.success).not.toHaveBeenCalled();
    expect(pushToast.warning).not.toHaveBeenCalled();
    expect(notifyIfLeader).not.toHaveBeenCalled();
  });
});
