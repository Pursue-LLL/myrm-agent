/** @vitest-environment jsdom */
import JSZip from 'jszip';
import { describe, expect, it, vi } from 'vitest';
import { buildHtmlDocument } from '../chatExportHtml';

// The Word file takes no stylesheet, and the KaTeX one is not loaded in jsdom anyway.
vi.mock('../katexExportStyle', () => ({ getKatexExportStyle: async () => '' }));

const CONTENT = [
  'Energy is $E = mc^2$ and \\(x_1 + x_2\\), but $5 and $10 are prices.',
  '',
  '$$',
  '\\int_0^1 x^2\\,dx = \\frac{1}{3}',
  '$$',
  '',
  '```bash',
  'echo "$HOME"',
  '```',
].join('\n');

function readBlob(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

/** What Word shows: the text runs of the file the real converter writes from the static export document. */
async function wordText(): Promise<string> {
  const html = await buildHtmlDocument(
    {
      chat: { id: 'chat-docx', title: 'Word', source: 'myrm', createdAt: '2026-10-01T10:00:00Z' },
      messages: [{ role: 'assistant', content: CONTENT, createdAt: '2026-10-01T10:02:00Z', metadata: {} }],
      redacted: false,
    },
    'light',
    'en',
    { static: true },
  );
  const { toDocx } = await import('docshift');
  const zip = await JSZip.loadAsync(await readBlob(await toDocx(html)));
  const body = zip.file('word/document.xml');
  if (!body) {
    throw new Error('The Word file has no word/document.xml');
  }
  const xml = await body.async('string');
  return [...xml.matchAll(/<w:t[^>]*>([^<]*)<\/w:t>/g)].map((run) => run[1]).join('\n');
}

describe('Word file written from the static export document', () => {
  it('has the page text and none of the page controls or script', async () => {
    const text = await wordText();

    expect(text).toContain('Energy is');
    expect(text).not.toMatch(/Dark|Light|Copy|function\s*\(|addEventListener/);
  });

  it('has each formula once, as TeX', async () => {
    const text = await wordText();

    for (const source of ['$E = mc^2$', '$x_1 + x_2$', '$$\\int_0^1 x^2\\,dx = \\frac{1}{3}$$']) {
      expect(text.split(source)).toHaveLength(2);
    }
    expect(text).toContain('$5 and $10');
    expect(text.split('mc^2')).toHaveLength(2);
  });
});
