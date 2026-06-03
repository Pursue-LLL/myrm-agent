import { getWebuiUrl } from '@/lib/api';

export interface WebuiProtectionConfig {
  require_password: boolean;
  admin_configured: boolean;
}

export interface WebuiSetupTokenResponse {
  temp_token: string;
  setup_path: string;
}

async function webuiFetch<T>(endpoint: string, init?: RequestInit): Promise<T> {
  const response = await fetch(getWebuiUrl(endpoint), {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init?.headers as Record<string, string>) },
    ...init,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Request failed';
    throw new Error(detail);
  }
  return data as T;
}

export async function fetchWebuiProtection(): Promise<WebuiProtectionConfig> {
  return webuiFetch<WebuiProtectionConfig>('/auth/protection');
}

export async function updateWebuiProtection(requirePassword: boolean): Promise<WebuiProtectionConfig> {
  return webuiFetch<WebuiProtectionConfig>('/auth/protection', {
    method: 'PUT',
    body: JSON.stringify({ require_password: requirePassword }),
  });
}

export async function changeWebuiPassword(currentPassword: string, newPassword: string): Promise<void> {
  await webuiFetch<{ ok: boolean }>('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export async function disableWebuiProtection(password: string): Promise<void> {
  await webuiFetch<{ ok: boolean }>('/auth/disable-protection', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
}

export async function generateWebuiSetupToken(): Promise<WebuiSetupTokenResponse> {
  return webuiFetch<WebuiSetupTokenResponse>('/auth/generate-setup-token', { method: 'POST' });
}
