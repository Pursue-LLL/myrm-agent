/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry, FileTreeResult } from '@/services/chat';
import { useWorkspaceFiles } from '../useWorkspaceFiles';

const WORKSPACE = '/vault/chat-1';
const OTHER_WORKSPACE = '/vault/chat-2';
const SRC = `${WORKSPACE}/src`;
const DEEP = `${SRC}/deep`;
const INNER = `${DEEP}/inner`;
const MORE = `${INNER}/more`;

const browseWorkspaceFilesMock = vi.fn<(path: string, depth?: number) => Promise<FileTreeResult>>();

vi.mock('@/services/chat', () => ({
  browseWorkspaceFiles: (path: string, depth?: number) => browseWorkspaceFilesMock(path, depth),
  registerWorkspaceWatch: async (workspace: string) => ({ workspace }),
  unregisterWorkspaceWatch: async (workspace: string) => ({ workspace }),
}));

const file = (path: string): FileEntry => ({
  name: path.split('/').pop() ?? path,
  path,
  type: 'file',
  size: 1,
  mtime: null,
  is_text: true,
  children: null,
});

const dir = (path: string, children: FileEntry[] | null): FileEntry => ({
  name: path.split('/').pop() ?? path,
  path,
  type: 'directory',
  size: null,
  mtime: null,
  is_text: null,
  children,
});

const scan = (root: string, entries: FileEntry[], truncated = false): FileTreeResult => ({ root, entries, truncated });

// A two-level scan: `deep` sits on the last scanned level, so it comes back without its children.
const ROOT_SCAN = scan(WORKSPACE, [file(`${WORKSPACE}/README.md`), dir(SRC, [file(`${SRC}/app.ts`), dir(DEEP, null)])]);
const DEEP_SCAN = scan(DEEP, [file(`${DEEP}/mod.ts`), dir(INNER, [dir(MORE, null)])]);
const MORE_SCAN = scan(MORE, [file(`${MORE}/leaf.ts`)]);

