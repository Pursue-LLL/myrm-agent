// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { diffAgainstBaseline } from '../hardcoded-copy-ratchet';

describe('diffAgainstBaseline', () => {
  it('reports nothing when every file matches its baseline', () => {
    expect(diffAgainstBaseline({ 'a.tsx': 2, 'b.tsx': 1 }, { 'a.tsx': 2, 'b.tsx': 1 })).toEqual({
      increased: [],
      drifted: [],
    });
  });

  it('flags a file whose count rose above the baseline', () => {
    expect(diffAgainstBaseline({ 'a.tsx': 3 }, { 'a.tsx': 2 })).toEqual({ increased: ['a.tsx'], drifted: [] });
  });

  it('treats a file missing from the baseline as starting at zero', () => {
    expect(diffAgainstBaseline({ 'a.tsx': 1, 'new.tsx': 1 }, { 'a.tsx': 1 })).toEqual({
      increased: ['new.tsx'],
      drifted: [],
    });
  });

  it('flags drift when a count fell below the baseline', () => {
    expect(diffAgainstBaseline({ 'a.tsx': 1 }, { 'a.tsx': 2 })).toEqual({ increased: [], drifted: ['a.tsx'] });
  });

  it('treats a deleted or renamed file as drift so its freed quota cannot be reused silently', () => {
    expect(diffAgainstBaseline({ 'renamed.tsx': 2 }, { 'old.tsx': 2 })).toEqual({
      increased: ['renamed.tsx'],
      drifted: ['old.tsx'],
    });
  });

  it('compares per file: cleaning one file does not offset a new literal in another', () => {
    expect(diffAgainstBaseline({ 'clean.tsx': 0, 'dirty.tsx': 4 }, { 'clean.tsx': 3, 'dirty.tsx': 3 })).toEqual({
      increased: ['dirty.tsx'],
      drifted: ['clean.tsx'],
    });
  });

  it('returns files in sorted order regardless of input order', () => {
    expect(diffAgainstBaseline({ 'z.tsx': 1, 'a.tsx': 1, 'm.tsx': 1 }, {}).increased).toEqual([
      'a.tsx',
      'm.tsx',
      'z.tsx',
    ]);
  });
});
