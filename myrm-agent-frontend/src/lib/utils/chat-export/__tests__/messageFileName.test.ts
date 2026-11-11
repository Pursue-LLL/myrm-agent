/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '@/store/chat/types';

const triggerDownload = vi.hoisted(() => vi.fn(async (_blob: Blob, _filename: string) => true));
vi.mock('@/lib/utils/fileUtils', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/fileUtils')>()),
  triggerDownload,
}));
// The subject here is the name of the file, so each format's document builder is a stub.
vi.mock('../chatExportHtml', () => ({ buildHtmlDocument: vi.fn(async () => '<html></html>') }));
vi.mock('../chatExportDocx', () => ({ buildDocxBlob: vi.fn(async () => new Blob(['docx'])) }));
vi.mock('html2canvas', () => ({
  default: vi.fn(async () => ({ toBlob: (done: (blob: Blob | null) => void) => done(new Blob(['png'])) })),
}));

import {
  downloadMessageAsDocx,
  downloadMessageAsHtml,
  downloadMessageAsImage,
  downloadMessageAsMarkdown,
} from '../chatExport';
import type { MessageLabels } from '../chatExportMessageText';

const OPENAI_KEY = 'sk-live1234567890abcdef1234567890';
const SUFFIX = /-\d{4}-\d{2}-\d{2}\.[a-z]+$/;
const LABELS: MessageLabels = { reasoning: 'Reasoning', sources: 'Sources', untitledSource: 'Untitled' };

type Exporter = (message: Message, redact: boolean) => Promise<void> | void;
const FORMATS: Record<string, { extension: string; run: Exporter }> = {
  Markdown: { extension: 'md', run: (m, redact) => downloadMessageAsMarkdown(m, false, LABELS, redact) },
  HTML: { extension: 'html', run: (m, redact) => downloadMessageAsHtml(m, false, LABELS, 'light', 'en', redact) },
  Word: { extension: 'docx', run: (m, redact) => downloadMessageAsDocx(m, false, LABELS, redact) },
  Image: { extension: 'png', run: (m, redact) => downloadMessageAsImage(document.createElement('div'), m, redact) },
};

function messageOf(content: string): Message {
  return {
    messageId: 'msg-name',
    chatId: 'chat-name',
    createdAt: new Date('2026-10-01T10:00:00Z'),
    role: 'assistant',
    content,
  } as Message;
}

/** The name of the file the user is offered, without its date and extension. */
async function titleOf(format: string, content: string, redact = true): Promise<string> {
  triggerDownload.mockClear();
  await FORMATS[format].run(messageOf(content), redact);
  const filename = triggerDownload.mock.calls[0][1];
  expect(filename.endsWith(`.${FORMATS[format].extension}`)).toBe(true);
  return filename.replace(SUFFIX, '');
}

describe.each(Object.keys(FORMATS))('the file name of a single message exported as %s', (format) => {
  beforeEach(() => {
    triggerDownload.mockClear();
  });

  it('does not give a redacted secret away', async () => {
    expect(await titleOf(format, `Use ${OPENAI_KEY} for auth\nBody`)).toBe('Use [REDACTED_API_KEY] for auth');
  });

  it('keeps the first line as written when the export is not redacted', async () => {
    expect(await titleOf(format, `Use ${OPENAI_KEY} for auth\nBody`, false)).toBe(`Use ${OPENAI_KEY} for auth`);
  });

  it('redacts a secret that crosses the cut before it cuts', async () => {
    const title = await titleOf(format, `${'x'.repeat(70)} ${OPENAI_KEY}`);

    expect(title).not.toContain('sk-live');
    expect(title).toHaveLength(80);
  });

  it.each([
    ['# Quarterly plan', 'Quarterly plan'],
    ['### Deep heading', 'Deep heading'],
    ['> Quoted', 'Quoted'],
    ['> ## Quoted heading', 'Quoted heading'],
    ['- Item', 'Item'],
    ['* Item', 'Item'],
    ['12. Step', 'Step'],
    ['3) Step', 'Step'],
  ])('leaves the Markdown marker of %s out of the name', async (line, title) => {
    expect(await titleOf(format, `${line}\nBody`)).toBe(title);
  });

  it.each(['#', '-', '1.', '>', '> #'])(
    'falls back to a plain name when the first line is nothing but the marker %j',
    async (line) => {
      expect(await titleOf(format, `${line}\nBody`)).toBe('message');
    },
  );

  it('cuts the name by character, so an emoji at the cut is kept whole', async () => {
    expect(await titleOf(format, `${'a'.repeat(79)}😀${'b'.repeat(10)}`)).toBe(`${'a'.repeat(79)}😀`);
  });

  it('keeps what is not a marker: a hashtag and a number that is not a list item', async () => {
    expect(await titleOf(format, '#hashtag first')).toBe('#hashtag first');
    expect(await titleOf(format, '2026 plan')).toBe('2026 plan');
  });

  it('falls back to a plain name for an empty first line, and drops the carriage return of a Windows line end', async () => {
    expect(await titleOf(format, '\nBody')).toBe('message');
    expect(await titleOf(format, 'Title\r\nBody')).toBe('Title');
  });
});
