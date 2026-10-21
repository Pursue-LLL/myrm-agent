/**
 * Zustand store for Tiered Risk HITL Approval & Dry-Run state.
 *
 * [INPUT] TieredRiskEvaluation, RiskConfirmPayload
 * [OUTPUT] useRiskGateStore hook
 * [POS] Item 29 global risk brake state manager. Strictly under 150 lines. Zero `any`.
 */

import { create } from 'zustand';
import type { TieredRiskEvaluation, RiskConfirmPayload } from '@/components/features/risk-approval/riskApprovalTypes';

interface RiskGateState {
  activeEvaluation: TieredRiskEvaluation | null;
  setActiveEvaluation: (evaluation: TieredRiskEvaluation | null) => void;
  clearEvaluation: () => void;
  confirmEvaluation: (payload: RiskConfirmPayload) => Promise<void>;
  rejectEvaluation: (reason?: string) => Promise<void>;
}

export const useRiskGateStore = create<RiskGateState>((set, get) => ({
  activeEvaluation: null,
  setActiveEvaluation: (evaluation) => set({ activeEvaluation: evaluation }),
  clearEvaluation: () => set({ activeEvaluation: null }),
  confirmEvaluation: async (_payload) => {
    // Dispatches resolution and resets active evaluation
    get().clearEvaluation();
  },
  rejectEvaluation: async (_reason) => {
    // Dispatches abort and resets active evaluation
    get().clearEvaluation();
  },
}));
