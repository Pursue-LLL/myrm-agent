import { describe, it, expect } from 'vitest';
import type {
  ContextWatermarkLevel,
  CacheMissReason,
  AutoCompactState,
  ContextHudMetrics,
  CacheAttributionReport,
  ContextHudStoreState,
} from '../contextHudTypes';

describe('contextHudTypes', () => {
  it('validates context HUD and cache attribution domain types', () => {
    const level: ContextWatermarkLevel = 'healthy';
    expect(level).toBe('healthy');

    const reason: CacheMissReason = 'timestamp_jitter';
    expect(reason).toBe('timestamp_jitter');

    const compactState: AutoCompactState = 'ready';
    expect(compactState).toBe('ready');

    const metrics: ContextHudMetrics = {
      inputTokens: 12500,
      outputTokens: 1800,
      cachedReadTokens: 10000,
      cacheHitRate: 80,
      contextLimit: 128000,
      usedTokens: 14300,
      watermarkPercentage: 11,
      watermarkLevel: 'healthy',
      autoCompactState: 'ready',
    };
    expect(metrics.usedTokens).toBe(14300);
    expect(metrics.cacheHitRate).toBe(80);

    const report: CacheAttributionReport = {
      reason: 'system_prompt_drift',
      reasonTitle: '系统提示词发生动态漂移',
      description: '前缀发生变动',
      suggestion: '固化静态前缀',
      estimatedTokenSavings: 8000,
      score: 45,
    };
    expect(report.score).toBe(45);
    expect(report.estimatedTokenSavings).toBe(8000);

    const storeState: ContextHudStoreState = {
      metricsByChatId: {
        'chat-1': metrics,
      },
      attributionReports: {
        'chat-1': report,
      },
      activeChatId: 'chat-1',
      isPopoverOpen: false,
    };
    expect(storeState.activeChatId).toBe('chat-1');
    expect(storeState.metricsByChatId['chat-1'].cacheHitRate).toBe(80);
  });
});
