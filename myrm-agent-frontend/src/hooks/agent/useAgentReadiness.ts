/**
 * [INPUT]
 * - @/services/agent::getAgentReadiness (POS: readiness API)
 * - @/store/useChatStore::agentConfig (POS: current agent selection)
 *
 * [OUTPUT]
 * - useAgentReadiness: SWR hook returning AgentReadinessReport for active agent
 *
 * [POS]
 * Proactive readiness polling for the active agent. Feeds ComposerReadinessBadge
 * and Settings readiness indicator. 5min revalidation aligned with server cache TTL.
 */

import useSWR from 'swr';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import {
  type AgentReadinessReport,
  type ReadinessLevel,
  getAgentReadiness,
  invalidateAgentReadiness,
} from '@/services/agent';

const SWR_KEY_PREFIX = 'agent-readiness:';
const REVALIDATE_INTERVAL_MS = 5 * 60 * 1000; // 5min — matches server TTL

export function useAgentReadiness() {
  const agentId = useChatStore(useShallow((s) => s.agentConfig?.agentId));

  const { data, error, isLoading, mutate } = useSWR<AgentReadinessReport>(
    agentId ? `${SWR_KEY_PREFIX}${agentId}` : null,
    () => getAgentReadiness(agentId!),
    {
      suspense: false,
      revalidateOnFocus: false,
      refreshInterval: REVALIDATE_INTERVAL_MS,
      errorRetryCount: 1,
      dedupingInterval: 30_000,
    },
  );

  const refresh = async () => {
    if (!agentId) return;
    await invalidateAgentReadiness(agentId);
    await mutate();
  };

  return {
    report: data ?? null,
    overallLevel: (data?.overall_level ?? 'ready') as ReadinessLevel,
    hasIssues: !!data && data.overall_level !== 'ready',
    isLoading,
    error,
    refresh,
  };
}
