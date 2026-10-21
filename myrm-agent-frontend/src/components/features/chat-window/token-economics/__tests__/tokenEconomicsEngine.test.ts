import { describe, it, expect } from 'vitest';
import {
  resolvePricingRate,
  formatCurrencyAmount,
  formatTokenCount,
  calculateTokenCost,
  determineWatermarkLevel,
  validateProviderBalanceInfo,
} from '../tokenEconomicsEngine';

describe('tokenEconomicsEngine', () => {
  describe('resolvePricingRate', () => {
    it('resolves known models correctly', () => {
      const deepseekRate = resolvePricingRate('deepseek-chat');
      expect(deepseekRate.currency).toBe('CNY');
      expect(deepseekRate.promptCostPer1k).toBe(0.001);

      const openaiRate = resolvePricingRate('gpt-4o');
      expect(openaiRate.currency).toBe('USD');
      expect(openaiRate.promptCostPer1k).toBe(0.0025);

      const claudeRate = resolvePricingRate('claude-3-5-sonnet');
      expect(claudeRate.currency).toBe('USD');
      expect(claudeRate.completionCostPer1k).toBe(0.015);

      const qwenRate = resolvePricingRate('qwen-max');
      expect(qwenRate.currency).toBe('CNY');
      expect(qwenRate.promptCostPer1k).toBe(0.02);
    });

    it('falls back to default currency based on provider', () => {
      const fallbackCny = resolvePricingRate('unknown-model', 'deepseek');
      expect(fallbackCny.currency).toBe('CNY');

      const fallbackUsd = resolvePricingRate('unknown-model', 'openai');
      expect(fallbackUsd.currency).toBe('USD');
    });
  });

  describe('formatCurrencyAmount', () => {
    it('formats zero correctly', () => {
      expect(formatCurrencyAmount(0, 'USD')).toBe('$0.00');
      expect(formatCurrencyAmount(0, 'CNY')).toBe('¥0.00');
    });

    it('formats micro amounts below 0.01 with 4 decimals', () => {
      expect(formatCurrencyAmount(0.0042, 'USD')).toBe('$0.0042');
      expect(formatCurrencyAmount(0.008, 'CNY')).toBe('¥0.0080');
    });

    it('formats standard amounts with 2 decimals', () => {
      expect(formatCurrencyAmount(12.5, 'USD')).toBe('$12.50');
      expect(formatCurrencyAmount(88.456, 'CNY')).toBe('¥88.46');
    });
  });

  describe('formatTokenCount', () => {
    it('formats small and zero token counts', () => {
      expect(formatTokenCount(0)).toBe('0');
      expect(formatTokenCount(-10)).toBe('0');
      expect(formatTokenCount(540)).toBe('540');
    });

    it('formats thousands into k notation', () => {
      expect(formatTokenCount(1000)).toBe('1.0k');
      expect(formatTokenCount(12450)).toBe('12.5k');
      expect(formatTokenCount(999900)).toBe('999.9k');
    });

    it('formats millions into M notation', () => {
      expect(formatTokenCount(1000000)).toBe('1.00M');
      expect(formatTokenCount(2500000)).toBe('2.50M');
    });
  });

  describe('calculateTokenCost', () => {
    it('calculates cost from usage and rate accurately', () => {
      const rate = {
        promptCostPer1k: 0.002,
        completionCostPer1k: 0.006,
        currency: 'USD' as const,
      };

      const usage = {
        promptTokens: 2000,
        completionTokens: 1000,
        totalTokens: 3000,
      };

      const result = calculateTokenCost(usage, rate);
      expect(result.promptCost).toBe(0.004);
      expect(result.completionCost).toBe(0.006);
      expect(result.totalCost).toBe(0.01);
      expect(result.formattedCost).toBe('$0.01');
    });
  });

  describe('determineWatermarkLevel', () => {
    it('evaluates ratio when totalQuota is provided', () => {
      expect(determineWatermarkLevel(5, 100)).toBe('critical'); // 5%
      expect(determineWatermarkLevel(20, 100)).toBe('warning'); // 20%
      expect(determineWatermarkLevel(60, 100)).toBe('healthy'); // 60%
    });

    it('evaluates absolute thresholds when totalQuota is absent', () => {
      expect(determineWatermarkLevel(3)).toBe('critical'); // <=5
      expect(determineWatermarkLevel(15)).toBe('warning'); // <=20
      expect(determineWatermarkLevel(50)).toBe('healthy'); // >20
    });
  });

  describe('validateProviderBalanceInfo', () => {
    it('validates a valid ProviderBalanceInfo', () => {
      const valid = {
        provider: 'deepseek',
        providerName: 'DeepSeek',
        availableBalance: 50,
        currency: 'CNY',
        watermarkLevel: 'healthy',
      };
      const result = validateProviderBalanceInfo(valid);
      expect(result.valid).toBe(true);
      expect(result.errors).toEqual([]);
    });

    it('rejects invalid inputs', () => {
      expect(validateProviderBalanceInfo(null).valid).toBe(false);

      const invalid = {
        provider: '',
        providerName: '',
        availableBalance: 'not-number',
        currency: 'EUR',
        watermarkLevel: 'unknown',
      };
      const result = validateProviderBalanceInfo(invalid);
      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThanOrEqual(4);
    });
  });
});
