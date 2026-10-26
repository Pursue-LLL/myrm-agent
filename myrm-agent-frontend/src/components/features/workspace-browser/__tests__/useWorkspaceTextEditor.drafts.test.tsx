/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkspaceTextError } from '@/services/workspaceText';
import { keptDraft, useWorkspaceDraftStore } from '@/store/useWorkspaceDraftStore';
import { useWorkspaceTextEditor } from '../useWorkspaceTextEditor';
import {
  A,
  B,
  deferred,
  readMock,
  resetEditorTest,
  saveMock,
  snapshot,
  toastError,
  WORKSPACE,
  written,
} from './editorTestKit';

const stableT = (key: string) => key;

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

type EditorHook = ReturnType<typeof renderHook<ReturnType<typeof useWorkspaceTextEditor>, { path: string }>>;

/** Opens a file in a fresh editor, the way a preview does each time it appears. */
async function visit(path = A): Promise<EditorHook> {
  const hook = renderHook(({ path: current }) => useWorkspaceTextEditor(WORKSPACE, current, true), {
    initialProps: { path },
  });
  await waitFor(() => expect(hook.result.current.phase).toBe('ready'));
  return hook;
}

const type = (hook: EditorHook, value: string) => act(() => hook.result.current.setDraft(value));

/** Types into a file and leaves it, so the next visit has something to come back to. */
async function leaveWithUnsavedText(text = 'my edit', content = 'hello'): Promise<void> {
  readMock.mockResolvedValue(snapshot(content));
  const hook = await visit();
  type(hook, text);
  hook.unmount();
}

beforeEach(resetEditorTest);

describe('keeping what is typed', () => {
  it('keeps it for exactly as long as it differs from the file', async () => {
    readMock.mockResolvedValue(snapshot('hello'));
    const hook = await visit();
    expect(keptDraft(WORKSPACE, A)).toBeUndefined();

    type(hook, 'hello!');
    expect(keptDraft(WORKSPACE, A)).toMatchObject({ text: 'hello!', base: { content: 'hello', version: 'v1' } });

    type(hook, 'hello');
    expect(keptDraft(WORKSPACE, A)).toBeUndefined();
  });

  it('keeps nothing for a file that was only looked at', async () => {
    readMock.mockResolvedValue(snapshot('hello'));
    const hook = await visit();
    hook.unmount();

    expect(useWorkspaceDraftStore.getState().drafts).toEqual({});
  });
});

describe('coming back to a file', () => {
  it('starts from the text that was left, over the version it was typed against', async () => {
    await leaveWithUnsavedText('hello!');

    const hook = await visit();

    expect(hook.result.current).toMatchObject({ draft: 'hello!', dirty: true, restored: true, conflict: false });
    expect(hook.result.current.snapshot).toMatchObject({ content: 'hello', version: 'v1' });
    saveMock.mockResolvedValue(written('v2'));
    await act(() => hook.result.current.save());
    expect(saveMock).toHaveBeenLastCalledWith(WORKSPACE, A, 'hello!', 'v1');
  });

  it('keeps the text of each file apart while moving between files, and shows none of it for another file', async () => {
    readMock.mockResolvedValue(snapshot('hello'));
    const hook = await visit();
    type(hook, 'edit of a');

    readMock.mockResolvedValue(snapshot('file b', { path: B, version: 'b1' }));
    hook.rerender({ path: B });
    await waitFor(() => expect(hook.result.current.draft).toBe('file b'));
    expect(hook.result.current).toMatchObject({ dirty: false, restored: false });
    type(hook, 'edit of b');

    readMock.mockResolvedValue(snapshot('hello'));
    hook.rerender({ path: A });
    await waitFor(() => expect(hook.result.current.draft).toBe('edit of a'));
    expect(hook.result.current).toMatchObject({ dirty: true, restored: true });

    readMock.mockResolvedValue(snapshot('file b', { path: B, version: 'b1' }));
    hook.rerender({ path: B });
    await waitFor(() => expect(hook.result.current.draft).toBe('edit of b'));
  });

  it('says at once that the file changed since the text was typed, before anything is saved', async () => {
    await leaveWithUnsavedText('my edit');
    readMock.mockResolvedValue(snapshot('agent wrote this', { version: 'v-disk' }));

    const hook = await visit();

    expect(hook.result.current).toMatchObject({ draft: 'my edit', dirty: true, restored: true, conflict: true });
    expect(hook.result.current.snapshot?.content).toBe('hello');
    expect(saveMock).not.toHaveBeenCalled();

    saveMock.mockResolvedValueOnce(written('v-new'));
    await act(() => hook.result.current.overwrite());
    expect(saveMock).toHaveBeenLastCalledWith(WORKSPACE, A, 'my edit', 'v-disk');
    expect(hook.result.current).toMatchObject({ conflict: false, dirty: false, restored: false });
    expect(keptDraft(WORKSPACE, A)).toBeUndefined();
  });

  it('lets the text go when the file now holds exactly that text', async () => {
    await leaveWithUnsavedText('my edit');
    readMock.mockResolvedValue(snapshot('my edit', { version: 'v-disk' }));

    const hook = await visit();

    expect(hook.result.current).toMatchObject({ draft: 'my edit', dirty: false, restored: false, conflict: false });
    expect(keptDraft(WORKSPACE, A)).toBeUndefined();
  });

  it('gives the text back even when the file cannot be read now, and lets a save say what is wrong', async () => {
    await leaveWithUnsavedText('my edit');
    readMock.mockRejectedValue(new Error('Errno 2 /Users/me/gone.txt'));

    const hook = await visit();

    expect(hook.result.current).toMatchObject({ draft: 'my edit', dirty: true, restored: true, conflict: false });
    saveMock.mockRejectedValue(new WorkspaceTextError('not_found'));
    await act(() => hook.result.current.save());
    expect(toastError).toHaveBeenCalledWith('saveGone');
    expect(hook.result.current.draft).toBe('my edit');
  });

  it('keeps the text but refuses to overwrite a file that can no longer be edited here', async () => {
    await leaveWithUnsavedText('my edit');
    readMock.mockResolvedValue(
      snapshot('', { version: '', editable: false, readonlyReason: 'too_large', truncated: true }),
    );

    const hook = await visit();
    expect(hook.result.current).toMatchObject({ draft: 'my edit', restored: true, conflict: true });
    saveMock.mockRejectedValue(new Error('request refused'));
    await act(() => hook.result.current.overwrite());

    expect(saveMock).toHaveBeenLastCalledWith(WORKSPACE, A, 'my edit', '');
    expect(toastError).toHaveBeenCalledWith('saveFailed');
    expect(hook.result.current).toMatchObject({ draft: 'my edit', conflict: true, saving: false });
  });

  it('stops calling the text restored with the first edit', async () => {
    await leaveWithUnsavedText('my edit');
    const hook = await visit();
    expect(hook.result.current.restored).toBe(true);

    type(hook, 'my edit!');

    expect(hook.result.current).toMatchObject({ draft: 'my edit!', restored: false });
  });
});

