/**
 * Tests for routingMetaEvents handler — verifies ROUTING_DECISION SSE events
 * correctly write routingTier into the chat store.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

const { mockFind, mockSetMessages } = vi.hoisted(() => {
  return {
    mockFind: vi.fn((_messages, messageId: string) => (messageId === 'msg-1' ? 0 : -1)),
    mockSetMessages: vi.fn((updater: (state: Record<string, unknown>) => void) => {
      updater({
        messages: [
          {
            messageId: 'msg-1',
            chatId: 'c1',
            role: 'assistant',
            content: 'hello from llm',
            createdAt: new Date(),
          },
        ],
      });
    }),
  };
});

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    ROUTING_DECISION: 'routing_decision',
    PRIVACY_LEVEL: 'privacy_level',
    PRIVACY_ROUTE: 'privacy_route',
    TOKEN_USAGE: 'token_usage',
  },
  findAssistantMessageIndex: mockFind,
  resolveStreamChatId: (state: { chatId?: string; messages?: Array<{ chatId?: string }> }) =>
    state.chatId?.trim() || state.messages?.[0]?.chatId?.trim() || '',
}));

import { routingMetaEvents } from '../routingMetaEvents';
import type { StreamCtx } from '../../streamContext';

function makeCtx(overrides: Partial<StreamCtx> = {}): StreamCtx {
  const base: StreamCtx = {
    data: { type: 'routing_decision', messageId: 'msg-1', data: { tier: 'simple' } } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: {
      messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() }],
      messageAppeared: false,
      loading: true,
    } as never,
    actions: {
      setMessages: mockSetMessages,
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
    } as never,
    files: [],
  };
  return { ...base, ...overrides };
}

describe('routingMetaEvents', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('updates routingTier on existing assistant message (added=true)', async () => {
    const ctx = makeCtx();
    let captured: Record<string, unknown> = {};
    mockSetMessages.mockImplementation((updater: (s: Record<string, unknown>) => void) => {
      const draft: Record<string, unknown> = {
        messages: [
          {
            messageId: 'msg-1',
            chatId: 'c1',
            role: 'assistant',
            content: 'hello from llm',
            createdAt: new Date(),
          },
        ],
      };
      updater(draft);
      captured = draft;
    });

    await routingMetaEvents(ctx);
    expect(mockSetMessages).toHaveBeenCalledTimes(1);
    const messages = captured.messages as Array<Record<string, unknown>>;
    expect(messages[0].routingTier).toBe('simple');
  });

  it('pushes an assistant placeholder when added=false and no message exists', async () => {
    const ctx = makeCtx({ added: false });
    let captured: Record<string, unknown> = {};
    mockSetMessages.mockImplementation((updater: (s: Record<string, unknown>) => void) => {
      const draft: Record<string, unknown> = { messages: [] };
      updater(draft);
      captured = draft;
    });

    await routingMetaEvents(ctx);
    const messages = captured.messages as Array<Record<string, unknown>>;
    expect(messages).toHaveLength(1);
    expect(messages[0].routingTier).toBe('simple');
    expect(messages[0].role).toBe('assistant');
  });

  it('ignores non-routing events', async () => {
    const ctx = makeCtx({
      data: { type: 'some_unhandled_event', messageId: 'msg-1', data: {} } as never,
    });
    const result = await routingMetaEvents(ctx);
    expect(result).toBeNull();
    expect(mockSetMessages).not.toHaveBeenCalled();
  });

  it('updates routingSpecialty and routingTier on existing assistant message (added=true)', async () => {
    const ctx = makeCtx({
      data: { type: 'routing_decision', messageId: 'msg-1', data: { tier: 'code', specialty: 'code' } } as never,
    });
    let captured: Record<string, unknown> = {};
    mockSetMessages.mockImplementation((updater: (s: Record<string, unknown>) => void) => {
      const draft: Record<string, unknown> = {
        messages: [
          {
            messageId: 'msg-1',
            chatId: 'c1',
            role: 'assistant',
            content: 'def solve(): pass',
            createdAt: new Date(),
          },
        ],
      };
      updater(draft);
      captured = draft;
    });

    await routingMetaEvents(ctx);
    expect(mockSetMessages).toHaveBeenCalledTimes(1);
    const messages = captured.messages as Array<Record<string, unknown>>;
    expect(messages[0].routingTier).toBe('code');
    expect(messages[0].routingSpecialty).toBe('code');
  });

  it('handles model_tier-only events (weak model, no routing)', async () => {
    const ctx = makeCtx({
      data: { type: 'routing_decision', messageId: 'msg-1', data: { model_tier: 'weak' } } as never,
    });
    let captured: Record<string, unknown> = {};
    mockSetMessages.mockImplementation((updater: (s: Record<string, unknown>) => void) => {
      const draft: Record<string, unknown> = {
        messages: [
          {
            messageId: 'msg-1',
            chatId: 'c1',
            role: 'assistant',
            content: '',
            createdAt: new Date(),
          },
        ],
      };
      updater(draft);
      captured = draft;
    });

    await routingMetaEvents(ctx);
    const messages = captured.messages as Array<Record<string, unknown>>;
    expect(messages[0].modelTier).toBe('weak');
  });
});
