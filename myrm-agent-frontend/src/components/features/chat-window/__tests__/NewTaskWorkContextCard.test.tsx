/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { expectNonNull } from '@/test-utils/expectDefined';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import NewTaskWorkContextCard from '../NewTaskWorkContextCard';

const translations: Record<string, string> = {
  title: 'New Task Work Context',
  modeLocal: 'Local Workspace',
  modeLocalDesc: 'Bind a local folder',
  modeCloud: 'Cloud Sandbox',
  modeCloudDesc: 'Isolated sandbox environment',
  modeCloudBadge: 'Dedicated sandbox storage',
  modeChat: 'Quick Chat',
  modeChatDesc: 'General AI conversation',
  bindWorkspace: 'Select Workspace',
  currentWorkspace: 'Current Workspace',
  noWorkspaceSelected: 'No workspace selected (click to bind)',
  scaffoldBtn: 'Initialize Office Scaffold',
  scaffoldTooltip: 'Create standard folders: {folders}',
  scaffoldSuccess: 'Standard office structure initialized',
  scaffoldFailed: 'Failed to initialize office structure',
  clearWorkspace: 'Unbind',
  changeWorkspace: 'Change',
  invalidPath: 'Invalid path',
  updated: 'Working directory updated',
  cleared: 'Working directory cleared',
  placeholder: 'Enter path...',
  selectThis: 'Select this directory',
  back: 'Back',
  tooBroad: 'This folder is too broad',
};

const stableT = (key: string, values?: Record<string, string>) =>
  (translations[key] ?? key).replace(/\{(\w+)\}/g, (placeholder, name: string) => values?.[name] ?? placeholder);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/chat', () => ({
  browseDirectories: vi.fn(),
  updateChatWorkspaceDir: vi.fn(),
  mkdirInWorkspace: vi.fn(),
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

