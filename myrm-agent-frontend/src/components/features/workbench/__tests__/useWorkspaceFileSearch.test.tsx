/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { WorkspaceFileSearchResponse, WorkspaceFileSearchResult } from '@/services/chat';
import { useWorkspaceFileSearch } from '../tabs/useWorkspaceFileSearch';

const WORKSPACE = '/vault/chat-1';
const OTHER_WORKSPACE = '/vault/chat-2';

const searchWorkspaceFilesMock = vi.fn<(workspace: string, query: string) => Promise<WorkspaceFileSearchResponse>>();

vi.mock('@/services/chat', () => ({
  searchWorkspaceFiles: (workspace: string, query: string) => searchWorkspaceFilesMock(workspace, query),
}));

const match = (name: string, workspace: string = WORKSPACE): WorkspaceFileSearchResult => ({
  name,
  path: `${workspace}/${name}`,
  relative_path: name,
  size: 1,
});

const answer = (...names: string[]): WorkspaceFileSearchResponse => ({
  results: names.map((name) => match(name)),
  total: names.length,
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Lets the debounce elapse and any answered request settle. */
const settle = () =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });

describe('useWorkspaceFileSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('stays idle without a workspace or with a blank query', async () => {
    const none = renderHook(() => useWorkspaceFileSearch(null, 'hello'));
    const blank = renderHook(() => useWorkspaceFileSearch(WORKSPACE, '   '));
    await settle();

    expect(none.result.current).toEqual({ status: 'idle', results: [] });
    expect(blank.result.current).toEqual({ status: 'idle', results: [] });
    expect(searchWorkspaceFilesMock).not.toHaveBeenCalled();
  });

  it('searches the trimmed query once typing pauses and reports the matches', async () => {
    searchWorkspaceFilesMock.mockResolvedValue(answer('Hello.ts'));
    const { result } = renderHook(() => useWorkspaceFileSearch(WORKSPACE, '  hello '));

    expect(result.current.status).toBe('searching');
    expect(searchWorkspaceFilesMock).not.toHaveBeenCalled();
    await settle();

    expect(searchWorkspaceFilesMock).toHaveBeenCalledWith(WORKSPACE, 'hello');
    expect(result.current).toEqual({ status: 'done', results: answer('Hello.ts').results });
  });

  it('keeps the previous matches on screen while a newer query is searching', async () => {
    searchWorkspaceFilesMock.mockResolvedValueOnce(answer('Hello.ts'));
    const { result, rerender } = renderHook(({ query }) => useWorkspaceFileSearch(WORKSPACE, query), {
      initialProps: { query: 'hel' },
    });
    await settle();

    rerender({ query: 'hello' });

    expect(result.current.status).toBe('searching');
    expect(result.current.results).toEqual(answer('Hello.ts').results);
  });

  it('drops the answer of an older query that arrives after a newer one', async () => {
    const slowFirst = deferred<WorkspaceFileSearchResponse>();
    searchWorkspaceFilesMock.mockReturnValueOnce(slowFirst.promise).mockResolvedValueOnce(answer('Newer.ts'));
    const { result, rerender } = renderHook(({ query }) => useWorkspaceFileSearch(WORKSPACE, query), {
      initialProps: { query: 'old' },
    });
    await settle();

    rerender({ query: 'new' });
    await settle();
    expect(result.current).toEqual({ status: 'done', results: answer('Newer.ts').results });

    await act(async () => {
      slowFirst.resolve(answer('Older.ts'));
    });

    expect(result.current).toEqual({ status: 'done', results: answer('Newer.ts').results });
  });

  it('does not show the matches of another workspace while its own search runs', async () => {
    searchWorkspaceFilesMock.mockResolvedValueOnce(answer('Hello.ts'));
    const { result, rerender } = renderHook(({ workspace }) => useWorkspaceFileSearch(workspace, 'hello'), {
      initialProps: { workspace: WORKSPACE },
    });
    await settle();

    rerender({ workspace: OTHER_WORKSPACE });

    expect(result.current).toEqual({ status: 'searching', results: [] });
  });

  it('reports a failed search without matches', async () => {
    searchWorkspaceFilesMock.mockRejectedValue(new Error('ECONNREFUSED'));
    const { result } = renderHook(() => useWorkspaceFileSearch(WORKSPACE, 'hello'));

    await settle();

    expect(result.current).toEqual({ status: 'failed', results: [] });
  });

  it('returns to idle when the query is cleared', async () => {
    searchWorkspaceFilesMock.mockResolvedValue(answer('Hello.ts'));
    const { result, rerender } = renderHook(({ query }) => useWorkspaceFileSearch(WORKSPACE, query), {
      initialProps: { query: 'hello' },
    });
    await settle();

    rerender({ query: '' });

    expect(result.current).toEqual({ status: 'idle', results: [] });
  });
});
