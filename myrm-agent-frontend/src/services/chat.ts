import { API_BASE_URL, apiRequest, fetchWithTimeout } from '@/lib/api';
import type { ExportData } from '@/lib/utils/chatExport';
import { Message, type ActionMode, type ModelSelection } from '@/store/chat/types';
import { requestManager } from '@/lib/utils/requestManager';

export interface ChatItem {
  id: string;
  title: string;
  firstMessage: string;
  lastMessage: string;
  actionMode: string;
  source: string;
  isCompacted?: boolean;
  isPinned?: boolean;
  pinOrder?: number;
  projectId?: string | null;
  updatedAt: Date;
  createdAt: Date;
}

export interface PaginationInfo {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ChatHistoryResponse {
  items: ChatItem[];
  pagination: PaginationInfo;
}

/**
 * 获取聊天历史列表（支持分页、来源和项目过滤）
 */
export const getChatHistory = async (
  page: number = 1,
  pageSize: number = 20,
  source?: string,
  projectId?: string | null,
  keyword?: string,
): Promise<ChatHistoryResponse> => {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (source) params.set('source', source);
  if (projectId) params.set('project_id', projectId);
  if (projectId === null) params.set('unassigned', 'true');
  if (keyword) params.set('keyword', keyword);
  const data = (await apiRequest(`/chats?${params}`)) as {
    items?: unknown[];
    pagination?: PaginationInfo;
  };

  // 从新的响应格式中提取数据
  const items = data.items || [];
  const pagination = data.pagination || {
    page: 1,
    page_size: pageSize,
    total: 0,
    total_pages: 0,
    has_next: false,
    has_prev: false,
  };

  const chatItems = (items as Record<string, unknown>[]).map((chat) => ({
    id: chat.id as string,
    title: (chat.title || chat.firstMessage || 'Untitled Chat') as string,
    firstMessage: (chat.firstMessage || '') as string,
    lastMessage: (chat.lastMessage || '') as string,
    actionMode: (chat.actionMode || 'fast') as string,
    source: (chat.source || 'web') as string,
    isCompacted: Boolean(chat.isCompacted),
    isPinned: Boolean(chat.isPinned),
    pinOrder: (chat.pinOrder as number) || 0,
    projectId: (chat.projectId as string | null) ?? null,
    updatedAt: new Date((chat.updated_at || chat.created_at) as string),
    createdAt: new Date((chat.created_at || chat.updated_at) as string),
  }));

  return {
    items: chatItems,
    pagination,
  };
};

/** 获取最近聊天历史列表，返回 ChatItem 数组。 */
export const getChatHistoryLegacy = async (): Promise<ChatItem[]> => {
  const response = await getChatHistory(1, 50); // 默认获取前50条
  return response.items;
};

export interface SearchResult {
  id: string;
  chat_id: string;
  role: string;
  content: string;
  sent_at: string;
  chat_title: string | null;
  snippet: string;
}

export interface SearchResponse {
  items: SearchResult[];
  total: number;
}

export const searchChatHistory = async (
  query: string,
  limit: number = 20,
  offset: number = 0,
  since?: string,
  until?: string,
): Promise<SearchResponse> => {
  const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
  if (since) params.set('since', since);
  if (until) params.set('until', until);
  const data = (await apiRequest(`/chats/search?${params}`)) as SearchResponse;
  return { items: data.items || [], total: data.total || 0 };
};

/**
 * 获取聊天元数据（不含消息）
 */
export const getChatDetail = async (
  chatId: string,
  silent: boolean = false,
): Promise<{
  chat: {
    id: string;
    title: string | null;
    actionMode: string;
    agent_id: string | null;
    is_incognito: boolean;
    compacted_summary: string | null;
    compacted_before_id: string | null;
    workspace_dir: string | null;
    created_at: string;
    updated_at: string;
  };
  message_count: number;
}> => {
  return apiRequest(`/chats/${chatId}`, { silent });
};

/**
 * Update per-chat working directory
 */
export const updateChatWorkspaceDir = async (
  chatId: string,
  workspaceDir: string | null,
): Promise<{ workspace_dir: string | null }> => {
  return apiRequest(`/chats/${chatId}/workspace`, {
    method: 'PATCH',
    body: JSON.stringify({ workspace_dir: workspaceDir }),
  });
};

export interface DirectoryEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface BrowseResult {
  current: string;
  parent: string | null;
  entries: DirectoryEntry[];
}

/**
 * Browse directories on the server for workspace selection
 */
export const browseDirectories = async (path: string = '~'): Promise<BrowseResult> => {
  const params = new URLSearchParams({ path });
  return apiRequest(`/files/browse?${params}`);
};

// ---------------------------------------------------------------------------
// Workspace file browser API
// ---------------------------------------------------------------------------

export interface FileEntry {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size: number | null;
  mtime: string | null;
  children: FileEntry[] | null;
}

export interface FileTreeResult {
  root: string;
  entries: FileEntry[];
  truncated: boolean;
}

/**
 * Browse workspace directory files with metadata (for file browser UI)
 */
export const browseWorkspaceFiles = async (path: string, depth: number = 2): Promise<FileTreeResult> => {
  const params = new URLSearchParams({ path, depth: String(depth) });
  return apiRequest(`/files/browse/files?${params}`);
};

/**
 * Get workspace file content URL for preview or download
 */
export const getWorkspaceFileContentUrl = (filePath: string, workspace: string, download: boolean = false): string => {
  const params = new URLSearchParams({ path: filePath, workspace });
  if (download) params.set('download', 'true');
  return `${API_BASE_URL}/files/browse/content?${params}`;
};

/**
 * Fetch workspace file content as text for inline preview
 */
export const fetchWorkspaceFileContent = async (filePath: string, workspace: string): Promise<string> => {
  const params = new URLSearchParams({ path: filePath, workspace });
  const res = await fetchWithTimeout(`/files/browse/content?${params}`, { method: 'GET', credentials: 'include' });
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error');
    throw new Error(text);
  }
  return res.text();
};

