/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
import { buildHtmlDocument } from '../chatExportHtml';
import type { ExportData, ExportMessage } from '../chatExport';

const SCRIPT_SCHEMES = new Set(['javascript:', 'vbscript:', 'data:']);

function exportOf(messages: ExportMessage[]): ExportData {
  return {
    chat: { id: 'chat-hostile', title: 'Hostile', source: 'myrm', createdAt: '2026-10-01T10:00:00Z' },
    messages,
    redacted: false,
  };
}

function assistant(content: string, sources?: Array<{ title?: string; url?: string }>): ExportMessage {
  return { role: 'assistant', content, createdAt: '2026-10-01T10:02:00Z', metadata: sources ? { sources } : {} };
}

async function renderedDocument(messages: ExportMessage[]): Promise<Document> {
  const html = await buildHtmlDocument(exportOf(messages), 'light', 'en');
  return new DOMParser().parseFromString(html, 'text/html');
}

/** What the browser will do with each link, resolved the way it resolves it. */
function linkProtocols(doc: Document): string[] {
  return [...doc.querySelectorAll('a[href]')].map(
    (a) => new URL(a.getAttribute('href') ?? '', 'https://x.test/').protocol,
  );
}

describe('exported HTML never carries a link that runs script', () => {
  it.each([
    ['inline', '[click](javascript:alert(1))'],
    ['mixed case', '[click](JaVaScRiPt:alert(1))'],
    ['entity-encoded scheme', '[click](&#106;avascript:alert(1))'],
    ['angle-bracket destination', '[click](<javascript:alert(1)>)'],
    ['reference definition', '[click][x]\n\n[x]: javascript:alert(1)'],
    ['autolink', '<javascript:alert(1)>'],
    ['vbscript', '[click](vbscript:msgbox(1))'],
    ['data document', '[click](data:text/html,<script>alert(1)</script>)'],
  ])('%s', async (_name, markdown) => {
    const doc = await renderedDocument([assistant(markdown)]);

    for (const protocol of linkProtocols(doc)) {
      expect(SCRIPT_SCHEMES.has(protocol), protocol).toBe(false);
    }
    expect(doc.querySelector('.msg-body a[href]')).toBeNull();
  });

  it('leaves a tab inside the scheme as an encoded relative path, which the browser does not run', async () => {
    const doc = await renderedDocument([assistant('[click](java&#9;script:alert(1))')]);

    expect([...doc.querySelectorAll('.msg-body a[href]')].map((a) => a.getAttribute('href'))).toEqual([
      'java%09script:alert(1)',
    ]);
    for (const protocol of linkProtocols(doc)) {
      expect(SCRIPT_SCHEMES.has(protocol), protocol).toBe(false);
    }
  });

  it('keeps the text of a refused link', async () => {
    const doc = await renderedDocument([assistant('see [the docs](javascript:alert(1)) now')]);

    expect(doc.querySelector('.msg-body')?.textContent).toContain('see the docs now');
  });

  it('keeps ordinary links as links', async () => {
    const doc = await renderedDocument([
      assistant('[a](https://example.com/a) [b](mailto:x@example.com) [c](#top) [d](/rel) https://auto.example.com/z'),
    ]);

    const hrefs = [...doc.querySelectorAll('.msg-body a[href]')].map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual([
      'https://example.com/a',
      'mailto:x@example.com',
      '#top',
      '/rel',
      'https://auto.example.com/z',
    ]);
  });

  it('refuses a script URL in a message from the user as well', async () => {
    const doc = await renderedDocument([
      { role: 'user', content: '[x](javascript:alert(1))', createdAt: '2026-10-01T10:01:00Z', metadata: {} },
    ]);

    expect(doc.querySelector('a[href]')).toBeNull();
  });

  it('does not turn a search-result URL into a script link in the sources list', async () => {
    const doc = await renderedDocument([
      assistant('answer', [
        { title: 'Bad result', url: 'javascript:alert(document.domain)' },
        { title: 'Good result', url: 'https://example.com/good' },
      ]),
    ]);

    const anchors = [...doc.querySelectorAll('.sources a')];
    expect(anchors.map((a) => a.getAttribute('href'))).toEqual(['https://example.com/good']);
    expect(anchors[0]?.getAttribute('rel')).toBe('noopener');
    expect(doc.querySelector('.sources')?.textContent).toContain('Bad result');
  });

  it('shows a refused source URL as plain text when it has no title', async () => {
    const doc = await renderedDocument([assistant('answer', [{ url: 'javascript:alert(1)' }])]);

    expect(doc.querySelector('.sources a')).toBeNull();
    expect(doc.querySelector('.sources')?.textContent).toContain('javascript:alert(1)');
  });
});
