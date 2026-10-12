/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AgentFleetCockpit } from '../AgentFleetCockpit';
import type { FleetCockpitSummary } from '@/services/sessionMap';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconSearch: () => <span data-testid="icon-search" />,
  IconX: () => <span data-testid="icon-x" />,
  IconActivity: () => <span data-testid="icon-activity" />,
  IconFolder: () => <span data-testid="icon-folder" />,
  IconSparkles: () => <span data-testid="icon-sparkles" />,
  IconCheck: () => <span data-testid="icon-check" />,
}));

describe('AgentFleetCockpit component', () => {
  const mockSummary: FleetCockpitSummary = {
    total_projects: 4,
    total_sessions: 16,
    total_agents: 16,
    working_agents: 7,
    ready_agents: 6,
    waiting_input_agents: 2,
    error_agents: 1,
    total_tokens_consumed: 185000,
    top_active_sessions: [],
  };

  const defaultProps = {
    summary: mockSummary,
    onFilterChange: vi.fn(),
    searchQuery: '',
    onSearchChange: vi.fn(),
    viewMode: 'topology' as const,
    onViewModeChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders aggregate fleet metrics correctly', () => {
    render(<AgentFleetCockpit {...defaultProps} />);

    expect(screen.getByText('4')).toBeDefined(); // projects
    expect(screen.getByText('7')).toBeDefined(); // working
    expect(screen.getByText('6')).toBeDefined(); // ready
    expect(screen.getByText('2')).toBeDefined(); // waiting
    expect(screen.getByText('1')).toBeDefined(); // errors
    expect(screen.getByText('185k')).toBeDefined(); // tokens
  });

  it('triggers onFilterChange when state filter pill is clicked', () => {
    render(<AgentFleetCockpit {...defaultProps} />);

    const workingBtn = screen.getByRole('button', { name: 'filterWorking' });
    fireEvent.click(workingBtn);
    expect(defaultProps.onFilterChange).toHaveBeenCalledWith('working');

    const allBtn = screen.getByRole('button', { name: 'filterAll' });
    fireEvent.click(allBtn);
    expect(defaultProps.onFilterChange).toHaveBeenCalledWith(undefined);
  });

  it('handles search query change and clear', () => {
    const { rerender } = render(<AgentFleetCockpit {...defaultProps} searchQuery="auth" />);

    const input = screen.getByPlaceholderText('searchPlaceholder');
    fireEvent.change(input, { target: { value: 'database' } });
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith('database');

    // Click clear button
    const clearBtn = screen.getByRole('button', { name: 'clearSearch' });
    fireEvent.click(clearBtn);
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith('');

    // When query is empty, clear button is not shown
    rerender(<AgentFleetCockpit {...defaultProps} searchQuery="" />);
    expect(screen.queryByRole('button', { name: 'clearSearch' })).toBeNull();
  });

  it('toggles view mode between topology and list', () => {
    render(<AgentFleetCockpit {...defaultProps} />);

    const listViewBtn = screen.getByRole('button', { name: 'viewList' });
    fireEvent.click(listViewBtn);
    expect(defaultProps.onViewModeChange).toHaveBeenCalledWith('list');

    const topViewBtn = screen.getByRole('button', { name: 'viewTopology' });
    fireEvent.click(topViewBtn);
    expect(defaultProps.onViewModeChange).toHaveBeenCalledWith('topology');
  });
});
