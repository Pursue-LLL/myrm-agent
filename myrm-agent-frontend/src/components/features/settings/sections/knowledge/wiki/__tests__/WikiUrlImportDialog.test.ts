import { describe, expect, it } from 'vitest';

function parseInputUrls(rawText: string): string[] {
  const rawLines = rawText.split('\n');
  const seen = new Set<string>();
  const valid: string[] = [];
  for (const raw of rawLines) {
    const line = raw.trim();
    if (!line) continue;
    if (!/^https?:\/\//i.test(line)) continue;
    if (!seen.has(line)) {
      seen.add(line);
      valid.push(line);
    }
  }
  return valid;
}

describe('WikiUrlImportDialog URL parser', () => {
  it('filters empty lines and trims whitespace', () => {
    const text = '\n  https://example.com/page-1   \n\n   \nhttps://example.com/page-2\n';
    expect(parseInputUrls(text)).toEqual(['https://example.com/page-1', 'https://example.com/page-2']);
  });

  it('rejects invalid schemes such as javascript: or file://', () => {
    const text = 'javascript:alert(1)\nfile:///etc/passwd\nhttps://example.com/safe\nhttp://example.org/doc';
    expect(parseInputUrls(text)).toEqual(['https://example.com/safe', 'http://example.org/doc']);
  });

  it('deduplicates identical URLs while preserving order', () => {
    const text = 'https://example.com/a\nhttps://example.com/b\nhttps://example.com/a\nhttps://example.com/c';
    expect(parseInputUrls(text)).toEqual(['https://example.com/a', 'https://example.com/b', 'https://example.com/c']);
  });

  it('handles up to 50 items and supports slicing cleanly', () => {
    const lines = Array.from({ length: 60 }, (_, i) => `https://example.com/post-${i + 1}`);
    const parsed = parseInputUrls(lines.join('\n'));
    expect(parsed.length).toBe(60);
    const sliced = parsed.slice(0, 50);
    expect(sliced.length).toBe(50);
    expect(sliced[0]).toBe('https://example.com/post-1');
    expect(sliced[49]).toBe('https://example.com/post-50');
  });
});
