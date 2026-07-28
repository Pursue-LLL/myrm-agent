import { useEffect, useMemo } from 'react';
import useAgentStore from '@/store/useAgentStore';

/**
 * Resolve an agent_id to a human-friendly name via the cached agent list.
 * Triggers a one-time fetch if agents haven't been loaded yet (deduped by store).
 * Falls back to raw agentId when the agent is not found (e.g. deleted).
 */
export function useAgentName(agentId: string | null | undefined): string | null {
  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => s.fetchAgents);

  useEffect(() => {
    if (agentId) {
      fetchAgents();
    }
  }, [agentId, fetchAgents]);

  if (!agentId) return null;
  return agents.find((a) => a.id === agentId)?.name ?? agentId;
}

/**
 * Batch-resolve multiple agent_ids in a single render pass.
 * Returns a stable Map<agentId, displayName> via useMemo to avoid re-render churn.
 */
export function useAgentNameMap(agentIds: (string | null)[]): Map<string, string> {
  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => s.fetchAgents);

  const hasIds = agentIds.some(Boolean);

  useEffect(() => {
    if (hasIds) {
      fetchAgents();
    }
  }, [hasIds, fetchAgents]);

  return useMemo(() => {
    const map = new Map<string, string>();
    for (const id of agentIds) {
      if (!id) continue;
      if (map.has(id)) continue;
      map.set(id, agents.find((a) => a.id === id)?.name ?? id);
    }
    return map;
  }, [agentIds, agents]);
}
