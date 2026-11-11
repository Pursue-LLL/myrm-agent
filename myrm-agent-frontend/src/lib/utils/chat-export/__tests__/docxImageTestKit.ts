import rehypeStringify from 'rehype-stringify';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import { unified } from 'unified';
import { vi } from 'vitest';
import { rehypeWordImages, type WordImageLimits } from '../chatExportDocxImages';

/** 1x1 files written by ImageMagick; the first bytes are what the export recognises an image by. */
export const PNG =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQMAAAAl21bKAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAAGUExURTNmzP///w3eOY0AAAABYktHRAH/Ai3eAAAAB3RJTUUH6gsLAgMaDhFagwAAAApJREFUCNdjYAAAAAIAAeIhvDMAAAAldEVYdGRhdGU6Y3JlYXRlADIwMjYtMTEtMTFUMDI6MDM6MjYrMDA6MDBPuOGxAAAAJXRFWHRkYXRlOm1vZGlmeQAyMDI2LTExLTExVDAyOjAzOjI2KzAwOjAwPuVZDQAAACh0RVh0ZGF0ZTp0aW1lc3RhbXAAMjAyNi0xMS0xMVQwMjowMzoyNiswMDowMGnweNIAAAAASUVORK5CYII=';
export const JPEG =
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAABAAEDAREAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAAB//EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAVAQEBAAAAAAAAAAAAAAAAAAAHCP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AC9UAkf/2Q==';
export const GIF = 'R0lGODlhAQABAPAAADNmzAAAACH5BAAAAAAALAAAAAABAAEAAAICRAEAOw==';
export const BMP = 'Qk06AAAAAAAAADYAAAAoAAAAAQAAAAEAAAABABgAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAzGYzAA==';
export const WEBP = 'UklGRjYAAABXRUJQVlA4ICoAAADQAQCdASoBAAEAAgA0JaACdLoB+AADsAD+7L2P/PTNeYP8nP+3Jl5tsAA=';
export const GIF_BYTES = 43;

export const bytesOf = (base64: string): Uint8Array<ArrayBuffer> =>
  Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));

export type Reply =
  | { body: Uint8Array<ArrayBuffer> | string; status?: number; contentLength?: number; pieceSize?: number }
  | 'network-error'
  | 'hang';

/** A body that arrives in pieces of `pieceSize` bytes, as a download does. */
export function streamOf(
  body: Uint8Array<ArrayBuffer> | string,
  pieceSize = Infinity,
): ReadableStream<Uint8Array<ArrayBuffer>> {
  const bytes = typeof body === 'string' ? new TextEncoder().encode(body) : body;
  let offset = 0;
  return new ReadableStream<Uint8Array<ArrayBuffer>>({
    pull(controller) {
      if (offset >= bytes.length) {
        controller.close();
        return;
      }
      controller.enqueue(bytes.slice(offset, offset + pieceSize));
      offset += pieceSize;
    },
  });
}

/** What an endless download did: how many bytes the export pulled from it, and whether it gave up on it. */
export interface EndlessStats {
  pulled: number;
  cancelled: boolean;
}

/** A body the host never finishes: it keeps sending `piece` until the reader cancels. */
export function endlessStream(
  piece: Uint8Array<ArrayBuffer>,
  stats: EndlessStats,
): ReadableStream<Uint8Array<ArrayBuffer>> {
  return new ReadableStream<Uint8Array<ArrayBuffer>>({
    pull(controller) {
      stats.pulled += piece.byteLength;
      controller.enqueue(piece);
    },
    cancel() {
      stats.cancelled = true;
    },
  });
}

/** The part of a fetch response the export reads; `contentLength` is the size the host states. */
export function imageResponse(
  body: ReadableStream<Uint8Array<ArrayBuffer>> | null,
  status = 200,
  contentLength?: number,
) {
  return {
    ok: status < 400,
    status,
    headers: new Headers(contentLength === undefined ? {} : { 'content-length': String(contentLength) }),
    body,
  };
}

/** Stands in for the browser's fetch: each address gets its reply; an unlisted one is a 404. */
export function stubFetch(replies: Record<string, Reply>): ReturnType<typeof vi.fn> {
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
    return imageResponse(streamOf(reply.body, reply.pieceSize), reply.status, reply.contentLength);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** What the plugin leaves in the HTML, for limits that would need megabytes of real data in the Word file. */
export async function htmlWith(markdown: string, limits?: Partial<WordImageLimits>): Promise<string> {
  const processor = unified().use(remarkParse).use(remarkRehype).use(rehypeWordImages, limits).use(rehypeStringify);
  return String(await processor.process(markdown));
}

export const embedded = (html: string): number => (html.match(/src="data:image\/gif;base64,/g) ?? []).length;