const mockState = {
  chatId: 'test-chat-1',
  actionMode: 'agent',
  sandboxMode: false,
  workspaceDir: null as string | null,
  setActionMode: vi.fn(),
  setSandboxMode: vi.fn(),
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

const STANDARD_FOLDERS = ['00_原始资料', '01_参考', '02_生成结果', '03_历史版本'];

function mockWorkspaceFolders(names: string[]): void {
  vi.mocked(browseDirectories).mockResolvedValue({
    current: '/home/user/my-project',
    parent: '/home/user',
    entries: names.map((name) => ({ name, path: `/home/user/my-project/${name}`, is_dir: true })),
  });
}

function clickScaffoldButton(): void {
  const scaffoldBtn = screen.getByText('Initialize Office Scaffold').closest('button');
  expectNonNull(scaffoldBtn, 'scaffoldBtn');
  fireEvent.click(scaffoldBtn);
}

describe('NewTaskWorkContextCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockState.actionMode = 'agent';
    mockState.sandboxMode = false;
    mockState.workspaceDir = null;
    (browseDirectories as unknown as ReturnType<typeof vi.fn>).mockImplementation(async (path?: string) => ({
      current: path && path !== '~' ? path : '/home/user/workspace',
      parent: '/home/user',
      entries: [
        { name: 'project-a', path: '/home/user/workspace/project-a', is_dir: true },
        { name: 'project-b', path: '/home/user/workspace/project-b', is_dir: true },
      ],
    }));
    (mkdirInWorkspace as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ path: '/mock', name: 'mock' });
  });

  it('renders mode tabs and switches to cloud sandbox', () => {
    render(<NewTaskWorkContextCard />);
    expect(screen.getByText('Local Workspace')).toBeDefined();
    expect(screen.getByText('Cloud Sandbox')).toBeDefined();
    expect(screen.getByText('Quick Chat')).toBeDefined();

    const cloudBtn = screen.getByText('Cloud Sandbox').closest('button');
    expect(cloudBtn).toBeDefined();
    expectNonNull(cloudBtn, 'cloudBtn');
    fireEvent.click(cloudBtn);

    expect(mockState.setSandboxMode).toHaveBeenCalledWith(true);
    expect(mockState.setActionMode).toHaveBeenCalledWith('agent');
  });

  it.each([
    { name: 'local', state: { sandboxMode: false, actionMode: 'agent' } },
    { name: 'cloud', state: { sandboxMode: true, actionMode: 'agent' } },
    { name: 'chat', state: { sandboxMode: false, actionMode: 'fast' } },
  ])('exposes only the $name tab as pressed for the matching store state', ({ name, state }) => {
    Object.assign(mockState, state);
    render(<NewTaskWorkContextCard />);

    const modes = ['local', 'cloud', 'chat'];
    const pressed = modes.map((mode) => screen.getByTestId(`context-mode-${mode}`).getAttribute('aria-pressed'));

    expect(pressed).toEqual(modes.map((mode) => String(mode === name)));
  });

  it('switches to quick chat mode', () => {
    render(<NewTaskWorkContextCard />);
    const chatBtn = screen.getByText('Quick Chat').closest('button');
    expectNonNull(chatBtn, 'chatBtn');
    fireEvent.click(chatBtn);

    expect(mockState.setSandboxMode).toHaveBeenCalledWith(false);
    expect(mockState.setActionMode).toHaveBeenCalledWith('fast');
    expect(mockState.setWorkspaceDir).toHaveBeenCalledWith(null);
  });

  it('shows scaffold button when workspace directory is set and handles scaffold creation', async () => {
    mockState.workspaceDir = '/home/user/my-project';
    render(<NewTaskWorkContextCard />);

    clickScaffoldButton();

    await waitFor(() => {
      expect(mkdirInWorkspace).toHaveBeenCalledTimes(4);
      for (const folder of STANDARD_FOLDERS) {
        expect(mkdirInWorkspace).toHaveBeenCalledWith('/home/user/my-project', folder);
      }
      expect(toast).toHaveBeenCalledWith({ title: 'Standard office structure initialized' });
    });
  });

  it('names the folders the scaffold creates in the button tooltip', () => {
    mockState.workspaceDir = '/home/user/my-project';
    render(<NewTaskWorkContextCard />);

    expect(screen.getByTitle(`Create standard folders: ${STANDARD_FOLDERS.join(', ')}`)).toBeDefined();
  });

  it('labels the cloud sandbox storage from the locale messages', () => {
    mockState.sandboxMode = true;
    render(<NewTaskWorkContextCard />);

    expect(screen.getByText('Dedicated sandbox storage')).toBeDefined();
  });

  it.each([
    { name: 'local', state: { sandboxMode: false, actionMode: 'agent' }, description: 'Bind a local folder' },
    { name: 'cloud', state: { sandboxMode: true, actionMode: 'agent' }, description: 'Isolated sandbox environment' },
    { name: 'chat', state: { sandboxMode: false, actionMode: 'fast' }, description: 'General AI conversation' },
  ])('states the $name mode description exactly once', ({ state, description }) => {
    Object.assign(mockState, state);
    render(<NewTaskWorkContextCard />);

    expect(screen.getAllByText(description)).toHaveLength(1);
  });

  it('reports success without creating anything when every standard folder already exists', async () => {
    mockState.workspaceDir = '/home/user/my-project';
    mockWorkspaceFolders([...STANDARD_FOLDERS, 'notes']);
    render(<NewTaskWorkContextCard />);

    clickScaffoldButton();

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({ title: 'Standard office structure initialized' });
    });
    expect(mkdirInWorkspace).not.toHaveBeenCalled();
    expect(toast).not.toHaveBeenCalledWith(expect.objectContaining({ variant: 'destructive' }));
  });

  it('creates only the standard folders the workspace lacks', async () => {
    mockState.workspaceDir = '/home/user/my-project';
    mockWorkspaceFolders(STANDARD_FOLDERS.slice(0, 2));
    render(<NewTaskWorkContextCard />);

    clickScaffoldButton();

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({ title: 'Standard office structure initialized' });
    });
    expect(mkdirInWorkspace).toHaveBeenCalledTimes(2);
    expect(mkdirInWorkspace).toHaveBeenCalledWith('/home/user/my-project', '02_生成结果');
    expect(mkdirInWorkspace).toHaveBeenCalledWith('/home/user/my-project', '03_历史版本');
  });

  it('reports failure when a missing folder cannot be created even though others exist', async () => {
    mockState.workspaceDir = '/home/user/my-project';
    mockWorkspaceFolders(STANDARD_FOLDERS.slice(0, 3));
    vi.mocked(mkdirInWorkspace).mockRejectedValue(new Error('Permission denied'));
    render(<NewTaskWorkContextCard />);

    clickScaffoldButton();

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        title: 'Failed to initialize office structure',
        variant: 'destructive',
      });
    });
    expect(mkdirInWorkspace).toHaveBeenCalledTimes(1);
    expect(mkdirInWorkspace).toHaveBeenCalledWith('/home/user/my-project', '03_历史版本');
  });

  it('reports failure without creating anything when the workspace cannot be listed', async () => {
    mockState.workspaceDir = '/home/user/my-project';
    vi.mocked(browseDirectories).mockRejectedValue(new Error('offline'));
    render(<NewTaskWorkContextCard />);

    clickScaffoldButton();

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        title: 'Failed to initialize office structure',
        variant: 'destructive',
      });
    });
    expect(mkdirInWorkspace).not.toHaveBeenCalled();
  });

  it('allows unbinding workspace directory', async () => {
    mockState.workspaceDir = '/home/user/my-project';
    render(<NewTaskWorkContextCard />);

    const unbindBtn = screen.getByTitle('Unbind');
    expect(unbindBtn).toBeDefined();
    fireEvent.click(unbindBtn);

    await waitFor(() => {
      expect(mockState.setWorkspaceDir).toHaveBeenCalledWith(null);
      expect(toast).toHaveBeenCalledWith({ title: 'Working directory cleared' });
    });
  });

  it('handles directory selection via Web popover browse', async () => {
    render(<NewTaskWorkContextCard />);
    const bindBtn = screen.getByText('No workspace selected (click to bind)').closest('button');
    expect(bindBtn).toBeDefined();
    expectNonNull(bindBtn, 'bindBtn');
    fireEvent.click(bindBtn);

    await waitFor(() => {
      expect(browseDirectories).toHaveBeenCalled();
      expect(screen.getByText('project-a')).toBeDefined();
    });

    const projectA = screen.getByText('project-a');
    fireEvent.click(projectA);

    await waitFor(() => {
      expect(browseDirectories).toHaveBeenCalledWith('/home/user/workspace/project-a');
    });

    const selectBtn = screen.getByTitle('Select this directory');
    fireEvent.click(selectBtn);

    await waitFor(() => {
      expect(mockState.setWorkspaceDir).toHaveBeenCalledWith('/home/user/workspace/project-a');
    });
  });

  async function selectBrowsedDirectory(): Promise<void> {
    render(<NewTaskWorkContextCard />);
    const bindBtn = screen.getByText('No workspace selected (click to bind)').closest('button');
    expectNonNull(bindBtn, 'bindBtn');
    fireEvent.click(bindBtn);
    await waitFor(() => {
      expect(screen.getByTitle('Select this directory')).toBeDefined();
    });
    fireEvent.click(screen.getByTitle('Select this directory'));
  }

  it('does not bind a folder the server refuses as too broad', async () => {
    vi.mocked(updateChatWorkspaceDir).mockRejectedValue(
      new ApiError('refused', 40001, [{ field: 'workspace_dir', issue: 'too_broad' }]),
    );
    await selectBrowsedDirectory();

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({ title: 'This folder is too broad', variant: 'destructive' });
    });
    expect(mockState.setWorkspaceDir).not.toHaveBeenCalled();
    expect(mockState.setActionMode).not.toHaveBeenCalled();
  });

  it('still binds locally when the chat cannot be updated yet', async () => {
    vi.mocked(updateChatWorkspaceDir).mockRejectedValue(new Error('chat not created'));
    await selectBrowsedDirectory();

    await waitFor(() => {
      expect(mockState.setWorkspaceDir).toHaveBeenCalledWith('/home/user/workspace');
    });
  });

  it('handles scaffold creation failure gracefully', async () => {
    (mkdirInWorkspace as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Disk full'));
    mockState.workspaceDir = '/home/user/my-project';
    render(<NewTaskWorkContextCard />);

    clickScaffoldButton();

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        title: 'Failed to initialize office structure',
        variant: 'destructive',
      });
    });
  });
});
