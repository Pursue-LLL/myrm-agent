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

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      clearSubagentPromptTimer: vi.fn(),
      setSubagentPromptVisible: vi.fn(),
      initializeChat: vi.fn(),
      addEnvironmentAlert: vi.fn(),
    }),
  },
}));

const createStatefulActions = (state: StreamHandlerState): StreamHandlerActions => ({
  setMessages: (updater) => updater(state),
  setMessageAppeared: () => undefined,
  setLoading: () => undefined,
  _processSuggestions: async () => undefined,
  scheduleAutoSave: () => undefined,
});

describe('messageStreamHandler reasoning duration tracking', () => {
  const BASE_TIME = 1700000000000;
  let originalDateNow: () => number;
  let originalSetTimeout: typeof globalThis.setTimeout;
  let mockedNow: number;
  let pendingTimeouts: Array<() => void>;

  beforeEach(() => {
    mockedNow = BASE_TIME;
    originalDateNow = Date.now;
    Date.now = () => mockedNow;

    pendingTimeouts = [];
    originalSetTimeout = globalThis.setTimeout;
    // @ts-expect-error override for test
    globalThis.setTimeout = (fn: () => void) => {
      pendingTimeouts.push(fn);
      return 0;
    };
  });

  afterEach(() => {
    Date.now = originalDateNow;
    globalThis.setTimeout = originalSetTimeout;
  });

  function flushTimeouts() {
    while (pendingTimeouts.length > 0) {
      const fn = pendingTimeouts.shift()!;
      fn();
    }
  }

  it('records reasoningStartedAt on first REASONING event', async () => {
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:00:00Z'),
      content: '',
      role: 'assistant',
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.REASONING,
        messageId: 'assistant-1',
        data: 'Let me think about this...',
      } as unknown as Parameters<typeof handleMessageStream>[0],
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    flushTimeouts();

    expect(state.messages[0].reasoningStartedAt).toBe(BASE_TIME);
    expect(state.messages[0].reasoning).toBe('Let me think about this...');
  });

  it('does not overwrite reasoningStartedAt on subsequent REASONING events', async () => {
    const firstTimestamp = BASE_TIME;
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:00:00Z'),
      content: '',
      role: 'assistant',
      reasoning: 'First chunk',
      reasoningStartedAt: firstTimestamp,
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: true,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    mockedNow = BASE_TIME + 3000;

    await handleMessageStream(
      {
        type: AgentEventType.REASONING,
        messageId: 'assistant-1',
        data: ' second chunk',
      } as unknown as Parameters<typeof handleMessageStream>[0],
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    flushTimeouts();

    expect(state.messages[0].reasoningStartedAt).toBe(firstTimestamp);
    expect(state.messages[0].reasoning).toBe('First chunk second chunk');
  });

  it('calculates reasoningDurationMs when first MESSAGE event arrives', async () => {
    const startTime = BASE_TIME;
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:00:00Z'),
      content: '',
      role: 'assistant',
      reasoning: 'Thinking...',
      reasoningStartedAt: startTime,
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: true,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    mockedNow = BASE_TIME + 5000;

    await handleMessageStream(
      {
        type: AgentEventType.MESSAGE,
        messageId: 'assistant-1',
        data: 'Here is my answer',
      } as unknown as Parameters<typeof handleMessageStream>[0],
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    flushTimeouts();

    expect(state.messages[0].reasoningDurationMs).toBe(5000);
  });

  it('does not overwrite reasoningDurationMs on subsequent MESSAGE events', async () => {
    const startTime = BASE_TIME;
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:00:00Z'),
      content: 'Part one',
      role: 'assistant',
      reasoning: 'Thinking...',
      reasoningStartedAt: startTime,
      reasoningDurationMs: 5000,
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: true,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    mockedNow = BASE_TIME + 8000;

    await handleMessageStream(
      {
        type: AgentEventType.MESSAGE,
        messageId: 'assistant-1',
        data: ' more content',
      } as unknown as Parameters<typeof handleMessageStream>[0],
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    flushTimeouts();

    expect(state.messages[0].reasoningDurationMs).toBe(5000);
  });

  it('finalizes reasoningDurationMs on MESSAGE_END when no MESSAGE was received (budget_exhausted)', async () => {
    const startTime = BASE_TIME;
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:00:00Z'),
      content: '',
      role: 'assistant',
      reasoning: 'Deep reasoning...',
      reasoningStartedAt: startTime,
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: true,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    mockedNow = BASE_TIME + 12000;

    await handleMessageStream(
      {
        type: AgentEventType.MESSAGE_END,
        messageId: 'assistant-1',
        completion_status: 'thinking_budget_exhausted',
        usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 },
      } as unknown as Parameters<typeof handleMessageStream>[0],
      '',
      undefined,
      true,
      '',
      state,
      createStatefulActions(state),
    );

    flushTimeouts();

    expect(state.messages[0].reasoningDurationMs).toBe(12000);
  });

  it('does not set reasoningDurationMs if reasoningStartedAt was never set', async () => {
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:00:00Z'),
      content: '',
      role: 'assistant',
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: true,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.MESSAGE,
        messageId: 'assistant-1',
        data: 'Direct answer without reasoning',
      } as unknown as Parameters<typeof handleMessageStream>[0],
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    flushTimeouts();

    expect(state.messages[0].reasoningDurationMs).toBeUndefined();
    expect(state.messages[0].reasoningStartedAt).toBeUndefined();
  });

  it('ignores empty REASONING data', async () => {
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:00:00Z'),
      content: '',
      role: 'assistant',
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.REASONING,
        messageId: 'assistant-1',
        data: '',
      } as unknown as Parameters<typeof handleMessageStream>[0],
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    flushTimeouts();

    expect(state.messages[0].reasoningStartedAt).toBeUndefined();
    expect(state.messages[0].reasoning).toBeUndefined();
  });

  it('handles REASONING event for non-existent messageId without crash', async () => {
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:00:00Z'),
      content: '',
      role: 'assistant',
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.REASONING,
        messageId: 'non-existent-id',
        data: 'Some reasoning for unknown message',
      } as unknown as Parameters<typeof handleMessageStream>[0],
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    flushTimeouts();

    expect(state.messages[0].reasoningStartedAt).toBeUndefined();
    expect(state.messages[0].reasoning).toBeUndefined();
  });

  it('isolates reasoning tracking between different messageIds', async () => {
    const msg1: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:00:00Z'),
      content: 'done',
      role: 'assistant',
      reasoning: 'Old reasoning',
      reasoningStartedAt: BASE_TIME - 10000,
      reasoningDurationMs: 3000,
    };
    const msg2: Message = {
      messageId: 'assistant-2',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:01:00Z'),
      content: '',
      role: 'assistant',
    };
    const state: StreamHandlerState = {
      messages: [msg1, msg2],
      messageAppeared: true,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.REASONING,
        messageId: 'assistant-2',
        data: 'New reasoning',
      } as unknown as Parameters<typeof handleMessageStream>[0],
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    flushTimeouts();

    expect(state.messages[0].reasoningDurationMs).toBe(3000);
    expect(state.messages[0].reasoningStartedAt).toBe(BASE_TIME - 10000);
    expect(state.messages[1].reasoning).toBe('New reasoning');
    expect(state.messages[1].reasoningStartedAt).toBe(BASE_TIME);
  });

  it('strips unicode control characters from reasoning content', async () => {
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-25T00:00:00Z'),
      content: '',
      role: 'assistant',
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    // Include actual control chars that UNICODE_CONTROL_RE filters: \x00-\x08, \x7F, \uFFFD
    await handleMessageStream(
      {
        type: AgentEventType.REASONING,
        messageId: 'assistant-1',
        data: 'Clean\x01text\x7F',
      } as unknown as Parameters<typeof handleMessageStream>[0],
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    flushTimeouts();

    expect(state.messages[0].reasoning).toBe('Cleantext');
    expect(state.messages[0].reasoningStartedAt).toBe(BASE_TIME);
  });
});
