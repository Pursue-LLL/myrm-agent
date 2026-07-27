import { describe, expect, it, vi } from 'vitest';

import type { Message } from '@/store/chat/types';
import {
  recordChatWikiQueryAttempt,
  recordChatWikiQuerySubmitted,
  resolveChatWikiEvidenceContext,
} from '@/hooks/useMessageInputWikiEvidenceCore';

const recordWikiQueryAttemptMock = vi.fn();
const recordWikiQuerySubmittedMock = vi.fn();

vi.mock('@/services/wikiEvidenceMetrics', () => ({
  recordWikiQueryAttempt: (...args: unknown[]) => recordWikiQueryAttemptMock(...args),
  recordWikiQuerySubmitted: (...args: unknown[]) => recordWikiQuerySubmittedMock(...args),
}));

function makeMessage(overrides: Partial<Message>): Message {
  return {
    messageId: 'm-default',
    chatId: 'chat-1',
    createdAt: new Date('2026-07-27T00:00:00.000Z'),
    content: '',
    role: 'assistant',
    ...overrides,
  };
}

describe('useMessageInputWikiEvidenceCore', () => {
  it('prefers latest assistant KB evidence message as context key', () => {
    const messages: Message[] = [
      makeMessage({ messageId: 'u-1', role: 'user', content: 'hello' }),
      makeMessage({ messageId: 'a-1', role: 'assistant', sources: [{ index: 1, type: 'knowledge', kb_name: 'KB', snippet: 'S1' }] }),
      makeMessage({ messageId: 'a-2', role: 'assistant', sources: [{ index: 2, type: 'knowledge', kb_name: 'KB', summary: 'S2' }] }),
    ];

    expect(resolveChatWikiEvidenceContext(messages, 'chat-xyz')).toEqual({
      contextKey: 'chat:a-2',
      turnDistance: 0,
    });
  });

  it('calculates assistant turn distance for stale evidence context', () => {
    const messages: Message[] = [
      makeMessage({ messageId: 'a-1', role: 'assistant', sources: [{ index: 1, type: 'knowledge', kb_name: 'KB', snippet: 'S1' }] }),
      makeMessage({ messageId: 'a-2', role: 'assistant', content: 'no kb evidence' }),
    ];

    expect(resolveChatWikiEvidenceContext(messages, 'chat-xyz')).toEqual({
      contextKey: 'chat:a-1',
      turnDistance: 1,
    });
  });

  it('falls back to chat id context when no KB evidence exists', () => {
    const messages: Message[] = [
      makeMessage({ messageId: 'a-1', role: 'assistant', sources: [{ index: 1, type: 'web_search', title: 'web' }] }),
      makeMessage({ messageId: 'a-2', role: 'assistant', sources: [{ index: 2, type: 'knowledge', kb_name: 'KB' }] }),
    ];

    expect(resolveChatWikiEvidenceContext(messages, 'chat-xyz')).toEqual({
      contextKey: 'chat:chat-xyz',
      turnDistance: undefined,
    });
  });

  it('falls back to chat id context when evidence is beyond rollback boundary', () => {
    const messages: Message[] = [
      makeMessage({ messageId: 'a-evidence', role: 'assistant', sources: [{ index: 1, type: 'knowledge', kb_name: 'KB', snippet: 'S1' }] }),
      ...Array.from({ length: 9 }, (_, idx) =>
        makeMessage({
          messageId: `a-${idx}`,
          role: 'assistant',
          content: `assistant-${idx}`,
        }),
      ),
    ];

    expect(resolveChatWikiEvidenceContext(messages, 'chat-xyz')).toEqual({
      contextKey: 'chat:chat-xyz',
      turnDistance: undefined,
    });
  });

  it('records chat query attempt metric with resolved context', () => {
    const messages: Message[] = [
      makeMessage({ messageId: 'a-1', role: 'assistant', sources: [{ index: 1, type: 'knowledge', kb_name: 'KB', snippet: 'S1' }] }),
    ];

    recordWikiQueryAttemptMock.mockReset();
    recordChatWikiQueryAttempt(messages, 'chat-xyz');

    expect(recordWikiQueryAttemptMock).toHaveBeenCalledWith('chat', 'chat:a-1', 0);
  });

  it('records chat query success metric with resolved context', () => {
    const messages: Message[] = [
      makeMessage({ messageId: 'a-1', role: 'assistant', sources: [{ index: 1, type: 'knowledge', kb_name: 'KB', snippet: 'S1' }] }),
    ];

    recordWikiQuerySubmittedMock.mockReset();
    recordChatWikiQuerySubmitted(messages, 'chat-xyz');

    expect(recordWikiQuerySubmittedMock).toHaveBeenCalledWith('chat', 'chat:a-1', 0);
  });

  it('returns undefined context key when chat id is missing', () => {
    const messages: Message[] = [
      makeMessage({ messageId: 'a-1', role: 'assistant', sources: [{ index: 1, type: 'knowledge', kb_name: 'KB', snippet: 'S1' }] }),
    ];

    expect(resolveChatWikiEvidenceContext(messages, '   ')).toEqual({
      contextKey: undefined,
      turnDistance: undefined,
    });
  });
});
