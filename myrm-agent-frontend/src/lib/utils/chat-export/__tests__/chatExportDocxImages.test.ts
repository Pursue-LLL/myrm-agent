/** @vitest-environment jsdom */
import rehypeStringify from 'rehype-stringify';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import { unified } from 'unified';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildDocxBlob } from '../chatExportDocx';
import { rehypeWordImages, type WordImageLimits } from '../chatExportDocxImages';
import { elements, externalTargets, openDocx, paragraphTexts, type DocxPackage } from './docxTestKit';

/** 1x1 files written by ImageMagick; the first bytes are what the export recognises an image by. */
const PNG =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQMAAAAl21bKAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAAGUExURTNmzP///w3eOY0AAAABYktHRAH/Ai3eAAAAB3RJTUUH6gsLAgMaDhFagwAAAApJREFUCNdjYAAAAAIAAeIhvDMAAAAldEVYdGRhdGU6Y3JlYXRlADIwMjYtMTEtMTFUMDI6MDM6MjYrMDA6MDBPuOGxAAAAJXRFWHRkYXRlOm1vZGlmeQAyMDI2LTExLTExVDAyOjAzOjI2KzAwOjAwPuVZDQAAACh0RVh0ZGF0ZTp0aW1lc3RhbXAAMjAyNi0xMS0xMVQwMjowMzoyNiswMDowMGnweNIAAAAASUVORK5CYII=';
const JPEG =
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAABAAEDAREAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAAB//EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAVAQEBAAAAAAAAAAAAAAAAAAAHCP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AC9UAkf/2Q==';
const GIF = 'R0lGODlhAQABAPAAADNmzAAAACH5BAAAAAAALAAAAAABAAEAAAICRAEAOw==';
const BMP = 'Qk06AAAAAAAAADYAAAAoAAAAAQAAAAEAAAABABgAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAzGYzAA==';
const WEBP = 'UklGRjYAAABXRUJQVlA4ICoAAADQAQCdASoBAAEAAgA0JaACdLoB+AADsAD+7L2P/PTNeYP8nP+3Jl5tsAA=';
const GIF_BYTES = 43;

const bytesOf = (base64: string): Uint8Array<ArrayBuffer> => Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));

type Reply =
  { body: Uint8Array<ArrayBuffer> | string; status?: number; contentLength?: number } | 'network-error' | 'hang';

/** The part of a fetch response the export reads; `contentLength` is the size the host states. */
function imageResponse(body: Uint8Array<ArrayBuffer> | string, status = 200, contentLength?: number) {
  return {
    ok: status < 400,
    status,
    headers: new Headers(contentLength === undefined ? {} : { 'content-length': String(contentLength) }),
    blob: async () => new Blob([body], { type: 'image/png' }),
  };
}

/** Stands in for the browser's fetch: each address gets its reply; an unlisted one is a 404. */
function stubFetch(replies: Record<string, Reply>): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const reply = replies[url] ?? { body: 'not found', status: 404 };
    if (reply === 'network-error') {
      throw new TypeError('Failed to fetch');
    }
    if (reply === 'hang') {
      return new Promise<never>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('The operation was aborted.', 'AbortError')),
        );
      });
    }
    return imageResponse(reply.body, reply.status, reply.contentLength);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const docxOf = async (markdown: string): Promise<DocxPackage> => openDocx(await buildDocxBlob(markdown));
const textOf = (docx: DocxPackage): string => paragraphTexts(docx.document).join('\n');
const targetsOf = (docx: DocxPackage): string[] => externalTargets(docx.parts['word/_rels/document.xml.rels']);

/** What the plugin leaves in the HTML, for limits that would need megabytes of real data in the Word file. */
async function htmlWith(markdown: string, limits?: Partial<WordImageLimits>): Promise<string> {
  const processor = unified().use(remarkParse).use(remarkRehype).use(rehypeWordImages, limits).use(rehypeStringify);
  return String(await processor.process(markdown));
}

const embedded = (html: string): number => (html.match(/src="data:image\/gif;base64,/g) ?? []).length;

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

describe('limits on images', () => {
  const gif = (n: number): string => `https://img.example/${n}.gif`;
  const gifs = (count: number): Record<string, Reply> =>
    Object.fromEntries(Array.from({ length: count }, (_, i) => [gif(i), { body: bytesOf(GIF) } as Reply]));
  const markdownOf = (count: number): string =>
    Array.from({ length: count }, (_, i) => `![g${i}](${gif(i)})`).join('\n\n');

  it('embeds an image of exactly the largest size and leaves out one byte more', async () => {
    stubFetch(gifs(1));

    expect(embedded(await htmlWith(markdownOf(1), { maxImageBytes: GIF_BYTES }))).toBe(1);
    expect(embedded(await htmlWith(markdownOf(1), { maxImageBytes: GIF_BYTES - 1 }))).toBe(0);
  });

  it('does not download an image the host says is over the largest size', async () => {
    const fetchMock = stubFetch({
      [gif(0)]: { body: bytesOf(GIF), contentLength: GIF_BYTES + 1 },
      [gif(1)]: { body: bytesOf(GIF), contentLength: GIF_BYTES },
    });

    const html = await htmlWith(markdownOf(2), { maxImageBytes: GIF_BYTES });

    // Both bodies are small enough to embed, so only the size the host states can have kept the first one out.
    expect(embedded(html)).toBe(1);
    expect(html).toContain('g0');
    expect((fetchMock.mock.calls[0][1] as RequestInit).signal?.aborted).toBe(true);
    expect((fetchMock.mock.calls[1][1] as RequestInit).signal?.aborted).toBe(false);
  });

  it('stops the body of a failed response from going on downloading', async () => {
    const fetchMock = stubFetch({ [gif(0)]: { body: 'not found', status: 404 } });

    await htmlWith(markdownOf(1));

    expect((fetchMock.mock.calls[0][1] as RequestInit).signal?.aborted).toBe(true);
  });

  it('embeds images until the total would go over, and leaves the rest as text', async () => {
    stubFetch(gifs(3));

    const html = await htmlWith(markdownOf(3), { maxTotalBytes: GIF_BYTES * 2 + 1 });

    expect(embedded(html)).toBe(2);
    expect(html.match(/<img /g)).toHaveLength(2);
    expect(html.match(/<a href="https:\/\/img\.example\/\d\.gif">g\d<\/a>/g)).toHaveLength(1);
  });

  it('gives up on a host that does not answer in time, and the export goes on', async () => {
    const fetchMock = stubFetch({ [gif(0)]: 'hang', [gif(1)]: { body: bytesOf(GIF) } });
    const started = Date.now();

    const html = await htmlWith(markdownOf(2), { timeoutMs: 30 });

    expect(Date.now() - started).toBeLessThan(2000);
    expect(embedded(html)).toBe(1);
    expect(html).toContain('g0');
    expect((fetchMock.mock.calls[0][1] as RequestInit).signal?.aborted).toBe(true);
  });

  it('asks for all images at once, not one after the other', async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = vi.fn(async () => {
      await gate;
      return imageResponse(bytesOf(GIF));
    });
    vi.stubGlobal('fetch', fetchMock);

    const pending = htmlWith(markdownOf(3));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    release();

    expect(embedded(await pending)).toBe(3);
  });
});
