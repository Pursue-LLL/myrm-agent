/**
 * [INPUT]
 * - @/components/features/chat-window/token-economics/tokenEconomicsTypes
 *
 * [OUTPUT]
 * - resolvePricingRate, calculateTokenCost, determineWatermarkLevel,
 *   formatTokenCount, formatCurrencyAmount, validateProviderBalanceInfo
 *
 * [POS]
 * Pure computation engine for Item 193 (P1): SessionTokenEconomicsAndProviderBalanceCardSuite.
 * Calculates real-time model token fees, formats currencies, and evaluates provider watermarks.
 */

import type {
  ProviderKind,
  TokenUsageMetrics,
  TokenPricingRate,
  TokenCostEstimate,
  BalanceWatermarkLevel,
  ProviderBalanceInfo,
} from './tokenEconomicsTypes';

export const DEFAULT_MODEL_PRICING: Readonly<Record<string, TokenPricingRate>> = {
  // DeepSeek models
  'deepseek-chat': { promptCostPer1k: 0.001, completionCostPer1k: 0.002, currency: 'CNY' },
  'deepseek-reasoner': { promptCostPer1k: 0.004, completionCostPer1k: 0.016, currency: 'CNY' },

  // OpenAI models
  'gpt-4o': { promptCostPer1k: 0.0025, completionCostPer1k: 0.01, currency: 'USD' },
  'gpt-4o-mini': { promptCostPer1k: 0.00015, completionCostPer1k: 0.0006, currency: 'USD' },

  // Anthropic models
  'claude-3-5-sonnet': { promptCostPer1k: 0.003, completionCostPer1k: 0.015, currency: 'USD' },
  'claude-3-5-haiku': { promptCostPer1k: 0.0008, completionCostPer1k: 0.004, currency: 'USD' },

  // Alibaba Bailian Qwen models
  'qwen-max': { promptCostPer1k: 0.02, completionCostPer1k: 0.06, currency: 'CNY' },
  'qwen-plus': { promptCostPer1k: 0.0008, completionCostPer1k: 0.002, currency: 'CNY' },
};

const FALLBACK_PRICING_USD: TokenPricingRate = {
  promptCostPer1k: 0.002,
  completionCostPer1k: 0.006,
  currency: 'USD',
};

const FALLBACK_PRICING_CNY: TokenPricingRate = {
  promptCostPer1k: 0.002,
  completionCostPer1k: 0.006,
  currency: 'CNY',
};

export function resolvePricingRate(modelId: string, provider?: ProviderKind): TokenPricingRate {
  const normalized = modelId.toLowerCase();
  for (const [key, rate] of Object.entries(DEFAULT_MODEL_PRICING)) {
    if (normalized.includes(key)) {
      return rate;
    }
  }

  if (provider === 'deepseek' || provider === 'bailian') {
    return FALLBACK_PRICING_CNY;
  }
  return FALLBACK_PRICING_USD;
}

export function formatCurrencyAmount(amount: number, currency: 'USD' | 'CNY'): string {
  const prefix = currency === 'USD' ? '$' : '¥';
  if (amount === 0) {
    return `${prefix}0.00`;
  }
  if (amount < 0.01) {
    return `${prefix}${amount.toFixed(4)}`;
  }
  return `${prefix}${amount.toFixed(2)}`;
}

export function formatTokenCount(tokens: number): string {
  if (tokens <= 0) {
    return '0';
  }
  if (tokens < 1000) {
    return tokens.toString();
  }
  if (tokens < 1000000) {
    const k = Math.round(tokens / 100) / 10;
    return `${k.toFixed(1)}k`;
  }
  const m = Math.round(tokens / 10000) / 100;
  return `${m.toFixed(2)}M`;
}

export function calculateTokenCost(
  usage: TokenUsageMetrics,
  rate: TokenPricingRate,
): TokenCostEstimate {
  const promptCost = (Math.max(0, usage.promptTokens) / 1000) * rate.promptCostPer1k;
  const completionCost = (Math.max(0, usage.completionTokens) / 1000) * rate.completionCostPer1k;
  const totalCost = promptCost + completionCost;

  return {
    promptCost,
    completionCost,
    totalCost,
    currency: rate.currency,
    formattedCost: formatCurrencyAmount(totalCost, rate.currency),
  };
}

export function determineWatermarkLevel(
  availableBalance: number,
  totalQuota?: number,
): BalanceWatermarkLevel {
  if (totalQuota && totalQuota > 0) {
    const ratio = availableBalance / totalQuota;
    if (ratio <= 0.1) {
      return 'critical';
    }
    if (ratio <= 0.25) {
      return 'warning';
    }
    return 'healthy';
  }

  // Absolute threshold evaluation
  if (availableBalance <= 5) {
    return 'critical';
  }
  if (availableBalance <= 20) {
    return 'warning';
  }
  return 'healthy';
}

export function validateProviderBalanceInfo(balance: unknown): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];

  if (!balance || typeof balance !== 'object') {
    return { valid: false, errors: ['Balance info must be a non-null object'] };
  }

  const b = balance as Record<string, unknown>;

  if (typeof b.provider !== 'string' || !b.provider.trim()) {
    errors.push('provider must be a non-empty string');
  }
  if (typeof b.providerName !== 'string' || !b.providerName.trim()) {
    errors.push('providerName must be a non-empty string');
  }
  if (typeof b.availableBalance !== 'number' || isNaN(b.availableBalance)) {
    errors.push('availableBalance must be a valid number');
  }
  if (b.currency !== 'USD' && b.currency !== 'CNY') {
    errors.push('currency must be USD or CNY');
  }
  if (b.watermarkLevel !== 'healthy' && b.watermarkLevel !== 'warning' && b.watermarkLevel !== 'critical') {
    errors.push('watermarkLevel must be healthy, warning, or critical');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
