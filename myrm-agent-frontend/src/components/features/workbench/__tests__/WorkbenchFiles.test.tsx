/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { filterFileEntries, WorkbenchFiles } from '../tabs/WorkbenchFiles';

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
    return ({ workspacePath, files, error, onFileClick }: BrowserStubProps) => (
      <div data-testid="file-browser" data-workspace={workspacePath}>
        {error ? <span role="alert">{error}</span> : null}
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
}

const hookState: HookState = {
  files: [],
  loading: false,
  error: null,
  truncated: false,
  refresh: vi.fn(async () => {}),
};
const useWorkspaceFilesMock = vi.fn((_workspacePath: string | null | undefined) => hookState);

vi.mock('@/components/features/workspace-browser/useWorkspaceFiles', () => ({
  useWorkspaceFiles: (workspacePath: string | null | undefined) => useWorkspaceFilesMock(workspacePath),
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

describe('filterFileEntries', () => {
  it('returns every entry for a blank query', () => {
    expect(filterFileEntries(TREE, '   ', WORKSPACE)).toBe(TREE);
  });

  it('matches names case-insensitively', () => {
    const result = filterFileEntries(TREE, 'readme', WORKSPACE);

    expect(result.map((item) => item.name)).toEqual(['README.md']);
  });

  it('keeps the directories that lead to a match but only the matching children', () => {
    const result = filterFileEntries(TREE, 'util', WORKSPACE);

    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('src');
    expect(result[0].children?.map((item) => item.name)).toEqual(['util.ts']);
  });

  it('keeps the whole content of a directory whose own path matches', () => {
    const result = filterFileEntries(TREE, 'src', WORKSPACE);

    expect(result[0].children?.map((item) => item.name)).toEqual(['index.ts', 'util.ts']);
  });

  it("does not match on the workspace root's own folder names", () => {
    expect(filterFileEntries(TREE, 'vault', WORKSPACE)).toEqual([]);
    expect(filterFileEntries(TREE, 'chat-1', WORKSPACE)).toEqual([]);
  });

  it('falls back to the file name for entries outside the workspace root', () => {
    const outside: FileEntry[] = [{ ...entry('a.txt', 'file'), path: '/elsewhere/vault/a.txt' }];

    expect(filterFileEntries(outside, 'vault', WORKSPACE)).toEqual([]);
    expect(filterFileEntries(outside, 'a.txt', WORKSPACE)).toHaveLength(1);
  });
});

describe('WorkbenchFiles', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(hookState, { files: TREE, loading: false, error: null, truncated: false });
    useChatStore.setState({ chatId: 'chat-1', workspaceDir: WORKSPACE });
  });

  it('browses the workspace of the current chat through the shared browser', () => {
    render(<WorkbenchFiles />);

    expect(useWorkspaceFilesMock).toHaveBeenCalledWith(WORKSPACE);
    expect(screen.getByTestId('file-browser').getAttribute('data-workspace')).toBe(WORKSPACE);
    expect(screen.getByText('README.md')).toBeDefined();
    expect(screen.getByText('index.ts')).toBeDefined();
  });

  it('says there is no workspace folder yet instead of browsing anything', () => {
    useChatStore.setState({ workspaceDir: null });

    render(<WorkbenchFiles />);

    expect(useWorkspaceFilesMock).toHaveBeenCalledWith(null);
    expect(screen.getByText('workspaceUnavailable')).toBeDefined();
    expect(screen.queryByTestId('file-browser')).toBeNull();
    expect(screen.queryByRole('searchbox')).toBeNull();
  });

  it('replaces a raw load failure with the localized message', () => {
    hookState.error = 'ECONNREFUSED 127.0.0.1:8080';

    render(<WorkbenchFiles />);

    expect(screen.getByRole('alert').textContent).toBe('workspaceUnavailable');
    expect(screen.queryByText(/ECONNREFUSED/)).toBeNull();
  });

  it('narrows the tree to the files matching the search query', () => {
    render(<WorkbenchFiles />);

    fireEvent.change(screen.getByRole('searchbox', { name: 'searchPlaceholder' }), { target: { value: 'README' } });

    expect(screen.getByText('README.md')).toBeDefined();
    expect(screen.queryByText('src')).toBeNull();
    expect(screen.queryByText('emptyResults')).toBeNull();
  });

  it('reports an unmatched search while keeping the browser mounted', () => {
    render(<WorkbenchFiles />);

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'no-such-file' } });

    expect(screen.getByText('emptyResults')).toBeDefined();
    expect(screen.getByTestId('file-browser')).toBeDefined();

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '' } });

    expect(screen.queryByText('emptyResults')).toBeNull();
    expect(screen.getByText('README.md')).toBeDefined();
  });

  it('does not call an empty workspace an unmatched search', () => {
    hookState.files = [];

    render(<WorkbenchFiles />);
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'anything' } });

    expect(screen.queryByText('emptyResults')).toBeNull();
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
