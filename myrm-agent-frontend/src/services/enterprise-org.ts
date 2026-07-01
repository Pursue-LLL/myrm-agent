/**
 * Enterprise Organization Management API Service.
 *
 * Calls Control Plane enterprise org endpoints via the sandbox proxy.
 * Only available in cloud-hosted enterprise edition.
 */

import { getApiUrl } from './config/getApiUrl';

export interface OrgInfo {
  id: string;
  name: string;
  owner_user_id: string;
  sso_domain: string | null;
  archive_retention_days: number;
}

export interface OrgMember {
  user_id: string;
  role: string;
  joined_at: number;
}

export interface HandoffLog {
  id: string;
  source_user_id: string;
  target_user_id: string | null;
  admin_user_id: string;
  action: string;
  status: string;
  created_at: number;
  completed_at: number | null;
}

const CP_BASE = '/api/enterprise/org';

function cpUrl(path: string): string {
  return getApiUrl(`${CP_BASE}${path}`);
}

export async function createOrg(name: string, ssoDomain?: string): Promise<OrgInfo> {
  const res = await fetch(cpUrl(''), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, sso_domain: ssoDomain || null }),
  });
  if (!res.ok) throw new Error(`Create org failed: ${res.status}`);
  return res.json();
}

export async function getOrg(orgId: string): Promise<OrgInfo> {
  const res = await fetch(cpUrl(`/${orgId}`));
  if (!res.ok) throw new Error(`Get org failed: ${res.status}`);
  return res.json();
}

export async function listMembers(orgId: string): Promise<OrgMember[]> {
  const res = await fetch(cpUrl(`/${orgId}/members`));
  if (!res.ok) throw new Error(`List members failed: ${res.status}`);
  return res.json();
}

export async function addMember(orgId: string, userId: string, role = 'member'): Promise<OrgMember> {
  const res = await fetch(cpUrl(`/${orgId}/members`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, role }),
  });
  if (!res.ok) throw new Error(`Add member failed: ${res.status}`);
  return res.json();
}

export async function removeMember(orgId: string, userId: string): Promise<void> {
  const res = await fetch(cpUrl(`/${orgId}/members/${userId}`), { method: 'DELETE' });
  if (!res.ok) throw new Error(`Remove member failed: ${res.status}`);
}

export async function offboardUser(orgId: string, sourceUserId: string): Promise<HandoffLog> {
  const res = await fetch(cpUrl(`/${orgId}/offboarding/${sourceUserId}`), { method: 'POST' });
  if (!res.ok) throw new Error(`Offboard failed: ${res.status}`);
  return res.json();
}

export async function transferVolume(
  orgId: string,
  sourceUserId: string,
  targetUserId: string,
  backupPath?: string
): Promise<HandoffLog> {
  const res = await fetch(cpUrl(`/${orgId}/transfer/${sourceUserId}`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_user_id: targetUserId, backup_path: backupPath || null }),
  });
  if (!res.ok) throw new Error(`Transfer failed: ${res.status}`);
  return res.json();
}

export async function listHandoffLogs(orgId: string): Promise<HandoffLog[]> {
  const res = await fetch(cpUrl(`/${orgId}/handoff-logs`));
  if (!res.ok) throw new Error(`List handoff logs failed: ${res.status}`);
  return res.json();
}
