import { create } from 'zustand';
import {
  applyApprovalDecision,
  DEFAULT_APPROVAL_REQUESTS,
} from './executiveApprovalEngine';
import type {
  ApprovalDecision,
  ApprovalRequest,
  ApprovalRiskLevel,
  ApprovalStatus,
} from './executiveApprovalTypes';

export interface ExecutiveApprovalState {
  readonly requests: readonly ApprovalRequest[];
  readonly selectedRequestId: string | null;
  readonly filterRiskLevel: ApprovalRiskLevel | 'all';
  readonly filterStatus: ApprovalStatus | 'all';
  readonly isDeckOpen: boolean;

  submitApprovalRequest: (
    req: Omit<ApprovalRequest, 'id' | 'createdAt' | 'status'>
  ) => string;
  approveRequest: (id: string, feedbackComment?: string) => void;
  rejectRequest: (id: string, feedbackComment: string) => void;
  modifyAndApproveRequest: (
    id: string,
    modifiedContent: string,
    feedbackComment?: string
  ) => void;
  selectRequest: (id: string | null) => void;
  setRiskFilter: (level: ApprovalRiskLevel | 'all') => void;
  setStatusFilter: (status: ApprovalStatus | 'all') => void;
  toggleDeck: (open?: boolean) => void;
  resetStore: () => void;
}

export const useExecutiveApprovalStore = create<ExecutiveApprovalState>((set, get) => {
  return {
    requests: DEFAULT_APPROVAL_REQUESTS,
    selectedRequestId: DEFAULT_APPROVAL_REQUESTS[0]?.id ?? null,
    filterRiskLevel: 'all',
    filterStatus: 'pending',
    isDeckOpen: false,

    submitApprovalRequest: (req) => {
      const id = `req-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      const newRequest: ApprovalRequest = {
        ...req,
        id,
        createdAt: new Date().toISOString(),
        status: 'pending',
      };

      set((state) => {
        return {
          requests: [newRequest, ...state.requests],
          selectedRequestId: id,
        };
      });

      return id;
    },

    approveRequest: (id: string, feedbackComment?: string) => {
      const decision: ApprovalDecision = {
        decision: 'approve',
        feedbackComment,
      };

      set((state) => {
        const nextRequests = state.requests.map((item) => {
          if (item.id === id) {
            return applyApprovalDecision(item, decision);
          }
          return item;
        });
        return { requests: nextRequests };
      });
    },

    rejectRequest: (id: string, feedbackComment: string) => {
      const decision: ApprovalDecision = {
        decision: 'reject',
        feedbackComment,
      };

      set((state) => {
        const nextRequests = state.requests.map((item) => {
          if (item.id === id) {
            return applyApprovalDecision(item, decision);
          }
          return item;
        });
        return { requests: nextRequests };
      });
    },

    modifyAndApproveRequest: (
      id: string,
      modifiedContent: string,
      feedbackComment?: string
    ) => {
      const decision: ApprovalDecision = {
        decision: 'modify_and_approve',
        modifiedContent,
        feedbackComment,
      };

      set((state) => {
        const nextRequests = state.requests.map((item) => {
          if (item.id === id) {
            return applyApprovalDecision(item, decision);
          }
          return item;
        });
        return { requests: nextRequests };
      });
    },

    selectRequest: (id: string | null) => {
      set({ selectedRequestId: id });
    },

    setRiskFilter: (level: ApprovalRiskLevel | 'all') => {
      set({ filterRiskLevel: level });
    },

    setStatusFilter: (status: ApprovalStatus | 'all') => {
      set({ filterStatus: status });
    },

    toggleDeck: (open?: boolean) => {
      set((state) => {
        return {
          isDeckOpen: open !== undefined ? open : !state.isDeckOpen,
        };
      });
    },

    resetStore: () => {
      set({
        requests: DEFAULT_APPROVAL_REQUESTS,
        selectedRequestId: DEFAULT_APPROVAL_REQUESTS[0]?.id ?? null,
        filterRiskLevel: 'all',
        filterStatus: 'pending',
        isDeckOpen: false,
      });
    },
  };
});
