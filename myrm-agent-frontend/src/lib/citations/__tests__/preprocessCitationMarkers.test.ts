import { describe, expect, it } from 'vitest';
import type { Source } from '@/store/chat/types';
import { maskCodeRegions, unmaskCodeRegions } from '../maskCodeRegions';
import {
  preprocessCitationMarkers,
  stripUnsupportedCitationControlMarkers,
} from '../preprocessCitationMarkers';

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
  {
    index: 3,
    type: 'web_search',
    title: 'Doc C',
    url: 'https://example.org/doc-c',
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

  it('converts composite citations with commas 【1, 2】 and [1, 2]', () => {
    const resultZh = preprocessCitationMarkers('两者均采用新架构【1, 2】。', sources);
    expect(resultZh).toContain('<citation data-num="1"');
    expect(resultZh).toContain('<citation data-num="2"');
    expect(resultZh).not.toContain('【1, 2】');

    const resultEn = preprocessCitationMarkers('Both use new architecture [1, 2].', sources);
    expect(resultEn).toContain('<citation data-num="1"');
    expect(resultEn).toContain('<citation data-num="2"');
    expect(resultEn).not.toContain('[1, 2]');
  });

  it('converts full-width comma and enumeration comma 【1，2】 and 【1、2】', () => {
    const resultChineseComma = preprocessCitationMarkers('数据支持【1，2】。', sources);
    expect(resultChineseComma).toContain('<citation data-num="1"');
    expect(resultChineseComma).toContain('<citation data-num="2"');

    const resultDunHao = preprocessCitationMarkers('数据支持【1、2】。', sources);
    expect(resultDunHao).toContain('<citation data-num="1"');
    expect(resultDunHao).toContain('<citation data-num="2"');
  });

  it('expands range citations [1-3] and 【1-3】', () => {
    const result = preprocessCitationMarkers('多篇论文支持该结论 [1-3]。', sources);
    expect(result).toContain('<citation data-num="1"');
    expect(result).toContain('<citation data-num="2"');
    expect(result).toContain('<citation data-num="3"');
    expect(result).not.toContain('[1-3]');
  });

  it('converts variant brackets ［1］ and 〔1〕', () => {
    const resultSquare = preprocessCitationMarkers('全角方括号［1］。', sources);
    expect(resultSquare).toContain('<citation data-num="1"');

    const resultHex = preprocessCitationMarkers('六角括号〔1〕。', sources);
    expect(resultHex).toContain('<citation data-num="1"');
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

    const resultComposite = preprocessCitationMarkers('Unknown [9, 10].', sources);
    expect(resultComposite).toBe('Unknown [9, 10].');
  });

  it('does not convert markers inside fenced code blocks', () => {
    const input = 'Prose cites 【1, 2】。\n\n```python\n# example marker 【1, 2】\narr = [1, 2]\n```';
    const result = preprocessCitationMarkers(input, sources);
    expect(result).toContain('<citation data-num="1"');
    expect(result).toContain('<citation data-num="2"');
    expect(result).toContain('# example marker 【1, 2】');
    expect(result).toContain('arr = [1, 2]');
    expect(result).not.toMatch(/arr = <citation/);
  });

  it('does not convert half-width markers inside inline code', () => {
    const input = 'Use `arr[1, 2]` for indexing and cite [1] in prose.';
    const result = preprocessCitationMarkers(input, sources);
    expect(result).toContain('`arr[1, 2]`');
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

  it('converts full-width digit markers 【１】 and 【１，２】', () => {
    const result = preprocessCitationMarkers('Python 3.14 新特性【１】。', sources);
    expect(result).toContain('<citation data-num="1"');
    expect(result).not.toContain('【１】');

    const resultFwComposite = preprocessCitationMarkers('Python 3.14 新特性【１，２】。', sources);
    expect(resultFwComposite).toContain('<citation data-num="1"');
    expect(resultFwComposite).toContain('<citation data-num="2"');
  });

  it('strips unsupported private Unicode citation control tokens', () => {
    const rawWithControl = 'Search answer.\uE200cite\uE202turn0search1\uE201 [1] \uE200cite\uE201';
    const cleaned = stripUnsupportedCitationControlMarkers(rawWithControl);
    expect(cleaned).toBe('Search answer. [1]');

    const rendered = preprocessCitationMarkers(rawWithControl, sources);
    expect(rendered).toContain('<citation data-num="1"');
    expect(rendered).not.toContain('\uE200');
    expect(rendered).not.toContain('\uE201');
  });
});

describe('maskCodeRegions', () => {
  it('round-trips fenced and inline code slots', () => {
    const original = 'Text\n```js\nconst x = arr[1, 2];\n``` and `arr[2]` end';
    const { text, slots } = maskCodeRegions(original);
    expect(text).not.toContain('arr[1, 2]');
    expect(unmaskCodeRegions(text, slots)).toBe(original);
  });
});
