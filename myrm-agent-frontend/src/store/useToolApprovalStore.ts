import { create } from 'zustand';
import type { ToolApprovalRequest } from '@/store/chat/types';

interface ToolApprovalState {
  queue: ToolApprovalRequest[];
  // Set of messageIds that are currently being processed (either text approval sent or button clicked)
  // Used to prevent dual submission (text + button) or redundant text sends
  processingMessageIds: Set<string>;

  addRequest: (request: ToolApprovalRequest) => void;
  removeRequest: (requestId: string) => void;
  removeRequestsByMessageId: (messageId: string) => void;
  clearAll: () => void;

  // Mark a message as being processed (blocks text input)
  markProcessing: (messageId: string) => void;
  // Unmark a message (releases the block)
  unmarkProcessing: (messageId: string) => void;
  // Check if a message is currently being processed
  isProcessing: (messageId: string) => boolean;
}

const useToolApprovalStore = create<ToolApprovalState>((set, get) => ({
  queue: [],
  processingMessageIds: new Set(),

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

  clearAll: () => set({ queue: [], processingMessageIds: new Set() }),

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
