import { describe, expect, it } from 'vitest';
import type { Message, Source } from '@/store/chat/types';
import {
  formatMessageMarkdown,
  formatReasoning,
  formatSourcesFootnotes,
  type MessageLabels,
} from '../chatExportMessageText';

const OPENAI_KEY = 'sk-live1234567890abcdef1234567890';
const LABELS: MessageLabels = { reasoning: '思考过程', sources: '来源', untitledSource: '未命名' };

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
    expect(formatReasoning('Because.', 'fold', '思考过程')).toEqual([
      '<details>',
      '<summary>思考过程</summary>',
      '',
      'Because.',
      '',
      '</details>',
      '',
    ]);
  });

  it('sets the reasoning apart as a labelled quote, with every one of its lines inside the quote', () => {
    expect(formatReasoning('One.\n\n- a\n- b', 'quote', '思考过程')).toEqual([
      '> **思考过程**',
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
    expect(formatMessageMarkdown(message, true, LABELS)).toBe(
      '<details>\n<summary>思考过程</summary>\n\nBecause.\n\n</details>\n\nAnswer.',
    );
  });

  it('quotes the reasoning in front of the answer when asked to', () => {
    expect(formatMessageMarkdown(message, true, LABELS, true, 'quote')).toBe(
      '> **思考过程**\n>\n> Because.\n\nAnswer.',
    );
  });

  it.each(['fold', 'quote'] as const)('leaves the reasoning out when it is not included (%s)', (layout) => {
    expect(formatMessageMarkdown(message, false, LABELS, true, layout)).toBe('Answer.');
  });

  it.each(['fold', 'quote'] as const)('redacts a secret in the reasoning before laying it out (%s)', (layout) => {
    const withSecret = messageOf({ reasoning: `Key ${OPENAI_KEY}.` });

    expect(formatMessageMarkdown(withSecret, true, LABELS, true, layout)).not.toContain('sk-live');
    expect(formatMessageMarkdown(withSecret, true, LABELS, false, layout)).toContain(OPENAI_KEY);
  });

  it('lists the sources under the caller label, one to a line, naming each by address, else title, else the stand-in', () => {
    const sources: Source[] = [
      { index: 1, type: 'web_search', url: 'https://one.example/a', title: 'One' },
      { index: 2, type: 'web_search', title: 'Two, with no address' },
      { index: 3, type: 'web_search' },
    ];

    expect(formatMessageMarkdown(messageOf({ sources }), false, LABELS)).toContain(
      '来源:  \n[1] https://one.example/a  \n[2] Two, with no address  \n[3] 未命名',
    );
  });

  it.each([[undefined], [[]]])('adds no sources section to a message whose sources are %j', (sources) => {
    expect(formatMessageMarkdown(messageOf({ sources }), false, LABELS)).toBe('Answer.');
  });
});

describe('formatSourcesFootnotes', () => {
  it('leads with the blank line that sets the list off from the text before it', () => {
    const sources: Source[] = [{ index: 1, type: 'web_search', url: 'https://one.example/a' }];

    expect(formatSourcesFootnotes(sources, { sources: 'Sources', untitledSource: 'Untitled' })).toBe(
      '\n\nSources:  \n[1] https://one.example/a',
    );
  });

  it.each([[undefined], [[]]])('is empty when the sources are %j', (sources) => {
    expect(formatSourcesFootnotes(sources, LABELS)).toBe('');
  });
});
