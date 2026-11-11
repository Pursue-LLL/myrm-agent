/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message, Source } from '@/store/chat/types';
import { elements, externalTargets, openDocx, paragraphTexts, type DocxPackage } from './docxTestKit';

const triggerDownload = vi.hoisted(() => vi.fn(async (_blob: Blob, _filename: string) => true));
vi.mock('@/lib/utils/fileUtils', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/fileUtils')>()),
  triggerDownload,
}));

import { downloadMessageAsDocx } from '../chatExport';
import type { MessageLabels } from '../chatExportMessageText';

const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const OPENAI_KEY = 'sk-live1234567890abcdef1234567890';
const LABELS: MessageLabels = { reasoning: '思考过程', sources: '来源', untitledSource: '未命名' };

function messageOf(overrides: Partial<Message>): Message {
  return {
    messageId: 'msg-docx',
    chatId: 'chat-docx',
    createdAt: new Date('2026-10-01T10:00:00Z'),
    role: 'assistant',
    content: 'Answer.',
    ...overrides,
  } as Message;
}

/** The file the user would have been handed. */
async function downloaded(): Promise<{ docx: DocxPackage; blob: Blob; filename: string; text: string }> {
  const [blob, filename] = triggerDownload.mock.calls[0];
  const docx = await openDocx(blob);
  return { docx, blob, filename, text: paragraphTexts(docx.document).join('\n') };
}

beforeEach(() => {
  triggerDownload.mockClear();
});

describe('downloadMessageAsDocx', () => {
  it('hands over a Word file named after the first line of the message', async () => {
    await downloadMessageAsDocx(messageOf({ content: 'Quarterly plan\n\nFirst we ship.' }), false, LABELS);

    const { blob, filename, text } = await downloaded();
    expect(blob.type).toBe(DOCX_MIME);
    expect(filename).toMatch(/^Quarterly plan.*\.docx$/);
    expect(text).toBe('Quarterly plan\nFirst we ship.');
  });

  it('writes a message with a table, a list and a formula as Word structure', async () => {
    await downloadMessageAsDocx(
      messageOf({ content: '## Results\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- one\n- two\n\nSolve $x^2 = 4$.' }),
      false,
      LABELS,
    );

    const { docx } = await downloaded();
    expect(elements(docx.document, 'w:tbl')).toHaveLength(1);
    expect(elements(docx.document, 'w:numPr')).toHaveLength(2);
    expect(elements(docx.document, 'm:oMath')).toHaveLength(1);
  });

  it('hides secrets by default and keeps them only when redaction is turned off', async () => {
    const message = messageOf({ content: `Use ${OPENAI_KEY} for auth.` });

    await downloadMessageAsDocx(message, false, LABELS);
    await downloadMessageAsDocx(message, false, LABELS, false);

    const redacted = paragraphTexts((await openDocx(triggerDownload.mock.calls[0][0])).document).join('\n');
    const raw = paragraphTexts((await openDocx(triggerDownload.mock.calls[1][0])).document).join('\n');
    expect(redacted).toContain('[REDACTED_API_KEY]');
    expect(redacted).not.toContain(OPENAI_KEY);
    expect(raw).toContain(OPENAI_KEY);
  });

  it('sets the reasoning apart from the answer, in a labelled indented block, only when asked to', async () => {
    const message = messageOf({
      content: 'The answer.',
      reasoning: 'First I weigh the options.\n\n- option a\n- option b',
    });

    await downloadMessageAsDocx(message, true, LABELS);
    await downloadMessageAsDocx(message, false, LABELS);

    const withReasoning = (await openDocx(triggerDownload.mock.calls[0][0])).document;
    const without = (await openDocx(triggerDownload.mock.calls[1][0])).document;
    const paragraphs = elements(withReasoning, 'w:p');
    const indentOf = (paragraph: Element): number =>
      Number(elements(paragraph, 'w:ind')[0]?.getAttribute('w:left') ?? 0);
    expect(paragraphTexts(withReasoning)).toEqual([
      '思考过程',
      'First I weigh the options.',
      'option a',
      'option b',
      'The answer.',
    ]);
    expect(elements(paragraphs[0], 'w:b')).toHaveLength(1);
    expect(paragraphs.slice(0, 4).every((paragraph) => indentOf(paragraph) > 0)).toBe(true);
    expect(indentOf(paragraphs[4])).toBe(0);
    expect(paragraphTexts(without)).toEqual(['The answer.']);
  });

  it('lists each source on a line of its own, as a link when it has an address', async () => {
    const sources: Source[] = [
      { index: 1, type: 'web_search', url: 'https://one.example/a', title: 'One' },
      { index: 2, type: 'web_search', url: 'https://two.example/b', title: 'Two' },
      { index: 3, type: 'web_search', title: 'Third, with no address' },
    ];

    await downloadMessageAsDocx(messageOf({ content: 'Claim.', sources }), false, LABELS);

    const { docx, text } = await downloaded();
    expect(text).toContain('来源:\n[1] https://one.example/a\n[2] https://two.example/b\n[3] Third, with no address');
    expect(externalTargets(docx.parts['word/_rels/document.xml.rels'])).toEqual([
      'https://one.example/a',
      'https://two.example/b',
    ]);
  });
});
