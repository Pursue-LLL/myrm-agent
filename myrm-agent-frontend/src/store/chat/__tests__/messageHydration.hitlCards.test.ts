/**
 * The record a card keeps survives the round trip through the database.
 *
 * Real scenario: the user answers a clarification and a directory request, closes the tab and reopens the chat. The
 * rows come back from `/chats/{id}/messages` with the cards in `extra_data`; the cards must still say how they were
 * settled, and the summarizers must read what the server wrote.
 */
import { describe, expect, it } from 'vitest';

import { parseMessages } from '@/store/chat/messageHydration';
import { summarizeClarificationRecord, summarizeDirectoryRecord } from '@/store/chat/hitlAnswerRecord';
import type { Message } from '@/store/chat/types';

function persisted(card: Record<string, unknown>): Message {
  return {
    messageId: 'm-1',
    chatId: 'chat-1',
    role: 'assistant',
    content: '',
    createdAt: new Date('2026-10-16T00:00:00.000Z'),
    metadata: card,
  } as unknown as Message;
}

describe('parseMessages settled cards', () => {
  it('keeps the answer record of a clarification the user answered', () => {
    const form = {
      questions: [{ id: 'strategy', prompt: 'Choose a strategy', options: [{ id: 'canary', label: 'Canary' }] }],
    };
    const [parsed] = parseMessages([
      persisted({
        clarification: { answered: true, form, answerRecord: { by: 'user', value: { strategy: 'canary' } } },
      }),
    ]);

    expect(parsed.clarification?.answered).toBe(true);
    expect(summarizeClarificationRecord(parsed.clarification?.answerRecord, parsed.clarification?.form)).toEqual({
      kind: 'answered',
      lines: [{ key: 'strategy', prompt: 'Choose a strategy', text: 'Canary' }],
    });
  });

  it('keeps the timeout record of a directory request nobody answered', () => {
    const [parsed] = parseMessages([
      persisted({
        directoryRequest: {
          answered: true,
          request: { path: '/work' },
          answerRecord: { by: 'timeout', value: { granted: false } },
        },
      }),
    ]);

    expect(summarizeDirectoryRecord(parsed.directoryRequest?.answerRecord)).toEqual({ kind: 'timeout' });
  });

  it('reads a card settled before records existed as answered without a record', () => {
    const [parsed] = parseMessages([persisted({ clarification: { answered: true } })]);

    expect(parsed.clarification?.answered).toBe(true);
    expect(parsed.clarification?.answerRecord).toBeUndefined();
  });
});
