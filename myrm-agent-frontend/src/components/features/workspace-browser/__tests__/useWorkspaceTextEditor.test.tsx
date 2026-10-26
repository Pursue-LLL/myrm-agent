/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  WorkspaceTextError,
  type WorkspaceTextFailureReason,
  type WorkspaceTextSnapshot,
} from '@/services/workspaceText';
import { useWorkspaceTextEditor } from '../useWorkspaceTextEditor';
import {
  A,
  B,
  deferred,
  openEditor,
  readMock,
  resetEditorTest,
  saveMock,
  saveResult,
  snapshot,
  toastError,
  toastSuccess,
  type,
  WORKSPACE,
  written,
} from './editorTestKit';

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

beforeEach(resetEditorTest);

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

  it('says whether the file holds the text afterwards', async () => {
    const hook = await openEditor('hello');
    expect(await saveResult(hook)).toBe(true);
    expect(saveMock).not.toHaveBeenCalled();

    type(hook, 'hello!');
    saveMock.mockRejectedValueOnce(new WorkspaceTextError('write_blocked'));
    expect(await saveResult(hook)).toBe(false);

    saveMock.mockRejectedValueOnce(new WorkspaceTextError('version_conflict', 'v-disk'));
    expect(await saveResult(hook)).toBe(false);

    saveMock.mockResolvedValueOnce(written('v2'));
    expect(await saveResult(hook)).toBe(true);

    readMock.mockResolvedValue(snapshot('locked', { editable: false, readonlyReason: 'not_utf8' }));
    const locked = renderHook(() => useWorkspaceTextEditor(WORKSPACE, B, true));
    await waitFor(() => expect(locked.result.current.phase).toBe('ready'));
    act(() => locked.result.current.setDraft('forced'));
    expect(await saveResult(locked)).toBe(false);
  });

  it('keeps text typed while the save is in flight, still counted as unsaved', async () => {
    const hook = await openEditor('hello');
    const inFlight = deferred<ReturnType<typeof written>>();
    saveMock.mockReturnValue(inFlight.promise);

    type(hook, 'hello!');
    let saving!: Promise<boolean>;
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
