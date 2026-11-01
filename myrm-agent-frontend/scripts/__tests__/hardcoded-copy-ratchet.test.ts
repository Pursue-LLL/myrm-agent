// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { diffAgainstBaseline, partitionByReachability } from '../hardcoded-copy-ratchet';

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

describe('partitionByReachability', () => {
  const sitesByFile = new Map([
    ['src/live/Panel.tsx', ['a', 'b']],
    ['src/dead/Studio.tsx', ['c']],
  ]);

  it('keeps reachable files in scope and sets orphan files aside with their literals intact', () => {
    const { reachable, orphaned } = partitionByReachability(sitesByFile, new Set(['src/dead/Studio.tsx']));

    expect([...reachable]).toEqual([['src/live/Panel.tsx', ['a', 'b']]]);
    expect([...orphaned]).toEqual([['src/dead/Studio.tsx', ['c']]]);
  });

  it('puts every file in scope when nothing is an orphan, so an unmounted file cannot hide by accident', () => {
    const { reachable, orphaned } = partitionByReachability(sitesByFile, new Set());

    expect([...reachable.keys()]).toEqual(['src/live/Panel.tsx', 'src/dead/Studio.tsx']);
    expect(orphaned.size).toBe(0);
  });

  it('makes a file count as a new offender once it stops being an orphan', () => {
    const asOrphan = partitionByReachability(sitesByFile, new Set(['src/dead/Studio.tsx'])).reachable;
    const mounted = partitionByReachability(sitesByFile, new Set()).reachable;
    const counts = (m: Map<string, string[]>) => Object.fromEntries([...m].map(([f, s]) => [f, s.length]));

    expect(diffAgainstBaseline(counts(asOrphan), { 'src/live/Panel.tsx': 2 })).toEqual({ increased: [], drifted: [] });
    expect(diffAgainstBaseline(counts(mounted), { 'src/live/Panel.tsx': 2 })).toEqual({
      increased: ['src/dead/Studio.tsx'],
      drifted: [],
    });
  });
});
