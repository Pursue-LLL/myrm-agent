/**
 * [INPUT]
 * @/store/config/providerTypes::SingleModelSelection (POS: Provider/model selection type contract)
 *
 * [OUTPUT]
 * Chat message, stream event, artifact, memory citation and store state TypeScript contracts.
 *
 * [POS]
 * Chat state and SSE event type definitions. Split from monolithic types.ts for maintainability.
 */

import type { CostStatus } from './contextMetrics';

// Token 使用量统计
export type TokenUsage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cached_tokens?: number;
  cache_write_tokens?: number;
  reasoning_tokens?: number;
  citation_tokens?: number;
};

// Token 经济学快照
export type TokenEconomicsSnapshot = {
  usage: TokenUsage;
  call_count: number;
  total_cost_usd: number;
  total_cache_savings_usd?: number;
  cost_status: CostStatus;
  error_count: number;
  latency: {
    avg_ms: number;
    p95_ms: number;
    min_ms: number;
    max_ms: number;
    avg_ttft_ms: number;
    p95_ttft_ms: number;
    avg_tokens_per_second: number;
  };
  model_breakdown?: Record<string, TokenUsage & { cost_usd: number }>;
  tool_breakdown?: Record<string, TokenUsage & { cost_usd: number }>;
};
