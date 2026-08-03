import { apiRequest } from '@/lib/api';

export type ProviderOAuthProvider = 'anthropic' | 'openai' | 'copilot';

export interface ProviderOAuthStartResponse {
  authorize_url?: string;
  state?: string;
  user_code?: string;
  verification_uri?: string;
  expires_in?: number;
  interval?: number;
}

export interface ProviderOAuthPollResponse {
  status: 'success' | 'pending' | 'expired' | 'denied';
  error?: string;
  slow_down?: boolean;
  available_models?: string[];
  base_url?: string;
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

const PROVIDER_OAUTH_CONFIGS: Record<
  ProviderOAuthProvider,
  { flow: 'pkce' | 'device_code'; providerId: string; name: string; nameZh: string }
> = {
  anthropic: {
    flow: 'pkce',
    providerId: 'anthropic',
    name: 'Claude Pro/Max',
    nameZh: 'Claude Pro/Max 订阅',
  },
  openai: {
    flow: 'device_code',
    providerId: 'openai',
    name: 'ChatGPT Plus/Pro',
    nameZh: 'ChatGPT Plus/Pro 订阅',
  },
  copilot: {
    flow: 'device_code',
    providerId: 'copilot',
    name: 'GitHub Copilot',
    nameZh: 'GitHub Copilot 订阅',
  },
};

export function getProviderOAuthConfig(provider: ProviderOAuthProvider) {
  return PROVIDER_OAUTH_CONFIGS[provider];
}

export function getProviderOAuthProviderByProviderId(
  providerId: string,
): ProviderOAuthProvider | null {
  if (providerId === 'anthropic') return 'anthropic';
  if (providerId === 'openai') return 'openai';
  if (providerId === 'copilot' || providerId === 'github_copilot') return 'copilot';
  return null;
}

export async function startProviderOAuth(
  provider: ProviderOAuthProvider,
): Promise<ProviderOAuthStartResponse> {
  return apiRequest<ProviderOAuthStartResponse>(
    `/integrations/provider-oauth/${provider}/start`,
    { method: 'POST' },
  );
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

export async function fetchProviderOAuthStatus(
  provider: ProviderOAuthProvider,
): Promise<ProviderOAuthStatus> {
  return apiRequest<ProviderOAuthStatus>(
    `/integrations/provider-oauth/status/${provider}`,
    { silent: true },
  );
}

export async function disconnectProviderOAuth(
  provider: ProviderOAuthProvider,
): Promise<void> {
  await apiRequest(`/integrations/provider-oauth/disconnect/${provider}`, {
    method: 'DELETE',
  });
}
