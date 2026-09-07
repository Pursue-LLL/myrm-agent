import { apiRequest } from '@/lib/api';

export interface A2APeer {
  id: string;
  name: string;
  base_url: string;
  description?: string | null;
  auth_type: string;
  is_active: boolean;
  has_token: boolean;
  masked_token?: string | null;
  last_probed_at?: string | null;
  last_probe_status?: 'ok' | 'error' | 'ssrf_blocked' | 'unreachable' | null;
  last_probe_error?: string | null;
  cached_card_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface A2APeerCreateInput {
  name: string;
  base_url: string;
  description?: string | null;
  auth_type?: string;
  auth_token?: string | null;
  is_active?: boolean;
}

export interface A2APeerUpdateInput {
  name?: string;
  base_url?: string;
  description?: string | null;
  auth_type?: string;
  auth_token?: string | null;
  is_active?: boolean;
}

export interface A2APeerProbeInput {
  url?: string | null;
  auth_token?: string | null;
  peer_id?: string | null;
}

export interface A2APeerProbeResult {
  success: boolean;
  status: 'ok' | 'error' | 'ssrf_blocked' | 'unreachable';
  latency_ms: number;
  agent_card?: Record<string, unknown> | null;
  error?: string | null;
}

export async function listA2APeers(activeOnly = false): Promise<A2APeer[]> {
  const query = activeOnly ? '?active_only=true' : '';
  return apiRequest<A2APeer[]>(`/a2a/peers${query}`);
}

export async function getA2APeer(id: string): Promise<A2APeer> {
  return apiRequest<A2APeer>(`/a2a/peers/${id}`);
}

export async function createA2APeer(input: A2APeerCreateInput): Promise<A2APeer> {
  return apiRequest<A2APeer>('/a2a/peers', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function updateA2APeer(id: string, input: A2APeerUpdateInput): Promise<A2APeer> {
  return apiRequest<A2APeer>(`/a2a/peers/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  });
}

export async function deleteA2APeer(id: string): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/a2a/peers/${id}`, {
    method: 'DELETE',
  });
}

export async function probeA2APeer(input: A2APeerProbeInput): Promise<A2APeerProbeResult> {
  return apiRequest<A2APeerProbeResult>('/a2a/peers/probe', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}
