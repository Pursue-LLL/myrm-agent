/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry } from '@/services/chat';
import { readWorkspaceText, saveWorkspaceText, type WorkspaceTextSnapshot } from '@/services/workspaceText';
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
  path: `${WORKSPACE}/notes.txt`,
  name: 'notes.txt',
  content,
  version: 'v1',
  size: content.length,
  editable: true,
  readonlyReason: null,
  truncated: false,
  ...overrides,
});

const written = { path: `${WORKSPACE}/notes.txt`, name: 'notes.txt', version: 'v2', size: 6, changed: true };

const readMock = vi.mocked(readWorkspaceText);
const saveMock = vi.mocked(saveWorkspaceText);

const preview = (file: FileEntry) => <WorkspaceFilePreview file={file} workspace={WORKSPACE} onClose={vi.fn()} />;

beforeEach(() => {
  useWorkspaceDraftStore.setState({ drafts: {} });
});

/** Opens the editor and types, which leaves unsaved edits. */
function typeIntoEditor(text: string): void {
  fireEvent.click(screen.getByTitle('editMode'));
  fireEvent.change(screen.getByRole('textbox', { hidden: true }), { target: { value: text } });
}

describe('WorkspaceFilePreview save shortcut', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    readMock.mockResolvedValue(snapshot('hello'));
    saveMock.mockResolvedValue(written);
  });

  const pressSave = () => fireEvent.keyDown(window, { key: 's', ctrlKey: true });

  it('saves the edits on Ctrl+S while the preview is on screen', async () => {
    render(preview(textFile('notes.txt')));
    await screen.findByText('hello');
    typeIntoEditor('hello!');

    const notPrevented = pressSave();

    expect(notPrevented).toBe(false);
    await waitFor(() => expect(saveMock).toHaveBeenCalledWith(WORKSPACE, `${WORKSPACE}/notes.txt`, 'hello!', 'v1'));
  });

  it('leaves Ctrl+S alone while the panel holding the preview is hidden', async () => {
    render(<div hidden>{preview(textFile('notes.txt'))}</div>);
    await screen.findByText('hello');
    typeIntoEditor('hello!');

    const notPrevented = pressSave();

    expect(notPrevented).toBe(true);
    expect(saveMock).not.toHaveBeenCalled();
  });

  it('saves again once the panel is shown', async () => {
    const { rerender } = render(<div hidden>{preview(textFile('notes.txt'))}</div>);
    await screen.findByText('hello');
    typeIntoEditor('hello!');

    rerender(<div>{preview(textFile('notes.txt'))}</div>);
    pressSave();

    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
  });
});

describe('WorkspaceFilePreview when a file cannot be read', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('words the failure in the user language and never shows the reason the server gave', async () => {
    readMock.mockRejectedValue(
      new Error('{"detail":"Cannot read file: [Errno 13] Permission denied: \'/Users/me/.secret\'"}'),
    );

    render(preview(textFile('notes.txt')));

    expect(await screen.findByText('previewLoadError')).toBeTruthy();
    expect(screen.queryByText(/Errno|secret|detail/)).toBeNull();
  });

  it('drops the failure notice when another file opens fine', async () => {
    readMock.mockRejectedValueOnce(new Error('boom')).mockResolvedValue(snapshot('second file'));
    const { rerender } = render(preview(textFile('broken.txt')));
    await screen.findByText('previewLoadError');

    rerender(preview(textFile('fine.txt')));

    expect(await screen.findByText('second file')).toBeTruthy();
    expect(screen.queryByText('previewLoadError')).toBeNull();
  });
});
