import { create } from 'zustand';
import { GoalState, GoalStatus } from '@/components/features/chat-window/goals/GoalStatusCard';
import { fetchWithTimeout } from '@/lib/api';

export interface QueuedGoal {
  goal_id: string;
  objective: string;
  priority: number;
  status: string;
  created_at?: string;
}

interface GoalStore {
  activeGoal: GoalState | null;
  gitBranch: string | null;
  queuedGoals: QueuedGoal[];
  setActiveGoal: (goal: GoalState | null) => void;
  updateGoalStatus: (status: GoalStatus) => void;
  updateGoalBudget: (chatId: string, additionalTokens: number) => Promise<void>;
  updateObjective: (chatId: string, newObjective: string) => Promise<void>;
  setGitBranch: (branch: string | null) => void;
  fetchQueue: (chatId: string) => Promise<void>;
  cancelQueuedGoal: (chatId: string, goalId: string) => Promise<void>;
  reorderQueue: (chatId: string, orderedIds: string[]) => Promise<void>;
}

export const useGoalStore = create<GoalStore>((set) => ({
  activeGoal: null,
  gitBranch: null,
  queuedGoals: [],
  setGitBranch: (branch) => set({ gitBranch: branch }),
  setActiveGoal: (goal) => set({ activeGoal: goal }),
  updateGoalStatus: (status) =>
    set((state) => ({
      activeGoal: state.activeGoal ? { ...state.activeGoal, status } : null,
    })),
  fetchQueue: async (chatId) => {
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/queue`);
      if (!res.ok) return;
      const data = await res.json();
      set({ queuedGoals: data.queue || [] });
    } catch {
      // Silently fail — queue is non-critical UI
    }
  },
  cancelQueuedGoal: async (chatId, goalId) => {
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/queue/${goalId}`, {
        method: 'DELETE',
      });
      if (!res.ok) return;
      set((state) => ({
        queuedGoals: state.queuedGoals.filter((g) => g.goal_id !== goalId),
      }));
    } catch {
      // Silently fail
    }
  },
  reorderQueue: async (chatId, orderedIds) => {
    try {
      await fetchWithTimeout(`/goals/${chatId}/queue/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ordered_goal_ids: orderedIds }),
      });
    } catch {
      // Silently fail
    }
  },
  updateObjective: async (chatId, newObjective) => {
    const res = await fetchWithTimeout(`/goals/${chatId}/objective`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objective: newObjective }),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Failed to update objective: ${text}`);
    }
    set((state) => {
      if (!state.activeGoal) return state;
      return { activeGoal: { ...state.activeGoal, objective: newObjective } };
    });
  },
  updateGoalBudget: async (chatId, additionalTokens) => {
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/budget`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ additionalTokens: additionalTokens }),
      });
      if (!res.ok) {
        console.error('Failed to update goal budget:', await res.text());
        throw new Error('Failed to update budget');
      }
      const data = await res.json();
      set((state) => {
        if (!state.activeGoal) return state;
        return {
          activeGoal: {
            ...state.activeGoal,
            budget: data.new_budget
              ? {
                  maxTokens: data.new_budget.max_tokens,
                  maxUsd: data.new_budget.max_usd,
                  maxTimeSeconds: data.new_budget.max_time_seconds,
                  maxTurns: data.new_budget.max_turns,
                  convergenceWindow: data.new_budget.convergence_window,
                  loopOnPause: data.new_budget.loop_on_pause,
                  maxLoopRestarts: data.new_budget.max_loop_restarts,
                }
              : state.activeGoal.budget,
          },
        };
      });
      console.log(`Successfully updated budget for ${chatId} with ${additionalTokens} tokens`);
    } catch (e) {
      console.error(`Network error: failed to update budget`, e);
      throw e;
    }
  },
}));
