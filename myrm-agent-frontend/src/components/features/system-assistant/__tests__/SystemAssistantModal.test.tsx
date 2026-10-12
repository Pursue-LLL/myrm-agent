/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SystemAssistantModal } from '../SystemAssistantModal';
import * as systemAssistantService from '@/services/systemAssistant';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconBrain: () => <span data-testid="icon-brain" />,
  IconCheck: () => <span data-testid="icon-check" />,
  IconClose: () => <span data-testid="icon-close" />,
  IconRefresh: () => <span data-testid="icon-refresh" />,
  IconSparkles: () => <span data-testid="icon-sparkles" />,
  IconTerminal: () => <span data-testid="icon-terminal" />,
  IconX: () => <span data-testid="icon-x" />,
}));

vi.mock('@/services/systemAssistant', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/systemAssistant')>();
  return {
    ...actual,
    executeSystemAssistantCommand: vi.fn(),
    getSystemAssistantStatus: vi.fn(),
  };
});

describe('SystemAssistantModal component', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
  };

  const mockStatus: systemAssistantService.SystemAssistantStatusResponse = {
    active_agents_count: 2,
    running_tasks_count: 3,
    total_projects_count: 4,
    system_health: 'optimal',
    voice_enabled: true,
    last_heartbeat: '2026-10-12T07:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(systemAssistantService.getSystemAssistantStatus).mockResolvedValue(mockStatus);
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <SystemAssistantModal {...defaultProps} isOpen={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders modal header, telemetry status badge, and input bar when open', async () => {
    render(<SystemAssistantModal {...defaultProps} />);

    expect(screen.getByText('hubTitle')).toBeDefined();
    expect(screen.getByText('hubSubtitle')).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText(/tasksRunningBadge/)).toBeDefined();
    });
  });

  it('sends command when clicking a preset prompt pill', async () => {
    const mockResponse: systemAssistantService.SystemAssistantCommandResponse = {
      command_id: 'cmd-001',
      intent: 'create_project',
      summary: 'Project Created Successfully',
      action: {
        action_type: 'project_created',
        status: 'success',
        details: { project_id: 'proj-new-001' },
      },
      suggested_followups: ['View Project Details'],
      created_at: '2026-10-12T07:00:00Z',
    };

    vi.mocked(systemAssistantService.executeSystemAssistantCommand).mockResolvedValueOnce(
      mockResponse,
    );

    render(<SystemAssistantModal {...defaultProps} />);

    const presetBtn = screen.getByRole('button', { name: 'createProjectPrompt' });
    fireEvent.click(presetBtn);

    await waitFor(() => {
      expect(systemAssistantService.executeSystemAssistantCommand).toHaveBeenCalledWith({
        user_prompt: 'createProjectPrompt',
      });
      expect(screen.getByText('Project Created Successfully')).toBeDefined();
      expect(screen.getByText('proj-new-001')).toBeDefined();
    });
  });

  it('sends command via input text on Enter or Send button click', async () => {
    const mockResponse: systemAssistantService.SystemAssistantCommandResponse = {
      command_id: 'cmd-002',
      intent: 'query_tasks',
      summary: 'All tasks running properly',
      action: {
        action_type: 'tasks_queried',
        status: 'success',
        details: { running_count: '3' },
      },
      suggested_followups: [],
      created_at: '2026-10-12T07:00:00Z',
    };

    vi.mocked(systemAssistantService.executeSystemAssistantCommand).mockResolvedValueOnce(
      mockResponse,
    );

    render(<SystemAssistantModal {...defaultProps} />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: '查询所有活跃任务' } });

    const sendBtn = screen.getByRole('button', { name: 'sendAction' });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(systemAssistantService.executeSystemAssistantCommand).toHaveBeenCalledWith({
        user_prompt: '查询所有活跃任务',
      });
      expect(screen.getByText('All tasks running properly')).toBeDefined();
    });
  });

  it('toggles voice simulation mode on voice button click', async () => {
    render(<SystemAssistantModal {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText('hubTitle')).toBeDefined();
    });

    const voiceBtn = screen.getByRole('button', { name: 'voiceButtonTitle' });
    fireEvent.click(voiceBtn);

    expect(screen.getByPlaceholderText('listeningPlaceholder')).toBeDefined();
  });

  it('calls onClose when close button is clicked', async () => {
    render(<SystemAssistantModal {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText('hubTitle')).toBeDefined();
    });

    const closeBtn = screen.getByRole('button', { name: 'closeAriaLabel' });
    fireEvent.click(closeBtn);

    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });
});
