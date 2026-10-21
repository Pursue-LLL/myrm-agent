import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  __resetPendingChatWikiQuerySuccessForTest,
  consumePendingChatWikiQuerySuccess,
  queuePendingChatWikiQuerySuccess,
} from '@/services/wiki/evidenceQuerySuccessPendingCore';

describe('wikiEvidenceQuerySuccessPendingCore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-27T10:00:00.000Z'));
    __resetPendingChatWikiQuerySuccessForTest();
  });

  afterEach(() => {
    __resetPendingChatWikiQuerySuccessForTest();
    vi.useRealTimers();
  });

  it('consumes queued pending success when chat and message id match', () => {
    queuePendingChatWikiQuerySuccess('chat-1', { contextKey: 'chat:a-1', turnDistance: 0 }, 'msg-1');

    expect(consumePendingChatWikiQuerySuccess('chat-1', 'msg-1')).toEqual({
      contextKey: 'chat:a-1',
      turnDistance: 0,
    });
    expect(consumePendingChatWikiQuerySuccess('chat-1', 'msg-1')).toBeUndefined();
  });

  it('keeps pending success when message id does not match', () => {
    queuePendingChatWikiQuerySuccess('chat-1', { contextKey: 'chat:a-1', turnDistance: 0 }, 'msg-1');

    expect(consumePendingChatWikiQuerySuccess('chat-1', 'msg-2')).toBeUndefined();
    expect(consumePendingChatWikiQuerySuccess('chat-1', 'msg-1')).toEqual({
      contextKey: 'chat:a-1',
      turnDistance: 0,
    });
  });

  it('expires pending success after ttl', () => {
    queuePendingChatWikiQuerySuccess('chat-1', { contextKey: 'chat:a-1', turnDistance: 0 }, 'msg-1');
    vi.advanceTimersByTime(120_001);

    expect(consumePendingChatWikiQuerySuccess('chat-1', 'msg-1')).toBeUndefined();
  });

  it('ignores empty chat ids', () => {
    queuePendingChatWikiQuerySuccess('  ', { contextKey: 'chat:a-1', turnDistance: 0 }, 'msg-1');
    expect(consumePendingChatWikiQuerySuccess('chat-1', 'msg-1')).toBeUndefined();
  });
});
