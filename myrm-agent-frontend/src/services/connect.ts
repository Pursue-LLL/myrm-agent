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

export interface ConnectProfile {
  id: string;
  label: string;
  description: string;
  config_file_path: string;
  status: 'ready' | 'manual_config_required' | 'missing';
}

export interface GenerateConfigResponse {
  profile_id: string;
  mcp_url: string;
  token: string;
  config_json: Record<string, unknown>;
  instructions: string;
}

export interface DoctorResponse {
  profile_id: string;
  healthy: boolean;
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
  doctor_ok: boolean;
  connected_at: string | null;
}

export async function listConnectProfiles(): Promise<ConnectProfile[]> {
  return apiRequest<ConnectProfile[]>('/connect/profiles');
}

export async function generateConnectConfig(profileId: string): Promise<GenerateConfigResponse> {
  return apiRequest<GenerateConfigResponse>('/connect/generate', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export async function runConnectDoctor(profileId: string): Promise<DoctorResponse> {
  return apiRequest<DoctorResponse>('/connect/doctor', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export async function revokeConnect(
  profileId: string,
  clearSyncedMemory: boolean = false,
): Promise<RevokeResponse> {
  return apiRequest<RevokeResponse>('/connect/revoke', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, clear_synced_memory: clearSyncedMemory }),
  });
}

export async function listConnectorStatus(): Promise<ConnectorStatus[]> {
  return apiRequest<ConnectorStatus[]>('/connect/status');
}
