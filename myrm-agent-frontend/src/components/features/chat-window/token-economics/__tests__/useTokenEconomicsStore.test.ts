import { describe, it, expect, beforeEach } from 'vitest';
import { useTokenEconomicsStore } from '../useTokenEconomicsStore';
import type { ProviderBalanceInfo } from '../tokenEconomicsTypes';

describe('useTokenEconomicsStore', () => {
  beforeEach(() => {
    useTokenEconomicsStore.getState().resetStore();
  });

  it('initializes with default provider balances', () => {
    const state = useTokenEconomicsStore.getState();
    expect(state.sessionSnapshots).toEqual({});
    expect(state.isBalanceModalOpen).toBe(false);
    expect(state.isLoadingBalances).toBe(false);
    expect(state.providerBalances.deepseek).toBeDefined();
    expect(state.providerBalances.openai).toBeDefined();
    expect(state.providerBalances.anthropic).toBeDefined();
    expect(state.providerBalances.bailian).toBeDefined();
  });

  it('records token usage and creates cost estimate for chat session', () => {
    useTokenEconomicsStore.getState().recordTokenUsage(
      'chat-alpha',
      'deepseek-chat',
      {
        promptTokens: 2000,
        completionTokens: 3000,
        totalTokens: 5000,
      },
      'deepseek',
    );

    const snapshot = useTokenEconomicsStore.getState().sessionSnapshots['chat-alpha'];
    expect(snapshot).toBeDefined();
    expect(snapshot.chatId).toBe('chat-alpha');
    expect(snapshot.modelId).toBe('deepseek-chat');
    expect(snapshot.usage.totalTokens).toBe(5000);
    expect(snapshot.costEstimate.currency).toBe('CNY');
    expect(snapshot.costEstimate.totalCost).toBeGreaterThan(0);
  });

  it('updates provider balances and handles activeChatId', () => {
    const customBalance: ProviderBalanceInfo = {
      provider: 'custom',
      providerName: 'Custom Host',
      availableBalance: 99.9,
      currency: 'USD',
      watermarkLevel: 'healthy',
      status: 'active',
      lastChecked: 1760000000000,
    };

    useTokenEconomicsStore.getState().setProviderBalances([customBalance]);
    expect(useTokenEconomicsStore.getState().providerBalances.custom).toEqual(customBalance);

    useTokenEconomicsStore.getState().setActiveChatId('chat-active-1');
    expect(useTokenEconomicsStore.getState().activeChatId).toBe('chat-active-1');
  });

  it('toggles balance modal open and closed', () => {
    useTokenEconomicsStore.getState().toggleBalanceModal(true);
    expect(useTokenEconomicsStore.getState().isBalanceModalOpen).toBe(true);

    useTokenEconomicsStore.getState().toggleBalanceModal(false);
    expect(useTokenEconomicsStore.getState().isBalanceModalOpen).toBe(false);

    useTokenEconomicsStore.getState().toggleBalanceModal();
    expect(useTokenEconomicsStore.getState().isBalanceModalOpen).toBe(true);
  });

  it('clears specific session usage', () => {
    useTokenEconomicsStore.getState().recordTokenUsage('chat-1', 'gpt-4o', {
      promptTokens: 100,
      completionTokens: 200,
      totalTokens: 300,
    });
    expect(useTokenEconomicsStore.getState().sessionSnapshots['chat-1']).toBeDefined();

    useTokenEconomicsStore.getState().clearSessionUsage('chat-1');
    expect(useTokenEconomicsStore.getState().sessionSnapshots['chat-1']).toBeUndefined();
  });

  it('refreshes provider balances with simulated latency', async () => {
    const refreshPromise = useTokenEconomicsStore.getState().refreshProviderBalances();
    expect(useTokenEconomicsStore.getState().isLoadingBalances).toBe(true);

    await refreshPromise;
    expect(useTokenEconomicsStore.getState().isLoadingBalances).toBe(false);
    expect(useTokenEconomicsStore.getState().providerBalances.deepseek.lastChecked).toBeGreaterThan(0);
  });
});
