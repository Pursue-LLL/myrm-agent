/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Connect Wizard API DTOs and request helpers for external agent connection management.
 *
 * [POS]
 * Frontend Connect Wizard API client. Typed HTTP contracts for listing profiles,
 * generating MCP configs, health checks, and revoking external agent connections.
 */

import { apiRequest } from '@/lib/api';
import type { DoctorSeverity } from '@/lib/i18n/connectDoctor';

/** Connector state id used for the Agent Plugins bundle (server-side constant). */
export const AGENT_PLUGIN_PROFILE_ID = 'agent_plugin';

export interface ConnectProfile {
  id: string;
  label: string;
  description: string;
  config_file_path: string;
  status: 'ready' | 'manual_config_required' | 'missing';
}

export interface GenerateConfigResponse {
  profile_id: string;
  agent_id: string;
  mcp_url: string;
  token: string;
  config_json: Record<string, unknown>;
  instructions: string;
}

export interface DoctorResponse {
  profile_id: string;
  healthy: boolean;
  /** Machine-readable outcome code; map to a localized message in the UI. */
  detail: string;
  /** Server-owned presentation severity ('ok' | 'warn' | 'error'). */
  severity: DoctorSeverity;
}

export interface RevokeResponse {
  profile_id: string;
  revoked: boolean;
  trees_removed: number;
}

export interface ConnectorStatus {
  profile_id: string;
  label: string;
  status: 'ready' | 'manual_config_required' | 'missing';
  agent_id: string;
  doctor_ok: boolean;
  last_doctor_detail: string;
  connected_at: string | null;
  last_doctor_at: string | null;
}

export interface AgentPluginBundleResponse {
  agent_id: string;
  mcp_url: string;
  token: string;
  embed_token: boolean;
  files: Record<string, string>;
  instructions: string;
}

export async function listConnectProfiles(): Promise<ConnectProfile[]> {
  return apiRequest<ConnectProfile[]>('/connect/profiles');
}

export async function generateConnectConfig(
  profileId: string,
  agentId: string = 'default',
): Promise<GenerateConfigResponse> {
  return apiRequest<GenerateConfigResponse>('/connect/generate', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, agent_id: agentId }),
  });
}

export async function runConnectDoctor(profileId: string): Promise<DoctorResponse> {
  return apiRequest<DoctorResponse>('/connect/doctor', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export async function revokeConnect(profileId: string, clearSyncedMemory: boolean = false): Promise<RevokeResponse> {
  return apiRequest<RevokeResponse>('/connect/revoke', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, clear_synced_memory: clearSyncedMemory }),
  });
}

export async function listConnectorStatus(): Promise<ConnectorStatus[]> {
  return apiRequest<ConnectorStatus[]>('/connect/status');
}

export async function generateAgentPluginBundle(
  agentId: string,
  embedToken: boolean = false,
): Promise<AgentPluginBundleResponse> {
  return apiRequest<AgentPluginBundleResponse>('/connect/agent-plugin', {
    method: 'POST',
    body: JSON.stringify({ agent_id: agentId, embed_token: embedToken }),
  });
}
