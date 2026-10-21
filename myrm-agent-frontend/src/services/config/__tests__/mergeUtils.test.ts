import { describe, expect, it } from 'vitest';
import { threeWayMerge } from '@/services/config/mergeUtils';

describe('threeWayMerge', () => {
  it('merges additive server fields when base is missing', () => {
    const local = { a: 1 };
    const server = { a: 1, b: 2 };
    const result = threeWayMerge(null, local, server);
    expect(result.hasConflict).toBe(false);
    expect(result.merged).toEqual({ a: 1, b: 2 });
  });

  it('flags same-field divergence', () => {
    const base = { a: 1 };
    const local = { a: 2 };
    const server = { a: 3 };
    const result = threeWayMerge(base, local, server);
    expect(result.hasConflict).toBe(true);
  });

  it('auto-merges independent field edits', () => {
    const base = { a: 1, b: 1 };
    const local = { a: 2, b: 1 };
    const server = { a: 1, b: 3 };
    const result = threeWayMerge(base, local, server);
    expect(result.hasConflict).toBe(false);
    expect(result.merged).toEqual({ a: 2, b: 3 });
  });
});
