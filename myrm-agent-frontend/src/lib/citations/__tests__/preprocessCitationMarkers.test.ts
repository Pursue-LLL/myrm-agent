import { describe, expect, it } from 'vitest';
import type { Source } from '@/store/chat/types';
import { maskCodeRegions, unmaskCodeRegions } from '../maskCodeRegions';
import { preprocessCitationMarkers } from '../preprocessCitationMarkers';

const sources: Source[] = [
  {
    index: 1,
    type: 'web_search',
    title: 'Paper A',
    url: 'https://example.com/a',
  },
  {
    index: 2,
    type: 'web_search',
    title: 'Report B',
    url: 'https://news.example.org/report',
  },
];

describe('preprocessCitationMarkers', () => {
  it('converts full-width markers', () => {
    const result = preprocessCitationMarkers('增长 5%【1】。', sources);
    expect(result).toContain('<citation data-num="1"');
    expect(result).toContain('data-source-index="0"');
  });

  it('converts half-width markers', () => {
    const result = preprocessCitationMarkers('Growth was 5% [1].', sources);
    expect(result).toContain('<citation data-num="1"');
  });

  it('converts citation markdown links', () => {
    const result = preprocessCitationMarkers(
      'Claim [citation:Paper A](https://example.com/a).',
      sources,
    );
    expect(result).toContain('<citation data-num="1"');
    expect(result).not.toContain('[citation:');
  });

  it('leaves unknown indices as plain text', () => {
    const result = preprocessCitationMarkers('Unknown [9].', sources);
    expect(result).toBe('Unknown [9].');
  });

  it('does not convert full-width markers inside fenced code blocks', () => {
    const input = 'Prose cites 【1】。\n\n```python\n# example marker 【1】\n```';
    const result = preprocessCitationMarkers(input, sources);
    expect(result).toContain('<citation data-num="1"');
    expect(result).toContain('# example marker 【1】');
    expect(result).not.toMatch(/example marker <citation/);
  });

  it('does not convert half-width markers inside fenced code blocks', () => {
    const input = 'Prose cites [1].\n\n```python\nvalue = arr[1]\n```';
    const result = preprocessCitationMarkers(input, sources);
    expect(result).toContain('<citation data-num="1"');
    expect(result).toContain('value = arr[1]');
    expect(result).not.toMatch(/arr< citation/);
  });

  it('does not convert half-width markers inside inline code', () => {
    const input = 'Use `arr[1]` for indexing and cite [1] in prose.';
    const result = preprocessCitationMarkers(input, sources);
    expect(result).toContain('`arr[1]`');
    expect(result).toContain('<citation data-num="1"');
  });

  it('matches string index values from SSE payloads', () => {
    const stringIndexed = sources.map((source) => ({
      ...source,
      index: String(source.index) as unknown as number,
    }));
    const result = preprocessCitationMarkers('增长 5%【1】。', stringIndexed);
    expect(result).toContain('<citation data-num="1"');
  });

  it('falls back to positional index when source.index is missing', () => {
    const noIndexSources = sources.map(({ index: _index, ...rest }) => rest) as Source[];
    const result = preprocessCitationMarkers('增长 5%【1】。', noIndexSources);
    expect(result).toContain('<citation data-num="1"');
  });

  it('converts full-width digit markers 【１】', () => {
    const result = preprocessCitationMarkers('Python 3.14 新特性【１】。', sources);
    expect(result).toContain('<citation data-num="1"');
    expect(result).not.toContain('【１】');
  });
});

describe('maskCodeRegions', () => {
  it('round-trips fenced and inline code slots', () => {
    const original = 'Text\n```js\nconst x = arr[1];\n``` and `arr[2]` end';
    const { text, slots } = maskCodeRegions(original);
    expect(text).not.toContain('arr[1]');
    expect(unmaskCodeRegions(text, slots)).toBe(original);
  });
});
