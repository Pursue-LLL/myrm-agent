/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchFileExplorer } from '../tabs/WorkbenchFileExplorer';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import * as workbenchService from '@/services/workbench';

const stableT = (key: string, values?: Record<string, unknown>) => {
    if (values && 'id' in values) {
      return `${key}:${String(values.id)}`;
    }
    return key;
  };

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/workbench', () => ({
  fetchWorkspaceFiles: vi.fn(),
  fetchFileContent: vi.fn(),
}));

const mockTreeData: workbenchService.FileTreeResponse = {
  root_path: '/workspace',
  total_files: 2,
  total_dirs: 1,
  nodes: [
    {
      name: 'src',
      path: 'src',
      node_type: 'directory',
      size_bytes: 0,
      modified_at: '2023-11-14T22:13:20Z',
      extension: '',
      children: [
        {
          name: 'index.ts',
          path: 'src/index.ts',
          node_type: 'file',
          size_bytes: 2048,
          modified_at: '2023-11-14T22:13:20Z',
          extension: 'ts',
        },
      ],
    },
    {
      name: 'README.md',
      path: 'README.md',
      node_type: 'file',
      size_bytes: 1024,
      modified_at: '2023-11-14T22:13:20Z',
      extension: 'md',
    },
  ],
};

const fileReply = (
  overrides: Partial<workbenchService.FileContentResponse>,
): workbenchService.FileContentResponse => ({
  path: 'README.md',
  content: '',
  language: 'plaintext',
  size_bytes: 0,
  is_binary: false,
  truncated: false,
  modified_at: '2023-11-14T22:13:20Z',
  ...overrides,
});

