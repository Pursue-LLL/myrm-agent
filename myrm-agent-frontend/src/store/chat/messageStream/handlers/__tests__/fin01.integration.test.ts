/**
 * FIN-01 Integration Test: Verifies the full chain from SSE event → handler → usePlanStore
 * without mocking the plan store. Only external deps (network, toast, notification) are mocked.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';

vi.mock('@/services/notification', () => ({
  notificationService: { notify: vi.fn() },
}));

vi.mock('@/lib/utils/completionSound', () => ({
  playCompletionSound: vi.fn(() => false),
}));

vi.mock('@/services/chat', () => ({
  getChatDetail: vi.fn(async () => ({ chat: {} })),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { error: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: vi.fn(async () => ({ ok: true, json: async () => ({ plan: null }) })),
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    GOAL_STATUS: 'goal_status',
    FILE_MUTATION_FAILED: 'file_mutation_failed',
    MESSAGE_END: 'message_end',
    ERROR: 'error',
    AGENT_CANCELLED: 'agent_cancelled',
    STEERING: 'steering',
    ITERATION_LIMIT_REACHED: 'iteration_limit_reached',
    CONTEXT_OVERFLOW_RESET: 'context_overflow_reset',
    TOOL_FALLBACK: 'tool_fallback',
    CONTEXT_REFERENCE_WARNING: 'context_reference_warning',
    PTC_NOTIFY: 'ptc_notify',
  },
  findAssistantMessageIndex: vi.fn(() => 0),
  normalizeGoalState: vi.fn(),
  getUserFriendlyError: vi.fn(async () => ({ message: 'Error', hint: undefined })),
  useChatStore: {
    getState: vi.fn(() => ({ chatId: 'c1', setWorkspaceDir: vi.fn(), initializeChat: vi.fn() })),
  },
  useConfigStore: {
    getState: () => ({ enableCompletionSound: false, enableWebNotifications: false }),
  },
  useToolApprovalStore: {
    getState: vi.fn(() => ({ unmarkProcessing: vi.fn() })),
  },
  playCompletionSound: vi.fn(() => false),
  getContextOverflowMessage: vi.fn(() => 'overflow'),
}));

import { completionEvents } from '../completionEvents';
import { agentControlEvents } from '../agentControlEvents';
import type { StreamCtx } from '../../streamContext';

function makeActivePlan() {
  return {
    goal: 'Integration test',
    reasoning: '',
    steps: [
      { step_id: 'a', description: 'Step A', expected_output: '', status: 'in_progress' as const, dependencies: [] },
      { step_id: 'b', description: 'Step B', expected_output: '', status: 'pending' as const, dependencies: [] },
    ],
  };
}

function makeCompletedPlan() {
  return {
    goal: 'Completed task',
    reasoning: '',
    steps: [
      { step_id: 'a', description: 'Step A', expected_output: '', status: 'completed' as const, dependencies: [] },
      { step_id: 'b', description: 'Step B', expected_output: '', status: 'completed' as const, dependencies: [] },
    ],
  };
}

function makeBaseCtx(type: string, extra: Record<string, unknown> = {}): StreamCtx {
  return {
    data: { type, messageId: 'msg-1', ...extra } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: 'done',
    state: {
      messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date(), progressSteps: [] }],
      messageAppeared: false,
      loading: true,
    } as never,
    actions: {
      setMessages: vi.fn((updater: (s: Record<string, unknown>) => void) => updater({
        messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date(), progressSteps: [] }],
        loading: true,
        messageAppeared: false,
      })),
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      _processSuggestions: vi.fn(),
      scheduleAutoSave: vi.fn(),
    } as never,
    files: [],
  };
}

describe('FIN-01 Integration: SSE event → handler → real usePlanStore', () => {
  beforeEach(() => {
    usePlanStore.setState({ plan: null, isLoading: false });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('MESSAGE_END clears active plan (real store)', async () => {
    usePlanStore.setState({ plan: makeActivePlan() });
    expect(usePlanStore.getState().plan).not.toBeNull();

    const ctx = makeBaseCtx('message_end');
    await completionEvents(ctx);
    await vi.dynamicImportSettled();

    expect(usePlanStore.getState().plan).toBeNull();
  });

  it('MESSAGE_END preserves completed plan (real store)', async () => {
    const completed = makeCompletedPlan();
    usePlanStore.setState({ plan: completed });

    const ctx = makeBaseCtx('message_end');
    await completionEvents(ctx);
    await vi.dynamicImportSettled();

    expect(usePlanStore.getState().plan).toEqual(completed);
  });

  it('ERROR event clears active plan (real store)', async () => {
    usePlanStore.setState({ plan: makeActivePlan() });

    const ctx = makeBaseCtx('error', { error: 'Rate limit exceeded' });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(usePlanStore.getState().plan).toBeNull();
  });

  it('AGENT_CANCELLED clears active plan (real store)', async () => {
    usePlanStore.setState({ plan: makeActivePlan() });

    const ctx = makeBaseCtx('agent_cancelled', { data: { reason: 'user_cancelled' } });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(usePlanStore.getState().plan).toBeNull();
  });

  it('AGENT_CANCELLED preserves completed plan (real store)', async () => {
    const completed = makeCompletedPlan();
    usePlanStore.setState({ plan: completed });

    const ctx = makeBaseCtx('agent_cancelled', { data: { reason: 'user_cancelled' } });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(usePlanStore.getState().plan).toEqual(completed);
  });

  it('STEERING does not affect plan state', async () => {
    const plan = makeActivePlan();
    usePlanStore.setState({ plan });

    const ctx = makeBaseCtx('steering', { data: { messages: ['steer'] } });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(usePlanStore.getState().plan).toEqual(plan);
  });
});
