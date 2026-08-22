// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ChatInlineTeamRunVisibilityStrip } from '../ChatInlineTeamRunVisibilityStrip';
import { useSubagentStore, type SubagentNode } from '@/store/chat/useSubagentStore';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.count !== undefined) {
    return `${key}:${params.count}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/agent/AgentAvatar', () => ({
  AgentAvatar: ({ name }: { name: string }) => <div data-testid="agent-avatar">{name}</div>,
}));

function makeNode(partial: Partial<SubagentNode>): SubagentNode {
  return {
    task_id: 'task-1',
    parent_task_id: '',
    agent_type: 'scout',
    description: 'Scouting market',
    status: 'running',
    progress: 0,
    ...partial,
  };
}

describe('ChatInlineTeamRunVisibilityStrip', () => {
  beforeEach(() => {
    useSubagentStore.getState().clear();
  });

  it('renders null when there are no subagent nodes', () => {
    const { container } = render(<ChatInlineTeamRunVisibilityStrip />);
    expect(container.firstChild).toBeNull();
  });

  it('renders null when all subagents are completed initially without active transition', () => {
    useSubagentStore.getState().setNodes([
      makeNode({ task_id: '1', status: 'completed' }),
      makeNode({ task_id: '2', status: 'completed' }),
    ]);
    const { container } = render(<ChatInlineTeamRunVisibilityStrip />);
    expect(container.firstChild).toBeNull();
  });

  it('renders visibility strip when active subagents exist (including pending & verifying)', () => {
    useSubagentStore.getState().setNodes([
      makeNode({ task_id: '1', status: 'running', agent_type: 'coder', last_tool: 'bash', progress: 40 }),
      makeNode({ task_id: '2', status: 'pending', agent_type: 'auditor', progress: 0 }),
    ]);

    render(<ChatInlineTeamRunVisibilityStrip />);
    const strip = screen.getByTestId('chat-inline-team-run-visibility-strip');
    expect(strip).toBeDefined();
    expect(screen.getByText('inlineStripActiveSummary:2')).toBeDefined();
    expect(screen.getByText('bash')).toBeDefined();

    // Progress bar check
    const progressTrack = screen.getByTestId('inline-progress-track');
    expect(progressTrack).toBeDefined();
  });

  it('preempts status with highest priority for pending_approval', () => {
    useSubagentStore.getState().setNodes([
      makeNode({ task_id: '1', status: 'running', agent_type: 'coder', last_tool: 'bash' }),
      makeNode({ task_id: '2', status: 'pending_approval', agent_type: 'deployer' }),
    ]);

    render(<ChatInlineTeamRunVisibilityStrip />);
    expect(screen.getByText('inlineStripPendingApprovalAlert:1')).toBeDefined();
  });

  it('preempts status with stale alert when node is stalled', () => {
    useSubagentStore.getState().setNodes([
      makeNode({ task_id: '1', status: 'running', agent_type: 'coder', last_tool: 'bash' }),
      makeNode({ task_id: '2', status: 'running', agent_type: 'scraper', stale: true }),
    ]);

    render(<ChatInlineTeamRunVisibilityStrip />);
    expect(screen.getByText('inlineStripStaleAlert:1')).toBeDefined();
  });

  it('triggers onOpenDashboard with specific taskId when avatar is clicked', () => {
    useSubagentStore.getState().setNodes([
      makeNode({ task_id: 'node-alpha', status: 'running', agent_type: 'alpha' }),
      makeNode({ task_id: 'node-beta', status: 'running', agent_type: 'beta' }),
    ]);

    const handleOpen = vi.fn();
    render(<ChatInlineTeamRunVisibilityStrip onOpenDashboard={handleOpen} />);

    const avatar = screen.getByTestId('inline-avatar-node-alpha');
    fireEvent.click(avatar);
    expect(handleOpen).toHaveBeenCalledWith('node-alpha');
  });

  it('renders completed graceful exit buffer when transitioning from active to all completed', () => {
    vi.useFakeTimers();

    useSubagentStore.getState().setNodes([
      makeNode({ task_id: '1', status: 'running' }),
    ]);

    const { rerender } = render(<ChatInlineTeamRunVisibilityStrip />);
    expect(screen.getByText('inlineStripActiveSummary:1')).toBeDefined();

    // Transition to all completed
    act(() => {
      useSubagentStore.getState().setNodes([
        makeNode({ task_id: '1', status: 'completed' }),
      ]);
      rerender(<ChatInlineTeamRunVisibilityStrip />);
    });

    // Completed banner buffer should be visible
    expect(screen.getByText('inlineStripCompleted:1')).toBeDefined();

    // After 2.5s timeout, it should disappear
    act(() => {
      vi.advanceTimersByTime(2600);
      rerender(<ChatInlineTeamRunVisibilityStrip />);
    });

    expect(screen.queryByText('inlineStripCompleted:1')).toBeNull();

    vi.useRealTimers();
  });
});
