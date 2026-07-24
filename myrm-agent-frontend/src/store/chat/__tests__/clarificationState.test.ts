import { describe, expect, it } from 'vitest';

import {
  findActivePendingClarification,
  normalizeHydratedClarification,
} from '@/store/chat/clarificationState';
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
          isResumeMode: true,
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
          isResumeMode: true,
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
          isResumeMode: true,
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
});

describe('normalizeHydratedClarification', () => {
  it('defaults answered=false and isResumeMode from source', () => {
    const normalized = normalizeHydratedClarification({
      answered: undefined as unknown as false,
      form: { questions: [{ id: 'q1', prompt: 'Pick' }] },
      source: 'deep_research',
    });

    expect(normalized.answered).toBe(false);
    expect(normalized.isResumeMode).toBe(false);
  });

  it('defaults isResumeMode=true for general clarify without source', () => {
    const normalized = normalizeHydratedClarification({
      answered: false,
      form: { questions: [{ id: 'q1', prompt: 'Pick' }] },
    });

    expect(normalized.isResumeMode).toBe(true);
  });
});
