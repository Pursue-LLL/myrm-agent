import { describe, expect, it } from 'vitest';

import { removeWaitingForTurnStep } from '@/store/chat/messageUtils';
import type { Message } from '@/store/chat/types';

function makeMessage(messageId: string, steps: Array<{ step_key: string }>): Message {
  return {
    messageId,
    chatId: 'chat-1',
    role: 'assistant',
    content: 'answer',
    createdAt: new Date('2026-08-04T00:00:00.000Z'),
    progressSteps: steps.map((s) => ({ ...s })),
  } as Message;
}

describe('removeWaitingForTurnStep', () => {
  it('removes waiting_for_turn step from the target message only', () => {
    const waitingStep = { step_key: 'waiting_for_turn' };
    const otherStep = { step_key: 'model_failover' };
    const messages = [
      makeMessage('msg-target', [waitingStep, otherStep]),
      makeMessage('msg-other', [waitingStep]),
    ];

    const result = removeWaitingForTurnStep(messages, 'msg-target');

    expect(result[0].progressSteps).toEqual([otherStep]);
    // 其他消息不受影响
    expect(result[1].progressSteps).toEqual([waitingStep]);
  });

  it('returns the same array when the target message has no waiting_for_turn step', () => {
    const otherStep = { step_key: 'tool_call_truncated' };
    const messages = [makeMessage('msg-target', [otherStep])];

    const result = removeWaitingForTurnStep(messages, 'msg-target');

    expect(result).toBe(messages);
  });

  it('is a no-op for an unknown message id', () => {
    const waitingStep = { step_key: 'waiting_for_turn' };
    const messages = [makeMessage('msg-target', [waitingStep])];

    const result = removeWaitingForTurnStep(messages, 'msg-ghost');

    expect(result).toBe(messages);
  });

  it('does not mutate the original messages (immutable update)', () => {
    const waitingStep = { step_key: 'waiting_for_turn' };
    const messages = [makeMessage('msg-target', [waitingStep])];

    removeWaitingForTurnStep(messages, 'msg-target');

    expect(messages[0].progressSteps).toEqual([waitingStep]);
  });

  it('handles empty messages array', () => {
    expect(removeWaitingForTurnStep([], 'anything')).toEqual([]);
  });
});
