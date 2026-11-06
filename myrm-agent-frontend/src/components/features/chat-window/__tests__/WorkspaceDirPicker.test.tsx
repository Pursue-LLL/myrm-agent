/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import WorkspaceDirPicker from '../WorkspaceDirPicker';

const translations: Record<string, string> = {
  label: 'Working Directory',
  placeholder: 'Enter path or browse below...',
  tooltip: 'Set a working directory',
  change: 'Change',
  clear: 'Clear',
  browse: 'Browse',
  back: 'Back',
  selectThis: 'Select this directory',
  noSubdirs: 'No subdirectories',
  invalidPath: 'Invalid path',
  updated: 'Working directory updated',
  cleared: 'Working directory cleared',
  recent: 'Recent',
  filter: 'Filter directories...',
  sessionDefault: 'Session folder',
  sessionDefaultHint: 'No folder needed: the agent works only inside this chat own folder',
  scaffoldOffice: 'Create office folders',
  scaffoldDone: 'Office folders are ready',
  scaffoldFailed: 'Could not create the office folders',
  tooBroad: 'This folder is too broad',
  dangerous: 'This folder cannot be used',
};

const TRIGGER = 'workspace-dir-trigger';

const stableT = (key: string) => translations[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/chat', () => ({
  browseDirectories: vi.fn(),
  mkdirInWorkspace: vi.fn(),
  updateChatWorkspaceDir: vi.fn(),
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

const mockState = {
  chatId: 'test-chat-1',
  actionMode: 'agent' as string,
  workspaceDir: null as string | null,
  setWorkspaceDir: vi.fn(),
};

vi.mock('@/store/useChatStore', () => {
  const fn = (selector: (s: typeof mockState) => unknown) => selector(mockState);
  fn.getState = () => mockState;
  return { default: fn };
});

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: vi.fn(() => false),
}));

import { browseDirectories, mkdirInWorkspace, updateChatWorkspaceDir } from '@/services/chat';
import { ApiError } from '@/lib/api';
import { toast } from '@/hooks/shared/useToast';

function renderPicker() {
  return render(<WorkspaceDirPicker />);
}

