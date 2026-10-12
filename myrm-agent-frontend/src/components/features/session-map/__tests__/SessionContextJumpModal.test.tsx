/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SessionContextJumpModal } from '../SessionContextJumpModal';
import type { SessionNode, ProjectCluster } from '@/services/sessionMap';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconX: () => <span data-testid="icon-x" />,
  IconSparkles: () => <span data-testid="icon-sparkles" />,
  IconFolder: () => <span data-testid="icon-folder" />,
  IconActivity: () => <span data-testid="icon-activity" />,
  IconCheck: () => <span data-testid="icon-check" />,
}));

describe('SessionContextJumpModal component', () => {
  const mockSession: SessionNode = {
    id: 'sess-target-99',
    title: 'Security Vulnerability Patch',
    agent_id: 'agent-sec-01',
    agent_name: 'SecAuditor',
    state: 'working',
    current_task: 'Patching SQL injection and sandbox escape vector',
    tokens_used: 28400,
    last_active_at: '2026-10-12T15:30:00Z',
    tags: ['cve', 'security'],
    workspace_dir: '/workspace/security-patch',
  };

  const mockProject: ProjectCluster = {
    id: 'proj-sec',
    name: 'Security Core',
    description: 'Kernel and Sandbox Isolation',
    color: '#ef4444',
    workspace_path: '/workspace/security-core',
    git_repo_url: 'https://github.com/myrm-agent/security.git',
    sessions: [mockSession],
    active_agent_count: 1,
    total_tokens: 28400,
  };

  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    session: mockSession,
    project: mockProject,
    onJumpIn: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not render when isOpen is false or session is null', () => {
    const { container: c1 } = render(
      <SessionContextJumpModal {...defaultProps} isOpen={false} />,
    );
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(
      <SessionContextJumpModal {...defaultProps} session={null} />,
    );
    expect(c2.firstChild).toBeNull();
  });

  it('renders session details, project name, path, agent, and active task', () => {
    render(<SessionContextJumpModal {...defaultProps} />);

    expect(screen.getByText('Security Vulnerability Patch')).toBeDefined();
    expect(screen.getByText('Security Core')).toBeDefined();
    expect(screen.getByText('SecAuditor')).toBeDefined();
    expect(screen.getByText(/Patching SQL injection/)).toBeDefined();
    expect(screen.getByText(/28,400/)).toBeDefined();
    expect(screen.getByText('#cve')).toBeDefined();
    expect(screen.getByText('#security')).toBeDefined();
  });

  it('triggers onJumpIn and onClose when clicking jump in button', () => {
    render(<SessionContextJumpModal {...defaultProps} />);

    const jumpBtn = screen.getByRole('button', { name: 'jumpInAction' });
    fireEvent.click(jumpBtn);

    expect(defaultProps.onJumpIn).toHaveBeenCalledWith('sess-target-99');
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('triggers onClose when close or cancel button is clicked', () => {
    render(<SessionContextJumpModal {...defaultProps} />);

    const closeBtn = screen.getByRole('button', { name: 'closeAriaLabel' });
    fireEvent.click(closeBtn);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);

    const cancelBtn = screen.getByRole('button', { name: 'cancelAction' });
    fireEvent.click(cancelBtn);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(2);
  });
});
