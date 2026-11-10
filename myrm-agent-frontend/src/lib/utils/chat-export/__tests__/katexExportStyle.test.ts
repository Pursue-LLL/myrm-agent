/** @vitest-environment jsdom */
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';

/** The stylesheet and fonts that ship with the installed KaTeX, which is what the app's CSS import brings onto a page. */
const katexDist = join(dirname(createRequire(import.meta.url).resolve('katex/package.json')), 'dist');
const katexCss = readFileSync(join(katexDist, 'katex.min.css'), 'utf8');
const fontBytes = (file: string): Buffer => readFileSync(join(katexDist, 'fonts', file));

const FONT_COUNT = 20;

function addStylesheet(css: string): CSSStyleSheet {
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);
  return style.sheet as CSSStyleSheet;
}

/** Serves the KaTeX fonts by file name (any other file gets its own name as content); `failing` maps a file name to how its request fails. */
function stubFonts(failing: Record<string, 'network' | 'status'> = {}): Mock<(input: URL) => Promise<Response>> {
  const fetchStub = vi.fn(async (input: URL) => {
    const file = input.pathname.split('/').pop() ?? '';
    if (failing[file] === 'network') {
      throw new TypeError('Failed to fetch');
    }
    if (failing[file] === 'status') {
      return new Response('missing', { status: 404 });
    }
    return new Response(new Uint8Array(file.startsWith('KaTeX_') ? fontBytes(file) : Buffer.from(file)));
  });
  vi.stubGlobal('fetch', fetchStub);
  return fetchStub;
}

async function loadModule(): Promise<typeof import('../katexExportStyle')> {
  vi.resetModules();
  return import('../katexExportStyle');
}

const faceCount = (css: string): number => css.split('@font-face').length - 1;

