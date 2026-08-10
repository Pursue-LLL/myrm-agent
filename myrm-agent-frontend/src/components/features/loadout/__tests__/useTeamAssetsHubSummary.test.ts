import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useTeamAssetsHubSummary } from '@/components/features/loadout/useTeamAssetsHubSummary';

const agentApi = vi.hoisted(() => ({
  listAgents: vi.fn(),
  getFleetOverview: vi.fn(),
  getAgentReadiness: vi.fn(),
}));

const skillApi = vi.hoisted(() => ({
  listSkills: vi.fn(),
}));

const memoryApi = vi.hoisted(() => ({
  getPendingMemories: vi.fn(),
}));

const configState = vi.hoisted(() => ({
  enableMemory: true,
}));

vi.mock('@/services/agent', () => ({
  listAgents: agentApi.listAgents,
  getFleetOverview: agentApi.getFleetOverview,
  getAgentReadiness: agentApi.getAgentReadiness,
}));

vi.mock('@/services/skill', () => ({
  listSkills: skillApi.listSkills,
}));

vi.mock('@/services/memory', () => ({
  getPendingMemories: memoryApi.getPendingMemories,
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: typeof configState) => unknown) => selector(configState),
}));

describe('useTeamAssetsHubSummary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    agentApi.listAgents.mockResolvedValue({
      items: [
        {
          id: 'agent-1',
          name: 'General',
          is_built_in: true,
          skill_ids: ['s1'],
          enabled_builtin_tools: ['wiki'],
        },
        {
          id: 'agent-2',
          name: 'Coder',
          is_built_in: false,
          skill_ids: [],
          enabled_builtin_tools: [],
        },
      ],
      total: 2,
    });
    agentApi.getFleetOverview.mockResolvedValue({
      kpi: {},
      agents: {
        'agent-1': { cronCount: 2, status: 'idle' },
        'agent-2': { cronCount: 0, status: 'busy' },
      },
    });
    agentApi.getAgentReadiness.mockResolvedValue({
      agent_id: 'agent-1',
      overall_level: 'ready',
      items: [],
      checked_at: 0,
    });
    skillApi.listSkills.mockResolvedValue({ skills: [], total: 12 });
    memoryApi.getPendingMemories.mockResolvedValue({ items: [], total: 3 });
  });

  it('aggregates memory policy, skill count, pending count, and agent overviews', async () => {
    const { result } = renderHook(() => useTeamAssetsHubSummary({ enabled: true }));

    await waitFor(() => {
      expect(result.current.summary).not.toBeNull();
    });

    expect(result.current.summary).toMatchObject({
      enableMemory: true,
      skillCount: 12,
      skillStatus: 'ok',
      pendingCount: 3,
      pendingStatus: 'ok',
      agentsStatus: 'ok',
    });
    expect(result.current.summary?.agents).toHaveLength(2);
    expect(result.current.summary?.agents[0]).toMatchObject({
      agentId: 'agent-1',
      name: 'General',
      isBuiltIn: true,
      readinessLevel: 'ready',
      readinessStatus: 'ok',
      skillCount: 1,
      wikiEnabled: true,
      cronCount: 2,
    });
    expect(result.current.summary?.agents[1]).toMatchObject({
      agentId: 'agent-2',
      isBuiltIn: false,
      skillCount: 0,
      wikiEnabled: false,
    });
  });

  it('degrades agent list to unavailable when listAgents fails', async () => {
    agentApi.listAgents.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => useTeamAssetsHubSummary({ enabled: true }));

    await waitFor(() => {
      expect(result.current.summary).not.toBeNull();
    });

    expect(result.current.summary?.agentsStatus).toBe('unavailable');
    expect(result.current.summary?.agents).toEqual([]);
    expect(result.current.summary?.skillCount).toBe(12);
    expect(result.current.summary?.pendingCount).toBe(3);
  });

  it('degrades skill and pending counts to unavailable independently', async () => {
    skillApi.listSkills.mockRejectedValue(new Error('boom'));
    memoryApi.getPendingMemories.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => useTeamAssetsHubSummary({ enabled: true }));

    await waitFor(() => {
      expect(result.current.summary).not.toBeNull();
    });

    expect(result.current.summary?.skillStatus).toBe('unavailable');
    expect(result.current.summary?.pendingStatus).toBe('unavailable');
    expect(result.current.summary?.agentsStatus).toBe('ok');
  });
});
