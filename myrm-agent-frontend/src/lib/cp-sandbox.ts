/**
 * [INPUT]
 * - process.env.NEXT_PUBLIC_CP_API_URL (POS: Control Plane 基础 URL)
 * - localStorage auth_token (POS: CP JWT)
 *
 * [OUTPUT]
 * - fetchUserSandbox: 拉取当前用户沙箱
 * - fetchSandboxVncUrl: 拉取 VNC WebSocket URL + token
 *
 * [POS]
 * SaaS Sandbox 模式下 CP 沙箱/VNC API 薄封装。
 */

import { getCpApiBaseUrl } from '@/lib/cp-billing';

export interface SandboxSummary {
  id: string;
  user_id: string;
  status: string;
  vnc_url: string | null;
}

export interface SandboxVncResponse {
  vnc_url: string;
  token: string;
  sandbox_id: string;
}

function authHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  const headers: HeadersInit = { 'Content-Type': 'application/json' };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

export async function fetchUserSandbox(): Promise<SandboxSummary | null> {
  const response = await fetch(`${getCpApiBaseUrl()}/api/sandboxes`, {
    headers: authHeaders(),
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch sandboxes: ${response.status}`);
  }
  const payload = (await response.json()) as { sandboxes?: SandboxSummary[] };
  const sandboxes = payload.sandboxes ?? [];
  return sandboxes[0] ?? null;
}

export async function fetchSandboxVncUrl(sandboxId: string): Promise<SandboxVncResponse> {
  const response = await fetch(`${getCpApiBaseUrl()}/api/sandboxes/${sandboxId}/vnc`, {
    headers: authHeaders(),
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch VNC URL: ${response.status}`);
  }
  return response.json();
}

export function buildVncWebSocketUrl(vncUrl: string, token: string): string {
  if (!vncUrl) {
    return '';
  }
  if (vncUrl.includes('token=')) {
    return vncUrl;
  }
  const separator = vncUrl.includes('?') ? '&' : '?';
  return `${vncUrl}${separator}token=${encodeURIComponent(token)}`;
}
