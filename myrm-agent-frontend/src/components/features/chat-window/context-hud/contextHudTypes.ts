/**
 * [INPUT]
 * - None (Pure domain type definitions for Context Watermark and Cache Attribution HUD)
 *
 * [OUTPUT]
 * - ContextWatermarkLevel, CacheMissReason, ContextHudMetrics,
 *   CacheAttributionReport, ContextHudStoreState
 *
 * [POS]
 * Unified types for Item 195 (P1): ContextWatermarkAndCacheAttributionHudSuite.
 * Powers the 6-metrics health HUD and prompt cache attribution diagnostics
 * (Input tokens, Output tokens, Cached read tokens, Cache hit rate, Watermark %, Auto-compact).
 */

export type ContextWatermarkLevel = 'healthy' | 'warning' | 'critical';

export type CacheMissReason =
  | 'system_prompt_drift'
  | 'timestamp_jitter'
  | 'tool_schema_mutation'
  | 'boundary_misalignment'
  | 'first_turn_cold'
  | 'none';

export type AutoCompactState = 'disabled' | 'ready' | 'active';

export interface ContextHudMetrics {
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly cachedReadTokens: number;
  readonly cacheHitRate: number;
  readonly contextLimit: number;
  readonly usedTokens: number;
  readonly watermarkPercentage: number;
  readonly watermarkLevel: ContextWatermarkLevel;
  readonly autoCompactState: AutoCompactState;
}

export interface CacheAttributionReport {
  readonly reason: CacheMissReason;
  readonly reasonTitle: string;
  readonly description: string;
  readonly suggestion: string;
  readonly estimatedTokenSavings: number;
  readonly score: number;
}

export interface ContextHudStoreState {
  readonly metricsByChatId: Readonly<Record<string, ContextHudMetrics>>;
  readonly attributionReports: Readonly<Record<string, CacheAttributionReport>>;
  readonly activeChatId: string | null;
  readonly isPopoverOpen: boolean;
}
