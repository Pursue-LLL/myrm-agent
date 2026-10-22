/**
 * [INPUT]
 * - None (Pure domain type definitions for Session Token Economics and Provider Balance Card Suite)
 *
 * [OUTPUT]
 * - ProviderKind, TokenUsageMetrics, TokenPricingRate, TokenCostEstimate,
 *   ProviderBalanceInfo, SessionEconomicsSnapshot, TokenEconomicsStoreState
 *
 * [POS]
 * Unified types for Item 193 (P1): SessionTokenEconomicsAndProviderBalanceCardSuite.
 * Eliminates LLM blackbox anxiety by providing real-time session token metering,
 * cost projection, and upstream provider balance self-inspection.
 */

export type ProviderKind =
  | 'deepseek'
  | 'openai'
  | 'anthropic'
  | 'bailian'
  | 'custom';

export interface TokenUsageMetrics {
  readonly promptTokens: number;
  readonly completionTokens: number;
  readonly totalTokens: number;
}

export interface TokenPricingRate {
  readonly promptCostPer1k: number;
  readonly completionCostPer1k: number;
  readonly currency: 'USD' | 'CNY';
}

export interface TokenCostEstimate {
  readonly promptCost: number;
  readonly completionCost: number;
  readonly totalCost: number;
  readonly currency: 'USD' | 'CNY';
  readonly formattedCost: string;
}

export type BalanceWatermarkLevel = 'healthy' | 'warning' | 'critical';

export interface ProviderBalanceInfo {
  readonly provider: ProviderKind;
  readonly providerName: string;
  readonly availableBalance: number;
  readonly totalQuota?: number;
  readonly currency: 'USD' | 'CNY';
  readonly expiresAt?: string | null;
  readonly watermarkLevel: BalanceWatermarkLevel;
  readonly status: 'active' | 'expired' | 'rate_limited' | 'error';
  readonly lastChecked: number;
}

export interface SessionEconomicsSnapshot {
  readonly chatId: string;
  readonly modelId: string;
  readonly provider: ProviderKind;
  readonly usage: TokenUsageMetrics;
  readonly costEstimate: TokenCostEstimate;
  readonly updatedAt: number;
}

export interface TokenEconomicsStoreState {
  readonly sessionSnapshots: Readonly<Record<string, SessionEconomicsSnapshot>>;
  readonly providerBalances: Readonly<Record<string, ProviderBalanceInfo>>;
  readonly activeChatId: string | null;
  readonly isBalanceModalOpen: boolean;
  readonly isLoadingBalances: boolean;
}
