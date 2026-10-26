/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  readWorkspaceText,
  saveWorkspaceText,
  saveWorkspaceTextCopy,
  WorkspaceTextError,
  type WorkspaceTextFailureReason,
  type WorkspaceTextSnapshot,
} from '@/services/workspaceText';
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
  saveWorkspaceText: vi.fn(),
  saveWorkspaceTextCopy: vi.fn(),
}));

const WORKSPACE = '/ws';
const A = '/ws/a.txt';
const B = '/ws/b.txt';

const snapshot = (content: string, overrides: Partial<WorkspaceTextSnapshot> = {}): WorkspaceTextSnapshot => ({
  path: A,
  name: 'a.txt',
  content,
  version: 'v1',
  size: content.length,
  editable: true,
  readonlyReason: null,
  truncated: false,
  ...overrides,
});

const written = (version: string, name = 'a.txt') => ({ path: `/ws/${name}`, name, version, size: 1, changed: true });

const readMock = vi.mocked(readWorkspaceText);
const saveMock = vi.mocked(saveWorkspaceText);
const copyMock = vi.mocked(saveWorkspaceTextCopy);
const toastError = vi.mocked(toast.error);
const toastSuccess = vi.mocked(toast.success);

/** A promise the test settles by hand, to hold a request in flight. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function openEditor(initial = 'hello') {
  readMock.mockResolvedValue(snapshot(initial));
  const hook = renderHook(({ path, enabled }) => useWorkspaceTextEditor(WORKSPACE, path, enabled), {
    initialProps: { path: A, enabled: true },
  });
  await waitFor(() => expect(hook.result.current.phase).toBe('ready'));
  return hook;
}

const type = (hook: Awaited<ReturnType<typeof openEditor>>, value: string) =>
  act(() => hook.result.current.setDraft(value));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('reading and editing', () => {
  it('opens with a draft equal to what the file holds', async () => {
    const { result } = await openEditor('hello');

    expect(result.current).toMatchObject({ draft: 'hello', dirty: false, saving: false, conflict: false });
    expect(result.current.snapshot?.version).toBe('v1');
    expect(readMock).toHaveBeenCalledWith(WORKSPACE, A);
  });

  it('counts as edited only while the draft differs from the file, so typing the text back clears it', async () => {
    const hook = await openEditor('hello');

    type(hook, 'hello!');
    expect(hook.result.current.dirty).toBe(true);

    type(hook, 'hello');
    expect(hook.result.current.dirty).toBe(false);
  });

  it('discards the draft and goes back to what the file holds', async () => {
    const hook = await openEditor('hello');
    type(hook, 'something else');

    act(() => hook.result.current.discard());

    expect(hook.result.current).toMatchObject({ draft: 'hello', dirty: false });
  });

  it('reports a failed read without any wording from the server and without a toast', async () => {
    readMock.mockRejectedValue(new Error('Errno 13 /Users/me/.secret'));

    const { result } = renderHook(() => useWorkspaceTextEditor(WORKSPACE, A, true));

    await waitFor(() => expect(result.current.phase).toBe('failed'));
    expect(result.current.snapshot).toBeNull();
    expect(toastError).not.toHaveBeenCalled();
  });

  it('does not read files that are never edited as text', () => {
    const { result } = renderHook(() => useWorkspaceTextEditor(WORKSPACE, A, false));

    expect(result.current.phase).toBe('idle');
    expect(readMock).not.toHaveBeenCalled();
  });
});

describe('saving', () => {
  it('saves against the version that was read, then against the version the save returned', async () => {
    const hook = await openEditor('hello');
    saveMock.mockResolvedValueOnce(written('v2')).mockResolvedValueOnce(written('v3'));

    type(hook, 'hello!');
    await act(() => hook.result.current.save());
    expect(saveMock).toHaveBeenLastCalledWith(WORKSPACE, A, 'hello!', 'v1');
    expect(hook.result.current).toMatchObject({ dirty: false, saving: false });
    expect(hook.result.current.snapshot).toMatchObject({ content: 'hello!', version: 'v2' });
    expect(toastSuccess).toHaveBeenCalledWith('saveSuccess');

    type(hook, 'hello!!');
    await act(() => hook.result.current.save());
    expect(saveMock).toHaveBeenLastCalledWith(WORKSPACE, A, 'hello!!', 'v2');
    expect(hook.result.current.snapshot?.version).toBe('v3');
  });

  it('keeps text typed while the save is in flight, still counted as unsaved', async () => {
    const hook = await openEditor('hello');
    const inFlight = deferred<ReturnType<typeof written>>();
    saveMock.mockReturnValue(inFlight.promise);

    type(hook, 'hello!');
    let saving!: Promise<void>;
    act(() => {
      saving = hook.result.current.save();
    });
    expect(hook.result.current.saving).toBe(true);
    type(hook, 'hello!!');
    await act(async () => {
      inFlight.resolve(written('v2'));
      await saving;
    });

    expect(hook.result.current).toMatchObject({ draft: 'hello!!', dirty: true, saving: false });
    expect(hook.result.current.snapshot?.content).toBe('hello!');
  });

  it('sends nothing when nothing changed or when the editor may not change the file', async () => {
    const hook = await openEditor('hello');
    await act(() => hook.result.current.save());
    expect(saveMock).not.toHaveBeenCalled();

    readMock.mockResolvedValue(snapshot('locked', { editable: false, readonlyReason: 'not_utf8' }));
    const locked = renderHook(() => useWorkspaceTextEditor(WORKSPACE, B, true));
    await waitFor(() => expect(locked.result.current.phase).toBe('ready'));
    act(() => locked.result.current.setDraft('forced'));
    await act(() => locked.result.current.save());
    expect(saveMock).not.toHaveBeenCalled();
  });

  it('does not start a second save while one is running, even from a handler that has not seen a re-render yet', async () => {
    const hook = await openEditor('hello');
    const inFlight = deferred<ReturnType<typeof written>>();
    saveMock.mockReturnValue(inFlight.promise);
    type(hook, 'hello!');

    // Two key presses handled by the same, not yet re-rendered, closure.
    const { save } = hook.result.current;
    await act(async () => {
      void save();
      void save();
      inFlight.resolve(written('v2'));
    });

    expect(saveMock).toHaveBeenCalledTimes(1);
    expect(hook.result.current.conflict).toBe(false);
  });

  it('lets another file be saved while a save for the previous file is still running', async () => {
    const hook = await openEditor('hello');
    const slowA = deferred<ReturnType<typeof written>>();
    saveMock.mockReturnValueOnce(slowA.promise).mockResolvedValueOnce(written('b2', 'b.txt'));
    type(hook, 'hello!');
    act(() => {
      void hook.result.current.save();
    });
    readMock.mockResolvedValue(snapshot('file b', { path: B, version: 'b1' }));
    hook.rerender({ path: B, enabled: true });
    await waitFor(() => expect(hook.result.current.draft).toBe('file b'));

    type(hook, 'file b!');
    await act(() => hook.result.current.save());

    expect(saveMock).toHaveBeenLastCalledWith(WORKSPACE, B, 'file b!', 'b1');
    await act(async () => slowA.resolve(written('v2')));
  });

  it.each<[WorkspaceTextFailureReason, string]>([
    ['write_blocked', 'saveBlocked'],
    ['not_found', 'saveGone'],
    ['not_a_file', 'saveGone'],
    ['content_too_large', 'saveTooLarge'],
    ['invalid_content', 'saveInvalidContent'],
    ['binary', 'saveFailed'],
  ])('words a %s refusal as %s and keeps the draft', async (reason, copy) => {
    const hook = await openEditor('hello');
    saveMock.mockRejectedValue(new WorkspaceTextError(reason));
    type(hook, 'hello!');

    await act(() => hook.result.current.save());

    expect(toastError).toHaveBeenCalledWith(copy);
    expect(hook.result.current).toMatchObject({ draft: 'hello!', dirty: true, saving: false, conflict: false });
  });

  it('words an unnamed failure (network, server) in the generic way', async () => {
    const hook = await openEditor('hello');
    saveMock.mockRejectedValue(new TypeError('Failed to fetch'));
    type(hook, 'hello!');

    await act(() => hook.result.current.save());

    expect(toastError).toHaveBeenCalledWith('saveFailed');
    expect(hook.result.current.draft).toBe('hello!');
  });
});

describe('a file that changed on disk during the edit', () => {
  const conflictHook = async () => {
    const hook = await openEditor('hello');
    saveMock.mockRejectedValueOnce(new WorkspaceTextError('version_conflict', 'v-disk'));
    type(hook, 'my edit');
    await act(() => hook.result.current.save());
    return hook;
  };

  it('keeps the draft, raises the conflict and does not pretend the save failed', async () => {
    const { result } = await conflictHook();

    expect(result.current).toMatchObject({ draft: 'my edit', dirty: true, conflict: true, saving: false });
    expect(toastError).not.toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('overwrites on purpose by saving against the version found on disk', async () => {
    const hook = await conflictHook();
    saveMock.mockResolvedValueOnce(written('v-new'));

    await act(() => hook.result.current.overwrite());

    expect(saveMock).toHaveBeenLastCalledWith(WORKSPACE, A, 'my edit', 'v-disk');
    expect(hook.result.current).toMatchObject({ conflict: false, dirty: false });
    expect(hook.result.current.snapshot?.version).toBe('v-new');
  });

  it('asks the user again when the file changed once more before the overwrite', async () => {
    const hook = await conflictHook();
    saveMock.mockRejectedValueOnce(new WorkspaceTextError('version_conflict', 'v-disk-2'));

    await act(() => hook.result.current.overwrite());
    saveMock.mockResolvedValueOnce(written('v-new'));
    await act(() => hook.result.current.overwrite());

    expect(saveMock).toHaveBeenLastCalledWith(WORKSPACE, A, 'my edit', 'v-disk-2');
    expect(hook.result.current.conflict).toBe(false);
  });

  it('ends the conflict together with the draft when the user drops their text', async () => {
    const hook = await conflictHook();

    act(() => hook.result.current.discard());

    expect(hook.result.current).toMatchObject({ draft: 'hello', dirty: false, conflict: false });
  });

  it('loads the latest version and drops the draft and the conflict', async () => {
    const hook = await conflictHook();
    readMock.mockResolvedValue(snapshot('agent wrote this', { version: 'v-disk' }));

    await act(() => hook.result.current.reload());

    expect(hook.result.current).toMatchObject({ draft: 'agent wrote this', dirty: false, conflict: false });
    expect(hook.result.current.snapshot?.version).toBe('v-disk');
  });

  it('keeps the draft as a copy, names the new file, and leaves the decision open', async () => {
    const hook = await conflictHook();
    copyMock.mockResolvedValue(written('v9', 'a (1).txt'));

    await act(() => hook.result.current.saveCopy());

    expect(copyMock).toHaveBeenCalledWith(WORKSPACE, A, 'my edit');
    expect(toastSuccess).toHaveBeenCalledWith('saveCopySuccess:a (1).txt');
    expect(hook.result.current).toMatchObject({ draft: 'my edit', conflict: true, saving: false });
  });

  it.each<[Error, string]>([
    [new WorkspaceTextError('write_blocked'), 'saveBlocked'],
    [new WorkspaceTextError('name_unavailable'), 'saveCopyFailed'],
    [new TypeError('Failed to fetch'), 'saveCopyFailed'],
  ])('words a failed copy (%s) as %s', async (failure, copy) => {
    const hook = await conflictHook();
    copyMock.mockRejectedValue(failure);

    await act(() => hook.result.current.saveCopy());

    expect(toastError).toHaveBeenCalledWith(copy);
    expect(hook.result.current).toMatchObject({ draft: 'my edit', conflict: true, saving: false });
  });
});

describe('moving between files', () => {
  it('never shows what was read or typed for the previous file, not even for one render', async () => {
    const rendered: Array<{ path: string; draft: string; phase: string }> = [];
    readMock.mockResolvedValueOnce(snapshot('hello'));
    const hook = renderHook(
      ({ path }) => {
        const editor = useWorkspaceTextEditor(WORKSPACE, path, true);
        rendered.push({ path, draft: editor.draft, phase: editor.phase });
        return editor;
      },
      { initialProps: { path: A } },
    );
    await waitFor(() => expect(hook.result.current.phase).toBe('ready'));
    type(hook, 'unsaved edit');
    readMock.mockReturnValue(deferred<WorkspaceTextSnapshot>().promise);

    hook.rerender({ path: B });

    const forB = rendered.filter((render) => render.path === B);
    expect(forB.length).toBeGreaterThan(0);
    expect(forB).toSatisfy((renders: typeof forB) =>
      renders.every((render) => render.draft === '' && render.phase === 'loading'),
    );
    expect(hook.result.current).toMatchObject({ phase: 'loading', draft: '', snapshot: null, dirty: false });
  });

  it('drops the answer of a slow read once another file has been opened', async () => {
    const slowA = deferred<WorkspaceTextSnapshot>();
    readMock.mockReturnValueOnce(slowA.promise).mockResolvedValueOnce(snapshot('file b', { path: B }));
    const hook = renderHook(({ path }) => useWorkspaceTextEditor(WORKSPACE, path, true), {
      initialProps: { path: A },
    });

    hook.rerender({ path: B });
    await waitFor(() => expect(hook.result.current.phase).toBe('ready'));
    await act(async () => slowA.resolve(snapshot('file a')));

    expect(hook.result.current.draft).toBe('file b');
  });

  it('applies a late save result to nothing but still says when the text did not reach the disk', async () => {
    const hook = await openEditor('hello');
    const inFlight = deferred<ReturnType<typeof written>>();
    saveMock.mockReturnValue(inFlight.promise);
    type(hook, 'hello!');
    act(() => {
      void hook.result.current.save();
    });
    readMock.mockResolvedValue(snapshot('file b', { path: B }));
    hook.rerender({ path: B, enabled: true });
    await waitFor(() => expect(hook.result.current.draft).toBe('file b'));

    await act(async () => inFlight.reject(new WorkspaceTextError('write_blocked')));

    expect(toastError).toHaveBeenCalledWith('saveBlocked');
    expect(hook.result.current).toMatchObject({ draft: 'file b', saving: false, conflict: false });
  });

  it('turns a conflict that arrives after leaving the file into a plain failure notice', async () => {
    const hook = await openEditor('hello');
    const inFlight = deferred<ReturnType<typeof written>>();
    saveMock.mockReturnValue(inFlight.promise);
    type(hook, 'hello!');
    act(() => {
      void hook.result.current.save();
    });
    readMock.mockResolvedValue(snapshot('file b', { path: B }));
    hook.rerender({ path: B, enabled: true });
    await waitFor(() => expect(hook.result.current.draft).toBe('file b'));

    await act(async () => inFlight.reject(new WorkspaceTextError('version_conflict', 'v-disk')));

    expect(toastError).toHaveBeenCalledWith('saveFailed');
    expect(hook.result.current.conflict).toBe(false);
  });
});
