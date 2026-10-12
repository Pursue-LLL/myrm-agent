/**
 * [INPUT]
 * @/services/api::apiClient (POS: standard client facade)
 *
 * [OUTPUT]
 * Types and client functions for Item 108:
 * ZeroRefactorHostLifecyclePluginAndExperienceObservabilitySuite.
 *
 * [POS]
 * Client layer connecting frontend command-center UI to FastAPI backend endpoints.
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import { apiClient } from '@/services/api';

export type HostAccessChannel = 'plugin' | 'mcp' | 'skill';
export type ExperienceEffectStatus = 'effective' | 'neutral' | 'adverse';

export interface ExperienceObservabilityMetricDTO {
  entry_id: string;
  name: string;
  source_session_id: string;
  access_channel: HostAccessChannel;
  recall_count: number;
  injection_count: number;
  success_count: number;
  dispute_count: number;
  success_rate: number;
  effect_status: ExperienceEffectStatus;
  last_observed_at: string | null;
}

export interface SessionTraceEvidenceDTO {
  session_id: string;
  title: string;
  trajectory_summary: string;
  key_evidence_snippets: string[];
  agent_role: string;
  timestamp: string;
}

export interface HostPluginConfigDTO {
  enabled: boolean;
  active_channel: HostAccessChannel;
  auto_warmup: boolean;
  auto_capture: boolean;
  auto_commit: boolean;
  monitored_host: string;
}

export interface UpdatePluginConfigRequest {
  enabled?: boolean;
  active_channel?: HostAccessChannel;
  auto_warmup?: boolean;
  auto_capture?: boolean;
  auto_commit?: boolean;
  monitored_host?: string;
}

export interface ObservabilityDashboardResponseDTO {
  status: string;
  total_experiences_tracked: number;
  overall_success_rate: number;
  total_recalls: number;
  total_injections: number;
  plugin_config: HostPluginConfigDTO;
  metrics: ExperienceObservabilityMetricDTO[];
}

export async function fetchObservabilityDashboard(): Promise<ObservabilityDashboardResponseDTO> {
  return apiClient.get<ObservabilityDashboardResponseDTO>(
    '/memory/experience-observability/dashboard',
  );
}

export async function fetchObservabilityMetrics(
  channel?: string,
  status?: string,
): Promise<ExperienceObservabilityMetricDTO[]> {
  const params = new URLSearchParams();
  if (channel) params.set('channel', channel);
  if (status) params.set('status', status);
  const qStr = params.toString() ? `?${params.toString()}` : '';
  return apiClient.get<ExperienceObservabilityMetricDTO[]>(
    `/memory/experience-observability/metrics${qStr}`,
  );
}

export async function fetchTraceEvidence(
  sessionId: string,
): Promise<SessionTraceEvidenceDTO> {
  return apiClient.get<SessionTraceEvidenceDTO>(
    `/memory/experience-observability/traces/${encodeURIComponent(sessionId)}`,
  );
}

export async function recordRecallHit(
  entryId: string,
  channel: HostAccessChannel = 'plugin',
): Promise<ExperienceObservabilityMetricDTO> {
  return apiClient.post<ExperienceObservabilityMetricDTO>(
    '/memory/experience-observability/record-recall',
    { entry_id: entryId, channel },
  );
}

export async function recordEffectOutcome(
  entryId: string,
  isSuccess: boolean,
  isDispute: boolean = false,
): Promise<ExperienceObservabilityMetricDTO> {
  return apiClient.post<ExperienceObservabilityMetricDTO>(
    '/memory/experience-observability/record-effect',
    { entry_id: entryId, is_success: isSuccess, is_dispute: isDispute },
  );
}

export async function fetchPluginConfig(): Promise<HostPluginConfigDTO> {
  return apiClient.get<HostPluginConfigDTO>(
    '/memory/experience-observability/config',
  );
}

export async function updatePluginConfig(
  payload: UpdatePluginConfigRequest,
): Promise<HostPluginConfigDTO> {
  return apiClient.post<HostPluginConfigDTO>(
    '/memory/experience-observability/config',
    payload,
  );
}
