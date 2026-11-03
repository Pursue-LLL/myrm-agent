import { describe, expect, it } from 'vitest';

import { columnLabel } from '../columnLabel';

describe('columnLabel', () => {
  it.each([
    [0, 'A'],
    [1, 'B'],
    [25, 'Z'],
    [26, 'AA'],
    [27, 'AB'],
    [51, 'AZ'],
    [52, 'BA'],
    [701, 'ZZ'],
    [702, 'AAA'],
  ])('labels column index %i as %s', (index, label) => {
    expect(columnLabel(index)).toBe(label);
  });
});
