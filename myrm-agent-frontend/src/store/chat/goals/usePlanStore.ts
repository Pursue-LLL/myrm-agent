import { create } from 'zustand';
import { fetchWithTimeout } from '@/lib/api';

export type PlanStep = {
  step_id: string;
  description: string;
  expected_output: string;
  status: 'pending' | 'in_progress' | 'completed' | 'skipped';
  dependencies: string[];
};

export type Plan = {
  goal: string;
  reasoning: string;
  steps: PlanStep[];
  current_step_id?: string;
};

interface PlanStore {
  plan: Plan | null;
  isLoading: boolean;
  setPlan: (plan: Plan | null) => void;
  clearPlan: () => void;
  clearActivePlan: () => void;
  updateStepStatus: (stepId: string, status: PlanStep['status']) => void;
  fetchPlan: (chatId: string) => Promise<void>;
}

let _lastFetchId = 0;

export const usePlanStore = create<PlanStore>((set) => ({
  plan: null,
  isLoading: false,
  setPlan: (plan) => set({ plan }),
  clearPlan: () => set({ plan: null }),
  clearActivePlan: () =>
    set((state) => {
      if (!state.plan) return state;
      const hasActive = state.plan.steps.some((s) => s.status === 'pending' || s.status === 'in_progress');
      return hasActive ? { plan: null } : state;
    }),
  updateStepStatus: (stepId, status) =>
    set((state) => {
      if (!state.plan) return state;
      const steps = state.plan.steps.map((step) => (step.step_id === stepId ? { ...step, status } : step));
      return { plan: { ...state.plan, steps } };
    }),
  fetchPlan: async (chatId: string) => {
    const fetchId = ++_lastFetchId;
    set({ isLoading: true });
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/plan`);
      if (fetchId !== _lastFetchId) return;
      if (res.ok) {
        const data = await res.json();
        set({ plan: data.plan || null });
      }
    } catch (error) {
      if (fetchId !== _lastFetchId) return;
      console.error('Failed to fetch goal progress:', error);
    } finally {
      if (fetchId === _lastFetchId) {
        set({ isLoading: false });
      }
    }
  },
}));
