/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PresetWorkspaceGrid } from '../PresetWorkspaceGrid';
import * as layoutHook from '@/hooks/ui/useWorkspaceLayoutMode';

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconCpu: () => <span data-testid="icon-cpu" />,
  IconSparkles: () => <span data-testid="icon-sparkles" />,
  IconTerminal: () => <span data-testid="icon-terminal" />,
  IconUsers: () => <span data-testid="icon-users" />,
}));

describe('PresetWorkspaceGrid component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders easy_minimal layout container by default', () => {
    vi.spyOn(layoutHook, 'useWorkspaceLayoutMode').mockReturnValue({
      layoutMode: 'easy_minimal',
      setLayoutMode: vi.fn(),
      resetLayout: vi.fn(),
      isCopilot: false,
      isMultiAgent: false,
      isRemoteCompute: false,
      isEasyMinimal: true,
    });

    render(
      <PresetWorkspaceGrid>
        <div data-testid="test-child">Child Content</div>
      </PresetWorkspaceGrid>,
    );

    expect(screen.getByTestId('workspace-grid-easy-minimal')).toBeDefined();
    expect(screen.getByTestId('test-child')).toBeDefined();
  });

  it('renders copilot layout with code review inspector aside', () => {
    render(
      <PresetWorkspaceGrid overrideMode="copilot">
        <div data-testid="test-child">Copilot Arena</div>
      </PresetWorkspaceGrid>,
    );

    expect(screen.getByTestId('workspace-grid-copilot')).toBeDefined();
    expect(screen.getByText(/Copilot Code Review/)).toBeDefined();
    expect(screen.getByTestId('test-child')).toBeDefined();
  });

  it('renders multi_agent layout with cluster topology banner', () => {
    render(
      <PresetWorkspaceGrid overrideMode="multi_agent">
        <div data-testid="test-child">Agent Mesh</div>
      </PresetWorkspaceGrid>,
    );

    expect(screen.getByTestId('workspace-grid-multi-agent')).toBeDefined();
    expect(screen.getByText(/Multi-Agent Cluster Topology/)).toBeDefined();
    expect(screen.getByTestId('test-child')).toBeDefined();
  });

  it('renders remote_compute layout with sandbox telemetry aside', () => {
    render(
      <PresetWorkspaceGrid overrideMode="remote_compute">
        <div data-testid="test-child">Compute Frame</div>
      </PresetWorkspaceGrid>,
    );

    expect(screen.getByTestId('workspace-grid-remote-compute')).toBeDefined();
    expect(screen.getByText(/Remote Sandbox Telemetry/)).toBeDefined();
    expect(screen.getByTestId('test-child')).toBeDefined();
  });
});
