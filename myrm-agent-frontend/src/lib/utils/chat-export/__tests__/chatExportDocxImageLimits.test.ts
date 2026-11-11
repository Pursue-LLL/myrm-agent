/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  GIF,
  GIF_BYTES,
  bytesOf,
  embedded,
  endlessStream,
  htmlWith,
  imageResponse,
  streamOf,
  stubFetch,
  type EndlessStats,
  type Reply,
} from './docxImageTestKit';

afterEach(() => {
  vi.unstubAllGlobals();
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

  it.each([
    ['states no size', undefined],
    ['states a size under the limit', 10],
  ])('stops reading a body that never ends, when the host %s', async (_case, contentLength) => {
    const stats: EndlessStats = { pulled: 0, cancelled: false };
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => imageResponse(endlessStream(new Uint8Array(1024), stats), 200, contentLength)),
    );

    const html = await htmlWith(markdownOf(1), { maxImageBytes: 4 * 1024 });

    expect(embedded(html)).toBe(0);
    expect(html).toContain('g0');
    expect(stats.cancelled).toBe(true);
    // The limit plus the pieces the stream may have ready ahead of the reader, not the whole of an endless body.
    expect(stats.pulled).toBeLessThanOrEqual(4 * 1024 + 3 * 1024);
  });

  it('stops reading a download that would take the document over the total', async () => {
    const stats: EndlessStats = { pulled: 0, cancelled: false };
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => imageResponse(endlessStream(new Uint8Array(1024), stats))),
    );

    const html = await htmlWith(markdownOf(1), { maxImageBytes: 64 * 1024, maxTotalBytes: 3 * 1024 });

    expect(embedded(html)).toBe(0);
    expect(stats.cancelled).toBe(true);
    expect(stats.pulled).toBeLessThanOrEqual(3 * 1024 + 3 * 1024);
  });

  it('counts the bytes of every download under way against the same total', async () => {
    const stats = [0, 1].map((): EndlessStats => ({ pulled: 0, cancelled: false }));
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => imageResponse(endlessStream(new Uint8Array(1024), stats[url === gif(0) ? 0 : 1]))),
    );

    const html = await htmlWith(markdownOf(2), { maxImageBytes: 64 * 1024, maxTotalBytes: 8 * 1024 });

    expect(embedded(html)).toBe(0);
    expect(stats.every(({ cancelled }) => cancelled)).toBe(true);
    // Neither download was left to run on to the image limit.
    expect(Math.max(...stats.map(({ pulled }) => pulled))).toBeLessThan(64 * 1024);
  });

  it('gives back what a cut-off download held, so a later image still fits', async () => {
    const stats: EndlessStats = { pulled: 0, cancelled: false };
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url === gif(0)) {
          return imageResponse(endlessStream(new Uint8Array(1024), stats));
        }
        // The second image is asked for only once the first has been given up on.
        await vi.waitFor(() => expect(stats.cancelled).toBe(true));
        return imageResponse(streamOf(bytesOf(GIF)));
      }),
    );

    const html = await htmlWith(markdownOf(2), { maxImageBytes: 64 * 1024, maxTotalBytes: 3 * 1024 });

    expect(embedded(html)).toBe(1);
    expect(html).toContain('g0');
  });

  it('gives back what a download held when it turned out not to be an image', async () => {
    let finished = false;
    const page = new TextEncoder().encode('x'.repeat(40));
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url === gif(0)) {
          let sent = false;
          return imageResponse(
            new ReadableStream<Uint8Array<ArrayBuffer>>({
              pull(controller) {
                if (sent) {
                  finished = true;
                  controller.close();
                  return;
                }
                sent = true;
                controller.enqueue(page);
              },
            }),
          );
        }
        // The second image is asked for only once the first has been read to its end.
        await vi.waitFor(() => expect(finished).toBe(true));
        return imageResponse(streamOf(bytesOf(GIF)));
      }),
    );

    // Room for the GIF, but not for the GIF and the 40 bytes of the page if those were still held.
    const html = await htmlWith(markdownOf(2), { maxTotalBytes: GIF_BYTES + 10 });

    expect(embedded(html)).toBe(1);
    expect(html).toContain('g0');
  });

  it('stops the body of a failed response from going on downloading', async () => {
    const fetchMock = stubFetch({ [gif(0)]: { body: 'not found', status: 404 } });

    await htmlWith(markdownOf(1));

    expect((fetchMock.mock.calls[0][1] as RequestInit).signal?.aborted).toBe(true);
  });

  it('embeds images until the total would go over, and leaves the rest as text', async () => {
    stubFetch(gifs(3));

    // Room for exactly two: an image that fills the total up to the last byte still goes in.
    const html = await htmlWith(markdownOf(3), { maxTotalBytes: GIF_BYTES * 2 });

    expect(embedded(html)).toBe(2);
    expect(html.match(/<img /g)).toHaveLength(2);
    expect(html.match(/<a href="https:\/\/img\.example\/\d\.gif">g\d<\/a>/g)).toHaveLength(1);
  });

  it('keeps the bytes of an embedded image counted against an image that arrives after it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url !== gif(0)) {
          // Long after the first image has been read into the document.
          await new Promise((resolve) => setTimeout(resolve, 50));
        }
        return imageResponse(streamOf(bytesOf(GIF)));
      }),
    );

    const html = await htmlWith(markdownOf(2), { maxTotalBytes: GIF_BYTES + 10 });

    expect(embedded(html)).toBe(1);
    expect(html).toContain('g1');
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
      return imageResponse(streamOf(bytesOf(GIF)));
    });
    vi.stubGlobal('fetch', fetchMock);

    const pending = htmlWith(markdownOf(3));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    release();

    expect(embedded(await pending)).toBe(3);
  });
});
