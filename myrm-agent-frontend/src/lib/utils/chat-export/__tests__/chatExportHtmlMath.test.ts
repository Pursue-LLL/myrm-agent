/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
import { buildHtmlDocument } from '../chatExportHtml';

/** The exported body of one assistant message, parsed the way a browser parses the file. */
async function exportedMessage(content: string): Promise<HTMLElement> {
  const html = await buildHtmlDocument(
    {
      chat: { id: 'chat-math', title: 'Math', source: 'myrm', createdAt: '2026-10-01T10:00:00Z' },
      messages: [{ role: 'assistant', content, createdAt: '2026-10-01T10:02:00Z', metadata: {} }],
      redacted: false,
    },
    'light',
    'en',
  );
  const body = new DOMParser().parseFromString(html, 'text/html').querySelector<HTMLElement>('.msg-body');
  if (!body) {
    throw new Error('the exported message has no body');
  }
  return body;
}

describe('exported HTML math', () => {
  it('keeps a price sentence as text instead of rendering one formula out of it', async () => {
    const body = await exportedMessage('The plan costs $5 per month and $10 per seat.');

    expect(body.querySelectorAll('.katex')).toHaveLength(0);
    expect(body.textContent).toContain('The plan costs $5 per month and $10 per seat.');
  });

  it('renders formulas in any notation', async () => {
    const body = await exportedMessage('Inline $a+b$, then \\(c+d\\), then\n\n$$\ne^{i\\pi}=-1\n$$');

    expect(body.querySelectorAll('.katex')).toHaveLength(3);
    expect(body.querySelectorAll('.katex-error')).toHaveLength(0);
  });

  it('keeps the dollar signs and percent signs inside code as written', async () => {
    const body = await exportedMessage(
      'Price $5.\n\n```bash\ntrap "rm -f /tmp/lock.$$" EXIT\necho 100%\n```\n\nThen $10.',
    );

    expect(body.querySelectorAll('.katex')).toHaveLength(0);
    expect(body.querySelector('pre code')?.textContent).toBe('trap "rm -f /tmp/lock.$$" EXIT\necho 100%\n');
  });

  it('does not turn commands that link or load a resource into links or images', async () => {
    const body = await exportedMessage(
      '$\\href{https://example.com}{x}$ $\\includegraphics{https://example.com/a.png}$',
    );

    expect(body.querySelectorAll('.katex')).toHaveLength(2);
    expect(body.querySelectorAll('a, img')).toHaveLength(0);
  });
});
