import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Message } from '@/store/chat/types';
import { useAssistantMessageActions } from '../useAssistantMessageActions';

const mocks = vi.hoisted(() => ({
  sendMessage: vi.fn(),
  setState: vi.fn(),
  setMessages: vi.fn(),
  abort: vi.fn(),
  fetchPlan: vi.fn(),
  regenerateLastTurn: vi.fn(),
  cancelAgentRequest: vi.fn(),
  recordNegative: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) => selector({ sendMessage: mocks.sendMessage }),
    {
      getState: () => ({ abortController: { abort: mocks.abort }, setMessages: mocks.setMessages }),
      setState: mocks.setState,
    },
  ),
}));
vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ fetchPlan: mocks.fetchPlan }) },
}));
vi.mock('@/services/chat', () => ({
  regenerateLastTurn: mocks.regenerateLastTurn,
  cancelAgentRequest: mocks.cancelAgentRequest,
}));
vi.mock('@/services/wiki/evidenceMetrics', () => ({ recordQualityOutcomeNegative: mocks.recordNegative }));

function message(messageId: string, role: Message['role'], extra: Partial<Message> = {}): Message {
  return {
    messageId,
    chatId: 'chat-1',
    role,
    content: messageId,
    createdAt: new Date('2026-11-09T00:00:00.000Z'),
    ...extra,
  };
}

const TARGET = message('a1', 'assistant');

function mountActions({
  chatId = 'chat-1',
  hasKbEvidence = false,
}: { chatId?: string | null; hasKbEvidence?: boolean } = {}) {
  return renderHook(() => useAssistantMessageActions({ message: TARGET, chatId: chatId ?? undefined, hasKbEvidence }))
    .result.current;
}

type StateUpdater = (state: { messages: Message[] }) => Record<string, unknown>;

describe('useAssistantMessageActions regenerate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('does nothing without a chat', async () => {
    const { handleRegenerate } = mountActions({ chatId: null });

    await expect(handleRegenerate()).resolves.toBe(false);

    expect(mocks.regenerateLastTurn).not.toHaveBeenCalled();
    expect(mocks.setState).not.toHaveBeenCalled();
  });

  it('drops the answer, refreshes the plan and sends the query without its datetime tag', async () => {
    mocks.regenerateLastTurn.mockResolvedValue({
      success: true,
      query: '<current_datetime>2026-11-09</current_datetime> summarise',
      sibling_group_id: 'g1',
    });
    mocks.sendMessage.mockResolvedValue(true);
    const { handleRegenerate } = mountActions();

    await expect(handleRegenerate('be concise')).resolves.toBe(true);

    expect(mocks.regenerateLastTurn).toHaveBeenCalledWith('chat-1', 'be concise');
    expect(mocks.fetchPlan).toHaveBeenCalledWith('chat-1');
    expect(mocks.sendMessage).toHaveBeenCalledWith('summarise');
    const dropAnswer = mocks.setState.mock.calls[0][0] as StateUpdater;
    const user = message('u1', 'user');
    const otherAnswer = message('a2', 'assistant');
    expect(dropAnswer({ messages: [user, TARGET, otherAnswer] })).toEqual({
      messages: [user, otherAnswer],
      regenerateSiblingGroupId: 'g1',
      regenerateInstruction: 'be concise',
    });
  });

  it('clears the sibling hints once the turn was dispatched', async () => {
    mocks.regenerateLastTurn.mockResolvedValue({ success: true, query: 'again', sibling_group_id: 'g1' });
    mocks.sendMessage.mockResolvedValue(true);
    const { handleRegenerate } = mountActions();

    await handleRegenerate();

    expect(mocks.setState).toHaveBeenLastCalledWith({
      regenerateSiblingGroupId: undefined,
      regenerateInstruction: undefined,
    });
  });

  it('counts replacing an answer that cited knowledge-base evidence as a negative outcome', async () => {
    mocks.regenerateLastTurn.mockResolvedValue({ success: true, query: 'again' });
    mocks.sendMessage.mockResolvedValue(true);

    await mountActions({ hasKbEvidence: true }).handleRegenerate();

    expect(mocks.recordNegative).toHaveBeenCalledWith('chat', 1, 'chat:a1');
  });

  it('records no quality outcome for an answer without knowledge-base evidence', async () => {
    mocks.regenerateLastTurn.mockResolvedValue({ success: true, query: 'again' });
    mocks.sendMessage.mockResolvedValue(true);

    await mountActions().handleRegenerate();

    expect(mocks.recordNegative).not.toHaveBeenCalled();
  });

  it.each([
    ['a refused request', { success: false, query: 'again' }],
    ['a reply without a query', { success: true }],
  ])('keeps the answer and sends nothing for %s', async (_name, reply) => {
    mocks.regenerateLastTurn.mockResolvedValue(reply);

    await expect(mountActions().handleRegenerate()).resolves.toBe(false);

    expect(mocks.sendMessage).not.toHaveBeenCalled();
    expect(mocks.setState).toHaveBeenCalledTimes(1);
    expect(mocks.setState).toHaveBeenCalledWith({
      regenerateSiblingGroupId: undefined,
      regenerateInstruction: undefined,
    });
  });

  it('reports a failure of the request and still clears the sibling hints', async () => {
    mocks.regenerateLastTurn.mockRejectedValue(new Error('held by a risk rule'));

    await expect(mountActions().handleRegenerate('use the key I pasted')).resolves.toBe(false);

    expect(console.error).toHaveBeenCalledWith('Regenerate failed:', expect.any(Error));
    expect(mocks.setState).toHaveBeenLastCalledWith({
      regenerateSiblingGroupId: undefined,
      regenerateInstruction: undefined,
    });
  });
});

describe('useAssistantMessageActions cancel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('cancels the request, closes the stream and drops the waiting step it left behind', async () => {
    mocks.cancelAgentRequest.mockResolvedValue(undefined);

    await mountActions().handleCancel();

    expect(mocks.cancelAgentRequest).toHaveBeenCalledWith('a1');
    expect(mocks.abort).toHaveBeenCalledTimes(1);
    const dropWaitingStep = mocks.setMessages.mock.calls[0][0] as (draft: { messages: Message[] }) => void;
    const draft = {
      messages: [
        message('a1', 'assistant', { progressSteps: [{ step_key: 'waiting_for_turn' }, { step_key: 'searching' }] }),
      ],
    };
    dropWaitingStep(draft);
    expect(draft.messages[0].progressSteps).toEqual([{ step_key: 'searching' }]);
  });

  it('leaves the stream and the transcript alone when the server refuses to cancel', async () => {
    mocks.cancelAgentRequest.mockRejectedValue(new Error('gone'));

    await mountActions().handleCancel();

    expect(console.error).toHaveBeenCalledWith('Cancel failed:', expect.any(Error));
    expect(mocks.abort).not.toHaveBeenCalled();
    expect(mocks.setMessages).not.toHaveBeenCalled();
  });
});
