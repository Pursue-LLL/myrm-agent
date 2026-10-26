/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry, WorkspaceFileSearchResponse } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { WorkbenchFiles } from '../tabs/WorkbenchFiles';

const WORKSPACE = '/vault/chat-1';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

interface BrowserStubProps {
  workspacePath: string;
  files: FileEntry[];
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
    return ({ workspacePath, files, error, onFileClick, onLoadChildren }: BrowserStubProps) => (
      <div data-testid="file-browser" data-workspace={workspacePath}>
        {error ? <span role="alert">{error}</span> : null}
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
  });

  afterEach(() => {
    vi.useRealTimers();
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

  it('replaces a raw load failure with the localized message', () => {
    hookState.error = 'ECONNREFUSED 127.0.0.1:8080';

    render(<WorkbenchFiles />);

    expect(screen.getByRole('alert').textContent).toBe('workspaceUnavailable');
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
});
