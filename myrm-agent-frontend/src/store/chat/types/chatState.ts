/**
 * [INPUT]
 * ./messages::Message (POS: 持久化与渲染用的聊天消息实体)
 * ./sessionConfig::AgentConfig (POS: 会话级 Agent 与模式配置类型)
 * 
 * [OUTPUT]
 * ChatState 接口（Zustand 形状 + actions）。
 * 
 * [POS]
 * useChatStore 状态与操作方法契约。
 */

import type { ActionMode, AgentConfig, SearchDepth, SelectedModels } from './sessionConfig';
import type { ArchiveRestoreAction } from './archiveRestore';
import type { BuiltinToolId } from './builtinTools';
import type {
  ChatHistoryItem,
  File,
  MentionReference,
  Message,
  PaginationInfo,
} from './messages';
import type { PendingGapRetry } from './pendingGapRetry';

export interface ChatState {
  // 聊天基本信息
  chatId: string | undefined;
  newChatCreated: boolean;
  messages: Message[];
  compactedSummary: string | null;
  compactedBeforeId: string | null;
  workspaceDir: string | null;
  sessionSkillOverrides: string[] | null;

  // 聊天历史列表（分页）
  chatHistoryItems: ChatHistoryItem[];
  chatHistoryPagination: PaginationInfo | null;
  chatHistoryLoading: boolean;
  chatHistoryError: string | null;
  chatHistorySourceFilter: string | null;
  chatHistoryAvailableSources: string[];

  // 聊天文件
  files: File[];
  cameraFrames: string[];
  hideAttachList: boolean;
  hasUsedImagesInCurrentChat: boolean;

  // @ 结构化上下文引用
  mentionReferences: MentionReference[];

  // 操作模式配置
  actionMode: ActionMode;
  searchDepth: SearchDepth;
  optimizationMode: string;
  isGoalMode: boolean;
  isWorkflowMode: boolean;
  incognitoMode: boolean;
  sandboxMode: boolean;
  goalBudgetTokens: number | null;
  goalBudgetUsd: number | null;
  goalMaxTimeSeconds: number | null;
  goalMaxTurns: number | null;
  goalProtectedPaths: string[] | null;
  goalLoopOnPause: boolean;
  goalConvergenceWindow: number | null;
  goalAcceptanceCriteria: Array<Record<string, unknown>> | null;
  goalConstraints: string[] | null;

  // 智能代理模式工具开关（当前会话临时配置，切换 Agent 时从永久配置初始化）
  currentBuiltinTools: BuiltinToolId[];

  // 智能体配置
  agentConfig: AgentConfig | null;

  // 模型选择
  selectedModels: SelectedModels;
  hasUserSelectedModel: boolean;

  // 当前输入框内容（用于实时 Token 估算）
  inputMessage: string;
  pendingArchiveRestoreAction: ArchiveRestoreAction | null;
  pendingArchiveRestoreActions: ArchiveRestoreAction[];

  // Deferred entitlement-gap resend (set on preflight gap, flushed after MESSAGE_END)
  pendingGapRetry: PendingGapRetry | null;

  // 消息状态
  loading: boolean;
  loadingOlder: boolean;
  hasMoreMessages: boolean;
  nextCursor: string | null;
  messageAppeared: boolean;
  isMessagesLoaded: boolean;
  notFound: boolean;
  loadError: boolean;

  // 请求控制
  abortController: AbortController | null;

  // Regenerate sibling 状态（临时，单次请求后清除）
  regenerateSiblingGroupId?: string;
  regenerateInstruction?: string;

  // 当前会话的messageId - 用于确保文件上传和消息发送使用相同的ID
  currentSessionMessageId: string | null;

  // 智能体配置面板展开状态
  isConfigPanelExpanded: boolean;

  // 环境约束状态 — 由 SSE 事件流中的 error_category 驱动
  environmentAlerts: Set<string>;

  // 自动保存定时器 - 用于防抖
  _autoSaveTimer: NodeJS.Timeout | null;
  _messageUpdateScheduled: boolean;

  // Subagent 智能提示状态
  subagentPromptVisible: boolean;
  subagentPromptTimer: NodeJS.Timeout | null;
  subagentPromptMessageId: string | null;

  // 性能诊断弹窗状态
  activeSessionAnalyticsId: string | null;
  activeSessionAnalyticsMessageId: string | null;

  // 侧边栏会话实时状态（generating / awaiting_approval）
  sessionStatuses: Record<string, string>;

  // 安全状态更新方法 (支持 immer)
  updateMessages: (updater: (state: ChatState) => void) => void;

