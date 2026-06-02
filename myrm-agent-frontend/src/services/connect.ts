/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: HTTP client wrapper)
 *
 * [OUTPUT]
 * Connect Wizard API client functions.
 *
 * [POS]
 * Frontend service for managing external agent connections (Connect Wizard).
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

export interface ConnectorStatusItem {
  profile_id: string;
  label: string;
  status: 'ready' | 'manual_config_required' | 'missing';
  doctor_ok: boolean;
  connected_at: string | null;
}

export async function fetchConnectProfiles(): Promise<ConnectProfile[]> {
  return apiRequest<ConnectProfile[]>('/connect/profiles');
}

export async function generateConnectConfig(profileId: string): Promise<GenerateConfigResponse> {
  return apiRequest<GenerateConfigResponse>('/connect/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export async function runConnectDoctor(profileId: string): Promise<DoctorResponse> {
  return apiRequest<DoctorResponse>('/connect/doctor', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export async function revokeConnect(profileId: string, clearSyncedMemory = false): Promise<RevokeResponse> {
  return apiRequest<RevokeResponse>('/connect/revoke', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId, clear_synced_memory: clearSyncedMemory }),
  });
}

export async function fetchConnectorStatus(): Promise<ConnectorStatusItem[]> {
  return apiRequest<ConnectorStatusItem[]>('/connect/status');
}
