/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry } from '@/services/chat';
import { readWorkspaceText, readWorkspaceTextIfChanged, type WorkspaceTextSnapshot } from '@/services/workspaceText';
import { useWorkspaceDraftStore } from '@/store/useWorkspaceDraftStore';
import { WorkspaceFilePreview } from '../WorkspaceFilePreview';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/components/features/files/FileTypeIcon', () => ({
  FileTypeIcon: () => <span data-testid="file-icon" />,
}));

vi.mock('@/services/chat', () => ({
  getWorkspaceFileContentUrl: vi.fn(() => '/content'),
}));

vi.mock('@/services/workspaceText', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/workspaceText')>()),
  readWorkspaceText: vi.fn(),
  readWorkspaceTextIfChanged: vi.fn(),
  saveWorkspaceText: vi.fn(),
  saveWorkspaceTextCopy: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  getStorageUrl: (url: string) => url,
}));

vi.mock('next/dynamic', () => ({
  default: () => () => null,
}));

vi.mock('@/components/features/artifacts/renderers/MediaPreview', () => ({
  SvgPreview: () => null,
}));

const WORKSPACE = '/workspace';
const NOTES = `${WORKSPACE}/notes.txt`;

const file: FileEntry = {
  name: 'notes.txt',
  path: NOTES,
  type: 'file',
  size: 5,
  mtime: null,
  is_text: true,
  children: null,
};

const snapshot = (content: string, version = 'v1'): WorkspaceTextSnapshot => ({
  path: NOTES,
  name: 'notes.txt',
  content,
  version,
  size: content.length,
  editable: true,
  readonlyReason: null,
  truncated: false,
});

const readMock = vi.mocked(readWorkspaceText);
const refreshMock = vi.mocked(readWorkspaceTextIfChanged);

const SOON = { timeout: 5000 };
const editor = () => screen.getByRole('textbox', { hidden: true }) as HTMLTextAreaElement;
const fileChangesOnDisk = () =>
  act(() => {
    window.dispatchEvent(new CustomEvent('workspace-file-changed', { detail: { workspace_path: WORKSPACE } }));
  });

beforeEach(() => {
  vi.clearAllMocks();
  useWorkspaceDraftStore.setState({ drafts: {} });
  readMock.mockResolvedValue(snapshot('hello'));
  render(<WorkspaceFilePreview file={file} workspace={WORKSPACE} onClose={vi.fn()} />);
});

describe('WorkspaceFilePreview while the file changes on disk', () => {
  it('shows what the file holds now, without being asked', async () => {
    await screen.findByText('hello');
    refreshMock.mockResolvedValue(snapshot('what the agent wrote', 'v2'));

    fileChangesOnDisk();

    expect(await screen.findByText('what the agent wrote', undefined, SOON)).toBeTruthy();
    expect(screen.queryByText('hello')).toBeNull();
    expect(refreshMock).toHaveBeenCalledWith(WORKSPACE, NOTES, 'v1');
  });

  it('replaces the text in an editor nothing was typed in', async () => {
    await screen.findByText('hello');
    fireEvent.click(screen.getByTitle('editMode'));
    refreshMock.mockResolvedValue(snapshot('what the agent wrote', 'v2'));

    fileChangesOnDisk();

    await waitFor(() => expect(editor().value).toBe('what the agent wrote'), SOON);
    expect(screen.queryByTestId('workspace-edit-conflict')).toBeNull();
  });

  it('keeps the typed text and offers the three ways out when something was typed', async () => {
    await screen.findByText('hello');
    fireEvent.click(screen.getByTitle('editMode'));
    fireEvent.change(editor(), { target: { value: 'my text' } });
    refreshMock.mockResolvedValue(snapshot('what the agent wrote', 'v2'));

    fileChangesOnDisk();

    expect(await screen.findByTestId('workspace-edit-conflict', undefined, SOON)).toBeTruthy();
    expect(editor().value).toBe('my text');
  });

  it('shows nothing new while the file is unchanged', async () => {
    await screen.findByText('hello');
    refreshMock.mockResolvedValue(null);

    fileChangesOnDisk();

    await waitFor(() => expect(refreshMock).toHaveBeenCalledTimes(1), SOON);
    expect(screen.getByText('hello')).toBeTruthy();
    expect(screen.queryByTestId('workspace-edit-conflict')).toBeNull();
  });
});
