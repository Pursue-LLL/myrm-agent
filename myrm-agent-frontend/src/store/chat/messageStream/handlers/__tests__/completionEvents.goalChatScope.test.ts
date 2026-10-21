/**
 * Real scenario: a goal's stream in chat A reports its last status while the user has already opened chat B. The status
 * belongs to chat A and must not replace the goal shown for chat B.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ clearActivePlan: vi.fn() }) },
}));

vi.mock('@/services/notification', () => ({
  notificationService: { notify: vi.fn() },
}));

vi.mock('@/lib/utils/completionSound', () => ({
  playCompletionSound: vi.fn(() => false),
  dispatchPetSurfaceAwayCompletion: vi.fn(),
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
  normalizeGoalState: (raw: { goal_id: string; status: string }) => ({
    goalId: raw.goal_id,
    objective: raw.goal_id,
    status: raw.status,
    tokensUsed: 0,
    timeUsedSeconds: 0,
  }),
  useChatStore: { getState: vi.fn(() => ({ chatId: 'chat-a', setWorkspaceDir: vi.fn() })) },
  useConfigStore: { getState: () => ({ enableCompletionSound: false, enableWebNotifications: false }) },
  useToolApprovalStore: { getState: vi.fn(() => ({ unmarkProcessing: vi.fn() })) },
  playCompletionSound: vi.fn(() => false),
  dispatchPetSurfaceAwayCompletion: vi.fn(),
  releaseInspectorControls: vi.fn(),
  resolveStreamChatId: (state: { chatId?: string }) => state.chatId?.trim() ?? '',
  isStreamForOpenChat: (state: { chatId?: string }) => (state.chatId?.trim() ?? '') === 'chat-a',
}));

import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { completionEvents } from '../completionEvents';
import type { StreamCtx } from '../../streamContext';

/** The stream of `streamChatId`, as it was when the message was sent, delivering `data`. */
function streamOf(streamChatId: string, data: Record<string, unknown>): StreamCtx {
  return {
    data: { messageId: 'msg-1', ...data } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: 'done',
    state: { chatId: streamChatId, messages: [], messageAppeared: false, loading: true } as never,
    actions: {
      setMessages: vi.fn(),
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      _processSuggestions: vi.fn(),
      scheduleAutoSave: vi.fn(),
    } as never,
    files: [],
  };
}

const goalOf = (goalId: string, status: string) => ({ goal_id: goalId, status });

describe('completionEvents goal status of a stream', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useGoalStore.setState({ chatId: null, activeGoal: null, gitBranch: null, queuedGoals: [] });
  });

  it.each([
    ['goal_status', { type: 'goal_status', data: goalOf('goal-a', 'complete') }],
    ['message_end', { type: 'message_end', goal_status: goalOf('goal-a', 'complete') }],
  ])('shows the status of its own chat on %s', async (_event, data) => {
    useGoalStore.getState().bindChat('chat-a');

    await completionEvents(streamOf('chat-a', data));
    await vi.dynamicImportSettled();

    expect(useGoalStore.getState().activeGoal?.goalId).toBe('goal-a');
  });

  it.each([
    ['goal_status', { type: 'goal_status', data: goalOf('goal-a', 'complete') }],
    ['message_end', { type: 'message_end', goal_status: goalOf('goal-a', 'complete') }],
  ])('leaves the goal of the chat that is open now alone on %s', async (_event, data) => {
    useGoalStore.getState().bindChat('chat-b');
    useGoalStore.getState().setActiveGoal('chat-b', {
      goalId: 'goal-b',
      objective: 'goal-b',
      status: 'active',
      tokensUsed: 0,
      timeUsedSeconds: 0,
    });

    await completionEvents(streamOf('chat-a', data));
    await vi.dynamicImportSettled();

    expect(useGoalStore.getState().activeGoal?.goalId).toBe('goal-b');
    expect(useGoalStore.getState().activeGoal?.status).toBe('active');
  });
});
