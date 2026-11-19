import { describe, expect, it } from 'vitest';

import { findActivePendingClarification, normalizeHydratedClarification } from '@/store/chat/clarificationState';
import type { Message } from '@/store/chat/types';

describe('findActivePendingClarification', () => {
  it('returns the latest unanswered assistant clarification', () => {
    const messages: Message[] = [
      {
        messageId: 'u1',
        chatId: 'c1',
        role: 'user',
        content: 'hello',
        createdAt: new Date(),
      },
      {
        messageId: 'a1',
        chatId: 'c1',
        role: 'assistant',
        content: 'Which one?',
        createdAt: new Date(),
        clarification: {
          answered: false,
          form: {
            questions: [{ id: 'q1', prompt: 'Which one?' }],
          },
        },
      },
    ];

    expect(findActivePendingClarification(messages)?.messageId).toBe('a1');
  });

  it('returns null when the latest assistant clarification is answered', () => {
    const messages: Message[] = [
      {
        messageId: 'a1',
        chatId: 'c1',
        role: 'assistant',
        content: 'done',
        createdAt: new Date(),
        clarification: {
          answered: true,
        },
      },
    ];

    expect(findActivePendingClarification(messages)).toBeNull();
  });

  it('skips newer assistants without clarification and finds an earlier pending one', () => {
    const messages: Message[] = [
      {
        messageId: 'a1',
        chatId: 'c1',
        role: 'assistant',
        content: 'Which one?',
        createdAt: new Date('2025-06-01T10:00:00Z'),
        clarification: {
          answered: false,
          form: {
            questions: [{ id: 'q1', prompt: 'Which one?' }],
          },
        },
      },
      {
        messageId: 'a2',
        chatId: 'c1',
        role: 'assistant',
        content: 'Regenerated draft',
        createdAt: new Date('2025-06-01T10:01:00Z'),
      },
    ];

    expect(findActivePendingClarification(messages)?.messageId).toBe('a1');
  });

  describe('once the user has moved on', () => {
    const card: Message = {
      messageId: 'a1',
      chatId: 'c1',
      role: 'assistant',
      content: 'Which one?',
      createdAt: new Date('2025-06-01T10:00:00Z'),
      clarification: { answered: false, form: { questions: [{ id: 'q1', prompt: 'Which one?' }] } },
    };
    const userTurn = (messageId: string): Message => ({
      messageId,
      chatId: 'c1',
      role: 'user',
      content: 'never mind, do something else',
      createdAt: new Date('2025-06-01T10:05:00Z'),
    });

    it('ignores a card the user answered with a new message and the agent replied to', () => {
      const reply: Message = {
        messageId: 'a2',
        chatId: 'c1',
        role: 'assistant',
        content: 'Sure.',
        createdAt: new Date(),
      };

      expect(findActivePendingClarification([card, userTurn('u2'), reply])).toBeNull();
    });

    it('ignores a card as soon as the new user message is in the list, before any reply', () => {
      expect(findActivePendingClarification([card, userTurn('u2')])).toBeNull();
    });

    it('keeps a card that only background messages follow', () => {
      const notice: Message = {
        messageId: 'n1',
        chatId: 'c1',
        role: 'custom_message',
        content: 'A background task finished',
        createdAt: new Date(),
      };

      expect(findActivePendingClarification([userTurn('u1'), card, notice])?.messageId).toBe('a1');
    });

    it('keeps the card of the current turn, whose user message comes before it', () => {
      expect(findActivePendingClarification([userTurn('u1'), card])?.messageId).toBe('a1');
    });
  });
});

describe('normalizeHydratedClarification', () => {
  it('defaults answered=false and keeps the form', () => {
    const normalized = normalizeHydratedClarification({
      answered: undefined as unknown as false,
      form: { questions: [{ id: 'q1', prompt: 'Pick' }] },
    });

    expect(normalized.answered).toBe(false);
    expect(normalized.form?.questions[0]?.prompt).toBe('Pick');
  });
});
