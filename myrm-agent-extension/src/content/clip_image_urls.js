/**
 * Pure image URL resolution for wiki clip (srcset / lazy attrs / picture).
 * Loaded before clip.js; exposed on globalThis for injected content scripts.
 */

(function initClipImageUrls(root) {
  const HTTP_PREFIX = /^https?:\/\//i;

  function absUrl(raw, baseUrl) {
    if (!raw || !String(raw).trim()) return null;
    try {
      return new URL(String(raw).trim(), baseUrl).href;
    } catch {
      return null;
    }
  }

  /**
   * Pick the widest width-descriptor candidate from srcset (Substack CDN-safe comma tokenization).
   */
  function parseSrcset(srcset, baseUrl) {
    if (!srcset || !String(srcset).trim()) return null;
    let bestUrl = null;
    let bestWidth = 0;
    let fallbackUrl = null;
    const tokens = String(srcset)
      .trim()
      .split(/,\s+(?=https?:\/\/)/i)
      .map((part) => part.trim())
      .filter(Boolean);
    for (const token of tokens) {
      const parts = token.split(/\s+/);
      if (parts.length === 0 || !parts[0]) continue;
      const candidateUrl = absUrl(parts[0], baseUrl);
      if (!candidateUrl) continue;
      if (!fallbackUrl) fallbackUrl = candidateUrl;
      const descriptor = parts[parts.length - 1] || "";
      const widthMatch = /^(\d+)w$/i.exec(descriptor);
      if (widthMatch && parts.length >= 2) {
        const width = Number.parseInt(widthMatch[1], 10);
        if (width > bestWidth) {
          bestWidth = width;
          bestUrl = candidateUrl;
        }
      }
    }
    return bestUrl || fallbackUrl;
  }

  function findLazySrc(el, baseUrl) {
    for (const attr of el.attributes) {
      if (attr.name === "src") continue;
      if (/^data-.*src/i.test(attr.name)) {
        const resolved = absUrl(attr.value, baseUrl);
        if (resolved) return resolved;
      }
    }
    return null;
  }

  function resolveImgUrl(img, baseUrl) {
    const fromSrcset =
      parseSrcset(img.getAttribute("srcset"), baseUrl) ||
      parseSrcset(img.getAttribute("data-srcset"), baseUrl);
    if (fromSrcset) return fromSrcset;

    const direct =
      absUrl(img.getAttribute("src"), baseUrl) ||
      absUrl(img.getAttribute("data-src"), baseUrl) ||
      absUrl(img.getAttribute("data-lazy-src"), baseUrl) ||
      absUrl(img.getAttribute("data-original"), baseUrl) ||
      findLazySrc(img, baseUrl);
    return direct;
  }

  function collectPictureUrls(doc, baseUrl, urls, seen) {
    doc.querySelectorAll("picture source[srcset], picture source[data-srcset]").forEach((source) => {
      const picked =
        parseSrcset(source.getAttribute("srcset"), baseUrl) ||
        parseSrcset(source.getAttribute("data-srcset"), baseUrl) ||
        absUrl(source.getAttribute("src"), baseUrl);
      if (picked && HTTP_PREFIX.test(picked) && !seen.has(picked)) {
        seen.add(picked);
        urls.push(picked);
      }
    });
  }

  function collectImageUrls(rootHtml, baseUrl, maxAssets = 20) {
    const doc = new DOMParser().parseFromString(rootHtml, "text/html");
    const urls = [];
    const seen = new Set();

    collectPictureUrls(doc, baseUrl, urls, seen);

    doc.querySelectorAll("img").forEach((img) => {
      const picked = resolveImgUrl(img, baseUrl);
      if (picked && HTTP_PREFIX.test(picked) && !seen.has(picked)) {
        seen.add(picked);
        urls.push(picked);
      }
    });

    return urls.slice(0, maxAssets);
  }

  root.MyrmClipImageUrls = {
    absUrl,
    parseSrcset,
    resolveImgUrl,
    collectImageUrls,
  };
})(typeof globalThis !== "undefined" ? globalThis : self);
