import { describe, it, expect } from 'vitest';
import {
  formatTokenMetric,
  formatPercentage,
  computeContextHudMetrics,
  diagnoseCacheMiss,
  resolveWatermarkColor,
  DEFAULT_CONTEXT_LIMIT,
} from '../contextHudEngine';

describe('contextHudEngine', () => {
  describe('formatTokenMetric', () => {
    it('formats zero and negative numbers', () => {
      expect(formatTokenMetric(0)).toBe('0');
      expect(formatTokenMetric(-10)).toBe('0');
    });

    it('formats small integers', () => {
      expect(formatTokenMetric(850)).toBe('850');
    });

    it('formats thousands into k notation', () => {
      expect(formatTokenMetric(1000)).toBe('1.0k');
      expect(formatTokenMetric(12450)).toBe('12.5k');
      expect(formatTokenMetric(128000)).toBe('128.0k');
    });

    it('formats millions into M notation', () => {
      expect(formatTokenMetric(1000000)).toBe('1.00M');
      expect(formatTokenMetric(2500000)).toBe('2.50M');
    });
  });

  describe('formatPercentage', () => {
    it('formats and clamps percentages', () => {
      expect(formatPercentage(0)).toBe('0%');
      expect(formatPercentage(42.4)).toBe('42%');
      expect(formatPercentage(85.7)).toBe('86%');
      expect(formatPercentage(150)).toBe('100%');
      expect(formatPercentage(-10)).toBe('0%');
    });
  });

  describe('computeContextHudMetrics', () => {
    it('computes metrics with default limit', () => {
      const res = computeContextHudMetrics({
        inputTokens: 10000,
        outputTokens: 2000,
        cachedReadTokens: 8000,
      });

      expect(res.usedTokens).toBe(12000);
      expect(res.cacheHitRate).toBe(80);
      expect(res.contextLimit).toBe(DEFAULT_CONTEXT_LIMIT);
      expect(res.watermarkLevel).toBe('healthy');
      expect(res.watermarkPercentage).toBe(9);
    });

    it('handles zero input gracefully without division by zero', () => {
      const res = computeContextHudMetrics({
        inputTokens: 0,
        outputTokens: 0,
        cachedReadTokens: 0,
      });

      expect(res.cacheHitRate).toBe(0);
      expect(res.watermarkPercentage).toBe(0);
      expect(res.watermarkLevel).toBe('healthy');
    });

    it('transitions watermark level based on thresholds', () => {
      // 65% usage -> warning
      const warningRes = computeContextHudMetrics({
        inputTokens: 65000,
        outputTokens: 0,
        cachedReadTokens: 0,
        contextLimit: 100000,
      });
      expect(warningRes.watermarkLevel).toBe('warning');

      // 90% usage -> critical
      const criticalRes = computeContextHudMetrics({
        inputTokens: 90000,
        outputTokens: 0,
        cachedReadTokens: 0,
        contextLimit: 100000,
      });
      expect(criticalRes.watermarkLevel).toBe('critical');
    });
  });

  describe('diagnoseCacheMiss', () => {
    it('detects first turn cold cache start', () => {
      const res = diagnoseCacheMiss({
        inputTokens: 2000,
        cachedReadTokens: 0,
        turnIndex: 1,
      });
      expect(res.reason).toBe('first_turn_cold');
      expect(res.score).toBe(95);
    });

    it('detects timestamp jitter when hasDynamicTime is true', () => {
      const res = diagnoseCacheMiss({
        inputTokens: 5000,
        cachedReadTokens: 0,
        turnIndex: 3,
        hasDynamicTime: true,
      });
      expect(res.reason).toBe('timestamp_jitter');
      expect(res.score).toBe(40);
      expect(res.estimatedTokenSavings).toBeGreaterThan(0);
    });

    it('detects system prompt drift', () => {
      const res = diagnoseCacheMiss({
        inputTokens: 6000,
        cachedReadTokens: 500,
        turnIndex: 3,
        hasSystemPromptChanged: true,
      });
      expect(res.reason).toBe('system_prompt_drift');
      expect(res.score).toBe(45);
    });

    it('detects tool schema mutation', () => {
      const res = diagnoseCacheMiss({
        inputTokens: 4000,
        cachedReadTokens: 200,
        turnIndex: 3,
        hasToolMutation: true,
      });
      expect(res.reason).toBe('tool_schema_mutation');
      expect(res.score).toBe(50);
    });

    it('detects minimum boundary misalignment (<1024 tokens)', () => {
      const res = diagnoseCacheMiss({
        inputTokens: 512,
        cachedReadTokens: 0,
        turnIndex: 3,
      });
      expect(res.reason).toBe('boundary_misalignment');
      expect(res.score).toBe(85);
    });

    it('reports excellent health when hit ratio >= 50%', () => {
      const res = diagnoseCacheMiss({
        inputTokens: 10000,
        cachedReadTokens: 8500,
        turnIndex: 4,
      });
      expect(res.reason).toBe('none');
      expect(res.score).toBe(100);
      expect(res.estimatedTokenSavings).toBe(8500);
    });
  });

  describe('resolveWatermarkColor', () => {
    it('provides distinct class styles for each watermark level', () => {
      const healthy = resolveWatermarkColor('healthy');
      expect(healthy.textClass).toContain('emerald');

      const warning = resolveWatermarkColor('warning');
      expect(warning.textClass).toContain('amber');

      const critical = resolveWatermarkColor('critical');
      expect(critical.textClass).toContain('rose');
    });
  });
});
