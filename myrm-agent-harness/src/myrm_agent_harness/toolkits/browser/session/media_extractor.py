"""Media extraction: the image, video, audio and preview-image URLs of a page.


[INPUT]
- patchright.async_api::Page (POS: Patchright page instance whose frames are read)

[OUTPUT]
- extract_page_media: lists a page's high-value media URLs as Markdown text

[POS]
Media half of content extraction: ``extractor.Extractor.extract_media`` delegates here, so ``Extractor`` stays a thin
facade over the text, screenshot, PDF and visual-content readers. One script per frame collects images (lazy-loaded
included), videos, audio and OG/Twitter preview images; icons, logos and tiny decorative images are dropped, URLs are
de-duplicated across frames, and the listing is bounded in size.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from patchright.async_api import Page

logger = logging.getLogger(__name__)


async def extract_page_media(page: Page, selector: str, max_images: int, max_videos: int, max_audios: int) -> str:
    """Collect the media URLs of every frame of ``page``; arguments as in ``Extractor.extract_media``."""
    js_script = """
            (params) => {
                const maxImages = params.maxImages;
                const maxVideos = params.maxVideos;
                const maxAudios = params.maxAudios;
                const selector = params.selector;

                const root = selector
                    ? (document.querySelector(selector) || document.body)
                    : document.body;

                const seen = new Set();
                function abs(url) {
                    if (!url || url.startsWith('data:') || url.startsWith('blob:')) return null;
                    try { return new URL(url, document.baseURI).href; }
                    catch { return null; }
                }
                function dedup(url) {
                    if (!url || seen.has(url)) return null;
                    seen.add(url);
                    return url;
                }

                const ICON_PATTERNS = /icon|logo|favicon|sprite|avatar|badge|arrow|caret|chevron|spinner/i;
                function isDecorativeImg(el) {
                    const src = el.getAttribute('src') || '';
                    const cls = el.className || '';
                    const id = el.id || '';
                    if (ICON_PATTERNS.test(src) || ICON_PATTERNS.test(cls) || ICON_PATTERNS.test(id)) return true;
                    const w = el.naturalWidth || el.width || parseInt(el.getAttribute('width')) || 0;
                    const h = el.naturalHeight || el.height || parseInt(el.getAttribute('height')) || 0;
                    if (w > 0 && h > 0 && w < 50 && h < 50) return true;
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && rect.width < 50 && rect.height < 50) return true;
                    return false;
                }

                function parseSrcset(srcset) {
                    if (!srcset) return null;
                    const candidates = srcset.split(',').map(s => s.trim().split(/\\s+/));
                    let best = null;
                    let bestW = 0;
                    for (const [url, descriptor] of candidates) {
                        const w = parseInt(descriptor) || 0;
                        if (w > bestW || !best) { best = url; bestW = w; }
                    }
                    return abs(best);
                }

                function findLazySrc(el) {
                    for (const attr of el.attributes) {
                        if (attr.name !== 'src' && /^data-.*src/i.test(attr.name)) {
                            const resolved = abs(attr.value);
                            if (resolved) return resolved;
                        }
                    }
                    return null;
                }

                // Collect images
                const images = [];
                for (const img of root.querySelectorAll('img')) {
                    if (isDecorativeImg(img)) continue;
                    const src = abs(img.getAttribute('src'))
                        || abs(img.getAttribute('data-src'))
                        || abs(img.getAttribute('data-lazy-src'))
                        || abs(img.getAttribute('data-original'))
                        || parseSrcset(img.getAttribute('srcset'))
                        || parseSrcset(img.getAttribute('data-srcset'))
                        || findLazySrc(img);
                    const url = dedup(src);
                    if (!url) continue;
                    const w = img.naturalWidth || img.width || parseInt(img.getAttribute('width')) || null;
                    const h = img.naturalHeight || img.height || parseInt(img.getAttribute('height')) || null;
                    const alt = (img.getAttribute('alt') || '').slice(0, 80);
                    images.push({ url, w, h, alt });
                    if (images.length >= maxImages) break;
                }

                // <picture><source> elements
                if (images.length < maxImages) {
                    for (const pic of root.querySelectorAll('picture')) {
                        for (const source of pic.querySelectorAll('source')) {
                            const url = dedup(parseSrcset(source.getAttribute('srcset')) || abs(source.getAttribute('src')));
                            if (!url) continue;
                            images.push({ url, w: null, h: null, alt: '' });
                            if (images.length >= maxImages) break;
                        }
                        if (images.length >= maxImages) break;
                    }
                }

                // Collect videos
                const videos = [];
                for (const vid of root.querySelectorAll('video')) {
                    const src = abs(vid.getAttribute('src'));
                    const poster = abs(vid.getAttribute('poster'));
                    if (src) {
                        const url = dedup(src);
                        if (url) videos.push({ url, poster: poster || null });
                    }
                    for (const source of vid.querySelectorAll('source')) {
                        const url = dedup(abs(source.getAttribute('src')));
                        if (url) videos.push({ url, poster: poster || null });
                    }
                    if (videos.length >= maxVideos) break;
                }
                // iframe embeds (YouTube, Vimeo, etc.)
                if (videos.length < maxVideos) {
                    for (const iframe of root.querySelectorAll('iframe[src]')) {
                        const src = iframe.getAttribute('src') || '';
                        if (/youtube|vimeo|dailymotion|wistia/.test(src)) {
                            const url = dedup(abs(src));
                            if (url) videos.push({ url, poster: null });
                            if (videos.length >= maxVideos) break;
                        }
                    }
                }

                // Collect audio
                const audios = [];
                for (const aud of root.querySelectorAll('audio')) {
                    const src = abs(aud.getAttribute('src'));
                    if (src) {
                        const url = dedup(src);
                        if (url) audios.push({ url });
                    }
                    for (const source of aud.querySelectorAll('source')) {
                        const url = dedup(abs(source.getAttribute('src')));
                        if (url) audios.push({ url });
                    }
                    if (audios.length >= maxAudios) break;
                }

                // Meta images (OG, Twitter)
                const metaImages = [];
                for (const meta of document.querySelectorAll('meta[property="og:image"], meta[name="twitter:image"], meta[property="og:image:url"]')) {
                    const url = dedup(abs(meta.getAttribute('content')));
                    if (url) metaImages.push({ property: meta.getAttribute('property') || meta.getAttribute('name'), url });
                }

                return { images, videos, audios, metaImages };
            }
    """

    all_media: dict[str, list[dict[str, str | int | None]]] = {
        "images": [],
        "videos": [],
        "audios": [],
        "metaImages": [],
    }
    seen_urls: set[str] = set()

    for i, frame in enumerate(page.frames):
        try:
            frame_media = await frame.evaluate(
                js_script,
                {"maxImages": max_images, "maxVideos": max_videos, "maxAudios": max_audios, "selector": selector},
            )
            for key in all_media:
                for item in frame_media.get(key, []):
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_media[key].append(item)
        except Exception as exc:
            logger.debug("Extractor: could not extract media from frame %d: %s", i, exc)

    lines: list[str] = []

    imgs = all_media["images"][:max_images]
    if imgs:
        lines.append(f"## Images ({len(imgs)} found)")
        for idx, img in enumerate(imgs, 1):
            parts = [str(img["url"])]
            dims = []
            if img.get("w") and img.get("h"):
                dims.append(f"{img['w']}x{img['h']}")
            if img.get("alt"):
                dims.append(f'alt="{img["alt"]}"')
            if dims:
                parts.append(f"[{', '.join(dims)}]")
            lines.append(f"{idx}. {' '.join(parts)}")

    vids = all_media["videos"][:max_videos]
    if vids:
        lines.append(f"\n## Videos ({len(vids)} found)")
        for idx, vid in enumerate(vids, 1):
            extra = f" [poster: {vid['poster']}]" if vid.get("poster") else ""
            lines.append(f"{idx}. {vid['url']}{extra}")

    auds = all_media["audios"][:max_audios]
    if auds:
        lines.append(f"\n## Audio ({len(auds)} found)")
        for idx, aud in enumerate(auds, 1):
            lines.append(f"{idx}. {aud['url']}")

    metas = all_media["metaImages"]
    if metas:
        lines.append("\n## Meta Images")
        for m in metas:
            lines.append(f"- {m['property']}: {m['url']}")

    if not lines:
        return "No media resources found on this page."

    result = "\n".join(lines)
    if len(result) > 8000:
        result = result[:7950] + "\n\n... (truncated, use selector to narrow scope)"

    logger.info("Extractor: extracted media — %d images, %d videos, %d audio", len(imgs), len(vids), len(auds))
    return result
