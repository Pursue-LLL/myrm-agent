/**
 * [INPUT]
 * - @/lib/api::apiRequest, fetchWithTimeout (POS: 前端统一请求入口)
 *
 * [OUTPUT]
 * - ExternalAgentAuthStatus / ExternalAgentAuthEvent 类型
 * - getExternalAgentAuthStatus / streamExternalAgentLogin / feedExternalAgentLogin
 *   / importExternalAgentCredential / logoutExternalAgent
 *
 * [POS]
 * 外部委托 Agent 订阅鉴权前端服务层。封装登录状态查询、SSE 交互式登录、
 * 凭据导入/登出，供设置页的鉴权 UI 调用（local + SaaS 全模式可用）。
 */
import { apiRequest, fetchWithTimeout } from '@/lib/api';

export type ExternalAgentLoginStrategy = 'device_code' | 'browser_oauth' | 'setup_token' | 'manual_import';

export interface ExternalAgentHealthMetrics {
  restart_count: number;
  last_crash_time: number | null;
  last_check_time: number | null;
  total_uptime_seconds: number;
}

export interface ExternalAgentAuthStatus {
  backend: string;
  installed: boolean;
  path: string | null;
  version: string | null;
  authenticated: boolean;
  authStatus: 'authenticated' | 'not_authenticated' | 'unknown';
  loginStrategy: ExternalAgentLoginStrategy;
  scriptableLogin: boolean;
  needsCodeInput: boolean;
  healthMetrics?: ExternalAgentHealthMetrics;
}

export interface ExternalAgentAuthEvent {
  type: 'status' | 'prompt' | 'success' | 'error' | 'progress';
  message: string;
  url?: string;
  code?: string;
}

interface ExternalAgentCredentialState {
  backend: string;
  authenticated: boolean;
  authStatus: string;
}

/** Fetch install + login state for every known delegated backend (drives badges). */
export async function getExternalAgentAuthStatus(): Promise<ExternalAgentAuthStatus[]> {
  const res = await apiRequest<{ backends: ExternalAgentAuthStatus[] }>('/external-agents/auth/status', {
    silent: true,
  });
  return res.backends ?? [];
}

export async function* streamExternalAgentInstall(
  backend: string
): AsyncGenerator<ExternalAgentAuthEvent, void, unknown> {
  const response = await fetchWithTimeout(`/external-agents/install/${backend}`, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
    },
    timeout: 300000, // 5 minutes for installation
  });

  if (!response.body) {
    throw new Error('No response body');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') return;
          try {
            const event = JSON.parse(data) as ExternalAgentAuthEvent;
            yield event;
          } catch (e) {
            console.error('Failed to parse SSE event:', data, e);
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** Persist a credential blob captured elsewhere (universal fallback). */
export function importExternalAgentCredential(
  backend: string,
  content: string,
  filename?: string,
): Promise<ExternalAgentCredentialState> {
  return apiRequest<ExternalAgentCredentialState>('/external-agents/auth/import', {
    method: 'POST',
    body: JSON.stringify({ backend, content, filename }),
  });
}

/** Remove a backend's stored subscription credentials. */
export function logoutExternalAgent(backend: string): Promise<ExternalAgentCredentialState> {
  return apiRequest<ExternalAgentCredentialState>('/external-agents/auth/logout', {
    method: 'POST',
    body: JSON.stringify({ backend }),
  });
}

/** Forward a user-supplied code to a live login session (setup_token flow). */
export function feedExternalAgentLogin(sessionId: string, text: string): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>(`/external-agents/auth/login/${encodeURIComponent(sessionId)}/feed`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

/**
 * Drive an interactive CLI login over SSE, invoking `onEvent` for each event
 * until the stream closes. Pass an AbortSignal to cancel mid-flight.
 */
export async function streamExternalAgentLogin(
  params: { command: string; backend?: string; sessionId: string },
  onEvent: (event: ExternalAgentAuthEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetchWithTimeout(
    '/external-agents/auth/login',
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ command: params.command, backend: params.backend, sessionId: params.sessionId }),
      signal,
    },
    0,
  );

  if (!response.ok || !response.body) {
    throw new Error(`Login stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const dataLine = frame.split('\n').find((line) => line.startsWith('data:'));
        if (!dataLine) continue;
        try {
          onEvent(JSON.parse(dataLine.slice(5).trim()) as ExternalAgentAuthEvent);
        } catch {
          // ignore malformed frame
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
