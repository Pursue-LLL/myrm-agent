import { create } from 'zustand';
import { fetchWithTimeout } from '@/lib/api';

export type PlanStep = {
  step_id: string;
  description: string;
  expected_output: string;
  status: 'pending' | 'in_progress' | 'completed' | 'skipped' | 'blocked';
  dependencies: string[];
};

export type Plan = {
  goal: string;
  reasoning: string;
  revision?: number;
  steps: PlanStep[];
  current_step_id?: string;
};

interface PlanStore {
  plan: Plan | null;
  isLoading: boolean;
  setPlan: (plan: Plan | null) => void;
  clearPlan: () => void;
  clearActivePlan: () => void;
  updateStepStatus: (
    stepId: string,
    status: PlanStep['status'],
    revision?: number,
    description?: string,
  ) => void;
  fetchPlan: (chatId: string) => Promise<void>;
}

let _lastFetchId = 0;

export const usePlanStore = create<PlanStore>((set) => ({
  plan: null,
  isLoading: false,
  setPlan: (plan) =>
    set((state) => {
      if (!plan) {
        return { plan: null };
      }
      if (
        state.plan?.revision !== undefined &&
        plan.revision !== undefined &&
        plan.revision < state.plan.revision
      ) {
        return state;
      }
      return { plan };
    }),
  clearPlan: () => set({ plan: null }),
  clearActivePlan: () =>
    set((state) => {
      if (!state.plan) {
        return state;
      }
      const hasActive = state.plan.steps.some((s) => s.status === 'pending' || s.status === 'in_progress');
      return hasActive ? { plan: null } : state;
    }),
  updateStepStatus: (stepId, status, revision, description) =>
    set((state) => {
      if (!state.plan) {
        return state;
      }
      if (
        revision !== undefined &&
        state.plan.revision !== undefined &&
        revision < state.plan.revision
      ) {
        return state;
      }

      let found = false;
      const steps = state.plan.steps.map((step) => {
        if (step.step_id === stepId) {
          found = true;
          return {
            ...step,
            status,
            description: description || step.description,
          };
        }
        return step;
      });

      const nextSteps = found
        ? steps
        : [
            ...steps,
            {
              step_id: stepId,
              description: description || '',
              expected_output: '',
              status,
              dependencies: [],
            },
          ];

      const nextRevision =
        revision !== undefined
          ? Math.max(state.plan.revision ?? 0, revision)
          : state.plan.revision;

      return {
        plan: {
          ...state.plan,
          revision: nextRevision,
          steps: nextSteps,
        },
      };
    }),
  fetchPlan: async (chatId: string) => {
    const fetchId = ++_lastFetchId;
    set({ isLoading: true });
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/plan`);
      if (fetchId !== _lastFetchId) {
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const incomingPlan: Plan | null = data.plan || null;
        set((state) => {
          if (!incomingPlan) {
            return { plan: null };
          }
          if (
            state.plan?.revision !== undefined &&
            incomingPlan.revision !== undefined &&
            incomingPlan.revision < state.plan.revision
          ) {
            return state;
          }
          return { plan: incomingPlan };
        });
      }
    } catch (error) {
      if (fetchId !== _lastFetchId) {
        return;
      }
      console.error('Failed to fetch goal progress:', error);
    } finally {
      if (fetchId === _lastFetchId) {
        set({ isLoading: false });
      }
    }
  },
}));