describe('letting the text go', () => {
  it('forgets it once it is saved', async () => {
    readMock.mockResolvedValue(snapshot('hello'));
    const hook = await visit();
    type(hook, 'hello!');
    saveMock.mockResolvedValue(written('v2'));

    await act(() => hook.result.current.save());

    expect(keptDraft(WORKSPACE, A)).toBeUndefined();
  });

  it('forgets it when it is discarded, even if the preview goes away in the same breath', async () => {
    readMock.mockResolvedValue(snapshot('hello'));
    const hook = await visit();
    type(hook, 'hello!');

    act(() => {
      hook.result.current.discard();
      hook.unmount();
    });

    expect(keptDraft(WORKSPACE, A)).toBeUndefined();
  });

  it('stops calling the text restored once it is discarded', async () => {
    await leaveWithUnsavedText('my edit');
    const hook = await visit();
    expect(hook.result.current.restored).toBe(true);

    act(() => hook.result.current.discard());

    expect(hook.result.current).toMatchObject({ draft: 'hello', dirty: false, restored: false });
    expect(keptDraft(WORKSPACE, A)).toBeUndefined();
  });

  it('forgets it when the file is read again, and does not bring it back', async () => {
    readMock.mockResolvedValue(snapshot('hello'));
    const hook = await visit();
    type(hook, 'hello!');

    await act(() => hook.result.current.reload());

    expect(hook.result.current).toMatchObject({ draft: 'hello', dirty: false, restored: false });
    expect(keptDraft(WORKSPACE, A)).toBeUndefined();
  });

  it('forgets it when a save finishes after the editor was left', async () => {
    readMock.mockResolvedValue(snapshot('hello'));
    const hook = await visit();
    type(hook, 'hello!');
    const inFlight = deferred<ReturnType<typeof written>>();
    saveMock.mockReturnValue(inFlight.promise);
    act(() => {
      void hook.result.current.save();
    });
    hook.unmount();
    expect(keptDraft(WORKSPACE, A)?.text).toBe('hello!');

    await act(async () => inFlight.resolve(written('v2')));

    expect(keptDraft(WORKSPACE, A)).toBeUndefined();
  });

  it('lets text typed during a save that finishes after the editor was left continue from what was written', async () => {
    readMock.mockResolvedValue(snapshot('hello'));
    const hook = await visit();
    type(hook, 'hello!');
    const inFlight = deferred<ReturnType<typeof written>>();
    saveMock.mockReturnValue(inFlight.promise);
    act(() => {
      void hook.result.current.save();
    });
    type(hook, 'hello!!');
    hook.unmount();

    await act(async () => inFlight.resolve(written('v2')));

    expect(keptDraft(WORKSPACE, A)).toMatchObject({
      text: 'hello!!',
      base: { content: 'hello!', version: 'v2' },
    });
    // Coming back, the file is what the save wrote: nothing in it is anyone else's change.
    readMock.mockResolvedValue(snapshot('hello!', { version: 'v2' }));
    const back = await visit();
    expect(back.result.current).toMatchObject({ draft: 'hello!!', dirty: true, restored: true, conflict: false });
  });
});
