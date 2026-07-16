import { apiRequest, BACKEND_BASE_URL } from '@/lib/api';

// ==================== Channel Service Factory ====================

export interface ChannelTestResult {
  ok: boolean;
  message: string;
}

export async function cpChannelRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  if (!headers['Content-Type'] && options.body) {
    headers['Content-Type'] = 'application/json';
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${BACKEND_BASE_URL}${path}`, {
    cache: 'no-store',
    credentials: 'include',
    ...options,
    headers,
  });

  if (response.status === 401 || response.status === 403) {
    throw new Error('Authentication required for Control Plane channel API');
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `CP channel request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function getCpChannelCredentialStatus(): Promise<{
  configured: string[];
  webhook_urls: Record<string, string>;
}> {
  return cpChannelRequest('/api/channels/credentials/status');
}

export function createChannelCredentialService<T>(configKey: string, testEndpoint: string) {
  return {
    get: async (): Promise<T | null> => {
      try {
        const record = await apiRequest<{ value: T }>(`/config/${configKey}`);
        return record.value;
      } catch {
        return null;
      }
    },
    save: async (creds: T): Promise<void> => {
      await apiRequest(`/config/${configKey}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: creds, deviceId: 'web' }),
      });
    },
    test: async (params: Record<string, unknown>): Promise<ChannelTestResult> => {
      return apiRequest(testEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
    },
  };
}
