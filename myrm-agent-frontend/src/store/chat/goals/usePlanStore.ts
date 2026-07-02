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
  updateStepStatus: (stepId: string, status: PlanStep['status']) => void;
  fetchPlan: (chatId: string) => Promise<void>;
}

export const usePlanStore = create<PlanStore>((set) => ({
  plan: null,
  isLoading: false,
  setPlan: (plan) => set({ plan }),
  updateStepStatus: (stepId, status) =>
    set((state) => {
      if (!state.plan) return state;
      const steps = state.plan.steps.map((step) => (step.step_id === stepId ? { ...step, status } : step));
      return { plan: { ...state.plan, steps } };
    }),
  fetchPlan: async (chatId: string) => {
    set({ isLoading: true });
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/plan`);
      if (res.ok) {
        const data = await res.json();
        if (data.plan) {
          set({ plan: data.plan });
        } else {
          set({ plan: null });
        }
      }
    } catch (error) {
      console.error('Failed to fetch goal progress:', error);
    } finally {
      set({ isLoading: false });
    }
  },
}));
