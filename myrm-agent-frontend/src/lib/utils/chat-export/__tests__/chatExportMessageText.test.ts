import { describe, expect, it } from 'vitest';
import type { Message } from '@/store/chat/types';
import { formatMessageMarkdown, formatReasoning } from '../chatExportMessageText';

const OPENAI_KEY = 'sk-live1234567890abcdef1234567890';

const messageOf = (overrides: Partial<Message>): Message =>
  ({
    messageId: 'm',
    chatId: 'c',
    createdAt: new Date(0),
    role: 'assistant',
    content: 'Answer.',
    ...overrides,
  }) as Message;

describe('formatReasoning', () => {
  it('folds the reasoning into a block the reader can open', () => {
    expect(formatReasoning('Because.', 'fold')).toEqual([
      '<details>',
      '<summary>Thinking</summary>',
      '',
      'Because.',
      '',
      '</details>',
      '',
    ]);
  });

  it('sets the reasoning apart as a labelled quote, with every one of its lines inside the quote', () => {
    expect(formatReasoning('One.\n\n- a\n- b', 'quote')).toEqual([
      '> **Thinking**',
      '>',
      '> One.',
      '>',
      '> - a',
      '> - b',
      '',
    ]);
  });
});

describe('formatMessageMarkdown', () => {
  const message = messageOf({ reasoning: 'Because.' });

  it('folds the reasoning in front of the answer unless told otherwise', () => {
    expect(formatMessageMarkdown(message, true)).toBe(
      '<details>\n<summary>Thinking</summary>\n\nBecause.\n\n</details>\n\nAnswer.',
    );
  });

  it('quotes the reasoning in front of the answer when asked to', () => {
    expect(formatMessageMarkdown(message, true, true, 'quote')).toBe('> **Thinking**\n>\n> Because.\n\nAnswer.');
  });

  it.each(['fold', 'quote'] as const)('leaves the reasoning out when it is not included (%s)', (layout) => {
    expect(formatMessageMarkdown(message, false, true, layout)).toBe('Answer.');
  });

  it.each(['fold', 'quote'] as const)('redacts a secret in the reasoning before laying it out (%s)', (layout) => {
    const withSecret = messageOf({ reasoning: `Key ${OPENAI_KEY}.` });

    expect(formatMessageMarkdown(withSecret, true, true, layout)).not.toContain('sk-live');
    expect(formatMessageMarkdown(withSecret, true, false, layout)).toContain(OPENAI_KEY);
  });
});
