/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkspaceTextError } from '@/services/workspaceText';
import {
  A,
  B,
  deferred,
  openEditor,
  readMock,
  refreshMock,
  resetEditorTest,
  saveMock,
  snapshot,
  toastError,
  toastSuccess,
  type,
  WORKSPACE,
  written,
} from './editorTestKit';
import { FILE_CHANGE_WINDOW_MS } from '../useWorkspaceFileChanged';
import { useWorkspaceTextEditor } from '../useWorkspaceTextEditor';

const stableT = (key: string, values?: Record<string, string>) => (values ? `${key}:${values.name}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/services/workspaceText', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/workspaceText')>()),
  readWorkspaceText: vi.fn(),
  readWorkspaceTextIfChanged: vi.fn(),
  saveWorkspaceText: vi.fn(),
  saveWorkspaceTextCopy: vi.fn(),
}));

const announce = () =>
  window.dispatchEvent(new CustomEvent('workspace-file-changed', { detail: { workspace_path: WORKSPACE } }));

/** One change on disk, and the time the editor waits before it looks. */
async function fileChanges(): Promise<void> {
  announce();
  await act(async () => {
    vi.advanceTimersByTime(FILE_CHANGE_WINDOW_MS);
  });
}

/** An editor that is ready and has been given fake timers, so the window can be stepped through. */
async function openWithClock(initial = 'hello') {
  const hook = await openEditor(initial);
  vi.useFakeTimers();
  return hook;
}

beforeEach(resetEditorTest);

afterEach(() => {
  vi.useRealTimers();
});

describe('an open file that is rewritten on disk', () => {
  it('shows the new text at once when nothing was typed, without a toast or a question', async () => {
    const { result } = await openWithClock('hello');
    refreshMock.mockResolvedValue(snapshot('hello from the agent', { version: 'v2' }));

    await fileChanges();

    expect(refreshMock).toHaveBeenCalledWith(WORKSPACE, A, 'v1');
    expect(result.current.snapshot?.content).toBe('hello from the agent');
    expect(result.current.draft).toBe('hello from the agent');
    expect(result.current.snapshot?.version).toBe('v2');
    expect([result.current.dirty, result.current.conflict]).toEqual([false, false]);
    expect(toastError).not.toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('leaves everything as it is while the file is unchanged', async () => {
    const { result } = await openWithClock('hello');
    refreshMock.mockResolvedValue(null);
    const before = result.current.snapshot;

    await fileChanges();

    expect(refreshMock).toHaveBeenCalledTimes(1);
    expect(result.current.snapshot).toBe(before);
  });

  it('keeps what the user typed and raises the conflict, whose overwrite saves against the newer version', async () => {
    const hook = await openWithClock('hello');
    const { result } = hook;
    type(hook, 'my edit');
    refreshMock.mockResolvedValue(snapshot('agent text', { version: 'v2' }));

    await fileChanges();

    expect(result.current.draft).toBe('my edit');
    expect(result.current.snapshot?.content).toBe('hello');
    expect([result.current.dirty, result.current.conflict]).toEqual([true, true]);

    saveMock.mockResolvedValue(written('v3'));
    await act(() => result.current.overwrite());
    expect(saveMock).toHaveBeenCalledWith(WORKSPACE, A, 'my edit', 'v2');
  });

  it('takes the newest version when the file changes again under an unanswered conflict', async () => {
    const hook = await openWithClock('hello');
    const { result } = hook;
    type(hook, 'my edit');
    refreshMock.mockResolvedValueOnce(snapshot('first', { version: 'v2' }));
    await fileChanges();
    refreshMock.mockResolvedValueOnce(snapshot('second', { version: 'v3' }));
    await fileChanges();

    saveMock.mockResolvedValue(written('v4'));
    await act(() => result.current.overwrite());

    expect(saveMock).toHaveBeenLastCalledWith(WORKSPACE, A, 'my edit', 'v3');
  });

  it('is no conflict when the user typed exactly what the file now holds', async () => {
    const hook = await openWithClock('hello');
    const { result } = hook;
    type(hook, 'same text');
    refreshMock.mockResolvedValue(snapshot('same text', { version: 'v2' }));

    await fileChanges();

    expect([result.current.dirty, result.current.conflict]).toEqual([false, false]);
    expect(result.current.snapshot?.version).toBe('v2');
  });

  it('asks again with the version of the first change after a second change', async () => {
    await openWithClock('hello');
    refreshMock.mockResolvedValueOnce(snapshot('one', { version: 'v2' })).mockResolvedValueOnce(null);

    await fileChanges();
    await fileChanges();

    expect(refreshMock.mock.calls.map((call) => call[2])).toEqual(['v1', 'v2']);
  });

  it('checks the file once for a burst of writes', async () => {
    await openWithClock('hello');
    refreshMock.mockResolvedValue(null);

    for (let i = 0; i < 30; i += 1) {
      announce();
    }
    await act(async () => {
      vi.advanceTimersByTime(FILE_CHANGE_WINDOW_MS);
    });

    expect(refreshMock).toHaveBeenCalledTimes(1);
  });
});

describe('the editor saving its own text', () => {
  it('finds the file unchanged afterwards, because it asks with the version it just saved', async () => {
    const hook = await openWithClock('hello');
    const { result } = hook;
    type(hook, 'saved text');
    saveMock.mockResolvedValue(written('v2'));
    await act(() => result.current.save());
    refreshMock.mockResolvedValue(null);

    await fileChanges();

    expect(refreshMock).toHaveBeenCalledWith(WORKSPACE, A, 'v2');
    expect(result.current.draft).toBe('saved text');
    expect(result.current.snapshot?.version).toBe('v2');
    expect([result.current.dirty, result.current.conflict]).toEqual([false, false]);
  });

  it('does not look while its own write is in flight, which would read as a foreign change', async () => {
    const hook = await openWithClock('hello');
    const { result } = hook;
    type(hook, 'saved text');
    const inFlight = deferred<ReturnType<typeof written>>();
    saveMock.mockReturnValue(inFlight.promise);
    let saving!: Promise<boolean>;
    act(() => {
      saving = result.current.save();
    });

    await fileChanges();

    expect(refreshMock).not.toHaveBeenCalled();
    inFlight.resolve(written('v2'));
    await act(async () => {
      await saving;
    });
    expect(result.current.conflict).toBe(false);
  });

  it('drops an answer that was overtaken by a save', async () => {
    const hook = await openWithClock('hello');
    const { result } = hook;
    const slow = deferred<ReturnType<typeof snapshot> | null>();
    refreshMock.mockReturnValue(slow.promise);
    await fileChanges();
    type(hook, 'saved text');
    saveMock.mockResolvedValue(written('v2'));
    await act(() => result.current.save());

    await act(async () => {
      slow.resolve(snapshot('an older read', { version: 'v1b' }));
    });

    expect(result.current.snapshot?.version).toBe('v2');
    expect(result.current.draft).toBe('saved text');
    expect(result.current.conflict).toBe(false);
  });
});

describe('a check that cannot be used', () => {
  it('is ignored when the file cannot be read now, and says nothing', async () => {
    const { result } = await openWithClock('hello');
    refreshMock.mockRejectedValue(new WorkspaceTextError('not_found'));

    await fileChanges();

    expect(result.current.snapshot?.content).toBe('hello');
    expect(result.current.phase).toBe('ready');
    expect(toastError).not.toHaveBeenCalled();
  });

  it('is dropped when the editor has moved to another file by the time it is answered', async () => {
    readMock.mockImplementation(async (_workspace, path) => snapshot(path === B ? 'file b' : 'file a', { path }));
    const hook = renderHook(({ path }) => useWorkspaceTextEditor(WORKSPACE, path, true), { initialProps: { path: A } });
    await waitFor(() => expect(hook.result.current.phase).toBe('ready'));
    vi.useFakeTimers();
    const slow = deferred<ReturnType<typeof snapshot> | null>();
    refreshMock.mockReturnValue(slow.promise);
    await fileChanges();

    hook.rerender({ path: B });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      slow.resolve(snapshot('a rewritten', { version: 'v9' }));
    });

    expect(hook.result.current.snapshot?.content).toBe('file b');
    expect(hook.result.current.snapshot?.version).toBe('v1');
  });

  it('is not made for a file too large to be versioned, which shows only its beginning', async () => {
    readMock.mockResolvedValue(snapshot('first megabyte', { version: '', truncated: true, editable: false }));
    const hook = renderHook(() => useWorkspaceTextEditor(WORKSPACE, A, true));
    await waitFor(() => expect(hook.result.current.phase).toBe('ready'));
    vi.useFakeTimers();

    await fileChanges();

    expect(refreshMock).not.toHaveBeenCalled();
  });

  it('is not made for a file that is not read as text, or before the first read has finished', async () => {
    const pending = deferred<ReturnType<typeof snapshot>>();
    readMock.mockReturnValue(pending.promise);
    vi.useFakeTimers();
    const loading = renderHook(() => useWorkspaceTextEditor(WORKSPACE, A, true));
    const idle = renderHook(() => useWorkspaceTextEditor(WORKSPACE, A, false));

    await fileChanges();

    expect(loading.result.current.phase).toBe('loading');
    expect(idle.result.current.phase).toBe('idle');
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it('stops with the editor: a change after it was closed is not looked at', async () => {
    const hook = await openWithClock('hello');
    announce();
    hook.unmount();

    await act(async () => {
      vi.advanceTimersByTime(FILE_CHANGE_WINDOW_MS * 2);
    });
    await fileChanges();

    expect(refreshMock).not.toHaveBeenCalled();
  });
});
