/**
 * @vitest-environment jsdom
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';

const CLIP_IMAGE_URLS_PATH = path.resolve(
  __dirname,
  '../../../../../myrm-agent-extension/src/content/clip_image_urls.js',
);

type ClipImageUrlsApi = {
  parseSrcset: (srcset: string, baseUrl: string) => string | null;
  collectImageUrls: (rootHtml: string, baseUrl: string, maxAssets?: number) => string[];
};

declare global {
  // eslint-disable-next-line no-var
  var MyrmClipImageUrls: ClipImageUrlsApi | undefined;
}

beforeAll(() => {
  const source = readFileSync(CLIP_IMAGE_URLS_PATH, 'utf8');
  // Classic IIFE script; safe to eval once in jsdom test harness.
  // eslint-disable-next-line no-eval
  eval(source);
});

describe('MyrmClipImageUrls', () => {
  const api = (): ClipImageUrlsApi => {
    if (!globalThis.MyrmClipImageUrls) {
      throw new Error('MyrmClipImageUrls failed to load');
    }
    return globalThis.MyrmClipImageUrls;
  };

  it('parseSrcset prefers the widest width descriptor', () => {
    const picked = api().parseSrcset(
      'https://cdn.example.com/a-424w.webp 424w, https://cdn.example.com/a-1272w.webp 1272w',
      'https://example.com/post',
    );
    expect(picked).toBe('https://cdn.example.com/a-1272w.webp');
  });

  it('collectImageUrls uses srcset over low-res src (Substack-style)', () => {
    const html = `
      <article>
        <img
          src="https://substackcdn.com/image/fetch/w_424,c_limit/https%3A%2F%2Fmedia.example%2Fthumb.webp"
          srcset="
            https://substackcdn.com/image/fetch/w_424,c_limit/https%3A%2F%2Fmedia.example%2Fthumb.webp 424w,
            https://substackcdn.com/image/fetch/w_1272,c_limit/https%3A%2F%2Fmedia.example%2Ffull.webp 1272w
          "
        />
      </article>
    `;
    const urls = api().collectImageUrls(html, 'https://newsletter.example.com/p/article', 5);
    expect(urls).toHaveLength(1);
    expect(urls[0]).toContain('w_1272');
    expect(urls[0]).not.toContain('w_424');
  });

  it('collectImageUrls includes picture source srcset candidates', () => {
    const html = `
      <picture>
        <source srcset="https://cdn.example.com/hero-800.webp 800w, https://cdn.example.com/hero-1600.webp 1600w" />
        <img src="https://cdn.example.com/hero-400.webp" />
      </picture>
    `;
    const urls = api().collectImageUrls(html, 'https://example.com', 5);
    expect(urls.some((u) => u.includes('hero-1600'))).toBe(true);
  });
});
