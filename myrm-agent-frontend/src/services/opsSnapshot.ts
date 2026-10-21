/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: unified API client)
 *
 * [OUTPUT]
 * - OpsAggregatedSnapshot: DTO for GET /api/v1/ops/snapshot
 * - getOpsSnapshot: fetch runtime operational snapshot
 *
 * [POS]
 * Client for server ops aggregated snapshot (liveness, resources, memory, doctor summary).
 */

import { apiRequest } from '@/lib/api';

export type OpsLivenessState = 'idle' | 'busy' | 'degraded' | 'draining';

export interface OpsAggregatedSnapshot {
  system: {
    app_name: string;
    app_version: string;
    deploy_mode: string;
    uptime_seconds: number;
    timestamp_utc: string;
  };
  liveness: {
    state: OpsLivenessState;
    active_sessions_count: number;
    available_slots: number;
    max_concurrent: number;
  };
  resources: {
    memory_level: string;
    memory_percent: number;
    process_rss_mb: number | null;
  };
  memory: {
    health_status: 'healthy' | 'degraded' | 'critical' | 'unknown';
    queue_backlog: number;
  };
  doctor_summary: {
    status: 'pass' | 'warn' | 'fail';
    harness_failed: number;
    server_failed: number;
  } | null;
}

export async function getOpsSnapshot(includeDoctor = false): Promise<OpsAggregatedSnapshot> {
  const q = includeDoctor ? 'true' : 'false';
  return apiRequest<OpsAggregatedSnapshot>(`/ops/snapshot?include_doctor=${q}`, { silent: true });
}
