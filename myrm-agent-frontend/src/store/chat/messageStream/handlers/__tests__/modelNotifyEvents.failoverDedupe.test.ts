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
) {
  const state = {
    messages: [
      {
        content: '',
        messageId: 'msg-1',
        chatId: 'c1',
        role: 'assistant' as const,
        progressSteps: existingSteps,
        createdAt: new Date(),
      },
    ],
  };
  const setMessages = vi.fn((updater: (s: typeof state) => void) => {
    updater(state);
  });
  const ctx: StreamCtx = {
    data: {
      type: 'model_failover',
      messageId: 'msg-1',
      data: { fromModel, toModel, reason },
    } as never,
    input: '',
    sources: undefined,
    added: false,
    recievedMessage: '',
    state: {} as never,
    actions: { setLoading: vi.fn(), setMessages: setMessages as never } as never,
    files: [],
  };
  return { state, ctx };
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
});
