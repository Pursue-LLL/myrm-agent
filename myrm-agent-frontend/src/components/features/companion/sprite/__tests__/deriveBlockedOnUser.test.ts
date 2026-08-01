import { describe, expect, it } from 'vitest';

import { deriveBlockedOnUser, hasPendingClarificationFromMessages } from '../deriveBlockedOnUser';

describe('deriveBlockedOnUser', () => {
  const baseInput = {
    toolApprovalQueueLength: 0,
    approvalQueueLength: 0,
    hasPendingClarification: false,
    desktopControlPending: false,
    browserTakeoverPending: false,
  };

  it('returns false when no HITL signals are active', () => {
    expect(deriveBlockedOnUser(baseInput)).toBe(false);
  });

  it('returns true when tool approval queue is non-empty', () => {
    expect(deriveBlockedOnUser({ ...baseInput, toolApprovalQueueLength: 1 })).toBe(true);
  });

  it('returns true when server approval queue is non-empty', () => {
    expect(deriveBlockedOnUser({ ...baseInput, approvalQueueLength: 1 })).toBe(true);
  });

  it('returns true when desktop control approval is pending', () => {
    expect(deriveBlockedOnUser({ ...baseInput, desktopControlPending: true })).toBe(true);
  });

  it('returns true when browser takeover is pending', () => {
    expect(deriveBlockedOnUser({ ...baseInput, browserTakeoverPending: true })).toBe(true);
  });

  it('returns true when clarify form is unanswered', () => {
    expect(deriveBlockedOnUser({ ...baseInput, hasPendingClarification: true })).toBe(true);
  });
});

describe('hasPendingClarificationFromMessages', () => {
  it('detects unanswered assistant clarification', () => {
    expect(
      hasPendingClarificationFromMessages([
        {
          messageId: 'm1',
          chatId: 'c1',
          role: 'assistant',
          content: '',
          createdAt: new Date(),
          clarification: { answered: false, isResumeMode: true },
        },
      ]),
    ).toBe(true);
  });
});
