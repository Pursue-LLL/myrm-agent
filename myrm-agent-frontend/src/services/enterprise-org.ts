/**
 * Enterprise Organization Management API Service.
 *
 * Calls Control Plane enterprise org endpoints directly (not via the sandbox
 * proxy — these routes live on the Control Plane itself). Requires the
 * Control Plane JWT that the sandbox proxy already validated.
 * Only available in cloud-hosted enterprise edition.
 */

import { resolveCpBaseUrl } from '@/lib/cp-base-url';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

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
  idp_groups: string[] | null;
  joined_at: number;
  oauth_bound?: boolean | null;
  email?: string | null;
  display_name?: string | null;
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
  return `${resolveCpBaseUrl()}${CP_BASE}${path}`;
}

function jsonHeaders(): Record<string, string> {
  return { 'Content-Type': 'application/json', ...getAuthHeaders() };
}

async function toError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body?.detail === 'string' && body.detail) {
      return new Error(body.detail);
    }
  } catch {
    // non-JSON error body — fall through to the generic message
  }
  return new Error(fallback);
}

export async function createOrg(name: string, ssoDomain?: string): Promise<OrgInfo> {
  const res = await fetch(cpUrl(''), {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ name, sso_domain: ssoDomain || null }),
  });
  if (!res.ok) {throw new Error(`Create org failed: ${res.status}`);}
  return res.json();
}

export async function getOrg(orgId: string): Promise<OrgInfo> {
  const res = await fetch(cpUrl(`/${orgId}`), { headers: getAuthHeaders() });
  if (!res.ok) {throw new Error(`Get org failed: ${res.status}`);}
  return res.json();
}

export async function getMyOrg(): Promise<OrgInfo> {
  const res = await fetch(cpUrl('/me'), { headers: getAuthHeaders() });
  if (!res.ok) {throw new Error(`Get my org failed: ${res.status}`);}
  return res.json();
}

export async function updateOrgSsoDomain(orgId: string, ssoDomain: string): Promise<OrgInfo> {
  const res = await fetch(cpUrl(`/${orgId}`), {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify({ sso_domain: ssoDomain.trim() || null }),
  });
  if (!res.ok) {throw new Error(`Update org SSO domain failed: ${res.status}`);}
  return res.json();
}

export async function listMembers(orgId: string): Promise<OrgMember[]> {
  const res = await fetch(cpUrl(`/${orgId}/members`), { headers: getAuthHeaders() });
  if (!res.ok) {throw new Error(`List members failed: ${res.status}`);}
  return res.json();
}

export async function addMember(orgId: string, userId: string, role = 'member'): Promise<OrgMember> {
  const res = await fetch(cpUrl(`/${orgId}/members`), {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ user_id: userId, role }),
  });
  if (!res.ok) {throw await toError(res, `Add member failed: ${res.status}`);}
  return res.json();
}

