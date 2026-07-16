import { apiRequest, getApiUrl } from '@/lib/api';
import type { LoginEvent, StartLoginResponse } from '@/types/channels';

/**
 * Start async login flow
 */
export async function startLogin(channelId: string, method: string): Promise<StartLoginResponse> {
  return apiRequest(`/channels/${channelId}/login/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ method }),
    silent: true,
  });
}

/**
 * Subscribe to login state SSE stream
 *
 * @returns EventSource for real-time updates
 */
export function subscribeLoginStream(
  sessionId: string,
  onEvent: (event: LoginEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
  const url = getApiUrl(`/channels/login/${sessionId}/stream`);
  const eventSource = new EventSource(url);

  eventSource.addEventListener('login_state', (event: MessageEvent) => {
    try {
      const parsed: LoginEvent = JSON.parse(event.data);
      onEvent(parsed);
    } catch (error) {
      console.error('Failed to parse login event:', error);
    }
  });

  if (onError) {
    eventSource.onerror = onError;
  }

  return eventSource;
}

/**
 * Cancel ongoing login flow
 */
export async function cancelLogin(sessionId: string): Promise<void> {
  return apiRequest(`/channels/login/${sessionId}`, {
    method: 'DELETE',
  });
}
