/**
 * modelNotifyEvents MODEL_FAILOVER progress-step dedupe against the STATUS
 * channel (harness emits both STATUS model_failover and MODEL_FAILOVER SSE for
 * the same transition; the message must show a single failover step).
 */
import { describe, expect, it, vi } from 'vitest';

const { showI18nToast } = vi.hoisted(() => ({ showI18nToast: vi.fn() }));

vi.mock('../handlerDeps', () => ({
  findAssistantMessageIndex: vi.fn(() => 0),
  ensureAssistantStreamMessage: vi.fn(),
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
  AgentEventType: {
    MODEL_FAILOVER: 'model_failover',
    MODEL_ESCALATED: 'model_escalated',
    MODEL_RECOVERY: 'model_recovery',
  },
}));

vi.mock('@/services/i18nToastService', () => ({ showI18nToast }));

import { modelNotifyEvents } from '../modelNotifyEvents';
import type { StreamCtx } from '../../streamContext';

function makeFailoverCtx(
  fromModel: string,
  toModel: string,
  reason: string | undefined,
  existingSteps: Array<Record<string, unknown>>,
  initialRecieved = '',
) {
  const state = {
    messages: [
      {
        content: initialRecieved,
        messageId: 'msg-1',
        chatId: 'c1',
        role: 'assistant' as const,
        reasoning: '',
        progressSteps: existingSteps,
        createdAt: new Date(),
      },
    ],
  };
  const setMessages = vi.fn((updater: (s: typeof state) => void) => {
    updater(state);
  });
  const cancel = vi.fn();
  const ctx: StreamCtx = {
    data: {
      type: 'model_failover',
      messageId: 'msg-1',
      data: { fromModel, toModel, reason },
    } as never,
    input: '',
    sources: undefined,
    added: false,
    recievedMessage: initialRecieved,
    state: { scheduler: { cancel } } as never,
    actions: { setLoading: vi.fn(), setMessages: setMessages as never } as never,
    files: [],
  };
  return { state, ctx, cancel };
}

describe('modelNotifyEvents MODEL_FAILOVER progress-step dedupe', () => {
  beforeEach(() => {
    showI18nToast.mockClear();
  });

  it('updates the STATUS-recorded failover step instead of appending a duplicate', async () => {
    const { state, ctx } = makeFailoverCtx('agnes', 'MiniMax-M3', 'model_not_found', [
      {
        step_key: 'model_failover_model_not_found',
        items: [{ text: 'MiniMax-M3' }],
        status: 'success',
      },
    ]);

    const result = await modelNotifyEvents(ctx);
    expect(result).not.toBeNull();
    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps[0]).toMatchObject({
      step_key: 'model_failover_model_not_found',
      items: [{ text: 'agnes → MiniMax-M3' }],
    });
    expect(showI18nToast).toHaveBeenCalledTimes(1);
  });

  it('appends a failover step when the STATUS channel never arrived', async () => {
    const { state, ctx } = makeFailoverCtx('agnes', 'MiniMax-M3', 'overloaded', []);

    await modelNotifyEvents(ctx);

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps[0]).toMatchObject({
      step_key: 'model_failover_overloaded',
      items: [{ text: 'agnes → MiniMax-M3' }],
    });
  });

  it('merges safety_block SSE into the STATUS safety_fallback_active step', async () => {
    const { state, ctx } = makeFailoverCtx('agnes', 'safety-mini', 'safety_block', [
      { step_key: 'safety_fallback_active', items: [], status: 'success' },
    ]);

    await modelNotifyEvents(ctx);

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps[0]).toMatchObject({
      step_key: 'safety_fallback_active',
      items: [{ text: 'agnes → safety-mini' }],
    });
  });

  it('drops partial text and reasoning streamed before the failure', async () => {
    const { state, ctx } = makeFailoverCtx(
      'agnes',
      'MiniMax-M3',
      'overloaded',
      [],
      'Partial draft ',
    );

    await modelNotifyEvents(ctx);

    expect(ctx.recievedMessage).toBe('');
    expect(state.messages[0].content).toBe('');
    expect(state.messages[0].reasoning).toBe('');
    expect(state.messages[0].progressSteps).toHaveLength(1);
  });

  it('cancels the pending render task so the stale draft cannot be written back', async () => {
    const { state, ctx, cancel } = makeFailoverCtx(
      'agnes',
      'MiniMax-M3',
      'overloaded',
      [],
      'Partial draft ',
    );

    await modelNotifyEvents(ctx);

    expect(cancel).toHaveBeenCalledTimes(1);
    expect(ctx.recievedMessage).toBe('');
    expect(state.messages[0].content).toBe('');
  });
});

describe('modelNotifyEvents MODEL_ESCALATED restart protocol', () => {
  function makeEscalatedCtx(restart?: boolean) {
    const state = {
      messages: [
        {
          content: restart ? 'Partial draft ' : 'Kept draft ',
          messageId: 'msg-1',
          chatId: 'c1',
          role: 'assistant' as const,
          reasoning: restart ? 'partial reasoning' : 'kept reasoning',
          reasoningStartedAt: 1000,
          reasoningDurationMs: 500,
          progressSteps: [] as Array<Record<string, unknown>>,
          createdAt: new Date(),
        },
      ],
    };
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });
    const cancel = vi.fn();
    const ctx: StreamCtx = {
      data: {
        type: 'model_escalated',
        messageId: 'msg-1',
        data: {
          from_model: 'agnes',
          to_model: 'MiniMax-M3',
          reason: 'overloaded',
          ...(restart !== undefined ? { restart } : {}),
        },
      } as never,
      input: '',
      sources: undefined,
      added: false,
      recievedMessage: restart ? 'Partial draft ' : 'Kept draft ',
      state: { scheduler: { cancel } } as never,
      actions: { setLoading: vi.fn(), setMessages: setMessages as never } as never,
      files: [],
    };
    return { state, ctx, cancel };
  }

  it('clears the draft when restart === true', async () => {
    const { state, ctx, cancel } = makeEscalatedCtx(true);

    await modelNotifyEvents(ctx);

    expect(ctx.recievedMessage).toBe('');
    expect(state.messages[0].content).toBe('');
    expect(state.messages[0].reasoning).toBe('');
    expect(state.messages[0].reasoningStartedAt).toBeUndefined();
    expect(state.messages[0].reasoningDurationMs).toBeUndefined();
    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps[0].step_key).toBe('model_escalated');
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it('keeps the draft when restart is absent', async () => {
    const { state, ctx, cancel } = makeEscalatedCtx(undefined);

    await modelNotifyEvents(ctx);

    expect(ctx.recievedMessage).toBe('Kept draft ');
    expect(state.messages[0].content).toBe('Kept draft ');
    expect(state.messages[0].reasoning).toBe('kept reasoning');
    expect(state.messages[0].reasoningStartedAt).toBe(1000);
    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(cancel).not.toHaveBeenCalled();
  });
});
