import { describe, expect, it } from 'vitest';
import type { Source } from '@/store/chat/types';
import { buildCitationSources } from '../buildCitationSources';

function page(index: number, name: string): Source {
  return { index, type: 'web_search', title: name, url: `https://${name}.example/page` };
}

const titles = (sources: Source[]): string[] => sources.map((source) => `${source.index}:${source.title}`);

describe('buildCitationSources', () => {
  it('orders the own sources by number when no message came before', () => {
    expect(titles(buildCitationSources([], [page(3, 'c'), page(1, 'a'), page(2, 'b')]))).toEqual(['1:a', '2:b', '3:c']);
  });

  it('adds the pages an earlier turn found next to the own ones', () => {
    const earlier = [{ sources: [page(1, 'a'), page(2, 'b')] }];

    expect(titles(buildCitationSources(earlier, [page(3, 'c')]))).toEqual(['1:a', '2:b', '3:c']);
  });

  it('lets a number of the message itself win over the same number of an earlier message', () => {
    const earlier = [{ sources: [page(1, 'earlier-one'), page(2, 'earlier-two')] }];

    expect(titles(buildCitationSources(earlier, [page(1, 'own-one')]))).toEqual(['1:own-one', '2:earlier-two']);
  });

  it('gives a number to the nearest earlier message that has it', () => {
    const earlier = [{ sources: [page(2, 'far')] }, { sources: [page(1, 'other')] }, { sources: [page(2, 'near')] }];

    expect(titles(buildCitationSources(earlier, []))).toEqual(['1:other', '2:near']);
  });

  it('reads messages that carry no sources as empty', () => {
    const earlier = [{}, { sources: undefined }, { sources: [page(1, 'a')] }, {}];

    expect(titles(buildCitationSources(earlier, []))).toEqual(['1:a']);
  });

  it('skips an earlier source that carries no usable number', () => {
    const unusable = [0, -2, Number.NaN, undefined, 'seven'].map(
      (index) => ({ ...page(9, 'unusable'), index }) as unknown as Source,
    );

    expect(titles(buildCitationSources([{ sources: [...unusable, page(4, 'kept')] }], []))).toEqual(['4:kept']);
  });

  it('reads a number that came as a string from the SSE payload', () => {
    const fromPayload = { ...page(0, 'payload'), index: '3' } as unknown as Source;

    const [source] = buildCitationSources([{ sources: [fromPayload] }], []);

    expect(source.index).toBe(3);
  });

  it('numbers an own source that came without a number after the highest number of the message', () => {
    const unnumbered = { type: 'web_search', title: 'unnumbered', url: 'https://unnumbered.example/page' } as Source;

    expect(titles(buildCitationSources([{ sources: [page(2, 'earlier')] }], [page(1, 'a'), unnumbered]))).toEqual([
      '1:a',
      '2:unnumbered',
    ]);
  });

  it('leaves the sources it was given as they were', () => {
    const own = [page(2, 'own')];
    const earlierSources = [page(1, 'earlier')];
    const snapshot = JSON.stringify([own, earlierSources]);

    buildCitationSources([{ sources: earlierSources }], own);

    expect(JSON.stringify([own, earlierSources])).toBe(snapshot);
  });
});