// ---------------------------------------------------------------------------
// Workspace file write operations API
// ---------------------------------------------------------------------------

export interface WorkspaceUploadResult {
  uploaded_count: number;
  files: Array<{ name: string; path: string; size: number }>;
}

export const uploadToWorkspace = async (
  workspace: string,
  files: File[],
  targetDir: string = '',
  onProgress?: (percent: number) => void,
): Promise<WorkspaceUploadResult> => {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));

  const params = new URLSearchParams({ workspace });
  if (targetDir) params.set('target_dir', targetDir);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE_URL}/files/browse/upload?${params}`);
    xhr.withCredentials = true;

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const res = JSON.parse(xhr.responseText);
        resolve(res.data);
      } else {
        reject(new Error(xhr.responseText || `Upload failed: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.send(formData);
  });
};

export const mkdirInWorkspace = async (workspace: string, path: string): Promise<{ path: string; name: string }> => {
  return apiRequest('/files/browse/mkdir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace, path }),
  });
};

export const renameInWorkspace = async (
  workspace: string,
  path: string,
  newName: string,
): Promise<{ old_name: string; new_name: string; path: string }> => {
  return apiRequest('/files/browse/rename', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace, path, new_name: newName }),
  });
};

export const moveInWorkspace = async (
  workspace: string,
  source: string,
  targetDir: string,
): Promise<{ name: string; old_path: string; new_path: string }> => {
  return apiRequest('/files/browse/move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace, source, target_dir: targetDir }),
  });
};

export const deleteInWorkspace = async (
  workspace: string,
  path: string,
): Promise<{ deleted: string; type: string }> => {
  const params = new URLSearchParams({ workspace, path });
  return apiRequest(`/files/browse/delete?${params}`, { method: 'DELETE' });
};

export const saveWorkspaceFileContent = async (
  workspace: string,
  path: string,
  content: string,
): Promise<{ path: string; name: string; size: number }> => {
  return apiRequest('/files/browse/content', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace, path, content }),
  });
};

// ---------------------------------------------------------------------------
// Structured @ reference suggestion API
// ---------------------------------------------------------------------------

