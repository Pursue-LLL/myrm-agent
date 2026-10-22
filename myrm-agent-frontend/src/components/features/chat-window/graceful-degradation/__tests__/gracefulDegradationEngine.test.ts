import { describe, it, expect } from 'vitest';
import {
  computeOverallSystemHealth,
  formatLatency,
  generateFallbackPillText,
  getCircuitBreakerLabel,
} from '../gracefulDegradationEngine';
import {
  ComponentHealthRecord,
  DegradationEvent,
} from '../gracefulDegradationTypes';

describe('gracefulDegradationEngine', () => {
  describe('computeOverallSystemHealth', () => {
    it('returns default healthy status when component list is empty', () => {
      const summary = computeOverallSystemHealth([]);
      expect(summary.overallStatus).toBe('healthy');
      expect(summary.healthyCount).toBe(0);
      expect(summary.healthScore).toBe(100);
      expect(summary.averageLatencyMs).toBe(0);
    });

    it('computes healthy summary when all components are closed and low latency', () => {
      const mockComponents: ComponentHealthRecord[] = [
        {
          id: 'c1',
          name: '主模型',
          type: 'model',
          status: 'closed',
          latencyMs: 300,
          errorRatePercent: 0,
          lastCheckedAt: Date.now(),
          fallbackStrategy: '轮换',
        },
        {
          id: 'c2',
          name: '沙箱',
          type: 'sandbox',
          status: 'closed',
          latencyMs: 100,
          errorRatePercent: 0,
          lastCheckedAt: Date.now(),
          fallbackStrategy: '只读',
        },
      ];

      const summary = computeOverallSystemHealth(mockComponents);
      expect(summary.overallStatus).toBe('healthy');
      expect(summary.healthyCount).toBe(2);
      expect(summary.degradedCount).toBe(0);
      expect(summary.openBreakerCount).toBe(0);
      expect(summary.averageLatencyMs).toBe(200);
      expect(summary.healthScore).toBe(100);
    });

    it('computes degraded status when a component is half-open or has errors', () => {
      const mockComponents: ComponentHealthRecord[] = [
        {
          id: 'c1',
          name: '主模型',
          type: 'model',
          status: 'closed',
          latencyMs: 400,
          errorRatePercent: 0,
          lastCheckedAt: Date.now(),
          fallbackStrategy: '轮换',
        },
        {
          id: 'c2',
          name: '检索服务',
          type: 'search',
          status: 'half_open',
          latencyMs: 1600,
          errorRatePercent: 8,
          lastCheckedAt: Date.now(),
          fallbackStrategy: '切本地',
        },
      ];

      const summary = computeOverallSystemHealth(mockComponents);
      expect(summary.overallStatus).toBe('degraded');
      expect(summary.healthyCount).toBe(1);
      expect(summary.degradedCount).toBe(1);
      expect(summary.healthScore).toBeLessThan(100);
    });

    it('computes maintenance status when multiple circuit breakers are open', () => {
      const mockComponents: ComponentHealthRecord[] = [
        {
          id: 'c1',
          name: '主模型',
          type: 'model',
          status: 'open',
          latencyMs: 3000,
          errorRatePercent: 90,
          lastCheckedAt: Date.now(),
          fallbackStrategy: '无',
        },
        {
          id: 'c2',
          name: '检索服务',
          type: 'search',
          status: 'open',
          latencyMs: 4000,
          errorRatePercent: 100,
          lastCheckedAt: Date.now(),
          fallbackStrategy: '无',
        },
      ];

      const summary = computeOverallSystemHealth(mockComponents);
      expect(summary.overallStatus).toBe('maintenance');
      expect(summary.openBreakerCount).toBe(2);
      expect(summary.healthScore).toBeLessThan(50);
    });
  });

  describe('formatLatency', () => {
    it('categorizes low latency as good', () => {
      const res = formatLatency(250);
      expect(res.text).toBe('250ms');
      expect(res.level).toBe('good');
    });

    it('categorizes medium latency as moderate', () => {
      const res = formatLatency(850);
      expect(res.text).toBe('850ms');
      expect(res.level).toBe('moderate');
    });

    it('categorizes high latency as slow', () => {
      const res = formatLatency(2400);
      expect(res.text).toBe('2.4s');
      expect(res.level).toBe('slow');
    });
  });

  describe('generateFallbackPillText', () => {
    it('returns seamless fallback message when fallback is active', () => {
      const event: DegradationEvent = {
        id: 'e1',
        componentId: 'c1',
        componentName: '网络检索',
        severity: 'warning',
        title: '超时',
        explanation: '搜索超时',
        fallbackActive: true,
        fallbackActionLabel: '已切本地',
        timestamp: Date.now(),
      };

      const text = generateFallbackPillText(event);
      expect(text).toContain('网络检索暂时拥堵');
      expect(text).toContain('已无缝切换至降级策略');
    });

    it('returns jitter message when fallback is not active', () => {
      const event: DegradationEvent = {
        id: 'e2',
        componentId: 'c2',
        componentName: '代码沙箱',
        severity: 'info',
        title: '延迟波动',
        explanation: '稍微慢了一点',
        fallbackActive: false,
        fallbackActionLabel: '重试中',
        timestamp: Date.now(),
      };

      const text = generateFallbackPillText(event);
      expect(text).toBe('代码沙箱存在偶发抖动');
    });
  });

  describe('getCircuitBreakerLabel', () => {
    it('maps closed status to green label', () => {
      const res = getCircuitBreakerLabel('closed');
      expect(res.label).toContain('Closed');
      expect(res.badgeClass).toContain('emerald');
    });

    it('maps half_open status to amber label', () => {
      const res = getCircuitBreakerLabel('half_open');
      expect(res.label).toContain('Half-Open');
      expect(res.badgeClass).toContain('amber');
    });

    it('maps open status to destructive label', () => {
      const res = getCircuitBreakerLabel('open');
      expect(res.label).toContain('Open');
      expect(res.badgeClass).toContain('destructive');
    });
  });
});
