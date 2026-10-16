/**
 * The Deep Research clarify phase reports how the question was settled, and the card keeps that record.
 *
 * Real scenario: a Deep Research run asks which framework to compare; the user answers, or leaves and the timeout
 * resolves it. Both arrive as a `clarify` `resolved` status event, and the card must show which one happened.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('../handlerDeps', () => ({ findAssistantMessageIndex: vi.fn(() => 0) }));

import type { Message } from '@/store/chat/types';

import type { StreamCtx } from '../../streamContext';
import { applyStatusPhaseData } from '../statusStreamPhaseData';

function resolveClarify(statusData: Record<string, unknown>): NonNullable<Message['clarification']> {
  const state = {
    messages: [{ messageId: 'msg-1', role: 'assistant', clarification: { answered: false } }] as Message[],
  };
  const ctx = {
    data: { messageId: 'msg-1' },
    actions: { setMessages: (recipe: (draft: typeof state) => void) => recipe(state) },
  } as unknown as StreamCtx;

  applyStatusPhaseData(ctx, { phase: 'clarify', status: 'resolved', ...statusData });

  const card = state.messages[0].clarification;
  if (!card) {
    throw new Error('the clarification card disappeared');
  }
  return card;
}

describe('clarify resolved status', () => {
  it.each([
    ['the answer the user gave', { by: 'user', value: { framework: 'langchain' } }],
    ['the timeout that resolved it', { by: 'timeout', value: {} }],
  ])('keeps %s on the card', (_label, answerRecord) => {
    const card = resolveClarify({ answerRecord });

    expect(card.answered).toBe(true);
    expect(card.answerRecord).toEqual(answerRecord);
  });

  it('settles the card without a record when the event carries none', () => {
    const card = resolveClarify({});

    expect(card.answered).toBe(true);
    expect(card.answerRecord).toBeUndefined();
  });

  it.each([
    ['an unknown author', { by: 'agent', value: {} }],
    ['a value of the wrong shape', 'answered'],
  ])('ignores a record with %s', (_label, answerRecord) => {
    const card = resolveClarify({ answerRecord });

    expect(card.answered).toBe(true);
    expect(card.answerRecord).toBeUndefined();
  });
});
