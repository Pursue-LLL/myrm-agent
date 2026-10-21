import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  BACKGROUND_TASKS_CHANGED_EVENT,
  notifyBackgroundTasksChangedForShellJobFinish,
} from '@/services/backgroundTasksRefresh';

describe('notifyBackgroundTasksChangedForShellJobFinish', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('dispatches refresh event for shell background job finish', () => {
    const listener = vi.fn();
    window.addEventListener(BACKGROUND_TASKS_CHANGED_EVENT, listener);

    notifyBackgroundTasksChangedForShellJobFinish({
      kind: 'background_job_finish',
      chat_id: 'chat-export-1',
    });

    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(BACKGROUND_TASKS_CHANGED_EVENT, listener);
  });

  it('ignores non-finish notifications', () => {
    const listener = vi.fn();
    window.addEventListener(BACKGROUND_TASKS_CHANGED_EVENT, listener);

    notifyBackgroundTasksChangedForShellJobFinish({
      kind: 'goal_needs_review',
      chat_id: 'chat-export-1',
    });

    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(BACKGROUND_TASKS_CHANGED_EVENT, listener);
  });

  it('ignores finish without chat_id', () => {
    const listener = vi.fn();
    window.addEventListener(BACKGROUND_TASKS_CHANGED_EVENT, listener);

    notifyBackgroundTasksChangedForShellJobFinish({
      kind: 'background_job_finish',
      chat_id: '   ',
    });

    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(BACKGROUND_TASKS_CHANGED_EVENT, listener);
  });
});
