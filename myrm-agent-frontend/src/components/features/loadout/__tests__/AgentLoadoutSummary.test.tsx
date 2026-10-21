import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AgentLoadoutSummary } from '@/components/features/loadout/AgentLoadoutSummary';
import type { AgentLoadoutSummaryData } from '@/components/features/loadout/useAgentLoadoutSummary';

const messages: Record<string, string> = {
  'loadout.title': 'Agent loadout',
  'loadout.subtitle': 'Summary',
  'loadout.loading': 'Loading',
  'loadout.saveAgentFirst': 'Save first',
  'loadout.fix': 'Fix',
  'loadout.openTeamAssets': 'Team assets',
  'loadout.openWiki': 'Wiki',
  'loadout.openSkills': 'Skills',
  'loadout.openMemory': 'Memory',
  'loadout.readiness.ready': 'Ready',
  'loadout.readiness.warning': 'Warning',
  'loadout.readiness.blocked': 'Blocked',
  'loadout.tiles.sharedContexts': 'Shared contexts',
  'loadout.tiles.skills': 'Skills',
  'loadout.tiles.skillsCount': '{count} mounted',
  'loadout.tiles.wiki': 'Wiki',
  'loadout.tiles.wikiOn': 'On',
  'loadout.tiles.wikiOff': 'Off',
  'loadout.tiles.memoryPolicy': 'Memory policy',
  'loadout.sharedContexts.none': 'None',
  'loadout.sharedContexts.unavailable': 'Unavailable',
  'loadout.memoryPolicy.on': 'On',
  'loadout.memoryPolicy.off': 'Off',
  'loadout.memoryPolicy.onWithPreCompact': 'On {tokens}',
};

const mockUseAgentLoadoutSummary = vi.hoisted(() => vi.fn());

const stableT = (key: string, params?: Record<string, string | number>) => {
  const fullKey = `loadout.${key}`;
  const template = messages[fullKey] ?? key;
  if (!params) {
    return template;
  }
  return Object.entries(params).reduce((acc, [name, value]) => acc.replace(`{${name}}`, String(value)), template);
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/loadout/useAgentLoadoutSummary', () => ({
  useAgentLoadoutSummary: mockUseAgentLoadoutSummary,
  readinessLevelTone: () => 'text-emerald-600',
}));

function baseLoadoutData(overrides: Partial<AgentLoadoutSummaryData> = {}): AgentLoadoutSummaryData {
  return {
    agent: { id: 'agent-1', skill_ids: ['s1'] } as AgentLoadoutSummaryData['agent'],
    readiness: { overall_level: 'ready', items: [], agent_id: 'agent-1', checked_at: 0 },
    readinessStatus: 'ok',
    sharedContextBindings: [],
    boundContextNames: ['Team Pool'],
    bindingsStatus: 'ok',
    proposalsStatus: 'ok',
    pendingProposalCount: 2,
    wikiEnabled: true,
    skillCount: 3,
    memoryPolicy: {
      enableMemory: true,
      requireConfirmation: true,
      autoExtraction: true,
      conversationSearch: true,
      preCompactEnabled: true,
      preCompactBudgetTokens: 1200,
    },
    ...overrides,
  };
}

describe('AgentLoadoutSummary', () => {
  it('renders loadout tiles and team assets link', () => {
    mockUseAgentLoadoutSummary.mockReturnValue({
      data: baseLoadoutData(),
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<AgentLoadoutSummary agentId="agent-1" skillCount={3} />);

    expect(screen.getByText('Agent loadout')).toBeInTheDocument();
    expect(screen.getByText('Team Pool')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Team assets' })).toHaveAttribute('href', '/settings/memory?sub=team-hub');
  });

  it('hides proposal badge when proposals are unavailable', () => {
    mockUseAgentLoadoutSummary.mockReturnValue({
      data: baseLoadoutData({ proposalsStatus: 'unavailable', pendingProposalCount: 0 }),
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<AgentLoadoutSummary agentId="agent-1" skillCount={3} />);

    expect(screen.getByText('Team Pool')).toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('shows unavailable label when bindings cannot be loaded', () => {
    mockUseAgentLoadoutSummary.mockReturnValue({
      data: baseLoadoutData({
        bindingsStatus: 'unavailable',
        boundContextNames: [],
        proposalsStatus: 'unavailable',
        pendingProposalCount: 0,
      }),
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<AgentLoadoutSummary agentId="agent-1" skillCount={3} />);

    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.queryByText('None')).not.toBeInTheDocument();
  });

  it('hides readiness badge when readiness API is unavailable', () => {
    mockUseAgentLoadoutSummary.mockReturnValue({
      data: baseLoadoutData({
        readiness: null,
        readinessStatus: 'unavailable',
      }),
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(<AgentLoadoutSummary agentId="agent-1" skillCount={3} />);

    expect(screen.queryByText('Ready')).not.toBeInTheDocument();
  });
});
