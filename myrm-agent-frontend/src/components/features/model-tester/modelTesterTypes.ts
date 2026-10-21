/**
 * Model Ping and Speed Testing Domain Types.
 *
 * [INPUT] None (Standard TypeScript)
 * [OUTPUT] Pure domain types for model latency, throughput, and connection health states.
 * [POS] src/components/features/model-tester/modelTesterTypes.ts
 */

export type ModelHealthStatus = 'healthy' | 'degraded' | 'unreachable';

export interface ModelPingRequestDTO {
  model_id: string;
  provider?: string;
  timeout_seconds?: number;
}

export interface ModelPingResponseDTO {
  model_id: string;
  provider: string;
  status: ModelHealthStatus;
  ttft_ms: number;
  tokens_per_second: number;
  auth_verified: boolean;
  checked_at_epoch: number;
  error_message: string | null;
}

export interface ModelSpeedTesterState {
  isTesting: boolean;
  result: ModelPingResponseDTO | null;
  error: string | null;
}
