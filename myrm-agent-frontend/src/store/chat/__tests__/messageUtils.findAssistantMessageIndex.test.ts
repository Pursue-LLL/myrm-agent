import { describe, expect, it } from 'vitest';
import { ensureAssistantStreamMessage, findAssistantMessageIndex } from '@/store/chat/messageUtils';
import type { Message } from '@/store/chat/types';

function row(role: Message['role'], messageId: string, requestMessageId?: string): Message {
  return { role, messageId, chatId: 'c1', content: '', createdAt: new Date(), requestMessageId } as Message;
}

describe('findAssistantMessageIndex', () => {
  it('finds a streamed row by its own id', () => {
    expect(findAssistantMessageIndex([row('user', 'u1'), row('assistant', 'r-1')], 'r-1')).toBe(1);
  });

  it('finds a row hydrated from the DB by the request it was streamed for', () => {
    const messages = [row('user', 'r-1'), row('assistant', 'uuid-1', 'r-1')];

    expect(findAssistantMessageIndex(messages, 'r-1')).toBe(1);
  });

  it('picks the latest stored segment of a turn that paused and resumed', () => {
    const messages = [row('user', 'r-1'), row('assistant', 'uuid-1', 'r-1'), row('assistant', 'uuid-2', 'r-1')];

    expect(findAssistantMessageIndex(messages, 'r-1')).toBe(2);
  });

  it('prefers the exact id over a request id match', () => {
    const messages = [row('assistant', 'uuid-1', 'r-1'), row('assistant', 'r-1')];

    expect(findAssistantMessageIndex(messages, 'r-1')).toBe(1);
  });

  it('does not match user rows', () => {
    expect(findAssistantMessageIndex([row('user', 'r-1')], 'r-1')).toBe(-1);
  });

  it('matches nothing for an event without a message id, even though most rows have no request id', () => {
    const messages = [row('user', 'u1'), row('assistant', 'r-1')];

    expect(findAssistantMessageIndex(messages, undefined as unknown as string)).toBe(-1);
    expect(findAssistantMessageIndex(messages, '')).toBe(-1);
  });
});

describe('ensureAssistantStreamMessage', () => {
  it('reuses the hydrated row of the turn instead of adding a second one', () => {
    const messages = [row('user', 'r-1'), row('assistant', 'uuid-1', 'r-1')];

    expect(ensureAssistantStreamMessage(messages, 'r-1', 'c1')).toBe(1);
    expect(messages).toHaveLength(2);
  });

  it('adds a row for a turn the transcript does not show', () => {
    const messages = [row('user', 'r-2')];

    expect(ensureAssistantStreamMessage(messages, 'r-2', 'c1')).toBe(1);
    expect(messages[1]).toMatchObject({ role: 'assistant', messageId: 'r-2' });
  });
});
