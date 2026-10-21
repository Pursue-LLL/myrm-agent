import { useEffect, useMemo } from 'react';
import { useLocale } from 'next-intl';
import useAgentStore from '@/store/useAgentStore';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';

/**
 * Resolve an agent_id to a localized human-friendly name via the cached agent list.
 * Built-in agents render their locale-specific name (e.g. zh → 通用助手).
 * Triggers a one-time fetch if agents haven't been loaded yet (deduped by store).
 * Falls back to raw agentId when the agent is not found (e.g. deleted).
 */
export function useAgentName(agentId: string | null | undefined): string | null {
  const locale = useLocale();
  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => s.fetchAgents);

  useEffect(() => {
    if (agentId) {
      fetchAgents();
    }
  }, [agentId, fetchAgents]);

  if (!agentId) {
    return null;
  }
  const agent = agents.find((a) => a.id === agentId);
  if (!agent) {
    return agentId;
  }
  return getBuiltinAgentName(agent.id, agent.name, locale);
}

/**
 * Batch-resolve multiple agent_ids in a single render pass.
 * Returns a stable Map<agentId, displayName> via useMemo to avoid re-render churn.
 * Built-in agents render their locale-specific name.
 */
export function useAgentNameMap(agentIds: (string | null)[]): Map<string, string> {
  const locale = useLocale();
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
      if (!id) {
        continue;
      }
      if (map.has(id)) {
        continue;
      }
      const agent = agents.find((a) => a.id === id);
      map.set(id, agent ? getBuiltinAgentName(agent.id, agent.name, locale) : id);
    }
    return map;
  }, [agentIds, agents, locale]);
}