/** Answers each path from `answers`; any other path rejects like an unreadable folder. */
function serve(answers: Record<string, FileTreeResult>): void {
  browseWorkspaceFilesMock.mockImplementation(async (path) => {
    const answer = answers[path];
    if (!answer) {
      throw new Error(`cannot read ${path}`);
    }
    return answer;
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/** The children of `src` (index 1 of the root scan) and what `deep` holds inside it. */
const deepChildrenOf = (files: FileEntry[]): FileEntry[] | null => files[1].children?.[1].children ?? null;

async function mountLoaded(answers: Record<string, FileTreeResult> = { [WORKSPACE]: ROOT_SCAN }) {
  serve(answers);
  const hook = renderHook(() => useWorkspaceFiles(WORKSPACE));
  await waitFor(() => expect(hook.result.current.files).toEqual(ROOT_SCAN.entries));
  return hook;
}

describe('useWorkspaceFiles', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('scans the first two levels of the workspace', async () => {
    await mountLoaded();

    expect(browseWorkspaceFilesMock).toHaveBeenCalledWith(WORKSPACE, 2);
  });

  it('does not scan without a workspace or while disabled', () => {
    const none = renderHook(() => useWorkspaceFiles(null));
    const disabled = renderHook(() => useWorkspaceFiles(WORKSPACE, false));

    expect(browseWorkspaceFilesMock).not.toHaveBeenCalled();
    expect(none.result.current.files).toEqual([]);
    expect(disabled.result.current.files).toEqual([]);
  });

  it('reports the failure of the workspace scan', async () => {
    serve({});

    const { result } = renderHook(() => useWorkspaceFiles(WORKSPACE));

    await waitFor(() => expect(result.current.error).toBe(`cannot read ${WORKSPACE}`));
    expect(result.current.loading).toBe(false);
  });

  it('fills a folder the scan did not reach when it is loaded, leaving other branches untouched', async () => {
    const { result } = await mountLoaded({ [WORKSPACE]: ROOT_SCAN, [DEEP]: DEEP_SCAN });
    const readme = result.current.files[0];

    await act(async () => {
      await result.current.loadChildren(DEEP);
    });

    expect(deepChildrenOf(result.current.files)).toEqual(DEEP_SCAN.entries);
    expect(result.current.files[0]).toBe(readme);
    expect(browseWorkspaceFilesMock).toHaveBeenCalledWith(DEEP, 2);
  });

  it('rejects when the folder cannot be read and leaves the tree alone', async () => {
    const { result } = await mountLoaded();
    const before = result.current.files;

    await act(async () => {
      await expect(result.current.loadChildren(DEEP)).rejects.toThrow(`cannot read ${DEEP}`);
    });

    expect(result.current.files).toBe(before);
  });

  it('keeps the loaded folders, rescanned, when the workspace is scanned again', async () => {
    const { result } = await mountLoaded({ [WORKSPACE]: ROOT_SCAN, [DEEP]: DEEP_SCAN });
    await act(async () => {
      await result.current.loadChildren(DEEP);
    });
    const changedDeep = scan(DEEP, [file(`${DEEP}/mod.ts`), file(`${DEEP}/fresh.ts`)]);
    const changedRoot = scan(WORKSPACE, [...ROOT_SCAN.entries, file(`${WORKSPACE}/new.txt`)]);
    serve({ [WORKSPACE]: changedRoot, [DEEP]: changedDeep });

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.files.map((entry) => entry.name)).toEqual(['README.md', 'src', 'new.txt']);
    expect(deepChildrenOf(result.current.files)).toEqual(changedDeep.entries);
  });

  it('restores nested loaded folders, parents first, whatever order they were loaded in', async () => {
    const answers = { [WORKSPACE]: ROOT_SCAN, [DEEP]: DEEP_SCAN, [MORE]: MORE_SCAN };
    const { result } = await mountLoaded(answers);
    const loadChildren = async (path: string) => {
      await act(async () => {
        await result.current.loadChildren(path);
      });
    };
    const refresh = async () => {
      await act(async () => {
        await result.current.refresh();
      });
    };
    await loadChildren(DEEP);
    await loadChildren(MORE);
    // `deep` is unreadable for one scan and is loaded again afterwards, so it now follows `more` in load order.
    serve({ [WORKSPACE]: ROOT_SCAN, [MORE]: MORE_SCAN });
    await refresh();
    serve(answers);
    await loadChildren(DEEP);

    await refresh();

    const inner = deepChildrenOf(result.current.files)?.[1];
    expect(inner?.children?.[0].children).toEqual(MORE_SCAN.entries);
  });

  it('forgets a loaded folder that can no longer be read without failing the scan', async () => {
    const { result } = await mountLoaded({ [WORKSPACE]: ROOT_SCAN, [DEEP]: DEEP_SCAN });
    await act(async () => {
      await result.current.loadChildren(DEEP);
    });
    serve({ [WORKSPACE]: ROOT_SCAN });

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.error).toBeNull();
    expect(deepChildrenOf(result.current.files)).toBeNull();
  });

  it('keeps the truncation notice of a loaded folder across a rescan', async () => {
    const truncatedDeep = scan(DEEP, DEEP_SCAN.entries, true);
    const { result } = await mountLoaded({ [WORKSPACE]: ROOT_SCAN, [DEEP]: truncatedDeep });
    expect(result.current.truncated).toBe(false);

    await act(async () => {
      await result.current.loadChildren(DEEP);
    });
    expect(result.current.truncated).toBe(true);

    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.truncated).toBe(true);

    serve({ [WORKSPACE]: ROOT_SCAN, [DEEP]: DEEP_SCAN });
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.truncated).toBe(false);
  });

  it('drops the answer for a folder when the workspace changed while it loaded', async () => {
    const otherScan = scan(OTHER_WORKSPACE, [file(`${OTHER_WORKSPACE}/notes.md`)]);
    const slowDeep = deferred<FileTreeResult>();
    const truncatedDeep = scan(DEEP, DEEP_SCAN.entries, true);
    browseWorkspaceFilesMock.mockImplementation(async (path) => {
      if (path === DEEP) {
        return slowDeep.promise;
      }
      return path === OTHER_WORKSPACE ? otherScan : ROOT_SCAN;
    });
    const { result, rerender } = renderHook(({ workspace }) => useWorkspaceFiles(workspace), {
      initialProps: { workspace: WORKSPACE },
    });
    await waitFor(() => expect(result.current.files).toEqual(ROOT_SCAN.entries));
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.loadChildren(DEEP);
    });

    rerender({ workspace: OTHER_WORKSPACE });
    await waitFor(() => expect(result.current.files).toEqual(otherScan.entries));
    await act(async () => {
      slowDeep.resolve(truncatedDeep);
      await pending;
    });
    expect(result.current.truncated).toBe(false);
    await act(async () => {
      await result.current.refresh();
    });

    // The late folder belongs to the previous workspace, so the new one never re-reads it.
    expect(browseWorkspaceFilesMock.mock.calls.filter(([path]) => path === DEEP)).toHaveLength(1);
    expect(result.current.files).toEqual(otherScan.entries);
  });

  it('drops the answer of an older scan that arrives after a newer one', async () => {
    const olderRoot = scan(WORKSPACE, [file(`${WORKSPACE}/old.txt`)]);
    const newerRoot = scan(WORKSPACE, [file(`${WORKSPACE}/new.txt`)]);
    const slowFirst = deferred<FileTreeResult>();
    let scans = 0;
    browseWorkspaceFilesMock.mockImplementation(async () => {
      scans += 1;
      return scans === 1 ? slowFirst.promise : newerRoot;
    });
    const { result } = renderHook(() => useWorkspaceFiles(WORKSPACE));

    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.files).toEqual(newerRoot.entries);
    expect(result.current.loading).toBe(false);

    await act(async () => {
      slowFirst.resolve(olderRoot);
    });

    expect(result.current.files).toEqual(newerRoot.entries);
    expect(result.current.loading).toBe(false);
  });
});
