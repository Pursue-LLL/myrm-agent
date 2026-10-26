/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry, WorkspaceFileSearchResponse } from '@/services/chat';
import type { WorkspaceTextSnapshot } from '@/services/workspaceText';
import useChatStore from '@/store/useChatStore';
import { useWorkspaceDraftStore } from '@/store/useWorkspaceDraftStore';
import { WorkbenchFiles } from '../tabs/WorkbenchFiles';

const WORKSPACE = '/vault/chat-1';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

interface BrowserStubProps {
  workspacePath: string;
  files: FileEntry[];
  loading?: boolean;
  error?: string | null;
  onFileClick?: (file: FileEntry) => void;
  onLoadChildren: (dirPath: string) => Promise<void>;
}

interface PreviewStubProps {
  file: FileEntry;
  workspace: string;
  onClose: () => void;
}

const renderEntries = (entries: FileEntry[], onFileClick?: (file: FileEntry) => void): React.ReactNode =>
  entries.map((entry) => (
    <div key={entry.path}>
      <button type="button" onClick={() => onFileClick?.(entry)}>
        {entry.name}
      </button>
      {entry.children ? renderEntries(entry.children, onFileClick) : null}
    </div>
  ));

vi.mock('next/dynamic', () => ({
  default: (loader: () => Promise<unknown>) => {
    if (String(loader).includes('WorkspaceFilePreview')) {
      return ({ file, workspace, onClose }: PreviewStubProps) => (
        <div data-testid="file-preview" data-workspace={workspace}>
          <span>{file.path}</span>
          <button type="button" onClick={onClose}>
            close-preview
          </button>
        </div>
      );
    }
    return ({ workspacePath, files, loading, error, onFileClick, onLoadChildren }: BrowserStubProps) => (
      <div
        data-testid="file-browser"
        data-workspace={workspacePath}
        data-loading={String(Boolean(loading))}
        data-error={error ?? ''}
      >
        <button type="button" onClick={() => void onLoadChildren(`${workspacePath}/deep`)}>
          open-deep-folder
        </button>
        {renderEntries(files, onFileClick)}
      </div>
    );
  },
}));

interface HookState {
  files: FileEntry[];
  loading: boolean;
  error: string | null;
  truncated: boolean;
  refresh: () => Promise<void>;
  loadChildren: (dirPath: string) => Promise<void>;
}

const hookState: HookState = {
  files: [],
  loading: false,
  error: null,
  truncated: false,
  refresh: vi.fn(async () => {}),
  loadChildren: vi.fn(async () => {}),
};
const useWorkspaceFilesMock = vi.fn((_workspacePath: string | null | undefined) => hookState);

vi.mock('@/components/features/workspace-browser/useWorkspaceFiles', () => ({
  useWorkspaceFiles: (workspacePath: string | null | undefined) => useWorkspaceFilesMock(workspacePath),
}));

const searchWorkspaceFilesMock = vi.fn(
  async (_workspace: string, _query: string): Promise<WorkspaceFileSearchResponse> => ({ results: [], total: 0 }),
);

vi.mock('@/services/chat', () => ({
  searchWorkspaceFiles: (workspace: string, query: string) => searchWorkspaceFilesMock(workspace, query),
}));

const entry = (path: string, type: FileEntry['type'], children: FileEntry[] | null = null): FileEntry => ({
  name: path.split('/').pop() ?? path,
  path: `${WORKSPACE}/${path}`,
  type,
  size: type === 'file' ? 10 : null,
  mtime: null,
  is_text: type === 'file' ? true : null,
  children,
});

const TREE: FileEntry[] = [
  entry('src', 'directory', [entry('src/index.ts', 'file'), entry('src/util.ts', 'file')]),
  entry('README.md', 'file'),
];

const DEEP_MATCH = {
  name: 'Hello.ts',
  path: `${WORKSPACE}/src/components/Hello.ts`,
  relative_path: 'src/components/Hello.ts',
  size: 84,
};

/** Types a query and lets the search debounce elapse and the answer arrive. */
async function search(query: string): Promise<void> {
  fireEvent.change(screen.getByRole('searchbox', { name: 'searchPlaceholder' }), { target: { value: query } });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });
}