export type ReferenceSuggestionSource = 'workspace' | 'uploaded' | 'generated' | 'special' | 'agent';
export type ReferenceSuggestionType =
  | 'workspace_file'
  | 'workspace_folder'
  | 'uploaded_file'
  | 'generated_file'
  | 'git_diff'
  | 'git_staged'
  | 'url'
  | 'agent';

export interface ReferenceSuggestion {
  source: ReferenceSuggestionSource;
  reference_type: ReferenceSuggestionType;
  kind: 'file' | 'directory' | 'reference' | 'agent';
  label: string;
  basename: string;
  directory: string;
  relative_path: string | null;
  file_id: string | null;
  description: string | null;
  size: number | null;
  score_tier: string;
  score: number;
  match_ranges: Array<[number, number]>;
  avatar_url?: string;
}

export interface ReferenceSuggestResponse {
  results: ReferenceSuggestion[];
  total: number;
}

export interface MentionReferencePayload {
  type: ReferenceSuggestionType;
  path?: string;
  file_id?: string;
  url?: string;
  label?: string;
  start_line?: number;
  end_line?: number;
}

export const suggestReferences = async (
  chatId: string,
  query: string,
  limit: number = 30,
  kind: 'any' | 'file' | 'directory' = 'any',
): Promise<ReferenceSuggestResponse> => {
  const params = new URLSearchParams({ chat_id: chatId, q: query, limit: String(limit), kind });
  return apiRequest(`/files/suggest?${params}`);
};

export interface CursorPage {
  messages: Message[];
  has_more: boolean;
  next_cursor: string | null;
}

/**
 * Cursor-paginated message loading
 */
export const getMessages = async (
  chatId: string,
  options?: { before?: string; limit?: number; silent?: boolean },
): Promise<CursorPage> => {
  const params = new URLSearchParams();
  if (options?.before) params.set('before', options.before);
  if (options?.limit) params.set('limit', String(options.limit));
  const qs = params.toString();
  return apiRequest(`/chats/${chatId}/messages${qs ? `?${qs}` : ''}`, { silent: options?.silent });
};

interface AgentConfigPayload {
  skill_ids: string[];
  enabled_builtin_tools: string[];
  browser_source?: string;
}

export interface StreamRequestBody {
  query: string | object[];
  message_id: string;
  chat_id: string;
  action_mode: ActionMode;
  search_depth?: 'normal' | 'deep';
  model_selection: ModelSelection;
  timezone: string;
  timestamp?: number;
  locale?: string;
  agent_id?: string;
  ephemeral_subagents?: Record<string, unknown>;
  user_instructions?: string;
  lite_model_selection?: ModelSelection;
  fallback_lite_model_selection?: ModelSelection;
  safety_fallback_model_selection?: ModelSelection;
  filter_model_selection?: ModelSelection;
  fallback_model_selection?: ModelSelection;
  fallback_filter_model_selection?: ModelSelection;
  light_model_selection?: ModelSelection;
  fallback_light_model_selection?: ModelSelection;
  reasoning_model_selection?: ModelSelection;
  fallback_reasoning_model_selection?: ModelSelection;
  vision_fallback_model_selection?: ModelSelection;
  mcp_cfg?: object[];
  fetch_raw_webpage?: boolean;
  enable_memory?: boolean;
  memory_require_confirmation?: boolean;
  enable_memory_auto_extraction?: boolean;
  enable_advanced_retrieval?: boolean;
  agent_config?: AgentConfigPayload;
  force_delegate_agent?: string;
  privacy_enabled?: boolean;
  privacy_s2_action?: string;
  privacy_s3_action?: string;
  privacy_routing?: object;
  privacy_custom_keywords_s2?: string[];
  privacy_custom_keywords_s3?: string[];
  privacy_custom_patterns_s2?: string[];
  privacy_custom_patterns_s3?: string[];
  privacy_sensitive_tools_s2?: string[];
  privacy_sensitive_tools_s3?: string[];
  privacy_deep_scan?: boolean;
  user_id?: string;
  task_adaptive_digest?: Record<string, unknown>;
  sibling_group_id?: string;
  regenerate_instruction?: string;
  goal?: {
    max_tokens: number | null;
    acceptance_criteria?: Array<Record<string, unknown>>;
  };
  mention_references?: MentionReferencePayload[];
  quote?: {
    source_message_id: string;
    quoted_text: string;
  };
  resume_value?: unknown;
}

