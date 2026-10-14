// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { tightenCounts } from '../ratchet-baseline.ts';

describe('tightenCounts', () => {
  it('lowers an entry to the current value when it improved', () => {
    expect(tightenCounts({ 'a.tsx': 2 }, { 'a.tsx': 5 })).toEqual({ 'a.tsx': 2 });
  });

  it('never raises an entry above the baseline', () => {
    expect(tightenCounts({ 'a.tsx': 9 }, { 'a.tsx': 5 })).toEqual({ 'a.tsx': 5 });
  });

  it('never adds an entry the baseline does not have', () => {
    expect(tightenCounts({ 'new.tsx': 3, 'a.tsx': 1 }, { 'a.tsx': 1 })).toEqual({ 'a.tsx': 1 });
  });

  it('drops entries that reached zero or no longer exist', () => {
    expect(tightenCounts({ 'zero.tsx': 0 }, { 'zero.tsx': 4, 'gone.tsx': 2 })).toEqual({});
  });

  it('keeps the baseline entry order so the written diff stays minimal', () => {
    const result = tightenCounts({ b: 1, a: 1, c: 1 }, { b: 2, a: 2, c: 2 });
    expect(Object.keys(result)).toEqual(['b', 'a', 'c']);
  });

  it('returns an equal map when nothing improved', () => {
    const baseline = { 'a.tsx': 3, 'b.tsx': 1 };
    expect(tightenCounts({ 'a.tsx': 3, 'b.tsx': 4 }, baseline)).toEqual(baseline);
  });

  it('does not mutate its inputs', () => {
    const current = { 'a.tsx': 1 };
    const baseline = { 'a.tsx': 2 };
    tightenCounts(current, baseline);
    expect(current).toEqual({ 'a.tsx': 1 });
    expect(baseline).toEqual({ 'a.tsx': 2 });
  });
});
