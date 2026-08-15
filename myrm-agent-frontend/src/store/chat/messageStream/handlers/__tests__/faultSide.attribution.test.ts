/**
 * fault_side attribution — ERROR and TOOL_FAILURE stream events must surface
 * the deterministic FaultSide token on their progress steps so the GUI can
 * tell users who owns the failure (model / tool / pipeline / env / owner).
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/store/chat/pendingGapRetry', () => ({
  scheduleFlushPendingGapRetry: vi.fn(),
}));

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ clearActivePlan: vi.fn() }) },
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    ERROR: 'error',
    AGENT_CANCELLED: 'agent_cancelled',
    TOOL_FAILURE: 'tool_failure',
    TOOL_STDOUT_CHUNK: 'tool_stdout_chunk',
    TOOL_EVICTED_REF: 'tool_evicted_ref',
    TASKS_STEPS: 'tasks_steps',
    TOOL_HEARTBEAT: 'tool_heartbeat',
  },
  findAssistantMessageIndex: vi.fn(() => 0),
  releaseInspectorControls: vi.fn(),
  resolveStreamChatId: (state: { chatId?: string; messages?: Array<{ chatId?: string }> }) =>
    state.chatId?.trim() || state.messages?.[0]?.chatId?.trim() || '',
  getUserFriendlyError: vi.fn(async () => ({ message: 'failed', hint: undefined })),
  useToolApprovalStore: {
    getState: vi.fn(() => ({ unmarkProcessing: vi.fn() })),
  },
}));

import { agentControlEvents } from '../agentControlEvents';
import { toolLifecycleEvents } from '../toolLifecycleEvents';
import type { StreamCtx } from '../../streamContext';
import type { ProgressItem } from '@/store/chat/types';

function makeAssistantState() {
  return {
    messages: [
      {
        messageId: 'msg-1',
        chatId: 'c1',
        role: 'assistant' as const,
        content: '',
        createdAt: new Date(),
        progressSteps: [] as ProgressItem[],
      },
    ],
  };
}

function makeCtx(overrides: Partial<StreamCtx['data']> & { type: string }): StreamCtx {
  const state = makeAssistantState();
  const ctx = {
    data: { messageId: 'msg-1', ...overrides } as never,
    input: '',
    sources: undefined,
    added: false,
    recievedMessage: '',
    state: state as never,
    actions: {
      setLoading: vi.fn(),
      setMessages: vi.fn((updater: (s: { messages: unknown[] }) => void) => updater(state as never)),
      setMessageAppeared: vi.fn(),
      _processSuggestions: vi.fn(),
      scheduleAutoSave: vi.fn(),
    } as never,
    files: [],
  };
  return ctx;
}

describe('agentControlEvents fault_side', () => {
  it('surfaces fault_side from the ERROR event onto the progress step', async () => {
    const ctx = makeCtx({
      type: 'error',
      error: 'rate limit exceeded',
      error_kind: 'rate_limit',
      fault_side: 'env',
      diagnostic_result: {
        error_type: 'rate_limit',
        user_message: 'Rate limit exceeded',
        resolution_steps: [],
        locale: 'en',
      },
    });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    const step = (ctx.state as { messages: Array<{ progressSteps: ProgressItem[] }> }).messages[0].progressSteps[0];
    expect(step.step_key).toBe('processing_failed');
    expect(step.fault_side).toBe('env');
  });

  it('omits fault_side when the ERROR event carries none', async () => {
    const ctx = makeCtx({
      type: 'error',
      error: 'boom',
      diagnostic_result: { error_type: 'x', user_message: 'boom', resolution_steps: [], locale: 'en' },
    });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    const step = (ctx.state as { messages: Array<{ progressSteps: ProgressItem[] }> }).messages[0].progressSteps[0];
    expect(step.fault_side).toBeUndefined();
  });
});

describe('toolLifecycleEvents fault_side', () => {
  it('surfaces fault_side from the TOOL_FAILURE event onto the last step', async () => {
    const state = makeAssistantState();
    state.messages[0].progressSteps = [{ step_key: 'code_execute', tool_name: 'code_execute' }];
    const ctx: StreamCtx = {
      data: {
        type: 'tool_failure',
        messageId: 'msg-1',
        tool_name: 'code_execute',
        error: 'Segmentation fault',
        fault_side: 'harness_tool',
      } as never,
      input: '',
      sources: undefined,
      added: false,
      recievedMessage: '',
      state: state as never,
      actions: {
        setLoading: vi.fn(),
        setMessages: vi.fn((updater: (s: { messages: unknown[] }) => void) => updater(state as never)),
        setMessageAppeared: vi.fn(),
        _processSuggestions: vi.fn(),
        scheduleAutoSave: vi.fn(),
      } as never,
      files: [],
    };
    await toolLifecycleEvents(ctx);

    const step = state.messages[0].progressSteps[0];
    expect(step.status).toBe('error');
    expect(step.fault_side).toBe('harness_tool');
  });

  it('does not set fault_side when the TOOL_FAILURE event carries none', async () => {
    const state = makeAssistantState();
    state.messages[0].progressSteps = [{ step_key: 'code_execute', tool_name: 'code_execute' }];
    const ctx: StreamCtx = {
      data: {
        type: 'tool_failure',
        messageId: 'msg-1',
        tool_name: 'code_execute',
        error: 'boom',
      } as never,
      input: '',
      sources: undefined,
      added: false,
      recievedMessage: '',
      state: state as never,
      actions: {
        setLoading: vi.fn(),
        setMessages: vi.fn((updater: (s: { messages: unknown[] }) => void) => updater(state as never)),
        setMessageAppeared: vi.fn(),
        _processSuggestions: vi.fn(),
        scheduleAutoSave: vi.fn(),
      } as never,
      files: [],
    };
    await toolLifecycleEvents(ctx);

    const step = state.messages[0].progressSteps[0];
    expect(step.status).toBe('error');
    expect(step.fault_side).toBeUndefined();
  });
});
