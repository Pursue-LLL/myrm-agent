/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import NewTaskWorkContextCard from '../NewTaskWorkContextCard';

const translations: Record<string, string> = {
  title: 'New Task Work Context',
  modeLocal: 'Local Workspace',
  modeLocalDesc: 'Bind a local folder',
  modeCloud: 'Cloud Sandbox',
  modeCloudDesc: 'Isolated sandbox environment',
  modeChat: 'Quick Chat',
  modeChatDesc: 'General AI conversation',
  bindWorkspace: 'Select Workspace',
  currentWorkspace: 'Current Workspace',
  noWorkspaceSelected: 'No workspace selected (click to bind)',
  scaffoldBtn: 'Initialize Office Scaffold',
  scaffoldTooltip: 'Create standard folders',
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
};

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => translations[key] ?? key,
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

import { browseDirectories, mkdirInWorkspace } from '@/services/chat';
import { toast } from '@/hooks/shared/useToast';

describe('NewTaskWorkContextCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockState.actionMode = 'agent';
    mockState.sandboxMode = false;
    mockState.workspaceDir = null;
    (browseDirectories as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      current: '/home/user/workspace',
      parent: '/home/user',
      entries: [
        { name: 'project-a', path: '/home/user/workspace/project-a', is_dir: true },
        { name: 'project-b', path: '/home/user/workspace/project-b', is_dir: true },
      ],
    });
    (mkdirInWorkspace as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ path: '/mock', name: 'mock' });
  });

  it('renders mode tabs and switches to cloud sandbox', () => {
    render(<NewTaskWorkContextCard />);
    expect(screen.getByText('Local Workspace')).toBeDefined();
    expect(screen.getByText('Cloud Sandbox')).toBeDefined();
    expect(screen.getByText('Quick Chat')).toBeDefined();

    const cloudBtn = screen.getByText('Cloud Sandbox').closest('button');
    expect(cloudBtn).toBeDefined();
    fireEvent.click(cloudBtn!);

    expect(mockState.setSandboxMode).toHaveBeenCalledWith(true);
    expect(mockState.setActionMode).toHaveBeenCalledWith('agent');
  });

  it('switches to quick chat mode', () => {
    render(<NewTaskWorkContextCard />);
    const chatBtn = screen.getByText('Quick Chat').closest('button');
    fireEvent.click(chatBtn!);

    expect(mockState.setSandboxMode).toHaveBeenCalledWith(false);
    expect(mockState.setActionMode).toHaveBeenCalledWith('fast');
    expect(mockState.setWorkspaceDir).toHaveBeenCalledWith(null);
  });

  it('shows scaffold button when workspace directory is set and handles scaffold creation', async () => {
    mockState.workspaceDir = '/home/user/my-project';
    render(<NewTaskWorkContextCard />);

    const scaffoldBtn = screen.getByText('Initialize Office Scaffold').closest('button');
    expect(scaffoldBtn).toBeDefined();

    fireEvent.click(scaffoldBtn!);

    await waitFor(() => {
      expect(mkdirInWorkspace).toHaveBeenCalledTimes(4);
      expect(mkdirInWorkspace).toHaveBeenCalledWith('/home/user/my-project', '00_原始资料');
      expect(mkdirInWorkspace).toHaveBeenCalledWith('/home/user/my-project', '01_参考');
      expect(mkdirInWorkspace).toHaveBeenCalledWith('/home/user/my-project', '02_生成结果');
      expect(mkdirInWorkspace).toHaveBeenCalledWith('/home/user/my-project', '03_历史版本');
      expect(toast).toHaveBeenCalledWith({ title: 'Standard office structure initialized' });
    });
  });

  it('allows unbinding workspace directory', () => {
    mockState.workspaceDir = '/home/user/my-project';
    render(<NewTaskWorkContextCard />);

    const unbindBtn = screen.getByTitle('Unbind');
    expect(unbindBtn).toBeDefined();
    fireEvent.click(unbindBtn);

    expect(mockState.setWorkspaceDir).toHaveBeenCalledWith(null);
    expect(toast).toHaveBeenCalledWith({ title: 'Working directory cleared' });
  });
});
