/**
 * [INPUT]: Rate limit partitioned metrics, provider failure attribution, and event payloads.
 * [OUTPUT]: Strong TypeScript interfaces for RateLimitSourceSplitHUD component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/rateLimitSplitTypes.ts
 */

export type RateLimitSourceType = 'myrm' | 'upstream';

export interface RateLimitEventItem {
  source: RateLimitSourceType;
  provider: string;
  model: string;
  timestamp_ms: number;
  reason: string;
}

export interface FailureEventItem {
  provider: string;
  model: string;
  error_code: string;
  timestamp_ms: number;
  reason: string;
}

export interface RateLimitSplitMetricsData {
  total_requests: number;
  total_completed: number;
  total_rate_limited: number;
  rate_limited_by_source: Record<string, number>;
  total_failed: number;
  failed_by_provider: Record<string, number>;
  totals_consistent: boolean;
  recent_rate_limit_events: RateLimitEventItem[];
  recent_failure_events: FailureEventItem[];
}

export interface RateLimitSourceSplitHUDProps {
  data: RateLimitSplitMetricsData;
  onRefresh?: () => void;
  onReset?: () => Promise<void> | void;
  isRefreshing?: boolean;
}
