/** @vitest-environment jsdom */
import { act, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkspaceTextError } from '@/services/workspaceText';
import {
  A,
  copyMock,
  openEditor,
  readMock,
  resetEditorTest,
  saveMock,
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

  it('ends the conflict together with the draft, and shows the file as it is now rather than as it was read', async () => {
    const hook = await conflictHook();
    readMock.mockResolvedValue(snapshot('agent wrote this', { version: 'v-disk' }));

    act(() => hook.result.current.discard());

    await waitFor(() =>
      expect(hook.result.current).toMatchObject({ draft: 'agent wrote this', dirty: false, conflict: false }),
    );
    expect(hook.result.current.snapshot?.version).toBe('v-disk');
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
