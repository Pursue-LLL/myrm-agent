/**
 * Proactive past-pitfall alert and decision assist API client service.
 * Enables deterministic shadow intent evaluation, historical postmortem retrieval,
 * and session-scoped topic muting for proactive memory guardrails.
 */

import { apiClient } from '@/services/api';

export type DecisionIntentLevel = 'inquiry' | 'commitment';
export type AlertSeverity = 'critical' | 'warning' | 'info';
export type DispatchChannel = 'frontend_callout' | 'shadow_thought_only' | 'silent';

export interface EvaluateInputRequest {
  user_input: string;
  session_id?: string;
  current_runtime_version?: string;
}

export interface MuteSubjectRequest {
  session_id: string;
  subject: string;
}

export interface UnmuteSubjectRequest {
  session_id: string;
  subject: string;
}

export interface SeedTriadRequest {
  subject: string;
  approach: string;
  pitfall_lesson: string;
  validated_alternative: string;
  severity?: AlertSeverity;
  incident_date?: string;
  version_context?: string;
}

export interface PitfallAlertCardDTO {
  alert_id: string;
  subject: string;
  intent_summary: string;
  historical_pitfall: string;
  recommended_action: string;
  severity: AlertSeverity | string;
  source_ref: string;
  drift_warning: string;
  dispatch_channel: DispatchChannel | string;
  is_muted: boolean;
}

export interface PitfallEvaluationResponse {
  evaluation_id: string;
  intent_detected: boolean;
  intent_level: string;
  triad_matched: boolean;
  alert_generated: boolean;
  dispatched_channel: string;
  latency_ms: number;
  alert_card: PitfallAlertCardDTO | null;
}

export interface PitfallAlertStatusResponse {
  active: boolean;
  seeded_triads_count: number;
  muted_sessions_count: number;
}

export const decisionAssistService = {
  /**
   * Evaluate input query for decision commitment and retrieve matching failure postmortems.
   */
  async evaluate(request: EvaluateInputRequest): Promise<PitfallEvaluationResponse> {
    return apiClient.post<PitfallEvaluationResponse>(
      '/memory/pitfall-alert/evaluate',
      {
        user_input: request.user_input,
        session_id: request.session_id ?? 'default',
        current_runtime_version: request.current_runtime_version ?? '',
      }
    );
  },

  /**
   * Seed a new causal triad failure postmortem into the engine ledger.
   */
  async seedTriad(request: SeedTriadRequest): Promise<{ status: string; subject: string }> {
    return apiClient.post<{ status: string; subject: string }>(
      '/memory/pitfall-alert/seed',
      request
    );
  },

  /**
   * Mute alerts for a specific technical topic in the session.
   */
  async muteSubject(
    request: MuteSubjectRequest
  ): Promise<{ status: string; session_id: string; subject: string }> {
    return apiClient.post<{ status: string; session_id: string; subject: string }>(
      '/memory/pitfall-alert/mute',
      request
    );
  },

  /**
   * Unmute alerts for a specific technical topic in the session.
   */
  async unmuteSubject(
    request: UnmuteSubjectRequest
  ): Promise<{ status: string; session_id: string; subject: string }> {
    return apiClient.post<{ status: string; session_id: string; subject: string }>(
      '/memory/pitfall-alert/unmute',
      request
    );
  },

  /**
   * Retrieve pitfall alert engine operational status and counters.
   */
  async getStatus(): Promise<PitfallAlertStatusResponse> {
    return apiClient.get<PitfallAlertStatusResponse>(
      '/memory/pitfall-alert/status'
    );
  },
};
