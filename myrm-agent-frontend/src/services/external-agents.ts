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

export interface ExternalAgentAuthStatus {
  backend: string;
  installed: boolean;
  path: string | null;
  version: string | null;
  authenticated: boolean;
  authStatus: 'authenticated' | 'not_authenticated' | 'unknown';
  /** True when subscription cred exists OR the CLI binary is on PATH (third-party model setups). */
  readyForDelegation: boolean;
  loginStrategy: ExternalAgentLoginStrategy;
  scriptableLogin: boolean;
  needsCodeInput: boolean;
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

/** Whether this backend can be delegated to (subscription cred OR CLI on PATH). */
export function isExternalAgentDelegationReady(
  status: Pick<ExternalAgentAuthStatus, 'authenticated' | 'installed' | 'readyForDelegation'>,
): boolean {
  return Boolean(status.readyForDelegation || status.authenticated || status.installed);
}

export type ExternalAgentBadgeKind = 'subscription' | 'cli_ready' | 'logged_out';

export function resolveExternalAgentBadgeKind(
  status: Pick<ExternalAgentAuthStatus, 'authenticated' | 'installed' | 'readyForDelegation'>,
): ExternalAgentBadgeKind {
  if (status.authenticated) {
    return 'subscription';
  }
  if (isExternalAgentDelegationReady(status)) {
    return 'cli_ready';
  }
  return 'logged_out';
}

/**
 * Match a configured command to the server's status row for the same backend.
 *
 * Matches the executable basename exactly: the server only tracks its own known
 * binaries, so a derived name (`claude-bedrock`) or a wrapper is a different program it
 * cannot vouch for. Returns undefined for those, which callers treat as unknown.
 */
function resolveConfiguredBackendStatus(
  command: string,
  statuses: ReadonlyArray<ExternalAgentAuthStatus>,
): ExternalAgentAuthStatus | undefined {
  const executable = command
    .trim()
    .split(/[\\/]/)
    .pop()
    ?.toLowerCase()
    .replace(/\.[^.]+$/, '');
  if (!executable) {
    return undefined;
  }
  return statuses.find((row) => executable === row.backend.toLowerCase());
}

/**
 * Delegation readiness, split so the UI can tell "nothing configured" apart from
 * "configured but not installed" — two different problems needing two different fixes.
 */
export type ExternalCliReadiness = 'not_configured' | 'unavailable' | 'ready';

/** True when auth/status reports any backend ready for delegation (PATH auto-detect). */
export function hasAutoDetectedExternalCliBackend(statuses: ReadonlyArray<ExternalAgentAuthStatus>): boolean {
  return statuses.some((row) => isExternalAgentDelegationReady(row));
}

/**
 * Whether external CLI delegation can run, and if not, why.
 *
 * A bare command name is resolved through `PATH`, so the server's detection decides
 * whether it exists. A command the server does not track (a custom wrapper) or an
 * explicit path the user pinned is not something the server can confirm, so that
 * explicit configuration is trusted instead of reported as missing.
 */
export function resolveExternalCliReadiness(
  agents: ReadonlyArray<{ enabled?: boolean; command?: string }> | undefined,
  statuses: ReadonlyArray<ExternalAgentAuthStatus>,
  localMode: boolean,
): ExternalCliReadiness {
  const configured = (agents ?? [])
    .filter((agent) => agent.enabled !== false)
    .map((agent) => agent.command?.trim())
    .filter((command): command is string => Boolean(command));
  if (configured.length === 0) {
    return localMode && hasAutoDetectedExternalCliBackend(statuses) ? 'ready' : 'not_configured';
  }
  const resolvable = configured.some((command) => {
    if (/[\\/]/.test(command)) {
      // An explicit path is user-pinned; PATH-based detection says nothing about it.
      return true;
    }
    const status = resolveConfiguredBackendStatus(command, statuses);
    return status ? isExternalAgentDelegationReady(status) : true;
  });
  return resolvable ? 'ready' : 'unavailable';
}

export async function* streamExternalAgentInstall(
  backend: string,
): AsyncGenerator<ExternalAgentAuthEvent, void, unknown> {
  const response = await fetchWithTimeout(
    `/external-agents/install/${backend}`,
    {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
      },
    },
    300000, // 5 minutes for installation
  );

  if (!response.body) {
    throw new Error('No response body');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            return;
          }
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
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

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
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const dataLine = frame.split('\n').find((line) => line.startsWith('data:'));
        if (!dataLine) {
          continue;
        }
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
