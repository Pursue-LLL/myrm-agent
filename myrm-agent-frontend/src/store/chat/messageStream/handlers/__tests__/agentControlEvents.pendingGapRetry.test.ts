/**
 * Tests that agentControlEvents schedules pending gap retry flush on ERROR/CANCEL.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockScheduleFlushPendingGapRetry = vi.fn();

vi.mock('@/store/chat/pendingGapRetry', () => ({
  scheduleFlushPendingGapRetry: (...args: unknown[]) => mockScheduleFlushPendingGapRetry(...args),
}));

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ clearActivePlan: vi.fn() }) },
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    ERROR: 'error',
    AGENT_CANCELLED: 'agent_cancelled',
    STEERING: 'steering',
  },
  findAssistantMessageIndex: vi.fn(() => 0),
  getUserFriendlyError: vi.fn(async () => ({ message: 'failed', hint: undefined })),
  useToolApprovalStore: {
    getState: vi.fn(() => ({ unmarkProcessing: vi.fn() })),
  },
}));

import { agentControlEvents } from '../agentControlEvents';
import type { StreamCtx } from '../../streamContext';

function makeCtx(eventType: string): StreamCtx {
  return {
    data: { type: eventType, messageId: 'msg-1', error: 'rate_limited' } as never,
    input: '',
    sources: undefined,
    added: false,
    recievedMessage: '',
    state: {
      messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() }],
      messageAppeared: false,
      loading: true,
    } as never,
    actions: {
      setMessages: vi.fn((updater: (s: Record<string, unknown>) => void) => updater({
        messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() }],
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

describe('agentControlEvents pendingGapRetry flush', () => {
  beforeEach(() => {
    mockScheduleFlushPendingGapRetry.mockClear();
  });

  it('calls scheduleFlushPendingGapRetry on ERROR', async () => {
    await agentControlEvents(makeCtx('error'));
    await vi.dynamicImportSettled();
    expect(mockScheduleFlushPendingGapRetry).toHaveBeenCalledTimes(1);
  });

  it('calls scheduleFlushPendingGapRetry on AGENT_CANCELLED', async () => {
    const ctx = makeCtx('agent_cancelled');
    ctx.data = { type: 'agent_cancelled', messageId: 'msg-1', data: { reason: 'user_cancelled' } } as never;
    await agentControlEvents(ctx);
    await vi.dynamicImportSettled();
    expect(mockScheduleFlushPendingGapRetry).toHaveBeenCalledTimes(1);
  });
});
