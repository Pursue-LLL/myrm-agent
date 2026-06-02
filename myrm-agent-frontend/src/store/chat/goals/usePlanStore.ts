import { create } from 'zustand';
import { fetchWithTimeout } from '@/lib/api';

export type PlanStep = {
  step_id: string;
  description: string;
  expected_output: string;
  status: 'pending' | 'in_progress' | 'completed' | 'skipped';
  dependencies: string[];
};

export type DecisionRecord = {
  id: string;
  topic: string;
  decision: string;
  rationale: string;
  status: 'active' | 'superseded' | 'deprecated';
  timestamp?: string;
};

export type Plan = {
  goal: string;
  reasoning: string;
  steps: PlanStep[];
  current_step_id?: string;
  key_findings?: string[];
  decisions?: DecisionRecord[];
  pending_issues?: string[];
};

interface PlanStore {
  plan: Plan | null;
  isApproved: boolean;
  isLoading: boolean;
  setPlan: (plan: Plan | null) => void;
  setApproved: (approved: boolean) => void;
  updateStepStatus: (stepId: string, status: PlanStep['status']) => void;
  fetchPlan: (chatId: string) => Promise<void>;
  approvePlan: (chatId: string) => Promise<boolean>;
}

export const usePlanStore = create<PlanStore>((set) => ({
  plan: null,
  isApproved: false,
  isLoading: false,
  setPlan: (plan) => set({ plan }),
  setApproved: (approved) => set({ isApproved: approved }),
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
        }
      }
    } catch (e) {
      console.error('Failed to fetch plan:', e);
    } finally {
      set({ isLoading: false });
    }
  },
  approvePlan: async (chatId: string) => {
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/approve_plan`, {
        method: 'POST',
      });
      if (res.ok) {
        set({ isApproved: true });
        return true;
      }
      return false;
    } catch (e) {
      console.error('Failed to approve plan:', e);
      return false;
    }
  },
}));
