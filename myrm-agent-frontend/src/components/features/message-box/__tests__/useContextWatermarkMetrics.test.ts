import { describe, expect, it } from 'vitest';
import type { Message } from '@/store/chat/types';
import type { ContextBudget } from '@/store/chat/types';
import {
  resolveWeatherTier,
  calculateContextWatermarkMetrics,
} from '../useContextWatermarkMetrics';

function createMockBudget(currentTokens: number, usagePercent: number): ContextBudget {
  return {
    current_tokens: currentTokens,
    max_context_tokens: 128000,
    usage_percent: usagePercent,
    health_status: 'healthy',
  };
}

function createMockMessage(budget?: ContextBudget): Message {
  return {
    messageId: `msg-${Math.random()}`,
    chatId: 'chat-test-1',
    createdAt: new Date(),
    role: 'assistant',
    content: 'Hello',
    contextBudget: budget,
  };
}

describe('useContextWatermarkMetrics', () => {
  describe('resolveWeatherTier', () => {
    it('returns clear when usage < 25%', () => {
      expect(resolveWeatherTier(0)).toBe('clear');
      expect(resolveWeatherTier(24.9)).toBe('clear');
    });

    it('returns cloudy when 25% <= usage < 75%', () => {
      expect(resolveWeatherTier(25)).toBe('cloudy');
      expect(resolveWeatherTier(50)).toBe('cloudy');
      expect(resolveWeatherTier(74.9)).toBe('cloudy');
    });

    it('returns warning when 75% <= usage < 90%', () => {
      expect(resolveWeatherTier(75)).toBe('warning');
      expect(resolveWeatherTier(89.9)).toBe('warning');
    });

    it('returns critical when usage >= 90%', () => {
      expect(resolveWeatherTier(90)).toBe('critical');
      expect(resolveWeatherTier(99)).toBe('critical');
      expect(resolveWeatherTier(100)).toBe('critical');
    });
  });

  describe('calculateContextWatermarkMetrics', () => {
    it('handles empty message array gracefully', () => {
      const metrics = calculateContextWatermarkMetrics([]);
      expect(metrics.latestBudget).toBeNull();
      expect(metrics.historyTurnTokens).toEqual([]);
      expect(metrics.hasDelta).toBe(false);
      expect(metrics.deltaTokens).toBe(0);
      expect(metrics.usagePercent).toBe(0);
      expect(metrics.weatherTier).toBe('clear');
    });

    it('handles single assistant turn without delta', () => {
      const budget = createMockBudget(4000, 15);
      const messages: Message[] = [createMockMessage(budget)];

      const metrics = calculateContextWatermarkMetrics(messages);
      expect(metrics.latestBudget).toEqual(budget);
      expect(metrics.historyTurnTokens).toEqual([4000]);
      expect(metrics.hasDelta).toBe(false);
      expect(metrics.deltaTokens).toBe(0);
      expect(metrics.usagePercent).toBe(15);
      expect(metrics.weatherTier).toBe('clear');
      expect(metrics.weatherLabelKey).toBe('weatherClear');
    });

    it('calculates positive delta when context grows', () => {
      const budget1 = createMockBudget(4000, 20);
      const budget2 = createMockBudget(6500, 35);
      const messages: Message[] = [
        createMockMessage(budget1),
        createMockMessage(budget2),
      ];

      const metrics = calculateContextWatermarkMetrics(messages);
      expect(metrics.historyTurnTokens).toEqual([4000, 6500]);
      expect(metrics.hasDelta).toBe(true);
      expect(metrics.deltaTokens).toBe(2500);
      expect(metrics.usagePercent).toBe(35);
      expect(metrics.weatherTier).toBe('cloudy');
      expect(metrics.weatherLabelKey).toBe('weatherCloudy');
    });

    it('calculates negative delta after context compaction', () => {
      const budget1 = createMockBudget(100000, 80);
      const budget2 = createMockBudget(25000, 20);
      const messages: Message[] = [
        createMockMessage(budget1),
        createMockMessage(budget2),
      ];

      const metrics = calculateContextWatermarkMetrics(messages);
      expect(metrics.historyTurnTokens).toEqual([100000, 25000]);
      expect(metrics.hasDelta).toBe(true);
      expect(metrics.deltaTokens).toBe(-75000);
      expect(metrics.usagePercent).toBe(20);
      expect(metrics.weatherTier).toBe('clear');
    });

    it('slices recent turns up to maxTurns (default 12)', () => {
      const messages: Message[] = [];
      for (let i = 1; i <= 15; i++) {
        messages.push(createMockMessage(createMockBudget(i * 1000, i * 5)));
      }

      const metrics = calculateContextWatermarkMetrics(messages, 12);
      expect(metrics.historyTurnTokens.length).toBe(12);
      expect(metrics.historyTurnTokens[0]).toBe(4000);
      expect(metrics.historyTurnTokens[11]).toBe(15000);
      expect(metrics.deltaTokens).toBe(1000);
    });
  });
});