describe('WorkbenchFiles', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    Object.assign(hookState, { files: TREE, loading: false, error: null, truncated: false });
    searchWorkspaceFilesMock.mockResolvedValue({ results: [DEEP_MATCH], total: 1 });
    useChatStore.setState({ chatId: 'chat-1', workspaceDir: WORKSPACE });
    useWorkspaceDraftStore.setState({ drafts: {} });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('browses the workspace of the current chat through the shared browser', () => {
    render(<WorkbenchFiles />);

    expect(useWorkspaceFilesMock).toHaveBeenCalledWith(WORKSPACE);
    expect(screen.getByTestId('file-browser').getAttribute('data-workspace')).toBe(WORKSPACE);
    expect(screen.getByText('README.md')).toBeDefined();
    expect(screen.getByText('index.ts')).toBeDefined();
  });

  it('lets the browser load the folders the first scan did not reach', () => {
    render(<WorkbenchFiles />);

    fireEvent.click(screen.getByText('open-deep-folder'));

    expect(hookState.loadChildren).toHaveBeenCalledWith(`${WORKSPACE}/deep`);
  });

  it('says there is no workspace folder yet instead of browsing anything', () => {
    useChatStore.setState({ workspaceDir: null });

    render(<WorkbenchFiles />);

    expect(useWorkspaceFilesMock).toHaveBeenCalledWith(null);
    expect(screen.getByText('workspaceUnavailable')).toBeDefined();
    expect(screen.queryByTestId('file-browser')).toBeNull();
    expect(screen.queryByRole('searchbox')).toBeNull();
    expect(searchWorkspaceFilesMock).not.toHaveBeenCalled();
  });

  it('hands the scan state to the browser, which words a failure for the user itself', () => {
    Object.assign(hookState, { loading: true, error: 'ECONNREFUSED 127.0.0.1:8080' });

    render(<WorkbenchFiles />);

    const browser = screen.getByTestId('file-browser');
    expect(browser.getAttribute('data-loading')).toBe('true');
    expect(browser.getAttribute('data-error')).toBe('ECONNREFUSED 127.0.0.1:8080');
    expect(screen.queryByText(/ECONNREFUSED/)).toBeNull();
  });

  it('searches the whole workspace by the typed name once typing pauses', async () => {
    render(<WorkbenchFiles />);

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'hello' } });
    expect(searchWorkspaceFilesMock).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(searchWorkspaceFilesMock).toHaveBeenCalledTimes(1);
    expect(searchWorkspaceFilesMock).toHaveBeenCalledWith(WORKSPACE, 'hello');
    const results = within(screen.getByRole('list'));
    expect(results.getByText('Hello.ts')).toBeDefined();
    expect(results.getByText('src/components')).toBeDefined();
    expect(screen.getByTestId('file-browser')).toBeDefined();
  });

  it('searches for the newest text only while the user keeps typing', async () => {
    render(<WorkbenchFiles />);

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'he' } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'hello' } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(searchWorkspaceFilesMock).toHaveBeenCalledTimes(1);
    expect(searchWorkspaceFilesMock).toHaveBeenCalledWith(WORKSPACE, 'hello');
  });

  it('does not search for a blank query', async () => {
    render(<WorkbenchFiles />);

    await search('   ');

    expect(searchWorkspaceFilesMock).not.toHaveBeenCalled();
    expect(screen.queryByRole('list')).toBeNull();
  });

  it('reports an unmatched search and goes back to the tree when the query is cleared', async () => {
    searchWorkspaceFilesMock.mockResolvedValue({ results: [], total: 0 });
    render(<WorkbenchFiles />);

    await search('no-such-file');

    expect(screen.getByText('emptyResults')).toBeDefined();
    expect(screen.getByTestId('file-browser')).toBeDefined();

    await search('');

    expect(screen.queryByText('emptyResults')).toBeNull();
    expect(screen.getByText('README.md')).toBeDefined();
  });

  it('explains a failed search in the user language without the raw error', async () => {
    searchWorkspaceFilesMock.mockRejectedValue(new Error('ECONNREFUSED 127.0.0.1:8080'));
    render(<WorkbenchFiles />);

    await search('hello');

    expect(screen.getByText('searchFailed')).toBeDefined();
    expect(screen.queryByText(/ECONNREFUSED/)).toBeNull();
  });

  it('previews a clicked match over the results and returns to them on close', async () => {
    render(<WorkbenchFiles />);
    await search('hello');

    fireEvent.click(within(screen.getByRole('list')).getByText('Hello.ts'));

    const preview = screen.getByTestId('file-preview');
    expect(preview.getAttribute('data-workspace')).toBe(WORKSPACE);
    expect(preview.textContent).toContain(DEEP_MATCH.path);

    fireEvent.click(screen.getByText('close-preview'));

    expect(screen.queryByTestId('file-preview')).toBeNull();
    expect(within(screen.getByRole('list')).getByText('Hello.ts')).toBeDefined();
  });

  it('previews a clicked file over the tree and returns to the tree on close', () => {
    render(<WorkbenchFiles />);

    fireEvent.click(screen.getByText('README.md'));

    const preview = screen.getByTestId('file-preview');
    expect(preview.getAttribute('data-workspace')).toBe(WORKSPACE);
    expect(preview.textContent).toContain(`${WORKSPACE}/README.md`);

    fireEvent.click(screen.getByText('close-preview'));

    expect(screen.queryByTestId('file-preview')).toBeNull();
    expect(screen.getByTestId('file-browser')).toBeDefined();
  });

  it('does not open a preview for a directory', () => {
    render(<WorkbenchFiles />);

    fireEvent.click(screen.getByText('src'));

    expect(screen.queryByTestId('file-preview')).toBeNull();
  });

  describe('coming back to text that was left unsaved', () => {
    const keptSnapshot = (path: string): WorkspaceTextSnapshot => ({
      path,
      name: path.split('/').pop() ?? path,
      content: 'saved text',
      version: 'v1',
      size: 10,
      editable: true,
      readonlyReason: null,
      truncated: false,
    });
    const keepUnsaved = (path: string, workspace = WORKSPACE) =>
      useWorkspaceDraftStore.getState().keep(workspace, path, keptSnapshot(path), 'unsaved text');

    it('opens the file the unsaved text belongs to as soon as the tab appears', () => {
      keepUnsaved(`${WORKSPACE}/notes/todo.md`);

      render(<WorkbenchFiles />);

      const preview = screen.getByTestId('file-preview');
      expect(preview.getAttribute('data-workspace')).toBe(WORKSPACE);
      expect(preview.textContent).toContain(`${WORKSPACE}/notes/todo.md`);
    });

    it('opens the file edited last when several have unsaved text', () => {
      vi.setSystemTime(1_000);
      keepUnsaved(`${WORKSPACE}/first.md`);
      vi.setSystemTime(2_000);
      keepUnsaved(`${WORKSPACE}/second.md`);

      render(<WorkbenchFiles />);

      expect(screen.getByTestId('file-preview').textContent).toContain(`${WORKSPACE}/second.md`);
    });

    it('shows the tree when the unsaved text is in another workspace', () => {
      keepUnsaved('/vault/chat-2/other.md', '/vault/chat-2');

      render(<WorkbenchFiles />);

      expect(screen.queryByTestId('file-preview')).toBeNull();
      expect(screen.getByText('README.md')).toBeDefined();
    });

    it('does not take the preview back once the user closed it', () => {
      keepUnsaved(`${WORKSPACE}/notes/todo.md`);
      const { rerender } = render(<WorkbenchFiles />);

      fireEvent.click(screen.getByText('close-preview'));
      rerender(<WorkbenchFiles />);

      expect(screen.queryByTestId('file-preview')).toBeNull();
    });

    it('opens the file of the new workspace when the chat moves to one that has unsaved text', () => {
      useChatStore.setState({ workspaceDir: null });
      keepUnsaved(`${WORKSPACE}/notes/todo.md`);
      const { rerender } = render(<WorkbenchFiles />);
      expect(screen.queryByTestId('file-preview')).toBeNull();

      act(() => useChatStore.setState({ workspaceDir: WORKSPACE }));
      rerender(<WorkbenchFiles />);

      expect(screen.getByTestId('file-preview').textContent).toContain(`${WORKSPACE}/notes/todo.md`);
    });
  });
});
