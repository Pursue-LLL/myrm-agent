/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExportData } from '../chatExport';

const DATA: ExportData = {
  chat: { id: 'chat-engine', title: 'Engine', source: 'myrm', createdAt: '2026-10-01T10:00:00Z' },
  messages: [{ role: 'assistant', content: 'plain text', createdAt: '2026-10-01T10:02:00Z', metadata: {} }],
};
const STATIC = { static: true };

/** Counts the markdown engines `chatExportHtml` builds: each one starts from a `unified()` call. */
function countUnifiedCalls(failOnCall?: number): { calls: () => number } {
  let calls = 0;
  vi.doMock('unified', async (importOriginal) => {
    const actual = await importOriginal<typeof import('unified')>();
    return {
      ...actual,
      unified: () => {
        calls += 1;
        if (calls === failOnCall) {
          throw new Error('chunk failed to load');
        }
        return actual.unified();
      },
    };
  });
  return { calls: () => calls };
}

describe('markdown engine of the HTML export', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.doUnmock('unified');
  });

  it('is built once for each mode and shared by every export in that mode', async () => {
    const { calls } = countUnifiedCalls();
    const { buildHtmlDocument } = await import('../chatExportHtml');

    await buildHtmlDocument(DATA);
    await buildHtmlDocument(DATA);
    await buildHtmlDocument(DATA, 'light', 'en', STATIC);
    await buildHtmlDocument(DATA, 'light', 'en', STATIC);

    expect(calls()).toBe(2);
  });

  it('is built again after a failed build, and a failure leaves the other mode alone', async () => {
    const { calls } = countUnifiedCalls(2);
    const { buildHtmlDocument } = await import('../chatExportHtml');

    await buildHtmlDocument(DATA);
    await expect(buildHtmlDocument(DATA, 'light', 'en', STATIC)).rejects.toThrow('chunk failed to load');
    await buildHtmlDocument(DATA);
    expect(calls()).toBe(2);

    await expect(buildHtmlDocument(DATA, 'light', 'en', STATIC)).resolves.toContain('plain text');
    expect(calls()).toBe(3);
  });
});
