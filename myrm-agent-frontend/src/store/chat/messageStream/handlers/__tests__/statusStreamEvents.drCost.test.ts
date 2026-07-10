/**
 * DR real-time cost transparency — cycle cost + budget event SSE handlers.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('./handlerDeps', () => {
  const AgentEventType = {
    STATUS: 'status',
  } as const;

  return {
    AgentEventType,
    findAssistantMessageIndex: vi.fn(() => 0),
    parseArchiveRestoreBlockPayload: vi.fn(),
    parseArchiveRestoreResultPayload: vi.fn(),
    buildArchiveRestoreActions: vi.fn(() => []),
    useConfigStore: {
      getState: vi.fn(() => ({ enableCacheBreakNotification: false })),
    },
  };
});

import { statusStreamEvents } from '../statusStreamEvents';
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
        progressSteps: [
          { step_key: 'deep_research_researching' },
        ] as ProgressItem[],
        createdAt: new Date(),
      },
    ],
  };
}

function makeDrStatusCtx(statusData: Record<string, unknown>): StreamCtx {
  return {
    data: {
      type: 'status',
      step_key: undefined,
      messageId: 'msg-1',
      status: 'in_progress',
      data: statusData,
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

describe('statusStreamEvents DR cost transparency', () => {
  it('displays cycle cost in items when cost > 0', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeDrStatusCtx({
      phase: 'research',
      cycle: 2,
      max_cycles: 5,
      current_cost_usd: 0.32,
      progress_percent: 40,
    });
    ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await statusStreamEvents(ctx);

    const step = state.messages[0].progressSteps![0];
    expect(step.items).toEqual([{ text: 'Cycle 2/5 — $0.32' }]);
    expect(step.progress_percent).toBe(40);
  });

  it('omits cost display when cost is 0 (graceful degradation)', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeDrStatusCtx({
      phase: 'research',
      cycle: 1,
      max_cycles: 3,
      current_cost_usd: 0,
      progress_percent: 10,
    });
    ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await statusStreamEvents(ctx);

    const step = state.messages[0].progressSteps![0];
    expect(step.items).toEqual([{ text: 'Cycle 1/3' }]);
  });

  it('handles cycle without max_cycles', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeDrStatusCtx({
      phase: 'research',
      cycle: 3,
      current_cost_usd: 1.5,
    });
    ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await statusStreamEvents(ctx);

    const step = state.messages[0].progressSteps![0];
    expect(step.items).toEqual([{ text: 'Cycle 3 — $1.50' }]);
  });

  it('displays budget warning with cost details', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeDrStatusCtx({
      phase: 'research',
      budget_event: 'warning',
      current_cost_usd: 1.6,
      budget_usd: 2.0,
      percent_used: 80,
    });
    ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await statusStreamEvents(ctx);

    const step = state.messages[0].progressSteps![0];
    const items = step.items as { text: string }[];
    expect(items).toContainEqual({ text: 'Budget 80% used ($1.60/$2.00)' });
    expect(step.status).toBeUndefined();
  });

  it('displays budget exceeded with warning status', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeDrStatusCtx({
      phase: 'research',
      budget_event: 'exceeded',
      current_cost_usd: 2.3,
      budget_usd: 2.0,
      percent_used: 115,
    });
    ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await statusStreamEvents(ctx);

    const step = state.messages[0].progressSteps![0];
    const items = step.items as { text: string }[];
    expect(items).toContainEqual({ text: 'Budget exceeded ($2.30/$2.00)' });
    expect(step.status).toBe('warning');
  });

  it('does not crash when no progressSteps exist', async () => {
    const state = {
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
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeDrStatusCtx({
      phase: 'research',
      cycle: 1,
      max_cycles: 5,
      current_cost_usd: 0.1,
    });
    ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await statusStreamEvents(ctx);

    expect(state.messages[0].progressSteps).toHaveLength(0);
  });
});
