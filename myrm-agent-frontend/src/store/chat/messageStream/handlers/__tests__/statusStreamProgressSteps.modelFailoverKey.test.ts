/**
 * model_failover STATUS step — dynamic displayKey derivation from error_kind.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../handlerDeps', () => {
  return {
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
  };
});

import { applyStatusProgressStep, isStatusProgressStep } from '../statusStreamProgressSteps';
import type { ProgressItem } from '@/store/chat/types';
import type { StreamCtx } from '../../streamContext';

function makeMessagesState() {
  return {
    messages: [
      {
        content: '',
        messageId: 'msg-1',
        chatId: 'c1',
        role: 'assistant' as const,
        reasoning: '',
        progressSteps: [] as ProgressItem[],
        createdAt: new Date(),
      },
    ],
  };
}

function makeFailoverCtx(errorKind?: string): StreamCtx {
  return {
    data: {
      type: 'status',
      step_key: 'model_failover',
      messageId: 'msg-1',
      status: 'in_progress',
      error_kind: errorKind,
    } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: { scheduler: { cancel: vi.fn() } } as never,
    actions: {
      setLoading: vi.fn(),
      setMessages: vi.fn(),
    } as never,
    files: [],
  };
}

function schedulerCancelOf(ctx: StreamCtx): ReturnType<typeof vi.fn> {
  return (ctx.state as unknown as { scheduler: { cancel: ReturnType<typeof vi.fn> } }).scheduler
    .cancel;
}

describe('applyStatusProgressStep model_failover displayKey', () => {
  it('derives model_failover_response_format_error from error_kind', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeFailoverCtx('response_format_error');
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await applyStatusProgressStep(ctx, 'model_failover');

    const step = state.messages[0].progressSteps![0];
    expect(step.step_key).toBe('model_failover_response_format_error');
  });

  it('derives model_failover_model_not_found from error_kind', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeFailoverCtx('model_not_found');
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await applyStatusProgressStep(ctx, 'model_failover');

    const step = state.messages[0].progressSteps![0];
    expect(step.step_key).toBe('model_failover_model_not_found');
  });

  it('falls back to plain model_failover when error_kind is absent', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeFailoverCtx(undefined);
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await applyStatusProgressStep(ctx, 'model_failover');

    const step = state.messages[0].progressSteps![0];
    expect(step.step_key).toBe('model_failover');
  });

  it('creates assistant placeholder when model_failover arrives before MESSAGE', async () => {    const { findAssistantMessageIndex } = await import('../handlerDeps');
    // applyStatusProgressStep calls findAssistantMessageIndex exactly once per
    // invocation; mockReturnValueOnce keeps the -1 scoped to this test instead of
    // leaking into later tests (a persistent mockReturnValue would make every
    // later step skip clearAssistantDraft and fail the restart-protocol cases).
    vi.mocked(findAssistantMessageIndex).mockReturnValueOnce(-1);

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
        step_key: 'model_failover',
        messageId: 'msg-new',
        status: 'in_progress',
        error_kind: 'overloaded',
        fallback_model: 'minimax/MiniMax-M3',
      } as never,
      input: '',
      sources: undefined,
      added: false,
      recievedMessage: '',
      state: {} as never,
      actions: { setLoading: vi.fn(), setMessages: setMessages as never } as never,
      files: [],
    };

    await applyStatusProgressStep(ctx, 'model_failover');

    expect(state.messages).toHaveLength(2);
    expect(state.messages[1].role).toBe('assistant');
    expect(state.messages[1].messageId).toBe('msg-new');
    expect(state.messages[1].progressSteps?.[0]?.step_key).toBe('model_failover_overloaded');
    expect(ctx.added).toBe(true);
  });

  it('recognizes unconfigured failover progress steps', () => {
    expect(isStatusProgressStep('model_failover_unconfigured')).toBe(true);
    expect(isStatusProgressStep('safety_fallback_unconfigured')).toBe(true);
  });

  it('dedupes STATUS safety_fallback_active when SSE already created the step', async () => {
    const state = makeMessagesState();
    state.messages[0].progressSteps!.push({
      step_key: 'safety_fallback_active',
      items: [{ text: 'agnes → safety-mini' }],
      status: 'success',
    });
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeFailoverCtx('safety_block');
    (ctx.data as unknown as Record<string, unknown>).step_key = 'safety_fallback_active';
    (ctx.data as unknown as Record<string, unknown>).fallback_model = 'safety-mini';
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await applyStatusProgressStep(ctx, 'safety_fallback_active');

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps![0].step_key).toBe('safety_fallback_active');
  });

  it('keeps from → to label when STATUS arrives after the SSE failover step', async () => {
    const state = makeMessagesState();
    state.messages[0].progressSteps!.push({
      step_key: 'model_failover_overloaded',
      items: [{ text: 'agnes → minimax/MiniMax-M3' }],
      status: 'success',
    });
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeFailoverCtx('overloaded');
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await applyStatusProgressStep(ctx, 'model_failover');

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps![0].items?.[0]).toMatchObject({
      text: 'agnes → minimax/MiniMax-M3',
    });
  });

  it('routes unconfigured failover toast CTA to default model settings', async () => {
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { assign } });

    const showI18nToast = vi.fn((_key, _params, opts?: { action?: { onClick?: () => void } }) => {
      opts?.action?.onClick?.();
    });
    vi.doMock('@/services/i18nToastService', () => ({ showI18nToast }));

    vi.resetModules();
    const { applyStatusProgressStep: applyUnconfigured } = await import('../statusStreamProgressSteps');

    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx: StreamCtx = {
      data: {
        type: 'status',
        step_key: 'model_failover_unconfigured',
        messageId: 'msg-1',
        status: 'warning',
      } as never,
      input: '',
      sources: undefined,
      added: true,
      recievedMessage: '',
      state: {} as never,
      actions: { setLoading: vi.fn(), setMessages: setMessages as never } as never,
      files: [],
    };

    await applyUnconfigured(ctx, 'model_failover_unconfigured');
    expect(assign).toHaveBeenCalledWith('/settings/defaultModel');

    vi.unstubAllGlobals();
    vi.doUnmock('@/services/i18nToastService');
    vi.resetModules();
  });

  it('routes safety unconfigured toast CTA to agent loadout settings', async () => {
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { assign } });

    const showI18nToast = vi.fn((_key, _params, opts?: { action?: { onClick?: () => void } }) => {
      opts?.action?.onClick?.();
    });
    vi.doMock('@/services/i18nToastService', () => ({ showI18nToast }));

    vi.resetModules();
    const { applyStatusProgressStep: applySafety } = await import('../statusStreamProgressSteps');

    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx: StreamCtx = {
      data: {
        type: 'status',
        step_key: 'safety_fallback_unconfigured',
        messageId: 'msg-1',
        status: 'warning',
      } as never,
      input: '',
      sources: undefined,
      added: true,
      recievedMessage: '',
      state: {} as never,
      actions: { setLoading: vi.fn(), setMessages: setMessages as never } as never,
      files: [],
    };

    await applySafety(ctx, 'safety_fallback_unconfigured');
    expect(assign).toHaveBeenCalledWith('/settings/agents#loadout');

    vi.unstubAllGlobals();
    vi.doUnmock('@/services/i18nToastService');
    vi.resetModules();
  });

  it('deduplicates repeated model_failover STATUS into a single progress step', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeFailoverCtx('model_not_found');
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await applyStatusProgressStep(ctx, 'model_failover');
    await applyStatusProgressStep(ctx, 'model_failover');

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps![0].step_key).toBe('model_failover_model_not_found');
  });

  it('drops partial text streamed before the failure on the STATUS channel', async () => {
    const state = makeMessagesState();
    state.messages[0].content = 'Partial draft ';
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeFailoverCtx('overloaded');
    ctx.recievedMessage = 'Partial draft ';
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await applyStatusProgressStep(ctx, 'model_failover');

    expect(ctx.recievedMessage).toBe('');
    expect(state.messages[0].content).toBe('');
    expect(state.messages[0].reasoning).toBe('');
    expect(state.messages[0].progressSteps![0].step_key).toBe('model_failover_overloaded');
    expect(schedulerCancelOf(ctx)).toHaveBeenCalledTimes(1);
  });

  describe('restart protocol (data.restart === true)', () => {
    // Restore the shared handlerDeps mock default after any test mutates it,
    // so a stray mockReturnValue can never leak into later restart cases.
    beforeEach(async () => {
      const { findAssistantMessageIndex } = await import('../handlerDeps');
      vi.mocked(findAssistantMessageIndex).mockReturnValue(0);
    });

    function makeRestartCtx(stepKey: string, restart: boolean): StreamCtx {
      return {
        data: {
          type: 'status',
          step_key: stepKey,
          messageId: 'msg-1',
          status: 'in_progress',
          restart,
          ...(stepKey === 'transient_retry' ? { attempt: 1 } : {}),
        } as never,
        input: '',
        sources: undefined,
        added: true,
        recievedMessage: '',
        state: { scheduler: { cancel: vi.fn() } } as never,
        actions: {
          setLoading: vi.fn(),
          setMessages: vi.fn(),
        } as never,
        files: [],
      };
    }

    it('clears the draft on any restart STATUS step (e.g. transient_retry)', async () => {
      const state = makeMessagesState();
      const msg = state.messages[0] as unknown as {
        content: string;
        reasoning: string;
        reasoningStartedAt?: number;
        reasoningDurationMs?: number;
      };
      msg.content = 'Partial draft ';
      msg.reasoning = 'partial reasoning';
      msg.reasoningStartedAt = 1000;
      msg.reasoningDurationMs = 500;
      const setMessages = vi.fn((updater: (s: typeof state) => void) => {
        updater(state);
      });

      const ctx = makeRestartCtx('transient_retry', true);
      ctx.recievedMessage = 'Partial draft ';
      ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
      await applyStatusProgressStep(ctx, 'transient_retry');

      expect(ctx.recievedMessage).toBe('');
      expect(msg.content).toBe('');
      expect(msg.reasoning).toBe('');
      expect(msg.reasoningStartedAt).toBeUndefined();
      expect(msg.reasoningDurationMs).toBeUndefined();
      expect(state.messages[0].progressSteps![0].step_key).toBe('transient_retry');
      expect(schedulerCancelOf(ctx)).toHaveBeenCalledTimes(1);
    });

    it('keeps the draft when the STATUS step does not carry restart', async () => {
      const state = makeMessagesState();
      const msg = state.messages[0] as unknown as {
        content: string;
        reasoning: string;
        reasoningStartedAt?: number;
        reasoningDurationMs?: number;
      };
      msg.content = 'Kept draft ';
      msg.reasoning = 'kept reasoning';
      msg.reasoningStartedAt = 1000;
      const setMessages = vi.fn((updater: (s: typeof state) => void) => {
        updater(state);
      });

      const ctx = makeRestartCtx('memory_archived', false);
      ctx.recievedMessage = 'Kept draft ';
      ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
      await applyStatusProgressStep(ctx, 'memory_archived');

      expect(ctx.recievedMessage).toBe('Kept draft ');
      expect(msg.content).toBe('Kept draft ');
      expect(msg.reasoning).toBe('kept reasoning');
      expect(msg.reasoningStartedAt).toBe(1000);
      expect(schedulerCancelOf(ctx)).not.toHaveBeenCalled();
    });

    it.each(['empty_response_recovery', 'tool_call_retry'])(
      'is a whitelisted progress step and clears the draft on %s',
      async (stepKey) => {
        expect(isStatusProgressStep(stepKey)).toBe(true);

        const state = makeMessagesState();
        const msg = state.messages[0] as unknown as {
          content: string;
          reasoning: string;
          reasoningStartedAt?: number;
          reasoningDurationMs?: number;
        };
        msg.content = 'Partial draft ';
        msg.reasoning = 'partial reasoning';
        msg.reasoningStartedAt = 1000;
        msg.reasoningDurationMs = 500;
        const setMessages = vi.fn((updater: (s: typeof state) => void) => {
          updater(state);
        });

        const ctx = makeRestartCtx(stepKey, true);
        ctx.recievedMessage = 'Partial draft ';
        ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
        await applyStatusProgressStep(ctx, stepKey);

        expect(ctx.recievedMessage).toBe('');
        expect(msg.content).toBe('');
        expect(msg.reasoning).toBe('');
        expect(msg.reasoningStartedAt).toBeUndefined();
        expect(msg.reasoningDurationMs).toBeUndefined();
        expect(state.messages[0].progressSteps![0].step_key).toBe(stepKey);
        expect(schedulerCancelOf(ctx)).toHaveBeenCalledTimes(1);
      },
    );
  });
});
