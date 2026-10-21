import { describe, expect, it } from 'vitest';

import type { Message } from '@/store/chat/types';
import { findLastTurnAnswerId } from '../lastTurnAnswer';

const CREATED_AT = new Date('2026-10-13T00:00:00.000Z');

function message(messageId: string, role: Message['role'], extra: Partial<Message> = {}): Message {
  return { messageId, chatId: 'chat-1', role, content: messageId, createdAt: CREATED_AT, ...extra };
}

const user = (id: string) => message(id, 'user');
const answer = (id: string) => message(id, 'assistant');
const notice = (id: string) => message(id, 'assistant', { isSystemNotice: true });

describe('findLastTurnAnswerId', () => {
  it('returns the answer of the latest turn, not an earlier turn', () => {
    expect(findLastTurnAnswerId([user('u1'), answer('a1'), user('u2'), answer('a2')])).toBe('a2');
  });

  it('is not hidden by system notices that follow the answer', () => {
    expect(findLastTurnAnswerId([user('u1'), answer('a1'), notice('n1'), notice('n2')])).toBe('a1');
  });

  it('never picks a system notice, even when it is the only assistant message of the turn', () => {
    expect(findLastTurnAnswerId([user('u1'), answer('a1'), user('u2'), notice('n1')])).toBeNull();
  });

  it('does not reach back into an earlier turn while the latest user message has no answer yet', () => {
    expect(findLastTurnAnswerId([user('u1'), answer('a1'), user('u2')])).toBeNull();
  });

  it('skips non-conversation rows such as the compacted summary view', () => {
    const summary = message('compacted-summary-view', 'system', { isCompactedSummaryView: true });
    expect(findLastTurnAnswerId([summary, user('u1'), answer('a1')])).toBe('a1');
    expect(findLastTurnAnswerId([summary])).toBeNull();
  });

  it('returns null for an empty conversation', () => {
    expect(findLastTurnAnswerId([])).toBeNull();
  });

  it('picks the latest answer when the turn holds several', () => {
    expect(findLastTurnAnswerId([user('u1'), answer('a1'), answer('a2')])).toBe('a2');
  });
});
