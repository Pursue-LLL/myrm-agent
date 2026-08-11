/**
 * model_failover STATUS step — dynamic displayKey derivation from error_kind.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('../handlerDeps', () => {
  return {
    findAssistantMessageIndex: vi.fn(() => 0),
    parseArchiveRestoreBlockPayload: vi.fn(),
    parseArchiveRestoreResultPayload: vi.fn(),
    buildArchiveRestoreActions: vi.fn(() => []),
  };
});

import { applyStatusProgressStep } from '../statusStreamProgressSteps';
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
});
