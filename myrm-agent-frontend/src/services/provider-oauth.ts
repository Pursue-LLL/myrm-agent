import { apiRequest } from '@/lib/api';

export type ProviderOAuthProvider = 'xai';

export interface ProviderOAuthStatus {
  provider: string;
  issuer: string;
  connected: boolean;
}

export function getProviderOAuthProviderByProviderId(providerId: string): ProviderOAuthProvider | null {
  return providerId === 'xai' ? 'xai' : null;
}

export async function fetchProviderOAuthStatus(provider: ProviderOAuthProvider): Promise<ProviderOAuthStatus> {
  return apiRequest<ProviderOAuthStatus>(`/integrations/provider-oauth/status/${provider}`, { silent: true });
}

export async function disconnectProviderOAuth(provider: ProviderOAuthProvider): Promise<void> {
  await apiRequest(`/integrations/provider-oauth/disconnect/${provider}`, {
    method: 'DELETE',
  });
}