const getActionModeEndpoint = (actionMode: ActionMode): string => {
  switch (actionMode) {
    case 'claude_code':
      throw new Error('claude_code mode should be handled by Tauri IPC, not backend API');
    default:
      return '/agents/agent-stream';
  }
};

/**
 * 创建 AI 搜索流式请求（SSE）。
 * SSE 流式连接的生命周期由 AbortController 控制（用户取消），不设置超时。
 */
export const createAISearchStream = async (
  requestBody: StreamRequestBody,
  abortController?: AbortController,
): Promise<Response> => {
  const controller = abortController || new AbortController();
  requestManager.registerRequest(controller);

  const endpoint = getActionModeEndpoint(requestBody.action_mode);

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (requestBody.chat_id) {
    headers['X-Chat-ID'] = requestBody.chat_id;
  }

  const fetchOptions: RequestInit = {
    method: 'POST',
    headers,
    credentials: 'include',
    body: JSON.stringify(requestBody),
    signal: controller.signal,
  };

  try {
    return await fetchWithTimeout(endpoint, fetchOptions, 0);
  } finally {
    requestManager.unregisterRequest(controller);
  }
};

/**
 * 取消正在运行的Agent请求
 *
 * @param messageId - 要取消的消息ID
 * @returns 取消操作的响应
 */
export const cancelAgentRequest = async (messageId: string): Promise<{ cancelled: boolean }> => {
  return apiRequest(`/agents/agent/${messageId}/cancel`, {
    method: 'POST',
  });
};

/**
 * Cancel the active agent run for a chat (mobile remote / no workspace pane).
 */
export const cancelActiveChatAgent = async (chatId: string): Promise<{ cancelled: boolean; chat_id: string }> => {
  const { isMobileRemoteSurface, mobileRemotePost } = await import('@/lib/mobileRemote');
  if (isMobileRemoteSurface()) {
    return mobileRemotePost<{ cancelled: boolean; chat_id: string }>(
      `/api/v1/agents/chats/${chatId}/cancel`,
      {},
    );
  }
  return apiRequest(`/agents/chats/${chatId}/cancel`, {
    method: 'POST',
  });
};

/**
 * 获取后续建议（搜索模式和 Agent 模式通用）
 *
 * 后端从 UserConfig 表读取 filter model 配置。
 */
export const getSuggestions = async (
  chatHistory: [string, string][],
  abortController?: AbortController,
): Promise<string[]> => {
  const controller = abortController || new AbortController();
  requestManager.registerRequest(controller);

  try {
    const data = (await apiRequest('/agents/suggestions', {
      method: 'POST',
      body: JSON.stringify({ chat_history: chatHistory }),
      signal: controller.signal,
    })) as { suggestions?: string[] };

    return data.suggestions || [];
  } finally {
    requestManager.unregisterRequest(controller);
  }
};

/**
 * 更新聊天标题
 */
export const updateChatTitle = async (chatId: string, title: string): Promise<void> => {
  await apiRequest(`/chats/${chatId}/title`, {
    method: 'PUT',
    body: JSON.stringify({ title }),
  });
};

/**
 * 删除聊天
 */
export const deleteChat = async (chatId: string): Promise<void> => {
  await apiRequest(`/chats/${chatId}`, {
    method: 'DELETE',
  });
};

export const batchDeleteChats = async (ids: string[]): Promise<{ deleted: number; failed: number }> => {
  const data = await apiRequest('/chats/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  });
  return data as { deleted: number; failed: number };
};

/**
 * 从 Conversation Recall 中排除或恢复聊天。
 */
export const updateChatRecallExclusion = async (chatId: string, excluded: boolean): Promise<void> => {
  await apiRequest(`/chats/${chatId}/recall-exclusion`, {
    method: 'PATCH',
    body: JSON.stringify({ excluded }),
  });
};

export interface ConversationRecallEntry {
  chat_id: string;
  title: string | null;
  agent_id: string | null;
  source: string;
  snippet: string;
  summary: string | null;
  last_message_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  is_excluded: boolean;
}

export interface ConversationRecallListResponse {
  items: ConversationRecallEntry[];
  pagination: PaginationInfo;
}

export const listConversationRecallEntries = async (params: {
  excluded?: boolean;
  page?: number;
  pageSize?: number;
}): Promise<ConversationRecallListResponse> => {
  const query = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  });
  if (params.excluded !== undefined) query.set('excluded', String(params.excluded));
  const data = (await apiRequest(`/chats/recall/entries?${query}`)) as ConversationRecallListResponse;
  return {
    items: data.items || [],
    pagination: data.pagination,
  };
};

