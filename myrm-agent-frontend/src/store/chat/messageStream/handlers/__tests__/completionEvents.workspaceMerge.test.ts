import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ clearActivePlan: vi.fn() }) },
}));

vi.mock('@/store/chat/goals/useGoalStore', () => ({
  useGoalStore: { getState: () => ({ setActiveGoal: vi.fn() }) },
}));

vi.mock('@/services/notification', () => ({
  notificationService: { notify: vi.fn() },
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    WORKSPACE_MERGE_FAILED: 'workspace_merge_failed',
    MESSAGE_END: 'message_end',
  },
  findAssistantMessageIndex: vi.fn((messages: Array<{ messageId: string; role: string }>, messageId: string) =>
    messages.findIndex((msg) => msg.role === 'assistant' && msg.messageId === messageId),
  ),
  normalizeGoalState: vi.fn(),
  useChatStore: {
    getState: vi.fn(() => ({ chatId: 'c1', setWorkspaceDir: vi.fn() })),
  },
  useConfigStore: {
    getState: () => ({ enableCompletionSound: false, enableWebNotifications: false }),
  },
  useToolApprovalStore: {
    getState: vi.fn(() => ({ unmarkProcessing: vi.fn() })),
  },
  playCompletionSound: vi.fn(() => false),
  dispatchPetSurfaceAwayCompletion: vi.fn(),
}));

import { completionEvents } from '../completionEvents';
import type { StreamCtx } from '../../streamContext';

type TestState = {
  messages: Array<Record<string, unknown>>;
};

function makeMergeCtx(state: TestState, data: Record<string, unknown>): StreamCtx {
  return {
    data: data as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: state as never,
    actions: {
      setMessages: (updater: (draft: TestState) => void) => updater(state),
    } as never,
    files: [],
  };
}

describe('completionEvents workspace merge failures', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('stores workspaceMergeFailures with counts on WORKSPACE_MERGE_FAILED', async () => {
    const state: TestState = {
      messages: [{ messageId: 'msg-1', role: 'assistant', content: 'answer' }],
    };
    const ctx = makeMergeCtx(state, {
      type: 'workspace_merge_failed',
      messageId: 'msg-1',
      data: {
        failed_count: 3,
        truncated: 1,
        errors: [{ message: 'task_index=1: disk full' }],
      },
    });

    await completionEvents(ctx);

    expect(state.messages[0]?.workspaceMergeFailures).toEqual([
      { message: 'task_index=1: disk full' },
    ]);
    expect(state.messages[0]?.workspaceMergeFailedCount).toBe(3);
    expect(state.messages[0]?.workspaceMergeTruncated).toBe(1);
  });

  it('ignores WORKSPACE_MERGE_FAILED when assistant message is missing', async () => {
    const state: TestState = {
      messages: [{ messageId: 'other', role: 'assistant', content: 'x' }],
    };
    const ctx = makeMergeCtx(state, {
      type: 'workspace_merge_failed',
      messageId: 'msg-1',
      data: { errors: [{ message: 'boom' }] },
    });

    await completionEvents(ctx);

    expect(state.messages[0]?.workspaceMergeFailures).toBeUndefined();
  });
});
