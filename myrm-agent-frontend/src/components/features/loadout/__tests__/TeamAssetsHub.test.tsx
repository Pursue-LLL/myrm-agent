import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TeamAssetsHub } from '@/components/features/loadout/TeamAssetsHub';
import type { TeamAssetsHubSummary } from '@/components/features/loadout/useTeamAssetsHubSummary';

const messages: Record<string, string> = {
  'loadout.teamHub.title': 'Team assets',
  'loadout.teamHub.subtitle': 'One place',
  'loadout.teamHub.wikiTitle': 'Wiki',
  'loadout.teamHub.wikiDesc': 'KB',
  'loadout.teamHub.skillsTitle': 'Skills',
  'loadout.teamHub.skillsDesc': 'Capabilities',
  'loadout.teamHub.memoryTitle': 'Memory',
  'loadout.teamHub.memoryDesc': 'Brain',
  'loadout.teamHub.summaryLoading': 'Loading',
  'loadout.teamHub.overviewTitle': 'Asset overview',
  'loadout.teamHub.blockedCount': '{count} agents need attention',
  'loadout.teamHub.memoryStat': 'Memory',
  'loadout.teamHub.memoryOn': 'Enabled',
  'loadout.teamHub.memoryOff': 'Off',
  'loadout.teamHub.skillsStat': 'Skills',
  'loadout.teamHub.pendingStat': 'Pending reviews',
  'loadout.teamHub.unavailable': 'Unavailable',
  'loadout.teamHub.builtIn': 'Built-in',
  'loadout.teamHub.agentSummary': '{skills} skills · wiki {wiki} · {cron} cron',
  'loadout.teamHub.wikiOn': 'on',
  'loadout.teamHub.wikiOff': 'off',
  'loadout.readiness.ready': 'Ready',
  'loadout.readiness.warning': 'Needs attention',
  'loadout.readiness.blocked': 'Blocked',
};

const mockUseTeamAssetsHubSummary = vi.hoisted(() => vi.fn());

const stableT = (key: string, params?: Record<string, string | number>) => {
  const template = messages[`loadout.${key}`] ?? key;
  if (!params) {return template;}
  return Object.entries(params).reduce((acc, [name, value]) => acc.replace(`{${name}}`, String(value)), template);
};

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/loadout/useTeamAssetsHubSummary', () => ({
  useTeamAssetsHubSummary: mockUseTeamAssetsHubSummary,
}));

vi.mock('@/components/features/loadout/useAgentLoadoutSummary', () => ({
  readinessLevelTone: () => 'text-emerald-600',
}));

vi.mock('@/components/features/memory/shared-context/SharedContextPanel', () => ({
  default: () => <div data-testid="shared-context-panel" />,
}));

vi.mock('next/link', () => {
  return {
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
      <a href={href} {...rest}>
        {children}
      </a>
    ),
  };
});

function baseSummary(overrides: Partial<TeamAssetsHubSummary> = {}): TeamAssetsHubSummary {
  return {
    enableMemory: true,
    skillCount: 12,
    skillStatus: 'ok',
    pendingCount: 3,
    pendingStatus: 'ok',
    agents: [
      {
        agentId: 'agent-1',
        name: 'General',
        isBuiltIn: true,
        readinessLevel: 'ready',
        readinessStatus: 'ok',
        skillCount: 3,
        wikiEnabled: true,
        cronCount: 2,
      },
      {
        agentId: 'agent-2',
        name: 'Coder',
        isBuiltIn: false,
        readinessLevel: 'blocked',
        readinessStatus: 'ok',
        skillCount: 1,
        wikiEnabled: false,
        cronCount: 0,
      },
    ],
    agentsStatus: 'ok',
    ...overrides,
  };
}

describe('TeamAssetsHub', () => {
  it('renders summary stats and agent readiness overview', () => {
    mockUseTeamAssetsHubSummary.mockReturnValue({
      summary: baseSummary(),
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<TeamAssetsHub />);

    expect(screen.getByText('Asset overview')).toBeInTheDocument();
    expect(screen.getByText('Enabled')).toBeInTheDocument();
    expect(screen.getAllByText('12')).toHaveLength(2);
    expect(screen.getAllByText('3')).toHaveLength(2);
    expect(screen.getByText('General')).toBeInTheDocument();
    expect(screen.getByText('Coder')).toBeInTheDocument();
    expect(screen.getByText('Built-in')).toBeInTheDocument();
    expect(screen.getByText('1 agents need attention')).toBeInTheDocument();
  });

  it('deep links each agent row to its loadout settings', () => {
    mockUseTeamAssetsHubSummary.mockReturnValue({
      summary: baseSummary(),
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<TeamAssetsHub />);

    expect(screen.getByRole('link', { name: /General/ })).toHaveAttribute(
      'href',
      '/settings/agents?agentId=agent-1#loadout',
    );
    expect(screen.getByRole('link', { name: /Coder/ })).toHaveAttribute(
      'href',
      '/settings/agents?agentId=agent-2#loadout',
    );
  });

  it('renders loading state when summary is not ready', () => {
    mockUseTeamAssetsHubSummary.mockReturnValue({
      summary: null,
      loading: true,
      error: null,
      reload: vi.fn(),
    });

    render(<TeamAssetsHub />);

    expect(screen.getByText('Loading')).toBeInTheDocument();
  });

  it('renders skills/memory badges from summary counts', () => {
    mockUseTeamAssetsHubSummary.mockReturnValue({
      summary: baseSummary(),
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<TeamAssetsHub />);

    expect(screen.getByRole('link', { name: /Skills/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Memory/ })).toBeInTheDocument();
    expect(screen.getByTestId('shared-context-panel')).toBeInTheDocument();
  });
});
