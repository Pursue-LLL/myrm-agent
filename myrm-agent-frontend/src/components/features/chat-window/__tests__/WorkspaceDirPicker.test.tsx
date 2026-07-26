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
};

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => translations[key] ?? key,
}));

vi.mock('@/services/chat', () => ({
  browseDirectories: vi.fn(),
  updateChatWorkspaceDir: vi.fn(),
}));

vi.mock('@/hooks/useToast', () => ({
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

import { browseDirectories, updateChatWorkspaceDir } from '@/services/chat';
import { toast } from '@/hooks/useToast';

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
  });

  it('renders trigger button in agent mode', () => {
    renderPicker();
    expect(screen.getByTitle('Set a working directory')).toBeInTheDocument();
  });

  it('returns null when actionMode is not agent', () => {
    mockState.actionMode = 'chat';
    const { container } = renderPicker();
    expect(container.innerHTML).toBe('');
  });

  it('opens popover and loads directory on click', async () => {
    renderPicker();
    fireEvent.click(screen.getByTitle('Set a working directory'));

    await waitFor(() => {
      expect(browseDirectories).toHaveBeenCalledWith('~');
    });

    expect(screen.getByText('alpha')).toBeInTheDocument();
    expect(screen.getByText('beta')).toBeInTheDocument();
  });

  it('navigates on Enter in path input', async () => {
    renderPicker();
    fireEvent.click(screen.getByTitle('Set a working directory'));

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
    fireEvent.click(screen.getByTitle('Set a working directory'));

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
    fireEvent.click(screen.getByTitle('Set a working directory'));

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
    fireEvent.click(screen.getByTitle('Set a working directory'));

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
    fireEvent.click(screen.getByTitle('Set a working directory'));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Filter directories...')).toBeInTheDocument();
    });

    const filterInput = screen.getByPlaceholderText('Filter directories...');
    fireEvent.change(filterInput, { target: { value: 'dir-3' } });

    expect(screen.getByText('dir-3')).toBeInTheDocument();
    expect(screen.queryByText('dir-0')).not.toBeInTheDocument();
  });

  it('shows error toast on invalid path', async () => {
    vi.mocked(browseDirectories).mockRejectedValue(new Error('not found'));

    renderPicker();
    fireEvent.click(screen.getByTitle('Set a working directory'));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({ title: 'Invalid path', variant: 'destructive' });
    });
  });
});
