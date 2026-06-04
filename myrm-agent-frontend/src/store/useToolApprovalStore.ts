import { create } from 'zustand';
import type { ToolApprovalRequest } from '@/store/chat/types';

type BatchDecisionType = 'approve' | 'edit' | 'reject';

export interface BatchApprovalDecision {
  type: BatchDecisionType;
  extra?: {
    edited_args?: Record<string, unknown>;
    feedback?: string;
    allow_always?: boolean | { tool?: boolean; args?: boolean };
    allow_domain?: boolean;
  };
}

interface ToolApprovalState {
  queue: ToolApprovalRequest[];
  processingMessageIds: Set<string>;
  isResolving: boolean;
  batchDecisions: Map<string, BatchApprovalDecision>;

  addRequest: (request: ToolApprovalRequest) => void;
  removeRequest: (requestId: string) => void;
  removeRequestsByMessageId: (messageId: string) => void;
  clearAll: () => void;
  setResolving: (isResolving: boolean) => void;
  setBatchDecision: (requestId: string, decision: BatchApprovalDecision) => void;
  clearBatchDecisions: () => void;

  markProcessing: (messageId: string) => void;
  unmarkProcessing: (messageId: string) => void;
  isProcessing: (messageId: string) => boolean;
}

const useToolApprovalStore = create<ToolApprovalState>((set, get) => ({
  queue: [],
  processingMessageIds: new Set(),
  isResolving: false,
  batchDecisions: new Map(),

  addRequest: (request) => set((state) => ({ queue: [...state.queue, request] })),

  removeRequest: (requestId) =>
    set((state) => ({
      queue: state.queue.filter((r) => r.requestId !== requestId),
    })),

  removeRequestsByMessageId: (messageId) =>
    set((state) => {
      const newSet = new Set(state.processingMessageIds);
      newSet.delete(messageId);
      return {
        queue: state.queue.filter((r) => r.messageId !== messageId),
        processingMessageIds: newSet,
      };
    }),

  clearAll: () =>
    set({
      queue: [],
      processingMessageIds: new Set(),
      isResolving: false,
      batchDecisions: new Map(),
    }),

  setResolving: (isResolving) => set({ isResolving }),
  setBatchDecision: (requestId, decision) =>
    set((state) => {
      const next = new Map(state.batchDecisions);
      next.set(requestId, decision);
      return { batchDecisions: next };
    }),
  clearBatchDecisions: () => set({ batchDecisions: new Map() }),

  markProcessing: (messageId) =>
    set((state) => {
      const newSet = new Set(state.processingMessageIds);
      newSet.add(messageId);
      return { processingMessageIds: newSet };
    }),

  unmarkProcessing: (messageId) =>
    set((state) => {
      const newSet = new Set(state.processingMessageIds);
      newSet.delete(messageId);
      return { processingMessageIds: newSet };
    }),

  isProcessing: (messageId) => get().processingMessageIds.has(messageId),
}));

export default useToolApprovalStore;
