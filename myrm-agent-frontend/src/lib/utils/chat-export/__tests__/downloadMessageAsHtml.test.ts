/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { expectNonNull } from '@/test-utils/expectDefined';
import type { Message, Source } from '@/store/chat/types';

const triggerDownload = vi.hoisted(() => vi.fn(async (_blob: Blob, _filename: string) => true));
vi.mock('@/lib/utils/fileUtils', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/fileUtils')>()),
  triggerDownload,
}));

import { downloadMessageAsHtml } from '../chatExport';
import type { MessageLabels } from '../chatExportMessageText';

const LABELS: MessageLabels = { reasoning: '思考过程', sources: '来源', untitledSource: '未命名' };

function messageOf(overrides: Partial<Message>): Message {
  return {
    messageId: 'msg-html',
    chatId: 'chat-html',
    createdAt: new Date('2026-10-01T10:00:00Z'),
    role: 'assistant',
    content: 'Answer.',
    ...overrides,
  } as Message;
}

/** The page the nth download handed over, read the way a browser reads it. */
async function pageOfDownload(n: number): Promise<Document> {
  const [blob] = triggerDownload.mock.calls[n];
  return new DOMParser().parseFromString(new TextDecoder().decode(await blob.arrayBuffer()), 'text/html');
}

/** The part of the nth page that holds the message itself. */
async function bodyOfDownload(n: number): Promise<Element> {
  const body = (await pageOfDownload(n)).querySelector('.msg-body');
  expectNonNull(body, 'message body');
  return body;
}

beforeEach(() => {
  triggerDownload.mockClear();
});

describe('downloadMessageAsHtml', () => {
  it('writes the page in the language and theme it is given', async () => {
    await downloadMessageAsHtml(messageOf({}), false, LABELS, 'dark', 'zh');

    const { documentElement } = await pageOfDownload(0);
    expect(documentElement.getAttribute('lang')).toBe('zh');
    expect(documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('sets the reasoning apart from the answer, in a quote under the caller label, only when asked to', async () => {
    const message = messageOf({
      content: 'The answer.',
      reasoning: 'First I weigh the options.\n\n- option a\n- option b',
    });

    await downloadMessageAsHtml(message, true, LABELS);
    await downloadMessageAsHtml(message, false, LABELS);

    const withReasoning = await bodyOfDownload(0);
    const without = await bodyOfDownload(1);
    const quote = withReasoning.querySelector('blockquote');
    expectNonNull(quote, 'reasoning quote');
    expect(quote.querySelector('p > strong')?.textContent).toBe('思考过程');
    expect(quote.textContent).toContain('First I weigh the options.');
    expect([...quote.querySelectorAll('li')].map((item) => item.textContent)).toEqual(['option a', 'option b']);
    expect(withReasoning.lastElementChild?.textContent).toBe('The answer.');
    expect(quote.contains(withReasoning.lastElementChild)).toBe(false);
    expect(without.querySelector('blockquote')).toBeNull();
    expect(without.textContent).not.toContain('First I weigh the options.');
  });

  it('lists each source on a line of its own under the caller label, as a link when it has an address', async () => {
    const sources: Source[] = [
      { index: 1, type: 'web_search', url: 'https://one.example/a', title: 'One' },
      { index: 2, type: 'web_search', title: 'Titled, with no address' },
      { index: 3, type: 'web_search' },
    ];

    await downloadMessageAsHtml(messageOf({ content: 'Claim.', sources }), false, LABELS);

    const list = (await bodyOfDownload(0)).lastElementChild;
    expectNonNull(list, 'sources paragraph');
    expect(list.textContent).toBe('来源:\n[1] https://one.example/a\n[2] Titled, with no address\n[3] 未命名');
    // A newline in the text collapses on screen; the four lines (label and three sources) stay apart on three breaks.
    expect(list.querySelectorAll('br')).toHaveLength(3);
    expect([...list.querySelectorAll('a')].map((link) => link.getAttribute('href'))).toEqual(['https://one.example/a']);
  });

  // A wiki file or a conversation is named by text its author chose, so a name is data that never runs as markup.
  it('keeps the name of a source that carries markup or a script link from running', async () => {
    const sources: Source[] = [
      { index: 1, type: 'conversation_history', title: '<img src=x onerror=alert(1)><script>alert(2)</script>' },
      { index: 2, type: 'knowledge', kb_name: 'Work', filename: '[open](javascript:alert(3))' },
    ];

    await downloadMessageAsHtml(messageOf({ content: 'Claim.', sources }), false, LABELS);

    const list = (await bodyOfDownload(0)).lastElementChild;
    expectNonNull(list, 'sources paragraph');
    expect(list.querySelector('img, script, [onerror]')).toBeNull();
    expect(list.querySelector('a[href]')).toBeNull();
  });
});
