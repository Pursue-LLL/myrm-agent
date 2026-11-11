/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildDocxBlob } from '../chatExportDocx';
import { BMP, GIF, JPEG, PNG, WEBP, bytesOf, htmlWith, imageResponse, stubFetch, type Reply } from './docxImageTestKit';
import { elements, externalTargets, openDocx, paragraphTexts, type DocxPackage } from './docxTestKit';

const docxOf = async (markdown: string): Promise<DocxPackage> => openDocx(await buildDocxBlob(markdown));
const textOf = (docx: DocxPackage): string => paragraphTexts(docx.document).join('\n');
const targetsOf = (docx: DocxPackage): string[] => externalTargets(docx.parts['word/_rels/document.xml.rels']);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('images in the Word file', () => {
  it('embeds PNG, JPEG, GIF and BMP images', async () => {
    stubFetch({
      'https://img.example/a.png': { body: bytesOf(PNG) },
      'https://img.example/b.jpg': { body: bytesOf(JPEG) },
      'https://img.example/c.gif': { body: bytesOf(GIF) },
      'https://img.example/d.bmp': { body: bytesOf(BMP) },
    });

    const docx = await docxOf(
      '![a](https://img.example/a.png)\n\n![b](https://img.example/b.jpg)\n\n![c](https://img.example/c.gif)\n\n![d](https://img.example/d.bmp)',
    );

    expect(docx.media.map((name) => name.split('.').pop()).sort()).toEqual(['bmp', 'gif', 'jpg', 'png']);
    expect(elements(docx.document, 'w:drawing')).toHaveLength(4);
    expect(textOf(docx)).toBe('\n\n\n');
  });

  it('embeds an image that is written into the message as a data URL', async () => {
    const dataUrl = `data:image/png;base64,${PNG}`;
    stubFetch({ [dataUrl]: { body: bytesOf(PNG) } });

    const docx = await docxOf(`![inline](${dataUrl})`);

    expect(docx.media).toHaveLength(1);
    expect(textOf(docx)).not.toContain('base64');
  });

  it('asks for each image without a referrer and with a way to give up', async () => {
    const fetchMock = stubFetch({ 'https://img.example/a.png': { body: bytesOf(PNG) } });

    await docxOf('![a](https://img.example/a.png)');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://img.example/a.png',
      expect.objectContaining({ referrerPolicy: 'no-referrer', signal: expect.any(AbortSignal) }),
    );
  });

  it('does not fetch anything for a message without images', async () => {
    const fetchMock = stubFetch({});

    await docxOf('No pictures here, only [a link](https://a.example).');

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('keeps an image that is a link clickable', async () => {
    stubFetch({ 'https://img.example/a.png': { body: bytesOf(PNG) } });

    const docx = await docxOf('[![shot](https://img.example/a.png)](https://site.example/page)');
    const [link] = elements(docx.document, 'w:hyperlink');

    expect(targetsOf(docx)).toEqual(['https://site.example/page']);
    expect(elements(link, 'w:drawing')).toHaveLength(1);
  });

  it('shows the alt text of an image that Word cannot show as a link to it, and the address when there is no alt text', async () => {
    stubFetch({
      'https://img.example/a.webp': { body: bytesOf(WEBP) },
      'https://img.example/b.webp': { body: bytesOf(WEBP) },
    });

    const docx = await docxOf('![a photo](https://img.example/a.webp)\n\n![](https://img.example/b.webp)');

    expect(docx.media).toEqual([]);
    expect(paragraphTexts(docx.document)).toEqual(['a photo', 'https://img.example/b.webp']);
    expect([...targetsOf(docx)].sort()).toEqual(['https://img.example/a.webp', 'https://img.example/b.webp']);
  });

  it('does not take a page for an image because the host calls it one', async () => {
    stubFetch({ 'https://img.example/page.png': { body: '<html><body>Sign in</body></html>' } });

    const docx = await docxOf('![chart](https://img.example/page.png)');

    expect(docx.media).toEqual([]);
    expect(textOf(docx)).toContain('chart');
  });

  it.each([
    ['is not found, though its error page is an image', { body: bytesOf(PNG), status: 404 } as Reply],
    ['is refused by the server, though its error page is an image', { body: bytesOf(PNG), status: 403 } as Reply],
    ['cannot be reached', 'network-error' as Reply],
    ['is empty', { body: new Uint8Array(0) } as Reply],
  ])('keeps the alt text of an image that %s', async (_case, reply) => {
    stubFetch({ 'https://img.example/a.png': reply });

    const docx = await docxOf('![the alt](https://img.example/a.png)');

    expect(docx.media).toEqual([]);
    expect(textOf(docx)).toContain('the alt');
  });

  it('puts the pieces of a body back together in order', async () => {
    stubFetch({ 'https://img.example/a.png': { body: bytesOf(PNG), pieceSize: 5 } });

    const html = await htmlWith('![a](https://img.example/a.png)');

    expect(html).toContain(`src="data:image/png;base64,${PNG}"`);
  });

  it('keeps the alt text of an image whose response has no body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => imageResponse(null, 204)),
    );

    const html = await htmlWith('![the alt](https://img.example/a.png)');

    expect(html).not.toContain('<img');
    expect(html).toContain('the alt');
  });

  it('shows no address for an image inside a link, and keeps the link', async () => {
    stubFetch({});

    const docx = await docxOf('[![shot](https://img.example/a.png)](https://site.example/page)');

    expect(targetsOf(docx)).toEqual(['https://site.example/page']);
    expect(textOf(docx)).toBe('shot');
  });

  it('shows a relative address as text only, and nothing for a data image it cannot read', async () => {
    stubFetch({ 'data:image/png;base64,AAAA': { body: bytesOf('AAAA') } });

    const docx = await docxOf('![](/files/a.png)\n\n![](data:image/png;base64,AAAA)');

    expect(targetsOf(docx)).toEqual([]);
    expect(textOf(docx)).toContain('/files/a.png');
    expect(textOf(docx)).not.toContain('base64');
  });
});
