/**
 * API Key management service.
 *
 * [INPUT] @/lib/api::apiRequest (POS: unified HTTP client)
 * [OUTPUT] CRUD operations for OpenAI-compatible API keys
 * [POS] Frontend service layer for API key management.
 */

import { apiRequest } from '@/lib/api';

export interface APIKeyInfo {
  id: number;
  name: string;
  key_prefix: string;
  is_active: boolean;
  last_used_at: string | null;
  usage_count: number;
  expires_at: string | null;
  note: string | null;
  created_at: string;
}

export interface CreateKeyResponse {
  id: number;
  name: string;
  key: string;
  key_prefix: string;
  expires_at: string | null;
  created_at: string;
}

export interface CreateKeyParams {
  name: string;
  expires_in_days?: number | null;
  note?: string | null;
}

export async function createApiKey(params: CreateKeyParams): Promise<CreateKeyResponse> {
  return apiRequest<CreateKeyResponse>('/api-keys', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function listApiKeys(): Promise<APIKeyInfo[]> {
  return apiRequest<APIKeyInfo[]>('/api-keys');
}

export async function revokeApiKey(keyId: number): Promise<void> {
  await apiRequest(`/api-keys/${keyId}/revoke`, { method: 'PATCH' });
}

export async function deleteApiKey(keyId: number): Promise<void> {
  await apiRequest(`/api-keys/${keyId}`, { method: 'DELETE' });
}
