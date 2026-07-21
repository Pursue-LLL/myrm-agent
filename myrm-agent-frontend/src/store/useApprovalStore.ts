import { create } from 'zustand';

import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useChatStore from '@/store/useChatStore';

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
  url?: string;
  screenshot_base64?: string;
  live_assist_url?: string;
  is_managed?: boolean;
  reason?: string;
  messageId?: string;
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

export interface BrowserTakeoverActivationInput {
  reason: string;
  url?: string;
  screenshot_base64?: string;
  live_assist_url?: string;
  messageId?: string;
  is_managed?: boolean;
  auto_detect_completion?: boolean;
  chat_id?: string;
}

function isActiveChatForTakeover(approvalChatId?: string): boolean {
  if (!approvalChatId) {
    return true;
  }
  const storeChatId = useChatStore.getState().chatId?.trim();
  if (storeChatId && storeChatId === approvalChatId) {
    return true;
  }
  if (typeof window !== 'undefined') {
    const pathChatId = window.location.pathname.split('/').filter(Boolean)[0]?.trim();
    if (pathChatId && pathChatId === approvalChatId) {
      return true;
    }
  }
  return !storeChatId;
}

export function activateBrowserTakeover(input: BrowserTakeoverActivationInput): void {
  if (input.chat_id && !isActiveChatForTakeover(input.chat_id)) {
    return;
  }
  const messageId = resolveBrowserTakeoverMessageId(input.messageId);
  const isManaged = input.is_managed === true;
  useBrowserTakeoverStore.getState().requestTakeover({
    reason: input.reason,
    url: input.url,
    screenshot_base64: input.screenshot_base64,
    live_assist_url: input.live_assist_url,
    messageId,
    ui_mode: isManaged ? 'managed' : 'extension',
    auto_detect_completion: input.auto_detect_completion ?? false,
  });
}

function syncBrowserTakeoverFromApproval(approval: ApprovalPayload): void {
  if (approval.action_type !== 'browser_takeover') {
    return;
  }
  const nested = approval.payload ?? {};
  const nestedRecord = nested as Record<string, unknown>;
  const isManaged = nested.is_managed === true || nestedRecord.is_managed === true;
  const reason = approval.reason ?? nested.reason ?? '';
  const urlValue = nested.url ?? nested.page_url ?? nestedRecord.url;
  const screenshot = nested.screenshot_base64 ?? nestedRecord.screenshot_base64;
  const liveAssistUrl = nested.live_assist_url ?? nestedRecord.live_assist_url;
  const payloadMessageId =
    typeof nestedRecord.messageId === 'string' && nestedRecord.messageId.trim()
      ? nestedRecord.messageId.trim()
      : undefined;

  activateBrowserTakeover({
    reason: String(reason),
    url: typeof urlValue === 'string' ? urlValue : undefined,
    screenshot_base64: typeof screenshot === 'string' ? screenshot : undefined,
    live_assist_url: typeof liveAssistUrl === 'string' ? liveAssistUrl : undefined,
    messageId: payloadMessageId,
    is_managed: isManaged,
    auto_detect_completion: false,
    chat_id: approval.chat_id,
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
  const payloadUrl = asString(nestedPayload.url) || pageUrl;
  const payloadToolName = asString(raw.tool_name ?? nestedPayload.tool_name);
  const payloadReason = asString(raw.reason ?? nestedPayload.reason);
  const screenshotBase64 = asString(nestedPayload.screenshot_base64) || undefined;
  const liveAssistUrl = asString(nestedPayload.live_assist_url) || undefined;
  const isManaged = nestedPayload.is_managed === true;
  const payloadMessageId = asString(nestedPayload.messageId) || undefined;

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
      url: payloadUrl || undefined,
      screenshot_base64: screenshotBase64,
      live_assist_url: liveAssistUrl,
      is_managed: isManaged,
      reason: payloadReason || undefined,
      messageId: payloadMessageId,
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

/** SSOT for browser takeover messageId: payload → assistant → approval queue → session. */
export function resolveBrowserTakeoverMessageId(fallback?: string): string | undefined {
  const trimmed = fallback?.trim();
  if (trimmed) {
    return trimmed;
  }
  const chatState = useChatStore.getState();
  const lastAssistant = [...chatState.messages]
    .reverse()
    .find((message) => message.role === 'assistant');
  if (lastAssistant?.messageId?.trim()) {
    return lastAssistant.messageId.trim();
  }
  const pendingApproval = useApprovalStore
    .getState()
    .queue.find((approval) => approval.action_type === 'browser_takeover');
  const fromApproval = pendingApproval?.payload?.messageId?.trim();
  if (fromApproval) {
    return fromApproval;
  }
  const sessionId = chatState.currentSessionMessageId?.trim();
  return sessionId || undefined;
}

export default useApprovalStore;
