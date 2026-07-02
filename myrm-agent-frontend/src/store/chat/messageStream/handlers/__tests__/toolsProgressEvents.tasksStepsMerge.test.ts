/**
 * TASKS_STEPS merge-by-step_key — execution checklist re-emits must update in place.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/approval/buildToolApprovalRequest', () => ({
  buildToolApprovalRequest: vi.fn(() => ({ id: 'mock-req' })),
}));

import { mapTaskStepStatus } from '../../streamHelpers';

vi.mock('./handlerDeps', () => {
  const AgentEventType = {
    TASKS_STEPS: 'tasks_steps',
  } as const;

  return {
    AgentEventType,
    findAssistantMessageIndex: vi.fn(() => 0),
    useChatStore: {
      getState: vi.fn(() => ({
        chatId: 'c1',
        actionMode: 'auto',
        addEnvironmentAlert: vi.fn(),
      })),
    },
    useToolApprovalStore: {
      getState: vi.fn(() => ({
        addRequest: vi.fn(),
        removeRequestsByMessageId: vi.fn(),
      })),
    },
    useToolsSnapshotStore: {
      getState: vi.fn(() => ({ setTools: vi.fn() })),
    },
    mapTaskStepStatus,
    mergeMessageSources: vi.fn(),
  };
});

import { toolsProgressEvents } from '../toolsProgressEvents';
import type { ProgressItem } from '@/store/chat/types';
import type { StreamCtx } from '../../streamContext';

function makeMessagesState() {
  return {
    messages: [
      {
        content: 'hello',
        messageId: 'msg-1',
        chatId: 'c1',
        role: 'assistant' as const,
        progressSteps: [] as ProgressItem[],
        createdAt: new Date(),
      },
    ],
  };
}

function makeTasksStepsCtx(status: string, stepKey: string): StreamCtx {
  return {
    data: {
      type: 'tasks_steps',
      messageId: 'msg-1',
      step_key: stepKey,
      parent_step_key: 'checklist_root',
      is_plan: false,
      status,
      data: [{ text: 'Step one' }],
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

describe('toolsProgressEvents TASKS_STEPS step_key merge', () => {
  it('updates existing checklist step instead of duplicating on re-emit', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const pendingCtx = makeTasksStepsCtx('pending', 'checklist_1');
    pendingCtx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await toolsProgressEvents(pendingCtx);

    const runningCtx = makeTasksStepsCtx('running', 'checklist_1');
    runningCtx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await toolsProgressEvents(runningCtx);

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps![0].step_key).toBe('checklist_1');
    expect(state.messages[0].progressSteps![0].status).toBeUndefined();

    const successCtx = makeTasksStepsCtx('success', 'checklist_1');
    successCtx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await toolsProgressEvents(successCtx);

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps![0].status).toBe('success');
  });

  it('merges checklist_root summary updates', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    for (const status of ['in_progress', 'success'] as const) {
      const ctx = makeTasksStepsCtx(status, 'checklist_root');
      ctx.data = {
        ...ctx.data,
        data: [{ text: 'Execution checklist (1/2 done)' }],
      } as never;
      ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
      await toolsProgressEvents(ctx);
    }

    expect(state.messages[0].progressSteps).toHaveLength(1);
    expect(state.messages[0].progressSteps![0].step_key).toBe('checklist_root');
    expect(state.messages[0].progressSteps![0].status).toBe('success');
  });

  it('maps skipped harness status to cancelled on merge', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const ctx = makeTasksStepsCtx('skipped', 'checklist_9');
    ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await toolsProgressEvents(ctx);

    expect(state.messages[0].progressSteps![0].status).toBe('cancelled');
  });

  it('merges is_plan todo tree by step_key (progress_root + todo_step_*)', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    const rootCtx = makeTasksStepsCtx('in_progress', 'progress_root');
    rootCtx.data = {
      ...rootCtx.data,
      is_plan: true,
      data: [{ text: 'Launch checklist' }],
    } as never;
    rootCtx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await toolsProgressEvents(rootCtx);

    const childCtx = makeTasksStepsCtx('pending', 'todo_step_a');
    childCtx.data = {
      ...childCtx.data,
      is_plan: true,
      parent_step_key: 'progress_root',
      data: [{ text: 'Draft outline' }],
    } as never;
    childCtx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
    await toolsProgressEvents(childCtx);

    expect(state.messages[0].progressSteps).toHaveLength(2);
    const root = state.messages[0].progressSteps!.find((s) => s.step_key === 'progress_root');
    const child = state.messages[0].progressSteps!.find((s) => s.step_key === 'todo_step_a');
    expect(root?.is_plan).toBe(true);
    expect(child?.parent_step_key).toBe('progress_root');
  });

  it('keeps distinct step_keys as separate progress items', async () => {
    const state = makeMessagesState();
    const setMessages = vi.fn((updater: (s: typeof state) => void) => {
      updater(state);
    });

    for (const key of ['checklist_1', 'checklist_2']) {
      const ctx = makeTasksStepsCtx('pending', key);
      ctx.actions.setMessages = setMessages as StreamCtx['actions']['setMessages'];
      await toolsProgressEvents(ctx);
    }

    expect(state.messages[0].progressSteps).toHaveLength(2);
    expect(state.messages[0].progressSteps!.map((s) => s.step_key).sort()).toEqual([
      'checklist_1',
      'checklist_2',
    ]);
  });
});
