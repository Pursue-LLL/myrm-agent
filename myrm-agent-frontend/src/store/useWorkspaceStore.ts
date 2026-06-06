import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { ActiveSession, ActiveSessionsResponse } from '@/services/agent';
import { getActiveSessions } from '@/services/agent';
import type { ChatState } from './chat/types';

export interface PaneConfig {
  id: string;
  chatId: string | null;
  title: string;
  snapshot: Partial<ChatState> | null;
  abortController: AbortController | null;
  currentSessionMessageId: string | null;
}

interface WorkspaceState {
  panes: PaneConfig[];
  activePaneId: string | null;
  activeSessions: ActiveSession[];
  maxConcurrent: number;
  availableSlots: number;
  isPolling: boolean;

  addPane: (chatId?: string, title?: string) => string;
  removePane: (paneId: string) => void;
  setActivePaneId: (paneId: string) => void;
  updatePaneChatId: (paneId: string, chatId: string) => void;
  savePaneSnapshot: (paneId: string, snapshot: Partial<ChatState>) => void;
  getPaneSnapshot: (paneId: string) => Partial<ChatState> | null;
  refreshActiveSessions: () => Promise<void>;
  syncBackgroundPanes: () => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
}

let sseListener: (() => void) | null = null;
let sseTimeoutId: NodeJS.Timeout | null = null;

const useWorkspaceStore = create<WorkspaceState>()(
  immer((set, get) => ({
    panes: [],
    activePaneId: null,
    activeSessions: [],
    maxConcurrent: 3,
    availableSlots: 3,
    isPolling: false,

    addPane: (chatId?: string, title?: string) => {
      const id = `pane-${Date.now()}`;
      set((state) => {
        state.panes.push({
          id,
          chatId: chatId ?? null,
          title: title ?? `Pane ${state.panes.length + 1}`,
          snapshot: null,
        });
        state.activePaneId = id;
      });
      return id;
    },

    removePane: (paneId: string) => {
      set((state) => {
        state.panes = state.panes.filter((p) => p.id !== paneId);
        if (state.activePaneId === paneId) {
          state.activePaneId = state.panes[0]?.id ?? null;
        }
      });
    },

    setActivePaneId: (paneId: string) => {
      set((state) => {
        state.activePaneId = paneId;
      });
    },

    updatePaneChatId: (paneId: string, chatId: string) => {
      set((state) => {
        const pane = state.panes.find((p) => p.id === paneId);
        if (pane) pane.chatId = chatId;
      });
    },

    savePaneSnapshot: (paneId: string, snapshot: Partial<ChatState>) => {
      set((state) => {
        const pane = state.panes.find((p) => p.id === paneId);
        if (pane) {
          // Deep merge snapshot to avoid reference issues
          pane.snapshot = JSON.parse(JSON.stringify(snapshot));
        }
      });
    },

    getPaneSnapshot: (paneId: string) => {
      const pane = get().panes.find((p) => p.id === paneId);
      return pane?.snapshot ?? null;
    },

    refreshActiveSessions: async () => {
      try {
        const data: ActiveSessionsResponse = await getActiveSessions();
        set((state) => {
          state.activeSessions = data.activeSessions;
          state.maxConcurrent = data.maxConcurrent;
          state.availableSlots = data.availableSlots;
        });
      } catch {
        // Silently ignore polling errors
      }
    },

    syncBackgroundPanes: async () => {
      const state = get();
      const backgroundPanes = state.panes.filter(
        (p) => p.id !== state.activePaneId && p.chatId
      );

      if (backgroundPanes.length === 0) return;

      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const { getBackendUrl } = await import('@/lib/utils/apiConfig');
      const API_BASE_URL = getBackendUrl();

      for (const pane of backgroundPanes) {
        try {
          const response = await fetch(`${API_BASE_URL}/agents/chat/${pane.chatId}/attach?multiplexed=true`, {
            method: 'GET',
            headers,
            cache: 'no-store',
          });

          if (response.ok) {
            const data = await response.json();
            if (data.data?.catchup_snapshot) {
              get().savePaneSnapshot(pane.id, data.data.catchup_snapshot);
            }
          }
        } catch (error) {
          console.error(`Failed to sync background pane ${pane.id}`, error);
        }
      }
    },

    startPolling: () => {
      if (sseListener) return;
      set((state) => {
        state.isPolling = true;
      });
      get().refreshActiveSessions();
      sseListener = () => {
        if (sseTimeoutId) clearTimeout(sseTimeoutId);
        sseTimeoutId = setTimeout(() => {
          get().refreshActiveSessions();
        }, 1000);
      };
      window.addEventListener('subagents_updated', sseListener);
      window.addEventListener('app_resync_required', sseListener);
    },

    stopPolling: () => {
      if (sseListener) {
        window.removeEventListener('subagents_updated', sseListener);
        window.removeEventListener('app_resync_required', sseListener);
        sseListener = null;
      }
      if (sseTimeoutId) {
        clearTimeout(sseTimeoutId);
        sseTimeoutId = null;
      }
      set((state) => {
        state.isPolling = false;
      });
    },
  })),
);

// Listen to multiplex reconnect events to sync background panes
if (typeof window !== 'undefined') {
  window.addEventListener('multiplex_reconnected', () => {
    useWorkspaceStore.getState().syncBackgroundPanes();
  });
}

export default useWorkspaceStore;
