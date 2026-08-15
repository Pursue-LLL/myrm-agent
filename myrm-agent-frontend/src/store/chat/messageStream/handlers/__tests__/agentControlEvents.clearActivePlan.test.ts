/**
 * Tests that agentControlEvents calls clearActivePlan on ERROR and AGENT_CANCELLED,
 * and releases inspector turn engagement on all three terminal paths.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockClearActivePlan,
  mockUnmarkProcessing,
  mockReleaseTurnInspectorControls,
  mockFindAssistantMessageIndex,
} = vi.hoisted(() => ({
  mockClearActivePlan: vi.fn(),
  mockUnmarkProcessing: vi.fn(),
  mockReleaseTurnInspectorControls: vi.fn(),
  mockFindAssistantMessageIndex: vi.fn(() => 0),
}));

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ clearActivePlan: mockClearActivePlan }) },
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { error: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/store/chat/pendingGapRetry', () => ({
  scheduleFlushPendingGapRetry: vi.fn(),
}));

vi.mock('@/lib/inspector/releaseTurnInspectorControls', () => ({
  releaseTurnInspectorControls: mockReleaseTurnInspectorControls,
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
  findAssistantMessageIndex: mockFindAssistantMessageIndex,
  getUserFriendlyError: vi.fn(async () => ({ message: 'Error', hint: undefined })),
  releaseInspectorControls: (chatId: string) => mockReleaseTurnInspectorControls(chatId),
  resolveStreamChatId: (state: { chatId?: string; messages?: Array<{ chatId?: string }> }) =>
    state.chatId?.trim() || state.messages?.[0]?.chatId?.trim() || '',
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
    mockReleaseTurnInspectorControls.mockClear();
  });

  it('calls clearActivePlan and releases inspector controls on ERROR event', async () => {
    const ctx = makeCtx('error', { error: 'Something failed' });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockClearActivePlan).toHaveBeenCalledTimes(1);
    expect(mockReleaseTurnInspectorControls).toHaveBeenCalledTimes(1);
    expect(mockReleaseTurnInspectorControls).toHaveBeenCalledWith('c1');
  });

  it('calls clearActivePlan and releases inspector controls on AGENT_CANCELLED event', async () => {
    const ctx = makeCtx('agent_cancelled', { data: { reason: 'user_cancelled' } });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockClearActivePlan).toHaveBeenCalledTimes(1);
    expect(mockUnmarkProcessing).toHaveBeenCalledWith('msg-1');
    expect(mockReleaseTurnInspectorControls).toHaveBeenCalledTimes(1);
    expect(mockReleaseTurnInspectorControls).toHaveBeenCalledWith('c1');
  });

  it('releases inspector controls on CONTEXT_OVERFLOW_RESET event', async () => {
    const ctx = makeCtx('context_overflow_reset', { data: { chat_id: 'c1' } });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockReleaseTurnInspectorControls).toHaveBeenCalledTimes(1);
    expect(mockReleaseTurnInspectorControls).toHaveBeenCalledWith('c1');
  });

  it('does not call clearActivePlan or release inspector controls for STEERING event', async () => {
    const ctx = makeCtx('steering', { data: { messages: ['steer msg'] } });
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockClearActivePlan).not.toHaveBeenCalled();
    expect(mockReleaseTurnInspectorControls).not.toHaveBeenCalled();
  });

  it('releases inspector controls from state.chatId when the message list is empty (brand-new chat first turn)', async () => {
    const ctx = makeCtx('error', { error: 'Something failed' });
    ctx.state = {
      messages: [],
      messageAppeared: false,
      loading: true,
      chatId: 'c1',
    } as never;
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockReleaseTurnInspectorControls).toHaveBeenCalledTimes(1);
    expect(mockReleaseTurnInspectorControls).toHaveBeenCalledWith('c1');
  });

  it('passes fault_side through on ITERATION_LIMIT_REACHED into the progress step', async () => {
    let updatedState: Record<string, unknown> | undefined;
    const ctx = makeCtx('iteration_limit_reached', {
      data: { limit: 25, nodes_completed: 24, fault_side: 'harness_pipeline' },
    });
    (ctx.actions.setMessages as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      (updater: (s: Record<string, unknown>) => void) => {
        const base = {
          messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date(), progressSteps: [] }],
        };
        updatedState = base;
        updater(base as never);
        return base;
      },
    );
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();

    const messages = updatedState?.messages as Array<Record<string, unknown>>;
    const step = (messages?.[0].progressSteps as Array<Record<string, unknown>>).at(-1);
    expect(step).toMatchObject({
      step_key: 'iteration_limit_reached',
      status: 'warning',
      fault_side: 'harness_pipeline',
    });
  });

  it('creates the error message with the resolved chatId for a brand-new chat', async () => {
    mockFindAssistantMessageIndex.mockReturnValue(-1);
    const messages: Array<Record<string, unknown>> = [];
    const ctx = makeCtx('error', { error: 'Something failed' });
    ctx.state = {
      messages,
      messageAppeared: false,
      loading: true,
      chatId: 'c1',
    } as never;
    ctx.actions.setMessages = ((updater: (s: Record<string, unknown>) => void) => {
      updater({ messages, messageAppeared: false, loading: true });
    }) as never;

    await agentControlEvents(ctx);

    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({ chatId: 'c1', role: 'assistant' });
  });
});
