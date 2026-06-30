import { create } from 'zustand';

export interface ApprovalToolCall {
  name: string;
  args: Record<string, unknown>;
}

export interface ApprovalPayloadData {
  content?: string;
  patch_content?: string;
  original_content?: string;
  tool_name?: string;
  tool_calls?: ApprovalToolCall[];
  artifact_id?: string;
  artifact_name?: string;
  message?: string;
}

export interface ApprovalPayload {
  approval_id: string;
  user_id: string;
  action_type: string;
  status: string;
  severity: string;
  reason?: string;
  payload?: ApprovalPayloadData;
  chat_id?: string;
  expires_at?: string;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function normalizeToolCalls(value: unknown): ApprovalToolCall[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.map((item) => {
    const call = asRecord(item);
    return {
      name: asString(call.name, 'unknown'),
      args: asRecord(call.args),
    };
  });
}

export function normalizeApprovalPayload(raw: Record<string, unknown>): ApprovalPayload {
  const payload = asRecord(raw.payload);

  return {
    approval_id: asString(raw.approval_id) || asString(raw.id),
    user_id: asString(raw.user_id),
    action_type: asString(raw.action_type, 'unknown'),
    status: asString(raw.status, 'PENDING'),
    severity: asString(raw.severity, 'warning'),
    reason: asString(raw.reason) || undefined,
    payload: {
      content: asString(payload.content) || undefined,
      patch_content: asString(payload.patch_content) || undefined,
      original_content: asString(payload.original_content) || undefined,
      tool_calls: normalizeToolCalls(payload.tool_calls),
      artifact_id: asString(payload.artifact_id) || undefined,
      artifact_name: asString(payload.artifact_name) || undefined,
      message: asString(payload.message) || undefined,
    },
    chat_id: asString(raw.chat_id) || undefined,
    expires_at: asString(raw.expires_at) || undefined,
  };
}

interface ApprovalState {
  isOpen: boolean;
  queue: ApprovalPayload[];
  openApproval: (approval: ApprovalPayload) => void;
  closeApproval: (approvalId?: string) => void;
  closeApprovals: (approvalIds: string[]) => void;
  clearQueue: () => void;
  hideDrawer: () => void;
  showDrawer: () => void;
}

const useApprovalStore = create<ApprovalState>((set) => ({
  isOpen: false,
  queue: [],

  openApproval: (approval) =>
    set((state) => {
      if (state.queue.find((a) => a.approval_id === approval.approval_id)) {
        return state;
      }
      return { isOpen: true, queue: [...state.queue, approval] };
    }),
  closeApproval: (approvalId) =>
    set((state) => {
      if (!approvalId) {
        return { isOpen: false, queue: [] };
      }
      const newQueue = state.queue.filter((a) => a.approval_id !== approvalId);
      return { queue: newQueue, isOpen: newQueue.length > 0 };
    }),
  closeApprovals: (approvalIds) =>
    set((state) => {
      if (approvalIds.length === 0) return state;
      const removeSet = new Set(approvalIds);
      const newQueue = state.queue.filter((a) => !removeSet.has(a.approval_id));
      return { queue: newQueue, isOpen: newQueue.length > 0 };
    }),
  clearQueue: () => set({ isOpen: false, queue: [] }),
  hideDrawer: () => set({ isOpen: false }),
  showDrawer: () => set((state) => (state.queue.length > 0 ? { isOpen: true } : state)),
}));

export default useApprovalStore;
