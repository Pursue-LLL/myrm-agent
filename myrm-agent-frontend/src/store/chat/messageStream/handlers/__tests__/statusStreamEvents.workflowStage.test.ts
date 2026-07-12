/**
 * workflow_stage SSE handler — merge by category + progress_percent mirror.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('../handlerDeps', () => {
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
        progressSteps: [] as ProgressItem[],
        createdAt: new Date(),
      },
    ],
  };
}

function makeWorkflowStageCtx(
  message: string,
  overrides: Record<string, unknown> = {},
): StreamCtx {
  return {
    data: {
      type: 'status',
      step_key: 'workflow_stage',
      messageId: 'msg-1',
      status: 'in_progress',
      data: {
        message,
        notify_progress: -1,
        notify_step_index: 0,
        notify_total_steps: 0,
        notify_category: '',
        notify_level: 'info',
        ...overrides,
      },
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

describe('statusStreamEvents workflow_stage', () => {
  it('mirrors notify_progress into progress_percent for the progress bar', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeWorkflowStageCtx('Halfway done', {
      notify_progress: 50,
      notify_category: 'analysis',
    });
    ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await statusStreamEvents(ctx);

    const step = state.messages[0].progressSteps![0];
    expect(step.step_key).toBe('workflow_stage:analysis');
    expect(step.notify_message).toBe('Halfway done');
    expect(step.progress_percent).toBe(50);
    expect(step.notify_progress).toBe(50);
  });

  it('merges updates for the same notify_category', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    for (const message of ['Spawning sub-agent `t1`...', 'Sub-agent `t1` completed.']) {
      const ctx = makeWorkflowStageCtx(message, { notify_category: 'subagent' });
      ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
      await statusStreamEvents(ctx);
    }

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps![0].step_key).toBe('workflow_stage:subagent');
    expect(state.messages[0].progressSteps![0].notify_message).toBe('Sub-agent `t1` completed.');
  });

  it('keeps distinct categories as separate progress items', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    for (const category of ['analysis', 'summary']) {
      const ctx = makeWorkflowStageCtx(`Phase ${category}`, { notify_category: category });
      ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
      await statusStreamEvents(ctx);
    }

    expect(state.messages[0].progressSteps).toHaveLength(2);
    expect(state.messages[0].progressSteps!.map((s) => s.step_key).sort()).toEqual([
      'workflow_stage:analysis',
      'workflow_stage:summary',
    ]);
  });
});
