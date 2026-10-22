import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useSwarmExecutionStore } from '../useSwarmExecutionStore';
import type { OwnerRiskItem, RecalledRuleItem } from '../swarmTypes';

describe('useSwarmExecutionStore', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useSwarmExecutionStore.getState().reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('initializes with default state', () => {
    const state = useSwarmExecutionStore.getState();
    expect(state.isSwarmEnabled).toBe(false);
    expect(state.concurrencyQuota).toBe(5);
    expect(state.subagentTasks).toEqual([]);
    expect(state.recalledRules).toEqual([]);
    expect(state.ownerRisks).toEqual([]);
  });

  it('updates swarm toggle and concurrency quota with limits', () => {
    useSwarmExecutionStore.getState().setSwarmEnabled(true);
    expect(useSwarmExecutionStore.getState().isSwarmEnabled).toBe(true);

    useSwarmExecutionStore.getState().setConcurrencyQuota(12);
    expect(useSwarmExecutionStore.getState().concurrencyQuota).toBe(10); // clamped to 10

    useSwarmExecutionStore.getState().setConcurrencyQuota(0);
    expect(useSwarmExecutionStore.getState().concurrencyQuota).toBe(1); // clamped to 1
  });

  it('fetches and manages recalled rules and toggles active state', async () => {
    const mockRules: RecalledRuleItem[] = [
      {
        ruleId: 'r_01',
        summary: 'Vegan menu required',
        sourceTurnId: 'turn_02',
        confidence: 0.98,
        isActive: true,
        category: 'menu',
      },
    ];

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        code: 0,
        data: {
          rules: [
            {
              rule_id: 'r_01',
              summary: 'Vegan menu required',
              source_turn_id: 'turn_02',
              confidence: 0.98,
              is_active: true,
              category: 'menu',
            },
          ],
          active_prompt: '### [@active_rules: Vegan menu required]',
        },
      }),
    } as unknown as Response);

    await useSwarmExecutionStore.getState().fetchRecalledRules('chat_100');
    expect(useSwarmExecutionStore.getState().recalledRules.length).toBe(1);
    expect(useSwarmExecutionStore.getState().activeRulesPrompt).toContain('Vegan menu required');

    // Toggle rule active
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 0, data: { is_active: false } }),
    } as unknown as Response);

    await useSwarmExecutionStore.getState().toggleRuleActive('chat_100', 'r_01', false);
    expect(useSwarmExecutionStore.getState().recalledRules[0].isActive).toBe(false);
  });

  it('fetches and updates owner risks confirmation', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        code: 0,
        data: [
          {
            risk_id: 'risk_01',
            title: 'Substation limit',
            description: 'May exceed 40kW',
            severity: 'high',
            is_confirmed: false,
            confirmed_by: '',
            external_constraint_type: 'power',
            remediation_hint: 'Verify with property',
          },
        ],
      }),
    } as unknown as Response);

    await useSwarmExecutionStore.getState().fetchOwnerRisks('chat_100');
    expect(useSwarmExecutionStore.getState().ownerRisks.length).toBe(1);
    expect(useSwarmExecutionStore.getState().ownerRisks[0].isConfirmed).toBe(false);

    // Toggle risk confirmation
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 0, data: { is_confirmed: true } }),
    } as unknown as Response);

    await useSwarmExecutionStore.getState().toggleRiskConfirm('chat_100', 'risk_01', true, 'owner_bob');
    expect(useSwarmExecutionStore.getState().ownerRisks[0].isConfirmed).toBe(true);
    expect(useSwarmExecutionStore.getState().ownerRisks[0].confirmedBy).toBe('owner_bob');
  });
});
