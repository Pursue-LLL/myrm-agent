import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAgentLoadoutSummary } from '@/components/features/loadout/useAgentLoadoutSummary';

const agentApi = vi.hoisted(() => ({
  getAgent: vi.fn(),
  getAgentReadiness: vi.fn(),
}));

const memoryApi = vi.hoisted(() => ({
  listSharedContextBindingsForTarget: vi.fn(),
  listSharedContexts: vi.fn(),
  listSharedContextWriteProposals: vi.fn(),
}));

const configState = vi.hoisted(() => ({
  enableMemory: true,
  memoryRequireConfirmation: false,
  enableMemoryAutoExtraction: true,
  memoryEnableConversationSearch: true,
  preCompactEnabled: false,
  preCompactBudgetTokens: 0,
}));

vi.mock('@/services/agent', () => ({
  getAgent: agentApi.getAgent,
  getAgentReadiness: agentApi.getAgentReadiness,
}));

vi.mock('@/services/memorySharedContexts', () => ({
  listSharedContextBindingsForTarget: memoryApi.listSharedContextBindingsForTarget,
  listSharedContexts: memoryApi.listSharedContexts,
  listSharedContextWriteProposals: memoryApi.listSharedContextWriteProposals,
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: typeof configState) => unknown) => selector(configState),
}));

describe('useAgentLoadoutSummary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    agentApi.getAgent.mockResolvedValue({
      id: 'agent-1',
      skill_ids: ['skill-1'],
      enabled_builtin_tools: ['wiki'],
    });
    agentApi.getAgentReadiness.mockResolvedValue({
      agent_id: 'agent-1',
      overall_level: 'ready',
      items: [],
      checked_at: 0,
    });
    memoryApi.listSharedContextBindingsForTarget.mockResolvedValue({ items: [], total: 0 });
    memoryApi.listSharedContexts.mockResolvedValue({ items: [], total: 0 });
  });

  it('reloads when refreshKey changes', async () => {
    const { rerender } = renderHook(
      ({ refreshKey }) =>
        useAgentLoadoutSummary({
          agentId: 'agent-1',
          enabled: true,
          refreshKey,
        }),
      { initialProps: { refreshKey: 0 } },
    );

    await waitFor(() => {
      expect(agentApi.getAgent).toHaveBeenCalledTimes(1);
    });

    rerender({ refreshKey: 1 });

    await waitFor(() => {
      expect(agentApi.getAgent).toHaveBeenCalledTimes(2);
    });
  });
});