describe('WorkspaceDirPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockState.actionMode = 'agent';
    mockState.workspaceDir = null;
    vi.mocked(browseDirectories).mockResolvedValue({
      current: '/home/user/projects',
      parent: '/home/user',
      entries: [
        { name: 'alpha', path: '/home/user/projects/alpha', is_dir: true },
        { name: 'beta', path: '/home/user/projects/beta', is_dir: true },
      ],
    });
    vi.mocked(updateChatWorkspaceDir).mockResolvedValue({
      workspace_dir: '/home/user/projects',
    });
    vi.mocked(mkdirInWorkspace).mockResolvedValue({
      path: '/home/user/projects/00_原始资料',
      name: '00_原始资料',
    });
  });

  it('renders the workspace row in agent mode and names the session folder while unbound', () => {
    renderPicker();
    const trigger = screen.getByTestId(TRIGGER);

    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveTextContent('Session folder');
    expect(trigger).toHaveAttribute('title', translations.sessionDefaultHint);
  });

  it('shows the compact path instead of the session label once a folder is bound', () => {
    mockState.workspaceDir = '/home/user/projects';
    renderPicker();
    const trigger = screen.getByTestId(TRIGGER);

    expect(trigger).toHaveTextContent('~/projects');
    expect(trigger).toHaveAttribute('title', translations.tooltip);
  });

  it('returns null when actionMode is not agent', () => {
    mockState.actionMode = 'chat';
    const { container } = renderPicker();
    expect(container.innerHTML).toBe('');
  });

  it('opens popover and loads directory on click', async () => {
    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(browseDirectories).toHaveBeenCalledWith('~');
    });

    expect(screen.getByText('alpha')).toBeInTheDocument();
    expect(screen.getByText('beta')).toBeInTheDocument();
  });

  it('navigates on Enter in path input', async () => {
    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Enter path or browse below...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Enter path or browse below...');
    fireEvent.change(input, { target: { value: '/tmp/test' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      expect(browseDirectories).toHaveBeenCalledWith('/tmp/test');
    });
  });

  it('applies directory on select button click', async () => {
    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(screen.getByTitle('Select this directory')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle('Select this directory'));

    await waitFor(() => {
      expect(updateChatWorkspaceDir).toHaveBeenCalledWith('test-chat-1', '/home/user/projects');
    });
    expect(toast).toHaveBeenCalledWith({ title: 'Working directory updated' });
  });

  it('stores selected dir in recent dirs', async () => {
    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(screen.getByTitle('Select this directory')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle('Select this directory'));

    await waitFor(() => {
      expect(updateChatWorkspaceDir).toHaveBeenCalled();
    });

    const recent = JSON.parse(localStorage.getItem('myrm.workspaceDirPicker.recent') || '[]');
    expect(recent).toContain('/home/user/projects');
  });

  it('keeps the chosen folder when storage refuses the recent-list write', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError');
    });
    try {
      renderPicker();
      fireEvent.click(screen.getByTestId(TRIGGER));
      await waitFor(() => {
        expect(screen.getByTitle('Select this directory')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTitle('Select this directory'));

      await waitFor(() => {
        expect(toast).toHaveBeenCalledWith({ title: 'Working directory updated' });
      });
      expect(toast).not.toHaveBeenCalledWith(expect.objectContaining({ variant: 'destructive' }));
      expect(mockState.setWorkspaceDir).not.toHaveBeenCalledWith(null);
    } finally {
      setItem.mockRestore();
    }
  });

  it('reads the recent list only once the popover is open', async () => {
    localStorage.setItem('myrm.workspaceDirPicker.recent', JSON.stringify(['/home/user/notes']));
    const getItem = vi.spyOn(Storage.prototype, 'getItem');
    try {
      renderPicker();
      expect(getItem).not.toHaveBeenCalledWith('myrm.workspaceDirPicker.recent');

      fireEvent.click(screen.getByTestId(TRIGGER));

      expect(await screen.findByText('~/notes')).toBeInTheDocument();
      expect(getItem).toHaveBeenCalledWith('myrm.workspaceDirPicker.recent');
    } finally {
      getItem.mockRestore();
    }
  });

  it('names the parent-folder button instead of leaving an anonymous icon', async () => {
    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    expect(await screen.findByRole('button', { name: 'Back' })).toBeInTheDocument();
  });

  it('compacts a Windows path by its last two folders', () => {
    mockState.workspaceDir = 'D:\\work\\clients\\acme\\reports';
    renderPicker();

    expect(screen.getByTestId(TRIGGER)).toHaveTextContent('…/acme/reports');
  });

  it('shows filter input when entries exceed 8', async () => {
    vi.mocked(browseDirectories).mockResolvedValue({
      current: '/home/user/projects',
      parent: '/home/user',
      entries: Array.from({ length: 10 }, (_, i) => ({
        name: `dir-${i}`,
        path: `/home/user/projects/dir-${i}`,
        is_dir: true,
      })),
    });

    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Filter directories...')).toBeInTheDocument();
    });
  });

  it('filters directories by query', async () => {
    vi.mocked(browseDirectories).mockResolvedValue({
      current: '/home/user/projects',
      parent: '/home/user',
      entries: Array.from({ length: 10 }, (_, i) => ({
        name: `dir-${i}`,
        path: `/home/user/projects/dir-${i}`,
        is_dir: true,
      })),
    });

    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Filter directories...')).toBeInTheDocument();
    });

    const filterInput = screen.getByPlaceholderText('Filter directories...');
    fireEvent.change(filterInput, { target: { value: 'dir-3' } });

    expect(screen.getByText('dir-3')).toBeInTheDocument();
    expect(screen.queryByText('dir-0')).not.toBeInTheDocument();
  });

  it.each([
    ['too_broad', 'This folder is too broad'],
    ['dangerous', 'This folder cannot be used'],
  ])('explains a folder the server refuses as %s and keeps the current directory', async (issue, message) => {
    vi.mocked(updateChatWorkspaceDir).mockRejectedValue(
      new ApiError('refused', 40001, [{ field: 'workspace_dir', issue }]),
    );
    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(screen.getByTitle('Select this directory')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTitle('Select this directory'));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({ title: message, variant: 'destructive' });
    });
    // The optimistic write is rolled back to the folder that was bound before the attempt.
    expect(mockState.setWorkspaceDir).toHaveBeenLastCalledWith(null);
    expect(localStorage.getItem('myrm.workspaceDirPicker.recent')).toBeNull();
  });

  it('keeps the generic message for other failures', async () => {
    vi.mocked(updateChatWorkspaceDir).mockRejectedValue(new Error('network down'));
    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(screen.getByTitle('Select this directory')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTitle('Select this directory'));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({ title: 'Invalid path', variant: 'destructive' });
    });
  });

  it('keeps the folder locally when the chat row does not exist yet, so the first message carries it', async () => {
    vi.mocked(updateChatWorkspaceDir).mockRejectedValue(new ApiError('Chat session not found', 404));
    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(screen.getByTitle('Select this directory')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTitle('Select this directory'));

    await waitFor(() => {
      expect(mockState.setWorkspaceDir).toHaveBeenLastCalledWith('/home/user/projects');
    });
    expect(toast).not.toHaveBeenCalled();
    expect(JSON.parse(localStorage.getItem('myrm.workspaceDirPicker.recent') || '[]')).toContain('/home/user/projects');
  });

  it('creates only the office folders the workspace is missing', async () => {
    mockState.workspaceDir = '/home/user/projects';
    vi.mocked(browseDirectories).mockResolvedValue({
      current: '/home/user/projects',
      parent: '/home/user',
      entries: [
        { name: '00_原始资料', path: '/home/user/projects/00_原始资料', is_dir: true },
        { name: 'alpha', path: '/home/user/projects/alpha', is_dir: true },
      ],
    });
    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(screen.getByText('Create office folders')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Create office folders'));

    await waitFor(() => {
      expect(mkdirInWorkspace).toHaveBeenCalledTimes(3);
    });
    expect(vi.mocked(mkdirInWorkspace).mock.calls.map((call) => call[1])).toEqual([
      '01_参考',
      '02_生成结果',
      '03_历史版本',
    ]);
    expect(toast).toHaveBeenCalledWith({ title: 'Office folders are ready' });
  });

  it('shows error toast on invalid path', async () => {
    vi.mocked(browseDirectories).mockRejectedValue(new Error('not found'));

    renderPicker();
    fireEvent.click(screen.getByTestId(TRIGGER));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({ title: 'Invalid path', variant: 'destructive' });
    });
  });
});
