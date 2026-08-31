/**
 * [INPUT]
 * - @/lib/api::fetchWithTimeout (POS: unified frontend HTTP client)
 *
 * [OUTPUT]
 * - previewWorkspaceTrustManifest / decideWorkspaceTrust / listTrustedFolders / revokeTrustedFolder
 *
 * [POS]
 * REST client for /security/workspace-trust/* — FolderGate manifest preview and trust decisions.
 */

import { fetchWithTimeout } from '@/lib/api';

export type WorkspaceTrustLevel = 'TRUSTED' | 'RESTRICTED' | 'REVOKED';

export interface WorkspaceTrustManifest {
  path: string;
  canonical_path: string;
  skill_count: number;
  rule_count: number;
  repo_command_prefixes: string[];
  has_myrm_config: boolean;
  current_level: WorkspaceTrustLevel | null;
}

export interface WorkspaceTrustEntry {
  path: string;
  level: WorkspaceTrustLevel;
  decided_at: string;
  manifest_hash: string;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const json = (await response.json()) as { success?: boolean; data?: T; message?: string };
  if (!response.ok || !json.success) {
    throw new Error(json.message || 'Request failed');
  }
  return json.data as T;
}

export async function previewWorkspaceTrustManifest(path: string): Promise<WorkspaceTrustManifest> {
  const response = await fetchWithTimeout('/security/workspace-trust/manifest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  return parseResponse(response);
}

export async function decideWorkspaceTrust(
  path: string,
  level: 'TRUSTED' | 'RESTRICTED',
): Promise<WorkspaceTrustEntry> {
  const response = await fetchWithTimeout('/security/workspace-trust/decide', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, level }),
  });
  return parseResponse(response);
}

export async function listTrustedFolders(): Promise<WorkspaceTrustEntry[]> {
  const response = await fetchWithTimeout('/security/workspace-trust');
  return parseResponse(response);
}

export async function revokeTrustedFolder(path: string, remove = false): Promise<void> {
  const params = new URLSearchParams({ path });
  if (remove) {
    params.set('remove', 'true');
  }
  const response = await fetchWithTimeout(`/security/workspace-trust?${params.toString()}`, {
    method: 'DELETE',
  });
  await parseResponse(response);
}
