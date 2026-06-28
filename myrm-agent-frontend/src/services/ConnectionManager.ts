import { fetchEventSource } from '@microsoft/fetch-event-source';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import useChatStore from '@/store/useChatStore';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { apiRequest } from '@/lib/api';

interface ActiveSessionsResponse {
  activeSessions: Array<{ chatId: string; agentType: string }>;
}

class ConnectionManager {
  private static instance: ConnectionManager;
  private abortController: AbortController | null = null;
  private isConnected = false;

  private constructor() {}

  public static getInstance(): ConnectionManager {
    if (!ConnectionManager.instance) {
      ConnectionManager.instance = new ConnectionManager();
    }
    return ConnectionManager.instance;
  }

  public connect() {
    if (this.isConnected) return;
    this.isConnected = true;
    this.abortController = new AbortController();

    const API_BASE_URL = getBackendUrl();
    const token = localStorage.getItem('token');
    const headers = getAuthHeaders();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    let isFirstConnection = true;

    fetchEventSource(`${API_BASE_URL}/workspace/stream`, {
      method: 'GET',
      headers,
      signal: this.abortController.signal,
      async onopen(response) {
        if (response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
          ConnectionManager.getInstance().fetchActiveSessionsSnapshot();
          if (!isFirstConnection) {
            window.dispatchEvent(new CustomEvent('multiplex_reconnected'));
          }
          isFirstConnection = false;
        } else {
          throw new Error(`Failed to connect to workspace stream: ${response.statusText}`);
        }
      },
      async onmessage(ev) {
        if (ev.event === 'multiplex') {
          try {
            const data = JSON.parse(ev.data);
            const { chat_id, message_id, raw_chunk } = data;
            ConnectionManager.getInstance().dispatchChunk(chat_id, message_id, raw_chunk);
          } catch (e) {
            console.error('Failed to parse multiplex event', e);
          }
        } else if (ev.event === 'session_status') {
          try {
            const { chat_id, status } = JSON.parse(ev.data) as { chat_id: string; status: string };
            useChatStore.getState().setSessionStatus(chat_id, status);
          } catch (e) {
            console.error('Failed to parse session_status event', e);
          }
        }
      },
      onerror(err) {
        console.error('Workspace stream error:', err);
      },
      onclose() {
        console.log('Workspace stream closed');
      },
    });
  }

  public disconnect() {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    this.isConnected = false;
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

  private dispatchChunk(chatId: string | null, messageId: string, rawChunk: string) {
    if (!chatId) return;

    const workspaceState = useWorkspaceStore.getState();
    const activePane = workspaceState.panes.find((p) => p.id === workspaceState.activePaneId);

    if (activePane && activePane.chatId === chatId) {
      window.dispatchEvent(new CustomEvent(`multiplex_chunk_${messageId}`, { detail: rawChunk }));
    } else {
      window.dispatchEvent(new CustomEvent(`multiplex_chunk_${messageId}`, { detail: rawChunk }));
    }
  }
}

export const connectionManager = ConnectionManager.getInstance();
