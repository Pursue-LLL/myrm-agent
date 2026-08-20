import { apiRequest } from '@/lib/api';

export const XAI_ISSUER = 'xai';

export interface XaiOAuthStartResponse {
  user_code: string;
  verification_uri: string;
  verification_uri_complete: string;
  expires_in: number;
  interval: number;
}

export interface XaiOAuthPollResponse {
  status: 'success' | 'pending' | 'expired' | 'denied';
  error?: string;
  slow_down?: boolean;
}

export interface XaiOAuthStatus {
  issuer: string;
  connected: boolean;
  scope: string | null;
  expires_at: number | null;
}

export async function startXaiOAuth(): Promise<XaiOAuthStartResponse> {
  return apiRequest<XaiOAuthStartResponse>('/integrations/xai/oauth/start', {
    method: 'POST',
  });
}

export async function pollXaiOAuth(userCode: string): Promise<XaiOAuthPollResponse> {
  return apiRequest<XaiOAuthPollResponse>(`/integrations/xai/oauth/poll?user_code=${encodeURIComponent(userCode)}`, {
    method: 'POST',
    silent: true,
  });
}

export async function fetchXaiOAuthStatus(): Promise<XaiOAuthStatus> {
  return apiRequest<XaiOAuthStatus>('/integrations/xai/oauth/status', { silent: true });
}

export async function disconnectXaiOAuth(): Promise<void> {
  await apiRequest('/integrations/xai/oauth', { method: 'DELETE' });
}
