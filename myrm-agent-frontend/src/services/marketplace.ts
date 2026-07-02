/**
 * Org Agent Marketplace API Service.
 *
 * Calls Control Plane marketplace endpoints for browsing/publishing/installing
 * org-scoped Agent profiles. Only available in cloud-hosted (sandbox) mode.
 */

import { getApiUrl } from '@/lib/api';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

export interface MarketplaceEntry {
  id: string;
  org_id: string;
  publisher_user_id: string;
  name: string;
  description: string;
  avatar: string | null;
  tags: string[];
  status: string;
  latest_version: number;
  install_count: number;
  created_at: number;
  updated_at: number;
  is_installed?: boolean;
}

export interface MarketplaceVersion {
  id: string;
  entry_id: string;
  version: number;
  profile_data: Record<string, unknown>;
  changelog: string;
  published_at: number;
}

export interface PublishResult {
  entry_id: string;
  version: number;
  name: string;
}

export interface InstallResult {
  entry_id: string;
  version: number;
  profile_data: Record<string, unknown>;
}

const MP_BASE = '/api/marketplace';

function mpUrl(path: string): string {
  return getApiUrl(`${MP_BASE}${path}`);
}

export async function listMarketplaceEntries(
  orgId: string,
  options?: { search?: string; limit?: number; offset?: number },
): Promise<MarketplaceEntry[]> {
  const params = new URLSearchParams();
  if (options?.search) params.set('search', options.search);
  if (options?.limit) params.set('limit', String(options.limit));
  if (options?.offset) params.set('offset', String(options.offset));
  const qs = params.toString();
  const url = mpUrl(`/list/${orgId}${qs ? `?${qs}` : ''}`);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`List marketplace failed: ${res.status}`);
  return res.json();
}

export async function getMarketplaceEntry(entryId: string): Promise<MarketplaceEntry> {
  const res = await fetch(mpUrl(`/entry/${entryId}`));
  if (!res.ok) throw new Error(`Get entry failed: ${res.status}`);
  return res.json();
}

export async function getMarketplaceVersion(
  entryId: string,
  version?: number,
): Promise<MarketplaceVersion> {
  const params = version ? `?version=${version}` : '';
  const res = await fetch(mpUrl(`/version/${entryId}${params}`));
  if (!res.ok) throw new Error(`Get version failed: ${res.status}`);
  return res.json();
}

export async function installFromMarketplace(
  entryId: string,
  version?: number,
): Promise<InstallResult> {
  const params = version ? `?version=${version}` : '';
  const res = await fetch(mpUrl(`/install/${entryId}${params}`), { method: 'POST' });
  if (!res.ok) throw new Error(`Install failed: ${res.status}`);
  return res.json();
}

export async function publishToMarketplace(payload: {
  org_id: string;
  name: string;
  description: string;
  avatar?: string | null;
  tags?: string[];
  profile_data: Record<string, unknown>;
  changelog?: string;
}): Promise<PublishResult> {
  const res = await fetch(mpUrl('/publish'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Publish failed: ${res.status}`);
  return res.json();
}

export async function archiveMarketplaceEntry(entryId: string): Promise<void> {
  const res = await fetch(mpUrl(`/entry/${entryId}`), { method: 'DELETE' });
  if (!res.ok) throw new Error(`Archive failed: ${res.status}`);
}

export interface ForcePushResult {
  entry_id: string;
  version: number;
  total: number;
  synced: number;
  buffered: number;
  failed: number;
}

export async function forcePushUpdate(entryId: string): Promise<ForcePushResult> {
  const res = await fetch(mpUrl(`/force-push/${entryId}`), { method: 'POST' });
  if (!res.ok) throw new Error(`Force push failed: ${res.status}`);
  return res.json();
}

export interface ImportedAgent {
  id: string;
  name: string;
}

/**
 * Import a marketplace Agent package into the local sandbox
 * via the server's /api/v1/user-agents/marketplace-import endpoint.
 */
export async function importMarketplaceAgent(
  profileData: Record<string, unknown>,
): Promise<ImportedAgent> {
  const res = await fetch(`${getBackendUrl()}/api/v1/user-agents/marketplace-import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(profileData),
  });
  if (!res.ok) throw new Error(`Marketplace import failed: ${res.status}`);
  const json = await res.json();
  return json.data;
}
