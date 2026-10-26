/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AppDialogHost from '@/components/features/app-shell/app-dialog-host';
import type { FileEntry } from '@/services/chat';
import {
  readWorkspaceText,
  saveWorkspaceText,
  WorkspaceTextError,
  type WorkspaceTextSnapshot,
} from '@/services/workspaceText';
import { useAppDialogStore } from '@/store/useAppDialogStore';
import { keptDraft, useWorkspaceDraftStore } from '@/store/useWorkspaceDraftStore';
import en from '../../../../../locales/en.json';
import { WorkspaceFilePreview } from '../WorkspaceFilePreview';

const english: Record<string, Record<string, unknown>> = { appDialog: en.appDialog, common: en.common };

/** English text for the dialog host, so a missing key fails the test. */
const inEnglish = (namespace: string) => (key: string) =>
  typeof english[namespace][key] === 'string' ? (english[namespace][key] as string) : `MISSING ${namespace}.${key}`;

/** One stable translator per namespace: the dialog host speaks English, the preview shows its keys. */
const translators: Record<string, (key: string, values?: Record<string, string>) => string> = {
  appDialog: inEnglish('appDialog'),
  common: inEnglish('common'),
  workspace: (key, values) => (values ? `${key}:${values.name}` : key),
};
vi.mock('next-intl', () => ({ useTranslations: (namespace: string) => translators[namespace] }));

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
const OTHER = `${WORKSPACE}/other.txt`;

const textFile = (name: string): FileEntry => ({
  name,
  path: `${WORKSPACE}/${name}`,
  type: 'file',
  size: 5,
  mtime: null,
  is_text: true,
  children: null,
});

/** What the disk holds, by path; a test changes it to play the agent writing behind the user's back. */
const disk: Record<string, WorkspaceTextSnapshot> = {};

const onDisk = (path: string, content: string, version = 'v1'): WorkspaceTextSnapshot => ({
  path,
  name: path.split('/').pop() ?? path,
  content,
  version,
  size: content.length,
  editable: true,
  readonlyReason: null,
  truncated: false,
});

const readMock = vi.mocked(readWorkspaceText);
const saveMock = vi.mocked(saveWorkspaceText);
const written = { path: NOTES, name: 'notes.txt', version: 'v2', size: 6, changed: true };

const onClose = vi.fn();

const view = (file: FileEntry) => (
  <>
    <WorkspaceFilePreview file={file} workspace={WORKSPACE} onClose={onClose} />
    <AppDialogHost />
  </>
);

const editor = () => screen.getByRole('textbox', { hidden: true }) as HTMLTextAreaElement;

/** Opens the editor if it is not open yet, and types, which leaves unsaved edits. */
function typeIntoEditor(text: string): void {
  const toggle = screen.queryByTitle('editMode');
  if (toggle) {
    fireEvent.click(toggle);
  }
  fireEvent.change(editor(), { target: { value: text } });
}

const dialog = () => screen.findByRole('alertdialog');
const inDialog = async (name: string) => within(await dialog()).getByRole('button', { name });
const dialogGone = () => waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());

/** Types into the notes file and leaves it, so the next visit has unsaved text to come back to. */
async function leaveNotesUnsaved(text: string): Promise<void> {
  const first = render(view(textFile('notes.txt')));
  await screen.findByText('hello');
  typeIntoEditor(text);
  first.unmount();
}

beforeEach(() => {
  vi.clearAllMocks();
  useWorkspaceDraftStore.setState({ drafts: {} });
  useAppDialogStore.setState({ current: null, open: false, queue: [] });
  Object.assign(disk, { [NOTES]: onDisk(NOTES, 'hello'), [OTHER]: onDisk(OTHER, 'other file') });
  readMock.mockImplementation(async (_workspace, path) => disk[path]);
  saveMock.mockResolvedValue(written);
});

