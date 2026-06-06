import { fetchEventSource } from '@microsoft/fetch-event-source';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import useChatStore from '@/store/useChatStore';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

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

    fetchEventSource(`${API_BASE_URL}/workspace/stream`, {
      method: 'GET',
      headers,
      signal: this.abortController.signal,
      async onmessage(ev) {
        if (ev.event === 'multiplex') {
          try {
            const data = JSON.parse(ev.data);
            const { chat_id, message_id, raw_chunk } = data;
            
            // Dispatch the raw_chunk to the appropriate store
            ConnectionManager.getInstance().dispatchChunk(chat_id, message_id, raw_chunk);
          } catch (e) {
            console.error('Failed to parse multiplex event', e);
          }
        }
      },
      onerror(err) {
        console.error('Workspace stream error:', err);
        // Return undefined to let fetchEventSource retry automatically
      },
      onclose() {
        console.log('Workspace stream closed');
      }
    });
  }

  public disconnect() {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    this.isConnected = false;
  }

  private dispatchChunk(chatId: string | null, messageId: string, rawChunk: string) {
    if (!chatId) return;

    const workspaceState = useWorkspaceStore.getState();
    const activePane = workspaceState.panes.find(p => p.id === workspaceState.activePaneId);

    if (activePane && activePane.chatId === chatId) {
      // It's the active chat, we should ideally feed this to consumeStream.
      // But consumeStream expects a Response object.
      // To bridge this, we can emit a custom DOM event that consumeStream listens to,
      // OR we can just use a local EventTarget.
      window.dispatchEvent(new CustomEvent(`multiplex_chunk_${messageId}`, { detail: rawChunk }));
    } else {
      // It's a background chat. We need to update the snapshot.
      // For now, we just emit the event. If a background processor is listening, it will handle it.
      window.dispatchEvent(new CustomEvent(`multiplex_chunk_${messageId}`, { detail: rawChunk }));
    }
  }
}

export const connectionManager = ConnectionManager.getInstance();
