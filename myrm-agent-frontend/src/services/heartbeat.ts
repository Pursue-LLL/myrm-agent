import { apiRequest } from '@/lib/api';

export type ScheduleKind = 'interval' | 'cron';

export interface HeartbeatStatus {
  enabled: boolean;
  interval_ms: number | null;
  schedule_kind: ScheduleKind | null;
  cron_expr: string | null;
  timezone: string | null;
  schedule_description: string | null;
  prompt: string | null;
  model: string | null;
  agent_id: string | null;
  last_run_at: string | null;
  last_status: string | null;
  next_run_at: string | null;
  fire_count: number;
}

export interface HeartbeatEnableRequest {
  interval_ms?: number;
  schedule_kind?: ScheduleKind;
  cron_expr?: string;
  timezone?: string;
  prompt?: string;
  model?: string;
  agent_id?: string;
}

export async function getHeartbeatStatus(): Promise<HeartbeatStatus> {
  return apiRequest('/cron/heartbeat/status');
}

export async function enableHeartbeat(params?: HeartbeatEnableRequest): Promise<HeartbeatStatus> {
  return apiRequest('/cron/heartbeat/enable', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params ?? {}),
  });
}

export async function disableHeartbeat(): Promise<HeartbeatStatus> {
  return apiRequest('/cron/heartbeat/disable', { method: 'POST' });
}