describe('closing the preview over unsaved edits', () => {
  async function closeWithEdits() {
    render(view(textFile('notes.txt')));
    await screen.findByText('hello');
    typeIntoEditor('hello!');
    fireEvent.click(screen.getByTitle('close'));
  }

  it('asks in plain words what to do, and closes nothing yet', async () => {
    await closeWithEdits();

    const ask = await dialog();
    expect(ask).toHaveTextContent('unsavedTitle');
    expect(ask).toHaveTextContent('unsavedBody:notes.txt');
    expect(
      within(ask)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['Cancel', 'save', 'discardChanges']);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('saves, and closes once the file holds the text', async () => {
    await closeWithEdits();

    fireEvent.click(await inDialog('save'));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledWith(WORKSPACE, NOTES, 'hello!', 'v1');
    expect(keptDraft(WORKSPACE, NOTES)).toBeUndefined();
  });

  it('stays open, with the text, when the save was refused', async () => {
    saveMock.mockRejectedValue(new WorkspaceTextError('write_blocked'));
    await closeWithEdits();

    fireEvent.click(await inDialog('save'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('saveBlocked'));
    expect(onClose).not.toHaveBeenCalled();
    expect(editor().value).toBe('hello!');
    expect(keptDraft(WORKSPACE, NOTES)?.text).toBe('hello!');
  });

  it('closes without saving and forgets the text when the user discards it', async () => {
    await closeWithEdits();

    fireEvent.click(await inDialog('discardChanges'));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(saveMock).not.toHaveBeenCalled();
    expect(keptDraft(WORKSPACE, NOTES)).toBeUndefined();
  });

  it.each([
    ['Cancel', async () => fireEvent.click(await inDialog('Cancel'))],
    ['Escape', async () => fireEvent.keyDown(await dialog(), { key: 'Escape' })],
  ])('stays with the edits when the question is answered with %s', async (_name, answer) => {
    await closeWithEdits();

    await answer();

    await dialogGone();
    expect(onClose).not.toHaveBeenCalled();
    expect(editor().value).toBe('hello!');
    expect(keptDraft(WORKSPACE, NOTES)?.text).toBe('hello!');
  });

  it('closes at once, asking nothing, when there is nothing unsaved', async () => {
    render(view(textFile('notes.txt')));
    await screen.findByText('hello');

    fireEvent.click(screen.getByTitle('close'));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });
});

describe('leaving edit mode over unsaved edits', () => {
  it('asks the same question, and shows the file as saved when the edits are discarded', async () => {
    render(view(textFile('notes.txt')));
    await screen.findByText('hello');
    typeIntoEditor('hello!');

    fireEvent.click(screen.getByTitle('viewMode'));
    fireEvent.click(await inDialog('discardChanges'));

    expect(await screen.findByText('hello')).toBeTruthy();
    expect(screen.queryByRole('textbox', { hidden: true })).toBeNull();
    expect(screen.queryByText('unsaved')).toBeNull();
    expect(keptDraft(WORKSPACE, NOTES)).toBeUndefined();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('stays in the editor with the text when the user does not decide', async () => {
    render(view(textFile('notes.txt')));
    await screen.findByText('hello');
    typeIntoEditor('hello!');

    fireEvent.click(screen.getByTitle('viewMode'));
    fireEvent.click(await inDialog('Cancel'));

    await dialogGone();
    expect(editor().value).toBe('hello!');
  });

  it('switches at once, asking nothing, when nothing is unsaved', async () => {
    render(view(textFile('notes.txt')));
    await screen.findByText('hello');
    fireEvent.click(screen.getByTitle('editMode'));

    fireEvent.click(screen.getByTitle('viewMode'));

    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.queryByRole('textbox', { hidden: true })).toBeNull();
  });
});

describe('opening a file that has unsaved text from an earlier visit', () => {
  it('shows that text in the editor, says so, and counts it as unsaved', async () => {
    await leaveNotesUnsaved('hello!');

    render(view(textFile('notes.txt')));

    expect(await screen.findByTestId('workspace-edit-restored')).toHaveTextContent('draftRestored');
    expect(editor().value).toBe('hello!');
    expect(screen.getByText('unsaved')).toBeTruthy();
    expect(screen.queryByTestId('workspace-edit-conflict')).toBeNull();
  });

  it('never puts the saved text on screen in place of the restored text, not even for one frame', async () => {
    await leaveNotesUnsaved('hello!');
    const frames: string[] = [];
    const observer = new MutationObserver(() =>
      frames.push(
        `${screen.queryByTestId('workspace-edit-restored') ? 'notice' : 'plain'}/${
          screen.queryByRole('textbox', { hidden: true }) ? 'editor' : 'viewer'
        }`,
      ),
    );

    render(view(textFile('notes.txt')));
    observer.observe(document.body, { childList: true, subtree: true });
    await screen.findByTestId('workspace-edit-restored');
    observer.disconnect();

    expect(frames).toContain('notice/editor');
    expect(frames).not.toContain('notice/viewer');
  });

  it('stops announcing the text once the user edits it', async () => {
    await leaveNotesUnsaved('hello!');
    render(view(textFile('notes.txt')));
    await screen.findByTestId('workspace-edit-restored');

    fireEvent.change(editor(), { target: { value: 'hello!!' } });

    expect(screen.queryByTestId('workspace-edit-restored')).toBeNull();
    expect(editor().value).toBe('hello!!');
  });

  it('goes back to the saved text, with no notice, when the user discards the restored text', async () => {
    await leaveNotesUnsaved('hello!');
    render(view(textFile('notes.txt')));
    await screen.findByTestId('workspace-edit-restored');

    fireEvent.click(screen.getByTitle('viewMode'));
    fireEvent.click(await inDialog('discardChanges'));

    expect(await screen.findByText('hello')).toBeTruthy();
    expect(screen.queryByTestId('workspace-edit-restored')).toBeNull();
    expect(screen.queryByRole('textbox', { hidden: true })).toBeNull();
    expect(keptDraft(WORKSPACE, NOTES)).toBeUndefined();
  });

  it('raises the conflict at once, instead of the restored notice, when the file changed meanwhile', async () => {
    await leaveNotesUnsaved('hello!');
    disk[NOTES] = onDisk(NOTES, 'what the agent wrote', 'v-disk');

    render(view(textFile('notes.txt')));

    expect(await screen.findByTestId('workspace-edit-conflict')).toBeTruthy();
    expect(screen.queryByTestId('workspace-edit-restored')).toBeNull();
    expect(editor().value).toBe('hello!');
    expect(saveMock).not.toHaveBeenCalled();
  });

  it('offers no Save when closing over text that cannot be saved before the conflict is settled', async () => {
    await leaveNotesUnsaved('hello!');
    disk[NOTES] = onDisk(NOTES, 'what the agent wrote', 'v-disk');
    render(view(textFile('notes.txt')));
    await screen.findByTestId('workspace-edit-conflict');

    fireEvent.click(screen.getByTitle('close'));

    const ask = await dialog();
    expect(
      within(ask)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['Cancel', 'discardChanges']);
    expect(saveMock).not.toHaveBeenCalled();
  });

  it('opens the latest file, not the stale text, when the user discards a text whose file changed', async () => {
    await leaveNotesUnsaved('hello!');
    disk[NOTES] = onDisk(NOTES, 'what the agent wrote', 'v-disk');
    render(view(textFile('notes.txt')));
    await screen.findByTestId('workspace-edit-conflict');

    fireEvent.click(screen.getByTitle('viewMode'));
    fireEvent.click(await inDialog('discardChanges'));

    expect(await screen.findByText('what the agent wrote')).toBeTruthy();
    expect(screen.queryByTestId('workspace-edit-conflict')).toBeNull();
    expect(keptDraft(WORKSPACE, NOTES)).toBeUndefined();
  });
});

describe('moving between files', () => {
  it('keeps the text of each file apart: nothing typed in one shows in another, and each comes back as left', async () => {
    const { rerender } = render(view(textFile('notes.txt')));
    await screen.findByText('hello');
    typeIntoEditor('edit of notes');

    rerender(view(textFile('other.txt')));

    expect(await screen.findByText('other file')).toBeTruthy();
    expect(screen.queryByRole('textbox', { hidden: true })).toBeNull();
    expect(screen.queryByText('unsaved')).toBeNull();
    expect(screen.queryByTestId('workspace-edit-restored')).toBeNull();
    typeIntoEditor('edit of other');

    rerender(view(textFile('notes.txt')));
    await screen.findByTestId('workspace-edit-restored');
    expect(editor().value).toBe('edit of notes');

    rerender(view(textFile('other.txt')));
    await waitFor(() => expect(editor().value).toBe('edit of other'));
  });
});

describe('leaving the page while text is unsaved', () => {
  const pageAsksBeforeLeaving = () => {
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    return event.defaultPrevented;
  };

  it('asks from the first unsaved edit until the file holds the text, even after the preview is gone', async () => {
    const { unmount } = render(view(textFile('notes.txt')));
    await screen.findByText('hello');
    expect(pageAsksBeforeLeaving()).toBe(false);

    typeIntoEditor('hello!');
    expect(pageAsksBeforeLeaving()).toBe(true);

    unmount();
    expect(pageAsksBeforeLeaving()).toBe(true);

    render(view(textFile('notes.txt')));
    await screen.findByTestId('workspace-edit-restored');
    fireEvent.click(screen.getByTitle('save (Ctrl+S)'));
    await waitFor(() => expect(pageAsksBeforeLeaving()).toBe(false));
  });
});
