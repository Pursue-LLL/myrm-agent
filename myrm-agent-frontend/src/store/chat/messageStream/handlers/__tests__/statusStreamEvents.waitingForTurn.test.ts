/**
 * waiting_for_turn / waiting_for_turn_clear SSE handlers — project lock wait UX.
 *
 * Backend `stream_pump.py` emits `waiting_for_turn` when a project lock is held by
 * another agent and `waiting_for_turn_clear` right after acquiring. The frontend must
 * surface the waiting step (placeholder-safe, it is the first stream event) and remove
 * it once the clear event arrives.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('../handlerDeps', () => {
  const AgentEventType = {
    STATUS: 'status',
  } as const;

  return {
    AgentEventType,
    findAssistantMessageIndex: vi.fn(() => 0),
    ensureAssistantStreamMessage: (
      messages: Array<{ messageId: string; role: string; chatId: string; content: string; progressSteps: unknown[]; createdAt: Date }>,
      messageId: string | undefined,
      chatIdFallback: string,
    ) => {
      const normalizedId = messageId?.trim();
      if (!normalizedId) return -1;
      const existing = messages.findIndex((m) => m.messageId === normalizedId && m.role === 'assistant');
      if (existing !== -1) return existing;
      messages.push({
        content: '',
        messageId: normalizedId,
        chatId: chatIdFallback,
        role: 'assistant',
        progressSteps: [],
        createdAt: new Date(),
      });
      return messages.length - 1;
    },
    parseArchiveRestoreBlockPayload: vi.fn(),
    parseArchiveRestoreResultPayload: vi.fn(),
    buildArchiveRestoreActions: vi.fn(() => []),
    discardStreamedDraft: (ctx: {
      recievedMessage: string;
      state?: { scheduler?: { cancel?: () => void } };
    }) => {
      ctx.recievedMessage = '';
      ctx.state?.scheduler?.cancel?.();
    },
    clearAssistantDraft: (message: {
      content: string;
      reasoning?: string;
      reasoningStartedAt?: number;
      reasoningDurationMs?: number;
    }) => {
      message.content = '';
      message.reasoning = '';
      message.reasoningStartedAt = undefined;
      message.reasoningDurationMs = undefined;
    },
    useConfigStore: {
      getState: vi.fn(() => ({ enableCacheBreakNotification: false })),
    },
  };
});

import { statusStreamEvents } from '../statusStreamEvents';
import { isStatusProgressStep } from '../statusStreamProgressSteps';
import type { ProgressItem } from '@/store/chat/types';
import type { StreamCtx } from '../../streamContext';

const { findAssistantMessageIndex } = await import('../handlerDeps');

function makeMessagesState() {
  return {
    messages: [
      {
        content: '',
        messageId: 'msg-1',
        chatId: 'c1',
        role: 'assistant' as const,
        progressSteps: [] as ProgressItem[],
        createdAt: new Date(),
      },
    ],
  };
}

function makeWaitingCtx(stepKey: string): StreamCtx {
  return {
    data: {
      type: 'status',
      step_key: stepKey,
      messageId: 'msg-1',
      status: stepKey === 'waiting_for_turn_clear' ? 'success' : 'waiting',
      data: stepKey === 'waiting_for_turn' ? { message: 'Waiting for other agents in the project to finish...' } : undefined,
    } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: {} as never,
    actions: {
      setLoading: vi.fn(),
      setMessages: vi.fn(),
    } as never,
    files: [],
  };
}

describe('statusStreamEvents waiting_for_turn', () => {
  beforeEach(() => {
    vi.mocked(findAssistantMessageIndex).mockReturnValue(0);
  });

  it('recognizes waiting_for_turn as a progress step', () => {
    expect(isStatusProgressStep('waiting_for_turn')).toBe(true);
    expect(isStatusProgressStep('waiting_for_turn_clear')).toBe(false);
  });

  it('appends a waiting_for_turn progress step for a locked project turn', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeWaitingCtx('waiting_for_turn');
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await statusStreamEvents(ctx);

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps![0].step_key).toBe('waiting_for_turn');
    expect(state.messages[0].progressSteps![0].status).toBeUndefined();
  });

  it('creates an assistant placeholder when waiting_for_turn arrives before MESSAGE', async () => {
    vi.mocked(findAssistantMessageIndex).mockReturnValue(-1);

    const state = {
      messages: [
        {
          content: '只回复 OK',
          messageId: 'user-1',
          chatId: 'c1',
          role: 'user' as const,
          createdAt: new Date(),
        },
      ] as Array<{ content: string; messageId: string; chatId: string; role: string; createdAt: Date; progressSteps?: Array<{ step_key?: string }> }>,
    };
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx: StreamCtx = {
      data: {
        type: 'status',
        step_key: 'waiting_for_turn',
        messageId: 'msg-new',
        status: 'waiting',
        data: { message: 'Waiting for other agents in the project to finish...' },
      } as never,
      input: '',
      sources: undefined,
      added: false,
      recievedMessage: '',
      state: {} as never,
      actions: { setLoading: vi.fn(), setMessages: setMessages as never } as never,
      files: [],
    };

    await statusStreamEvents(ctx);

    expect(state.messages).toHaveLength(2);
    expect(state.messages[1].role).toBe('assistant');
    expect(state.messages[1].messageId).toBe('msg-new');
    expect(state.messages[1].progressSteps?.[0]?.step_key).toBe('waiting_for_turn');
    expect(ctx.added).toBe(true);
  });

  it('removes the waiting_for_turn step when waiting_for_turn_clear arrives', async () => {
    const state = makeMessagesState();
    state.messages[0].progressSteps!.push({
      step_key: 'waiting_for_turn',
      items: [],
    });
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeWaitingCtx('waiting_for_turn_clear');
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await statusStreamEvents(ctx);

    expect(state.messages[0].progressSteps).toHaveLength(0);
  });

  it('keeps other progress steps when clearing only the waiting step', async () => {
    const state = makeMessagesState();
    state.messages[0].progressSteps!.push({
      step_key: 'waiting_for_turn',
      items: [],
    });
    state.messages[0].progressSteps!.push({
      step_key: 'workflow_execution',
      items: [],
    });
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeWaitingCtx('waiting_for_turn_clear');
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await statusStreamEvents(ctx);

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps![0].step_key).toBe('workflow_execution');
  });
});
