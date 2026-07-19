import { create } from 'zustand';

export interface ApprovalToolCall {
  name: string;
  args: Record<string, unknown>;
}

export interface PlanItem {
  id: string;
  content: string;
  status?: string;
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
  tool_input?: Record<string, unknown>;
  element?: Record<string, unknown>;
  page_url?: string;
  reason?: string;
  action_type?: string;
  plan_items?: PlanItem[];
  total_items?: number;
  goal?: string;
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

function syncBrowserTakeoverFromApproval(approval: ApprovalPayload): void {
  if (approval.action_type !== 'browser_takeover') {
    return;
  }
  const nested = approval.payload ?? {};
  const nestedRecord = nested as Record<string, unknown>;
  const isManaged = nestedRecord.is_managed === true;
  const reason = approval.reason ?? nested.reason ?? '';
  const urlValue = nested.page_url ?? nestedRecord.url;
  const screenshot = nestedRecord.screenshot_base64;

  void Promise.all([
    import('@/store/useBrowserTakeoverStore'),
    import('@/store/useChatStore'),
  ]).then(([takeoverMod, chatMod]) => {
    const messages = chatMod.default.getState().messages;
    const lastAssistant = [...messages].reverse().find((message) => message.role === 'assistant');
    const messageId = lastAssistant?.messageId ?? '';
    takeoverMod.default.getState().requestTakeover({
      reason: String(reason),
      url: typeof urlValue === 'string' ? urlValue : undefined,
      screenshot_base64: typeof screenshot === 'string' ? screenshot : undefined,
      messageId,
      ui_mode: isManaged ? 'managed' : 'extension',
      auto_detect_completion: false,
    });
  });
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
  const nestedPayload = asRecord(raw.payload);
  const toolInput = asRecord(raw.tool_input ?? nestedPayload.tool_input);
  const element = asRecord(raw.element ?? nestedPayload.element);
  const pageUrl = asString(raw.page_url ?? nestedPayload.page_url);
  const payloadToolName = asString(raw.tool_name ?? nestedPayload.tool_name);
  const payloadReason = asString(raw.reason ?? nestedPayload.reason);

  return {
    approval_id: asString(raw.approval_id) || asString(raw.id),
    user_id: asString(raw.user_id),
    action_type: asString(raw.action_type, 'unknown'),
    status: asString(raw.status, 'PENDING'),
    severity: asString(raw.severity, 'warning'),
    reason: asString(raw.reason) || payloadReason || undefined,
    payload: {
      content: asString(nestedPayload.content) || undefined,
      patch_content: asString(nestedPayload.patch_content) || undefined,
      original_content: asString(nestedPayload.original_content) || undefined,
      tool_calls: normalizeToolCalls(nestedPayload.tool_calls ?? raw.tool_calls),
      artifact_id: asString(nestedPayload.artifact_id) || undefined,
      artifact_name: asString(nestedPayload.artifact_name) || undefined,
      message: asString(nestedPayload.message) || undefined,
      tool_name: payloadToolName || undefined,
      tool_input: Object.keys(toolInput).length > 0 ? toolInput : undefined,
      element: Object.keys(element).length > 0 ? element : undefined,
      page_url: pageUrl || undefined,
      reason: payloadReason || undefined,
      action_type: asString(nestedPayload.action_type ?? raw.action_type) || undefined,
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

  openApproval: (approval) => {
    syncBrowserTakeoverFromApproval(approval);
    set((state) => {
      if (state.queue.find((a) => a.approval_id === approval.approval_id)) {
        return state;
      }
      return { isOpen: true, queue: [...state.queue, approval] };
    });
  },
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
