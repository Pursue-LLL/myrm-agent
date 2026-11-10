import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import {
  Agent,
  AgentListItem,
  AgentCreate,
  AgentUpdate,
  listAllAgents,
  createAgent,
  updateAgent,
  deleteAgent,
  getAgent,
} from '@/services/agent';

interface AgentState {
  agents: AgentListItem[];
  selectedAgent: Agent | null;
  loading: boolean;
  error: string | null;

  // Actions
  /** Loads the whole roster; without `forceRefresh` it is skipped while a load runs or the roster is already there. */
  fetchAgents: (forceRefresh?: boolean) => Promise<void>;
  fetchAgent: (agentId: string, signal?: AbortSignal) => Promise<Agent | null>;
  create: (data: AgentCreate) => Promise<Agent | null>;
  update: (agentId: string, data: AgentUpdate) => Promise<Agent | null>;
  remove: (agentId: string) => Promise<boolean>;
  setSelectedAgent: (agent: Agent | null) => void;
  clearError: () => void;
}

// Roster reads overlap (events, gallery mount) and can finish out of order. A read only counts when it started after
// the one already applied, so a slow old read never brings back an outdated roster.
let latestRosterRequest = 0;
let appliedRosterRequest = 0;

const useAgentStore = create<AgentState>()(
  immer((set, get) => ({
    agents: [],
    selectedAgent: null,
    loading: false,
    error: null,

    fetchAgents: async (forceRefresh = false) => {
      const { loading, agents } = get();
      if (!forceRefresh && (loading || agents.length > 0)) {
        return;
      }
      const request = ++latestRosterRequest;
      set({ loading: true, error: null });
      try {
        const roster = await listAllAgents();
        if (request > appliedRosterRequest) {
          appliedRosterRequest = request;
          set({ agents: roster, loading: false, error: null });
        }
      } catch (error) {
        if (request > appliedRosterRequest) {
          set({
            error: error instanceof Error ? error.message : 'Failed to fetch agents',
            loading: false,
          });
        }
      }
    },

    fetchAgent: async (agentId: string, signal?: AbortSignal) => {
      set({ loading: true, error: null });
      try {
        const agent = await getAgent(agentId, false, signal);
        set({ selectedAgent: agent, loading: false });
        return agent;
      } catch (error) {
        if (signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')) {
          set({ loading: false });
          return null;
        }
        set({
          error: error instanceof Error ? error.message : 'Failed to fetch agent',
          loading: false,
        });
        return null;
      }
    },

    create: async (data: AgentCreate) => {
      set({ loading: true, error: null });
      try {
        const newAgent = await createAgent(data);
        // 转换为 AgentListItem 以便添加到列表
        const listItem: AgentListItem = {
          id: newAgent.id,
          name: newAgent.name,
          description: newAgent.description,
          avatar_url: newAgent.avatar_url,
          created_at: newAgent.created_at,
          updated_at: newAgent.updated_at,
        };
        set((state) => {
          state.agents.unshift(listItem);
          state.loading = false;
        });
        return newAgent;
      } catch (error) {
        set({
          error: error instanceof Error ? error.message : 'Failed to create agent',
          loading: false,
        });
        return null;
      }
    },

    update: async (agentId: string, data: AgentUpdate) => {
      set({ loading: true, error: null });
      try {
        const updatedAgent = await updateAgent(agentId, data);
        // 转换为 AgentListItem 以便更新列表
        const listItem: AgentListItem = {
          id: updatedAgent.id,
          name: updatedAgent.name,
          description: updatedAgent.description,
          avatar_url: updatedAgent.avatar_url,
          created_at: updatedAgent.created_at,
          updated_at: updatedAgent.updated_at,
        };
        set((state) => {
          const index = state.agents.findIndex((a) => a.id === agentId);
          if (index !== -1) {
            state.agents[index] = listItem;
          }
          if (state.selectedAgent?.id === agentId) {
            state.selectedAgent = updatedAgent;
          }
          state.loading = false;
        });
        return updatedAgent;
      } catch (error) {
        set({
          error: error instanceof Error ? error.message : 'Failed to update agent',
          loading: false,
        });
        return null;
      }
    },

    remove: async (agentId: string) => {
      set({ loading: true, error: null });
      try {
        await deleteAgent(agentId);
        set((state) => {
          state.agents = state.agents.filter((a) => a.id !== agentId);
          if (state.selectedAgent?.id === agentId) {
            state.selectedAgent = null;
          }
          state.loading = false;
        });
        return true;
      } catch (error) {
        set({
          error: error instanceof Error ? error.message : 'Failed to delete agent',
          loading: false,
        });
        return false;
      }
    },

    setSelectedAgent: (agent) => set({ selectedAgent: agent }),
    clearError: () => set({ error: null }),
  })),
);

export default useAgentStore;
