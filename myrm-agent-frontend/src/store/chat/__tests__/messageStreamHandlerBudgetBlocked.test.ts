import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdaptiveScheduler } from '../adaptiveScheduler';
import { handleMessageStream, type StreamHandlerActions, type StreamHandlerState } from '../messageStreamHandler';
import { AgentEventType, type Message } from '../types';

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    warning: vi.fn(),
  },
}));

vi.mock('@/utils/completionSound', () => ({
  playCompletionSound: vi.fn(() => false),
}));

vi.mock('@/services/chat', () => ({
  getChatDetail: vi.fn(async () => ({ chat: {} })),
}));

const createStatefulActions = (state: StreamHandlerState): StreamHandlerActions => ({
  setMessages: (updater) => updater(state),
  setMessageAppeared: () => undefined,
  setLoading: () => undefined,
  _processSuggestions: async () => undefined,
  scheduleAutoSave: () => undefined,
});

describe('messageStreamHandler budget_blocked', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('creates placeholder assistant on message_end when budget_blocked and no assistant exists', async () => {
    const userMessage: Message = {
      messageId: 'user-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-22T00:00:00Z'),
      content: 'Write my weekly report',
      role: 'user',
    };
    const state: StreamHandlerState = {
      messages: [userMessage],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.MESSAGE_END,
        messageId: 'assistant-budget-1',
        completion_status: 'budget_blocked',
        usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
      },
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    vi.runAllTimers();

    expect(state.messages).toHaveLength(2);
    expect(state.messages[1]).toMatchObject({
      messageId: 'assistant-budget-1',
      chatId: 'chat-1',
      role: 'assistant',
      content: '',
      completionStatus: 'budget_blocked',
    });
    expect(state.loading).toBe(false);
  });
});