describe('getKatexExportStyle', () => {
  beforeEach(() => {
    document.head.innerHTML = '';
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('keeps the KaTeX rules and embeds every font of the stylesheet, and nothing else on the page', async () => {
    addStylesheet(
      `${katexCss}.app-only-rule{color:red}@font-face{font-family:AppFont;src:url(app.woff2) format("woff2")}`,
    );
    const fetchStub = stubFonts();
    const { getKatexExportStyle } = await loadModule();

    const css = await getKatexExportStyle();

    expect(faceCount(css)).toBe(FONT_COUNT);
    expect(fetchStub).toHaveBeenCalledTimes(FONT_COUNT);
    expect(css).not.toContain('url(fonts/');
    expect(css).toContain('font-display:block');
    expect(css).toContain(`base64,${fontBytes('KaTeX_Main-Regular.woff2').toString('base64')}`);
    // The rule that hides the MathML half of every formula is the reason an export needs the stylesheet at all.
    expect(css).toContain('.katex .katex-mathml');
    expect(css).toContain('.katex-display');
    expect(css).not.toContain('app-only-rule');
    expect(css).not.toContain('AppFont');
  });

  it('embeds the woff2 source of a font face wherever it is listed, and resolves it against its stylesheet', async () => {
    const sheet = addStylesheet(
      '@font-face{font-family:KaTeX_Main;src:url(a.woff) format("woff"),url("b.woff2") format("woff2")}.katex{color:inherit}',
    );
    Object.defineProperty(sheet, 'href', { value: 'https://app.example/_next/static/css/app.css' });
    const fetchStub = stubFonts();
    const { getKatexExportStyle } = await loadModule();

    const css = await getKatexExportStyle();

    expect(fetchStub).toHaveBeenCalledTimes(1);
    expect(fetchStub.mock.calls[0][0].href).toBe('https://app.example/_next/static/css/b.woff2');
    expect(css).toContain(`base64,${Buffer.from('b.woff2').toString('base64')}`);
  });

  it('leaves out a font face that names no woff2 source', async () => {
    addStylesheet('@font-face{font-family:KaTeX_Main;src:url(a.ttf) format("truetype")}.katex{color:inherit}');
    const fetchStub = stubFonts();
    const { getKatexExportStyle } = await loadModule();

    const css = await getKatexExportStyle();

    expect(faceCount(css)).toBe(0);
    expect(fetchStub).not.toHaveBeenCalled();
    expect(css).toMatch(/\.katex\s*\{/);
  });

  it('encodes a font larger than one conversion chunk byte for byte', async () => {
    addStylesheet('@font-face{font-family:KaTeX_Big;src:url(big.woff2) format("woff2")}.katex{color:inherit}');
    const big = Uint8Array.from({ length: 100_003 }, (_, i) => (i * 31 + 7) % 256);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(big)),
    );
    const { getKatexExportStyle } = await loadModule();

    const css = await getKatexExportStyle();

    expect(css).toContain(`url(data:font/woff2;base64,${Buffer.from(big).toString('base64')}) format("woff2")`);
  });

  it('leaves out a font that cannot be fetched and keeps the rest', async () => {
    addStylesheet(katexCss);
    stubFonts({ 'KaTeX_Main-Regular.woff2': 'network', 'KaTeX_Size1-Regular.woff2': 'status' });
    const { getKatexExportStyle } = await loadModule();

    const css = await getKatexExportStyle();

    const faces = css.match(/@font-face\{[^}]*\}/g) ?? [];
    expect(faces).toHaveLength(FONT_COUNT - 2);
    expect(faces.some((face) => face.includes('font-family:KaTeX_Size1;'))).toBe(false);
    expect(
      faces.some(
        (face) =>
          face.includes('font-family:KaTeX_Main;') &&
          face.includes('font-weight:400') &&
          face.includes('font-style:normal'),
      ),
    ).toBe(false);
    expect(css).toContain('.katex .katex-mathml');
    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining('18 of 20 fonts'));
  });

  it('keeps only a complete result for the next export', async () => {
    addStylesheet(katexCss);
    stubFonts({ 'KaTeX_Main-Regular.woff2': 'network' });
    const { getKatexExportStyle } = await loadModule();
    expect(faceCount(await getKatexExportStyle())).toBe(FONT_COUNT - 1);

    const retryFetch = stubFonts();
    expect(faceCount(await getKatexExportStyle())).toBe(FONT_COUNT);
    expect(retryFetch).toHaveBeenCalledTimes(FONT_COUNT);

    await getKatexExportStyle();
    expect(retryFetch).toHaveBeenCalledTimes(FONT_COUNT);
  });

  it('fetches the fonts once for exports that run at the same time', async () => {
    addStylesheet(katexCss);
    const fetchStub = stubFonts();
    const { getKatexExportStyle } = await loadModule();

    const results = await Promise.all([getKatexExportStyle(), getKatexExportStyle(), getKatexExportStyle()]);

    expect(new Set(results).size).toBe(1);
    expect(fetchStub).toHaveBeenCalledTimes(FONT_COUNT);
  });

  it('returns an empty string without fetching when the page has no KaTeX stylesheet, and looks again next time', async () => {
    addStylesheet('.app-only-rule{color:red}');
    const fetchStub = stubFonts();
    const { getKatexExportStyle } = await loadModule();

    expect(await getKatexExportStyle()).toBe('');
    expect(fetchStub).not.toHaveBeenCalled();

    addStylesheet(katexCss);
    expect(faceCount(await getKatexExportStyle())).toBe(FONT_COUNT);
  });

  it('skips a stylesheet the page is not allowed to read', async () => {
    const blocked = addStylesheet('.katex{color:red}');
    Object.defineProperty(blocked, 'cssRules', {
      get() {
        throw new DOMException('Cannot access rules', 'SecurityError');
      },
    });
    addStylesheet(katexCss);
    stubFonts();
    const { getKatexExportStyle } = await loadModule();

    const css = await getKatexExportStyle();

    expect(faceCount(css)).toBe(FONT_COUNT);
    expect(css).not.toContain('color:red');
  });

  it('returns an empty string where there is no document', async () => {
    const fetchStub = stubFonts();
    vi.stubGlobal('document', undefined);
    const { getKatexExportStyle } = await loadModule();

    expect(await getKatexExportStyle()).toBe('');
    expect(fetchStub).not.toHaveBeenCalled();
  });
});
