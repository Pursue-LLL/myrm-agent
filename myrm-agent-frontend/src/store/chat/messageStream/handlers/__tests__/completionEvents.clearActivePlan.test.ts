/**
 * Tests that completionEvents calls clearActivePlan on MESSAGE_END.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockClearActivePlan = vi.fn();

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ clearActivePlan: mockClearActivePlan }) },
}));

vi.mock('@/store/chat/goals/useGoalStore', () => ({
  useGoalStore: { getState: () => ({ setActiveGoal: vi.fn() }) },
}));

vi.mock('@/services/notification', () => ({
  notificationService: { notify: vi.fn() },
}));

vi.mock('@/lib/utils/completionSound', () => ({
  playCompletionSound: vi.fn(() => false),
}));

vi.mock('@/services/chat', () => ({
  getChatDetail: vi.fn(async () => ({ chat: {} })),
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    GOAL_STATUS: 'goal_status',
    FILE_MUTATION_FAILED: 'file_mutation_failed',
    MESSAGE_END: 'message_end',
  },
  findAssistantMessageIndex: vi.fn(() => 0),
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
}));

import { completionEvents } from '../completionEvents';
import type { StreamCtx } from '../../streamContext';

function makeCtx(): StreamCtx {
  return {
    data: { type: 'message_end', messageId: 'msg-1' } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: 'done',
    state: {
      messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() }],
      messageAppeared: false,
      loading: true,
    } as never,
    actions: {
      setMessages: vi.fn((updater: (s: Record<string, unknown>) => void) => updater({
        messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() }],
        loading: true,
        messageAppeared: false,
      })),
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      _processSuggestions: vi.fn(),
      scheduleAutoSave: vi.fn(),
    } as never,
    files: [],
  };
}

describe('completionEvents clearActivePlan', () => {
  beforeEach(() => {
    mockClearActivePlan.mockClear();
    vi.useFakeTimers();
  });

  it('calls clearActivePlan on MESSAGE_END', async () => {
    const ctx = makeCtx();
    await completionEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockClearActivePlan).toHaveBeenCalledTimes(1);
  });

  it('does not call clearActivePlan for non-MESSAGE_END events', async () => {
    const ctx = makeCtx();
    ctx.data = { type: 'goal_status', data: {} } as never;
    await completionEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockClearActivePlan).not.toHaveBeenCalled();
  });
});
