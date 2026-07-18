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

vi.mock('@/services/chat', () => ({
  getChatDetail: vi.fn(async () => ({ chat: {} })),
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    GOAL_STATUS: 'goal_status',
    FILE_MUTATION_FAILED: 'file_mutation_failed',
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
}));

import { completionEvents } from '../completionEvents';
import type { StreamCtx } from '../../streamContext';

type TestState = {
  messages: Array<Record<string, unknown>>;
  messageAppeared: boolean;
  loading: boolean;
};

function makeCtx(state: TestState): StreamCtx {
  return {
    data: {
      type: 'message_end',
      messageId: 'msg-1',
      memory_brief_status: {
        state: 'skipped',
        reason: 'timeout',
        injection: { state: 'applied', source: 'fallback' },
      },
    } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: 'done',
    state: state as never,
    actions: {
      setMessages: (updater: (draft: TestState) => void) => updater(state),
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      _processSuggestions: vi.fn(),
      scheduleAutoSave: vi.fn(),
    } as never,
    files: [],
  };
}

describe('completionEvents memory brief status', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockClearActivePlan.mockReset();
  });

  it('stores memory_brief_status on assistant message after MESSAGE_END', async () => {
    const state: TestState = {
      messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() }],
      messageAppeared: false,
      loading: true,
    };
    const ctx = makeCtx(state);

    await completionEvents(ctx);
    vi.runAllTimers();
    await vi.dynamicImportSettled();

    expect(state.messages[0]?.memoryBriefStatus).toEqual({
      state: 'skipped',
      reason: 'timeout',
      injection: { state: 'applied', source: 'fallback' },
    });
  });

  it('creates assistant placeholder when memory_brief_status arrives before assistant message', async () => {
    const state: TestState = {
      messages: [{ messageId: 'user-1', chatId: 'c1', role: 'user', content: 'hello', createdAt: new Date() }],
      messageAppeared: false,
      loading: true,
    };
    const ctx = makeCtx(state);

    await completionEvents(ctx);
    vi.runAllTimers();
    await vi.dynamicImportSettled();

    expect(state.messages).toHaveLength(2);
    expect(state.messages[1]?.role).toBe('assistant');
    expect(state.messages[1]?.memoryBriefStatus).toEqual({
      state: 'skipped',
      reason: 'timeout',
      injection: { state: 'applied', source: 'fallback' },
    });
  });
});
