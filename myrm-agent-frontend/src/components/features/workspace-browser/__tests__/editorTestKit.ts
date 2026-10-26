/**
 * Shared set-up of the `useWorkspaceTextEditor` test files: file snapshots, handles on the mocked service calls and
 * a driver that opens the editor on one file.
 *
 * Each test file still registers `vi.mock` for `next-intl`, `sonner` and `@/services/workspaceText` itself (vitest
 * hoists those per file); the handles below are the mocked functions.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { expect, vi } from 'vitest';
import {
  readWorkspaceText,
  saveWorkspaceText,
  saveWorkspaceTextCopy,
  type WorkspaceTextSnapshot,
} from '@/services/workspaceText';
import { useWorkspaceDraftStore } from '@/store/useWorkspaceDraftStore';
import { useWorkspaceTextEditor } from '../useWorkspaceTextEditor';

export const WORKSPACE = '/ws';
export const A = '/ws/a.txt';
export const B = '/ws/b.txt';

export const snapshot = (content: string, overrides: Partial<WorkspaceTextSnapshot> = {}): WorkspaceTextSnapshot => ({
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

export const written = (version: string, name = 'a.txt') => ({
  path: `/ws/${name}`,
  name,
  version,
  size: 1,
  changed: true,
});

export const readMock = vi.mocked(readWorkspaceText);
export const saveMock = vi.mocked(saveWorkspaceText);
export const copyMock = vi.mocked(saveWorkspaceTextCopy);
export const toastError = vi.mocked(toast.error);
export const toastSuccess = vi.mocked(toast.success);

/** Clears every mock call and every kept draft; call it from `beforeEach`. */
export function resetEditorTest(): void {
  vi.clearAllMocks();
  useWorkspaceDraftStore.setState({ drafts: {} });
}

/** A promise the test settles by hand, to hold a request in flight. */
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Opens `a.txt` holding `initial` in an editor that stays mounted, and waits until it is ready. */
export async function openEditor(initial = 'hello') {
  readMock.mockResolvedValue(snapshot(initial));
  const hook = renderHook(({ path, enabled }) => useWorkspaceTextEditor(WORKSPACE, path, enabled), {
    initialProps: { path: A, enabled: true },
  });
  await waitFor(() => expect(hook.result.current.phase).toBe('ready'));
  return hook;
}

export const type = (hook: Awaited<ReturnType<typeof openEditor>>, value: string) =>
  act(() => hook.result.current.setDraft(value));

export async function saveResult(hook: Awaited<ReturnType<typeof openEditor>>): Promise<boolean> {
  let saved = false;
  await act(async () => {
    saved = await hook.result.current.save();
  });
  return saved;
}
