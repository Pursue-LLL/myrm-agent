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

  // A source's address or name is as much the page's own text as the answer is, and a URL often carries a key.
  it('redacts a secret in a source address or name along with the text, and keeps it when redaction is off', () => {
    const sources: Source[] = [
      { index: 1, type: 'web_search', url: 'https://api.example.com/v1/data?api_key=abcd1234efgh5678&page=2' },
      { index: 2, type: 'web_search', title: `Notes on ${OPENAI_KEY}` },
    ];
    const withSources = messageOf({ sources });

    const redacted = formatMessageMarkdown(withSources, false, LABELS);
    expect(redacted).not.toContain('abcd1234efgh5678');
    expect(redacted).not.toContain('sk-live');
    expect(redacted).toContain('[1] https://api.example.com/v1/data?api_key=[REDACTED_SECRET]&page=2');
    expect(redacted).toContain('[2] Notes on ');

    const verbatim = formatMessageMarkdown(withSources, false, LABELS, false);
    expect(verbatim).toContain('abcd1234efgh5678');
    expect(verbatim).toContain(OPENAI_KEY);
  });

  // The answer links to a file the way an object store hands the link out, and the page the answer drew on does too.
  it('masks the signature of a presigned link in the answer and in a source, and keeps the link itself', () => {
    const link =
      'https://bucket.s3.amazonaws.com/report.pdf?X-Amz-Expires=3600&X-Amz-Signature=abcd1234efgh5678abcd1234efgh5678';
    const message = messageOf({
      content: `Download [the report](${link}) within the hour.`,
      sources: [{ index: 1, type: 'web_search', url: link }],
    });
    const masked = 'https://bucket.s3.amazonaws.com/report.pdf?X-Amz-Expires=3600&X-Amz-Signature=[REDACTED_SECRET]';

    const markdown = formatMessageMarkdown(message, false, LABELS);
    expect(markdown).toContain(`Download [the report](${masked}) within the hour.`);
    expect(markdown).toContain(`[1] ${masked}`);
    expect(markdown).not.toContain('abcd1234efgh5678');

    expect(formatMessageMarkdown(message, false, LABELS, false)).toContain(`[the report](${link})`);
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

  // Numbering runs on across the turns of a chat, so a later answer's own sources start above 1 and its text cites them
  // by those numbers.
  it('numbers a source by the citation number the answer uses, not by its place in the list', () => {
    const sources: Source[] = [
      { index: 4, type: 'web_search', url: 'https://four.example' },
      { index: 5, type: 'web_search', url: 'https://five.example' },
    ];

    expect(formatSourcesFootnotes(sources, LABELS)).toBe(
      '\n\n来源:  \n[4] https://four.example  \n[5] https://five.example',
    );
  });

  it('words a wiki section the way the caller does, and leaves it as it is when the caller gives no wording', () => {
    const sources: Source[] = [
      { index: 1, type: 'knowledge', kb_name: 'Work', filename: 'index', section: 'index_routing' },
    ];
    const labels: MessageLabels = {
      ...LABELS,
      sectionLabel: (section) => (section === 'index_routing' ? '目录索引' : section),
    };

    expect(formatSourcesFootnotes(sources, labels)).toBe('\n\n来源:  \n[1] index § 目录索引');
    expect(formatSourcesFootnotes(sources, LABELS)).toBe('\n\n来源:  \n[1] index § index_routing');
  });

  // The kinds the server emits: a web result has an address and a title, a wiki hit a knowledge base and a file, an MCP
  // call only its skill, and a recalled conversation maybe a title.
  it('names each kind of source by the field that carries its name, as the interface shows it', () => {
    const sources: Source[] = [
      { index: 1, type: 'web_search', url: 'https://docs.example.com/guide', title: 'Guide' },
      { index: 2, type: 'web_fetch', url: 'https://example.com/post' },
      { index: 3, type: 'knowledge', kb_name: 'Work', filename: 'deploy-notes', section: 'Rollback' },
      { index: 4, type: 'knowledge', kb_name: 'Work', filename: 'runbook' },
      { index: 5, type: 'knowledge', kb_name: 'Work', section: 'Intro' },
      { index: 6, type: 'mcp', skill_name: 'github' },
      { index: 7, type: 'conversation_history', title: 'Earlier planning chat' },
      { index: 8, type: 'conversation_history' },
    ];

    expect(formatSourcesFootnotes(sources, LABELS)).toBe(
      `\n\n来源:  \n${[
        '[1] https://docs.example.com/guide',
        '[2] https://example.com/post',
        '[3] deploy-notes § Rollback',
        '[4] runbook',
        '[5] Work',
        '[6] github',
        '[7] Earlier planning chat',
        '[8] 未命名',
      ].join('  \n')}`,
    );
  });
});
