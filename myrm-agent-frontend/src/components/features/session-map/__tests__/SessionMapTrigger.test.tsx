/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SessionMapTrigger } from '../SessionMapTrigger';
import type { ProjectCluster, FleetCockpitSummary } from '@/services/sessionMap';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconActivity: () => <span data-testid="icon-activity" />,
  IconX: () => <span data-testid="icon-x" />,
  IconFolder: () => <span data-testid="icon-folder" />,
  IconFilter: () => <span data-testid="icon-filter" />,
  IconSearch: () => <span data-testid="icon-search" />,
  IconMaximize: () => <span data-testid="icon-maximize" />,
  IconSparkles: () => <span data-testid="icon-sparkles" />,
  IconCheck: () => <span data-testid="icon-check" />,
}));

const mockProjects: ProjectCluster[] = [
  {
    id: 'proj-1',
    name: 'Myrm Agent Core',
    description: 'Autonomous execution engine',
    color: '#3b82f6',
    workspace_path: '/workspace/core',
    sessions: [
      {
        id: 'sess-101',
        title: 'Core Architecture Refactor',
        agent_id: 'agent-1',
        agent_name: 'LeadArchitect',
        state: 'working',
        current_task: 'Refactoring runtime loop',
        tokens_used: 12500,
        last_active_at: '2026-10-12T10:00:00Z',
        tags: ['core', 'refactor'],
      },
    ],
    active_agent_count: 1,
    total_tokens: 12500,
  },
];

const mockSummary: FleetCockpitSummary = {
  total_projects: 1,
  total_sessions: 1,
  total_agents: 1,
  working_agents: 1,
  ready_agents: 0,
  waiting_input_agents: 0,
  error_agents: 0,
  total_tokens_consumed: 12500,
  top_active_sessions: [],
};

const mockFetchSessionMapProjects = vi.fn();
const mockFetchFleetCockpitSummary = vi.fn();

vi.mock('@/services/sessionMap', () => ({
  fetchSessionMapProjects: (...args: unknown[]) => mockFetchSessionMapProjects(...args),
  fetchFleetCockpitSummary: () => mockFetchFleetCockpitSummary(),
}));

describe('SessionMapTrigger component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchSessionMapProjects.mockResolvedValue(mockProjects);
    mockFetchFleetCockpitSummary.mockResolvedValue(mockSummary);
  });

  // The Tools menu is the only visible entrance; it opens the map through this event.
  const openFromMenu = () => {
    act(() => {
      window.dispatchEvent(new CustomEvent('myrm:open-session-map'));
    });
  };

  it('renders no floating entrance and keeps the map closed initially', () => {
    render(<SessionMapTrigger />);

    expect(screen.queryByRole('button', { name: /hudTrigger/i })).toBeNull();
    expect(screen.queryByText('shortcutHint')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens modal and loads data when the Tools menu asks for it', async () => {
    render(<SessionMapTrigger />);

    openFromMenu();

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
    });

    expect(mockFetchSessionMapProjects).toHaveBeenCalledTimes(1);
    expect(mockFetchFleetCockpitSummary).toHaveBeenCalledTimes(1);
    expect(screen.getByText('modalTitle')).toBeDefined();
  });

  it('closes modal when clicking close button', async () => {
    render(<SessionMapTrigger />);

    // Open
    openFromMenu();
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
    });

    // Close via close button
    const closeBtn = screen.getByRole('button', { name: 'closeAriaLabel' });
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  it('toggles modal when Cmd+Shift+M or Ctrl+Shift+M is pressed', async () => {
    render(<SessionMapTrigger />);

    // Press Cmd+Shift+M to open
    fireEvent.keyDown(window, {
      key: 'm',
      metaKey: true,
      shiftKey: true,
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
    });

    // Press Escape to close
    fireEvent.keyDown(window, {
      key: 'Escape',
    });

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  it('shows the loading text, not the empty state, while the first load is pending', async () => {
    mockFetchSessionMapProjects.mockReturnValue(new Promise(() => {}));
    render(<SessionMapTrigger />);

    openFromMenu();

    await waitFor(() => {
      expect(screen.getByText('loadingTopology')).toBeDefined();
    });
    expect(screen.queryByText('defaultTitle')).toBeNull();
  });

  it('shows the empty state when there are no projects or sessions', async () => {
    mockFetchSessionMapProjects.mockResolvedValue([]);
    render(<SessionMapTrigger />);

    openFromMenu();

    await waitFor(() => {
      expect(screen.getByText('defaultTitle')).toBeDefined();
    });
    expect(screen.getByText('defaultDescription')).toBeDefined();
  });

  it('shows a retryable error state when loading fails', async () => {
    mockFetchSessionMapProjects.mockRejectedValueOnce(new Error('server unavailable'));
    render(<SessionMapTrigger />);

    openFromMenu();

    await waitFor(() => {
      expect(screen.getByText('loadFailed')).toBeDefined();
    });
    expect(screen.getByText('loadFailedDesc')).toBeDefined();
    expect(screen.queryByText('defaultTitle')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'retry' }));

    await waitFor(() => {
      expect(screen.queryByText('loadFailed')).toBeNull();
    });
    expect(mockFetchSessionMapProjects).toHaveBeenCalledTimes(2);
  });

  it('shows a project workspace path in the list view only when the project has one', async () => {
    mockFetchSessionMapProjects.mockResolvedValue([
      ...mockProjects,
      { ...mockProjects[0], id: 'proj-2', name: 'No Workspace Project', workspace_path: undefined, sessions: [] },
    ]);
    render(<SessionMapTrigger />);

    openFromMenu();
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
    });
    fireEvent.click(screen.getByRole('button', { name: 'viewList' }));

    await waitFor(() => {
      expect(screen.getByText('No Workspace Project')).toBeDefined();
    });
    expect(screen.getByText('(/workspace/core)')).toBeDefined();
    expect(screen.getAllByText(/^\(.*\)$/)).toHaveLength(1);
  });

  it('switches to list view and can open jump modal on session click', async () => {
    render(<SessionMapTrigger />);

    openFromMenu();

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
    });

    // Switch view mode to list
    const listViewBtn = screen.getByRole('button', { name: 'viewList' });
    fireEvent.click(listViewBtn);

    // Verify session card in list view
    await waitFor(() => {
      expect(screen.getByText('Core Architecture Refactor')).toBeDefined();
    });

    // Click session card to open Jump modal
    const sessionCardBtn = screen.getByText('Core Architecture Refactor').closest('button');
    expect(sessionCardBtn).not.toBeNull();
    if (sessionCardBtn) {
      fireEvent.click(sessionCardBtn);
    }

    // Session jump dialog should be opened
    await waitFor(() => {
      expect(screen.getByText('sessionModalSubtitle')).toBeDefined();
      expect(screen.getByRole('button', { name: 'jumpInAction' })).toBeDefined();
    });
  });
});
