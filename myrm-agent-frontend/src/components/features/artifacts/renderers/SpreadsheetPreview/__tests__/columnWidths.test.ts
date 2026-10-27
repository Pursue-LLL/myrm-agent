import { describe, expect, it } from 'vitest';
import { computeColumnWidths } from '../columnWidths';

describe('computeColumnWidths', () => {
  it('gives a column the width of its longest cell, header included', () => {
    const [name, note] = computeColumnWidths(
      ['Name', 'A note that is long'],
      [
        ['Alexander the Great', 'ok'],
        ['Bo', 'ok'],
      ],
    );
    expect(name).toBeGreaterThan(computeColumnWidths(['Name'], [['Bo']])[0]);
    expect(note).toBeGreaterThan(computeColumnWidths(['n'], [['ok']])[0]);
  });

  it('keeps every width between a readable minimum and a maximum that leaves room for the next column', () => {
    const [tiny, huge] = computeColumnWidths(['a', 'b'], [['x', 'y'.repeat(5000)]]);
    expect(tiny).toBe(72);
    expect(huge).toBe(320);
  });

  it('gives wide characters more room than narrow ones', () => {
    const [latin, cjk] = computeColumnWidths(['a', 'b'], [['abcdefghij', '一二三四五六七八九十']]);
    expect(cjk).toBeGreaterThan(latin);
  });

  it('reserves room in the header for the sort arrow', () => {
    const [header] = computeColumnWidths(['Quarterly revenue'], [['1']]);
    const [body] = computeColumnWidths(['q'], [['Quarterly revenue']]);
    expect(header).toBeGreaterThan(body);
  });

  it('looks only at the first rows, so a huge file costs no more than a small one', () => {
    const rows = Array.from({ length: 1000 }, (_, index) => [index === 500 ? 'z'.repeat(200) : 'ab']);
    expect(computeColumnWidths(['h'], rows)).toEqual(computeColumnWidths(['h'], rows.slice(0, 200)));
  });

  it('copes with short rows and no columns', () => {
    expect(computeColumnWidths(['a', 'b'], [['only one cell']])).toHaveLength(2);
    expect(computeColumnWidths([], [['x']])).toEqual([]);
  });
});
