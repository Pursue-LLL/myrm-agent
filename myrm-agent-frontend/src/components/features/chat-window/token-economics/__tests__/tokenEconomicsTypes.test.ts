import { describe, it, expect } from 'vitest';
import type {
  ProviderKind,
  TokenUsageMetrics,
  TokenPricingRate,
  TokenCostEstimate,
  BalanceWatermarkLevel,
  ProviderBalanceInfo,
  SessionEconomicsSnapshot,
  TokenEconomicsStoreState,
} from '../tokenEconomicsTypes';

describe('tokenEconomicsTypes', () => {
  it('validates domain types and contracts correctly', () => {
    const provider: ProviderKind = 'deepseek';
    expect(provider).toBe('deepseek');

    const usage: TokenUsageMetrics = {
      promptTokens: 1200,
      completionTokens: 3500,
      totalTokens: 4700,
    };
    expect(usage.totalTokens).toBe(4700);

    const rate: TokenPricingRate = {
      promptCostPer1k: 0.001,
      completionCostPer1k: 0.002,
      currency: 'CNY',
    };
    expect(rate.currency).toBe('CNY');

    const costEstimate: TokenCostEstimate = {
      promptCost: 0.0012,
      completionCost: 0.007,
      totalCost: 0.0082,
      currency: 'CNY',
      formattedCost: '¥0.0082',
    };
    expect(costEstimate.formattedCost).toBe('¥0.0082');

    const watermark: BalanceWatermarkLevel = 'healthy';
    expect(watermark).toBe('healthy');

    const balanceInfo: ProviderBalanceInfo = {
      provider: 'deepseek',
      providerName: 'DeepSeek',
      availableBalance: 88.5,
      totalQuota: 100,
      currency: 'CNY',
      expiresAt: null,
      watermarkLevel: 'healthy',
      status: 'active',
      lastChecked: 1760000000000,
    };
    expect(balanceInfo.providerName).toBe('DeepSeek');
    expect(balanceInfo.watermarkLevel).toBe('healthy');

    const snapshot: SessionEconomicsSnapshot = {
      chatId: 'chat-101',
      modelId: 'deepseek-chat',
      provider: 'deepseek',
      usage,
      costEstimate,
      updatedAt: 1760000000000,
    };
    expect(snapshot.chatId).toBe('chat-101');
    expect(snapshot.costEstimate.totalCost).toBe(0.0082);

    const storeState: TokenEconomicsStoreState = {
      sessionSnapshots: {
        'chat-101': snapshot,
      },
      providerBalances: {
        deepseek: balanceInfo,
      },
      activeChatId: 'chat-101',
      isBalanceModalOpen: false,
      isLoadingBalances: false,
    };
    expect(storeState.activeChatId).toBe('chat-101');
    expect(storeState.sessionSnapshots['chat-101'].modelId).toBe('deepseek-chat');
  });
});
