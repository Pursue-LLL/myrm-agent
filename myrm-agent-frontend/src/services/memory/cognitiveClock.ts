/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * - CognitiveClockStatus: Status representation of the nested multi-frequency clock.
 * - getCognitiveClockStatus: Read four-tier cognitive clock telemetry and states.
 * - reportUserActivity: Signal foreground typing/interaction to trigger background backoff.
 * - triggerT1SessionDebounce: Manually trigger T1 meso-session reflection.
 *
 * [POS]
 * Frontend Cognitive Clock API service layer. Decoupled from monolith memory services.
 */

import { apiRequest } from '@/lib/api';

export interface CognitiveClockStatus {
  running: boolean;
  last_run: number | null;
  next_run: number | null;
  healthy_interval_hours: number;
  unhealthy_interval_hours: number;
  health_threshold: number;
  seconds_until_next: number | null;
  consecutive_unhealthy: number;
  last_pattern_discovery: number;
  frequency_tier: string;
  quiet_window_enabled: boolean;
  quiet_window_start_hour: number;
  quiet_window_end_hour: number;
  timezone_offset_minutes: number;
  local_hour: number;
  within_quiet_window: boolean;
  seconds_until_quiet_window: number;
  wakeup_grace_period_active: boolean;
  user_activity_detected: boolean;
  seconds_since_last_user_activity: number;
  last_skip_reason?: string | null;
  consecutive_skips?: number;
}

export const getCognitiveClockStatus = async (): Promise<CognitiveClockStatus> => {
  return apiRequest<CognitiveClockStatus>('/memory/guardian/cognitive-clock/status');
};

export const reportUserActivity = async (
  sessionId?: string,
  reason: string = 'typing'
): Promise<{ status: string; recorded: boolean; reason: string }> => {
  return apiRequest<{ status: string; recorded: boolean; reason: string }>(
    '/memory/guardian/cognitive-clock/activity',
    {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, reason }),
    }
  );
};

export const triggerT1SessionDebounce = async (
  sessionId: string
): Promise<{ status: string; session_id: string }> => {
  return apiRequest<{ status: string; session_id: string }>(
    '/memory/guardian/cognitive-clock/trigger-t1',
    {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    }
  );
};
