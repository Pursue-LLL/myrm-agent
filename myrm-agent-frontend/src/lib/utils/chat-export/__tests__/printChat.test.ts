/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import type { ExportData } from '../chatExport';

const buildHtmlDocument = vi.hoisted(() => vi.fn(async () => '<html><body>built</body></html>'));
const printHtmlDocument = vi.hoisted(() => vi.fn(async () => undefined));
vi.mock('../chatExportHtml', () => ({ buildHtmlDocument }));
vi.mock('../printHtmlDocument', () => ({ printHtmlDocument }));

import { printChat } from '../chatExport';

const DATA: ExportData = {
  chat: { id: 'chat-print', title: 'Print', source: 'myrm', createdAt: '2026-10-01T10:00:00Z' },
  messages: [],
  redacted: false,
};

describe('printChat', () => {
  it('prints the document built for the chosen theme and language', async () => {
    await printChat(DATA, 'dark', 'zh');

    expect(buildHtmlDocument).toHaveBeenCalledWith(DATA, 'dark', 'zh');
    expect(printHtmlDocument).toHaveBeenCalledWith('<html><body>built</body></html>');
  });
});