describe('WorkbenchFileExplorer component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkbenchStore.setState({
      selectedFilePath: null,
      selectedFileContent: null,
    });
    vi.mocked(workbenchService.fetchWorkspaceFiles).mockResolvedValue(mockTreeData);
    vi.mocked(workbenchService.fetchFileContent).mockResolvedValue({
      path: 'src/index.ts',
      content: 'console.log("hello world");\nexport const x = 1;',
      language: 'typescript',
      size_bytes: 50,
      is_binary: false,
      truncated: false,
      modified_at: '2023-11-14T22:13:20Z',
    });
  });

  it('renders file tree and directory nodes', async () => {
    render(<WorkbenchFileExplorer chatId="chat-1" />);

    await waitFor(() => {
      expect(screen.getByText('src')).toBeDefined();
      expect(screen.getByText('README.md')).toBeDefined();
    });

    expect(screen.getByText('selectFileHint')).toBeDefined();
    expect(workbenchService.fetchWorkspaceFiles).toHaveBeenCalledWith('chat-1', undefined, 3);
  });

  it('says the workspace is unavailable when the tree cannot be loaded', async () => {
    vi.mocked(workbenchService.fetchWorkspaceFiles).mockRejectedValueOnce(new Error('404'));

    render(<WorkbenchFileExplorer chatId="chat-1" />);

    await waitFor(() => {
      expect(screen.getByText('workspaceUnavailable')).toBeDefined();
    });
  });

  it('expands directory when clicked and shows child nodes', async () => {
    render(<WorkbenchFileExplorer chatId="chat-1" />);

    await waitFor(() => {
      expect(screen.getByText('src')).toBeDefined();
    });

    // Initially child not visible until directory is toggled
    expect(screen.queryByText('index.ts')).toBeNull();

    fireEvent.click(screen.getByText('src'));

    await waitFor(() => {
      expect(screen.getByText('index.ts')).toBeDefined();
    });
  });

  it('loads and displays file content when a file node is selected', async () => {
    render(<WorkbenchFileExplorer chatId="chat-1" />);

    await waitFor(() => {
      expect(screen.getByText('README.md')).toBeDefined();
    });

    fireEvent.click(screen.getByText('README.md'));

    await waitFor(() => {
      expect(workbenchService.fetchFileContent).toHaveBeenCalledWith('chat-1', 'README.md');
      expect(screen.getByText(/hello world/)).toBeDefined();
    });
  });

  it('says a binary file cannot be previewed instead of printing its bytes', async () => {
    vi.mocked(workbenchService.fetchFileContent).mockResolvedValueOnce(
      fileReply({ path: 'README.md', is_binary: true, size_bytes: 4096 }),
    );
    render(<WorkbenchFileExplorer chatId="chat-1" />);
    await waitFor(() => expect(screen.getByText('README.md')).toBeDefined());

    fireEvent.click(screen.getByText('README.md'));

    await waitFor(() => expect(screen.getByText('binaryFile')).toBeDefined());
    expect(screen.queryByText('lineCount')).toBeNull();
  });

  it('says when only the beginning of a large file is shown', async () => {
    vi.mocked(workbenchService.fetchFileContent).mockResolvedValueOnce(
      fileReply({ content: 'first line', truncated: true, size_bytes: 5_000_000 }),
    );
    render(<WorkbenchFileExplorer chatId="chat-1" />);
    await waitFor(() => expect(screen.getByText('README.md')).toBeDefined());

    fireEvent.click(screen.getByText('README.md'));

    await waitFor(() => expect(screen.getByText('previewTruncated')).toBeDefined());
    expect(screen.getByText('first line')).toBeDefined();
  });

  it('shows the file clicked last when an earlier file answers later', async () => {
    let answerReadme: (value: workbenchService.FileContentResponse) => void = () => {};
    vi.mocked(workbenchService.fetchFileContent)
      .mockImplementationOnce(() => new Promise((resolve) => (answerReadme = resolve)))
      .mockResolvedValueOnce(fileReply({ path: 'src/index.ts', content: 'index body' }));
    render(<WorkbenchFileExplorer chatId="chat-1" />);
    await waitFor(() => expect(screen.getByText('README.md')).toBeDefined());

    fireEvent.click(screen.getByText('README.md'));
    fireEvent.click(screen.getByText('src'));
    fireEvent.click(await screen.findByText('index.ts'));
    await waitFor(() => expect(screen.getByText('index body')).toBeDefined());
    await act(async () => answerReadme(fileReply({ content: 'readme body' })));

    expect(screen.getByText('index body')).toBeDefined();
    expect(screen.queryByText('readme body')).toBeNull();
  });

  it('drops a file reply that arrives after the workspace session was reset', async () => {
    let answerReadme: (value: workbenchService.FileContentResponse) => void = () => {};
    vi.mocked(workbenchService.fetchFileContent).mockImplementationOnce(
      () => new Promise((resolve) => (answerReadme = resolve)),
    );
    render(<WorkbenchFileExplorer chatId="chat-1" />);
    await waitFor(() => expect(screen.getByText('README.md')).toBeDefined());

    fireEvent.click(screen.getByText('README.md'));
    act(() => useWorkbenchStore.getState().resetWorkspaceSession());
    useWorkbenchStore.getState().setSelectedFile('README.md', null);
    await act(async () => answerReadme(fileReply({ content: 'old chat body' })));

    expect(useWorkbenchStore.getState().selectedFileContent).toBeNull();
  });

  it('filters file nodes based on search query', async () => {
    render(<WorkbenchFileExplorer chatId="chat-1" />);

    await waitFor(() => {
      expect(screen.getByText('src')).toBeDefined();
      expect(screen.getByText('README.md')).toBeDefined();
    });

    const searchInput = screen.getByRole('searchbox');
    fireEvent.change(searchInput, { target: { value: 'README' } });

    expect(screen.getByText('README.md')).toBeDefined();
    expect(screen.queryByText('src')).toBeNull();
  });

  it('reloads file tree when refresh button is clicked', async () => {
    render(<WorkbenchFileExplorer chatId="chat-1" />);

    await waitFor(() => {
      expect(screen.getByText('src')).toBeDefined();
    });

    const refreshBtn = screen.getByRole('button', { name: 'refreshAction' });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(workbenchService.fetchWorkspaceFiles).toHaveBeenCalledTimes(2);
    });
  });
});
