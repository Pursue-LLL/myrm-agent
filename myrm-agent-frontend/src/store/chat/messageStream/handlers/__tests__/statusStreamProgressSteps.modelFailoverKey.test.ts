/**
 * model_failover STATUS step — dynamic displayKey derivation from error_kind.
 */
import { describe, expect, it, vi } from 'vitest';

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
    state: {} as never,
    actions: {
      setLoading: vi.fn(),
      setMessages: vi.fn(),
    } as never,
    files: [],
  };
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

  it('creates assistant placeholder when model_failover arrives before MESSAGE', async () => {
    const { findAssistantMessageIndex } = await import('../handlerDeps');
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
      ],
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
});
