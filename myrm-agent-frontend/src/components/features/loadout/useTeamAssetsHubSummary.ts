'use client';

/**
 * [INPUT]
 * @/services/agent::listAgents, getFleetOverview, getAgentReadiness (POS: Agent profile/fleet/readiness API client)
 * @/services/skill::listSkills (POS: Skills API client)
 * @/services/memory::getPendingMemories (POS: Memory API client)
 * @/store/useConfigStore (POS: Global memory policy configuration store)
 *
 * [OUTPUT]
 * useTeamAssetsHubSummary: Hook assembling the team assets hub read model from existing APIs.
 *
 * [POS]
 * Team assets data orchestration hook. Parallel-fetches global memory policy, skill count,
 * pending memory count, and per-agent readiness/binding entry summaries without introducing a
 * new backend aggregate API. Optional sources degrade to `unavailable` instead of a fake
 * zero/ready when the underlying API fails.
 */

import { useCallback, useEffect, useState } from 'react';

import {
  getAgentReadiness,
  getFleetOverview,
  listAgents,
  type AgentFleetStats,
  type AgentListItem,
  type ReadinessLevel,
} from '@/services/agent';
import { getPendingMemories } from '@/services/memory';
import { listSkills } from '@/services/skill';
import useConfigStore from '@/store/useConfigStore';

export type TeamAssetsHubStatus = 'ok' | 'unavailable';

export interface AgentReadinessOverview {
  agentId: string;
  name: string;
  isBuiltIn: boolean;
  readinessLevel: ReadinessLevel | null;
  readinessStatus: TeamAssetsHubStatus;
  skillCount: number;
  wikiEnabled: boolean;
  cronCount: number;
}

export interface TeamAssetsHubSummary {
  enableMemory: boolean;
  skillCount: number;
  skillStatus: TeamAssetsHubStatus;
  pendingCount: number;
  pendingStatus: TeamAssetsHubStatus;
  agents: AgentReadinessOverview[];
  agentsStatus: TeamAssetsHubStatus;
}

interface UseTeamAssetsHubSummaryOptions {
  enabled?: boolean;
  refreshKey?: number;
}

interface UseTeamAssetsHubSummaryResult {
  summary: TeamAssetsHubSummary | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

const AGENT_LIST_LIMIT = 100;

async function loadAgentOverview(): Promise<{
  agents: AgentReadinessOverview[];
  status: TeamAssetsHubStatus;
}> {
  let list: AgentListItem[] = [];
  let fleet: Record<string, AgentFleetStats> = {};
  try {
    const [agentResponse, fleetResponse] = await Promise.all([listAgents(1, AGENT_LIST_LIMIT), getFleetOverview()]);
    list = agentResponse.items;
    fleet = fleetResponse.agents ?? {};
  } catch {
    return { agents: [], status: 'unavailable' };
  }

  const readinessResults = await Promise.allSettled(list.map((agent) => getAgentReadiness(agent.id)));

  const agents: AgentReadinessOverview[] = list.map((agent, index) => {
    const stats = fleet[agent.id];
    const readiness = readinessResults[index];
    return {
      agentId: agent.id,
      name: agent.name,
      isBuiltIn: Boolean(agent.is_built_in),
      readinessLevel: readiness.status === 'fulfilled' ? readiness.value.overall_level : null,
      readinessStatus: readiness.status === 'fulfilled' ? 'ok' : 'unavailable',
      skillCount: agent.skill_ids?.length ?? 0,
      wikiEnabled: Boolean(agent.enabled_builtin_tools?.includes('wiki')),
      cronCount: stats?.cronCount ?? 0,
    };
  });

  return { agents, status: 'ok' };
}

export function useTeamAssetsHubSummary({
  enabled = true,
  refreshKey = 0,
}: UseTeamAssetsHubSummaryOptions = {}): UseTeamAssetsHubSummaryResult {
  const enableMemory = useConfigStore((state) => state.enableMemory);

  const [summary, setSummary] = useState<TeamAssetsHubSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!enabled) {
      setSummary(null);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const [skillResult, pendingResult] = await Promise.allSettled([listSkills(), getPendingMemories()]);
      const overview = await loadAgentOverview();

      setSummary({
        enableMemory,
        skillCount: skillResult.status === 'fulfilled' ? skillResult.value.total : 0,
        skillStatus: skillResult.status === 'fulfilled' ? 'ok' : 'unavailable',
        pendingCount: pendingResult.status === 'fulfilled' ? pendingResult.value.total : 0,
        pendingStatus: pendingResult.status === 'fulfilled' ? 'ok' : 'unavailable',
        agents: overview.agents,
        agentsStatus: overview.status,
      });
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : 'Failed to load team assets summary';
      setError(message);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [enableMemory, enabled]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return { summary, loading, error, reload: load };
}
