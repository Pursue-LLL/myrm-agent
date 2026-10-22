/**
 * The record a card keeps survives the round trip through the database.
 *
 * Real scenario: the user answers a clarification, closes the tab and reopens the chat. The
 * rows come back from `/chats/{id}/messages` with the cards in `extra_data`; the cards must still say how they were
 * settled, and the summarizers must read what the server wrote.
 */
import { describe, expect, it } from 'vitest';

import { parseMessages } from '@/store/chat/messageHydration';
import { summarizeClarificationRecord } from '@/store/chat/hitlAnswerRecord';
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

  it('reads a pending form the way the live event does', () => {
    // Shape of the server's `AskQuestionInput.model_dump()`, which is what extra_data persists.
    const form = {
      title: null,
      requires_confirmation: true,
      context: null,
      questions: [
        {
          id: 'targets',
          prompt: 'Which environments?',
          options: [
            { id: 'prod', label: 'Production', description: null },
            { id: 'staging', label: 'Staging', description: null },
          ],
          allow_multiple: true,
        },
      ],
    };
    const [parsed] = parseMessages([persisted({ clarification: { answered: false, form } })]);

    expect(parsed.clarification?.form).toEqual({
      requiresConfirmation: true,
      questions: [
        {
          id: 'targets',
          prompt: 'Which environments?',
          allowMultiple: true,
          options: [
            { id: 'prod', label: 'Production' },
            { id: 'staging', label: 'Staging' },
          ],
        },
      ],
    });
  });

  it('reads a card settled before records existed as answered without a record', () => {
    const [parsed] = parseMessages([persisted({ clarification: { answered: true } })]);

    expect(parsed.clarification?.answered).toBe(true);
    expect(parsed.clarification?.answerRecord).toBeUndefined();
  });
});
