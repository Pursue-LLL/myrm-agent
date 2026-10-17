import { create } from 'zustand';
import type { GoalState, GoalStatus } from '@/components/features/chat-window/goals/goalStatusTypes';
import { fetchWithTimeout } from '@/lib/api';
import { riskHeldErrorFromResponse } from '@/services/riskHeldToast';

export interface QueuedGoal {
  goal_id: string;
  objective: string;
  priority: number;
  status: string;
  created_at?: string;
}

/**
 * The goal of one chat: the chat it was last bound to. Every write names the chat it is about and is applied only
 * while that chat is still the bound one, so a stream event, a notification or a slow reply that belongs to another
 * chat never lands in the slot the open chat shows. A write whose source could not name its chat (an empty chat id)
 * belongs to no chat and is dropped.
 */
interface GoalStore {
  chatId: string | null;
  activeGoal: GoalState | null;
  gitBranch: string | null;
  queuedGoals: QueuedGoal[];
  /** Binds the slot to `chatId`; opening another chat empties it, binding the bound chat again keeps it. */
  bindChat: (chatId: string | null) => void;
  setActiveGoal: (chatId: string, goal: GoalState | null) => void;
  updateGoalStatus: (chatId: string, status: GoalStatus, reason?: string) => void;
  updateGoalBudget: (chatId: string, additionalTokens: number) => Promise<void>;
  updateObjective: (chatId: string, newObjective: string) => Promise<void>;
  refreshActiveGoal: (chatId: string) => Promise<void>;
  setGitBranch: (chatId: string, branch: string | null) => void;
  fetchQueue: (chatId: string) => Promise<void>;
  cancelQueuedGoal: (chatId: string, goalId: string) => Promise<void>;
  reorderQueue: (chatId: string, orderedIds: string[]) => Promise<void>;
}

const UNRANKED = Number.MAX_SAFE_INTEGER;

export const useGoalStore = create<GoalStore>((set, get) => {
  /**
   * Applies `patch` only while `chatId` is the bound chat. The bound chat is read when the patch is applied, not when
   * the request started, so a reply that comes back after the user opened another chat is dropped.
   */
  const applyForChat = (chatId: string, patch: (state: GoalStore) => Partial<GoalStore>): void =>
    set((state) => (state.chatId === chatId ? patch(state) : state));

  return {
    chatId: null,
    activeGoal: null,
    gitBranch: null,
    queuedGoals: [],
    bindChat: (chatId) =>
      set((state) =>
        state.chatId === chatId ? state : { chatId, activeGoal: null, gitBranch: null, queuedGoals: [] },
      ),
    setGitBranch: (chatId, branch) => applyForChat(chatId, () => ({ gitBranch: branch })),
    setActiveGoal: (chatId, goal) => applyForChat(chatId, () => ({ activeGoal: goal })),
    updateGoalStatus: (chatId, status, reason) =>
      applyForChat(chatId, (state) => ({
        activeGoal: state.activeGoal
          ? {
              ...state.activeGoal,
              status,
              ...(reason !== undefined ? { reason } : {}),
            }
          : null,
      })),
    fetchQueue: async (chatId) => {
      try {
        const res = await fetchWithTimeout(`/goals/${chatId}/queue`);
        if (!res.ok) {
          return;
        }
        const data = await res.json();
        applyForChat(chatId, () => ({ queuedGoals: data.queue || [] }));
      } catch {
        // Silently fail — queue is non-critical UI
      }
    },
    cancelQueuedGoal: async (chatId, goalId) => {
      try {
        const res = await fetchWithTimeout(`/goals/${chatId}/queue/${goalId}`, {
          method: 'DELETE',
        });
        if (!res.ok) {
          return;
        }
        applyForChat(chatId, (state) => ({ queuedGoals: state.queuedGoals.filter((g) => g.goal_id !== goalId) }));
      } catch {
        // Silently fail
      }
    },
    reorderQueue: async (chatId, orderedIds) => {
      const rank = new Map(orderedIds.map((id, index) => [id, index]));
      applyForChat(chatId, (state) => ({
        queuedGoals: [...state.queuedGoals].sort(
          (a, b) => (rank.get(a.goal_id) ?? UNRANKED) - (rank.get(b.goal_id) ?? UNRANKED),
        ),
      }));
      try {
        const res = await fetchWithTimeout(`/goals/${chatId}/queue/reorder`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ordered_goal_ids: orderedIds }),
        });
        if (res.ok) {
          return;
        }
      } catch {
        // Fall through: the server did not take the new order.
      }
      // The order shown optimistically is not the server's; show the server's again.
      await get().fetchQueue(chatId);
    },
    updateObjective: async (chatId, newObjective) => {
      const res = await fetchWithTimeout(`/goals/${chatId}/objective`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ objective: newObjective }),
      });
      if (!res.ok) {
        const riskHeld = await riskHeldErrorFromResponse(res);
        if (riskHeld) {
          throw riskHeld;
        }
        const text = await res.text();
        throw new Error(`Failed to update objective: ${text}`);
      }
      applyForChat(chatId, (state) =>
        state.activeGoal ? { activeGoal: { ...state.activeGoal, objective: newObjective } } : state,
      );
    },
    refreshActiveGoal: async (chatId) => {
      try {
        const res = await fetchWithTimeout(`/goals/${chatId}/status`);
        if (!res.ok) {
          return;
        }
        const data = (await res.json()) as { goal?: import('@/store/chat/types').GoalStatusPayload };
        if (!data.goal) {
          return;
        }
        const { normalizeGoalState } = await import('@/store/chat/messageStream/streamHelpers');
        const goal = normalizeGoalState(data.goal);
        applyForChat(chatId, () => ({ activeGoal: goal }));
      } catch {
        // Goal refresh is best-effort after background job finish
      }
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
        applyForChat(chatId, (state) => {
          if (!state.activeGoal) {
            return state;
          }
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
  };
});
