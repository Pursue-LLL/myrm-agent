/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Memory Guardian DTOs and request helpers: health score, guardian status and policy, manual maintenance
 * trigger, morning digest, and the combined overview.
 *
 * [POS]
 * Frontend Memory Guardian API client. Owns the typed HTTP contracts of the maintenance scheduler, kept apart
 * from the memory CRUD client.
 */

import { apiRequest } from '@/lib/api';

export interface MemoryHealthScore {
  total: number;
  dimensions: Record<string, number>;
  suggestions: string[];
  has_graph: boolean;
}

export type MemoryGuardianFrequencyTier = 'conservative' | 'balanced' | 'aggressive';
export type MemoryGuardianTriggerMode = 'safe' | 'force';

export interface MemoryGuardianPolicy {
  frequency_tier: MemoryGuardianFrequencyTier;
  quiet_window_enabled: boolean;
  quiet_window_start_hour: number;
  quiet_window_end_hour: number;
  timezone_offset_minutes: number;
  timezone_initialized?: boolean;
  timezone_source?: 'unknown' | 'client_header' | 'server_fallback' | 'manual';
}

export interface MemoryGuardianStatus {
  running: boolean;
  last_run: number | null;
  next_run: number | null;
  healthy_interval_hours: number;
  unhealthy_interval_hours: number;
  health_threshold: number;
  seconds_until_next: number | null;
  frequency_tier: MemoryGuardianFrequencyTier;
  quiet_window_enabled: boolean;
  quiet_window_start_hour: number;
  quiet_window_end_hour: number;
  timezone_offset_minutes: number;
  local_hour: number;
  within_quiet_window: boolean;
  seconds_until_quiet_window: number;
}

export interface MemoryHealthResponse {
  health: MemoryHealthScore;
  guardian: MemoryGuardianStatus;
  policy: MemoryGuardianPolicy;
  alerts?: {
    guard_unavailable?: {
      active: boolean;
      escalated: boolean;
      window_hours: number;
      total: number;
      reasons: Record<string, number>;
      dominant_reason: string | null;
      dominant_reason_count: number;
      dominant_reason_ratio: number;
      thresholds?: {
        min_total_events: number;
        escalation_min_reason_count: number;
        escalation_min_reason_ratio: number;
      } | null;
      last_occurred_at: string | null;
    };
  };
}

export interface MemoryMaintenanceTriggerResponse {
  triggered: boolean;
  mode: MemoryGuardianTriggerMode;
  applied: boolean;
  skipped_reason?: string;
  health?: MemoryHealthScore;
  error?: string;
}

export const triggerMemoryMaintenance = async (
  mode: MemoryGuardianTriggerMode = 'safe',
): Promise<MemoryMaintenanceTriggerResponse> => {
  return apiRequest<MemoryMaintenanceTriggerResponse>('/memory/guardian/trigger', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });
};

export const updateMemoryGuardianPolicy = async (policy: MemoryGuardianPolicy): Promise<MemoryGuardianPolicy> => {
  return apiRequest<MemoryGuardianPolicy>('/memory/guardian/policy', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(policy),
  });
};

export interface MemoryGuardianMorningDigest {
  available: boolean;
  occurred_at?: string;
  summary?: string;
  counts?: {
    forgotten: number;
    archived: number;
    merged: number;
    corrected: number;
    stale_removed: number;
    stale_extended: number;
  };
  forced?: boolean;
  forced_runs?: number;
  scheduled_runs?: number;
  event_count?: number;
  duration_ms?: number;
  health_total?: number;
  health_delta?: number | null;
  health_status?: string | null;
  next_run_seconds?: number | null;
  window_started_at?: string;
  window_ended_at?: string;
  window_mode?: 'quiet_window' | 'rolling_24h';
}

export interface MemoryGuardianOverviewResponse extends MemoryHealthResponse {
  digest: MemoryGuardianMorningDigest;
}

export const getMemoryGuardianOverview = async (): Promise<MemoryGuardianOverviewResponse> => {
  const timezoneOffsetMinutes = typeof window !== 'undefined' ? -new Date().getTimezoneOffset() : 0;
  return apiRequest<MemoryGuardianOverviewResponse>('/memory/guardian/overview', {
    silent: true,
    headers: { 'x-client-timezone-offset-minutes': String(timezoneOffsetMinutes) },
  });
};
