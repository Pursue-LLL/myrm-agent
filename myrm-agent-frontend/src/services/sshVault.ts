/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: Standard API request wrapper)
 *
 * [OUTPUT]
 * - SSHHostConfig, SSHAssetSummary, SSHProbeResult, BreakGlassRequest, BreakGlassResponse, HostPolicyUpdate
 * - getSSHVaultSummary, probeSSHHost, updateHostPolicy, requestBreakGlassToken
 *
 * [POS]
 * SSH Vault API client for host discovery, health probing, read-only gating, and break-glass tokens.
 */

import { apiRequest } from '@/lib/api';

export interface SSHHostConfig {
  host_alias: string;
  hostname: string;
  user?: string;
  port?: number;
  identity_file?: string;
  is_read_only: boolean;
  environment_tier: 'production' | 'staging' | 'development' | string;
  require_confirm_on_write: boolean;
  source: 'ssh_config' | 'custom' | string;
}

export interface SSHAssetSummary {
  hosts: SSHHostConfig[];
  total_hosts: number;
  config_path?: string;
}

export interface SSHProbeResult {
  host_alias: string;
  reachable: boolean;
  latency_ms: number;
  error_message?: string;
}

export interface BreakGlassRequest {
  host_alias: string;
  command: string;
  reason: string;
  ttl_seconds?: number;
}

export interface BreakGlassResponse {
  token: string;
  host_alias: string;
  reason: string;
  expires_at: number;
}

export interface HostPolicyUpdate {
  is_read_only?: boolean;
  environment_tier?: string;
  require_confirm_on_write?: boolean;
}

export async function getSSHVaultSummary(): Promise<SSHAssetSummary> {
  return await apiRequest<SSHAssetSummary>('/ssh-vault/summary');
}

export async function probeSSHHost(hostAlias: string, timeout = 3.0): Promise<SSHProbeResult> {
  return await apiRequest<SSHProbeResult>(`/ssh-vault/probe/${encodeURIComponent(hostAlias)}?timeout=${timeout}`);
}

export async function updateHostPolicy(
  hostAlias: string,
  update: HostPolicyUpdate,
): Promise<{ status: string; host_alias: string }> {
  return await apiRequest<{ status: string; host_alias: string }>(
    `/ssh-vault/host/${encodeURIComponent(hostAlias)}/policy`,
    {
      method: 'PATCH',
      body: JSON.stringify(update),
    },
  );
}

export async function requestBreakGlassToken(payload: BreakGlassRequest): Promise<BreakGlassResponse> {
  return await apiRequest<BreakGlassResponse>('/ssh-vault/break-glass/request', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
