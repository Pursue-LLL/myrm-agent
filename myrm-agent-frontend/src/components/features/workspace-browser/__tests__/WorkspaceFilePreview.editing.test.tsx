/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry } from '@/services/chat';
import {
  readWorkspaceText,
  saveWorkspaceText,
  saveWorkspaceTextCopy,
  WorkspaceTextError,
  type WorkspaceTextReadonlyReason,
  type WorkspaceTextSnapshot,
} from '@/services/workspaceText';
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
  saveWorkspaceText: vi.fn(),
  saveWorkspaceTextCopy: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  getStorageUrl: (url: string) => url,
}));

// The rich-media renderers are loaded on demand and are not what these tests are about.
vi.mock('next/dynamic', () => ({
  default: () => () => null,
}));

vi.mock('@/components/features/artifacts/renderers/MediaPreview', () => ({
  SvgPreview: () => null,
}));

const WORKSPACE = '/workspace';
const NOTES = `${WORKSPACE}/notes.txt`;

const textFile = (name: string): FileEntry => ({
  name,
  path: `${WORKSPACE}/${name}`,
  type: 'file',
  size: 5,
  mtime: null,
  is_text: true,
  children: null,
});

const snapshot = (content: string, overrides: Partial<WorkspaceTextSnapshot> = {}): WorkspaceTextSnapshot => ({
  path: NOTES,
  name: 'notes.txt',
  content,
  version: 'v1',
  size: content.length,
  editable: true,
  readonlyReason: null,
  truncated: false,
  ...overrides,
});

const written = (name = 'notes.txt', version = 'v2') => ({
  path: `${WORKSPACE}/${name}`,
  name,
  version,
  size: 6,
  changed: true,
});

const readMock = vi.mocked(readWorkspaceText);
const saveMock = vi.mocked(saveWorkspaceText);
const copyMock = vi.mocked(saveWorkspaceTextCopy);

const preview = (file: FileEntry) => <WorkspaceFilePreview file={file} workspace={WORKSPACE} onClose={vi.fn()} />;

const editor = () => screen.getByRole('textbox', { hidden: true }) as HTMLTextAreaElement;

beforeEach(() => {
  useWorkspaceDraftStore.setState({ drafts: {} });
});

describe('WorkspaceFilePreview with a file the editor must not change', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each<[Exclude<WorkspaceTextReadonlyReason, 'binary'>, string]>([
    ['not_utf8', 'readonlyNotUtf8'],
    ['mixed_line_endings', 'readonlyMixedLineEndings'],
    ['too_large', 'readonlyTooLarge'],
  ])('shows a %s file as view-only, says why in plain words, and offers no way to edit it', async (reason, copy) => {
    readMock.mockResolvedValue(snapshot('shown text', { editable: false, readonlyReason: reason }));

    render(preview(textFile('notes.txt')));

    expect(await screen.findByText('shown text')).toBeTruthy();
    expect(screen.getByTestId('workspace-edit-readonly').textContent).toContain(copy);
    expect(screen.queryByTitle('editMode')).toBeNull();
  });

  it('shows a file the listing took for text but the server found to be binary as a download, without a reason', async () => {
    readMock.mockResolvedValue(snapshot('', { editable: false, readonlyReason: 'binary' }));

    render(preview(textFile('mystery.xyz')));

    expect(await screen.findByTestId('workspace-preview-unsupported')).toBeTruthy();
    expect(screen.queryByTestId('workspace-edit-readonly')).toBeNull();
    expect(screen.queryByTitle('editMode')).toBeNull();
  });

  it('shows no reason for a file that can be edited', async () => {
    readMock.mockResolvedValue(snapshot('plain'));

    render(preview(textFile('notes.txt')));

    await screen.findByText('plain');
    expect(screen.queryByTestId('workspace-edit-readonly')).toBeNull();
    expect(screen.getByTitle('editMode')).toBeTruthy();
  });
});

describe('WorkspaceFilePreview when the file changed on disk during an edit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    readMock.mockResolvedValue(snapshot('hello'));
  });

  /** Opens the editor, types, saves, and returns the conflict banner the save ends in. */
  async function saveIntoConflict() {
    saveMock.mockRejectedValueOnce(new WorkspaceTextError('version_conflict', 'v-disk'));
    render(preview(textFile('notes.txt')));
    await screen.findByText('hello');
    fireEvent.click(screen.getByTitle('editMode'));
    fireEvent.change(editor(), { target: { value: 'my text' } });
    fireEvent.click(screen.getByTitle('save (Ctrl+S)'));
    return screen.findByTestId('workspace-edit-conflict');
  }

  it('keeps what the user typed, offers the three ways out, and does not report a failed save', async () => {
    const banner = await saveIntoConflict();

    expect(banner.getAttribute('role')).toBe('alert');
    for (const choice of ['conflictSaveCopy', 'conflictReload', 'conflictOverwrite']) {
      expect(within(banner).getByRole('button', { name: choice })).toBeTruthy();
    }
    expect(editor().value).toBe('my text');
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('overwrites only when the user chooses to, against the version found on disk', async () => {
    const banner = await saveIntoConflict();
    expect(saveMock).toHaveBeenCalledTimes(1);
    saveMock.mockResolvedValueOnce(written());

    fireEvent.click(within(banner).getByRole('button', { name: 'conflictOverwrite' }));

    await waitFor(() => expect(screen.queryByTestId('workspace-edit-conflict')).toBeNull());
    expect(saveMock).toHaveBeenLastCalledWith(WORKSPACE, NOTES, 'my text', 'v-disk');
  });

  it('opens the latest version in place of what the user typed', async () => {
    const banner = await saveIntoConflict();
    readMock.mockResolvedValue(snapshot('what the agent wrote', { version: 'v-disk' }));

    fireEvent.click(within(banner).getByRole('button', { name: 'conflictReload' }));

    await waitFor(() => expect(editor().value).toBe('what the agent wrote'));
    expect(screen.queryByTestId('workspace-edit-conflict')).toBeNull();
    expect(saveMock).toHaveBeenCalledTimes(1);
  });

  it('keeps the typed text as a copy and leaves the original decision open', async () => {
    copyMock.mockResolvedValue(written('notes (1).txt', 'v9'));
    const banner = await saveIntoConflict();

    fireEvent.click(within(banner).getByRole('button', { name: 'conflictSaveCopy' }));

    await waitFor(() => expect(copyMock).toHaveBeenCalledWith(WORKSPACE, NOTES, 'my text'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('saveCopySuccess'));
    expect(screen.getByTestId('workspace-edit-conflict')).toBeTruthy();
    expect(editor().value).toBe('my text');
  });

  it('cannot be answered twice at once while a choice is being carried out', async () => {
    const banner = await saveIntoConflict();
    copyMock.mockReturnValue(new Promise(() => {}));

    fireEvent.click(within(banner).getByRole('button', { name: 'conflictSaveCopy' }));

    await waitFor(() =>
      expect((within(banner).getByRole('button', { name: 'conflictOverwrite' }) as HTMLButtonElement).disabled).toBe(
        true,
      ),
    );
  });
});
