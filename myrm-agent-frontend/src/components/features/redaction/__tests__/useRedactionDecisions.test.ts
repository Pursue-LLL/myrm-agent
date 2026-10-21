import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { RedactionResponse } from '@/services/skill';

import { hasKeptFindings, keepEveryFinding, useRedactionDecisions } from '../useRedactionDecisions';

function finding(line: number): RedactionResponse {
  return { line_number: line, original: `secret-${line}`, redacted: '<REDACTED>', kinds: ['api_token'] };
}

describe('keepEveryFinding', () => {
  it('keeps every index of every file', () => {
    expect(keepEveryFinding({ 'a.md': [finding(1), finding(2)], 'b.md': [finding(7)] })).toEqual({
      'a.md': [0, 1],
      'b.md': [0],
    });
  });

  it('is empty when there is nothing to review', () => {
    expect(keepEveryFinding({})).toEqual({});
  });
});

describe('hasKeptFindings', () => {
  it('is false for no decisions and for files with nothing kept', () => {
    expect(hasKeptFindings({})).toBe(false);
    expect(hasKeptFindings({ 'a.md': [] })).toBe(false);
  });

  it('is true as soon as one finding is kept', () => {
    expect(hasKeptFindings({ 'a.md': [], 'b.md': [3] })).toBe(true);
  });
});

describe('useRedactionDecisions', () => {
  it('starts by redacting everything', () => {
    const { result } = renderHook(() => useRedactionDecisions());

    expect(result.current.ignored).toEqual({});
  });

  it('toggles a single finding between kept and redacted', () => {
    const { result } = renderHook(() => useRedactionDecisions());

    act(() => result.current.toggle('a.md', 1));
    expect(result.current.ignored).toEqual({ 'a.md': [1] });

    act(() => result.current.toggle('a.md', 2));
    expect(result.current.ignored).toEqual({ 'a.md': [1, 2] });

    act(() => result.current.toggle('a.md', 1));
    expect(result.current.ignored).toEqual({ 'a.md': [2] });
  });

  it('keeps all findings of a file when none is kept, and redacts them again otherwise', () => {
    const { result } = renderHook(() => useRedactionDecisions());

    act(() => result.current.toggleAll('a.md', 3));
    expect(result.current.ignored).toEqual({ 'a.md': [0, 1, 2] });

    act(() => result.current.toggleAll('a.md', 3));
    expect(result.current.ignored).toEqual({ 'a.md': [] });

    // A partially kept file is redacted again rather than extended.
    act(() => result.current.toggle('a.md', 1));
    act(() => result.current.toggleAll('a.md', 3));
    expect(result.current.ignored).toEqual({ 'a.md': [] });
  });

  it('forgets decisions when the preview is reloaded', () => {
    const { result } = renderHook(() => useRedactionDecisions());
    act(() => result.current.toggle('a.md', 0));

    act(() => result.current.reset());

    expect(result.current.ignored).toEqual({});
  });
});
