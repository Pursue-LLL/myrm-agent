import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatInlineTeamRunVisibilityStrip } from '../ChatInlineTeamRunVisibilityStrip';
import { useSubagentStore, type SubagentNode } from '@/store/chat/useSubagentStore';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    if (params?.count !== undefined) {
      return `${key}:${params.count}`;
    }
    return key;
  },
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
  it('renders null when there are no subagent nodes', () => {
    useSubagentStore.getState().clear();
    const { container } = render(<ChatInlineTeamRunVisibilityStrip />);
    expect(container.firstChild).toBeNull();
  });

  it('renders null when all subagents are completed', () => {
    useSubagentStore.getState().clear();
    useSubagentStore.getState().setNodes([
      makeNode({ task_id: '1', status: 'completed' }),
      makeNode({ task_id: '2', status: 'completed' }),
    ]);
    const { container } = render(<ChatInlineTeamRunVisibilityStrip />);
    expect(container.firstChild).toBeNull();
  });

  it('renders visibility strip when active subagents exist', () => {
    useSubagentStore.getState().clear();
    useSubagentStore.getState().setNodes([
      makeNode({ task_id: '1', status: 'running', agent_type: 'coder', last_tool: 'bash' }),
      makeNode({ task_id: '2', status: 'verifying', agent_type: 'auditor' }),
    ]);

    render(<ChatInlineTeamRunVisibilityStrip />);
    const strip = screen.getByTestId('chat-inline-team-run-visibility-strip');
    expect(strip).toBeDefined();
    expect(screen.getByText('inlineStripActiveSummary:2')).toBeDefined();
  });

  it('triggers onOpenDashboard when clicked', () => {
    useSubagentStore.getState().clear();
    useSubagentStore.getState().setNodes([
      makeNode({ task_id: '1', status: 'running' }),
    ]);

    const handleOpen = vi.fn();
    render(<ChatInlineTeamRunVisibilityStrip onOpenDashboard={handleOpen} />);

    const strip = screen.getByTestId('chat-inline-team-run-visibility-strip');
    fireEvent.click(strip);
    expect(handleOpen).toHaveBeenCalledTimes(1);
  });
});
