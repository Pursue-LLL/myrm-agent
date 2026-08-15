'use client';

/**
 * [INPUT]
 * @/services/agent::getAgent, getAgentReadiness (POS: Agent profile and readiness API client)
 * @/services/memory/sharedContexts::listSharedContextBindingsForTarget, listSharedContexts, listSharedContextWriteProposals (POS: Shared Context frontend API client)
 * @/store/useConfigStore (POS: Global memory policy configuration store)
 *
 * [OUTPUT]
 * useAgentLoadoutSummary: Hook assembling agent loadout read model from existing APIs.
 * readinessLevelTone: Tailwind class helper for readiness badge styling.
 *
 * [POS]
 * Loadout data orchestration hook. Parallel-fetches agent, readiness, shared-context bindings,
 * pending proposal counts, and global memory policy without introducing a new backend aggregate API.
 */

import { useCallback, useEffect, useState } from 'react';

import {
  getAgent,
  getAgentReadiness,
  type Agent,
  type AgentReadinessReport,
  type ReadinessLevel,
} from '@/services/agent';
import {
  listSharedContextBindingsForTarget,
  listSharedContexts,
  listSharedContextWriteProposals,
  type SharedContext,
  type SharedContextBinding,
} from '@/services/memory/sharedContexts';
import useConfigStore from '@/store/useConfigStore';

export type LoadoutFetchStatus = 'ok' | 'unavailable';

export interface AgentLoadoutMemoryPolicy {
  enableMemory: boolean;
  requireConfirmation: boolean;
  autoExtraction: boolean;
  conversationSearch: boolean;
  preCompactEnabled: boolean;
  preCompactBudgetTokens: number;
}

export interface AgentLoadoutSummaryData {
  agent: Agent | null;
  readiness: AgentReadinessReport | null;
  readinessStatus: LoadoutFetchStatus;
  sharedContextBindings: SharedContextBinding[];
  boundContextNames: string[];
  bindingsStatus: LoadoutFetchStatus;
  proposalsStatus: LoadoutFetchStatus;
  pendingProposalCount: number;
  wikiEnabled: boolean;
  skillCount: number;
  memoryPolicy: AgentLoadoutMemoryPolicy;
}

interface UseAgentLoadoutSummaryOptions {
  agentId: string | null;
  skillCount?: number;
  enabled?: boolean;
  refreshKey?: number;
}

interface UseAgentLoadoutSummaryResult {
  data: AgentLoadoutSummaryData | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

interface ProposalCountResult {
  count: number;
  status: LoadoutFetchStatus;
}

async function countPendingProposalsForBindings(
  bindings: SharedContextBinding[],
  contexts: SharedContext[],
): Promise<ProposalCountResult> {
  const activeContextIds = new Set(
    contexts.filter((context) => context.status === 'active').map((context) => context.id),
  );
  const relevantBindings = bindings.filter((binding) => activeContextIds.has(binding.context_id));
  if (relevantBindings.length === 0) {
    return { count: 0, status: 'ok' };
  }

  const uniqueContextIds = [...new Set(relevantBindings.map((binding) => binding.context_id))];
  const proposalLists = await Promise.all(
    uniqueContextIds.map((contextId) =>
      listSharedContextWriteProposals(contextId, { status: 'pending', limit: 50 }).catch(() => null),
    ),
  );

  if (proposalLists.some((response) => response === null)) {
    return { count: 0, status: 'unavailable' };
  }

  const count = proposalLists.reduce(
    (sum, response) => sum + (response!.total ?? response!.items.length),
    0,
  );
  return { count, status: 'ok' };
}

export function useAgentLoadoutSummary({
  agentId,
  skillCount = 0,
  enabled = true,
  refreshKey = 0,
}: UseAgentLoadoutSummaryOptions): UseAgentLoadoutSummaryResult {
  const enableMemory = useConfigStore((state) => state.enableMemory);
  const memoryRequireConfirmation = useConfigStore((state) => state.memoryRequireConfirmation);
  const enableMemoryAutoExtraction = useConfigStore((state) => state.enableMemoryAutoExtraction);
  const memoryEnableConversationSearch = useConfigStore((state) => state.memoryEnableConversationSearch);
  const preCompactEnabled = useConfigStore((state) => state.preCompactEnabled);
  const preCompactBudgetTokens = useConfigStore((state) => state.preCompactBudgetTokens);

  const [data, setData] = useState<AgentLoadoutSummaryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!enabled || !agentId) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    const policySnapshot: AgentLoadoutMemoryPolicy = {
      enableMemory,
      requireConfirmation: memoryRequireConfirmation,
      autoExtraction: enableMemoryAutoExtraction,
      conversationSearch: memoryEnableConversationSearch,
      preCompactEnabled,
      preCompactBudgetTokens,
    };

    try {
      const [agentResult, readinessResult] = await Promise.allSettled([
        getAgent(agentId),
        getAgentReadiness(agentId),
      ]);

      if (agentResult.status === 'rejected') {
        throw agentResult.reason;
      }

      const agent = agentResult.value;
      let readinessStatus: LoadoutFetchStatus = 'ok';
      let readiness: AgentReadinessReport | null = null;
      if (readinessResult.status === 'fulfilled') {
        readiness = readinessResult.value;
      } else {
        readinessStatus = 'unavailable';
      }

      let bindingsStatus: LoadoutFetchStatus = 'ok';
      let sharedContextBindings: SharedContextBinding[] = [];
      let contexts: SharedContext[] = [];

      try {
        const [bindingResponse, contextResponse] = await Promise.all([
          listSharedContextBindingsForTarget('agent', agentId),
          listSharedContexts(),
        ]);
        sharedContextBindings = bindingResponse.items;
        contexts = contextResponse.items;
      } catch {
        bindingsStatus = 'unavailable';
      }

      const contextById = new Map(contexts.map((context) => [context.id, context]));
      const boundContextNames =
        bindingsStatus === 'ok'
          ? sharedContextBindings
              .map((binding) => contextById.get(binding.context_id)?.name)
              .filter((name): name is string => Boolean(name))
          : [];

      const proposalResult =
        bindingsStatus === 'ok'
          ? await countPendingProposalsForBindings(sharedContextBindings, contexts)
          : { count: 0, status: 'unavailable' as LoadoutFetchStatus };

      const wikiEnabled = (agent.enabled_builtin_tools ?? []).includes('wiki');
      const resolvedSkillCount = skillCount > 0 ? skillCount : (agent.skill_ids?.length ?? 0);

      setData({
        agent,
        readiness,
        readinessStatus,
        sharedContextBindings,
        boundContextNames,
        bindingsStatus,
        proposalsStatus: proposalResult.status,
        pendingProposalCount: proposalResult.count,
        wikiEnabled,
        skillCount: resolvedSkillCount,
        memoryPolicy: policySnapshot,
      });
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : 'Failed to load agent loadout';
      setError(message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [
    agentId,
    enabled,
    enableMemory,
    memoryRequireConfirmation,
    enableMemoryAutoExtraction,
    memoryEnableConversationSearch,
    preCompactEnabled,
    preCompactBudgetTokens,
    skillCount,
    refreshKey,
  ]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, loading, error, reload: load };
}

export function readinessLevelTone(level: ReadinessLevel | undefined): string {
  switch (level) {
    case 'blocked':
      return 'text-destructive border-destructive/40 bg-destructive/5';
    case 'warning':
      return 'text-amber-600 dark:text-amber-400 border-amber-500/40 bg-amber-500/5';
    default:
      return 'text-emerald-600 dark:text-emerald-400 border-emerald-500/40 bg-emerald-500/5';
  }
}
