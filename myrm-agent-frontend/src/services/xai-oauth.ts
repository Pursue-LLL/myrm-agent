import { apiRequest } from '@/lib/api';

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
