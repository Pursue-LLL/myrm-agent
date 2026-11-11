/**
 * [INPUT] hast::Element, Root (type-only); unified::Plugin (type-only).
 * [OUTPUT] rehypeWordImages, WordImageLimits.
 * [POS] Which images of an exported message the Word file embeds. The converter downloads nothing and leaves out, without telling the reader, an image it cannot show, so each image is fetched here and stays text when the browser cannot get it or Word cannot show it.
 */
import type { Element, Root } from 'hast';
import type { Plugin } from 'unified';

export interface WordImageLimits {
  /** Word shows an image at page width, so a bigger file only makes the document heavier. */
  maxImageBytes: number;
  /** However many images a message links, one document embeds no more than this: each costs several copies in memory while it is built. The downloads under way count against it too, so it also caps what the export holds at once. */
  maxTotalBytes: number;
  /** A host that never answers would otherwise hold the export for as long as the browser keeps the connection open. */
  timeoutMs: number;
}

const DEFAULT_LIMITS: WordImageLimits = {
  maxImageBytes: 10 * 1024 * 1024,
  maxTotalBytes: 50 * 1024 * 1024,
  timeoutMs: 10_000,
};

/** The rasters Word can show, by the first bytes of the file: the converter reads an image by its bytes, whatever type the host declares. */
const IMAGE_SIGNATURES: ReadonlyArray<{ mime: string; bytes: readonly number[] }> = [
  { mime: 'image/png', bytes: [0x89, 0x50, 0x4e, 0x47] },
  { mime: 'image/jpeg', bytes: [0xff, 0xd8, 0xff] },
  { mime: 'image/gif', bytes: [0x47, 0x49, 0x46, 0x38] },
  { mime: 'image/bmp', bytes: [0x42, 0x4d] },
];

interface ImageRef {
  img: Element;
  /** An image inside a link keeps the link and gives up its own, because a link cannot hold a link. */
  insideLink: boolean;
}

function readAsDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

async function detectImageMime(blob: Blob): Promise<string | null> {
  const head = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
  return IMAGE_SIGNATURES.find(({ bytes }) => bytes.every((byte, i) => head[i] === byte))?.mime ?? null;
}

/** What the document may still take in: a download holds the bytes it has received until its image is in the document, and gives them back when it ends without one. */
interface ByteBudget {
  take(bytes: number): boolean;
  give(bytes: number): void;
}

function createByteBudget(total: number): ByteBudget {
  let remaining = total;
  return {
    take(bytes) {
      if (bytes > remaining) {
        return false;
      }
      remaining -= bytes;
      return true;
    },
    give(bytes) {
      remaining += bytes;
    },
  };
}

/**
 * The body as a Blob, read piece by piece and cancelled the moment it goes over the image limit or `hold` refuses a
 * piece, so a host that states no size, or a false one, cannot make the browser buffer more than the limits allow.
 * Null when it went over, or when there is no body to read.
 */
async function readBody(
  response: Response,
  maxImageBytes: number,
  hold: (bytes: number) => boolean,
): Promise<Blob | null> {
  const reader = response.body?.getReader();
  if (!reader) {
    return null;
  }
  const pieces: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      return new Blob(pieces);
    }
    size += value.byteLength;
    if (size > maxImageBytes || !hold(value.byteLength)) {
      await reader.cancel();
      return null;
    }
    pieces.push(value);
  }
}

/** The image as a data URL, or null when it cannot be had, is not a raster Word shows, or would go over a limit. */
async function fetchWordImage(
  src: string,
  { maxImageBytes, timeoutMs }: WordImageLimits,
  budget: ByteBudget,
): Promise<string | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let held = 0;
  let embedded = false;
  const hold = (bytes: number): boolean => {
    if (!budget.take(bytes)) {
      return false;
    }
    held += bytes;
    return true;
  };
  try {
    const response = await fetch(src, { referrerPolicy: 'no-referrer', signal: controller.signal });
    // A host that states a size over the limit is not downloaded at all. Aborting also stops the body of a failed
    // response from going on downloading.
    if (!response.ok || Number(response.headers.get('content-length')) > maxImageBytes) {
      controller.abort();
      return null;
    }
    const blob = await readBody(response, maxImageBytes, hold);
    const mime = blob && (await detectImageMime(blob));
    if (!blob || !mime) {
      return null;
    }
    const dataUrl = await readAsDataUrl(blob.slice(0, blob.size, mime));
    embedded = true;
    return dataUrl;
  } catch {
    // Offline, refused by the host's CORS policy, an address the browser cannot fetch, or the timeout: the image stays
    // text and the export goes on.
    return null;
  } finally {
    clearTimeout(timer);
    if (!embedded) {
      budget.give(held);
    }
  }
}

function collectImages(node: Root | Element, insideLink: boolean, found: ImageRef[]): void {
  for (const child of node.children) {
    if (child.type !== 'element') {
      continue;
    }
    if (child.tagName === 'img' && typeof child.properties.src === 'string' && child.properties.src) {
      found.push({ img: child, insideLink });
    }
    collectImages(child, insideLink || child.tagName === 'a', found);
  }
}

/** The image's alt text in its place; a web address with no alt text is kept as a link, so the reader can still open it. */
function replaceWithText(img: Element, src: string, insideLink: boolean): void {
  const alt = typeof img.properties.alt === 'string' ? img.properties.alt : '';
  const linkable = !insideLink && /^https?:\/\//i.test(src);
  img.tagName = linkable ? 'a' : 'span';
  img.properties = linkable ? { href: src } : {};
  // A data URL is the image itself, not something a reader can use as text.
  img.children = [{ type: 'text', value: alt || (src.startsWith('data:') ? '' : src) }];
}

/** Replaces each image's address by the image itself (a data URL), fetching all of them at once. */
export const rehypeWordImages: Plugin<[Partial<WordImageLimits>?], Root> = (overrides) => async (tree) => {
  const limits = { ...DEFAULT_LIMITS, ...overrides };
  const images: ImageRef[] = [];
  collectImages(tree, false, images);

  const budget = createByteBudget(limits.maxTotalBytes);

  await Promise.all(
    images.map(async ({ img, insideLink }) => {
      const src = String(img.properties.src);
      const dataUrl = await fetchWordImage(src, limits, budget);
      if (dataUrl) {
        img.properties.src = dataUrl;
      } else {
        replaceWithText(img, src, insideLink);
      }
    }),
  );
};
