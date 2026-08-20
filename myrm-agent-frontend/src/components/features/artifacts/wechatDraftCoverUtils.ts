const IMG_SRC_PATTERN = /<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi;

function isRemoteImageSrc(src: string): boolean {
  const normalized = src.trim().toLowerCase();
  return normalized.startsWith('http://') || normalized.startsWith('https://') || normalized.startsWith('data:');
}

export function extractFirstLocalImageSrc(html: string): string | null {
  for (const match of html.matchAll(IMG_SRC_PATTERN)) {
    const src = match[1]?.trim();
    if (!src || isRemoteImageSrc(src)) {
      continue;
    }
    return src;
  }
  return null;
}
