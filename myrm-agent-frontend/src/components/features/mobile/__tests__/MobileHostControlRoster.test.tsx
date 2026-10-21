/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MobileHostControlRoster } from '../MobileHostControlRoster';
import type { SpawnOptionAgent } from '@/services/remoteAccess';
import type { ActiveSession } from '@/services/agent';

const stableT = (key: string, params?: Record<string, unknown>) => {
    if (params && 'count' in params) {
      return `${key}:${String(params.count)}`;
    }
    if (params && 'time' in params) {
      return `${key}:${String(params.time)}`;
    }
    return key;
  };

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'zh',
}));

vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (_id: string, name: string) => name,
}));

describe('MobileHostControlRoster', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockAgents: SpawnOptionAgent[] = [
    { id: 'agent-coder', name: 'Code Expert', avatar: null },
    { id: 'agent-researcher', name: 'Deep Researcher', avatar: null },
  ];

  const mockSessions: ActiveSession[] = [
    {
      chatId: 'chat-101',
      agentId: 'agent-coder',
      agentName: 'Code Expert',
      agentType: 'coding',
      elapsedSeconds: 42,
    },
  ];

  it('renders agent carousel with running and idle indicators', () => {
    const onSelectAgent = vi.fn();
    render(
      <MobileHostControlRoster
        agents={mockAgents}
        activeSessions={mockSessions}
        selectedAgentId="agent-coder"
        onSelectAgent={onSelectAgent}
      />
    );

    expect(screen.getByText('agentRosterTitle')).toBeInTheDocument();
    expect(screen.getByText('Code Expert')).toBeInTheDocument();
    expect(screen.getByText('Deep Researcher')).toBeInTheDocument();

    // Code Expert has 1 active session
    expect(screen.getByText('runningTasks:1')).toBeInTheDocument();
    // Deep Researcher is idle
    expect(screen.getByText('idleStatus')).toBeInTheDocument();

    // Click Deep Researcher
    fireEvent.click(screen.getByText('Deep Researcher'));
    expect(onSelectAgent).toHaveBeenCalledWith('agent-researcher');
  });

  it('toggles cron automation accordion to view schedules', () => {
    render(
      <MobileHostControlRoster
        agents={mockAgents}
        activeSessions={[]}
      />
    );

    const cronToggle = screen.getByRole('button', { name: /cronDashboardTitle/i });
    expect(screen.queryByText('Host Health & Keepalive')).not.toBeInTheDocument();

    // Expand
    fireEvent.click(cronToggle);
    expect(screen.getByText('Host Health & Keepalive')).toBeInTheDocument();
    expect(screen.getByText('Vault State Sync')).toBeInTheDocument();
    expect(screen.getByText('0 * * * *')).toBeInTheDocument();

    // Collapse
    fireEvent.click(cronToggle);
    expect(screen.queryByText('Host Health & Keepalive')).not.toBeInTheDocument();
  });

  it('renders empty agent state when agents array is empty', () => {
    render(<MobileHostControlRoster agents={[]} activeSessions={[]} />);
    expect(screen.getByText('noAgentsFound')).toBeInTheDocument();
  });
});
