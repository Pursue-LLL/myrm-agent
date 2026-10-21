import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentReadinessItem, AgentReadinessReport } from '@/services/agent';

import ReadinessBadge from '../ReadinessBadge';

const MESSAGES: Record<string, string> = {
  'Agent.readiness.dimensions.mcp': 'MCP servers',
  'Agent.readiness.dimensions.other': 'Other',
  'Agent.readiness.reasons.mcp_not_enabled': 'Turned off: {names}',
  'Agent.readiness.reasons.mcp_missing_secrets': 'Missing keys: {names}',
  'Agent.readiness.fallback.warning': 'This may limit the agent',
  'agent.readiness.warning': 'Some configurations need attention',
  'agent.readiness.blocked': 'Agent cannot run',
};

const push = vi.fn();
let report: AgentReadinessReport;

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) =>
    Object.assign(
      (key: string, values?: Record<string, unknown>) =>
        Object.entries(values ?? {}).reduce(
          (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
          MESSAGES[`${namespace}.${key}`] ?? key,
        ),
      { has: (key: string) => `${namespace}.${key}` in MESSAGES },
    ),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('@/hooks/agent/useAgentReadiness', () => ({
  useAgentReadiness: () => ({
    report,
    overallLevel: report.overall_level,
    hasIssues: report.overall_level !== 'ready',
    isLoading: false,
  }),
}));
// The real tooltip only mounts its content on hover; render it inline so the rows can be inspected.
vi.mock('@/components/primitives/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

function item(overrides: Partial<AgentReadinessItem>): AgentReadinessItem {
  return {
    dimension: 'mcp',
    level: 'warning',
    code: 'mcp_not_enabled',
    reason: 'English diagnostic',
    next_action: 'Enable in MCP settings: slack',
    settings_path: '/settings/mcp',
    names: ['slack'],
    count: 1,
    ...overrides,
  };
}

describe('ReadinessBadge', () => {
  beforeEach(() => {
    push.mockClear();
  });

  it('words each finding from its stable code, never the backend diagnostics, with one row per finding', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    report = {
      overall_level: 'warning',
      agent_id: 'a1',
      checked_at: 0,
      items: [
        item({}),
        item({
          code: 'mcp_missing_secrets',
          names: ['SLACK_TOKEN'],
          settings_path: '/settings/agents?agentId=a1#secrets',
        }),
      ],
    };

    render(<ReadinessBadge />);

    expect(screen.getAllByText('MCP servers')).toHaveLength(2);
    expect(screen.getByText(/Turned off: slack/)).toBeInTheDocument();
    expect(screen.getByText(/Missing keys: SLACK_TOKEN/)).toBeInTheDocument();
    expect(screen.queryByText(/Enable in MCP settings/)).not.toBeInTheDocument();
    expect(screen.queryByText('mcp')).not.toBeInTheDocument();
    // React reports colliding list keys through console.error.
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('falls back to a generic line for a finding this build does not know and deep-links on click', () => {
    report = {
      overall_level: 'warning',
      agent_id: 'a1',
      checked_at: 0,
      items: [item({ dimension: 'future', code: 'something_new', next_action: 'Do the new thing' })],
    };

    render(<ReadinessBadge />);

    expect(screen.getByText('Other')).toBeInTheDocument();
    expect(screen.getByText(/This may limit the agent/)).toBeInTheDocument();
    expect(screen.queryByText(/Do the new thing/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button'));
    expect(push).toHaveBeenCalledWith('/settings/mcp');
  });

  it('renders nothing when the agent is ready', () => {
    report = { overall_level: 'ready', agent_id: 'a1', checked_at: 0, items: [] };

    const { container } = render(<ReadinessBadge />);

    expect(container).toBeEmptyDOMElement();
  });
});
