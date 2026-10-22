/**
 * [INPUT]: Stream call sessions, termination outcome verdicts, and aggregate metrics.
 * [OUTPUT]: Strong TypeScript definitions for streamed calls final outcome metrics cockpit.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/streamMetricsTypes.ts
 */

export type StreamCallOutcome = 'SUCCESS' | 'ERROR' | 'CANCELLED' | 'TIMEOUT';

export interface StreamCallSession {
  call_id: string;
  model_name: string;
  provider: string;
  start_time_ms: number;
  ttft_ms: number | null;
  end_time_ms: number | null;
  total_duration_ms: number | null;
  chunk_count: number;
  total_tokens: number;
  outcome: StreamCallOutcome | null;
  error_message: string | null;
  is_finalized: boolean;
}

export interface StreamMetricsAggregate {
  total_calls: number;
  success_calls: number;
  error_calls: number;
  cancelled_calls: number;
  timeout_calls: number;
  total_chunks: number;
  total_tokens: number;
  avg_ttft_ms: number;
  avg_duration_ms: number;
  success_rate_pct: number;
  chunk_inflation_ratio: number;
}

export interface StreamMetricsCockpitProps {
  aggregate: StreamMetricsAggregate;
  recentSessions?: StreamCallSession[];
  onRefresh?: () => void;
  selectedModel?: string;
  onSelectModel?: (model: string | undefined) => void;
}
