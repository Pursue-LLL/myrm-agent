import { fetchEventSource } from '@microsoft/fetch-event-source';
import useChatStore from '@/store/useChatStore';
import { getApiUrl, apiRequest } from '@/lib/api';
import { getApiBaseUrl, resolveE2eApiBase } from '@/lib/deploy-mode';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

interface ActiveSessionsResponse {
  activeSessions: Array<{ chatId: string; agentType: string }>;
}

declare global {
  interface Window {
    __MYRM_WAIT_WORKSPACE_STREAM__?: (timeoutMs?: number) => Promise<{ ok: boolean; origin?: string; err?: string }>;
    __MYRM_WORKSPACE_STREAM_STATUS__?: () => { connected: boolean; origin: string | null };
  }
}

class ConnectionManager {
  private static instance: ConnectionManager;
  private abortController: AbortController | null = null;
  private isConnected = false;
  private connectedOrigin: string | null = null;
  private readyResolve: (() => void) | null = null;
  private readyReject: ((error: Error) => void) | null = null;
  private readyPromise: Promise<void> = Promise.resolve();

  private constructor() {
    if (typeof window !== 'undefined') {
      window.__MYRM_WAIT_WORKSPACE_STREAM__ = (timeoutMs = 20_000) => this.waitUntilReady(timeoutMs);
      window.__MYRM_WORKSPACE_STREAM_STATUS__ = () => ({
        connected: this.isConnected,
        origin: this.connectedOrigin,
      });
    }
  }

  public static getInstance(): ConnectionManager {
    if (!ConnectionManager.instance) {
      ConnectionManager.instance = new ConnectionManager();
    }
    return ConnectionManager.instance;
  }

  private resetReadyPromise(): void {
    const readyPromise = new Promise<void>((resolve, reject) => {
      this.readyResolve = resolve;
      this.readyReject = reject;
    });
    // `connect()` may replace a pending connection before any caller has
    // entered waitUntilReady().  Mark the rejection as observed so a normal
    // reconnect does not become a browser-level unhandledRejection.
    void readyPromise.catch(() => undefined);
    this.readyPromise = readyPromise;
  }

  private resolveReady(): void {
    this.readyResolve?.();
    this.readyResolve = null;
    this.readyReject = null;
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('myrm_workspace_stream_ready'));
    }
  }

  private rejectReady(error: Error): void {
    this.readyReject?.(error);
    this.readyResolve = null;
    this.readyReject = null;
  }

  public async waitUntilReady(timeoutMs = 20_000): Promise<{ ok: boolean; origin?: string; err?: string }> {
    const origin = getApiBaseUrl().replace(/\/api\/v1\/?$/, '');
    if (this.isConnected && this.connectedOrigin === origin) {
      return { ok: true, origin };
    }
    this.connect();
    try {
      await Promise.race([
        this.readyPromise,
        new Promise<void>((_, reject) => {
          window.setTimeout(() => reject(new Error('workspace-stream-ready-timeout')), timeoutMs);
        }),
      ]);
      return { ok: true, origin: this.connectedOrigin ?? origin };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return { ok: false, origin, err: message };
    }
  }

  public connect() {
    const origin = getApiBaseUrl().replace(/\/api\/v1\/?$/, '');
    if (this.isConnected && this.connectedOrigin === origin) {
      return;
    }

    this.disconnect();
    this.isConnected = true;
    this.connectedOrigin = origin;
    this.resetReadyPromise();
    this.abortController = new AbortController();

    const headers = getAuthHeaders();
    let isFirstConnection = true;

    void fetchEventSource(getApiUrl('/workspace/stream'), {
      method: 'GET',
      headers,
      credentials: resolveE2eApiBase() ? 'omit' : 'include',
      signal: this.abortController.signal,
      openWhenHidden: true,
      async onopen(response) {
        if (response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
          ConnectionManager.getInstance().resolveReady();
          ConnectionManager.getInstance().fetchActiveSessionsSnapshot();
          if (!isFirstConnection) {
            window.dispatchEvent(new CustomEvent('myrm_workspace_stream_reconnected'));
          }
          isFirstConnection = false;
        } else {
          throw new Error(`Failed to connect to workspace stream: ${response.statusText}`);
        }
      },
      async onmessage(ev) {
        if (ev.event === 'session_status') {
          try {
            const { chat_id, status } = JSON.parse(ev.data) as { chat_id: string; status: string };
            useChatStore.getState().setSessionStatus(chat_id, status);
          } catch (e) {
            console.error('Failed to parse session_status event', e);
          }
        }
      },
      onerror(err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          return;
        }
        console.error('Workspace stream error:', err);
        const self = ConnectionManager.getInstance();
        self.isConnected = false;
        self.connectedOrigin = null;
        self.rejectReady(err instanceof Error ? err : new Error(String(err)));
      },
      onclose() {
        console.log('Workspace stream closed');
        const self = ConnectionManager.getInstance();
        self.isConnected = false;
        self.connectedOrigin = null;
      },
    });
  }

  public disconnect() {
    if (this.abortController) {
      this.abortController.abort('Workspace stream disconnected');
      this.abortController = null;
    }
    this.isConnected = false;
    this.connectedOrigin = null;
    this.rejectReady(new Error('workspace-stream-disconnected'));
    this.readyPromise = Promise.resolve();
  }

  private async fetchActiveSessionsSnapshot() {
    try {
      const data = (await apiRequest('/agents/active-sessions')) as ActiveSessionsResponse;
      const statuses: Record<string, string> = {};
      for (const session of data.activeSessions ?? []) {
        statuses[session.chatId] = 'generating';
      }
      useChatStore.getState().initSessionStatuses(statuses);
    } catch {
      // Non-critical; sidebar will show correct status on next SSE event
    }
  }
}

export const connectionManager = ConnectionManager.getInstance();
