/**
 * Tests that agentControlEvents calls clearActivePlan on ERROR and AGENT_CANCELLED.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockClearActivePlan = vi.fn();
const mockUnmarkProcessing = vi.fn();

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ clearActivePlan: mockClearActivePlan }) },
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { error: vi.fn(), warning: vi.fn() },
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
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
  getUserFriendlyError: vi.fn(async () => ({ message: 'Error', hint: undefined })),
  useChatStore: {
    getState: vi.fn(() => ({ chatId: 'c1', initializeChat: vi.fn() })),
  },
  useToolApprovalStore: {
    getState: vi.fn(() => ({ unmarkProcessing: mockUnmarkProcessing })),
  },
  getContextOverflowMessage: vi.fn(() => 'overflow'),
}));

import { agentControlEvents } from '../agentControlEvents';
import type { StreamCtx } from '../../streamContext';

function makeCtx(type: string, extra: Record<string, unknown> = {}): StreamCtx {
  return {
    data: { type, messageId: 'msg-1', ...extra } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
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
    } as never,
    files: [],
  };
}

describe('agentControlEvents clearActivePlan', () => {
  beforeEach(() => {
    mockClearActivePlan.mockClear();
    mockUnmarkProcessing.mockClear();
  });

  it('calls clearActivePlan on ERROR event', async () => {
    const ctx = makeCtx('error', { error: 'Something failed' });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockClearActivePlan).toHaveBeenCalledTimes(1);
  });

  it('calls clearActivePlan on AGENT_CANCELLED event', async () => {
    const ctx = makeCtx('agent_cancelled', { data: { reason: 'user_cancelled' } });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockClearActivePlan).toHaveBeenCalledTimes(1);
    expect(mockUnmarkProcessing).toHaveBeenCalledWith('msg-1');
  });

  it('does not call clearActivePlan for STEERING event', async () => {
    const ctx = makeCtx('steering', { data: { messages: ['steer msg'] } });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockClearActivePlan).not.toHaveBeenCalled();
  });
});
