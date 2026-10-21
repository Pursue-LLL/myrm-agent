import { describe, it, expect } from 'vitest';
import {
  calculateQuotaHealth,
  estimateRemainingDays,
  formatTokenCount,
  formatCurrency,
  parseTelemetryHeaders,
  getDefaultProviderSnapshots,
} from '../quotaTelemetryParser';

describe('quotaTelemetryParser', () => {
  it('正确根据剩余百分比和 Token 储备判定健康等级', () => {
    expect(calculateQuotaHealth(80, 5_000_000)).toBe('healthy');
    expect(calculateQuotaHealth(18, 90_000)).toBe('warning');
    expect(calculateQuotaHealth(4, 15_000)).toBe('critical');
    expect(calculateQuotaHealth(0, 0)).toBe('exhausted');
    expect(calculateQuotaHealth(-5, 0)).toBe('exhausted');
  });

  it('根据 USD 余额与日均消耗率计算预估可用天数', () => {
    expect(estimateRemainingDays(20, 2)).toBe(10);
    expect(estimateRemainingDays(18.5, 1.25)).toBe(14.8);
    expect(estimateRemainingDays(0, 2)).toBe(0);
    expect(estimateRemainingDays(10, 0)).toBe(0);
  });

  it('正确格式化 Token 计数和 USD 金额', () => {
    expect(formatTokenCount(2_500_000)).toBe('2.50M');
    expect(formatTokenCount(450_000)).toBe('450.0K');
    expect(formatTokenCount(850)).toBe('850');

    expect(formatCurrency(18.5)).toBe('$18.50');
    expect(formatCurrency(0.456)).toBe('$0.46');
  });

  it('正确解析 OpenAI / OpenRouter 遥测响应头', () => {
    const headers = {
      'x-ratelimit-remaining-tokens': '2000000',
      'x-ratelimit-limit-tokens': '10000000',
    };

    const parsed = parseTelemetryHeaders('openai', headers);
    expect(parsed.id).toBe('openai');
    expect(parsed.remainingTokens).toBe(2000000);
    expect(parsed.totalTokensLimit).toBe(10000000);
    expect(parsed.remainingPercentage).toBe(20);
    expect(parsed.status).toBe('warning');
  });

  it('正确解析 Anthropic 专属响应头', () => {
    const headers = {
      'anthropic-ratelimit-tokens-remaining': '6000000',
      'anthropic-ratelimit-tokens-limit': '8000000',
    };

    const parsed = parseTelemetryHeaders('anthropic', headers);
    expect(parsed.id).toBe('anthropic');
    expect(parsed.remainingTokens).toBe(6000000);
    expect(parsed.totalTokensLimit).toBe(8000000);
    expect(parsed.remainingPercentage).toBe(75);
    expect(parsed.status).toBe('healthy');
  });

  it('正确解析 Nous Portal 余额响应头', () => {
    const headers = {
      'x-portal-balance-usd': '14.25',
      'x-ratelimit-remaining-tokens': '4000000',
      'x-ratelimit-limit-tokens': '5000000',
    };

    const parsed = parseTelemetryHeaders('nous', headers);
    expect(parsed.id).toBe('nous');
    expect(parsed.balanceUsd).toBe(14.25);
    expect(parsed.remainingPercentage).toBe(80);
    expect(parsed.status).toBe('healthy');
  });

  it('预置多渠道 Provider 初始快照包含完整厂商定义', () => {
    const snapshots = getDefaultProviderSnapshots();
    expect(snapshots.nous.name).toContain('Nous Portal');
    expect(snapshots.openai.id).toBe('openai');
    expect(snapshots.anthropic.id).toBe('anthropic');
    expect(snapshots.local.supportsLiveTelemetry).toBe(false);
  });
});