/**
 * Fetch all chat data for export (metadata + messages).
 */
export const exportChat = async (chatId: string): Promise<ExportData> => {
  return apiRequest(`/chats/${chatId}/export`) as Promise<ExportData>;
};

/**
 * 生成聊天标题
 *
 * 不再发送 API Key，后端从 UserConfig 表读取 filter model 配置。
 */
export const generateChatTitle = async (messages: Message[], abortController?: AbortController): Promise<string> => {
  const controller = abortController || new AbortController();
  requestManager.registerRequest(controller);

  try {
    const data = (await apiRequest('/chats/generate-title', {
      method: 'POST',
      body: JSON.stringify({ messages }),
      signal: controller.signal,
    })) as { title?: string };

    return data.title || 'Untitled Chat';
  } finally {
    requestManager.unregisterRequest(controller);
  }
};

export interface CompactResult {
  compacted: boolean;
  message_count: number;
  tokens_saved: number;
  reason: string | null;
  focus_topic?: string;
}

export const compactChat = async (chatId: string, focusTopic?: string): Promise<CompactResult> => {
  const body = focusTopic ? JSON.stringify({ focus_topic: focusTopic }) : undefined;
  return (await apiRequest(`/chats/${chatId}/compact`, {
    method: 'POST',
    ...(body ? { body } : {}),
  })) as CompactResult;
};

export const focusFlushChat = async (chatId: string): Promise<{ cleared: boolean }> => {
  return (await apiRequest(`/chats/${chatId}/messages`, {
    method: 'DELETE',
  })) as { cleared: boolean };
};

export interface RegenerateResult {
  success: boolean;
  query: string;
  sibling_group_id: string;
  instruction?: string | null;
}

/**
 * Regenerate: mark old assistant messages as inactive siblings and return the query.
 */
export const regenerateLastTurn = async (chatId: string, instruction?: string): Promise<RegenerateResult> => {
  return (await apiRequest(`/chats/${chatId}/regenerate`, {
    method: 'POST',
    body: JSON.stringify(instruction ? { instruction } : {}),
  })) as RegenerateResult;
};

/**
 * Switch the active sibling in a sibling group.
 */
export const switchSibling = async (
  chatId: string,
  siblingGroupId: string,
  targetMessageId: string,
): Promise<{ success: boolean }> => {
  return (await apiRequest(`/chats/${chatId}/switch-sibling`, {
    method: 'POST',
    body: JSON.stringify({ sibling_group_id: siblingGroupId, target_message_id: targetMessageId }),
  })) as { success: boolean };
};

export interface SiblingInfo {
  id: string;
  is_active: boolean;
  created_at: string;
}

/**
 * Get all siblings in a group.
 */
export const getSiblings = async (chatId: string, siblingGroupId: string): Promise<{ siblings: SiblingInfo[] }> => {
  return (await apiRequest(`/chats/${chatId}/siblings/${siblingGroupId}`)) as { siblings: SiblingInfo[] };
};

export interface UndoResult {
  success: boolean;
  deleted_count: number;
}

/**
 * Undo the last turn: delete both user message and assistant responses.
 */
export const undoLastTurn = async (chatId: string): Promise<UndoResult> => {
  return (await apiRequest(`/chats/${chatId}/undo`, {
    method: 'POST',
  })) as UndoResult;
};

export interface TruncateResult {
  success: boolean;
  deleted_count: number;
}

/**
 * Truncate: delete a message and everything after it.
 * Used by edit-resend to sync backend before re-sending the edited message.
 */
