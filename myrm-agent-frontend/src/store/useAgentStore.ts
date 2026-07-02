import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import {
  Agent,
  AgentListItem,
  AgentCreate,
  AgentUpdate,
  listAgents,
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
  pagination: {
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
    hasNext: boolean;
    hasPrev: boolean;
  } | null;

  // Actions
  fetchAgents: (page?: number, pageSize?: number, forceRefresh?: boolean) => Promise<void>;
  fetchAgent: (agentId: string) => Promise<Agent | null>;
  create: (data: AgentCreate) => Promise<Agent | null>;
  update: (agentId: string, data: AgentUpdate) => Promise<Agent | null>;
  remove: (agentId: string) => Promise<boolean>;
  setSelectedAgent: (agent: Agent | null) => void;
  clearError: () => void;
}

const useAgentStore = create<AgentState>()(
  immer((set, get) => ({
    agents: [],
    selectedAgent: null,
    loading: false,
    error: null,
    pagination: null,

    fetchAgents: async (page = 1, pageSize = 20, forceRefresh = false) => {
      const { loading, agents } = get();
      // Skip duplicate fetches unless caller forces refresh (gallery needs page_size=50 for 24 presets).
      if (!forceRefresh && (loading || agents.length > 0)) {
        return;
      }
      set({ loading: true, error: null });
      try {
        const response = await listAgents(page, pageSize);
        set({
          agents: response.items,
          pagination: {
            page: response.pagination.page,
            pageSize: response.pagination.page_size,
            total: response.pagination.total,
            totalPages: response.pagination.total_pages,
            hasNext: response.pagination.has_next,
            hasPrev: response.pagination.has_prev,
          },
          loading: false,
        });
      } catch (error) {
        set({
          error: error instanceof Error ? error.message : 'Failed to fetch agents',
          loading: false,
        });
      }
    },

    fetchAgent: async (agentId: string) => {
      set({ loading: true, error: null });
      try {
        const agent = await getAgent(agentId);
        set({ selectedAgent: agent, loading: false });
        return agent;
      } catch (error) {
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
