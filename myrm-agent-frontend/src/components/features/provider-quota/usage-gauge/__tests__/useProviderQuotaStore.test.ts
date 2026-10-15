import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useProviderQuotaStore } from '../useProviderQuotaStore';

describe('useProviderQuotaStore', () => {
  beforeEach(() => {
    useProviderQuotaStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  it('初始状态具备默认活动渠道与完整分析模型分布', () => {
    const state = useProviderQuotaStore.getState();
    expect(state.activeProviderId).toBe('nous');
    expect(state.isAnalyticsModalOpen).toBe(false);
    expect(state.isExhaustionWarningOpen).toBe(false);
    expect(state.modelDistributions.length).toBeGreaterThan(0);
    expect(state.agentUsages.length).toBeGreaterThan(0);
    expect(state.dailyTrends.length).toBe(7);
  });

  it('切换到危急渠道时能够自动展开耗尽告警', () => {
    // openrouter 默认状态是 critical
    useProviderQuotaStore.getState().setActiveProvider('openrouter');

    const state = useProviderQuotaStore.getState();
    expect(state.activeProviderId).toBe('openrouter');
    expect(state.isExhaustionWarningOpen).toBe(true);

    // 切换回健康渠道，告警自动收起
    useProviderQuotaStore.getState().setActiveProvider('nous');
    expect(useProviderQuotaStore.getState().isExhaustionWarningOpen).toBe(false);
  });

  it('更新遥测响应头能够合并快照并派发耗尽告警事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    // 将当前 nous 提供商更新至耗尽状态
    useProviderQuotaStore.getState().updateFromTelemetryHeaders('nous', {
      'x-ratelimit-remaining-tokens': '1000',
      'x-ratelimit-limit-tokens': '5000000',
      'x-portal-balance-usd': '0.01',
    });

    const state = useProviderQuotaStore.getState();
    const nous = state.providers.nous;
    expect(nous.remainingTokens).toBe(1000);
    expect(nous.balanceUsd).toBe(0.01);
    expect(nous.status).toBe('critical');
    expect(state.isExhaustionWarningOpen).toBe(true);

    expect(dispatchSpy).toHaveBeenCalled();
    const event = dispatchSpy.mock.calls.find(
      (call) => (call[0] as CustomEvent).type === 'myrm:provider-quota-exhausted'
    );
    expect(event).toBeDefined();
  });

  it('触发故障转移能够执行平滑自愈并广播 failover 事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    useProviderQuotaStore.getState().triggerFailoverRecovery('anthropic');

    const state = useProviderQuotaStore.getState();
    expect(state.activeProviderId).toBe('anthropic');
    expect(state.isExhaustionWarningOpen).toBe(false);
    expect(state.lastFailoverAction).toEqual(
      expect.objectContaining({
        sourceProviderId: 'nous',
        targetProviderId: 'anthropic',
        reason: 'insufficient_quota',
      })
    );

    const event = dispatchSpy.mock.calls.find(
      (call) => (call[0] as CustomEvent).type === 'myrm:provider-failover'
    );
    expect(event).toBeDefined();
  });

  it('模拟消耗 Token 能够实时扣减额度并更新状态', () => {
    const initialTokens =
      useProviderQuotaStore.getState().providers.nous.remainingTokens;

    // 消耗 1,000,000 Tokens 与 $3.50
    useProviderQuotaStore.getState().simulateQuotaConsumption(1_000_000, 3.5);

    const updated = useProviderQuotaStore.getState().providers.nous;
    expect(updated.remainingTokens).toBe(initialTokens - 1_000_000);
    expect(updated.balanceUsd).toBe(15.0);
  });
});
