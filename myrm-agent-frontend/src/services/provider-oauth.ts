import { apiRequest } from '@/lib/api';

export type ProviderOAuthProvider = 'xai';

export interface ProviderOAuthStartResponse {
  user_code: string;
  verification_uri: string;
  verification_uri_complete: string;
  expires_in: number;
  interval: number;
}

export interface ProviderOAuthPollResponse {
  status: 'success' | 'pending' | 'expired' | 'denied';
  error?: string;
  slow_down?: boolean;
}

export interface ProviderOAuthStatus {
  provider: string;
  issuer: string;
  connected: boolean;
  expires_at?: number | null;
  scope?: string | null;
  base_url?: string | null;
  available_models?: string[];
}

export function getProviderOAuthProviderByProviderId(providerId: string): ProviderOAuthProvider | null {
  return providerId === 'xai' ? 'xai' : null;
}

export async function startProviderOAuth(provider: ProviderOAuthProvider): Promise<ProviderOAuthStartResponse> {
  return apiRequest<ProviderOAuthStartResponse>(`/integrations/provider-oauth/${provider}/start`, { method: 'POST' });
}

export async function pollProviderOAuth(
  provider: ProviderOAuthProvider,
  userCode: string,
): Promise<ProviderOAuthPollResponse> {
  return apiRequest<ProviderOAuthPollResponse>(
    `/integrations/provider-oauth/${provider}/poll?user_code=${encodeURIComponent(userCode)}`,
    { method: 'POST', silent: true },
  );
}

export async function fetchProviderOAuthStatus(provider: ProviderOAuthProvider): Promise<ProviderOAuthStatus> {
  return apiRequest<ProviderOAuthStatus>(`/integrations/provider-oauth/status/${provider}`, { silent: true });
}

export async function disconnectProviderOAuth(provider: ProviderOAuthProvider): Promise<void> {
  await apiRequest(`/integrations/provider-oauth/disconnect/${provider}`, {
    method: 'DELETE',
  });
}
