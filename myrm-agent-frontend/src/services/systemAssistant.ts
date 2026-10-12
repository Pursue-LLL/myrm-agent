/**
 * [INPUT]
 * @/services/api::apiClient (POS: centralized frontend API client adapter)
 *
 * [OUTPUT]
 * - SystemAssistantCommandRequest: Payload for natural language system assistant commands
 * - SystemAssistantActionPayload: Structured execution results and card details
 * - SystemAssistantCommandResponse: Response containing command ID, classified intent, action, and followups
 * - SystemAssistantStatusResponse: System telemetry overview (agents count, tasks count, health score)
 * - executeSystemAssistantCommand: Async function to send command to assistant
 * - getSystemAssistantStatus: Async function to fetch system assistant telemetry status
 *
 * [POS]
 * Client service layer for XiaoMo Unified Natural Language Control Center.
 * Single file < 100 lines. Zero `any` types.
 */

import { apiClient } from './api';

export interface SystemAssistantCommandRequest {
  user_prompt: string;
  context_hint?: Record<string, string>;
}

export interface SystemAssistantActionPayload {
  action_type:
    | 'project_created'
    | 'tasks_queried'
    | 'tasks_terminated'
    | 'health_diagnosed'
    | 'query_answered';
  status: 'success' | 'pending' | 'failed';
  details: Record<string, string>;
}

export interface SystemAssistantCommandResponse {
  command_id: string;
  intent: string;
  summary: string;
  action: SystemAssistantActionPayload;
  suggested_followups: string[];
  created_at: string;
}

export interface SystemAssistantStatusResponse {
  active_agents_count: number;
  running_tasks_count: number;
  total_projects_count: number;
  system_health: string;
  voice_enabled: boolean;
  last_heartbeat: string;
}

const SYSTEM_ASSISTANT_BASE = '/api/v1/system-assistant';

export async function executeSystemAssistantCommand(
  payload: SystemAssistantCommandRequest,
): Promise<SystemAssistantCommandResponse> {
  return apiClient.post<SystemAssistantCommandResponse>(
    `${SYSTEM_ASSISTANT_BASE}/command`,
    payload,
  );
}

export async function getSystemAssistantStatus(): Promise<SystemAssistantStatusResponse> {
  return apiClient.get<SystemAssistantStatusResponse>(
    `${SYSTEM_ASSISTANT_BASE}/status`,
  );
}
