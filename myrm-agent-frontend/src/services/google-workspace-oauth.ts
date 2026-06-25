import { apiRequest } from '@/lib/api';

export const GOOGLE_WORKSPACE_ISSUER = 'google_workspace';

export interface GoogleWorkspaceOAuthConfig {
  configured: boolean;
  issuer: string;
  callback_path: string;
  redirect_uri: string;
}

export interface GoogleWorkspaceOAuthStatus {
  issuer: string;
  connected: boolean;
  user_id: string | null;
  scope: string | null;
  expires_at: number | null;
}

export async function fetchGoogleWorkspaceOAuthConfig(): Promise<GoogleWorkspaceOAuthConfig> {
  return apiRequest<GoogleWorkspaceOAuthConfig>('/integrations/google-workspace/oauth/config', {
    silent: true,
  });
}

export async function startGoogleWorkspaceOAuth(): Promise<{ authorization_url: string; state: string }> {
  return apiRequest<{ authorization_url: string; state: string }>(
    '/integrations/google-workspace/oauth/start',
    { method: 'POST', body: JSON.stringify({}) },
  );
}

export async function pollGoogleWorkspaceOAuthState(state: string): Promise<{
  status: string;
  skill_auto_enabled?: boolean;
  skill_was_user_disabled?: boolean;
}> {
  return apiRequest<{
    status: string;
    skill_auto_enabled?: boolean;
    skill_was_user_disabled?: boolean;
  }>(
    `/integrations/google-workspace/oauth/status/${encodeURIComponent(state)}`,
    { silent: true },
  );
}

export async function fetchGoogleWorkspaceOAuthStatus(): Promise<GoogleWorkspaceOAuthStatus> {
  return apiRequest<GoogleWorkspaceOAuthStatus>('/integrations/google-workspace/oauth/status', {
    silent: true,
  });
}

export async function disconnectGoogleWorkspaceOAuth(): Promise<void> {
  await apiRequest('/integrations/google-workspace/oauth', { method: 'DELETE' });
}

export async function openGoogleAuthorizationUrl(url: string): Promise<void> {
  if (typeof window !== 'undefined' && '__TAURI__' in window) {
    const { open } = await import('@tauri-apps/plugin-shell');
    await open(url);
    return;
  }
  window.open(url, '_blank');
}
