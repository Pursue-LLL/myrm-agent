import { describe, expect, it } from 'vitest';
import type { Source } from '@/store/chat/types';
import { preprocessCitationMarkers } from './preprocessCitationMarkers';

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
});