export async function removeMember(orgId: string, userId: string): Promise<void> {
  const res = await fetch(cpUrl(`/${orgId}/members/${userId}`), {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {throw await toError(res, `Remove member failed: ${res.status}`);}
}

export async function unlinkOauth(orgId: string, userId: string): Promise<void> {
  const res = await fetch(cpUrl(`/${orgId}/members/${userId}/unlink-oauth`), {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {throw await toError(res, `Unlink OAuth failed: ${res.status}`);}
}

export async function offboardUser(orgId: string, sourceUserId: string): Promise<HandoffLog> {
  const res = await fetch(cpUrl(`/${orgId}/offboarding/${sourceUserId}`), {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {throw await toError(res, `Offboard failed: ${res.status}`);}
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
    headers: jsonHeaders(),
    body: JSON.stringify({ target_user_id: targetUserId, backup_path: backupPath || null }),
  });
  if (!res.ok) {throw await toError(res, `Transfer failed: ${res.status}`);}
  return res.json();
}

export async function listHandoffLogs(orgId: string): Promise<HandoffLog[]> {
  const res = await fetch(cpUrl(`/${orgId}/handoff-logs`), { headers: getAuthHeaders() });
  if (!res.ok) {throw new Error(`List handoff logs failed: ${res.status}`);}
  return res.json();
}

export interface OrgMCPDelivery {
  synced: number;
  skipped: number;
  failed: number;
}

export interface OrgMCPServer {
  id: string;
  name: string;
  type: 'sse' | 'streamable_http' | 'tunnel';
  url: string | null;
  command: string | null;
  args: string[] | null;
  headers_configured: boolean;
  acl_groups: string[] | null;
  description: string;
  enabled: boolean;
  created_by: string;
  created_at: number;
  updated_at: number;
}

export interface OrgMCPMutateResult {
  server: OrgMCPServer;
  delivery: OrgMCPDelivery;
}

export interface CreateOrgMCPServerInput {
  name: string;
  type: 'sse' | 'streamable_http' | 'tunnel';
  url?: string;
  description?: string;
  headers?: Record<string, string>;
  tunnel_id?: string;
  acl_groups?: string[];
}

export interface UpdateOrgMCPServerInput {
  name?: string;
  type?: 'sse' | 'streamable_http' | 'tunnel';
  url?: string;
  description?: string;
  headers?: Record<string, string>;
  enabled?: boolean;
  tunnel_id?: string;
  acl_groups?: string[];
}

// ── Tunnel Management ──────────────────────────────────────────────

export interface Tunnel {
  id: string;
  name: string;
  upstream_url: string;
  description: string;
  status: 'online' | 'offline' | 'degraded';
  last_heartbeat_at: number | null;
  last_upstream_error: string | null;
  last_error_at: number | null;
  created_by: string;
  created_at: number;
  updated_at: number;
}

export interface TunnelCreateResult {
  tunnel: Tunnel;
  auth_token: string;
}

export interface CreateTunnelInput {
  name: string;
  upstream_url: string;
  description?: string;
  upstream_headers?: Record<string, string>;
}

function tunnelUrl(orgId: string, tunnelId?: string): string {
  const base = cpUrl(`/${orgId}/tunnels`);
  return tunnelId ? `${base}/${tunnelId}` : base;
}

export async function listTunnels(orgId: string): Promise<Tunnel[]> {
  const res = await fetch(tunnelUrl(orgId), { headers: getAuthHeaders() });
  if (!res.ok) {throw new Error(`List tunnels failed: ${res.status}`);}
  return res.json();
}

export async function createTunnel(
  orgId: string,
  input: CreateTunnelInput,
): Promise<TunnelCreateResult> {
  const res = await fetch(tunnelUrl(orgId), {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) {throw new Error(`Create tunnel failed: ${res.status}`);}
  return res.json();
}

export async function deleteTunnel(orgId: string, tunnelId: string): Promise<void> {
  const res = await fetch(tunnelUrl(orgId, tunnelId), {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {throw new Error(`Delete tunnel failed: ${res.status}`);}
}

export async function rotateTunnelToken(
  orgId: string,
  tunnelId: string,
): Promise<TunnelCreateResult> {
  const res = await fetch(`${tunnelUrl(orgId, tunnelId)}/rotate-token`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {throw new Error(`Rotate tunnel token failed: ${res.status}`);}
  return res.json();
}

export async function bindTunnelToOrgMcp(
  orgId: string,
  tunnelId: string,
): Promise<OrgMCPMutateResult> {
  const res = await fetch(`${tunnelUrl(orgId, tunnelId)}/bind-mcp`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {throw new Error(`Bind tunnel to org MCP failed: ${res.status}`);}
  return res.json();
}

function mcpUrl(orgId: string, serverId?: string): string {
  const base = cpUrl(`/${orgId}/mcp-servers`);
  return serverId ? `${base}/${serverId}` : base;
}

export async function listOrgMcpServers(orgId: string): Promise<OrgMCPServer[]> {
  const res = await fetch(mcpUrl(orgId), { headers: getAuthHeaders() });
  if (!res.ok) {throw new Error(`List org MCP servers failed: ${res.status}`);}
  return res.json();
}

export async function createOrgMcpServer(
  orgId: string,
  input: CreateOrgMCPServerInput,
): Promise<OrgMCPMutateResult> {
  const res = await fetch(mcpUrl(orgId), {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) {throw new Error(`Create org MCP server failed: ${res.status}`);}
  return res.json();
}

export async function updateOrgMcpServer(
  orgId: string,
  serverId: string,
  input: UpdateOrgMCPServerInput,
): Promise<OrgMCPMutateResult> {
  const res = await fetch(mcpUrl(orgId, serverId), {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) {throw new Error(`Update org MCP server failed: ${res.status}`);}
  return res.json();
}

export async function deleteOrgMcpServer(
  orgId: string,
  serverId: string,
): Promise<{ delivery: OrgMCPDelivery }> {
  const res = await fetch(mcpUrl(orgId, serverId), {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {throw new Error(`Delete org MCP server failed: ${res.status}`);}
  return res.json();
}

export interface OrgOidcConfig {
  org_id: string;
  issuer_url: string;
  client_id: string;
  client_secret_masked: string;
  auto_provision: boolean;
  allowed_groups: string[];
  enabled: boolean;
  updated_at: number;
}

export interface UpsertOrgOidcConfigInput {
  issuer_url: string;
  client_id: string;
  client_secret?: string;
  auto_provision?: boolean;
  allowed_groups?: string[];
  enabled?: boolean;
}

function ssoUrl(orgId: string): string {
  return cpUrl(`/${orgId}/sso`);
}

export async function getOrgSsoConfig(orgId: string): Promise<OrgOidcConfig | null> {
  const res = await fetch(ssoUrl(orgId), { headers: getAuthHeaders() });
  if (res.status === 404) {return null;}
  if (!res.ok) {throw new Error(`Get org SSO config failed: ${res.status}`);}
  return res.json();
}

export async function upsertOrgSsoConfig(
  orgId: string,
  input: UpsertOrgOidcConfigInput,
): Promise<OrgOidcConfig> {
  const res = await fetch(ssoUrl(orgId), {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Upsert org SSO config failed: ${res.status}`);
  }
  return res.json();
}

export async function deleteOrgSsoConfig(orgId: string): Promise<void> {
  const res = await fetch(ssoUrl(orgId), {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {throw new Error(`Delete org SSO config failed: ${res.status}`);}
}

// ── Model Policy API ───────────────────────────────────────────────────

export interface ModelPolicyEntry {
  id: string;
  pattern: string;
  description: string;
  created_by: string;
  created_at: number;
}

export interface ModelPolicyResponse {
  patterns: ModelPolicyEntry[];
  fanout?: { synced: number; skipped: number; failed: number };
}

function modelPolicyUrl(orgId: string, entryId?: string): string {
  const base = cpUrl(`/${orgId}/model-policy`);
  return entryId ? `${base}/${entryId}` : base;
}

export async function getModelPolicy(orgId: string): Promise<ModelPolicyResponse> {
  const res = await fetch(modelPolicyUrl(orgId), { headers: getAuthHeaders() });
  if (!res.ok) {throw new Error(`Get model policy failed: ${res.status}`);}
  return res.json();
}

export async function addModelPolicy(
  orgId: string,
  pattern: string,
  description: string,
): Promise<ModelPolicyResponse> {
  const res = await fetch(modelPolicyUrl(orgId), {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ pattern, description }),
  });
  if (!res.ok) {throw new Error(await res.text());}
  return res.json();
}

export async function removeModelPolicy(orgId: string, entryId: string): Promise<ModelPolicyResponse> {
  const res = await fetch(modelPolicyUrl(orgId, entryId), {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {throw new Error(await res.text());}
  return res.json();
}

// ── Approval Policy API ────────────────────────────────────────────────

export interface ApprovalPolicyState {
  ignoreAllowlistForModels: string[];
  forceAutoReviewForModels: string[];
  disableYolo: boolean;
  disableAllowAlways: boolean;
}

export type ApprovalPolicySaveResult = ApprovalPolicyState & {
  fanout?: { synced: number; skipped: number; failed: number };
};

function approvalPolicyUrl(orgId: string): string {
  return cpUrl(`/${orgId}/approval-policy`);
}

export async function getApprovalPolicy(orgId: string): Promise<ApprovalPolicyState> {
  const res = await fetch(approvalPolicyUrl(orgId), { headers: getAuthHeaders() });
  if (!res.ok) {throw new Error(`Get approval policy failed: ${res.status}`);}
  return res.json();
}

export async function saveApprovalPolicy(
  orgId: string,
  input: ApprovalPolicyState,
): Promise<ApprovalPolicySaveResult> {
  const res = await fetch(approvalPolicyUrl(orgId), {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify({
      ignore_allowlist_for_models: input.ignoreAllowlistForModels,
      force_auto_review_for_models: input.forceAutoReviewForModels,
      disable_yolo: input.disableYolo,
      disable_allow_always: input.disableAllowAlways,
    }),
  });
  if (!res.ok) {throw new Error(await res.text());}
  return res.json();
}