export const truncateAfterMessage = async (chatId: string, messageId: string): Promise<TruncateResult> => {
  return (await apiRequest(`/chats/${chatId}/truncate-after`, {
    method: 'POST',
    body: JSON.stringify({ message_id: messageId }),
  })) as TruncateResult;
};

/**
 * Submit user's answer to a Deep Research clarification question.
 */
export const submitClarifyResponse = async (
  messageId: string,
  answer: string | string[] | Record<string, string | string[]>,
): Promise<void> => {
  await apiRequest('/agents/clarify-response', {
    method: 'POST',
    body: JSON.stringify({ messageId, answer }),
  });
};

/**
 * Submit user's response to a Deep Research plan confirmation gate.
 * @param action - "confirm" (use as-is), "edit" (use modified plan), "skip" (skip gate)
 */
export const submitPlanConfirmResponse = async (
  messageId: string,
  action: 'confirm' | 'edit' | 'skip',
  modifiedPlan?: string,
): Promise<void> => {
  await apiRequest('/agents/plan-confirm-response', {
    method: 'POST',
    body: JSON.stringify({ messageId, action, modifiedPlan }),
  });
};

/**
 * Retrieve all archived messages from the workspace backup files.
 */
export const getChatArchive = async (chatId: string): Promise<{ messages: Message[] }> => {
  return apiRequest(`/chats/${chatId}/archive`);
};

/**
 * Update the compacted summary for a chat (Intervention API).
 */
export const updateCompactionSummary = async (chatId: string, summary: string): Promise<void> => {
  await apiRequest(`/chats/${chatId}/compaction/summary`, {
    method: 'PUT',
    body: JSON.stringify({ summary }),
  });
};

export interface CatchupBrief {
  chat_id: string;
  chat_title: string;
  updated_at: string;
  last_user_prompt: string;
  latest_agent_response: string;
  files_touched: string[];
  tool_counts: Record<string, number>;
  activity_steps: string[];
  needs_from_user: string | null;
  status: string;
}

export interface CatchupResponse {
  briefs: CatchupBrief[];
}

/**
 * Fetch catchup briefs for all unread chats.
 */
export const getCatchupBriefs = async (): Promise<CatchupResponse> => {
  return apiRequest(`/chats/catchup?t=${Date.now()}`);
};

/**
 * Mark a chat as read.
 */
export const markChatAsRead = async (chatId: string): Promise<void> => {
  await apiRequest(`/chats/${chatId}/read`, {
    method: 'POST',
  });
};

// ── Pinned Threads ──────────────────────────────────────────────

export const pinChat = async (chatId: string): Promise<{ isPinned: boolean; pinOrder: number }> => {
  return apiRequest(`/chats/${chatId}/pin`, { method: 'PATCH' });
};

export const unpinChat = async (chatId: string): Promise<void> => {
  await apiRequest(`/chats/${chatId}/unpin`, { method: 'PATCH' });
};

export const reorderPinnedChats = async (items: { id: string; pin_order: number }[]): Promise<void> => {
  await apiRequest('/chats/pin-reorder', {
    method: 'PUT',
    body: JSON.stringify({ items }),
    headers: { 'Content-Type': 'application/json' },
  });
};

// ── Session Handoff ──────────────────────────────────────────────

export interface HandoffResponse {
  targetChannel: string;
  targetSessionKey: string;
}

export const handoffChat = async (chatId: string, targetChannel: string): Promise<HandoffResponse> => {
  const res = await apiRequest<{ data: HandoffResponse }>(`/chats/${chatId}/handoff`, {
    method: 'POST',
    body: JSON.stringify({ target_channel: targetChannel }),
    headers: { 'Content-Type': 'application/json' },
  });
  return res.data;
};

// ── Fission Topology ─────────────────────────────────────────────

export interface FissionTopologyResponse {
  fission_id: string;
  nodes: import('@/store/chat/types').FissionTopologyNode[];
  total_cost_usd: number;
}

export const getFissionTopology = async (chatId: string): Promise<FissionTopologyResponse | null> => {
  try {
    const res = await apiRequest<{ data: FissionTopologyResponse | null }>(`/chats/${chatId}/fission`);
    return res?.data || null;
  } catch (error) {
    console.error('Failed to fetch fission topology:', error);
    return null;
  }
};
