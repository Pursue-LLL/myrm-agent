/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getKatexExportStyle = vi.hoisted(() => vi.fn(async () => '.katex-export-style-sentinel{}'));
vi.mock('../katexExportStyle', () => ({ getKatexExportStyle }));

import { buildHtmlDocument, type HtmlDocumentOptions } from '../chatExportHtml';

const CONTENT = [
  'Inline $a+b$ and \\(c+d\\), then',
  '',
  '$$',
  'e^{i\\pi}=-1',
  '$$',
  '',
  '```bash',
  'echo "$HOME"',
  '```',
].join('\n');

interface Export {
  html: string;
  doc: Document;
}

async function exportOf(options?: HtmlDocumentOptions): Promise<Export> {
  const html = await buildHtmlDocument(
    {
      chat: { id: 'chat-static', title: 'Static', source: 'myrm', createdAt: '2026-10-01T10:00:00Z' },
      messages: [
        {
          role: 'assistant',
          content: CONTENT,
          createdAt: '2026-10-01T10:02:00Z',
          metadata: { reasoning_content: 'Thinking it over.' },
        },
      ],
      redacted: false,
    },
    'light',
    'en',
    options,
  );
  return { html, doc: new DOMParser().parseFromString(html, 'text/html') };
}

describe('static HTML export', () => {
  beforeEach(() => {
    getKatexExportStyle.mockClear();
  });

  it('is interactive by default, which the static checks below depend on', async () => {
    const { html, doc } = await exportOf();

    expect(html).toContain('<script>');
    expect(doc.querySelector('#theme-toggle')).not.toBeNull();
    expect(doc.querySelector('.copy-code-btn')).not.toBeNull();
    expect(doc.querySelectorAll('.katex').length).toBeGreaterThan(0);
  });

  it('has no script, theme button or copy button, and none of their text', async () => {
    const { html, doc } = await exportOf({ static: true });

    expect(html).not.toContain('<script');
    expect(doc.querySelector('#theme-toggle, .theme-toggle')).toBeNull();
    expect(doc.querySelector('.copy-code-btn')).toBeNull();
    expect(doc.body.textContent).not.toMatch(/Dark|Copy/);
  });

  it('writes each formula once, as its TeX source', async () => {
    const { doc } = await exportOf({ static: true });
    const text = doc.body.textContent ?? '';

    expect(doc.querySelectorAll('.katex, math, annotation')).toHaveLength(0);
    for (const source of ['$a+b$', '$c+d$', '$$e^{i\\pi}=-1$$']) {
      expect(text.split(source)).toHaveLength(2);
    }
    expect(text.split('a+b')).toHaveLength(2);
  });

  it('does not fetch the KaTeX style', async () => {
    const { doc } = await exportOf({ static: true });

    expect(getKatexExportStyle).not.toHaveBeenCalled();
    expect(doc.querySelector('head style')?.textContent).not.toContain('.katex-export-style-sentinel{}');
  });

  it('keeps the code block, its language and the rest of the document', async () => {
    const { doc } = await exportOf({ static: true });

    expect(doc.querySelector('.code-block pre code')?.textContent).toBe('echo "$HOME"\n');
    expect(doc.querySelector('.code-lang')?.textContent).toBe('bash');
    expect(doc.querySelector('.msg-body')).not.toBeNull();
    expect(doc.querySelector('.thinking-block')).not.toBeNull();
  });

  it('still applies the format options', async () => {
    const { doc } = await exportOf({ static: true, includeReasoning: false });

    expect(doc.querySelector('.thinking-block')).toBeNull();
  });
});
