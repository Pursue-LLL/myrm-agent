/**
 * Preflight pressure-gate STATUS steps — allowlist, item text, warning status.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../handlerDeps', () => {
  return {
    findAssistantMessageIndex: vi.fn(() => 0),
    ensureAssistantStreamMessage: (
      messages: Array<{
        messageId: string;
        role: string;
        chatId: string;
        content: string;
        progressSteps: unknown[];
        createdAt: Date;
      }>,
      messageId: string | undefined,
      chatIdFallback: string,
    ) => {
      const normalizedId = messageId?.trim();
      if (!normalizedId) {
        return -1;
      }
      const existing = messages.findIndex((m) => m.messageId === normalizedId && m.role === 'assistant');
      if (existing !== -1) {
        return existing;
      }
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
    discardStreamedDraft: (ctx: { recievedMessage: string; state?: { scheduler?: { cancel?: () => void } } }) => {
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
  };
});

import { applyStatusProgressStep, isStatusProgressStep } from '../statusStreamProgressSteps';
import type { ProgressItem } from '@/store/chat/types';
import type { StreamCtx } from '../../streamContext';

const PREFLIGHT_KEYS = [
  'context_preflight_compact',
  'context_preflight_truncation',
  'context_preflight_exhausted',
  'context_presumed_overflow',
  'context_presumed_overflow_exhausted',
];

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

function makeCtx(stepKey: string, extra: Record<string, unknown> = {}): StreamCtx {
  return {
    data: {
      type: 'status',
      step_key: stepKey,
      messageId: 'msg-1',
      restart: true,
      ...extra,
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

describe('preflight gate progress steps', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each(PREFLIGHT_KEYS)('recognizes %s as a progress step', (stepKey) => {
    expect(isStatusProgressStep(stepKey)).toBe(true);
  });

  it('renders freed tokens for preflight compact', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });
    const ctx = makeCtx('context_preflight_compact', { freed_tokens: 1200, request_tokens: 90000 });
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await applyStatusProgressStep(ctx, 'context_preflight_compact');

    const step = state.messages[0].progressSteps![0];
    expect(step.step_key).toBe('context_preflight_compact');
    expect(step.items).toEqual([{ text: '(freed 1200 tokens)' }]);
  });

  it('marks exhausted steps as warning', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });
    const ctx = makeCtx('context_preflight_exhausted', { restart: false, request_tokens: 95000 });
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await applyStatusProgressStep(ctx, 'context_preflight_exhausted');

    const step = state.messages[0].progressSteps![0];
    expect(step.status).toBe('warning');
    expect(step.items).toEqual([{ text: '(95000 tokens)' }]);
  });

  it('creates assistant placeholder when preflight arrives before MESSAGE', async () => {
    const { findAssistantMessageIndex } = await import('../handlerDeps');
    vi.mocked(findAssistantMessageIndex).mockReturnValueOnce(-1);

    const state = {
      messages: [
        {
          content: 'user text',
          messageId: 'user-1',
          chatId: 'c1',
          role: 'user' as const,
          progressSteps: [] as ProgressItem[],
          createdAt: new Date(),
        },
      ],
    };
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });
    const ctx = makeCtx('context_presumed_overflow', { freed_tokens: 800 });
    ctx.actions.setMessages = setMessages as unknown as StreamCtx['actions']['setMessages'];
    await applyStatusProgressStep(ctx, 'context_presumed_overflow');

    const placeholder = state.messages.find((m) => m.messageId === 'msg-1' && m.role === 'assistant');
    expect(placeholder).toBeDefined();
    expect(placeholder!.progressSteps!.length).toBe(1);
  });
});
