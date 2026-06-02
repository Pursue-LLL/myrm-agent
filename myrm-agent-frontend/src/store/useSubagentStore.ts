import { create } from 'zustand';

export interface SubagentLog {
  id: string;
  timestamp: number;
  level: string;
  message: string;
  toolName?: string;
  durationMs?: number;
  error?: string;
}

export interface SubagentState {
  taskId: string;
  messageId: string;
  agentType: string;
  agentInstance: string;
  description: string;
  status: 'running' | 'completed' | 'error' | 'cancelled';
  progressPercent: number;
  currentStep: string;
  logs: SubagentLog[];
  etaReadable?: string;
  toolCount?: number;
  isEstimated?: boolean;
  result?: string;
  createdAt: number;
  lastUpdatedAt: number;
}

interface SubagentStoreState {
  // messageId -> taskIds
  messageSubagents: Record<string, string[]>;
  // taskId -> SubagentState
  subagents: Record<string, SubagentState>;

  // actions
  startSubagent: (messageId: string, payload: { task_id: string; agent_type: string; description: string }) => void;

  updateProgress: (payload: {
    task_id: string;
    progress: number;
    current_step?: string;
    eta_readable?: string;
    tool_count?: number;
    is_estimated?: boolean;
  }) => void;

  addLog: (payload: {
    task_id: string;
    level: string;
    message: string;
    tool_name?: string;
    duration_ms?: number;
    error?: string;
    agent_instance?: string;
  }) => void;

  completeSubagent: (taskId: string, result?: string) => void;
  errorSubagent: (taskId: string, error?: string) => void;
  cancelSubagent: (taskId: string, reason?: string) => void;

  clearMessageSubagents: (messageId: string) => void;
  getHotSubagentStates: (messageId: string) => SubagentState[];
}

const useSubagentStore = create<SubagentStoreState>((set, get) => ({
  messageSubagents: {},
  subagents: {},

  startSubagent: (messageId, { task_id, agent_type, description }) => {
    set((state) => {
      const existingTaskIds = state.messageSubagents[messageId] || [];
      const isNew = !existingTaskIds.includes(task_id);

      return {
        messageSubagents: {
          ...state.messageSubagents,
          [messageId]: isNew ? [...existingTaskIds, task_id] : existingTaskIds,
        },
        subagents: {
          ...state.subagents,
          [task_id]: {
            taskId: task_id,
            messageId,
            agentType: agent_type,
            agentInstance: `${agent_type}-${task_id.substring(0, 4)}`,
            description,
            status: 'running',
            progressPercent: 0,
            currentStep: 'Starting...',
            logs: [],
            createdAt: Date.now(),
            lastUpdatedAt: Date.now(),
          },
        },
      };
    });
  },

  updateProgress: ({ task_id, progress, current_step, eta_readable, tool_count, is_estimated }) => {
    set((state) => {
      const subagent = state.subagents[task_id];
      if (!subagent) return state;

      return {
        subagents: {
          ...state.subagents,
          [task_id]: {
            ...subagent,
            progressPercent: Math.round(progress * 100),
            currentStep: current_step || subagent.currentStep,
            etaReadable: eta_readable,
            toolCount: tool_count,
            isEstimated: is_estimated,
            lastUpdatedAt: Date.now(),
          },
        },
      };
    });
  },

  addLog: ({ task_id, level, message, tool_name, duration_ms, error, agent_instance }) => {
    set((state) => {
      const subagent = state.subagents[task_id];
      if (!subagent) return state;

      const newLog: SubagentLog = {
        id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
        timestamp: Date.now(),
        level,
        message,
        toolName: tool_name,
        durationMs: duration_ms,
        error,
      };

      // Keep the last 1000 logs to prevent memory leaks in extremely long tasks
      const MAX_LOGS = 1000;
      const updatedLogs = [...subagent.logs, newLog];
      if (updatedLogs.length > MAX_LOGS) {
        updatedLogs.splice(0, updatedLogs.length - MAX_LOGS);
      }

      return {
        subagents: {
          ...state.subagents,
          [task_id]: {
            ...subagent,
            logs: updatedLogs,
            agentInstance: agent_instance || subagent.agentInstance,
            lastUpdatedAt: Date.now(),
          },
        },
      };
    });
  },

  completeSubagent: (taskId, result) => {
    set((state) => {
      const subagent = state.subagents[taskId];
      if (!subagent) return state;

      return {
        subagents: {
          ...state.subagents,
          [taskId]: {
            ...subagent,
            status: 'completed',
            progressPercent: 100,
            currentStep: 'Completed',
            result,
            lastUpdatedAt: Date.now(),
          },
        },
      };
    });
  },

  errorSubagent: (taskId, error) => {
    set((state) => {
      const subagent = state.subagents[taskId];
      if (!subagent) return state;

      return {
        subagents: {
          ...state.subagents,
          [taskId]: {
            ...subagent,
            status: 'error',
            currentStep: 'Failed',
            error,
            lastUpdatedAt: Date.now(),
          },
        },
      };
    });
  },

  cancelSubagent: (taskId, reason) => {
    set((state) => {
      const subagent = state.subagents[taskId];
      if (!subagent) return state;

      return {
        subagents: {
          ...state.subagents,
          [taskId]: {
            ...subagent,
            status: 'cancelled',
            currentStep: reason === 'timeout' ? 'Timed out' : 'Cancelled',
            error: reason || 'Cancelled',
            lastUpdatedAt: Date.now(),
          },
        },
      };
    });
  },

  clearMessageSubagents: (messageId) => {
    set((state) => {
      const taskIds = state.messageSubagents[messageId];
      if (!taskIds || taskIds.length === 0) return state;

      const newMessageSubagents = { ...state.messageSubagents };
      delete newMessageSubagents[messageId];

      const newSubagents = { ...state.subagents };
      taskIds.forEach((id) => {
        delete newSubagents[id];
      });

      return {
        messageSubagents: newMessageSubagents,
        subagents: newSubagents,
      };
    });
  },

  getHotSubagentStates: (messageId) => {
    const state = get();
    const taskIds = state.messageSubagents[messageId] || [];
    return taskIds.map((id) => state.subagents[id]).filter(Boolean);
  },
}));

export default useSubagentStore;
