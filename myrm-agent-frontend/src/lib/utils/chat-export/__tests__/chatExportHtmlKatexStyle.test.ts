/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getKatexExportStyle = vi.hoisted(() => vi.fn(async () => '.katex-export-style-sentinel{}'));
vi.mock('../katexExportStyle', () => ({ getKatexExportStyle }));

import { buildHtmlDocument } from '../chatExportHtml';

async function exportOf(...contents: string[]): Promise<Document> {
  const html = await buildHtmlDocument(
    {
      chat: { id: 'chat-style', title: 'Style', source: 'myrm', createdAt: '2026-10-01T10:00:00Z' },
      messages: contents.map((content, i) => ({
        role: 'assistant',
        content,
        createdAt: `2026-10-01T10:0${i}:00Z`,
        metadata: {},
      })),
      redacted: false,
    },
    'light',
    'en',
  );
  return new DOMParser().parseFromString(html, 'text/html');
}

describe('exported HTML carries the KaTeX style only for formulas', () => {
  beforeEach(() => {
    getKatexExportStyle.mockClear();
  });

  it('puts the KaTeX stylesheet into the document when a message has a formula', async () => {
    const doc = await exportOf('Plain text.', 'Energy is $E = mc^2$.');

    expect(doc.querySelector('head style')?.textContent).toContain('.katex-export-style-sentinel{}');
    expect(getKatexExportStyle).toHaveBeenCalledTimes(1);
  });

  it('counts a formula written as a display block or with \\( \\) as well', async () => {
    for (const content of ['$$\nx^2\n$$', 'so \\(x^2\\) holds']) {
      const doc = await exportOf(content);
      expect(doc.querySelector('head style')?.textContent).toContain('.katex-export-style-sentinel{}');
    }
  });

  it.each([
    ['prose without formulas', 'Nothing mathematical here.'],
    ['a price sentence', 'The plan costs $5 per month and $10 per seat.'],
    ['formula-like text in code', 'Run `echo $HOME and $PATH` or\n\n```tex\n$x^2$ and $$y$$\n```'],
    ['the markup of a formula quoted in code', 'KaTeX wraps each formula in `<span class="katex">`.'],
  ])('leaves the style out of an export with %s', async (_label, content) => {
    const doc = await exportOf(content);

    expect(doc.querySelector('head style')?.textContent).not.toContain('.katex-export-style-sentinel{}');
    expect(getKatexExportStyle).not.toHaveBeenCalled();
  });
});

describe('exported HTML keeps formula scripts at their typeset size', () => {
  // Chrome raises em-relative sizes below its minimum logical font size when the chain is rooted in the
  // browser default; a px root would ignore the reader's default font size, so only rem fits.
  it('declares the body font size in rem', async () => {
    const doc = await exportOf('Energy is $E = mc^2$.');
    const bodyRule = /(?:^|\n)body\{([^}]*)\}/.exec(doc.querySelector('head style')?.textContent ?? '')?.[1];

    expect(bodyRule).toMatch(/(?:^|;)font-size:1rem(?:;|$)/);
  });
});
