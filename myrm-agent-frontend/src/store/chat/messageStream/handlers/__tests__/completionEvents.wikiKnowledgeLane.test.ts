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

describe('completionEvents wiki knowledge lane metadata', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockClearActivePlan.mockReset();
  });

  it('stores execution_lane and wiki metrics on MESSAGE_END', async () => {
    const messages: TestState['messages'] = [
      {
        messageId: 'msg-wiki',
        chatId: 'chat-1',
        role: 'assistant',
        content: '',
        createdAt: new Date(),
      },
    ];

    const state: TestState = {
      messages,
      messageAppeared: false,
      loading: true,
    };

    const ctx = {
      data: {
        type: 'message_end',
        messageId: 'msg-wiki',
        execution_lane: 'wiki_knowledge',
        wiki_confidence_score: 0.82,
        wiki_source_count: 2,
        completion_status: 'success',
      },
      recievedMessage: 'Answer text',
      state,
      actions: {
        setMessages: (updater: (draft: TestState) => void) => {
          updater(state);
        },
        _processSuggestions: vi.fn(),
        scheduleAutoSave: vi.fn(),
      },
      added: false,
    } as unknown as StreamCtx;

    await completionEvents(ctx);
    await vi.runAllTimersAsync();

    expect(state.messages[0].executionLane).toBe('wiki_knowledge');
    expect(state.messages[0].wikiConfidenceScore).toBe(0.82);
    expect(state.messages[0].wikiSourceCount).toBe(2);
  });
});