  // 操作方法
  setChatId: (id: string | undefined) => void;
  setNewChatCreated: (created: boolean) => void;
  setMessages: (messages: Message[]) => void;
  setCompactedSummary: (summary: string | null) => void;
  setCompactedBeforeId: (id: string | null) => void;
  setWorkspaceDir: (dir: string | null) => void;
  setChatHistoryItems: (items: ChatHistoryItem[]) => void;
  setChatHistoryPagination: (pagination: PaginationInfo | null) => void;
  setChatHistoryLoading: (loading: boolean) => void;
  setChatHistorySourceFilter: (source: string | null) => void;
  setFiles: (files: File[]) => void;
  setCameraFrames: (frames: string[]) => void;
  setHideAttachList: (hide: boolean) => void;
  setHasUsedImagesInCurrentChat: (hasUsed: boolean) => void;
  addMentionReference: (reference: MentionReference) => void;
  removeMentionReference: (key: string) => void;
  clearMentionReferences: () => void;
  setActionMode: (mode: ActionMode) => void;
  setSearchDepth: (depth: SearchDepth) => void;
  setOptimizationMode: (mode: string) => void;
  setIsGoalMode: (isGoalMode: boolean) => void;
  setIsWorkflowMode: (isWorkflowMode: boolean) => void;
  setIncognitoMode: (incognitoMode: boolean) => void;
  setSessionSkillOverrides: (overrides: string[] | null) => void;
  setSandboxMode: (sandboxMode: boolean) => void;
  setGoalBudgetTokens: (tokens: number | null) => void;
  setGoalBudgetUsd: (usd: number | null) => void;
  setGoalMaxTimeSeconds: (seconds: number | null) => void;
  setGoalMaxTurns: (turns: number | null) => void;
  setGoalProtectedPaths: (paths: string[] | null) => void;
  setGoalLoopOnPause: (loop: boolean) => void;
  setGoalConvergenceWindow: (window: number | null) => void;
  setGoalAcceptanceCriteria: (criteria: Array<Record<string, unknown>> | null) => void;
  setGoalConstraints: (constraints: string[] | null) => void;
  toggleBuiltinTool: (toolId: BuiltinToolId) => void;
  setCurrentBuiltinTools: (tools: BuiltinToolId[]) => void;
  setAgentConfig: (config: AgentConfig | null) => void;
  updateAgentConfig: (partial: Partial<AgentConfig>) => void;
  setSelectedModels: (models: SelectedModels) => void;
  setInputMessage: (message: string) => void;
  setPendingArchiveRestoreAction: (action: ArchiveRestoreAction | null) => void;
  setPendingArchiveRestoreActions: (actions: ArchiveRestoreAction[]) => void;
  setPendingGapRetry: (pending: PendingGapRetry | null) => void;
  clearPendingGapRetry: () => void;
  setLoading: (loading: boolean) => void;
  setMessageAppeared: (appeared: boolean) => void;
  setIsMessagesLoaded: (loaded: boolean) => void;
  setNotFound: (notFound: boolean) => void;
  setLoadError: (loadError: boolean) => void;
  setActiveSessionAnalyticsId: (id: string | null) => void;
  setActiveSessionAnalyticsMessageId: (id: string | null) => void;
  setSessionStatus: (chatId: string, status: string) => void;
  initSessionStatuses: (statuses: Record<string, string>) => void;

  // 配置面板展开状态
  setConfigPanelExpanded: (expanded: boolean) => void;
  toggleConfigPanel: () => void;

  // 环境约束
  addEnvironmentAlert: (category: string) => void;
  clearEnvironmentAlerts: () => void;

  // 请求控制方法
  stopMessage: () => void;
  steerMessage: (message: string) => Promise<boolean>;

  // 当前会话messageId管理
  getCurrentSessionMessageId: () => string;
  clearCurrentSessionMessageId: () => void;
  resetSessionState: () => void;

  // Subagent 智能提示方法
  setSubagentPromptVisible: (visible: boolean) => void;
  clearSubagentPromptTimer: () => void;
  triggerSubagentPrompt: (messageId: string) => void;

  // 获取消息内容
  getMessageContent: (index: number) => string;
  // 获取聊天历史
  getChatHistory: (endIndex: number) => Message[];

  // 聊天功能
  sendMessage: (
    input: string,
    messageId?: string,
    errorMessage?: string,
    resumeValue?: unknown,
    archiveRestoreActions?: ArchiveRestoreAction[],
  ) => Promise<void>;
  // 初始化方法
  loadMessages: (chatId: string) => Promise<void>;
  loadOlderMessages: () => Promise<void>;
  initializeChat: (id?: string, initialMessage?: string | null) => void;
  scheduleAutoSave: () => void;

  // 分页聊天历史管理
  loadChatHistory: (page?: number, pageSize?: number) => Promise<void>;
  loadMoreChatHistory: () => Promise<void>;

  // Pinned Threads
  pinChat: (chatId: string) => Promise<void>;
  unpinChat: (chatId: string) => Promise<void>;
  reorderPinnedChats: (orderedIds: string[]) => Promise<void>;

  // 内部辅助方法
  _processSuggestions: (lastMsg: Message) => Promise<void>;
  // 内部辅助变量
  isReady: boolean;
}
