/**
 * Regression test: routing_decision followed by message / message_end must not
 * lose routingTier on the assistant message.
 *
 * Mirrors the real SSE event sequence from a simple turn:
 *   routing_decision (added=false) -> message (TEXT chunk) -> message_end
 */
import { describe, expect, it, vi } from 'vitest';
import { AdaptiveScheduler } from '../adaptiveScheduler';
import { handleMessageStream, type StreamHandlerActions, type StreamHandlerState } from '../messageStreamHandler';
import type { TurnMeta } from '../messageStream/handleMessageStream';
import { AgentEventType, type Message } from '../types';

vi.mock('@/lib/utils/toast', () => ({
  toast: { warning: vi.fn(), error: vi.fn() },
}));

const MESSAGE_ID = 'r-e2e-1';

const makeState = (): StreamHandlerState => {
  const userMessage: Message = {
    messageId: MESSAGE_ID,
    chatId: 'chat-1',
    createdAt: new Date('2026-06-04T00:00:00Z'),
    content: 'hello',
    role: 'user',
  };
  return {
    messages: [userMessage],
    messageAppeared: false,
    loading: true,
    scheduler: new AdaptiveScheduler(),
  };
};

const makeActions = (state: StreamHandlerState): StreamHandlerActions => ({
  setMessages: (updater) => updater(state),
  setMessageAppeared: (v) => {
    state.messageAppeared = v;
  },
  setLoading: (v) => {
    state.loading = v;
  },
  _processSuggestions: async () => undefined,
  scheduleAutoSave: () => undefined,
});

const serial = async (
  events: Array<Record<string, unknown>>,
  options?: { clearMessagesBeforeIndex?: number },
): Promise<StreamHandlerState> => {
  const state = makeState();
  const actions = makeActions(state);
  let added = false;
  let received = '';
  let meta: TurnMeta = {};
  for (let i = 0; i < events.length; i++) {
    if (options?.clearMessagesBeforeIndex === i) {
      state.messages = [];
    }
    const turn = await handleMessageStream(
      events[i] as never,
      '',
      undefined,
      added,
      received,
      state,
      actions,
      [],
      meta,
    );
    added = turn.added;
    received = turn.recievedMessage;
    if (turn.meta) {
      meta = turn.meta;
    }
  }
  state.scheduler.flush();
  state.scheduler.cancel();
  // MESSAGE_END applies its terminal payload (content, usage, ...) inside a
  // 50ms setTimeout; wait so assertions observe the finalized message.
  await new Promise((resolve) => setTimeout(resolve, 60));
  return state;
};

describe('routingTier retention across SSE sequence', () => {
  it('keeps routingTier when routing_decision arrives before message chunks', async () => {
    const state = await serial([
      {
        type: AgentEventType.ROUTING_DECISION,
        messageId: MESSAGE_ID,
        data: { tier: 'simple' },
      },
      {
        type: AgentEventType.MESSAGE,
        messageId: MESSAGE_ID,
        data: 'hello from llm',
      },
      {
        type: AgentEventType.MESSAGE_END,
        messageId: MESSAGE_ID,
        data: '',
        completion_status: 'success',
        model: 'MiniMax-M3',
      },
    ]);

    const assistant = state.messages.find((m) => m.role === 'assistant');
    expect(assistant, JSON.stringify(state.messages)).toBeDefined();
    expect(assistant?.routingTier).toBe('simple');
    expect(assistant?.content).toContain('hello from llm');
  });

  it('keeps routingTier when tools_snapshot arrives before routing_decision', async () => {
    const state = await serial([
      {
        type: AgentEventType.TOOL_START,
        messageId: MESSAGE_ID,
        step_key: 'tool_run',
        tool_name: 'grep',
        tool_call_id: 't1',
        data: [{ text: 'searching' }],
      },
      {
        type: AgentEventType.ROUTING_DECISION,
        messageId: MESSAGE_ID,
        data: { tier: 'simple' },
      },
      {
        type: AgentEventType.MESSAGE,
        messageId: MESSAGE_ID,
        data: 'final answer',
      },
      {
        type: AgentEventType.MESSAGE_END,
        messageId: MESSAGE_ID,
        data: '',
        completion_status: 'success',
        model: 'MiniMax-M3',
      },
    ]);

    const assistant = state.messages.find((m) => m.role === 'assistant');
    expect(assistant, JSON.stringify(state.messages)).toBeDefined();
    expect(assistant?.routingTier).toBe('simple');
    expect(assistant?.content).toContain('final answer');
  });

  it('restores routingTier when the store is cleared before message_end (attach/initializeChat race)', async () => {
    const state = await serial(
      [
        {
          type: AgentEventType.ROUTING_DECISION,
          messageId: MESSAGE_ID,
          data: { tier: 'simple' },
        },
        {
          type: AgentEventType.MESSAGE,
          messageId: MESSAGE_ID,
          data: 'final answer',
        },
        {
          type: AgentEventType.MESSAGE_END,
          messageId: MESSAGE_ID,
          data: '',
          completion_status: 'success',
          model: 'MiniMax-M3',
          memory_brief_status: { status: 'ready' },
        },
      ],
      { clearMessagesBeforeIndex: 2 },
    );

    // MESSAGE_END applies its terminal payload inside a 50ms setTimeout
    // (already awaited inside serial).
    const assistant = state.messages.find((m) => m.role === 'assistant');
    expect(assistant, JSON.stringify(state.messages)).toBeDefined();
    expect(assistant?.routingTier).toBe('simple');
    expect(assistant?.content).toContain('final answer');
  });
});
