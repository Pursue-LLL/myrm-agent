/** @vitest-environment jsdom */
import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AppDialogHost from '@/components/features/app-shell/app-dialog-host';
import type { FileEntry } from '@/services/chat';
import {
  readWorkspaceText,
  readWorkspaceTextIfChanged,
  saveWorkspaceText,
  type WorkspaceTextSnapshot,
} from '@/services/workspaceText';
import { useWorkspaceDraftStore } from '@/store/useWorkspaceDraftStore';
import { WorkspaceFilePreview } from '../WorkspaceFilePreview';

interface MonacoProps {
  defaultValue?: string;
  onChange?: (value: string | undefined) => void;
  onMount?: (editor: unknown, monaco: unknown) => void;
}

const { desktop, preloadCodeEditor, monaco } = vi.hoisted(() => ({
  desktop: { value: true },
  preloadCodeEditor: vi.fn(),
  monaco: { props: null as MonacoProps | null, text: '' },
}));

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

vi.mock('../codeEditorSupport', () => ({
  useSupportsCodeEditor: () => desktop.value,
  preloadCodeEditor,
}));

/** A stand-in for Monaco that keeps its text in a model like the real one and mounts the way the wrapper does. */
vi.mock('@/components/features/app-shell/lazy-monaco-editor', () => ({
  LazyMonacoEditor: (props: MonacoProps) => {
    monaco.props = props;
    React.useEffect(() => {
      monaco.text = props.defaultValue ?? '';
      const model = {
        getValue: () => monaco.text,
        setValue: (next: string) => {
          monaco.text = next;
        },
        setEOL: () => {},
      };
      const editor = { getModel: () => model, saveViewState: () => null, restoreViewState: () => {} };
      const api = {
        editor: { EndOfLineSequence: { LF: 0 } },
        typescript: {
          typescriptDefaults: { setDiagnosticsOptions: () => {} },
          javascriptDefaults: { setDiagnosticsOptions: () => {} },
        },
      };
      props.onMount?.(editor, api);
      // eslint-disable-next-line react-hooks/exhaustive-deps -- mounts once, like the real editor
    }, []);
    return <div data-testid="code-editor" />;
  },
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
const saveMock = vi.mocked(saveWorkspaceText);

const SOON = { timeout: 5000 };

/** The user types into the code editor: the model changes, then Monaco reports it. */
function typeIntoCodeEditor(text: string) {
  act(() => {
    monaco.text = text;
    monaco.props?.onChange?.(text);
  });
}

async function openPreview() {
  render(
    <>
      <WorkspaceFilePreview file={file} workspace={WORKSPACE} onClose={vi.fn()} />
      <AppDialogHost />
    </>,
  );
  await screen.findByText('hello');
}

beforeEach(() => {
  vi.clearAllMocks();
  desktop.value = true;
  monaco.props = null;
  monaco.text = '';
  useWorkspaceDraftStore.setState({ drafts: {} });
  readMock.mockResolvedValue(snapshot('hello'));
});

describe('WorkspaceFilePreview editing with the code editor', () => {
  it('edits in the code editor on a desktop pointer, starting from the text of the file', async () => {
    await openPreview();

    fireEvent.click(screen.getByTitle('editMode'));

    expect(screen.getByTestId('code-editor')).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(monaco.props?.defaultValue).toBe('hello');
  });

  it('keeps the textarea on a touch screen or in a narrow window', async () => {
    desktop.value = false;
    await openPreview();

    fireEvent.click(screen.getByTitle('editMode'));

    expect(screen.queryByTestId('code-editor')).toBeNull();
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('hello');
  });

  it('starts fetching the editor as soon as the Edit button is approached', async () => {
    await openPreview();

    fireEvent.pointerEnter(screen.getByTitle('editMode'));
    fireEvent.focus(screen.getByTitle('editMode'));

    expect(preloadCodeEditor).toHaveBeenCalledTimes(2);
  });

  it('counts what is typed in the code editor as unsaved, and Ctrl+S saves exactly that', async () => {
    await openPreview();
    fireEvent.click(screen.getByTitle('editMode'));
    saveMock.mockResolvedValue({ path: NOTES, name: 'notes.txt', version: 'v2', size: 6, changed: true });

    typeIntoCodeEditor('hello!');
    expect(screen.getByText('unsaved')).toBeTruthy();
    fireEvent.keyDown(window, { key: 's', ctrlKey: true });

    await waitFor(() => expect(saveMock).toHaveBeenCalledWith(WORKSPACE, NOTES, 'hello!', 'v1'));
  });

  it('puts what the agent wrote into a code editor nothing was typed in', async () => {
    await openPreview();
    fireEvent.click(screen.getByTitle('editMode'));
    refreshMock.mockResolvedValue(snapshot('what the agent wrote', 'v2'));

    act(() => {
      window.dispatchEvent(new CustomEvent('workspace-file-changed', { detail: { workspace_path: WORKSPACE } }));
    });

    await waitFor(() => expect(monaco.text).toBe('what the agent wrote'), SOON);
    expect(screen.queryByTestId('workspace-edit-conflict')).toBeNull();
  });

  it('leaves the typed text alone and raises the conflict when the file changes under it', async () => {
    await openPreview();
    fireEvent.click(screen.getByTitle('editMode'));
    typeIntoCodeEditor('my text');
    refreshMock.mockResolvedValue(snapshot('what the agent wrote', 'v2'));

    act(() => {
      window.dispatchEvent(new CustomEvent('workspace-file-changed', { detail: { workspace_path: WORKSPACE } }));
    });

    expect(await screen.findByTestId('workspace-edit-conflict', undefined, SOON)).toBeTruthy();
    expect(monaco.text).toBe('my text');
  });

  it('goes back to the saved text when the edits are discarded', async () => {
    await openPreview();
    fireEvent.click(screen.getByTitle('editMode'));
    typeIntoCodeEditor('my text');

    fireEvent.click(screen.getByTitle('viewMode'));
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'discardChanges' }));

    await waitFor(() => expect(screen.queryByTestId('code-editor')).toBeNull());
    expect(await screen.findByText('hello')).toBeTruthy();
  });
});
