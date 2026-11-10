/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import type { Message } from '@/store/chat/types';

const buildHtmlDocument = vi.hoisted(() => vi.fn(async () => '<html><body>static document</body></html>'));
const toDocx = vi.hoisted(() => vi.fn(async () => new Blob(['docx'])));
const triggerDownload = vi.hoisted(() => vi.fn(async () => undefined));
vi.mock('../chatExportHtml', () => ({ buildHtmlDocument }));
vi.mock('docshift', () => ({ toDocx }));
vi.mock('@/lib/utils/fileUtils', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/fileUtils')>()),
  triggerDownload,
}));

import { downloadMessageAsDocx } from '../chatExport';

const MESSAGE = {
  messageId: 'msg-docx',
  chatId: 'chat-docx',
  createdAt: new Date('2026-10-01T10:00:00Z'),
  content: 'Energy is $E = mc^2$.',
  role: 'assistant',
} as Message;

describe('downloadMessageAsDocx', () => {
  it('converts the static variant of the export document and downloads the result', async () => {
    await downloadMessageAsDocx(MESSAGE, false);

    expect(buildHtmlDocument).toHaveBeenCalledWith(expect.anything(), 'light', 'en', { static: true });
    expect(toDocx).toHaveBeenCalledWith('<html><body>static document</body></html>');
    expect(triggerDownload).toHaveBeenCalledWith(expect.any(Blob), expect.stringMatching(/\.docx$/));
  });
});
